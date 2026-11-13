# Certified lower bounds for open RG300 and DC2 instances: methods note

_2026-11-05 (drafted 2026-11-04; the integrity-pass counts in section 6 are final)._

## 1. What is claimed

Every bound below is a lower bound on the optimal makespan of a single-mode RCPSP instance, taken from the RG300 and DC2 sets of
SolutionsUpdate (tables `RG300_3.csv` and `DC2_1.csv`, downloaded 4 November 2026). Each bound comes with a **certificate file**: a
small JSON object with the bound and the combinatorial or LP evidence for it. A **checker** program reads the original `.rcp`
instance and the certificate and accepts or rejects. No bound relies on a solver's internal reasoning. Each one can be re-checked from
the two files.

| Set | Floors above the table LB | of which reach the table UB (instance closed) | Open time units closed |
|---|---|---|---|
| RG300 | 187 | 33 | 3,312 of 9,435 (floors only) |
| DC2 | 69 | 27 | 511 of 932 |

`MANIFEST_RG300.csv` and `MANIFEST_DC2.csv` list, for every instance, the table LB and UB, our floor, the certificate type, the
certificate file and its sha256 prefix. `LB_results.csv` gives the same floors in the SolutionsUpdate results-file format
(`lower bound` rows).

## 2. Notation

An instance has activities 1..n (1 and n are dummies) with durations d_j, demands r_jk on renewable resources k with capacities C_k, and
precedence arcs. Two activities are **compatible** if neither precedes the other, directly or transitively, and r_ik + r_jk ≤ C_k for every
k. A **feasible set** is a set of pairwise compatible activities whose demands fit every capacity jointly. In any schedule, the activities
running in one period form a feasible set. T denotes a candidate makespan. "Refuting T" means showing that no schedule has makespan ≤ T,
which proves LB ≥ T + 1.

## 3. Certificate types

Short names match the `lb_method` column of the manifests.

**dff: dual feasible functions (single resource).** For one resource of capacity C, each activity is d_j items of size r_j that must be
packed into T bins of size C. A function f on the demand values with Σ_{x∈p} f(x) ≤ 1 for every multiset p with Σp ≤ C gives
T ≥ ⌈Σ_j d_j f(r_j)⌉. The certificate lists f in exact rationals. The checker enumerates every multiset of occurring demands that fits C
and recomputes the bound exactly.

**vpdff: joint (vector-packing) dual feasible functions.** The same argument over all resources at once: f is defined on the distinct
demand vectors, and every multiset of vectors that fits (C_1..C_K) must have f-sum ≤ 1. The checker verifies this with an exact
integer knapsack dynamic program over the capacity lattice.

**clique: pairwise incompatible sets.** If every pair in a set S is incompatible, the members of S run one at a time, so
makespan ≥ Σ_{j∈S} d_j. This is Mingozzi et al.'s (1998) node-packing bound, here computed exactly. The checker recomputes the
transitive precedence relation by its own BFS and tests every pair.

**aclp: the feasible-set LP (Mingozzi et al.'s LB0).** Weights y_j ≥ 0 with y(F) ≤ 1 for every feasible set F give
makespan ≥ ⌈Σ_j d_j y_j⌉, because Σ_t y(F_t) = Σ_j d_j y_j and each period contributes at most 1. The certificate lists y in exact
rationals. The checker proves dual feasibility exactly, either by enumerating all maximal cliques of the compatibility graph on supp(y)
with a knapsack inside each (`verify_antichain.py`), or by a decision search for a feasible set of weight > 1 (`verify_antichain2.py`). If
a search cap is reached, the result is a failure, never a pass.

**zeroslack: zero-slack tiling.** This applies when an aclp certificate has an integer bound L. A schedule of makespan L must give every
period y-weight exactly 1. Activities with y = 1 cannot share a period with any other positive-weight activity. So the fractional
activities (0 < y < 1) must be laid out without preemption so that each period holds fractional weight 0 or exactly 1. The certificate
names a set of fractional activities that is closed under compatibility. The checker's exhaustive search shows that no such layout
exists, so LB ≥ L + 1.

**slackzero: slack-budget tiling.** The same argument with a fractional LP bound. With T = LB − 1 and slack s = T − Σ d·y ∈ [0, 1), the
per-period shortfalls 1 − y(F_t) sum to exactly s. A closed set of fractional activities whose every layout costs more than s in its own
periods therefore refutes T.

**blockgap / blockgap2: block-gap tiling.** The slack-budget argument for any slack s ≥ 0, with two more sound layout rules: (i) a member of
the refuting set R starts only after every member of R that precedes it has finished; (ii) a period used by R never holds a weight-1
activity, so a contiguous block of R-periods lies inside one gap of the weight-1 sequence. `verify_blockgap.py` runs the layout search in
Python. `verify_blockgap2.py` runs it in C (`verify_blockgap2_search.c`, which the checker compiles from source and pins by sha256),
with an exact memo of failed states. The `--mem` option sets the memo size. Any outcome other than "refuted", including CAP, MEMFULL or
an error, is a failure. `verify_blockgap3.py` is the same search but clears the memo when it fills, which trades time for memory.

**mirror: time reversal.** Renumber j → n + 1 − j and reverse every arc. The map S'_{n+1−j} = Z − S_j − d_j takes every schedule of
makespan Z to a schedule of the mirrored instance with the same makespan, and back, so both instances have the same optimum. The layout
search above is not symmetric under this reversal, so some T are refuted on the mirror but not on the original. The certificate pins the
mirrored `.rcp` and the mirror's block-gap certificate by sha256. `verify_mirror.py` checks the exact mirror relation (durations,
demands, reversed arc set), then runs the block-gap checker on the mirror.

