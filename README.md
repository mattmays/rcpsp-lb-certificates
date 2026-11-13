# Certified lower bounds for RG300 and DC2 (RCPSP)

This repository holds a certificate and a checker for each lower bound that Matt Mays submitted to the
[SolutionsUpdate](http://solutionsupdate.ugent.be/) table of best-known RCPSP results:

| Set | Bounds | Reference number in the table | Bounds that equal the table's UB (instance closed) |
|---|---|---|---|
| RG300 | 176 | 12 ([dataset page](http://solutionsupdate.ugent.be/dataset/rg300)) | 33 |
| DC2 | 69 | 10 ([dataset page](http://solutionsupdate.ugent.be/dataset/dc2)) | 31 |

The closure counts are against the November 2026 tables (`RG300_5.csv`, `DC2_2.csv`). In DC2, 7 of the 69 bounds tie
bounds that another author submitted earlier, so the table credits them to that author.

Each bound has a **certificate**: a small JSON file with the evidence for the bound. A **checker** program reads the original
`.rcp` instance and the certificate, and either accepts the bound or rejects it. You don't need to trust the program that found
the bound. You only need to trust the checker, and the checkers are short, standalone and use exact arithmetic.

## Quick start

Requirements: Python 3.9 or newer, numpy (used by `verify_vpdff.py` only), and gcc (the block-gap checkers compile their C search
from source the first time they run, into `scratch/`). Tested on Linux x86_64.

```
git clone https://github.com/mattmays/rcpsp-lb-certificates.git
cd rcpsp-lb-certificates
python3 run_all.py --light            # the 187 fast certificates: about 20 minutes
python3 run_all.py --only RG300_31    # one row
python3 run_all.py                    # all 245 rows: about 18 hours, see "Runtimes and memory" below
```

Each row prints `OK <instance> <bound> :: VERIFIED LB>=<bound> …` or `BAD …`. The last line is `TOTAL k/n verified`.

To run a single checker by hand:

```
python3 <checker> <instance.rcp> <certificate.json> --lb <table LB> --ub <table UB> [--mem MB]
```

The manifests give the checker, the arguments and the certificate for every row.

## Files

| Path | Contents |
|---|---|
| `RG300_LB_results.csv`, `DC2_LB_results.csv` | The results files exactly as submitted to SolutionsUpdate on 10 November 2026 (`lower bound` rows). |
| `MANIFEST_RG300.csv`, `MANIFEST_DC2.csv` | One row per bound: instance, table LB and UB when the certificate was made, the new bound, whether it closed the instance, certificate type, checker(s), certificate path and its sha256, and the memo size for block-gap checks. |
| `certs/` | The certificates. `certs/bases/` holds LP certificates that other certificates build on. `certs/mirror/` holds time-reversed instances and their certificates. Every dependency is pinned by sha256 inside the certificate that uses it. |
| `instances/` | The RG300 and DC2 `.rcp` instances that the bounds refer to, copied unchanged from SolutionsUpdate (see "Instances" below). |
| `verify*.py`, `verify_blockgap*_search.c` | The checkers. `verify.py` contains the shared `.rcp` parser. |
| `run_all.py` | Runs every row of both manifests. |
| `METHODS.md` | What each certificate type proves and why it is sound. |
| `INSIGHTS.md` | Which techniques worked on these sets, which didn't, and why, including the ones that produced no certificate. |
| `CHECKERS.md` | How each checker was tested and audited. |
| `reverify_logs/` | Logs of the full re-verification of 4–5 November 2026, including each checker's sha256. |
| `SHA256SUMS` | sha256 of every file in this repository. |

`METHODS.md`, `CHECKERS.md` and `reverify_logs/` were written for an earlier package of 256 bounds. This repository holds the 245 of them
that were submitted. The other 11 were left out because the table already had an equal or better bound. Their counts and table
names (`RG300_3`) therefore differ from this README. The certificates and checkers are byte-identical to that package.

## Certificate types

| Type | Idea | Checker | RG300 | DC2 |
|---|---|---|---|---|
| dff | Dual feasible function on one resource | `verify_dff.py` | 1 | 8 |
| vpdff | Dual feasible function on all resources jointly | `verify_vpdff.py` | 1 | 0 |
| clique | Pairwise incompatible activities run one at a time (node packing) | `verify_clique.py` | 28 | 19 |
| aclp | Feasible-set LP (Mingozzi et al. LB0), exact dual | `verify_antichain.py`, `verify_antichain2.py` | 57 | 11 |
| zeroslack, slackzero | Tiling refutation on top of an aclp certificate | `verify_zeroslack.py`, `verify_slackzero.py` | 3 | 0 |
| blockgap, blockgap2 | Block-gap tiling refutation (Python / C search) | `verify_blockgap.py`, `verify_blockgap2.py` | 32 | 13 |
| mirror | The same refutation on the time-reversed instance | `verify_mirror.py` | 10 | 3 |
| zseq | Sequence propagation on a clique | `verify_seqprop.py`, `verify_seqprop2.py` | 44 | 15 |

`METHODS.md` gives the argument behind each type. `INSIGHTS.md` explains why these types worked here, and lists the many approaches that did not.

## Runtimes and memory

These are timings on a 2-CPU, 3 GB machine. Most dff, clique, aclp and zseq certificates check in under a second. The 58 block-gap
and mirror rows take about 18 hours in total. Most of them take seconds to minutes, but three are much slower: `DC2_453` (about
6 h), `RG300_260` (about 4 h, nearly all of it in the LP dual check under its block-gap certificate) and `DC2_460` (about 2.6 h).
`reverify_logs/reverify_heavy*.log` records the time for each row.

Six block-gap rows need a large memo: RG300_270, RG300_383, DC2_453 and DC2_625 need 1800 MB, RG300_413 needs 2200 MB and
  RG300_396 needs 2300 MB. `run_all.py` passes the value from the manifest's `mem_mb` column. If a check runs out of memo, it reports a
  failure, never a pass.

## Instances

The instances belong to the RG300 and DC2 datasets of Vanhoucke, M., Coelho, J., & Batselier, J. (2016). An overview of project
data for integrated project management and control. *Journal of Modern Project Management*, 3(2), 6–21. They are copied here
unchanged so that the checks can run offline. The originals are available from the dataset pages linked above.

## License

The code, certificates and documentation are released under the MIT License (`LICENSE`). The instance files in `instances/` belong to
their authors (see "Instances") and are not covered by it.

## Provenance and status

This is a personal side project, and nearly all of the work in it was done by an AI.

**Matt Mays** set up the project: a small machine (2 CPUs, 3 GB RAM) that ran Anthropic's Claude in Claude Code in unattended daily
sessions. The model was Claude Fable 5.1, with Claude Opus 5.5 taking over when the usage cap was reached. He also wrote the ground rules:
every claim needs a checker that is separate from the code that produced it; a checker is frozen before it judges anything and audited in
a later session; and nothing leaves the machine without his approval. He chose which results to submit to SolutionsUpdate. He is not a
scheduling specialist and has not reviewed the checkers.

**Claude** chose the methods and wrote the solvers, the certificates, the checkers and their audits, mostly between 24 October and 4
November 2026. It also wrote this documentation, including `METHODS.md`, `CHECKERS.md` and `INSIGHTS.md`. The checker audits were done
by the same AI in later sessions with a fresh context, which is useful but is not independent review.

**No human has reviewed the checkers.** That is why every bound ships with its checker, its test record and a one-command re-check.
Please treat the bounds as checkable claims, not established results, until someone has. The checkers are short; `verify_clique.py` and
`verify_dff.py` are good places to start.

Reports of a checker accepting something it should not are very welcome.

The solver code is not included. The certificates name the producing tool in fields such as `method`, which are informational
only. The checkers never read those fields.
