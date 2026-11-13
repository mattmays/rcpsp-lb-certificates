#!/usr/bin/env python3
"""Independent feasibility checker for RCPSP / MRCPSP schedules (J1).

Written 2026-10-23 s1, before any solver code; kept separate from solvers/ on purpose.
Instance formats:
  .rcp  Patterson-style (RG300, DC2, SolutionsUpdate "rcp"): `N R`, then R capacities, then per activity
        `duration demand_1..demand_R n_succ succ_1..succ_n` (activities and successors are 1-based; 1 and N are dummies).
  .sm   PSPLIB single-mode (J30/J60/J90/J120).
  .mm   PSPLIB multi-mode (MMLIB50/100/MMplus): renewable + nonrenewable (+ doubly constrained, treated as both).
Solution JSON: {"start": [s_1, ..., s_N], "mode": [m_1, ..., m_N]} with 1-based modes (mode optional for single-mode;
a bare list is read as the start list). Starts are non-negative integers.

Checks: every activity has a start; modes in range; precedence (successor start >= predecessor finish); renewable
capacity in every time period; nonrenewable totals. Prints `VALID makespan=M` and exits 0, or `INVALID: reason` and exits 1.
With --ub X it also prints IMPROVES / MATCHES / WORSE against X (the published upper bound).

Usage:
  verify.py <instance.(rcp|sm|mm)> <solution.json> [--ub X]
"""
import json, re, sys


def parse_rcp(text):
    it = iter(text.split())
    n, r = int(next(it)), int(next(it))
    caps = [int(next(it)) for _ in range(r)]
    acts = []
    for _ in range(n):
        d = int(next(it)); dem = [int(next(it)) for _ in range(r)]
        ns = int(next(it)); succ = [int(next(it)) for _ in range(ns)]
        acts.append({"modes": [(d, dem, [])], "succ": succ})
    for a in acts:
        for s in a["succ"]:
            if not 1 <= s <= n:
                raise ValueError("successor out of range")
    return {"n": n, "ren": caps, "nonren": [], "acts": acts}


def parse_psplib(text):
    lines = text.splitlines()
    def find(prefix):
        for k, l in enumerate(lines):
            if re.sub(r"\s", "", l).upper().startswith(prefix):
                return k
        raise ValueError("section %s not found" % prefix)
    def count(pattern):
        m = re.search(pattern, text)
        return int(m.group(1)) if m else 0
    n_ren = count(r"renewable\s*:\s*(\d+)")
    n_non = count(r"nonrenewable\s*:\s*(\d+)")
    n_dbl = count(r"doubly\s*constrained\s*:\s*(\d+)")
    i = find("PRECEDENCERELATIONS") + 2
    succ = {}
    while not lines[i].startswith("*"):
        t = list(map(int, lines[i].split()))
        if t:
            succ[t[0]] = t[3:]
        i += 1
    i = find("REQUESTS/DURATIONS") + 3
    modes = {}; cur = None
    while not lines[i].startswith("*"):
        if lines[i].strip():
            t = list(map(int, lines[i].split()))
            if not lines[i][0].isspace() or len(t) == 3 + n_ren + n_non + n_dbl:
                cur = t[0]; t = t[1:]
            d = t[1]; req = t[2:]
            if len(req) != n_ren + n_non + n_dbl:
                raise ValueError("bad request row for job %s" % cur)
            ren = req[:n_ren] + req[n_ren + n_non:]          # doubly constrained count as renewable ...
            non = req[n_ren:n_ren + n_non] + req[n_ren + n_non:]  # ... and as nonrenewable
            modes.setdefault(cur, []).append((d, ren, non))
        i += 1
    i = find("RESOURCEAVAILABILITIES") + 2
    caps = list(map(int, lines[i].split()))
    if len(caps) != n_ren + n_non + n_dbl:
        raise ValueError("capacity count mismatch")
    ren_caps = caps[:n_ren] + caps[n_ren + n_non:]
    non_caps = caps[n_ren:n_ren + n_non] + caps[n_ren + n_non:]
    n = len(modes)
    if sorted(modes) != list(range(1, n + 1)) or sorted(succ) != list(range(1, n + 1)):
        raise ValueError("job numbering is not 1..N")
    acts = [{"modes": modes[j], "succ": succ[j]} for j in range(1, n + 1)]
    return {"n": n, "ren": ren_caps, "nonren": non_caps, "acts": acts}


def load_instance(path):
    text = open(path, encoding="latin-1").read()
    if path.lower().endswith(".rcp"):
        return parse_rcp(text)
    return parse_psplib(text)


def check(inst, start, mode=None):
    n = inst["n"]
    if len(start) != n:
        return False, "expected %d starts, got %d" % (n, len(start)), None
    if any((not isinstance(s, int)) or isinstance(s, bool) or s < 0 for s in start):
        return False, "starts must be non-negative integers", None
    if mode is None:
        mode = [1] * n
    if len(mode) != n:
        return False, "expected %d modes, got %d" % (n, len(mode)), None
    dur = []; ren = []; non = []
    for j, a in enumerate(inst["acts"]):
        m = mode[j]
        if not (isinstance(m, int) and 1 <= m <= len(a["modes"])):
            return False, "activity %d: mode %r out of range 1..%d" % (j + 1, m, len(a["modes"])), None
        d, r, nr = a["modes"][m - 1]
        dur.append(d); ren.append(r); non.append(nr)
    for j, a in enumerate(inst["acts"]):
        for s in a["succ"]:
            if start[s - 1] < start[j] + dur[j]:
                return False, "precedence %d -> %d violated (%d < %d + %d)" % (j + 1, s, start[s - 1], start[j], dur[j]), None
    makespan = max(start[j] + dur[j] for j in range(n))
    for k, cap in enumerate(inst["ren"]):
        diff = [0] * (makespan + 1)
        for j in range(n):
            if dur[j] > 0 and ren[j][k] > 0:
                diff[start[j]] += ren[j][k]; diff[start[j] + dur[j]] -= ren[j][k]
        load = 0
        for t in range(makespan):
            load += diff[t]
            if load > cap:
                return False, "renewable resource %d over capacity at t=%d (%d > %d)" % (k + 1, t, load, cap), None
    for k, cap in enumerate(inst["nonren"]):
        tot = sum(non[j][k] for j in range(n))
        if tot > cap:
            return False, "nonrenewable resource %d over budget (%d > %d)" % (k + 1, tot, cap), None
    return True, "ok", makespan


def load_solution(path):
    sol = json.load(open(path))
    if isinstance(sol, list):
        return sol, None
    return sol["start"], sol.get("mode")


def main(argv):
    if len(argv) < 3:
        print(__doc__); return 2
    ub = None
    if "--ub" in argv:
        ub = int(argv[argv.index("--ub") + 1])
    inst = load_instance(argv[1])
    start, mode = load_solution(argv[2])
    ok, msg, mk = check(inst, start, mode)
    if not ok:
        print("INVALID:", msg); return 1
    line = "VALID makespan=%d n=%d" % (mk, inst["n"])
    if ub is not None:
        line += " published_ub=%d %s" % (ub, "IMPROVES" if mk < ub else "MATCHES" if mk == ub else "WORSE")
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
