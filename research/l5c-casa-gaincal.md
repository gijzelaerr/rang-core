# L5-C: CASA `gaincal` as the second direction-independent comparator of the core's solver

Protocol frozen 2026-10-31 on branch `l5c-casa-gaincal` (from `main`
`8ab6db8`), in the commit that adds this file, before any CASA task or any
comparison was run on the fixture or the LUNO data. Task L5-C of
[big-plan.md](big-plan.md) (ecosystem survey section 5.2 item 8,
[ecosystem-survey.md](ecosystem-survey.md)). Status: **implemented and
measured 2026-10-31 on the fixture and the four-station slice; the whole
array was not run (the frozen budget rule fails: 341 min estimated against
60).** CASA G on the core's intervals is within L5's held-out margin of the
core on the slice (parallel hands +7.6e-5) and outside it on the fixture
(+1.23e-4); the convergence tail is **reproduced** on the slice (the 4
intervals the core leaves unsettled at 1e-4 are all among CASA's unsettled,
enrichment 5.6 against a threshold of 5) and undecidable on the fixture (no
interval at 1e-4). CASA stops by its
chi-squared rule long before convergence (median product step 3.8e-5 / 6.4e-4
on a restart) and never hits its own 50-iteration cap in a first solve. No
default changes. Results are added below the protocol, never edited into it;
this status line is the only edit above "Measured result".

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

## Implemented (commits 80bda5c, 744f874)

- `examples/oracle_casa_gaincal.py run {fixture,slice} <run>`: host
  `prepare` (L5's loader, gates that the solve flags contain every held-out
  cell), then one network-less container per step, each timed inside the
  container by `/usr/bin/time`: `copy` (KERN python3), `solve G | G-r1 |
  G-r2 | G-r3 | T | G-wholeband` (CASA venv), and per arm `flags`, `apply`,
  `export`; `receipt.json` with the image ID, the source MS tree hash, code
  hashes, git head and status, settings, step timings and the SHA256 of
  every caltable tree and export. The container side imports no `rang`.
- `examples/compare_l5c.py compare {fixture,slice} <run>` and `archive`:
  the measures above; `compare.json` and `per-interval.npz` (per-interval
  convergence distances and strata) in the run directory; the archive
  [results/l5c-casa-gaincal.json](results/l5c-casa-gaincal.json) (81 KB,
  derived numbers and hashes only).
- `python/rang/formats/caltable.py`: `time_interp='nearest'` in
  `_interpolate`, `jones_terms` and `correct` (closest float32 relative
  slot, ties to the earlier one, its value and flag); `linear` stays the
  default and unchanged. Tests in `tests/test_l5c.py` (3 unit tests; 3
  archive tests that recompute the verdicts and, with the run directory, the
  threshold counts).

## Measured result (2026-10-31)

Run `outputs/l5c-20261031-01` (log `outputs/l5c-20261031-01.log`), code at
`744f874`, image `rang-o-casa:6.7.6.14` (ID `sha256:24822b40…`),
`RAYON_NUM_THREADS=4`, `OMP_NUM_THREADS=4`, load 5–10 (siblings),
`MemAvailable` 25.7 GiB. Every gate passed on both sets: the MS copies equal
the core's arrays element for element (ANTENNA1/2, TIME, DATA,
WEIGHT_SPECTRUM, model) and read back (MODEL_DATA, FLAG, FLAG_ROW,
SCAN_NUMBER); the core D reproduces L5's D (`7b370c13…`) and K's `original`
(`4ed2aa89…`), D_T reproduces L5's D_T; every QuartiCal array is on the
core's grid; the numpy held-out error reproduces `fused_pass` to 2e-15;
CASA wrote at most one solution per interval and antenna, every solution
time inside its bin and every `CHAN_FREQ` at its chunk centre. A labelled
pipeline smoke on the fixture (`-00-smoke`, the same code before two
formatting and reporting edits) gave the same numbers and is deleted.

### Coverage

