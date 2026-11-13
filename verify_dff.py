#!/usr/bin/env python3
"""verify_dff.py — independent checker for dual-feasible-function (bin-packing LP dual) lower-bound certificates  (J1).

Written 2026-10-24 s2, before any claim it judges (checker-before-claim rule). Shares only the audited instance parser with
verify.py; it does not import the solver side (tools/dff_lb.py) and recomputes everything else from the instance file.

Claim JSON: {"instance": "RG300_15.rcp", "lb": L, "resource": k (1-based), "f": {"<size>": "<p/q>", ...}, ...}

Soundness argument checked here. Let C be the capacity of renewable resource k and r_j the demand of activity j on it. In any
feasible schedule of makespan T, activity j runs in exactly d_j periods, and in every period t the set R_t of running activities
has sum_{j in R_t} r_j <= C. If f maps every positive demand value that occurs on resource k to a rational number such that
    sum_{x in p} f(x) <= 1   for every multiset p of occurring demand values with sum(p) <= C          (dual feasibility)
then  sum_j d_j f(r_j) = sum_{t < T} sum_{j in R_t} f(r_j) <= T,  hence  T >= ceil( sum_j d_j f(r_j) ).
The checker (1) parses the instance, (2) collects the occurring demand values S on resource k and n[x] = sum of d_j over the
activities with r_j = x, (3) requires f to be defined on all of S, (4) enumerates every multiset over S with sum <= C and
checks the inequality in exact rationals, (5) computes ceil(sum_x n[x] f(x)) exactly and requires it to be >= the claimed L.
Negative or non-monotone f is allowed (the argument above never needs f >= 0). Multi-mode instances are not supported.

Usage:  verify_dff.py <instance file> <claim.json> [--lb <published LB>] [--ub <published UB>]
Exit 0 and "VERIFIED LB>=L" on success (plus IMPROVES / MATCHES / WORSE against --lb, and CLOSES if L >= --ub); exit 1 "FAILED: reason".
"""
import sys, os, json, math
from fractions import Fraction
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify import load_instance


def multisets_with_sum_at_most(sizes, C):
    sizes = sorted(sizes)
    def rec(i, rem, cur):
        if i == len(sizes):
            if any(cur):
                yield tuple(cur)
            return
        for c in range(rem // sizes[i] + 1):
            cur.append(c)
            yield from rec(i + 1, rem - c * sizes[i], cur)
            cur.pop()
    return sizes, rec(0, C, [])


def check(inst, claim):
    if any(len(a["modes"]) != 1 for a in inst["acts"]):
        return False, "multi-mode instances are not supported"
    k = int(claim["resource"]) - 1
    if not 0 <= k < len(inst["ren"]):
        return False, "resource %r out of range" % claim["resource"]
    C = inst["ren"][k]
    if "capacity" in claim and int(claim["capacity"]) != C:
        return False, "claim capacity %r != instance capacity %d" % (claim["capacity"], C)
    L = int(claim["lb"])
    n = {}
    for a in inst["acts"]:
        d, dem, _ = a["modes"][0]
        x = dem[k]
        if x < 0 or d < 0:
            return False, "negative demand or duration in the instance"
        if x > 0 and d > 0:
            n[x] = n.get(x, 0) + d
    if not n:
        return False, "resource %d carries no work" % (k + 1)
    try:
        f = {int(x): Fraction(str(v)) for x, v in claim["f"].items()}
    except Exception as e:
        return False, "cannot parse f: %s" % e
    missing = [x for x in n if x not in f]
    if missing:
        return False, "f is not defined on occurring demand values %s" % sorted(missing)
    sizes, gen = multisets_with_sum_at_most(n.keys(), C)
    fv = [f[x] for x in sizes]
    count = 0
    for row in gen:
        count += 1
        if sum(c * fx for c, fx in zip(row, fv)) > 1:
            return False, "f is not dual feasible: multiset %s (sum %d <= %d) has f-sum %s > 1" % (
                {sizes[i]: c for i, c in enumerate(row) if c}, sum(c * s for c, s in zip(row, sizes)), C,
                sum(c * fx for c, fx in zip(row, fv)))
    total = sum(n[x] * f[x] for x in n)
    bound = math.ceil(total)
    if bound < L:
        return False, "certified bound ceil(%s) = %d < claimed %d" % (total, bound, L)
    return True, "VERIFIED LB>=%d (resource %d, capacity %d, %d demand values, %d multisets checked, sum=%s)" % (
        L, k + 1, C, len(n), count, total)


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