**zseq: sequence propagation on a clique.** Start from a clique Q with Σ_Q d = L, checked by the clique checker. A schedule of
makespan ≤ L + s leaves at most s periods without a member of Q, called a carrier. Every other activity, called a rider, overlaps a
contiguous block of carriers that are compatible with it and long enough (Σ d ≥ d_r − s). The order of these blocks is constrained by the
precedences between riders and carriers. The checker propagates the resulting partial order on the carriers to a fixpoint. It
certifies LB ≥ L + s + 1 in three cases: a rider has no feasible block; the order gets a cycle; or (carrier capacity) a set of riders that
can never share a period needs more room than the union of their possible blocks. `verify_seqprop2.py` adds a hole budget: rider r needs
at least d_r − max(block length) carrier-free periods, and pairwise incompatible riders cannot share them, so a witness set with total
need > s refutes. Some bases use a "swapped" clique, Q − K + {r} for a rider r compatible with exactly the carriers K.

## 4. The checkers

- They are separate programs from the code that produced the certificates. They share no code with it and parse the `.rcp` file
  themselves (one parser, `verify.py`'s, used by every checker).
- They use exact rational arithmetic. They stop on a search cap and report FAILED, never VERIFIED.
- They print `VERIFIED LB>=X …` and exit 0, or `FAILED: reason` and exit 1. The certificate a check builds on (for example the LP
  certificate under a tiling claim, or the mirror file) is pinned by sha256 and checked again by its own checker.
- Each checker was written before the claims it judges, and it was frozen (sha256 recorded) before them. The checkers behind the
  tiling, block-gap, mirror and sequence-propagation bounds, and the LP checkers, were then audited in a separate session: a full read,
  random small instances compared against exhaustive search (hundreds to thousands of cases), tampered certificates, and, for the C
  search and the mirror checker, code mutants. The three simplest checkers (dff, vpdff, clique) had controls when they were written
  (correct and tampered certificates, wrong capacities or instances) but no separate audit. `CHECKERS.md` lists each checker's
  record.
- File hashes: see `reverify_*.log` (the `CHECKER` lines at the top).

## 5. How to re-check

Requirements: Python 3.9+ (standard library, plus numpy for `verify_vpdff.py`), and gcc for the two C searches (the checker compiles them
itself). Run the checkers from the folder that holds them: certificates name their base files by paths relative to it (`certs/…`).

```
python3 <checker>.py <instance.rcp> <certificate.json> --lb <table LB> --ub <table UB> [--mem MB]
```

The manifest gives the checker name for each row. `reverify_lb.py` runs every row; its logs are in this folder. Runtimes on a 2-CPU,
3 GB machine: under a second for most dff, clique, aclp and zseq certificates, and minutes for most block-gap ones. The exceptions are
RG300_260 (about 4.5 h, almost all spent in the LP dual check) and a few memo-heavy block-gap rows, which need `--mem 1800`–`2300`
(MB): RG300_396, RG300_413, RG300_383, RG300_270, DC2_453 and DC2_625.

## 6. Provenance and limitations

- **How these were produced.** The bounds, the solvers, the checkers and the checker audits were produced by an automated AI-agent
  pipeline running daily on a small machine between 24 October and 4 November 2026. The checkers have not yet been reviewed by an
  outside expert. This is why each certificate ships with the checker and its audit record, so that anyone can re-run them.
- **What is new.** The certificate ideas are known: dual feasible functions, node packing and LB0 (Mingozzi et al. 1998), and
  energetic and sequencing reasoning. To our knowledge, what is new is the bound values on these instances, and the tiling and
  sequence-propagation refutations on top of the LP and clique certificates, each with an independent checker.
- **Integrity pass (4–5 November 2026).** 256 of 256 floors re-verified from the saved files with the unchanged checkers: the 198 quick certificates in `reverify_logs/reverify_light.log`, the 58 heavy ones (block-gap, block-gap v2, mirror) across `reverify_heavy.log`, `reverify_heavy2.log`, `reverify_heavy_260.log`, `reverify_heavy3a.log` and `reverify_heavy3b.log` (the pass was interrupted by a machine reboot and resumed row by row). Each log starts with the sha256 of every checker file used; they are identical across the logs. One row is marked `ROW_NOT_OK` in `reverify_heavy2.log`: `DC2_625`, "C search error (exit -9)" — the checker's C search was killed by the reboot (4 November, 19:00 UTC), not rejected; the same certificate re-verified on 5 November in 482 s (`reverify_heavy3b.log`). The two checkers that had only been control-tested (`verify_clique.py`, `verify_dff.py`) received a separate-session audit on 5 November (CHECKERS.md)..