| | fixture | slice |
| --- | ---: | ---: |
| intervals (time × frequency bins) | 7 × 128 = 896 | 16 × 64 = 1024 |
| chunks with a CASA table (G / T) | 42 / 42 of 128 | 26 / 27 of 64 |
| intervals with observed pairs: triangle / under-constrained / none | 285 / 3 / 608 | 335 / 97 / 592 |
| CASA G solutions flagged | 2 of 1152 | 14 of 1652 |
| core D valid gains covered by CASA G | 100 % | 97.6 % |
| held-out cells matched (validation / test) | 9,115 / 9,169 (all) | 11,693 / 11,704 of 11,742 / 11,767 |

The chunks without a table are those whose 32 channels carry no unflagged
weight (CASA: "Found no unflagged data"); the core has no valid gain there
either. On the slice CASA flags 14 solutions that the core solves (19 first
solves report "CHI2 IS SPURIOUSLY ZERO", the exactly determined intervals).

### Held-out error (matched cells; MSE_test, relative to D)

| Arm | fixture parallel | fixture total | slice parallel | slice total |
| --- | ---: | ---: | ---: | ---: |
| D (core, cap 50) | 45.649306 | 24.919608 | 0.22934168 | 0.27582787 |
| D_T (= QuartiCal 0.2.8-dev) | +5.6e-10 | +6.9e-10 | −4.2e-10 | +7.3e-10 |
| R (core, 500 iterations) | −1.05e-7 | −1.23e-7 | +3.6e-8 | −7.9e-8 |
| QC027 (QuartiCal 0.2.7, archived) | 0 (held out) | 0 | −2.63e-2 (in-sample) | −2.51e-2 |
| QC028 (QuartiCal 0.2.8-dev, RV1) | +5.6e-10 (held out) | +6.9e-10 | −2.63e-2 (in-sample) | −2.51e-2 |
| D with off-diagonals zeroed (floor) | +2.41e-4 | +4.38e-2 | +9.45e-5 | +3.38e-1 |
| **CASA G** | **+1.23e-4** | +4.37e-2 | **+7.57e-5** | +3.38e-1 |
| CASA G after three restarts | +9.0e-5 | +4.37e-2 | +1.16e-4 | +3.38e-1 |
| CASA T | +13.8 (×14.8) | +12.7 | +3.83e-2 | +3.54e-1 |

Validation (parallel, relative to D): CASA G +1.56e-4 / +5.9e-5, the floor
+2.29e-4 / +2.7e-5, CASA T +13.4 / +3.9e-2 (fixture / slice).

**Margin verdict (frozen, δ = 1e-4, parallel hands, test):**

| CASA G against | fixture | slice |
| --- | --- | --- |
| D | +1.23e-4: **outside** (and worse) | +7.57e-5: **within** |
| D_T | +1.23e-4: outside | +7.57e-5: within |
| QC027 / QC028 | +1.23e-4: outside (both equal D / D_T) | in-sample: no verdict (+2.7e-2) |

On both sets CASA G is closer to D than the frozen "floor" is (D's own
diagonal entries, not refitted: +2.4e-4 / +9.4e-5). That floor is not a
lower bound for a diagonal model, since a refitted diagonal (CASA) beats
it; whether a refitted core diagonal would close CASA's remaining gap to D
is **not measured**, so the gap is not attributed to the model class or to
the solver (post-hoc reading). The total MSE fails by construction (the
cross hands of a diagonal model are the cross-hand data power, as O-CASA
found); CASA G's total differs from the floor's by −1.0e-4 / −5.8e-6. CASA
T (one gain for both polarisations) is ×14.8 on the fixture, where the core
D's X and Y gains differ by 45–67° in phase (median per antenna; amplitude
ratio 0.996–1.036, post hoc), and costs 3.8 % on the slice.

### Applycal route against the reader route

| | fixture G | fixture T | slice G | slice T |
| --- | ---: | ---: | ---: | ---: |
| values compared (cells × correlations) | 368,016 | 368,016 | 468,888 | 470,224 |
| max relative difference CASA vs reader `nearest` | 6.2e-7 | 5.6e-7 | 3.8e-7 | 3.6e-7 |
| max in float32 eps of the cell's largest correlation | 4.3 | 4.7 | 2.9 | 2.6 |
| flag differences | 0 | 0 | 0 | 0 |
| rows × chunks given another bin's solution by `nearest` | 120 | 120 | 36 | 0 |
| of which held-out cells | 0 | 0 | 5 | 0 |
| MSE_test parallel, applycal route vs bin-exact | −9e-9 | +3e-10 | +1.9e-8 | −5e-9 |

