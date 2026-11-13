# What worked, what didn't, and why

These notes come from the project's working log, which kept a running list of every technique tried, with its result and the reason it was
kept or dropped. They cover the RG300 and DC2 lower bounds in this repository, and briefly the RG300 upper-bound search (whose schedules are
in the SolutionsUpdate table under the same reference, though the solver code is not included here). The numbers are from runs on a
2-CPU, 3 GB machine between 23 October and 9 November 2026. "Gap" means table UB minus best LB for an instance.

A summary first:

- **The cheap classical bounds were not exhausted on these sets.** Dual feasible functions, maximum cliques and the feasible-set LP (LB0),
  computed exactly, raised many floors and closed instances outright. RG300 and DC2 had simply not been attacked with them at full strength.
- **The biggest single gain came from making one LP converge.** The feasible-set LP was stuck on most RG300 families until its pricing
  problem was solved exactly and fast (a dedicated C branch-and-bound). Generic pricers (CP-SAT, clique enumeration) were 10–100× too slow.
- **Refuting "makespan T" on a relaxation's structure, rather than on the full instance, is what turned LP floors into +1 and closures.**
  An optimal LP dual says which activities must fill which periods; searching for a layout of only the fractional part is small enough to
  finish where a full exact search is hopeless.
- **Time reversal is a free second chance for any chronological search.** The same search on the mirrored instance was often 100–1,000×
  faster, and settled worlds the forward search never finished.
- **General-purpose exact solvers (CP-SAT, CDCL SAT, LCG, MIP) did not decide the remaining gap-1 instances at full size.** They gave no
  useful bound on their own either. What they lack is the problem's global energy argument, and adding it (as a counter) helped only on small instances.

## 1. Lower bounds: what worked

### Dual feasible functions (DFF): cheap, and still productive

Per resource, a DFF turns the instance into bin packing (d_j items of size r_jk, bins of size C_k). On the first pass over the 336 then-open
RG300 instances it raised 11 floors and closed 2. On DC2 it raised 32 floors and closed 1. Solving the integer bin-packing problem never beat
the LP ceiling, and the joint (vector-packing) DFF never beat the best single-resource one. The reason is that every RG300 resource has
capacity 10: a precedence-free vector-packing LP solved to optimality (Gilmore–Gomory with exact knapsack pricing) equals the plain capacity
bound on the instances tested. **The remaining gap on the capacity-bound families is not packing loss. It is precedence and time.**

### Maximum cliques of pairwise-incompatible activities

Two activities are incompatible if one precedes the other (transitively) or they cannot run together on some resource. A clique of such
activities runs one at a time, so the makespan is at least the sum of their durations. Computed exactly, this closed 13 DC2 instances and
is the certificate for 47 bounds in this repository (28 RG300, 19 DC2), and the base of most sequence-propagation bounds. A 20-second search per instance already found the maximum: re-runs at 150 s found nothing more.

### The feasible-set LP (LB0), made to converge

The LP over feasible sets (Mingozzi et al. 1998) is classical, but on most RG300 families its column generation did not converge in
reasonable time. The pricing problem is a maximum-weight feasible set: an independent set in the compatibility graph with knapsack
constraints. Python clique enumeration took more than 10 minutes per call, and a CP-SAT pricer 9–12 s. An exact pricer written in C (weighted maximum-clique branch and bound with a greedy colouring bound)
made the LP converge on most families, with gains of +18 to +26 on RG300_291–300 and large gains on the 131–140, 371–380 and 441–450 families.
The densest families (around 29,000 compatible pairs, e.g. RG300_58 and 59) still did not converge. Their LP masters were still falling and
only 1–15 units above our floors, so long runs were not worth it.

The certificate is an exact rational dual y. Checking it means proving that no feasible set has y-weight above 1, which is the pricing problem
again, so the checker needs its own exact search. That is why there are two independent checkers for it (`verify_antichain.py`,
`verify_antichain2.py`).

### Tiling refutations on top of the LP: where most +1s and closures came from

If Σ d_j y_j = L is the LP value and we ask whether makespan T = L (or slightly above) is possible, the dual is very restrictive. Activities
with y = 1 cannot share a period with any other positive-weight activity, and the fractional activities must almost exactly tile the
remaining periods. The slack s = T − Σ d·y bounds how much "under-filling" is allowed in total. Searching for a non-preemptive layout of only
the fractional activities under that budget is far smaller than the scheduling problem itself.

