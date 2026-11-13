#!/usr/bin/env python3
"""verify_antichain.py — independent checker for feasible-set LP (antichain LP) lower-bound certificates (J1, written 2026-10-25 s1).

Claim JSON: {"instance": "RG300_73.rcp", "lb": L, "y": {"<1-based activity id>": "p/q", ...}, "destructive_T": null | T0}  (positive weights only)
Destructive mode (T0 given): under the hypothesis that the makespan is <= T0 every activity runs inside its window [ES_j, LF_j(T0)] (longest
paths), so two activities with disjoint windows are also incompatible. If then ceil(sum_j d_j y_j) > T0 the hypothesis is refuted and the
makespan is >= T0 + 1; the certified bound is T0 + 1 (the claimed lb must not exceed it). If the ceiling does not exceed T0, nothing follows: FAILED.
Argument. In any feasible schedule, the set F_t of activities running in period t is a *feasible set*: no member precedes another
(transitively), and the demands of its members fit every renewable capacity jointly. Activity j runs in exactly d_j periods. Hence for
weights y >= 0 with  sum_{j in F} y_j <= 1  for every feasible set F,
    sum_j d_j y_j = sum_t sum_{j in F_t} y_j <= T,   so  T >= ceil(sum_j d_j y_j).
Check. (1) Build the compatibility graph on the support S of y: a ~ b iff neither precedes the other (BFS reachability from every node)
and their demands fit together on every resource. Every feasible set inside S is a clique of this graph, so (2) enumerate the maximal
cliques of the graph (Bron–Kerbosch with pivoting); for each one whose y-sum exceeds 1, (3) enumerate its subsets that fit the capacities
jointly and require every such subset to have y-sum <= 1. All sums in exact rationals (integers over the common denominator).
(4) The bound sum_j d_j y_j is computed exactly and the claimed lb must not exceed its ceiling.
If the maximal-clique enumeration exceeds a hard cap the checker FAILS (unable to check), never passes.
Usage: verify_antichain.py <instance> <claim.json> [--lb L] [--ub U] [--max-cliques N]  -> VERIFIED LB>=... (exit 0) | FAILED: reason (exit 1)
Nothing is shared with the solver (tools/antichain_lp.py) except the audited instance parser of verify.py.
"""
import sys, os, json
from fractions import Fraction
from math import gcd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import load_instance


def reachability(inst):
    n = inst["n"]; succ = [[s - 1 for s in x["succ"]] for x in inst["acts"]]
    reach = []
    for a in range(n):
        seen = set(); stack = list(succ[a])
        while stack:
            v = stack.pop()
            if v in seen: continue
            seen.add(v); stack.extend(succ[v])
        reach.append(seen)
    return reach


def windows(inst, T0):
    """ES by forward longest paths, LF = T0 - longest path from the activity's end to the sink; iterative Bellman-style relaxation."""
    n = inst["n"]; dur = [x["modes"][0][0] for x in inst["acts"]]; succ = [[s - 1 for s in x["succ"]] for x in inst["acts"]]
    es = [0] * n
    for _ in range(n + 1):
        changed = False
        for a in range(n):
            for s_ in succ[a]:
                if es[s_] < es[a] + dur[a]: es[s_] = es[a] + dur[a]; changed = True
        if not changed: break
    else:
        raise ValueError("precedence graph has a cycle")
    tail = [0] * n
    for _ in range(n + 1):
        changed = False
        for a in range(n):
            for s_ in succ[a]:
                if tail[a] < dur[s_] + tail[s_]: tail[a] = dur[s_] + tail[s_]; changed = True
        if not changed: break
    return es, [T0 - tail[a] for a in range(n)]


def parse_frac(s):
    if isinstance(s, bool): raise ValueError("boolean weight")
    if isinstance(s, int): return Fraction(s)
    if isinstance(s, str): return Fraction(s.strip())
    raise ValueError("weight must be an integer or a 'p/q' string")