Within DF-IO's bound (1e-6 relative) everywhere: CASA's `applycal` with
`interp='nearest'` and the core's reader with the new `nearest` agree,
including where CASA's centroid time stamps send a row to the neighbouring
bin's solution. No tie was counted, so the tie rule is untested.

### Gain products (parallel hands, observed pairs; relative difference)

| Pair of arms | fixture median / p95 / max | slice median / p95 / max |
| --- | --- | --- |
| CASA G vs D | 4.9e-4 / 2.0e-3 / 1.6e-2 | 7.5e-5 / 2.1e-4 / 6.5e-3 |
| CASA G vs R | 4.9e-4 / 2.0e-3 / 1.6e-2 | 7.5e-5 / 2.1e-4 / 7.2e-3 |
| CASA G restarted vs R | 4.5e-4 / 1.7e-3 / 1.4e-2 | 7.0e-5 / 1.8e-4 / 2.0e-3 |
| CASA T vs D | 0.71 / 0.89 / 0.94 | 4.7e-3 / 1.1e-2 / 0.20 |
| D vs R | 8.5e-14 / 7.3e-9 / 2.1e-5 | 1.1e-17 / 1.8e-9 / 1.2e-3 |
| D_T vs D | 7.1e-16 / 1.8e-11 / 1.1e-7 | 1.8e-16 / 1.9e-12 / 1.2e-6 |
| QC027 vs D | 1.0e-16 / 2.4e-16 / 4.6e-16 | 1.1e-3 / 3.1e-3 / 3.4e-2 (in-sample) |
| QC028 vs D_T | 1.0e-16 / 2.4e-16 / 4.9e-16 | 1.1e-3 / 3.1e-3 / 3.4e-2 (in-sample) |

All pairs (not only observed): CASA G vs D max 1.6e-2 / 2.1e-2.

### Convergence

| | fixture | slice |
| --- | ---: | ---: |
| intervals compared (observed pairs in both) | 287 | 400 |
| core: gain test at the cap, replay = D's converged fraction | 0.98435 = 0.98435 | 0.98332 = 0.98332 |
| core: gains failing at the cap / their intervals | 18 / 5 | 28 / 7 |
| core D vs R, Frobenius, median / p95 / max | 4.1e-13 / 2.5e-8 / 1.9e-5 | 2.5e-16 / 1.4e-8 / 2.1e-3 |
| CASA first vs restarted, median / p95 / max | 6.4e-4 / 3.2e-3 / 1.6e-2 | 3.8e-5 / 3.8e-4 / 7.0e-3 |
| CASA restart steps 1 / 2 / 3, median | 6.3e-4 / 6.7e-6 / 7.8e-7 | 3.8e-5 / 2.7e-6 / 9.8e-7 |
| CASA "Reached iteration limit: 50" (first solve / restarts) | 0 / 0 | 0 / 1 (restart 1) |
| Spearman, core D–R vs CASA first–restarted | 0.61 | 0.70 |

Thresholds (core capped: D–R ≥ thr; CASA unsettled: first–restarted ≥ thr):

| | fixture 1e-4 | fixture 1e-6 | slice 1e-4 | slice 1e-6 |
| --- | ---: | ---: | ---: | ---: |
| core capped | 0 | 4 | 4 | 7 |
| CASA unsettled | 283 | 287 | 71 | 389 |
| overlap | 0 | 4 | 4 | 7 |
| fraction of core-capped CASA-unsettled | – | 1.0 | 1.0 | 1.0 |
| enrichment | – | 1.0 | **5.6** | 1.03 |
| core capped: triangle / under-constrained | 0 / 0 | 2 / 2 | 1 / 3 | 1 / 6 |
| CASA unsettled: triangle / under-constrained | 281 / 2 | 285 / 2 | 43 / 28 | 335 / 54 |

