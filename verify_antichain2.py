#!/usr/bin/env python3
"""verify_antichain2.py — independent checker for feasible-set LP (antichain LP) lower-bound certificates, without clique enumeration
(J1, written 2026-10-25 s5; NOT YET AUDITED: claims judged by it count only after a fresh-session audit, per the README rule).

Same claim format and argument as verify_antichain.py (non-destructive mode only):
    claim JSON {"instance": "RG300_<id>.rcp", "lb": L, "y": {"<1-based activity id>": "p/q", ...}, "destructive_T": null}
In any feasible schedule the set F_t of activities running in period t is a feasible set: no member precedes another (transitively) and
the members' demands fit every renewable capacity jointly. Activity j runs in exactly d_j periods, so for weights y >= 0 with
y(F) <= 1 for every feasible set F:   sum_j d_j y_j = sum_t y(F_t) <= T,   hence T >= ceil(sum_j d_j y_j).
Check.
 (1) Own reachability (DFS from every activity over the successor lists) and own pairwise compatibility on the support S of y:
     a ~ b iff neither reaches the other and dem_a[k] + dem_b[k] <= C_k for every resource k.
 (2) Integer weights w_j = y_j * Q over the common denominator Q. Decision search: is there a feasible set F within S with w(F) > Q?
     Depth-first over S in a fixed order (weight descending); a node holds the chosen set (pairwise compatible, fitting the
     capacities), its weight, the residual capacities and the candidate list = later items compatible with every chosen item and
     individually fitting the residual capacities. Every feasible set is reached exactly along its own ordered sequence of members.
     A node is pruned when  weight + U <= Q, where U is an upper bound on the weight addable from the candidates:
       U = min( sum of the candidates' weights,  min_k  F_k )   with F_k the fractional-knapsack (LP) optimum of
       max sum w_x z_x  s.t.  sum dem_x[k] z_x <= residual_k,  0 <= z <= 1  over the candidates (items with dem_x[k] = 0 enter whole).
     Any feasible extension is a 0/1 point of each of these relaxations, so pruning never discards a set of weight > Q.
     If any node has weight > Q: FAILED (a feasible set violates the dual constraint). A node cap makes the checker FAIL, never pass.
 (3) The bound sum_j d_j y_j in exact rationals; the claimed lb must not exceed its ceiling.
Usage: verify_antichain2.py <instance> <claim.json> [--lb L] [--ub U] [--max-nodes N]  -> VERIFIED LB>=... (exit 0) | FAILED: reason (exit 1)
Nothing is shared with the solver (tools/aclp_cg2.py, tools/colorprice*.py) or with verify_antichain.py; only verify.py's audited parser.
"""
import sys, os, json
from fractions import Fraction
from math import lcm
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import load_instance


def fail(msg):
    print("FAILED: " + msg); sys.exit(1)


