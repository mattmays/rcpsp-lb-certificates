#!/usr/bin/env python3
"""Re-run every certificate listed in MANIFEST_RG300.csv / MANIFEST_DC2.csv with its checker. Usage: python3 run_all.py [--light] [--only ID,...]
Rows whose method is blockgap/blockgap2/mirror can take minutes and 1.5-2.3 GB (see mem_mb); RG300_260 takes ~4.5 h."""
import csv, os, subprocess, sys
H = os.path.dirname(os.path.abspath(__file__)); a = sys.argv[1:]
only = set(a[a.index("--only") + 1].split(",")) if "--only" in a else None
n = ok = 0
for s in ("RG300", "DC2"):
    for r in csv.DictReader(open(os.path.join(H, "MANIFEST_%s.csv" % s))):
        if only and r["instance"] not in only: continue
        if "--light" in a and r["method"] in ("blockgap", "blockgap2", "mirror"): continue
        line = ""
        for chk in r["checker"].split("|"):
            cmd = [sys.executable, "-I", os.path.join(H, chk), os.path.join(H, r["instance_file"]), os.path.join(H, r["certificate"]),
                   "--lb", r["table_lb"], "--ub", r["table_ub"]]
            if chk in ("verify_blockgap2.py", "verify_mirror.py"): cmd += ["--mem", r["mem_mb"] or "1500"]
            p = subprocess.run(cmd, capture_output=True, text=True, cwd=H)
            line = (p.stdout.strip().splitlines() or [p.stderr.strip()[-200:]])[-1]
            if line.startswith("VERIFIED"): break
        good = line.startswith("VERIFIED") and ("LB>=" + r["new_lb"]) in line.replace(" ", "")
        n += 1; ok += good
        print(("OK  " if good else "BAD ") + r["instance"] + " " + r["new_lb"] + " :: " + line[:160], flush=True)
print("TOTAL %d/%d verified" % (ok, n))