**Tail verdict (frozen):** fixture **undecidable** (no interval where D is
1e-4 from R: the fixture's tail at the cap moves products by ≤ 2e-5);
slice **reproduced** (all 4 core-capped intervals are CASA-unsettled,
enrichment 5.6 ≥ 5).

Post hoc (labelled): every interval with a gain failing the core's test at
the cap (5 on the fixture, 7 on the slice) is also unsettled for CASA, and
ranks in CASA's top 30 % (fixture: 0.70–0.997 quantile) and top 2 % (slice:
0.983–0.998) by distance to CASA's own restarted solution. Six of the
slice's seven are under-constrained (five in frequency bin 35). CASA's own
50-iteration cap never binds in a first solve: CASA stops on its
chi-squared rule everywhere, with its products a median 3.8e-5 (slice) and
6.4e-4 (fixture) from where three restarts take them, against the core's
D-to-R median of 1e-16 to 1e-13; three restarts settle CASA to about 1e-6.
So both solvers are slow in the same intervals (a property of the data);
QuartiCal's cap shows it as an unpassed gain test, CASA's looser stop rule
hides it.

Post hoc, the restart probe's bin exactness: the restarts pre-apply with
`interp='nearest'`, which hands some rows the neighbouring bin's solution.
On the fixture no solve-unflagged cell lies in such a row (G, G-r1, G-r2
tables); on the slice 30 / 113 / 51 solve cells do, in 14 intervals
(frequency bins 1 and 35), none of them among the 400 compared intervals,
the 4 core-capped or the 7 failing-gain intervals. The verdict counts are
unchanged without them (4 / 4, enrichment 5.6).

### Cost (same session, 4 threads each)

| | fixture | slice |
| --- | ---: | ---: |
| core D solve wall (median of 3) / CPU | 0.049 s / 0.18 s | 0.096 s / 0.36 s |
| core R (500 iterations) wall / CPU | 0.48 s / 1.83 s | 0.89 s / 3.40 s |
| CASA G: `gaincal` task seconds (calls, mean) | 17.2 s (128, 0.134 s) | 7.2 s (64, 0.113 s) |
| CASA G: container wall / peak RSS | 20.1 s / 295 MB | 8.7 s / 278 MB |
| CASA G whole band, one call: task / container | 0.27 s / 1.6 s | 0.79 s / 4.9 s |
| CASA T: task seconds / container wall | 13.7 s / 16.1 s | 14.5 s / 18.0 s |
| CASA restarts 1–3: task seconds each | 11.0 / 9.8 / 11.4 s | 7.9 / 8.4 / 9.0 s |
| CASA applycal G: task seconds / container wall | 2.0 s / 3.3 s | 3.0 s / 7.0 s |
| whole oracle run (all steps) / comparison | 92.9 s / 6.8 s | 92.0 s / 10.4 s |

CASA's chunked G solve costs 350× (fixture) and 75× (slice) the core's D
wall; most of it is per-call overhead (a whole-band call of all channels
costs 0.27–0.79 s, about 2–7 chunk calls). Even one call per set is 5.5–8×
the core's D.

### Whole array (frozen rule): not run

CASA's solve-plus-apply wall on S, all frozen steps (solve G, three
restarts, T, whole band, apply G and T, container walls): 79.7 s. Scaled by
the visibility count: whole array × 256.7 = 341 min, stations 0–31 × 82.7 =
110 min, both above 60 min (`MemAvailable` 25.7 GiB passed). So A is **not
run**, as frozen. (Counting only the G solve and apply, 15.7 s, would give
67 and 22 min; that reading drops the restarts, which carry the tail
measure, and is not the frozen one. Linear scaling also overstates CASA's
per-call-dominated cost; recorded as an open item.)

## Decision

- **Margin (primary).** CASA G is within δ of the core D on the slice
  (+7.6e-5) and outside it on the fixture (+1.23e-4, worse), the same
  against D_T and, on the fixture, QuartiCal 0.2.7 and 0.2.8-dev (which
  equal D and D_T there). On both sets CASA is closer to D than D's own
  unrefitted diagonal part (+2.4e-4 / +9.4e-5); what CASA's remaining gap
  is due to is not measured.
- **Tail.** Reproduced on the slice (4 of 4 core-capped intervals, enrichment
  5.6 against 5), undecidable on the fixture, not measured on the array.
  On the evidence here the cap-50 tail sits in
  intervals the data barely constrain, not in QuartiCal's update; the
  fixture and slice tails are 1.6–1.7 % of gains and cannot speak for the
  array's 17 %.
- **What it means (no default change).** A better stop rule (L5 Q2) or
  Anderson (Q3) can only cut cost; the #455 comment can add that CASA's
  solver is slow in the same intervals and that its looser chi-squared stop
  hides it; the stop fraction should count only constrained intervals.
