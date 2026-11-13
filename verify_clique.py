#!/usr/bin/env python3
"""verify_clique.py — independent checker for clique lower-bound certificates (J1, written 2026-10-24 s4).

Claim JSON: {"instance": "RG300_72.rcp", "lb": L, "activities": [1-based ids], "destructive_T": null | T0}
Argument: every listed pair of activities is incompatible, i.e. cannot share a period in any feasible schedule, because one precedes the
other transitively, or their demands exceed some renewable capacity together, or (destructive mode only, under the hypothesis that the
makespan is <= T0) their time windows [ES, LF(T0)] are disjoint. Pairwise-incompatible activities must run one at a time, so every
feasible schedule has makespan >= sum of their durations. In destructive mode, if that sum exceeds T0 the hypothesis is refuted and the
makespan is >= T0 + 1; the certified bound is then min(claimed, T0 + 1).
Usage: verify_clique.py <instance> <claim.json> [--lb L] [--ub U]   -> VERIFIED LB>=... (exit 0) | FAILED: reason (exit 1)
Nothing is shared with the solver (tools/clique_lb.py) except the audited instance parser of verify.py.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import load_instance


def reachability(inst):
    """reach[a] = set of activities (0-based) reachable from a by >= 1 arcs, by a plain BFS from every node."""
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
            for s in succ[a]:
                if es[s] < es[a] + dur[a]: es[s] = es[a] + dur[a]; changed = True
        if not changed: break
    else:
        raise ValueError("precedence graph has a cycle")
    tail = [0] * n
    for _ in range(n + 1):
        changed = False
        for a in range(n):
            for s in succ[a]:
                if tail[a] < dur[s] + tail[s]: tail[a] = dur[s] + tail[s]; changed = True
        if not changed: break
    return es, [T0 - tail[a] for a in range(n)]


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    inst_path, claim_path = argv[0], argv[1]
    lb_pub = ub_pub = None
    for i, a in enumerate(argv):
        if a == "--lb": lb_pub = int(argv[i + 1])
        if a == "--ub": ub_pub = int(argv[i + 1])
    claim = json.load(open(claim_path)); inst = load_instance(inst_path)
    name = os.path.basename(inst_path)
    if claim.get("instance") != name:
        print("FAILED: claim is for %s, instance given is %s" % (claim.get("instance"), name)); return 1
    n = inst["n"]; C = inst["ren"]; K = len(C)
    acts = claim.get("activities")
    if not isinstance(acts, list) or not acts or any((not isinstance(j, int)) or isinstance(j, bool) or not 1 <= j <= n for j in acts):
        print("FAILED: activities must be a non-empty list of integers in 1..%d" % n); return 1
    if len(set(acts)) != len(acts):
        print("FAILED: repeated activity in the clique"); return 1
    L = claim.get("lb")
    if not isinstance(L, int) or isinstance(L, bool) or L < 0:
        print("FAILED: lb must be a non-negative integer"); return 1
    T0 = claim.get("destructive_T")
    if T0 is not None and (not isinstance(T0, int) or isinstance(T0, bool) or T0 < 0):
        print("FAILED: destructive_T must be null or a non-negative integer"); return 1
    dur = [x["modes"][0][0] for x in inst["acts"]]; dem = [x["modes"][0][1] for x in inst["acts"]]
    reach = reachability(inst)
    es, lf = windows(inst, T0) if T0 is not None else (None, None)
    S = [j - 1 for j in acts]; n_prec = n_res = n_win = 0
    for p in range(len(S)):
        a = S[p]
        for q in range(p + 1, len(S)):
            b = S[q]
            if b in reach[a] or a in reach[b]: n_prec += 1; continue
            if any(dem[a][k] + dem[b][k] > C[k] for k in range(K)): n_res += 1; continue
            if T0 is not None and (es[a] >= lf[b] or es[b] >= lf[a]): n_win += 1; continue
            print("FAILED: activities %d and %d are compatible (no precedence relation, demands fit%s)" % (a + 1, b + 1, ", windows overlap" if T0 is not None else "")); return 1
    total = sum(dur[j] for j in S)
    if T0 is None:
        bound = total
    else:
        if total <= T0:
            print("FAILED: destructive clique sum %d does not exceed the hypothesis T0=%d (no bound follows)" % (total, T0)); return 1
        bound = T0 + 1
    if L > bound:
        print("FAILED: claimed lb %d exceeds the certified bound %d (clique sum %d%s)" % (L, bound, total, "" if T0 is None else ", T0=%d" % T0)); return 1
    msg = "VERIFIED LB>=%d (clique of %d activities, durations sum %d; %d precedence pairs, %d resource pairs%s)" % (
        L, len(S), total, n_prec, n_res, (", %d window pairs under T<=%d" % (n_win, T0)) if T0 is not None else "")
    extra = ""
    if lb_pub is not None:
        extra += " published_lb=%d %s" % (lb_pub, "IMPROVES" if L > lb_pub else ("MATCHES" if L == lb_pub else "WORSE"))
    if ub_pub is not None:
        extra += " published_ub=%d%s" % (ub_pub, " CLOSES" if L >= ub_pub else "")
    print(msg + extra); return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