- **Zero-slack tiling** (s = 0) closed RG300_461 and RG300_355.
- **Block-gap tiling** adds two sound rules: precedence inside the refuting set, and the fact that a block of fractional periods must fit
  inside one gap of the weight-1 sequence. It works where precedence is dense, or where weight-1 activities "fence" the fractional ones into
  short gaps. Its C implementation was about 50× faster than the Python one and found refutations that earlier runs never finished.
- **Sequence propagation on a clique** (zseq) uses the same idea with a clique instead of an LP dual. A clique of total duration L at makespan
  L + s leaves only s periods free, so every other activity must overlap a run of compatible clique members. Propagating the order these runs
  impose found 39 refutations in its first pass, including the closures of RG300_307 and RG300_147. A "hole budget" refinement closed RG300_302.
- **Cliques below the table LB are still useful bases.** A clique too short to be a bound on its own can still give a tight world for sequence
  propagation. This closed RG300_31.

**Why it stops working.** When the LP solution is fractional on a large part of the instance (roughly more than 80 fractional activities at
slack below 1), the layout search does not finish. Measurements showed these worlds are limited by search time, not memory: 140–480 million
nodes in 10 minutes without a verdict. Residual capacity and clique bounds cut nodes 3–49× on solved
worlds, and a transposition table with dominance on the slack budget saved nothing measurable. Neither flipped an unsolved world.

### Time reversal (mirror)

Reversing every arc and mapping S_j → Z − S_j − d_j gives an instance with the same optimum. The layout search proceeds in time order, so a
bottleneck near the end of the forward instance sits near the start of the mirrored one, where a chronological search fails fast. On worlds
the forward search could not finish, the mirrored search was often 100–1,000× faster. It refuted 10 RG300 worlds and 2 DC2 worlds that had
stayed undecided forward, which gave +13 units on 10 RG300 instances and +5 on 2 DC2 instances. It costs nothing to try, and it needs only a
small checker (`verify_mirror.py`) that verifies the reversal exactly and then reuses the forward checker.

### Transfer to DC2

The DC2 set had softer published lower bounds than RG300. Running the already-audited RG300 tools unchanged gave 24 closures in one pass:
DFF 32 floors, cliques 42 floors and 13 closures, the LP 24 floors, plus sequence propagation and block-gap tiling on top. **Before building
something new for a set, run what you already have on it.**

## 2. Lower bounds: what didn't work, and why

| Idea | Result | Why it failed |
|---|---|---|
| Window-energetic DFF (prefix/suffix windows, f re-optimised per window) | No gain over the horizon DFF | Precedence-derived time windows are nearly the whole horizon at these T, so windows carry no compulsory parts |
| Destructive windows inside the LP or clique (pairs that cannot both fit in their windows at T = UB − 1) | 0 cuts on every gap-1–4 instance | Same reason: windows are too wide |
| Time-indexed LPs (destructive feasible-set LP, step LP z_jt = [S_j ≤ t]) | LP-feasible at UB − 1. Only buildable for T up to ~300; a T ≈ 1,500 build ran out of memory | A time-indexed LP smears work across periods, so it cannot see exact-fill infeasibility. RG300 critical paths (38–125) are tiny next to the horizon |
| Helly triple cuts (three pairwise-compatible activities that jointly overload a resource) | Converged at the plain LP value | Pairwise-overlap cuts cannot see time order |
| Forcing one fractional activity to weight 1 ("fix-one" worlds) | Costs 11–15 LP units on RG300_185 | Fractional activities carry heavy compatible neighbourhoods; the slack becomes far too large for any tiling refutation |
| Capacity duals (y = r/C on the tightest resource) as tiling bases | Tileable, or the search ran out of memory | Typically the whole instance is fractional, which is the worst case for the layout search |
| DFF weightings as block-gap bases on RG300 | 1 refutation in 67 fenced worlds (RG300_234 → 775); 0 of 26 gap-1 | The same worlds as the LP duals; DFF weights add nothing new there |
| LB0 machinery on J120 | The LP was far below J120's published bounds (e.g. 79 vs 90) | J120's published LBs (destructive LP, LCG) already dominate LB0, and there is no tiling world to exploit |

**Exact general-purpose solvers.** On RG300, CP-SAT's own lower bound was useless (356 against a table LB of 732 on RG300_291). At T = UB − 1,
CP-SAT returned UNKNOWN on all 22 instances tried, at 120 s each. CDCL SAT (kissat, CaDiCaL) on full time-indexed encodings of gap-1
instances returned UNKNOWN. At long horizons (T ≈ 1,650) the encoding has 19 million variables. A proof-logging LCG solver (Pumpkin) was no
stronger than CDCL on these cores, and a time-indexed MIP was weaker. Adding the LP dual to the SAT encoding as a weighted "deficiency
counter" (total under-fill ≤ T·D − Σ d·w) gave large speed-ups on small instances, for example 439 s → 2 s. It did not decide the RG300
gap-1 instances in 20 minutes.