- Cost is not gated: CASA is 75–350× the core's D wall on these sets as run
  (chunked), 5.5–8× in one call.

## Deviations and post-hoc items

1. **Smoke 5 was incomplete.** CASA does print "Reached iteration limit: 50
   iterations." on stdout (not in the CASA log) when its cap binds; the
   smoke never hit the cap. Seen once (slice, restart 1, time bin 0). The
   frozen log grep recorded it; convergence at the criterion is not
   printed, so iteration counts remain unobservable.
2. **Added reported numbers** (not used by a verdict): the second and third
   restart steps, the CASA-unsettled rank of the core's failing intervals,
   the applycal-vs-bin-exact MSE for T, CASA G restarted in the held-out
   table.
3. **A labelled pipeline smoke** (`outputs/l5c-20261031-00-smoke`, the
   fixture, real data) ran before the final formatting and the two extra
   restart numbers; identical numbers; deleted (344 MB).
4. **Whole array not run** by the frozen budget rule (above).
5. **QuartiCal on the slice is in-sample** (both archives solved on every
   cell), as stated in the protocol: no verdict.
6. `--user` container runs wrote the copies with `copyfile` (no mode bits)
   so the read-only source MSs stayed untouched; their tree hashes are in
   each `receipt.json`.
7. **Package lists.** The frozen implementation note promised the image's
   `dpkg`/`pip` lists in the receipt; `receipt.json` has the image ID only.
   Added after the run: `/opt/image-{debs,pip}.txt` copied into
   `outputs/l5c-20261031-01/`; they are byte-identical to O-CASA's
   (`outputs/o-casa-20261030-01/`), as the image ID is.
8. **Post-hoc checks** (scratch scripts, deleted): the restart probe's bin
   exactness and the fixture's X/Y gain phases (both above).

## Open items

- The whole array (or stations 0–31) with a cheaper CASA arm: one call per
  time bin over a 64-spw MS (`mstransform`) instead of 64 chunk calls, or a
  budget above 60 min. That is where #455's 17 % tail is.
- CASA's iteration count per interval is not observable through
  `gaincal`; a print level would need the C++ `VisCalSolver2::prtlev`.
- The tie rule of CASA's `nearest` (the reader takes the earlier slot) is
  untested: no tie occurred.
- O-CASA's ×1.10 parallel-hand gap (K·G·B at 120 s and per channel) is
  +7.6e-5 for G alone on the core's intervals (post hoc, a note for L4):
  the intervals and the chain changed together, so this does not say which
  of them made the gap.
- A refitted diagonal solve of the core (or a diagonal QuartiCal term) on
  the same intervals would say whether CASA's remaining +7.6e-5 / +1.23e-4
  is the model class or the solver.

## Tool timings

| When (UTC) | Tool run | Wall | Peak RSS | Note |
| --- | --- | ---: | ---: | --- |
| 2026-10-30 22:45 | `uv venv` + `uv pip install -e .[pointing,beam,test,imaging,formats]` (builds the extension) | 166 s | 1.15 GB | public PyPI |
| 2026-10-30 22:47–22:55 | environment smokes 1–4 in `rang-o-casa` (synthetic data) | 3.5–6 s each | ≈ 300 MB | scratch, deleted |
| 2026-10-30 22:58 | `inspect_sets.py` (L5 loader, orientation) | 1.6 s | 151 MB | scratch |
| 2026-10-30 23:03 | `oracle_casa_gaincal.py run fixture` smoke `-00-smoke` | 136 s | 125 MB host, 308 MB container | labelled, deleted |
| 2026-10-30 23:08 | `compare_l5c.py compare fixture` on the smoke | 6.8 s | 744 MB | |
| 2026-10-30 23:11 | **`oracle_casa_gaincal.py run fixture` `-01`** | 92.9 s | 125 MB host, 302 MB container | load 5 |
| 2026-10-30 23:12 | **`compare_l5c.py compare fixture` `-01`** | 6.8 s | 729 MB | |
| 2026-10-30 23:13 | **`oracle_casa_gaincal.py run slice` `-01`** | 92.0 s | 100 MB host, 287 MB container | load 10 |
| 2026-10-30 23:15 | **`compare_l5c.py compare slice` `-01`** | 10.4 s | 555 MB | |
| 2026-10-30 23:16 | `compare_l5c.py archive` | < 1 s | | 81 KB |
| 2026-10-30 23:20 | `bash tools/check-all.sh` (`outputs/l5c-20261031-check-all.log`), head 05831e7 plus this report | 557.6 s | 1.98 GB | **overall: PASS**; pytest 686 passed, 15 skipped in 130 s; includes the first cargo and maturin builds of this worktree |