def maximal_cliques(adj, verts, cap):
    """Bron–Kerbosch with pivoting over bitmasks; adj[v] = bitmask of neighbours. Yields maximal cliques as bitmasks; raises on cap."""
    out = []
    def bk(R, P, X):
        if not P and not X:
            out.append(R)
            if len(out) > cap: raise OverflowError("too many maximal cliques")
            return
        # pivot: vertex of P|X with most neighbours in P
        PX = P | X; best = -1; u = -1; c = PX
        while c:
            low = c & -c; v = low.bit_length() - 1; c ^= low
            k = bin(adj[v] & P).count("1")
            if k > best: best = k; u = v
        cand = P & ~adj[u]
        while cand:
            low = cand & -cand; v = low.bit_length() - 1; cand ^= low
            bk(R | low, P & adj[v], X & adj[v])
            P &= ~low; X |= low
    allv = 0
    for v in verts: allv |= 1 << v
    sys.setrecursionlimit(10000)
    bk(0, allv, 0)
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    inst_path, claim_path = argv[0], argv[1]
    lb_pub = ub_pub = None; cap = 5_000_000
    for i, a in enumerate(argv):
        if a == "--lb": lb_pub = int(argv[i + 1])
        if a == "--ub": ub_pub = int(argv[i + 1])
        if a == "--max-cliques": cap = int(argv[i + 1])
    claim = json.load(open(claim_path)); inst = load_instance(inst_path)
    name = os.path.basename(inst_path)
    if claim.get("instance") != name:
        print("FAILED: claim is for %s, instance given is %s" % (claim.get("instance"), name)); return 1
    n = inst["n"]; C = inst["ren"]; K = len(C)
    L = claim.get("lb")
    if not isinstance(L, int) or isinstance(L, bool) or L < 0:
        print("FAILED: lb must be a non-negative integer"); return 1
    T0 = claim.get("destructive_T")
    if T0 is not None and (not isinstance(T0, int) or isinstance(T0, bool) or T0 < 0):
        print("FAILED: destructive_T must be null or a non-negative integer"); return 1
    yraw = claim.get("y")
    if not isinstance(yraw, dict) or not yraw:
        print("FAILED: y must be a non-empty object {activity: weight}"); return 1
    y = {}
    try:
        for k, v in yraw.items():
            j = int(k)
            if not 1 <= j <= n: print("FAILED: activity %s out of range 1..%d" % (k, n)); return 1
            if j - 1 in y: print("FAILED: activity %d listed twice" % j); return 1
            f = parse_frac(v)
            if f <= 0: print("FAILED: weight of activity %d is not positive (%s)" % (j, v)); return 1
            y[j - 1] = f
    except (ValueError, ZeroDivisionError) as e:
        print("FAILED: bad weight (%s)" % e); return 1
    dur = [x["modes"][0][0] for x in inst["acts"]]; dem = [x["modes"][0][1] for x in inst["acts"]]
    for j in y:
        if any(dem[j][k] > C[k] for k in range(K)):
            print("FAILED: activity %d alone exceeds a capacity (instance infeasible?)" % (j + 1)); return 1
    # common denominator -> integer weights
    den = 1
    for f in y.values(): den = den * f.denominator // gcd(den, f.denominator)
    w = {j: int(f * den) for j, f in y.items()}  # exact
    S = sorted(y)
    reach = reachability(inst)
    es = lf = None
    if T0 is not None:
        es, lf = windows(inst, T0)
        if any(es[j] + dur[j] > lf[j] for j in range(n)):
            # the critical path alone exceeds T0: the hypothesis is refuted without the LP
            if L > T0 + 1: print("FAILED: claimed lb %d exceeds T0 + 1 = %d" % (L, T0 + 1)); return 1
            print("VERIFIED LB>=%d (critical path exceeds the hypothesis T<=%d; no LP argument needed)" % (L, T0)); return 0
    adj = {}
    n_prec = n_res = n_win = 0
    for p in range(len(S)):
        a = S[p]; adj.setdefault(a, 0)
        for q in range(p + 1, len(S)):
            b = S[q]; adj.setdefault(b, 0)
            if b in reach[a] or a in reach[b]: n_prec += 1; continue
            if any(dem[a][k] + dem[b][k] > C[k] for k in range(K)): n_res += 1; continue
            if T0 is not None and (es[a] >= lf[b] or es[b] >= lf[a]): n_win += 1; continue
            adj[a] |= 1 << b; adj[b] |= 1 << a
    try:
        cliques = maximal_cliques(adj, S, cap)
    except OverflowError:
        print("FAILED: more than %d maximal cliques in the compatibility graph of the support; unable to check (not a refutation)" % cap); return 1
    except RecursionError:
        print("FAILED: recursion limit in clique enumeration; unable to check"); return 1
    max_sum = 0; n_knap = 0; worst = None
    for Q in cliques:
        members = []; c = Q
        while c:
            low = c & -c; v = low.bit_length() - 1; c ^= low; members.append(v)
        tot = sum(w[v] for v in members)
        if tot <= den:
            if tot > max_sum: max_sum = tot; worst = members
            continue
        # subsets of the clique that fit the capacities jointly: DFS with exact weights
        n_knap += 1
        members.sort(key=lambda v: -w[v])
        m = len(members); suffix = [0] * (m + 1)
        for i in range(m - 1, -1, -1): suffix[i] = suffix[i + 1] + w[members[i]]
        best = [max_sum, None]
        def dfs(i, cur, ws, use):
            if ws > best[0]: best[0] = ws; best[1] = list(cur)
            if i == m or ws + suffix[i] <= best[0]: return
            v = members[i]; dv = dem[v]
            if all(use[k] + dv[k] <= C[k] for k in range(K)):
                cur.append(v); dfs(i + 1, cur, ws + w[v], [use[k] + dv[k] for k in range(K)]); cur.pop()
            dfs(i + 1, cur, ws, use)
        dfs(0, [], 0, [0] * K)
        if best[0] > max_sum: max_sum = best[0]; worst = best[1]
        if max_sum > den:
            print("FAILED: feasible set %s has weight %s > 1 (y is not dual-feasible)" % ([v + 1 for v in worst], Fraction(max_sum, den))); return 1
    bound = sum(Fraction(dur[j], 1) * y[j] for j in y)
    ceil_b = -((-bound.numerator) // bound.denominator)
    if T0 is None:
        certified = ceil_b
    else:
        if ceil_b <= T0:
            print("FAILED: under T<=%d the LP bound ceil(%s) = %d does not exceed T0 (hypothesis not refuted; no bound follows)" % (T0, bound, ceil_b)); return 1
        certified = T0 + 1
    if L > certified:
        print("FAILED: claimed lb %d exceeds the certified bound %d (sum d*y = %s%s)" % (L, certified, bound, "" if T0 is None else ", T0=%d" % T0)); return 1
    msg = "VERIFIED LB>=%d (support %d activities, %d precedence pairs, %d resource pairs%s, %d maximal cliques, %d knapsack checks, max feasible weight %s, sum d*y = %s, ceiling %d%s)" % (
        L, len(S), n_prec, n_res, (", %d window pairs under T<=%d" % (n_win, T0)) if T0 is not None else "", len(cliques), n_knap, Fraction(max_sum, den), bound, ceil_b,
        (" > T0=%d, so T >= %d" % (T0, T0 + 1)) if T0 is not None else "")
    extra = ""
    if lb_pub is not None:
        extra += " published_lb=%d %s" % (lb_pub, "IMPROVES" if L > lb_pub else ("MATCHES" if L == lb_pub else "WORSE"))
    if ub_pub is not None:
        extra += " published_ub=%d%s" % (ub_pub, " CLOSES" if L >= ub_pub else "")
    print(msg + extra); return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
