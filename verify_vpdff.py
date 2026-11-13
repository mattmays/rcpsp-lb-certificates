#!/usr/bin/env python3
"""verify_vpdff.py — independent checker for vector-packing dual-feasible-function lower-bound certificates  (J1).

Written 2026-10-24 s3, before any claim it judges (checker-before-claim rule). Shares only the audited instance parser with verify.py;
it does not import the solver side (tools/vpdff_lb.py) and recomputes everything else from the instance file.

Claim JSON: {"instance": "RG300_41.rcp", "lb": L, "capacities": [C_1..C_K], "bounded": true|false,
             "f": {"r_1,...,r_K": "p/q", ...}  (one entry per occurring demand vector), ...}

Soundness argument checked here. In any feasible schedule of makespan T, activity j runs in exactly d_j periods, and in every period t
the set R_t of running activities has sum_{j in R_t} r_j <= C componentwise (r_j = demand vector over the K renewable resources). Group
activities by distinct demand vector v ("type"); n_v = sum of d_j over the type, m_v = number of activities of the type. Each period
is a pattern: a count vector a over types with sum_v a_v v <= C; an activity runs at most once per period, so a_v <= m_v as well
(only used when "bounded" is true). If f >= 0 on the occurring types satisfies  sum_v a_v f(v) <= 1  for every pattern a  then
sum_v n_v f(v) = sum_{t < T} sum_{j in R_t} f(r_j) <= T, hence T >= ceil(sum_v n_v f(v)).
The checker (1) parses the instance, (2) recomputes the types, n_v and m_v, (3) requires f >= 0 to be defined on all of them,
(4) scales f to integers by the common denominator D and computes the exact maximum pattern value over ALL patterns with a
multi-dimensional knapsack DP over prod(C_k + 1) states (one pass per allowed copy of each type; int64 arithmetic, exact), requiring
max <= D, and (5) computes ceil(sum_v n_v f(v)) in exact Fractions and requires it to be >= the claimed L.

Usage:  verify_vpdff.py <instance file> <claim.json> [--lb <published LB>] [--ub <published UB>]
Exit 0 and "VERIFIED LB>=L" on success (plus IMPROVES / MATCHES / WORSE against --lb, and CLOSES if L >= --ub); exit 1 "FAILED: reason".
"""
import sys, os, json, math
from fractions import Fraction
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import load_instance
import numpy as np


def check(inst, claim):
    if any(len(a["modes"]) != 1 for a in inst["acts"]):
        return False, "multi-mode instances are not supported"
    C = [int(c) for c in inst["ren"]]; K = len(C)
    if "capacities" in claim and [int(c) for c in claim["capacities"]] != C:
        return False, "claim capacities %r != instance capacities %r" % (claim["capacities"], C)
    if any(c < 0 for c in C):
        return False, "negative capacity"
    L = int(claim["lb"]); bounded = bool(claim.get("bounded", False))
    n = {}; m = {}
    for a in inst["acts"]:
        d, dem, _ = a["modes"][0]
        v = tuple(int(x) for x in dem)
        if len(v) != K or any(x < 0 for x in v) or d < 0:
            return False, "bad demand vector or duration in the instance"
        if d > 0 and any(x > 0 for x in v):
            n[v] = n.get(v, 0) + d; m[v] = m.get(v, 0) + 1
    if not n:
        return False, "no resource work in the instance"
    try:
        f = {tuple(int(x) for x in key.split(",")): Fraction(str(val)) for key, val in claim["f"].items()}
    except Exception as e:
        return False, "cannot parse f: %s" % e
    missing = [v for v in n if v not in f]
    if missing:
        return False, "f is not defined on occurring demand vectors %s" % sorted(missing)[:5]
    types = sorted(n)
    fv = [f[v] for v in types]
    if any(x < 0 for x in fv):
        return False, "negative f value (this checker requires f >= 0)"
    D = 1
    for x in fv:
        D = D * x.denominator // math.gcd(D, x.denominator)
    w = [int(x * D) for x in fv]
    if max(w) * 20 >= 2 ** 62:
        return False, "denominator too large for exact int64 arithmetic"
    # exact DP: best[s] = max integer pattern value with vector sum <= s; one shift-max pass per allowed copy
    best = np.zeros(tuple(c + 1 for c in C), dtype=np.int64)
    passes = 0
    for v, wv in zip(types, w):
        if wv == 0:
            continue
        if any(v[k] > C[k] for k in range(K)):
            return False, "demand vector %r exceeds the capacities" % (v,)
        copies = min(C[k] // v[k] for k in range(K) if v[k] > 0)
        if bounded:
            copies = min(copies, m[v])
        src = tuple(slice(0, C[k] + 1 - v[k]) for k in range(K)); dst = tuple(slice(v[k], C[k] + 1) for k in range(K))
        for _ in range(copies):
            cand = best[src] + wv
            best[dst] = np.maximum(best[dst], cand); passes += 1
    M = int(best.max())
    if M > D:
        return False, "f is not dual feasible: some pattern has f-sum %s > 1" % Fraction(M, D)
    total = sum(n[v] * f[v] for v in types)
    bound = math.ceil(total)
    if bound < L:
        return False, "certified bound ceil(%s) = %d < claimed %d" % (total, bound, L)
    return True, "VERIFIED LB>=%d (capacities %s, %d types, %s, max pattern f-sum %s, %d DP passes, sum=%s)" % (
        L, C, len(types), "bounded multiplicity" if bounded else "unbounded", Fraction(M, D), passes, total)


def main(argv):
    if len(argv) < 3:
        print(__doc__); return 2
    inst = load_instance(argv[1])
    claim = json.load(open(argv[2]))
    name = os.path.basename(argv[1])
    if "instance" in claim and os.path.basename(claim["instance"]) != name:
        print("FAILED: claim is for %s, instance given is %s" % (claim["instance"], name)); return 1
    ok, msg = check(inst, claim)
    if not ok:
        print("FAILED:", msg); return 1
    L = int(claim["lb"]); extra = ""
    if "--lb" in argv:
        plb = int(argv[argv.index("--lb") + 1])
        extra += " published_lb=%d %s" % (plb, "IMPROVES" if L > plb else "MATCHES" if L == plb else "WORSE")
    if "--ub" in argv:
        pub = int(argv[argv.index("--ub") + 1])
        extra += " published_ub=%d%s" % (pub, " CLOSES" if L >= pub else "")
    print(msg + extra)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
