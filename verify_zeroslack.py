#!/usr/bin/env python3
"""verify_zeroslack.py — independent checker for zero-slack tiling lower-bound claims (J1, written 2026-10-25 s2).

Claim JSON: {"instance": "RG300_461.rcp", "lb": L + 1, "base_certificate": "certs/RG300_461_lb1648_aclp.json", "refuting_component": [1-based ids]}
Argument.
 (1) The base certificate's weights y >= 0 satisfy y(F) <= 1 for every feasible set F (an antichain of the precedence order whose demands fit
     every renewable capacity jointly). This is established by running the unchanged checker verify_antichain.py on the base certificate.
 (2) L = sum_j d_j y_j is computed exactly here and must be an integer. In any schedule of makespan M the running sets F_t (t < M) are feasible
     and sum_{t<M} y(F_t) = L. If M <= L, then (each term <= 1) M = L and y(F_t) = 1 for EVERY period t < M.
 (3) R = refuting_component must consist of activities with 0 < y < 1 and d > 0, and must be closed: no other activity with 0 < y < 1 is
     compatible (no precedence relation either way, demands fit pairwise) with a member of R. A period's running set is pairwise compatible, so
     if it contains a member of R its fractional members all lie in R; it holds no weight-1 activity (that would give weight > 1); weight-0
     activities add nothing. Hence in a schedule of makespan L every period has R-weight 0 or exactly 1, with a feasible running R-set:
     the runs of R (non-preemptive, d_j periods each) form a "tiling".
 (4) Exhaustive search for such a tiling, period by period: when nothing of R runs, the next period with an R-activity starts a block with a
     feasible set of weight exactly 1 (idle stretches are irrelevant and skipped); when the running weight is 1 nothing may start; when it
     drops below 1 after some end (and stays above 0), the activities starting in that period must bring it back to exactly 1 (feasibly);
     when it drops to 0 the block ends. Every tiling is one path of this search. No path => no schedule of makespan <= L => makespan >= L + 1.
 All weights are exact rationals (integers over the common denominator). A hard node cap makes the check FAIL (unable to check), never pass.
Usage: verify_zeroslack.py <instance> <claim.json> [--lb L] [--ub U] [--cap N]  -> VERIFIED LB>=... (exit 0) | FAILED: reason (exit 1)
Shares only the audited parser of verify.py; dual feasibility is delegated to the audited verify_antichain.py (subprocess).
"""
import sys, os, json, subprocess, hashlib
from fractions import Fraction
from math import gcd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from verify import load_instance


