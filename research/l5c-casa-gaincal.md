# L5-C: CASA `gaincal` as the second direction-independent comparator of the core's solver

Protocol frozen 2026-10-31 on branch `l5c-casa-gaincal` (from `main`
`8ab6db8`), in the commit that adds this file, before any CASA task or any
comparison was run on the fixture or the LUNO data. Task L5-C of
[big-plan.md](big-plan.md) (ecosystem survey section 5.2 item 8,
[ecosystem-survey.md](ecosystem-survey.md)). Status: **protocol frozen; not
yet run.** Results are added below the protocol, never edited into it; this
status line is the only edit above "Measured result".

## Why

L5 ([l5-solver-science.md](l5-solver-science.md)) measured the core's port of
QuartiCal 0.2.7's `complex` solver: at the archived cap of 50 iterations
1.6 % (fixture), 1.7 % (four-station slice) and 17 % (whole array) of gains
have not passed the 1e-7 gain test, while the held-out error has settled by
iteration 12–24. Task U2 filed this as QuartiCal#455. The open question is
whether that convergence tail is a property of QuartiCal's solver (its
Gauss–Newton step on a 2×2 complex Jones term with a gauge freedom, the
half-step pairing, the per-gain stop test) or of the data (intervals the data
barely constrain, which any solver would leave unsettled). CASA `gaincal` is
an independent solver on the same per-interval χ² (diagonal Jones, solved per
correlation, CASA's own chi-squared stop rule) and is what CARACal's
crosscal runs ([o-casa.md](o-casa.md)). This task puts CASA on L5's data
sets, intervals, flags and model and measures held-out error, gain-product
agreement, convergence and cost.

**This is a comparator measurement, not a default decision.** No default of
the core changes from this task (L5's rule stands); the decision section
states what each outcome would mean.

## Environment smokes (labelled; synthetic data only, before freezing)

Four smokes ran on a copy of O-CASA's slice `work.ms` whose DATA were
**replaced by synthetic gains × MODEL_DATA + noise** (seed 1, no real
visibility used; scratch `~/Build/tmp/20261031-l5c/smoke`, deleted at the
end). They fixed how CASA 6.7.6 can be made to solve on the core's grid:

1. `solint='16s,32ch'` for `gaintype='G'`/`'T'` returns one channel: gaincal
   ignores the frequency part. One `gaincal` per 32-channel chunk with
   `spw='0:a~b'` works; the solution `CHAN_FREQ` is the chunk centre.
2. A seconds `solint` does not reproduce the core's 2-integration bins
   (`'16s'` solution times up to 8 s off the pair centres, `'12s'` 21 bins
   for 16 pairs). With `SCAN_NUMBER` relabelled to the core's time-bin index
   and `solint='inf'`, `combine=''`, CASA gives exactly one solution per bin,
   its time inside the bin.
3. `minblperant=2` writes no table at all for a chunk where two antennas have
   one baseline each; `minblperant=1` solves them (the third antenna flagged
   as it has no data).
4. `applycal` with a channel selection writes CORRECTED_DATA only for those
   channels.
5. CASA reports no iteration count or convergence flag: the result
   dictionary has only `solvestats` (expected, data_unflagged,
   above_minblperant, above_minsnr, used_as_refant); neither stdout nor the
   log at `casalog.filter('DEBUG2')` contains VisCalSolver2's "Reached
   convergence" / "Reached iteration limit" strings (they are compiled in,
   behind a print level the task interface does not set).
6. A second `gaincal` with the first table pre-applied (`interp='nearest'`)
   returns gains within 4e-7 (median) / 2e-6 (max) of 1 on the exact grid;
   a chained third with two tables pre-applied, 1e-7 / 7e-7: the float32
   floor of CASA's solve. Two tables in the pre-apply list are accepted.
7. CASA solves from WEIGHT_SPECTRUM: chunks whose weights are zero report
   "Found no unflagged data" and write no table.

## Data sets (read-only)

As L5, with L5's loader (`examples/run_l5_solver_study.py load`):

1. **F, fixture clean case** (simulated near noise-free MeerKAT scan 9,
   4 stations, 140 rows, 4096 channels, 14 integrations): grid 2 × 32 gives
   7 × 128 intervals; solve flags `backups/clean-t2-f32-solve.npz` (they
   already contain the held-out cells), the archived split in `state.npz`
   (73,720 / 9,115 / 9,169). Model: `RANG_MODEL_DATA` of
   `outputs/tv-response-wsl-20261029-01/clean/work.ms` = `state.npz` `model`
   (the Reynolds point approximation the core and QuartiCal used).
2. **S, LUNO four-station slice**: `core_campaign_array.decode_inputs`
   stations 0–3, `build_state(nant=4)`, seed-7 split 94,047 / 11,742 /
   11,767, `solve_flags(state, 0)` (they contain the held-out cells), grid
   2 × 32 gives 16 × 64 intervals. Model: the stored MODEL_DATA (the model
   of K, L1 and L5). MS: a copy of `outputs/luno-solve-20261029-02/work.ms`.
3. **A, whole array (conditional; budget frozen here).** No MS of the whole
   array exists; it would have to be built (about 9 GB plus
   CORRECTED_DATA). A runs only after F and S are measured and committed,
   and only if at that moment `MemAvailable` ≥ 20 GiB and CASA's measured
   solve-plus-apply wall on S, scaled linearly by the visibility count
   (56·55/2 / 6 baselines, the same channels and integrations), is ≤ 60
   minutes. Otherwise the same rule for stations 0–31 (L5's fallback set);
   otherwise A is **not run**, recorded as such. The fixture and slice tails
   (1.6–1.7 % of gains at the cap) cannot speak for the array's 17 %; the
   report will say so.

## The CASA configurations (mapped onto L5's D)

Image `rang-o-casa:6.7.6.14` (O-CASA; ID `sha256:24822b40…`), container
conventions of O-CASA: `--user $(id -u):$(id -g)`, `--network none`,
`--tmpfs /tmp -e HOME=/tmp`, `OMP_NUM_THREADS=4`, inputs read-only, a fresh
`outputs/l5c-20261031-NN` mounted at `/run`.

**Training-flagged copies.** Per set, two copies of the source MS (`g.ms`,
`t.ms`), made in the container with the KERN python-casacore 3.7.1:

- Gate (stop on failure): ANTENNA1, ANTENNA2, TIME, DATA and
  WEIGHT_SPECTRUM equal the arrays the core solves, element for element;
  the model column (F: `RANG_MODEL_DATA`, S: `MODEL_DATA`) equals the
  core's model; the MS has one field, one DATA_DESC_ID and the expected
  channel count; no virtual model (no `SOURCE_MODEL` column, no model
  keyword).
- Written: FLAG = the core's solve flags on all four correlations (they
  contain the held-out validation and test cells, so the split is identical
  to the core's; CASA cannot weight cells away, so the split is by flags);
  FLAG_ROW = the core's `flag_row`; MODEL_DATA = the core's model (a new
  column on F, a DATA-like description); SCAN_NUMBER = 1 + the core's time
  bin of the row (metadata only; this fixes CASA's time grid to the core's,
  smoke 2). Read back and compared.

**Solves** (one Python process per arm, every call timed and logged with its
parameters and return value):

- **G** (primary): for each 32-channel chunk k (channels 32k … 32k+31; the
  core's frequency bin k), `gaincal(vis=g.ms, caltable=G/ck.tab,
  spw='0:{32k}~{32k+31}', solint='inf', combine='', gaintype='G',
  calmode='ap', refant='m000', minsnr=0, minblperant=1, solnorm=False,
  solmode='', gaintable=[])`. `refant='m000'` is antenna 0, the core's
  reference antenna in K, L1 and L5's phase convention (the products are
  gauge-free, so it does not enter any measure). `minsnr=0`: no SNR cut.
  `minblperant=1`: the closest to the core, which solves every gain with
  data (smoke 3); CASA's default 4 would reject every four-station solution.
  No pre-apply. Everything else at CASA 6.7.6 defaults
  (`refantmode='flex'`, `preavg=-1`, `corrdepflags=False`).
- **T** (scalar control): the same with `gaintype='T'` on `t.ms`.
- **G restarts** (the convergence probe, smoke 6): three further G passes
  on `g.ms`, pass j with the tables of passes 0 … j−1 pre-applied
  (`interp='nearest'`), giving composite gains G0·G1·G2·G3 per interval.
- **Whole-band G** (cost only): one `gaincal` with `spw=''` (all channels,
  one solution per time bin), to bound the per-call overhead of the chunked
  arms.
- A chunk for which CASA writes no table (no unflagged weight, smoke 7) is
  "no solution, all flagged" for every interval of that chunk; it is not a
  failure.

**Apply.** FLAG is set to the solve flags with the held-out cells unflagged
(so CORRECTED_DATA exists on them), then per chunk `applycal(spw='0:a~b',
gaintable=[ck.tab], interp=['nearest'], calwt=[False], applymode='calflag',
parang=False, flagbackup=False)` on `g.ms` (G) and `t.ms` (T). Exported per
set and arm: CORRECTED_DATA, FLAG after `applycal`, the caltables, the CASA
logs, `/usr/bin/time -v` wall and peak RSS of every container step.

## Comparator arms (all evaluated by the same code)

- **D**: the core, archived options, cap 50 (L5's D); its gains SHA256 must
  equal L5's archived D on F (`7b370c13…`) and K's `original` on S
  (`4ed2aa89…`), or no core number is reported.
- **D_T**: `RANG_SOLVE_OPTIONS=qp_weights=transposed`, cap 50 (= QuartiCal
  0.2.8-dev to 1e-15, RV1); hash must equal L5's D_T.
- **R**: archived options, 500 iterations, fraction 2 (L5's reference R).
- **D49**: archived options, cap 49 (a bit-identical prefix of D), for the
  per-gain test at the cap.
- **QC027**: QuartiCal 0.2.7's archived gains: F
  `trials/clean-t2-f32/diagnostics.npz` (the same flags: held out); S
  `outputs/luno-solve-20261029-02/solve/gains.npy` (solved on **all** cells:
  in-sample on the held-out cells, labelled so, never used for a margin
  verdict).
- **QC028**: QuartiCal 0.2.8-dev `referenced=false`
  (`outputs/rv1-20261030-10/{fixture,luno}/qc028u/gains.npy`); F held out, S
  in-sample as QC027.
- Gate: every comparator gain array is (time bin, frequency bin, antenna,
  2, 2) on the core's grid with antennas m000–m003 in order.
- **CASA G, CASA T** from the caltables read by `rang.formats.caltable.read`
  (the core's reader): each row maps to a core interval by its SCAN_NUMBER
  (time bin) and the chunk it was solved for (checked against its
  `CHAN_FREQ` = the chunk centre); the gains are diagonal 2×2 (T: the one
  parameter on both); valid where present, unflagged and finite. Gate: at
  most one solution per (interval, antenna); every solution time inside its
  bin.

## Measures

1. **Held-out error** (L5's metric: mean over cells of the correlation-mean
   `w|r|²`, `r = V − G_p M G_q^H`), on the validation and test cells, total
   and split into parallel (XX, YY) and cross (XY, YX) hands, for every arm,
   on **matched cells** (cells every compared arm predicts; coverage and
   dropped cells reported). Also the core D with its off-diagonal gains
   zeroed (the structural floor of a diagonal model). The numpy evaluation
   must reproduce the core's `fused_pass` losses of D to 1e-6 relative.
2. **CASA's applycal route against the reader route.** From CORRECTED_DATA:
   `P = DATA / CORRECTED` per correlation, `r = DATA − P·M`, the same
   held-out MSE. Per cell, CASA's corrected parallel and cross hands against
   the correction with the read gains by the core's reader semantics with
   `interp='nearest'` (the DF-IO reader implements `linear` only; adding
   `nearest` is this task's documented `caltable.py` change, with a test,
   CASA's tie rule taken from its output and stated). Bound: DF-IO's,
   1e-6 relative per cell, with its post-hoc fallback of 10.3 float32
   epsilons of the cell's largest correlation reported. Reported: the cells
   that `nearest` in time assigns to another bin's solution than the core's
   bin (CASA stamps a solution at the weighted centroid of its unflagged
   data), and the MSE difference between the bin-exact and the applycal
   routes.
3. **Gain-product agreement** (gauge-invariant): for each interval,
   observed pair p < q (at least one solve cell in the interval, L5's
   `observed_pairs`; **primary**, all pairs valid in both reported beside
   it) and hand a ∈ {X, Y}: the relative difference of the parallel-hand
   product, `|P_aa − P'_aa| / |P'_aa|`, with `P_aa` the diagonal of
   `G_p G_q^H` for the core and QuartiCal arms and `g_p,a conj(g_q,a)` for
   CASA. Median, p95 and max over intervals, pairs and hands; per interval
   the max. Between core arms also L5's full Frobenius product distance.
4. **Convergence.**
   - CASA: flagged fraction of solutions, `solvestats` per chunk, chunks
     without a table; iteration counts are not observable (smoke 5); a grep
     of every log for the VisCalSolver2 strings is recorded.
   - **CASA unsettled intervals**: per interval the max over observed pairs
     and hands of the relative difference between the first G solve's
     products and the composite products after three restarts (CASA's own
     long run); also the first restart step alone.
   - **Core capped intervals**: per interval the max over observed pairs of
     L5's relative product distance between D and R; and the per-gain test at
     the cap, `|g_50 − g_49|_F² / |g_49|_F² ≥ τ² = 1e-14` (D vs D49) on
     unflagged gains (its count must equal the core's `converged_fraction`
     of D: the replay check).
   - Thresholds, the same for both solvers: **1e-4 primary**, 1e-6 reported.
   - Reported: the number of intervals unsettled for each solver, their
     overlap, and the enrichment `P(CASA unsettled | core capped) /
     P(CASA unsettled)`; the Spearman rank correlation across intervals of
     the two per-interval distances.
   - **Stratified by identifiability**: intervals classified by their
     observed-baseline graph: "triangle" (every observed antenna on an
     observed triangle, so diagonal amplitudes are identified) or
     "under-constrained" (some observed antenna with one observed baseline,
     or no triangle); counts and every convergence number per stratum.
5. **Cost.** CASA: the sum of the `gaincal` task seconds per arm, the
   container wall and peak RSS of each solve step (`/usr/bin/time -v` inside
   the container, `OMP_NUM_THREADS=4`), the per-call mean, the whole-band
   call, and the apply step separately. Core: D, D_T and R solve wall and CPU
   seconds (`getrusage`), D as the median of three solves, at
   `RAYON_NUM_THREADS=4`, in the same session; load average before and
   after.

## Decision (frozen)

δ = 1e-4 relative (L5's held-out margin).

1. **Margin, primary: parallel-hand MSE_test on matched cells**, CASA G
   against the core D (two-sided: "within the margin" if
   |MSE_G / MSE_D − 1| ≤ δ; "not worse" if MSE_G ≤ (1 + δ) MSE_D is reported
   beside it), and against D_T and, on F, QC027 and QC028 (held out). On S
   QuartiCal's archived gains are in-sample and their numbers are reported
   without a verdict. The total MSE_test (all four hands) is reported; it
   fails by construction for a diagonal model (cross hands, O-CASA), so it
   is not the verdict. The structural floor (D with off-diagonals zeroed
   against D, parallel hands) is reported beside the verdict. CASA T: the
   same numbers, no verdict (a scalar control).
2. **Tail.** On each set with at least one core-capped interval at 1e-4:
   - **reproduced** (the tail is a property of the data, not of QuartiCal's
     solver) if at least half of the core-capped intervals are
     CASA-unsettled at 1e-4 and the enrichment is ≥ 5;
   - **not reproduced** (the tail is solver-specific) if fewer than 10 % of
     the core-capped intervals are CASA-unsettled;
   - **partly** otherwise; **undecidable** on a set with no core-capped
     interval at 1e-4.
   The stratified numbers say whether either solver's unsettled intervals
   are the under-constrained ones.
3. **What it would mean (no default change from this task).**
   - Reproduced: the cap-50 tail is in the data; a better stop rule (L5 Q2)
     or acceleration (Q3) can only cut cost, and #455 should ask for the stop
     fraction to count only constrained intervals.
   - Not reproduced: QuartiCal's update converges slower than CASA's
     diagonal solve on the same intervals; the #455 comment gets CASA's
     number as evidence that the slow mode is in the 2×2 `complex`
     parameterisation or its step (it may sit in the off-diagonal terms
     CASA does not model, which the stratified and diagonal-product numbers
     inform but cannot prove).
   - CASA within the margin: the core's held-out error is matched by an
     independent solver on the same grid; outside: the difference is
     reported with its sign as a measured property of the two solvers.
4. **Cost** is reported, not gated.
5. Any failure is recorded as frozen; anything decided after seeing results
   is labelled post hoc.

## Expected outcome (stated before running)

- Held-out, parallel hands: CASA G close to the core D but outside δ
  (|Δ| between 1e-4 and 1e-2): CASA averages within the interval before
  solving and stops on its chi-squared rule; T worse by a few per cent (one
  gain for both polarisations). Total MSE: CASA worse by about the cross-hand
  data power (O-CASA ×1.38).
- Products: CASA against D at 1e-3 median (O-CASA on other intervals: 0.4 %
  in amplitude).
- Tail: uncertain. If the slice's capped intervals are the 26 intervals with
  two observed baselines (L5 `-05`), CASA with `minblperant=1` will either
  leave them unconstrained (and unsettled: reproduced) or settle them at its
  float32 floor (not reproduced).
- Cost: CASA's chunked solve costs tens of seconds per set, dominated by the
  per-call overhead; the core D 0.3–0.7 s.

## Implementation (to be done after this commit)

- `examples/oracle_casa_gaincal.py`: host `prepare` (the problem arrays
  from L5's loader into `problem.npz`), container `copy` (KERN python3:
  gates, flags, model, scans), container `casa` (CASA venv: G, T, restarts,
  whole band, apply, export), host `receipt` (input, code and output
  SHA256, image ID, package lists, settings); `run` drives the steps for
  one set into a fresh run directory. The container side imports no `rang`.
- `examples/compare_l5c.py`: the measures and the decision, writing
  `compare.json` into the run directory; `archive` writes
  `research/results/l5c-casa-gaincal.json` (derived numbers only).
- `python/rang/formats/caltable.py`: `interp='nearest'` for time (the only
  change; `linear` unchanged), with a unit test.
- `tests/test_l5c.py`: the archive's internal consistency and, when the run
  directory exists, recomputation of headline numbers; skips without the
  outputs.