def main(argv):
    if len(argv) < 2: fail("usage: verify_antichain2.py <instance> <claim.json> [--lb L] [--ub U] [--max-nodes N]")
    inst = load_instance(argv[0]); claim = json.load(open(argv[1]))
    lb_pub = ub_pub = None; max_nodes = 200_000_000; i = 2
    while i < len(argv):
        if argv[i] == "--lb": lb_pub = int(argv[i + 1]); i += 2
        elif argv[i] == "--ub": ub_pub = int(argv[i + 1]); i += 2
        elif argv[i] == "--max-nodes": max_nodes = int(argv[i + 1]); i += 2
        else: fail("unknown argument %s" % argv[i])
    if claim.get("destructive_T") is not None: fail("destructive certificates are not supported by this checker")
    n = inst["n"]; C = list(inst["ren"]); K = len(C)
    if inst.get("nonren"): fail("nonrenewable resources present")
    if any(len(a["modes"]) != 1 for a in inst["acts"]): fail("multi-mode instance")
    dur = [a["modes"][0][0] for a in inst["acts"]]; dem = [list(a["modes"][0][1]) for a in inst["acts"]]
    succ = [[s - 1 for s in a["succ"]] for a in inst["acts"]]
    L = claim.get("lb")
    if not isinstance(L, int): fail("lb missing or not an integer")
    y = {}
    for key, val in claim.get("y", {}).items():
        j = int(key) - 1
        if not 0 <= j < n or str(j + 1) != key: fail("bad activity id %r" % key)
        f = Fraction(val)
        if f < 0: fail("negative weight on %s" % key)
        if f > 0: y[j] = f
    if not y: fail("empty certificate")
    # (1) reachability by iterative DFS, compatibility on the support
    reach = []
    for s0 in range(n):
        seen = set(); st = list(succ[s0])
        while st:
            v = st.pop()
            if v not in seen: seen.add(v); st.extend(succ[v])
        reach.append(seen)
    S = sorted(y, key=lambda j: (-y[j], j))
    for j in S:
        if any(dem[j][k] > C[k] for k in range(K)): fail("activity %d exceeds a capacity on its own" % (j + 1))
    pos = {j: t for t, j in enumerate(S)}; m = len(S)
    comp = [[False] * m for _ in range(m)]
    for a in range(m):
        for b in range(a + 1, m):
            ja, jb = S[a], S[b]
            ok = jb not in reach[ja] and ja not in reach[jb] and all(dem[ja][k] + dem[jb][k] <= C[k] for k in range(K))
            comp[a][b] = comp[b][a] = ok
    # (2) integer weights and the decision search
    Q = 1
    for j in S: Q = lcm(Q, y[j].denominator)
    w = [int(y[j] * Q) for j in S]
    D = [[dem[j][k] for k in range(K)] for j in S]
    ratio_order = []   # per resource: positions sorted by w / dem descending (dem 0 first)
    for k in range(K):
        ratio_order.append(sorted(range(m), key=lambda p: (D[p][k] != 0, -Fraction(w[p], D[p][k]) if D[p][k] else 0, p)))
    nodes = [0]; found = [None]

    def addable_bound(cands, res):
        """returns an upper bound (Fraction) on the weight a feasible subset of cands can add under residual capacities res."""
        cset = set(cands); best = Fraction(sum(w[p] for p in cands))
        for k in range(K):
            cap = res[k]; val = Fraction(0)
            for p in ratio_order[k]:
                if p not in cset: continue
                dk = D[p][k]
                if dk == 0: val += w[p]
                elif dk <= cap: val += w[p]; cap -= dk
                else: val += Fraction(w[p] * cap, dk); break
            if val < best: best = val
        return best

    def dfs(chosen, weight, res, cands):
        nodes[0] += 1
        if nodes[0] > max_nodes: return "CAP"
        if weight > Q: found[0] = [S[p] + 1 for p in chosen]; return "FOUND"
        if not cands: return None
        if weight + sum(w[p] for p in cands) <= Q: return None
        if weight + addable_bound(cands, res) <= Q: return None
        for t, p in enumerate(cands):
            r2 = [res[k] - D[p][k] for k in range(K)]
            c2 = [q for q in cands[t + 1:] if comp[p][q] and all(D[q][k] <= r2[k] for k in range(K))]
            chosen.append(p); out = dfs(chosen, weight + w[p], r2, c2); chosen.pop()
            if out: return out
        return None

    sys.setrecursionlimit(10000)
    out = dfs([], 0, list(C), list(range(m)))
    if out == "CAP": fail("node cap %d reached: unable to check" % max_nodes)
    if out == "FOUND": fail("feasible set %s has y-weight > 1" % found[0])
    # (3) the bound
    B = sum(dur[j] * y[j] for j in S)
    ceil_B = -((-B.numerator) // B.denominator)
    if L > ceil_B: fail("claimed lb %d exceeds ceil(sum d*y) = %d" % (L, ceil_B))
    msg = "VERIFIED LB>=%d (support %d activities, %d compatible pairs, decision search %d nodes, max feasible weight <= 1, sum d*y = %s, ceiling %d)" % (
        L, m, sum(comp[a][b] for a in range(m) for b in range(a + 1, m)), nodes[0], B, ceil_B)
    if lb_pub is not None: msg += " published_lb=%d %s" % (lb_pub, "IMPROVES" if L > lb_pub else "MATCHES" if L == lb_pub else "WORSE")
    if ub_pub is not None: msg += " published_ub=%d%s" % (ub_pub, " CLOSES" if L >= ub_pub else "")
    print(msg); sys.exit(0)


if __name__ == "__main__":
    main(sys.argv[1:])