**Semi-active dominance clauses** (no activity can start one period earlier) sped up SAT refutation only 1.4–1.6×. That is below the 3×
threshold set in advance for building a new checker.

## 3. What remains open, and why it is hard

The RG300 instances still at gap 1 fall into two groups:

- **Energy-blocked** (e.g. RG300_15, 20, 41, 43, 162, 171, 173, 174, 177, 370): one resource has only 1–2 periods of idle capacity in the
  entire best schedule. Any bound must reason about exact filling of that resource. The best LP dual is the capacity bound itself, and the
  whole instance is "fractional".
- **Precedence-blocked** (e.g. RG300_21, 64, 183–187, 191, 193, 194, 236, 360): idle capacity is plentiful, but every local improvement of the
  schedule is infeasible. The bottleneck is a long disjunctive chain on one resource plus activities that must ride alongside it.

For both groups the layout search, mirrored or not, stays undecided at 400 million nodes, and general solvers return UNKNOWN. A later
exact-fill search, which keeps every period exactly full under all valid counters, has not decided an RG300 core either.

## 4. Upper bounds (RG300 schedules; solver code not included)

- **Generic CP-SAT LNS from the best-known schedule found nothing.** A window LNS that re-optimises 20–60 activities at a time also stalled
  quickly. The makespan is carried by a disjunctive chain on the bottleneck resource, and measures that look only at the end of the schedule
  (how many activities finish at M, M − 1, …) cannot see that chain.
- **"Squeeze" moves worked.** Shift everything after a window of 10–30 activities one period left, and ask CP-SAT whether the window can
  absorb the lost period. On the first day this gave 8 improvements in 18 runs. Doing the same in reverse time found improvements where the
  forward move had stalled.
- **Soft resource capacities failed; "ghosts" worked.** This is a transfer from graph colouring. Fix the makespan at M − 1 and minimise
  resource overload: that failed, because soft capacities remove CP-SAT's cumulative propagation (its LP bound drops to about 0). Keep
  capacities hard instead, and let some activities be "ghosts" that keep their start time but use no resources, then minimise the ghosts'
  weight in small CP-SAT windows (PartialCol's idea). That worked, with 3 frontier improvements in its first 29 runs.
- **The remaining gap is the main predictor of success.** Improvements per run were about 1 in 91 for gaps below 20, and 5 in 37 to 4 in 19
  for gaps of 40 or more. A logistic model with every run feature available (622 runs, 53 hits) scored AUC 0.555, no better than ranking by
  gap. Yield per run stayed flat when a run got less CPU, so more parallel lanes simply meant more runs.
- **Small solver settings mattered.** Turning off CP-SAT's presolve, symmetry detection and linearisation for the small window models cut
  solver time 9–58 % with identical optima.
- **A short genetic algorithm with forward-backward improvement is a good screen, not a search.** Seeded from the best schedule, 25 s per
  instance found 7 improvements across 301 instances. Every gain landed within 2 s, and longer runs or other seeds found nothing more.
- **Path relinking between independent best schedules was not worth building.** Two independently found best schedules agreed on only
  62–72 % of their activity orderings, so the space between them is essentially the whole problem.

## 5. Lessons about the process

- **The checker is worth more than the solver.** A producer bug (activity ids off by one) once printed a "closure" of RG300_310. Writing the
  certificate and running the independent checker rejected it at once ("activities 18 and 33 are compatible"). Every certificate type had its
  checker written and frozen before any claim it judges.
- **Audit checkers with more than random tiny instances.** In one checker audit, random small instances did not catch a mutant with a weakened
  memo key. Only differential runs on medium-size instances showed that it gave wrong refutations. That checker is newer than this
  repository and is not included here, but the audit method carries over: mutants, real-size inputs, and node-count comparisons.
- **Write the stopping rule down before the experiment.** Several A/B tests on the upper-bound search were confounded by depletion: the
  easy instances get used up over time. Deciding the comparison and its threshold in advance (like the 3× bar above) kept effort from
  drifting into marginal ideas.
- **Measure where the search is stuck before adding memory or time.** The block-gap worlds looked memory-bound, but a bounded-memory
  version showed they were time-bound, which saved a dead end. Likewise "it needs more CPU" was false for the upper-bound search, where
  yield per run did not depend on CPU share.
