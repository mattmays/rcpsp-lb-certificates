#!/usr/bin/env python3
"""verify_blockgap.py — independent checker for slack-budget tiling claims with two extra layout rules (J1, written 2026-10-26 s1; NOT YET
AUDITED: claims judged by it count only after a fresh-session audit and only if produced in a later session, per the README Goal rule).

verify_slackzero.py (audited 10-26 s1) plus rules (5) and (6) below, and any slack s >= 0 (verify_slackzero.py requires s < 1; nothing in
(1)-(6) needs it: the deficits are >= 0 and sum to exactly s for every s, so the R-periods' deficits sum to <= s; T = lb - 1 may exceed
ceil(sum d*y)). `diff verify_slackzero.py verify_blockgap.py` shows every change.
Claim JSON: {"instance": "RG300_182.rcp", "lb": T + 1, "base_certificate": "certs/RG300_182_lb324_aclp.json", "base_sha256": "...",
             "refuting_component": [1-based ids]}
Argument.
 (1) The base certificate's weights y >= 0 satisfy y(F) <= 1 for every feasible set F (an antichain of the precedence order whose demands fit
     every renewable capacity jointly): established by running the unchanged, audited verify_antichain.py on it.
 (2) B = sum_j d_j y_j exactly; T = lb - 1 is the makespan to refute; the slack s = T - B must satisfy s >= 0 (any value; see above). In any schedule of makespan
     <= T the running sets F_t (t = 0..T-1, empty after the makespan) are feasible and sum_{t<T} y(F_t) = B, so the deficits 1 - y(F_t) are
     >= 0 and sum to exactly s.
 (3) R = refuting_component: activities with 0 < y < 1 and d > 0, closed (no other such activity is compatible with a member of R; compatible
     = no precedence path either way and demands fit pairwise). In a period where a member of R runs, the running set holds no weight-1
     activity (weight > 1) and no fractional activity outside R (not compatible), so its y-weight is the weight of its running R-set, which is
     a feasible set. Hence the R-periods alone have total deficit sum (1 - w(running R-set)) <= s.
 (4) Exhaustive search over non-preemptive layouts of R (each j runs d_j consecutive periods), period by period, with the remaining deficit
     budget: when nothing of R runs, the next R-period starts a block with a non-empty feasible set S (gaps are not R-periods and cost
     nothing here); in every later period of the block the running set is (still running) + (newly started, possibly none), which must be
     feasible, and each period is charged 1 - w(running set); when nothing remains running the block ends. Every layout of R is one path. If
     no path keeps the total charge <= s, no schedule of makespan <= T exists: makespan >= T + 1 = lb.
 (5) Precedence inside R: removing the non-R periods keeps the order of the R-periods, so a member may start only in a period after every
     member of R that precedes it (transitively) has finished.
 (6) Block gap. Q = {j : y_j = 1, d_j > 0}. A period in which a member of R runs (weight > 0) holds no member of Q (two activities of total
     weight > 1 never share a period, by dual feasibility). A search block is a run of consecutive real periods in each of which a member of
     R runs (a member continues from one block period to the next, non-preemptively), so no member of Q runs in any period of the block.
     For a member f and q in Q with q preceding f, q ends by start(f) and has no period in the
     block, so q ends before the block starts; for q in Q succeeding a member, q starts after the block ends. Hence if the members of one
     block have a Q-predecessor p and a Q-successor q with q = p or q preceding p, the layout is impossible: the search never forms such a
     block. (A real maximal run may consist of several search blocks; applying the rule to each is weaker, so sound.)
 All weights are exact rationals (integers over a common denominator). A node cap makes the check FAIL (unable to check), never pass.
Usage: verify_blockgap.py <instance> <claim.json> [--lb L] [--ub U] [--cap N]  -> VERIFIED LB>=... (exit 0) | FAILED: reason (exit 1)
Shares only the audited parser of verify.py; dual feasibility is delegated to the audited verify_antichain.py (subprocess). Independent of
the solver (scratch/zeroslack/slack_try.py, scratch/s6/slack_try6.py).
"""
import sys, os, json, subprocess, hashlib
from fractions import Fraction
from math import gcd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from verify import load_instance


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
    if not isinstance(lb, int) or isinstance(lb, bool) or lb < 1:
        print("FAILED: lb must be a positive integer"); return 1
    base_rel = claim.get("base_certificate")
    if not isinstance(base_rel, str) or os.path.isabs(base_rel) or ".." in base_rel.split("/"):
        print("FAILED: base_certificate must be a relative path inside the problem directory"); return 1
    base_path = os.path.join(HERE, base_rel)
    if not os.path.isfile(base_path):
        print("FAILED: base certificate %s not found" % base_rel); return 1
    base_raw = open(base_path, "rb").read()
    if claim.get("base_sha256") != hashlib.sha256(base_raw).hexdigest():
        print("FAILED: base_sha256 missing or different from the base certificate's sha256"); return 1
    base = json.loads(base_raw)
    if base.get("instance") != name:
        print("FAILED: base certificate is for %s" % base.get("instance")); return 1
    if base.get("destructive_T") is not None:
        print("FAILED: base certificate must be a plain (non-destructive) feasible-set LP certificate"); return 1
    # (1) dual feasibility by the audited checker
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "verify_antichain.py"), inst_path, base_path], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.startswith("VERIFIED"):
        print("FAILED: verify_antichain.py rejects the base certificate: %s" % (r.stdout.strip() or r.stderr.strip()[-300:])); return 1
    # (2) exact B, T, s
    n = inst["n"]; C = inst["ren"]; K = len(C)
    if inst.get("nonren"): print("FAILED: nonrenewable resources present"); return 1
    if any(len(x["modes"]) != 1 for x in inst["acts"]): print("FAILED: multi-mode instance"); return 1
    dur = [x["modes"][0][0] for x in inst["acts"]]; dem = [x["modes"][0][1] for x in inst["acts"]]
    y = {}
    for k, v in base["y"].items():
        if not isinstance(k, str) or not k.isdigit() or str(int(k)) != k: print("FAILED: bad activity key %r in base certificate" % (k,)); return 1
        j = int(k) - 1
        if not 0 <= j < n or j in y: print("FAILED: bad activity id %s in base certificate" % k); return 1
        f = Fraction(v) if isinstance(v, (str, int)) and not isinstance(v, bool) else None
        if f is None or f <= 0: print("FAILED: bad weight %r" % (v,)); return 1
        y[j] = f
    B = sum(dur[j] * y[j] for j in y)
    T = lb - 1; s = T - B
    if not (0 <= s):
        print("FAILED: slack s = T - sum d*y = %d - %s = %s is negative (the LP bound alone already gives more)" % (T, B, s)); return 1
    # (3) the refuting set: fractional, positive duration, closed under compatibility among fractional activities
    succ = [[v - 1 for v in x["succ"]] for x in inst["acts"]]
    reach = []
    for a in range(n):
        seen = set(); todo = list(succ[a])
        while todo:
            v = todo.pop()
            if v not in seen: seen.add(v); todo.extend(succ[v])
        reach.append(seen)

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
        for q in R:
            if compatible(j, q):
                print("FAILED: set not closed: fractional activity %d is compatible with member %d" % (j + 1, q + 1)); return 1
    # data for rules (5) and (6)
    Rpred = {k: frozenset(j for j in R if k in reach[j]) for k in R}           # members of R that precede k
    Q = sorted(j for j in y if y[j] == 1 and dur[j] > 0)
    down = {q: frozenset([q]) | frozenset(p for p in Q if p in reach[q]) for q in Q}   # p with q = p or q preceding p
    qpred = {k: frozenset(q for q in Q if k in reach[q]) for k in R}           # Q-predecessors of k
    qsucc_down = {}
    for k in R:
        acc = set()
        for q in Q:
            if q in reach[k]: acc |= down[q]                                     # q succeeds k: everything q precedes-or-equals
        qsucc_down[k] = frozenset(acc)
    # (4) exhaustive layout search with a deficit budget, exact integers over D
    D = s.denominator
    for j in R: D = D * y[j].denominator // gcd(D, y[j].denominator)
    w = {j: int(y[j] * D) for j in R}; budget0 = int(s * D)
    assert all(Fraction(w[j], D) == y[j] for j in R) and Fraction(budget0, D) == s
    nodes = [0]; memo = {}
    ri = {j: x for x, j in enumerate(R)}; qi = {q: x for x, q in enumerate(Q)}

    def kmask(S, idx):
        """memo-key encoding of a set as an int bitmask (a bijection for a fixed index map; keeps the memo small)"""
        m = 0
        for j in S: m |= 1 << idx[j]
        return m

    def feasible(group):
        for i in range(len(group)):
            for k2 in range(i + 1, len(group)):
                if not compatible(group[i], group[k2]): return False
        return all(sum(dem[j][k] for j in group) <= C[k] for k in range(K))

    def additions(rem, cur, lo, hi, nonempty):
        """subsets S of rem with cur + S feasible and lo <= w(cur) + w(S) <= hi (S non-empty if nonempty); rule (5): a member of S may start
        only if no member of R preceding it is still unfinished (in rem, or running in this period)."""
        wc = sum(w[j] for j in cur)
        unfinished = set(rem) | set(cur)
        cand = [j for j in sorted(rem) if wc + w[j] <= hi and feasible(cur + [j]) and not (Rpred[j] & unfinished)]
        def go(i, chosen, tot):     # generated lazily, in the same order as a full list would be
            if i == len(cand):
                if lo <= tot <= hi and (chosen or not nonempty) and feasible(cur + chosen): yield list(chosen)
                return
            if tot + w[cand[i]] <= hi:
                chosen.append(cand[i]); yield from go(i + 1, chosen, tot + w[cand[i]]); chosen.pop()
            yield from go(i + 1, chosen, tot)
        yield from go(0, [], wc)

    def blockstate(P, Dn, S):
        """rule (6): the block's Q-predecessors P and the down-closure Dn of its Q-successors after adding S; None if they intersect."""
        P2 = set(P); D2 = set(Dn)
        for j in S: P2 |= qpred[j]; D2 |= qsucc_down[j]
        if P2 & D2: return None
        return frozenset(P2), frozenset(D2)

    def layout(rem, running, b, P=frozenset(), Dn=frozenset()):
        """True iff the rest can be laid out with total charge <= b. running = members running in the CURRENT period with their periods
        left (incl. the current one); the current period has already been charged. (P, Dn) = rule (6) state of the current block."""
        key = (kmask(rem, ri), running, b, kmask(P, qi), kmask(Dn, qi))
        if key in memo: return memo[key]
        nodes[0] += 1
        if nodes[0] > cap: raise OverflowError
        ok = False
        if not running:
            if not rem: ok = True
            else:   # next R-period starts a block: non-empty feasible S, charge D - w(S) <= b
                for S in additions(rem, [], D - b, D, True):
                    st = blockstate(frozenset(), frozenset(), S)
                    if st is None: continue
                    if layout(rem - frozenset(S), tuple(sorted((j, dur[j]) for j in S)), b - (D - sum(w[j] for j in S)), st[0], st[1]):
                        ok = True; break
        else:
            nxt = tuple((j, k - 1) for j, k in running if k > 1)
            if not nxt:
                ok = layout(rem, (), b)     # the block may end here (a later block is a fresh start, with an empty rule (6) state)
            else:   # next period: still running + starts (possibly none), feasible, charge D - weight <= b
                cur = [j for j, _ in nxt]
                for S in additions(rem, cur, D - b, D, False):
                    st = blockstate(P, Dn, S)
                    if st is None: continue
                    wt = sum(w[j] for j in cur) + sum(w[j] for j in S)
                    if layout(rem - frozenset(S), tuple(sorted(nxt + tuple((j, dur[j]) for j in S))), b - (D - wt), st[0], st[1]):
                        ok = True; break
        memo[key] = ok
        return ok

    sys.setrecursionlimit(100000)
    try:
        possible = layout(frozenset(R), (), budget0)
    except OverflowError:
        print("FAILED: layout search exceeded %d nodes; unable to check (not a refutation)" % cap); return 1
    except RecursionError:
        print("FAILED: recursion limit in the layout search; unable to check"); return 1
    if possible:
        print("FAILED: the set admits a layout within the deficit budget %s (no contradiction)" % s); return 1
    msg = "VERIFIED LB>=%d (base %s: dual feasible, sum d*y = %s, T = %d, slack %s; set of %d fractional activities (%d in all), %d weight-1 activities; no layout within the slack under the R-precedence and block-gap rules in %d search nodes, so makespan >= %d)" % (
        lb, os.path.basename(base_rel), B, T, s, len(R), len(frac), len(Q), nodes[0], lb)
    if lb_pub is not None:
        msg += " published_lb=%d %s" % (lb_pub, "IMPROVES" if lb > lb_pub else ("MATCHES" if lb == lb_pub else "WORSE"))
    if ub_pub is not None:
        msg += " published_ub=%d%s" % (ub_pub, " CLOSES" if lb >= ub_pub else "")
    print(msg); return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