def successors_closure(inst):
    n = inst["n"]; succ = [[s - 1 for s in x["succ"]] for x in inst["acts"]]
    out = []
    for a in range(n):
        seen = set(); todo = list(succ[a])
        while todo:
            v = todo.pop()
            if v not in seen: seen.add(v); todo.extend(succ[v])
        out.append(seen)
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    inst_path, claim_path = argv[0], argv[1]
    lb_pub = ub_pub = None; cap = 5_000_000
    for i, a in enumerate(argv):
        if a == "--lb": lb_pub = int(argv[i + 1])
        if a == "--ub": ub_pub = int(argv[i + 1])
        if a == "--cap": cap = int(argv[i + 1])
    name = os.path.basename(inst_path)
    claim = json.load(open(claim_path)); inst = load_instance(inst_path)
    if claim.get("instance") != name:
        print("FAILED: claim is for %s, instance given is %s" % (claim.get("instance"), name)); return 1
    lb = claim.get("lb")
    if not isinstance(lb, int) or isinstance(lb, bool) or lb < 0:
        print("FAILED: lb must be a non-negative integer"); return 1
    base_rel = claim.get("base_certificate")
    if not isinstance(base_rel, str) or os.path.isabs(base_rel) or ".." in base_rel.split("/"):
        print("FAILED: base_certificate must be a relative path inside the problem directory"); return 1
    base_path = os.path.join(HERE, base_rel)
    if not os.path.isfile(base_path):
        print("FAILED: base certificate %s not found" % base_rel); return 1
    base_raw = open(base_path, "rb").read()
    if "base_sha256" in claim and claim["base_sha256"] != hashlib.sha256(base_raw).hexdigest():
        print("FAILED: base certificate sha256 differs from the claim's base_sha256"); return 1
    base = json.loads(base_raw)
    if base.get("instance") != name:
        print("FAILED: base certificate is for %s" % base.get("instance")); return 1
    if base.get("destructive_T") is not None:
        print("FAILED: base certificate must be a plain (non-destructive) feasible-set LP certificate"); return 1
    # (1) dual feasibility by the audited checker
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "verify_antichain.py"), inst_path, base_path], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.startswith("VERIFIED"):
        print("FAILED: verify_antichain.py rejects the base certificate: %s" % (r.stdout.strip() or r.stderr.strip()[-300:])); return 1
    # (2) exact L
    n = inst["n"]; C = inst["ren"]; K = len(C)
    dur = [x["modes"][0][0] for x in inst["acts"]]; dem = [x["modes"][0][1] for x in inst["acts"]]
    y = {}
    for k, v in base["y"].items():
        j = int(k) - 1
        if not 0 <= j < n or j in y: print("FAILED: bad activity id %s in base certificate" % k); return 1
        f = Fraction(v) if isinstance(v, (str, int)) and not isinstance(v, bool) else None
        if f is None or f <= 0: print("FAILED: bad weight %r" % (v,)); return 1
        y[j] = f
    Lq = sum(dur[j] * y[j] for j in y)
    if Lq.denominator != 1:
        print("FAILED: sum d*y = %s is not an integer (the zero-slack argument needs an integral bound)" % Lq); return 1
    L = Lq.numerator
    if lb > L + 1:
        print("FAILED: claimed lb %d exceeds L + 1 = %d" % (lb, L + 1)); return 1
    # (3) the refuting component: fractional, positive duration, closed under compatibility among fractional activities
    reach = successors_closure(inst)
    def compatible(a, b):
        if b in reach[a] or a in reach[b]: return False
        return all(dem[a][k] + dem[b][k] <= C[k] for k in range(K))
    frac = [j for j in y if y[j] < 1 and dur[j] > 0]
    Rl = claim.get("refuting_component")
    if not isinstance(Rl, list) or not Rl or not all(isinstance(v, int) and not isinstance(v, bool) for v in Rl):
        print("FAILED: refuting_component must be a non-empty list of activity ids"); return 1
    R = sorted(set(v - 1 for v in Rl))
    if len(R) != len(Rl): print("FAILED: refuting_component lists an activity twice"); return 1
    for j in R:
        if j not in y or not y[j] < 1 or dur[j] <= 0:
            print("FAILED: activity %d is not a fractional (0 < y < 1) activity of positive duration" % (j + 1)); return 1
    Rs = set(R)
    for j in frac:
        if j in Rs: continue
        for r_ in R:
            if compatible(j, r_):
                print("FAILED: component not closed: fractional activity %d is compatible with member %d" % (j + 1, r_ + 1)); return 1
    # (4) exhaustive tiling search, period by period, exact integer weights over D
    D = 1
    for j in R: D = D * y[j].denominator // gcd(D, y[j].denominator)
    w = {j: int(y[j] * D) for j in R}
    nodes = [0]; memo = {}

    def fits(group):
        for i in range(len(group)):
            for k2 in range(i + 1, len(group)):
                if not compatible(group[i], group[k2]): return False
        return all(sum(dem[j][k] for j in group) <= C[k] for k in range(K))

    def start_sets(rem, running, need):
        """all subsets S of rem (non-empty) with w(S) == need and running + S feasible."""
        base_ = [j for j, _ in running]
        cand = [j for j in sorted(rem) if w[j] <= need and fits(base_ + [j])]
        res = []
        def go(i, chosen, s):
            if s == need:
                if fits(base_ + chosen): res.append(list(chosen))
                return
            if i == len(cand): return
            if s + w[cand[i]] <= need:
                chosen.append(cand[i]); go(i + 1, chosen, s + w[cand[i]]); chosen.pop()
            go(i + 1, chosen, s)
        go(0, [], 0)
        return res

    def search(rem, running):
        """rem: frozenset not yet started; running: tuple of (j, periods left incl. the current one) for the CURRENT period, weight D."""
        key = (rem, running)
        if key in memo: return memo[key]
        nodes[0] += 1
        if nodes[0] > cap: raise OverflowError
        ok = False
        if not running:
            if not rem: ok = True
            else:
                for S in start_sets(rem, (), D):
                    if search(rem - frozenset(S), tuple(sorted((j, dur[j]) for j in S))): ok = True; break
        else:
            # advance one period
            nxt = tuple((j, k - 1) for j, k in running if k > 1)
            wnext = sum(w[j] for j, _ in nxt)
            if wnext == D:
                ok = search(rem, nxt)
            elif wnext == 0:
                ok = search(rem, ())
            else:
                for S in start_sets(rem, nxt, D - wnext):
                    if search(rem - frozenset(S), tuple(sorted(nxt + tuple((j, dur[j]) for j in S)))): ok = True; break
        memo[key] = ok
        return ok

    sys.setrecursionlimit(100000)
    try:
        tileable = search(frozenset(R), ())
    except OverflowError:
        print("FAILED: tiling search exceeded %d nodes; unable to check (not a refutation)" % cap); return 1
    except RecursionError:
        print("FAILED: recursion limit in the tiling search; unable to check"); return 1
    if tileable:
        print("FAILED: the component admits a weight-1 tiling (no contradiction; the bound stays %d)" % L); return 1
    msg = "VERIFIED LB>=%d (base %s: dual feasible, sum d*y = %d; component of %d fractional activities, %d fractional in all, no tiling in %d search nodes, so makespan >= %d)" % (
        lb, os.path.basename(base_rel), L, len(R), len(frac), nodes[0], L + 1)
    extra = ""
    if lb_pub is not None:
        extra += " published_lb=%d %s" % (lb_pub, "IMPROVES" if lb > lb_pub else ("MATCHES" if lb == lb_pub else "WORSE"))
    if ub_pub is not None:
        extra += " published_ub=%d%s" % (ub_pub, " CLOSES" if lb >= ub_pub else "")
    print(msg + extra); return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
