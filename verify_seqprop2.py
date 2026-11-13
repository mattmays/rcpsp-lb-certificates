#!/usr/bin/env python3
"""verify_seqprop2.py — verify_seqprop.py (written 2026-10-25 s2, audited 10-25 s3, sha256 c814ec5d…bca8) plus rule (6), the hole budget
(added 2026-10-25 s3; the rest of the file is unchanged, so `diff verify_seqprop.py verify_seqprop2.py` shows the whole addition).

Claim JSON: {"instance": "RG300_309.rcp", "lb": L + 1, "base_certificate": "certs/....json" (a clique certificate: "activities", "lb"),
             "base_sha256": "...", "mode": "propagation" | "shave", "shave_rider": <1-based id, mode shave only>,
             "hole_riders": [1-based ids] (optional, rule (6))}
Argument.
 (1) The base certificate's activity set Q is pairwise incompatible (checked by running the unchanged verify_clique.py on it). L = sum of the
     durations of Q, computed here. In a schedule of makespan <= L the members of Q (positive duration) never overlap, so they occupy L distinct
     periods inside [0, L): every period runs exactly one member ("carrier"), and the carriers form a sequence (order of start times).
 (2) Every other activity r with d_r > 0 ("rider") runs in d_r consecutive periods; in each one it shares the period with that period's carrier,
     which must be compatible with r (no precedence relation either way; demands fit pairwise on every resource). The carriers met by r form a
     contiguous block B_r of the sequence with total duration >= d_r; each clique predecessor of r finishes before r starts, so it comes before every
     member of B_r; each clique successor comes after every member of B_r.
 (3) A set `before` of ordered pairs of carriers that hold in every such schedule starts as the precedence order on Q. A block B is feasible for r
     iff B consists of carriers compatible with r, its durations sum to >= d_r, it is convex in `before` (a carrier ordered between two members is a
     member), and no member is `before` a clique predecessor of r, nor a clique successor `before` a member. B_r is feasible. Hence: a carrier in every
     feasible block of r is in B_r, so (predecessor of r, that carrier) and (that carrier, successor of r) hold: they are added, with transitive
     closure. Rider precedence: if r1 precedes r2 (transitively), b1 in B_r1, b2 in B_r2 and b1 != b2, then b1 comes before b2 (if b2 came first,
     r2 would start before b2 ends <= b1 starts < r1 ends, contradicting r1 -> r2). So a block of r2 is infeasible if a member is `before` a
     carrier known to be in B_r1 (a "core" carrier of r1), or a core carrier of a rider successor is `before` a member; and core carriers of r1 are
     ordered before distinct core carriers of r2. A rider without a feasible block, or a pair ordered both ways, means no schedule of makespan <= L
     exists: makespan >= L + 1.
 (3b) Carrier capacity: B_r is one of r's feasible blocks, so r runs inside the periods of U_r, the union of its feasible blocks. Two riders that
     can never share a period — not compatible, or every carrier in U_a & U_b overloads some resource together with both — have disjoint runs.
     A set of such riders therefore needs sum d_r <= sum of d over the union of their U's (the carriers' runs are disjoint); a violating set is a
     contradiction (makespan >= L + 1). (Sets of up to 4 riders with |U_r| <= 6 are examined; others are skipped, which is sound.)
 (4) mode "shave": after the fixpoint of (3), each feasible block B of the named rider is assumed in turn (adding the facts of (2) for B_r = B and
     contiguity: a carrier outside B ordered before / after one member of B is before / after all of it); each case must end in a contradiction.
 (5) Slack s (claim field "slack", default 0; the claim may then state lb = L + s + 1): for makespan M <= L + s the members of Q still occupy L
     distinct periods of [0, M), so at most s periods carry no carrier ("holes"). Everything above holds with these changes: a rider's carriers
     cover at least d_r - s of its periods (feasible blocks need sum d >= d_r - s; the empty block is feasible when d_r <= s); in (3b) the room grows by s and only incompatible riders are
     "never together" (compatible ones might share a hole). For s = 1: a rider none of whose feasible blocks covers d_r contains the hole period, so
     all such riders run together in it — they must be pairwise compatible, fit jointly, and no carrier may precede one of them and follow another.
 (6) Hole budget (slack s >= 1, witness list "hole_riders"): the carriers in B_r cover at most sum_{h in B_r} d_h of r's d_r periods, and B_r is one
     of r's feasible blocks, so r's interval contains at least need_r = d_r - max over its feasible blocks of sum d carrier-free periods. Two
     incompatible riders never run in the same period, so their carrier-free periods are distinct; a pairwise-incompatible set of riders with
     sum need_r > s needs more than the at most s carrier-free periods: contradiction. Checked at the fixpoint of (3), after (3b).
 Riders with more than MAXK compatible carriers are skipped (no conclusions drawn from them; sound).
Usage: verify_seqprop.py <instance> <claim.json> [--lb L] [--ub U]  -> VERIFIED LB>=... (exit 0) | FAILED: reason (exit 1)
Shares only the audited parser of verify.py; the clique check is delegated to the audited verify_clique.py (subprocess).
"""
import sys, os, json, subprocess, hashlib
from itertools import combinations
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from verify import load_instance

