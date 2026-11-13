#!/usr/bin/env python3
"""verify_mirror.py — independent checker for floor claims proved on the time-reversed ("mirrored") instance (J1, written 2026-11-02 s4).
NOT YET AUDITED: claims judged by it count only after a fresh-session audit and only if produced in a later session (README Goal rule).

Claim JSON: {"instance": "<original .rcp basename>", "lb": X,
             "mirror_instance": "<relative path of the mirrored .rcp>", "mirror_sha256": "...",
             "mirror_claim": "<relative path of a floor claim for the mirrored instance>", "mirror_claim_sha256": "...",
             "mirror_checker": "verify_blockgap.py" | "verify_blockgap2.py" | "verify_blockgap3.py"}
11-02 s7 edit (NOT YET RE-AUDITED; audited version = git show ecfe3f8:problems/j1-rcpsp-bounds/verify_mirror.py): verify_blockgap3.py
added to CHECKERS and given --mem like verify_blockgap2.py; nothing else changed.
Argument.
 (1) The mirrored file M is the time reversal of the original instance I: both parse (verify.py's audited parser) as single-mode
     instances without nonrenewable resources, with the same n and the same renewable capacities; for every j, activity n + 1 - j of M
     has the same duration and the same demand vector as activity j of I; and the arc set of M is exactly {(n+1-q, n+1-p) : (p, q) an arc of I}.
 (2) Then every schedule S of I with makespan Z gives S'_{n+1-j} = Z - S_j - d_j, a schedule of M with makespan Z: an arc p -> q of I
     (S_q >= S_p + d_p) is the arc q' -> p' of M, and S'_{p'} = Z - S_p - d_p >= Z - S_q = S'_{q'} + d_q; activity j occupies
     [S_j, S_j + d_j) in I and [Z - S_j - d_j, Z - S_j) in M, so the set running in period t of M is the image of the set running in
     period Z - 1 - t of I, with the same demands; starts stay >= 0 and finishes <= Z. Hence the optimum of M is <= the optimum of I
     (and, the map being an involution, equal), so a floor X for M is a floor X for I.
 (3) The floor for M is judged by the named, unchanged, audited checker, run as a subprocess on (M, mirror_claim) with the same --lb / --ub;
     its output must be "VERIFIED LB>=X" with X = this claim's lb. Both files are pinned by sha256 and must lie inside this directory.
Usage: verify_mirror.py <instance> <claim.json> [--lb L] [--ub U] [--mem MB]  -> VERIFIED LB>=... (exit 0) | FAILED: reason (exit 1)
Shares only the audited parser of verify.py; the floor itself is the delegated checker's verdict.
"""
import sys, os, re, json, subprocess, hashlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from verify import load_instance

CHECKERS = ("verify_blockgap.py", "verify_blockgap2.py", "verify_blockgap3.py")   # v3 added 11-02 s7 (re-audit pending)


def inside(rel):
    return isinstance(rel, str) and rel and not os.path.isabs(rel) and ".." not in rel.split("/") and os.path.isfile(os.path.join(HERE, rel))


def arcs(inst):
    return {(p, q) for p, a in enumerate(inst["acts"], 1) for q in a["succ"]}


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    inst_path, claim_path = argv[0], argv[1]
    lb_pub = ub_pub = mem = None
    for i, a in enumerate(argv):
        if a == "--lb": lb_pub = int(argv[i + 1])
        if a == "--ub": ub_pub = int(argv[i + 1])
        if a == "--mem": mem = int(argv[i + 1])
    claim = json.load(open(claim_path))
    name = os.path.basename(inst_path)
    if claim.get("instance") != name:
        print("FAILED: claim is for %s, instance given is %s" % (claim.get("instance"), name)); return 1
    lb = claim.get("lb")
    if not isinstance(lb, int) or isinstance(lb, bool) or lb < 1:
        print("FAILED: lb must be a positive integer"); return 1
    chk = claim.get("mirror_checker")
    if chk not in CHECKERS:
        print("FAILED: mirror_checker must be one of %s" % (CHECKERS,)); return 1
    for key, hkey in (("mirror_instance", "mirror_sha256"), ("mirror_claim", "mirror_claim_sha256")):
        if not inside(claim.get(key)):
            print("FAILED: %s must be an existing relative path inside the problem directory" % key); return 1
        raw = open(os.path.join(HERE, claim[key]), "rb").read()
        if claim.get(hkey) != hashlib.sha256(raw).hexdigest():
            print("FAILED: %s sha256 missing or different" % key); return 1
    m_path = os.path.join(HERE, claim["mirror_instance"])
    if os.path.basename(m_path) == name:
        print("FAILED: the mirrored file must have a different name from the original"); return 1
    I = load_instance(inst_path); M = load_instance(m_path)
    # (1) the mirror relation
    if I["n"] != M["n"] or I["ren"] != M["ren"] or I["nonren"] or M["nonren"]:
        print("FAILED: n, renewable capacities or nonrenewables differ (or nonrenewables present)"); return 1
    n = I["n"]
    for j in range(1, n + 1):
        a, b = I["acts"][j - 1], M["acts"][n - j]
        if len(a["modes"]) != 1 or len(b["modes"]) != 1:
            print("FAILED: activity %d: not single-mode" % j); return 1
        (da, ra, _), (db, rb, _) = a["modes"][0], b["modes"][0]
        if da != db or list(ra) != list(rb):
            print("FAILED: activity %d of the original and %d of the mirror differ in duration or demands" % (j, n + 1 - j)); return 1
    want = {(n + 1 - q, n + 1 - p) for (p, q) in arcs(I)}
    if arcs(M) != want:
        print("FAILED: the mirror's arc set is not the reversed arc set (%d vs %d arcs, %d differ)" % (len(arcs(M)), len(want), len(arcs(M) ^ want))); return 1
    # (3) the floor on the mirror, by the unchanged audited checker
    cmd = [sys.executable, "-I", os.path.join(HERE, chk), m_path, os.path.join(HERE, claim["mirror_claim"])]
    if lb_pub is not None: cmd += ["--lb", str(lb_pub)]
    if ub_pub is not None: cmd += ["--ub", str(ub_pub)]
    if mem is not None and chk in ("verify_blockgap2.py", "verify_blockgap3.py"): cmd += ["--mem", str(mem)]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE)
    out = (p.stdout.strip().splitlines() or [p.stderr.strip()[-300:] or "no output"])[-1]
    mm = re.match(r"^VERIFIED LB>=(\d+)(\s|$)", out)
    if p.returncode != 0 or not mm or int(mm.group(1)) != lb:
        print("FAILED: %s on the mirror did not verify LB>=%d: %s" % (chk, lb, out[:300])); return 1
    tail = ""
    if lb_pub is not None:
        tail += " published_lb=%d %s" % (lb_pub, "IMPROVES" if lb > lb_pub else "does not improve")
    if ub_pub is not None:
        tail += " published_ub=%d%s" % (ub_pub, " CLOSES" if lb == ub_pub else (" EXCEEDS UB (error?)" if lb > ub_pub else ""))
    print("VERIFIED LB>=%d via mirror (%d activities, %d arcs reversed; %s on %s: %s)%s" % (lb, n, len(want), chk, os.path.basename(m_path), out.split(" (")[0], tail))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