## For the coordinator

**Shared files: none edited.** Added: `examples/oracle_casa_gaincal.py`,
`examples/compare_l5c.py`, `tests/test_l5c.py`, this report and
`research/results/l5c-casa-gaincal.json`; changed (documented fix):
`python/rang/formats/caltable.py` (`time_interp='nearest'`, default
`linear` unchanged). No CLI stage, so `docs/cli.md` is unchanged. Lines for
the shared files, verbatim:

- **`research/STATE.md`, new top entry:**

  > L5-C CASA `gaincal` as the second solver comparator (big plan),
  > 2026-10-31 (implemented; measured; [l5c-casa-gaincal.md](l5c-casa-gaincal.md)).
  > Protocol frozen first. CASA 6.7.6 `gaincal` (O-CASA's image) solves on
  > L5's own intervals (2 integrations × 32 channels: one call per chunk,
  > scans relabelled to the core's time bins, `solint='inf'`,
  > `minblperant=1`, `minsnr=0`), flags and model, with the held-out cells
  > flagged, on the fixture and the LUNO four-station slice. Held-out test
  > error on the parallel hands against the core's QuartiCal port: +7.6e-5
  > on the slice (within L5's δ = 1e-4) and +1.23e-4 on the fixture
  > (outside); both are below the core's unrefitted diagonal part (+9.4e-5,
  > +2.4e-4), and what the remaining gap is due to is not measured. CASA's
  > `applycal` and the core's reader (new `nearest` time interpolation)
  > agree to 6.2e-7. The convergence tail is reproduced on the slice: the 4
  > intervals where the core's cap-50 iterate is 1e-4 from its
  > 500-iteration run are all unsettled for CASA (enrichment 5.6 against a
  > threshold of 5); post hoc, all 12 intervals with a gain failing the
  > core's test at the cap rank in CASA's top 2 % (slice) / 30 % (fixture),
  > and six of the slice's seven are under-constrained. CASA never hits its own
  > 50-iteration cap in a first solve: its chi-squared stop leaves the
  > products 3.8e-5 (slice) / 6.4e-4 (fixture) from its restarted solution.
  > The fixture is undecidable (no interval at 1e-4), the whole array not run
  > (the frozen budget rule: 341 min against 60). CASA costs 75–350× the
  > core's D wall as run. No default changes. Archive
  > `results/l5c-casa-gaincal.json`.

- **`research/README.md`, index entry:**

  > New, 2026-10-31: big plan task L5-C, [CASA gaincal comparator](l5c-casa-gaincal.md): CASA G on L5's intervals is within the held-out margin of the core on the slice (+7.6e-5) and outside it on the fixture (+1.2e-4), and is slow in the same intervals (the slice's tail is in the data), at 75–350× the cost.

- **`research/big-plan.md`**: "L5-C done 2026-10-31 (`l5c-casa-gaincal.md`:
  CASA G within δ of the core on the slice, outside on the fixture; tail
  reproduced on the slice (4 of 4, enrichment 5.6), undecidable on
  the fixture, array not run by the budget rule; no default change)."

- **`research/l5-solver-science.md`** (an "After L5-C" note below its open
  items): "L5-C (`l5c-casa-gaincal.md`) ran CASA `gaincal` G on the same
  intervals: the core's capped intervals on the slice are also CASA's
  slowest (tail reproduced, 4 of 4, enrichment 5.6; post hoc, six of seven
  failing-gain intervals under-constrained), so the 50-cap tail is a property of the
  data there; the array remains open."