MAXK = 14


def descendants(inst):
    n = inst["n"]; succ = [[s - 1 for s in x["succ"]] for x in inst["acts"]]
    out = []
    for a in range(n):
        seen = set(); todo = list(succ[a])
        while todo:
            v = todo.pop()
            if v not in seen: seen.add(v); todo.extend(succ[v])
        out.append(seen)
    return out


class Order:
    """strict order facts on carriers: after[a] = set of carriers known to come after a (kept transitively closed)."""
    def __init__(self, carriers):
        self.after = {a: set() for a in carriers}; self.bad = False; self.core = {}

    def copy(self):
        o = Order([]); o.after = {a: set(v) for a, v in self.after.items()}; o.bad = self.bad
        o.core = {r: set(v) for r, v in self.core.items()}; return o

    def add(self, a, b):
        """add a before b with closure; returns True if anything new."""
        if b in self.after[a]: return False
        if a == b or a in self.after[b]: self.bad = True
        ups = [x for x in self.after if a in self.after[x]] + [a]
        downs = self.after[b] | {b}
        for x in ups:
            for z in downs:
                if x == z or x in self.after[z]: self.bad = True
                self.after[x].add(z)
        return True

    def lt(self, a, b): return b in self.after[a]


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    inst_path, claim_path = argv[0], argv[1]
    lb_pub = ub_pub = None
    for i, a in enumerate(argv):
        if a == "--lb": lb_pub = int(argv[i + 1])
        if a == "--ub": ub_pub = int(argv[i + 1])
    name = os.path.basename(inst_path)
    claim = json.load(open(claim_path)); inst = load_instance(inst_path)
    if claim.get("instance") != name:
        print("FAILED: claim is for %s, instance given is %s" % (claim.get("instance"), name)); return 1
    lb = claim.get("lb")
    if not isinstance(lb, int) or isinstance(lb, bool) or lb < 0:
        print("FAILED: lb must be a non-negative integer"); return 1
    slack = claim.get("slack", 0)
    if not isinstance(slack, int) or isinstance(slack, bool) or slack < 0:
        print("FAILED: slack must be a non-negative integer"); return 1
    hole_riders = claim.get("hole_riders")
    if hole_riders is not None and (not isinstance(hole_riders, list) or len(hole_riders) < 1 or len(set(hole_riders)) != len(hole_riders)
                                    or not all(isinstance(v, int) and not isinstance(v, bool) for v in hole_riders)):
        print("FAILED: hole_riders must be a list of distinct activity ids"); return 1
    rel = claim.get("base_certificate")
    if not isinstance(rel, str) or os.path.isabs(rel) or ".." in rel.split("/"):
        print("FAILED: base_certificate must be a relative path inside the problem directory"); return 1
    bpath = os.path.join(HERE, rel)
    if not os.path.isfile(bpath):
        print("FAILED: base certificate %s not found" % rel); return 1
    raw = open(bpath, "rb").read()
    if "base_sha256" in claim and claim["base_sha256"] != hashlib.sha256(raw).hexdigest():
        print("FAILED: base certificate sha256 differs from the claim's base_sha256"); return 1
    base = json.loads(raw)
    if base.get("instance") != name:
        print("FAILED: base certificate is for %s" % base.get("instance")); return 1
    if base.get("destructive_T") is not None:
        print("FAILED: base certificate must be a plain clique certificate"); return 1
    r_ = subprocess.run([sys.executable, "-I", os.path.join(HERE, "verify_clique.py"), inst_path, bpath], capture_output=True, text=True)
    if r_.returncode != 0 or not r_.stdout.startswith("VERIFIED"):
        print("FAILED: verify_clique.py rejects the base certificate: %s" % (r_.stdout.strip() or r_.stderr.strip()[-300:])); return 1
    n = inst["n"]; C = inst["ren"]; K = len(C)
    dur = [x["modes"][0][0] for x in inst["acts"]]; dem = [x["modes"][0][1] for x in inst["acts"]]
    acts = base.get("activities")
    if not isinstance(acts, list) or not all(isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= n for v in acts) or len(set(acts)) != len(acts):
        print("FAILED: base activities must be distinct ids 1..%d" % n); return 1
    Q = sorted(set(v - 1 for v in acts if dur[v - 1] > 0))
    L = sum(dur[j] for j in Q)
    if lb > L + slack + 1:
        print("FAILED: claimed lb %d exceeds L + slack + 1 = %d" % (lb, L + slack + 1)); return 1
    desc = descendants(inst)
    def related(a, b): return b in desc[a] or a in desc[b]
    def compatible(a, b): return not related(a, b) and all(dem[a][k] + dem[b][k] <= C[k] for k in range(K))
    Qset = set(Q)
    order = Order(Q)
    for a in Q:
        for b in Q:
            if b in desc[a]: order.add(a, b)
    if order.bad:
        print("FAILED: the precedence order on the clique has a cycle"); return 1
    riders = []
    for r in sorted(range(n), reverse=True):  # a different processing order from the solver; the fixpoint does not depend on it
        if dur[r] == 0 or r in Qset: continue
        Kr = [h for h in Q if compatible(r, h)]
        P = [h for h in Q if r in desc[h]]; S = [h for h in Q if h in desc[r]]
        riders.append([r, Kr, P, S])
    rider_ids = set(t[0] for t in riders)
    for t in riders:
        r = t[0]
        t.append([x for x in rider_ids if r in desc[x]])   # rider predecessors
        t.append([x for x in rider_ids if x in desc[r]])   # rider successors

    def feasible_blocks(o, r, Kr, P, S, RP, RS):
        out = []
        if dur[r] - slack <= 0: out.append(set())   # (5): with d_r <= s the rider may run in carrier-free periods only (empty block)
        for size in range(1, len(Kr) + 1):
            for Bt in combinations(Kr, size):
                if sum(dur[h] for h in Bt) < dur[r] - slack: continue
                Bs = set(Bt)
                ok = True
                for a in Bt:
                    for b in Bt:
                        if a != b and o.lt(a, b):
                            for x in o.after[a]:
                                if x not in Bs and o.lt(x, b): ok = False; break
                        if not ok: break
                    if not ok: break
                if ok and any(o.lt(b, p) for b in Bt for p in P): ok = False
                if ok and any(o.lt(s, b) for b in Bt for s in S): ok = False
                if ok and any(b != h1 and o.lt(b, h1) for r1 in RP for h1 in o.core.get(r1, ()) for b in Bt): ok = False
                if ok and any(b != h3 and o.lt(h3, b) for r3 in RS for h3 in o.core.get(r3, ()) for b in Bt): ok = False
                if ok: out.append(Bs)
        return out

    def fixpoint(o):
        """returns a contradiction message or None (fixpoint reached)."""
        while True:
            new = False
            for r, Kr, P, S, RP, RS in riders:
                if len(Kr) > MAXK: continue
                fb = feasible_blocks(o, r, Kr, P, S, RP, RS)
                if not fb: return "rider %d (d=%d) has no feasible carrier block" % (r + 1, dur[r])
                core = set.intersection(*fb) | o.core.get(r, set())
                if core != o.core.get(r, set()): o.core[r] = core; new = True
                for h in core:
                    for p in P: new |= o.add(p, h)
                    for s in S: new |= o.add(h, s)
                    for r1 in RP:
                        for h1 in list(o.core.get(r1, ())):
                            if h1 != h: new |= o.add(h1, h)
                    for r3 in RS:
                        for h3 in list(o.core.get(r3, ())):
                            if h3 != h: new |= o.add(h, h3)
                if o.bad: return "a pair of carriers is ordered both ways"
            if not new: return None

    def capacity(o, maxU=6, maxk=4):
        """(3b): rider r runs inside the periods of U_r = the union of its feasible blocks. Two riders that can never share a period (not
        compatible, or every carrier both could meet overloads some resource together with both of them) have disjoint runs; a set of such
        riders must fit within the union of their U's: sum of their durations <= sum of the carriers' durations."""
        U = {}; in_hole = []
        for r, Kr, P, S, RP, RS in riders:
            if len(Kr) > MAXK: continue
            fb = feasible_blocks(o, r, Kr, P, S, RP, RS)
            u = set().union(*fb) if fb else set()
            if 0 < len(u) <= maxU: U[r] = u
            if slack == 1 and fb and all(sum(dur[h] for h in Bs) < dur[r] for Bs in fb): in_hole.append((r, set(P), set(S)))
        for (a, Pa, Sa), (b, Pb, Sb) in combinations(in_hole, 2):
            if not compatible(a, b):
                return "riders %d and %d must both run in the single carrier-free period but cannot run together" % (a + 1, b + 1)
            if (Pa & Sb) or (Pb & Sa):
                return "riders %d and %d must both run in the single carrier-free period, but a carrier precedes one and follows the other" % (a + 1, b + 1)
        if in_hole and any(sum(dem[r][k] for r, _, _ in in_hole) > C[k] for k in range(K)):
            return "riders %s must all run in the single carrier-free period and overload a resource there" % sorted(r + 1 for r, _, _ in in_hole)
        def never_together(a, b):
            if not compatible(a, b): return True
            if slack > 0: return False
            return all(any(dem[h][k] + dem[a][k] + dem[b][k] > C[k] for k in range(K)) for h in U[a] & U[b])
        cand = sorted(U)
        for size in range(2, maxk + 1):
            for sub in combinations(cand, size):
                carriers = set().union(*(U[x] for x in sub))
                room = sum(dur[h] for h in carriers) + slack; need = sum(dur[x] for x in sub)
                if need > room and all(never_together(a, b) for a, b in combinations(sub, 2)):
                    return "riders %s (durations %s) can never share a period and must all run within carriers %s: %d > %d periods" % (
                        [x + 1 for x in sub], [dur[x] for x in sub], sorted(h + 1 for h in carriers), need, room)
        if hole_riders and slack >= 1:   # (6) hole budget on the claimed witness set
            byid = {t[0]: t for t in riders}; needs = []
            for v in hole_riders:
                t = byid.get(v - 1)
                if t is None or len(t[1]) > MAXK: return None
                fb = feasible_blocks(o, *t)
                if not fb: return "rider %d (d=%d) has no feasible carrier block" % (v, dur[v - 1])
                needs.append(dur[v - 1] - max(sum(dur[h] for h in Bs) for Bs in fb))
            ids0 = [v - 1 for v in hole_riders]
            if all(not compatible(a, b) for a, b in combinations(ids0, 2)) and sum(max(0, x) for x in needs) > slack:
                return "riders %s pairwise never share a period and need %s carrier-free periods: %d > %d" % (hole_riders, needs, sum(max(0, x) for x in needs), slack)
        return None

    msg = fixpoint(order)
    if msg is None: msg = capacity(order)
    mode = claim.get("mode", "propagation")
    detail = ""
    if msg is None:
        if mode != "shave":
            print("FAILED: propagation reaches a fixpoint without contradiction (no bound beyond %d)" % (L + slack)); return 1
        sr = claim.get("shave_rider")
        rid = [t for t in riders if t[0] == (sr - 1 if isinstance(sr, int) else -1)]
        if not rid or len(rid[0][1]) > MAXK:
            print("FAILED: shave_rider %r is not a rider with at most %d compatible carriers" % (sr, MAXK)); return 1
        r, Kr, P, S, RP, RS = rid[0]
        fb = feasible_blocks(order, r, Kr, P, S, RP, RS)
        for Bs in fb:
            o = order.copy(); o.core[r] = set(Bs) | o.core.get(r, set())
            for b in Bs:
                for p in P: o.add(p, b)
                for s in S: o.add(b, s)
            for x in Q:
                if x in Bs: continue
                if any(o.lt(x, b) for b in Bs):
                    for b in Bs: o.add(x, b)
                if any(o.lt(b, x) for b in Bs):
                    for b in Bs: o.add(b, x)
            if o.bad: continue
            m2 = fixpoint(o)
            if m2 is None: m2 = capacity(o)
            if m2 is None:
                print("FAILED: shaving case B_%d = %s is not refuted" % (r + 1, sorted(h + 1 for h in Bs))); return 1
        detail = "shaving on rider %d: all %d feasible blocks refuted" % (r + 1, len(fb))
    else:
        detail = msg
    out = "VERIFIED LB>=%d (base %s: clique of %d activities, sum d = %d; sequence propagation with at most %d carrier-free period(s): %s; so makespan >= %d)" % (
        lb, os.path.basename(rel), len(Q), L, slack, detail, L + slack + 1)
    if lb_pub is not None:
        out += " published_lb=%d %s" % (lb_pub, "IMPROVES" if lb > lb_pub else ("MATCHES" if lb == lb_pub else "WORSE"))
    if ub_pub is not None:
        out += " published_ub=%d%s" % (ub_pub, " CLOSES" if lb >= ub_pub else "")
    print(out); return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