- **`research/tool-timings.md`**, rows:

  | Date | Tool / stage | Input | Wall | Peak RSS | Notes |
  | --- | --- | --- | ---: | ---: | --- |
  | 2026-10-30 | `uv venv` + `uv pip install -e .[pointing,beam,test,imaging,formats]` (L5-C worktree) | public PyPI | 166 s | 1.15 GB | builds the extension |
  | 2026-10-30 | CASA 6.7.6 `gaincal` environment smokes 1–4 (L5-C) | synthetic copy of O-CASA's slice MS | 3.5–6 s each | ≈ 300 MB | scratch, deleted |
  | 2026-10-30 | `oracle_casa_gaincal.py run fixture` (labelled smoke `l5c-20261031-00-smoke`) | fixture `work.ms` | 136 s | 308 MB container | deleted |
  | 2026-10-30 | `oracle_casa_gaincal.py run fixture` (`l5c-20261031-01`) | fixture `work.ms`, 128 chunks | 92.9 s | 302 MB container | G solve 20.1 s (128 calls, 0.134 s each), T 16.1 s, restarts 12–14 s each, apply 3.3 s |
  | 2026-10-30 | `oracle_casa_gaincal.py run slice` (`l5c-20261031-01`) | `luno-solve-20261029-02/work.ms`, 64 chunks | 92.0 s | 287 MB container | G solve 8.7 s (64 calls, 0.113 s), T 18.0 s, restarts 10–12 s, apply 7.0 s |
  | 2026-10-30 | `compare_l5c.py compare fixture / slice` | `-01` | 6.8 s / 10.4 s | 729 / 555 MB | core D 0.049 / 0.096 s wall at 4 threads |
  | 2026-10-30 | `bash tools/check-all.sh` (L5-C) | branch `l5c-casa-gaincal` | 557.6 s | 1.98 GB | overall PASS; pytest 686 passed, 15 skipped |

- **`research/upstream-notes.md`**, QuartiCal (RATT), for #455 (to file,
  not filed): "CASA 6.7.6 `gaincal` G solved on the same 2 × 32 intervals
  of the LUNO four-station slice is slowest in the same intervals as
  QuartiCal 0.2.7's `complex` (measured with rang's validated port of it:
  Spearman 0.70 of the per-interval distance to each solver's own long
  run; all 4 intervals whose products still move by 1e-4 between 50 and
  500 iterations are unsettled for CASA; post hoc, all 7 intervals with a
  gain failing the 1e-7 test at 50 iterations are in CASA's top 2 %, and
  six of the seven are under-constrained: an antenna with one observed
  baseline, or no observed triangle). CASA shows no tail because its
  chi-squared stop ends earlier (its own 50-iteration cap never binds; its
  products stay 4e-5 median from its restarted solution), with a held-out
  error within 1e-4 of the port's. This supports counting only constrained
  intervals in the stop fraction."
- **`research/non-ratt-observations.md`**, CASA:
  1. `gaincal` `gaintype='G'`/`'T'` silently ignores the frequency part of
     `solint` (`'16s,32ch'` gives one channel); frequency intervals need one
     call per channel selection.
  2. A seconds `solint` does not cut at integration pairs: with 8 s dumps
     `'16s'` drifts up to 8 s from the pair centres and `'12s'` gives 21
     bins for 16 pairs; relabelling scans with `solint='inf'` is exact.
  3. VisCalSolver2's iteration limit (50) is reported only on stdout
     ("Reached iteration limit: 50 iterations."), not in the CASA log or
     the returned dictionary; convergence at its chi-squared criterion is
     not reported at all, so iteration counts are not observable through
     the task.
  4. The chi-squared stop leaves G products a median 6.4e-4 (high-SNR
     fixture) / 3.8e-5 (slice) from the solution a restart reaches; three
     restarts settle to about 1e-6.
  5. `gaincal` pre-applies tables with `calwt=True` hard-coded
     (`task_gaincal.py`), which keeps restarts consistent with one solve.

**Ignored output directories** (nothing here is committed):

- `outputs/l5c-20261031-01` (548 MB: per set the problem arrays, two MS
  copies, six arms of 26–42 caltables, exports, CASA logs, `compare.json`,
  `per-interval.npz`, `receipt.json`) and its log
  `outputs/l5c-20261031-01.log`;
- `outputs/l5c-20261031-check-all.log`.
- Deleted: `outputs/l5c-20261031-00-smoke` (344 MB) and the scratch
  `~/Build/tmp/20261031-l5c` (smokes, scripts).
