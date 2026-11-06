# C4b: applying calibration to a Measurement Set, and W2b: the apply stage

Task C4b of [finish-plan.md](finish-plan.md) (C4), step 7 of
[c1-calibration-chain.md](c1-calibration-chain.md) section 6, together with W2b:
wiring C3a's models and the apply into W2's commands. Branch `fp-c4b-apply-ms`
from main `66c2967`. The kernel underneath is C4a's `rang.cal_apply`
([c4a-apply.md](c4a-apply.md)); the write-back is W1's `rang.core_writeback`
([w1-writeback.md](w1-writeback.md)); the commands are W2's
([w2-commands.md](w2-commands.md)); the models are C3a's `rang.calmodels`
([c3a-models.md](c3a-models.md)).

**Status: implemented and measured. The frozen run -02 failed (section 5); after three
post-hoc ports from CASA's and casacore's sources (section 6) the held-out run -04 passed
every criterion on all ten cases (section 8). W2b is wired and measured (section 9); its
criterion 13 fails as frozen, because E2 still names C4 through the uniform-weights
refusal (section 10).** Sections 1 to 4 are the design and the criteria, written
and committed before the first comparison. No novelty is claimed: this
reproduces CASA `applycal`.

## 0. What was read before this protocol

Read, not recalled: `casa6-mirror` (2023, C1 section 0; older than the oracle)
`VisCal.cc` (`VisCal::correct2`, `VisJones::applyCal2`, `syncCalMat`,
`calcWtScale`, `updateWt2`), `Jones.cc` (`JonesDiag`, `JonesScal`, the general
`Jones` apply, flag and `setMatByOk` rules), `StandardVisCal.cc`
(`BJones::calcWtScale`), `SolvableVisCal.cc` (`calcPowerNorm`, default
normalisation `mean`), `Calibrater.cc` (`correct2`, `calWt()`),
`CTPatchedInterp.cc` (field maps); and `task_applycal.py` of casatasks
6.7.6.14 in `rang-o-casa:6.7.6.14`. `VisBufferImpl2` (`resetWeightsUsingSigma`)
is not in the mirror, so the reset of the weights is measured, not read. What
the sources say, as hypotheses the cases below test:

- **Values under a diagonal flag.** CASA inverts each receptor and, when a
  receptor is bad, sets only that element to 1 (`JonesDiag::setMatByOk`); the
  other side of the baseline is still applied. C4a's kernel instead skips the
  whole division of a correlation when either side is bad. So with `g_x,p` bad
  CASA writes `XX / conj(g_x,q)` and rang wrote `XX`. This is the likely
  source of C4a's "values under solution flags differ" (synth-G: 36,976 of
  117,976 such cells equal DATA in CASA, which fits cells with both sides bad).
- **Weights.** `Calibrater::correct2` resets WEIGHT (and WEIGHT_SPECTRUM)
  from SIGMA in memory for every buffer, but writes them only if some applied
  term has `calWt` true. K, Df, X and general Jones terms force it false.
  For G and T the scale is `|g|^2` before inversion, a bad receptor counting 1,
  XX `p0 q0`, XY `p0 q1`, YX `p1 q0`, YY `p1 q1`. For B it is not per channel:
  `BJones::calcWtScale` takes the mean of `|B|^2` over the unflagged solution
  channels of the time-interpolated table, per antenna and receptor. With
  WEIGHT_SPECTRUM, WEIGHT becomes its channel median (`partialMedians`).
- **Field map.** `gainfield=''`: every field of the table pooled into one time
  series per antenna. A field name: the table's rows of that field. `nearest`:
  per MS field the sky-nearest field of the table (a single table field serves
  every MS field; a tie is an error). `caltable._series` instead takes the
  row's own field when the table has it, which is none of these for `''`.
- **CORRECTED_DATA** is added by `calibrater.open(addcorr=True)` when absent;
  W1's `ensure_column` adds it as `clearcal` does (initialised to DATA).
  FLAG_ROW: the VisBuffer writes FLAG; whether FLAG_ROW changes is measured.

A capability probe before this protocol (`/mnt/d/rang/outputs/c4b-20261106-00-probe`,
README there): CASA 6.7.6 `applycal` accepted a rang-written `J Jones` (general
2×2) table, but its output matched none of the general-Jones readings I tried
(max relative 0.73 to 1.06) and its flags looked diagonal. CASA is therefore not
used as the oracle for the `complex` term (section 3.3).

## 1. Design (proposed)

- **`python/rang/applycal.py`**: `applycal(ms, gaintable, interp, gainfield,
  calwt, field=None, applymode="calflag", column="CORRECTED_DATA",
  chunk_rows=None, session=None, flag_backup=..., spw=None)`, CASA's
  argument semantics (a one-element `calwt` or `interp` list is broadcast, as
  `task_applycal.py`). For each row chunk of W1's `WriteBack`: read DATA, FLAG,
  FLAG_ROW, the row columns and (when weights are written) WEIGHT,
  WEIGHT_SPECTRUM, SIGMA, SIGMA_SPECTRUM; for each (FIELD_ID, DATA_DESC_ID) of
  the selected rows, run `rang.cal_apply.apply` with each table's rows chosen by
  the field map; write CORRECTED_DATA of the selected rows (other rows keep
  theirs), FLAG = input OR new, and the weights. Returns a summary.
- **Field map** in `rang.cal_apply.pack`: a table field per call (`None`: all
  fields pooled), so `caltable.py` is unchanged.
- **`core/src/cal/apply.rs`**: (a) per-receptor substitution under a diagonal
  flag, as `JonesDiag::setMatByOk`, in both directions; (b) a binned general
  2×2 apply for the `complex` term (`apply_jones`: per row a time bin, per
  channel a frequency bin, `(bin_t, bin_f, ant, 2, 2)` gains and validity;
  `G_p^-1 V G_q^-H` in float64, written complex64), with CASA's general-Jones
  flag rule (`Jones::flagRight` then `flagLeft`: a bad gain of either antenna
  flags all four correlations, and input flags spread as those rules spread
  them) and its `setMatByOk` (a bad side is the identity, the other side still
  applied). Bound as `rang._core.cal_apply_jones`, wrapped in
  `rang.cal_apply.apply_jones`.
- **Weights** (`calwt`), in `applycal.py` with the kernel: G and T scales from
  the kernel's corrupt direction on unit visibilities (`|g_p conj(g_q)|^2` per
  correlation, a bad receptor 1); B from the time-interpolated table on its own
  solution channels (mean of `|B|^2` over unflagged channels). Written only when
  some table of type G, T or B has `calwt` true; otherwise WEIGHT,
  WEIGHT_SPECTRUM, SIGMA and SIGMA_SPECTRUM are not touched.
- **`applymode`**: `calflag` (CASA's default) and `calflagstrict` (also flags
  the rows of a field and window for which a table has no rows). Other modes
  are refused.
- **W2b, `rang-core calibrate`**: `model.source` `setjy`, `manual` and `lsm`
  call `calmodels.set_model` (`Standard`, `Manual`, `SkyModel`) on the fields
  of the primary section's terms, inside one `WriteBack` session (so a flag
  version is saved before the write, as every writing stage), then those terms
  solve against MODEL_DATA. Polarised `manual` (`polindex`, `polangle`,
  `rotmeas`, or Q, U, V not 0) is refused naming C7a. A term in `secondary` or
  `polcal` with such a model source is refused naming C2d (secondary models
  come from `fluxscale`).
- **W2b, `rang-core apply`**: applies `complex` terms of this run's calibrate
  stage to the fields and scans they were solved on, on their own solution bins
  (the QuartiCal semantics of corrected data), through `cal_apply.apply_jones`,
  into `apply.column` with FLAG OR'd. With `apply.targets` empty every solved
  term is applied to the fields it was solved on. Applying a `complex` term to
  a field it was not solved on (transfer to a target by time interpolation) is
  refused naming C2a, since CARACal transfers CASA G tables (C1 3.1); an
  `interp` on a `complex` table is refused (it has no meaning on its own bins).
  `calwt` on a `complex` term changes nothing (a general Jones term, as CASA).
- Refusals removed: the C3a model refusal and the C4 `apply` refusal. Kept,
  and listed for the coordinator: `data.weights: uniform` for imaging (names
  C4), `preapply` on `complex` (names C4a), `apply.parang` (C6a).

## 2. Data

Copies only, under `/mnt/d/rang/outputs/c4b-20261106-NN/`; inputs read in place.

| Name | Source | Layout |
| --- | --- | --- |
| S | `~/Github/rang/outputs/o-casa-20261030-01/c.ms` (O-CASA arm C) | 192 rows × 2048 ch × 4; one field in use (J1939-6342, id 1); CORRECTED_DATA, WEIGHT_SPECTRUM and SIGMA_SPECTRUM present |
| A | `/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small/a1-small.ms` (A1 small) | 12,480 rows × 64 ch × 4; fields J1939-6342, 3C286-SIM, SIM-GCAL, SIM-TARGET; WEIGHT_SPECTRUM, no SIGMA_SPECTRUM, no CORRECTED_DATA |
| E4 | `~/Github/rang/outputs/e4-20261030-01/casa/x.{K,G,B,Df}` | CASA's own tables of S |

Weight edits (seed 20261109, written with casatools in the CASA container
before either arm runs, so both arms read the same bytes): SIGMA, SIGMA_SPECTRUM
(S only), WEIGHT and WEIGHT_SPECTRUM set to independent uniform values in
[0.5, 2) (so `WEIGHT != 1/SIGMA^2` and the output shows which column the reset
read; channel values differ, so the even-count median rule is visible). FLAG_ROW
edit: 5 % of the selected rows set FLAG_ROW true with FLAG left as it is.

## 3. Criteria (frozen before the first comparison)

### 3.1 C4b against CASA `applycal`

Oracle: `applycal` in `rang-o-casa:6.7.6.14` (casatasks 6.7.6.14), O-CASA's
container conventions, `parang=False`, `flagbackup=False`, on one fresh copy
per case; rang's `applycal` on another fresh copy of the same (edited) input.
Every column compared is read with casacore 3.7.1 (casatools) in the container
from both outputs.

1. **CORRECTED_DATA, class C on every cell of the selected rows, flagged cells
   included**: per correlation `|r − c| ≤ 1e-6 |c|` or
   `≤ 11 eps32 max_k |c_k|` (the oracle's cell), every correlation of every
   cell of the selected rows, whatever either output's flags. Reported
   separately: cells unflagged in both, cells under a solution flag only,
   cells under an input flag.
2. **FLAG exact** on every cell of every row of the MS.
3. **FLAG_ROW** equal to CASA's on every row.
4. **Rows not selected**: CORRECTED_DATA bit-identical to CASA's (both left as
   they were, or both initialised when the column is added).
5. **Weights, `calwt=False`**: WEIGHT, WEIGHT_SPECTRUM, SIGMA and
   SIGMA_SPECTRUM bit-identical to the input in both outputs.
6. **Weights, `calwt=True`**: WEIGHT and WEIGHT_SPECTRUM per value
   `|r − c| ≤ 1e-6 |c|` against CASA's, on every row (CASA works in float32 in
   another order, so bit identity is not claimed); the fraction of values
   bit-identical is reported. SIGMA and SIGMA_SPECTRUM bit-identical to CASA's.
7. **Every other column** of rang's output bit-identical to the input
   (SHA-256 per column).

Cases (tables written by `caltable.write`, synthetic ones seeded 20261109; the
time slots of synthetic tables inside the data's time range unless stated):

| Case | MS | Tables (`interp`, `gainfield`) | `calwt` | Tests |
| --- | --- | --- | --- | --- |
| s-chain | S | E4 K, G, B, Df (`linear`, `nearest`) | False | C4a's chain through the MS path |
| s-G-flags | S | synthetic G, 3 slots: antenna 1 X bad at slot 1, antenna 2 both bad at every slot, antenna 3 Y bad at slot 0 (`linear`) | False | values under one-sided and two-sided flags |
| s-G-calwt | S, weights edited, FLAG_ROW edited | the same G (`linear`) | True | the reset and the G scale, WEIGHT_SPECTRUM and SIGMA_SPECTRUM present; FLAG_ROW |
| s-BT-calwt | S, weights edited | synthetic B on every 8th channel, amplitudes about 1.3, antenna 0 X channels 100-139 bad, plus synthetic T (`linear`) | [True, True] | B's power-norm scale, T's scalar scale |
| s-K-calwt | S, weights edited | E4 K (`linear`) | True | K forces `calwt` off: no weight written |
| s-Gnearest-mix | S, weights edited | synthetic G (`nearest`), E4 Df (`nearest`) | [True, False] | one term with weights, one without |
| a-pooled | A | synthetic G with slots on J1939-6342 and on SIM-GCAL, different values (`linear`, `''`), applied to SIM-TARGET | False | the pooled field map |
| a-named | A | the same (`linear`, `J1939-6342`) | False | a named gainfield (amended, see below) |
| a-nearest | A | the same (`linear`, `nearest`), applied to every field | False | the sky-nearest map per MS field |
| a-chain-calwt | A, weights edited | synthetic B (one slot on J1939-6342), the two-field G (`linear`, gainfield [J1939-6342, nearest]) applied to SIM-GCAL and SIM-TARGET | True | the reset from SIGMA without SIGMA_SPECTRUM; CORRECTED_DATA added |

Pass: every criterion on every case. A case fails as measured and is not
reworded. The three `a-*` field-map cases must also give different
CORRECTED_DATA from each other on SIM-TARGET (so each tells the maps apart).

Amended before the first comparison (a smoke run of rang alone, no CASA
output read): `a-named` first named `SIM-GCAL`, which is also SIM-TARGET's
nearest table field, so it could not differ from `a-nearest` on SIM-TARGET.
It now names `J1939-6342`, the other table field.

### 3.2 C4b's own properties (no external oracle)

8. **Chunking**: `chunk_rows` 50 (S) and 1000 (A) against one chunk of all
   rows: CORRECTED_DATA, FLAG, FLAG_ROW, WEIGHT and WEIGHT_SPECTRUM
   bit-identical, on s-G-calwt and a-chain-calwt.
9. **Idempotence**: rang's `applycal` run twice on s-G-calwt gives the same
   bytes in every column as once (the weights are reset from SIGMA each time).
10. **Flag backup**: a flag version is saved before the first write and
    equals the input FLAG and FLAG_ROW.

### 3.3 The `complex` term (W2b)

There is no external oracle here (section 0). The reference is a float64 NumPy
computation in the checker, written independently of the kernel: `np.linalg.inv`
of each gain (an invalid gain or a zero determinant: the identity on that side),
`G_p^-1 V G_q^-H`, rounded to complex64; flags by `Jones::flagRight` then
`flagLeft` with the gains' validity. It is a reimplementation, so agreement
shows the kernel does what the note says, not that it matches another package.

11. On a copy of A after `rang-core calibrate` (complex, `solint: int`,
    `freqint: 16`, on J1939-6342) and `rang-core apply`: class C against the
    reference on every cell of the solved field's rows, flags exact, the other
    fields' rows of CORRECTED_DATA equal to DATA (the column is added), FLAG of
    other rows unchanged. A second case with seeded gain flags (10 % of
    (time, frequency, antenna) entries made invalid in a copy of the store,
    seed 20261109) applied through `cal_apply.apply_jones` directly.

### 3.4 W2b: the commands

12. **Models**: `rang-core calibrate` with `model.source: setjy`
    (`Stevens-Reynolds 2016`, J1939-6342) on a copy of A writes MODEL_DATA
    bit-identical to `calmodels.set_model` called directly on another copy, and
    its gain store is byte-identical to `core.solve_complex` called with that
    MODEL_DATA (the W2 criterion 3 oracle with `model=`).
13. **Refusals** (pytest): E2-A and E2-B no longer name C3a or C4; their other
    refusals are unchanged except where this task adds one (C7a for a
    polarised model, if the configuration has one); `apply` on a field a
    `complex` term was not solved on is refused naming C2a.
14. **End to end**: `rang-core run` with stages flag, calibrate (complex,
    setjy model), apply and image on a copy of A, imaging J1939-6342 from
    CORRECTED_DATA: exit 0, every stage done, a receipt per call, and
    `image.column: auto` resolved to CORRECTED_DATA. Reported, not gated: the
    image peak against the model's Stokes I at the band centre, and the same
    run's image of DATA.

## 4. Reported, not gated

- The values under solution flags, by kind of flag (one side, both sides,
  missing antenna), against C4a's kernel before the fix (C4a's exports
  `c4a-20261106-0{1..4}` re-evaluated as a development set, labelled post hoc
  against this protocol).
- Wall times of rang's `applycal` and of `applycal` in the container (shared
  host; not timing measurements).

## 5. Run -02, the frozen verdict: FAIL

`python examples/check_apply_ms.py /mnt/d/rang/outputs/c4b-20261106-02`. **The code was not
committed when -02 and -03 ran** (as in C4a); at -02 it was the kernel with the one-sided flag
fix and `apply_jones`, and `rang.applycal` as first written. Image `rang-o-casa:6.7.6.14`
(`sha256:24822b40…`), seed 20261109; 289 s wall (CASA: prepare 6.3 s, 10 `applycal` 26.4 s,
export 59.2 s), heavy lock held. Archive `c4b-20261106-02/c4b.json` and `export/`.

| Case | Cells | Max eps of cell | Max relative | Failing | FLAG | FLAG_ROW | Weights |
| --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| s-chain | 1,572,864 | 4.41 | 1.6e-4 | 0 | exact | equal | unchanged (pass) |
| s-G-flags | 1,572,864 | 5.03 | 6.2e-7 | 0 | exact | equal | unchanged (pass) |
| s-G-calwt | 1,572,864 | 5.03 | 6.2e-7 | 0 | exact | equal | **WEIGHT fail** (9.5e-3); WEIGHT_SPECTRUM 4.5e-7 |
| s-BT-calwt | 1,572,864 | 3.51 | 4.5e-7 | 0 | exact | equal | **WEIGHT fail** (9.5e-3); WEIGHT_SPECTRUM 3.3e-7 |
| s-K-calwt | 1,572,864 | 2.91 | 3.5e-7 | 0 | exact | equal | not written by either (pass) |
| s-Gnearest-mix | 1,572,864 | 3.17 | 2.7e-5 | 0 | exact | equal | **WEIGHT fail** (9.5e-3); WEIGHT_SPECTRUM 3.3e-7 |
| **a-pooled** | 1,720,320 | **11.89** | 1.5e-6 | **33** | exact | equal | unchanged (pass) |
| a-named | 1,720,320 | 8.24 | 1.0e-6 | 0 | exact | equal | unchanged (pass) |
| **a-nearest** | 3,194,880 | **12.66** | 1.5e-6 | **53** | exact | equal | unchanged (pass) |
| a-chain-calwt | 2,334,720 | 10.54 | 1.3e-6 | 0 | exact | equal | WEIGHT and WEIGHT_SPECTRUM 8.1e-7 (pass) |

Every case: rows not selected bit-identical to CASA's (A cases), SIGMA and SIGMA_SPECTRUM
bit-identical to CASA's, every other column bit-identical to the input, the flag version equal
to the input flags. Chunking (50 and 1000 rows) and a second run gave the same bytes. Cells under
a solution flag pass class C on every case (largest 5.17 eps, a-chain-calwt), so the one-sided
substitution is CASA's. **CASA left FLAG_ROW as it was in every case**, including the 5 % of rows
set before the run and rows whose every cell became flagged; rang does the same.

The verdict is **fail**, on three counts, as measured:

1. **WEIGHT on the slice** (2048 channels, SIGMA_SPECTRUM varying per channel): rang took the
   upper middle channel value (index n/2) as the median; CASA's WEIGHT is off from that by up to
   9.5e-3 relative on every value. On A, WEIGHT passes because its spectrum weights are constant
   over channels (no SIGMA_SPECTRUM), so any median rule gives the same value.
2. **Class C on a-pooled and a-nearest**: 33 and 53 cells, at most 12.7 eps (1.5e-6 relative),
   all unflagged; synthetic G with phases uniform on the circle between slots.
3. **The field maps could not be told apart on SIM-TARGET**: CASA's `''` output equals its
   `nearest` output bit for bit there (rang's differ at the ulp level), because the target's
   times are bracketed by SIM-GCAL slots in both maps. The case design, not the code, failed
   this criterion; the named map differs from both.

The weights reset is measured, as the protocol meant to: CASA wrote `1/SIGMA_SPECTRUM^2` (S) and
`1/SIGMA^2` repeated over channels (A) times the scales, WEIGHT_SPECTRUM within 4.5e-7 of rang's
and bit-identical on 40 to 65 % of values; K with `calwt=True` wrote no weights.

## 6. Post hoc after -02 (fitted to the data that found the problems)

- **The median** (`posthoc-median.json` in `-02`): CASA's WEIGHT equals the **lower** middle value
  (index (n − 1) // 2 of the sorted channel values) on every value of the three slice cases
  (exact fraction 1.0); the upper one misses by 9.5e-3, their mean by 4.7e-3, NumPy's median of
  unflagged channels by 0.17. `rang.applycal` now takes the lower middle.
- **Phase tracking.** `CTTimeInterp1::interpolate` reads only the two bracketing rows (or one row
  for `nearest` and exact times) through `fparamArray(rows)`, so `RIorAPArray::trackPhase` runs
  over those rows only; C4a's kernel tracked along an antenna's whole series. CASA's `''` and
  `nearest` being equal while rang's differed (`posthoc-pooled.json`) fits this: with pairwise
  tracking a slot's phase does not depend on which other slots are in the series. The kernel
  now tracks per pair (`apply.rs`, `track`). On C4a's exports this lowered h-G-many-linear from
  9.77 to 7.04 eps and h-G-many-nearest from 8.51 to 4.41 (`c4b-20261106-01-dev`).
- **Post hoc run -03** (same cases and seed, code with both changes): every slice case passes
  (WEIGHT within 3.4e-7, 53 to 67 % bit-identical), a-pooled 5.10 eps (0 failing); a-nearest
  still 53 cells at 12.66 eps, all on one row (baseline 8-10 of J1939-6342 in the last scan,
  YY, `posthoc_nearest.py`), interpolated between slots 11,000 s apart. The distinctness check
  fails again for the reason in 5.3.
- **The linear formula.** casacore 3.7.1's `Interpolate1D<Float, Array<Float>>` (read in
  `rang-casacore-cpp:3.7.1`, `Interpolate1D.tcc`) computes `y1 + ((x − x1)/(x2 − x1))(y2 − y1)`;
  the kernel had `caltable.py`'s `y0 + (x − x0)(y1 − y0)/(x1 − x0)`. Ported after -03.
  Re-evaluated without a new CASA run (`examples/recheck_apply_ms.py`, the five cases whose
  input is an unedited copy; `-03/recheck-casacore-linear.json`): s-chain 4.41, s-G-flags 3.41,
  a-pooled 5.10, a-named 6.17, **a-nearest 9.21 eps**, all pass with flags exact. On C4a's
  exports, every cell (flagged ones included; `c4b-20261106-01-dev/recheck-casacore-linear.json`)
  passes class C on every case but three: h-B-gaps-linear and h-B-gaps-freqnearest (33.1 and
  32.3 eps, C4a's residual of section 7 there, unchanged) and h-Df-2slot-linear (3 cells under
  input flags at 14.0 eps, 5.9e-5 relative; unflagged cells pass at 6.7). Elsewhere the largest
  fell from 9.77 (C4a's head kernel) to 5.05 eps; h-G-many-linear 9.77 → 4.98, synth-G
  5.30 → 2.68.

These fits are not the verdict; section 7 holds out a new run.

## 7. Held-out confirmation (frozen before run -04)

`python examples/check_apply_ms.py <run> --heldout --seed 20261110` on the code committed with
this section: the ten cases of 3.1 with new synthetic values (seed 20261110 for the tables and
for the weight and FLAG_ROW edits), and one change of design for the field maps: in the
held-out set the two-field G also has J1939-6342 slots at the middle of every SIM-TARGET scan,
so on SIM-TARGET the pooled map brackets with J1939-6342 slots and the nearest map with
SIM-GCAL slots. Pass: criteria 1 to 10 of section 3 on every case, unchanged, and the three
field-map cases pairwise different on SIM-TARGET in CASA's output. **The -04 result is the
verdict reported for C4b.** CASA's tables and E4's are the same as in -02.

## 8. Run -04, the held-out verdict: PASS

`python examples/check_apply_ms.py /mnt/d/rang/outputs/c4b-20261106-04 --heldout --seed 20261110`
at commit `ff891a8`, working tree clean during the run, heavy lock held; 277 s (CASA: prepare
5.2 s, 10 `applycal` 24.9 s, export 55.5 s). **Every criterion of 3.1 and 3.2 passes on every
case**, and the three field maps differ pairwise on SIM-TARGET in CASA's output.

| Case | Cells | Max eps of cell | Max relative | Under solution flags (cells, eps) | WEIGHT / WEIGHT_SPECTRUM max relative (bit-identical) |
| --- | ---: | ---: | ---: | --- | --- |
| s-chain | 1,572,864 | 4.41 | 1.6e-4 | – | unchanged, bit-identical to the input |
| s-G-flags | 1,572,864 | 3.43 | 4.2e-7 | 341,190, 3.15 | unchanged |
| s-G-calwt | 1,572,864 | 3.43 | 4.2e-7 | 341,190, 3.15 | 3.1e-7 / 3.6e-7 (73 %) |
| s-BT-calwt | 1,572,864 | 3.30 | 4.0e-7 | – | 3.0e-7 / 3.6e-7 (43 %) |
| s-K-calwt | 1,572,864 | 2.91 | 3.5e-7 | – | not written by either: 0 / 0 |
| s-Gnearest-mix | 1,572,864 | 3.66 | 1.7e-4 | 326,517, 3.34 | 2.2e-7 / 2.8e-7 (61 %) |
| a-pooled | 1,720,320 | 5.85 | 7.0e-7 | 30,720, 4.01 | unchanged |
| a-named | 1,720,320 | 8.64 | 1.3e-6 | 7,680, 6.90 | unchanged |
| a-nearest | 3,194,880 | 8.90 | 1.1e-6 | 88,320, 3.18 | unchanged |
| a-chain-calwt | 2,334,720 | 9.17 | 1.2e-6 | 76,800, 3.83 | 6.9e-7 / 6.9e-7 (46 %) |

In every case: FLAG exact on every cell of the MS; FLAG_ROW equal to CASA's, which **CASA never
changed** (0 rows in every case, including the 5 % set beforehand and rows every cell of which
became flagged); unselected rows' CORRECTED_DATA bit-identical to CASA's (the A cases, where the
column is added); SIGMA and SIGMA_SPECTRUM bit-identical to CASA's; every other column
bit-identical to the input; the flag version equal to the input flags. Chunks of 50 (slice) and
1000 (A) rows and a second run gave the same bytes. The larger relative errors (1.7e-4) are cross
hands under Df that cancel, inside the eps branch, as in C4a.

C4b's verdict: **met on the held-out run**, after a frozen run that failed (section 5) and three
post-hoc ports (section 6). The CASA rules now reproduced by `rang.applycal`, each measured:
values under a one-sided diagonal flag, WEIGHT_SPECTRUM reset from SIGMA_SPECTRUM (or SIGMA) and
scaled by `|g|^2` per side (G, T) or B's mean `|B|^2` over unflagged solution channels, WEIGHT as
the lower middle channel value, no weights written when only K, Df or general terms have
`calwt`, FLAG_ROW never written, the three field maps.

**After -04** (not exercised by any case, so not part of the verdict): a group of rows for which
some table has no solutions is now left as CASA leaves it (`VisEquation::VBOKforCalApply` fails,
so `Calibrater::correct2` neither initialises CORRECTED_DATA nor resets the weights there;
`calflagstrict` flags it). As run in -04, rang applied the covering tables and dropped the others.
A pytest covers the new rule; there is no CASA comparison of it.

## 9. W2b: the commands (sections 3.3 and 3.4)

Run `python examples/check_w2b.py /mnt/d/rang/outputs/c4b-20261106-w2b-03` (90 s; no CASA) on
copies of A1 small, strategy CARACal's `mk_rfi_flagging_calibrator_fields_firstpass.yaml`
(`8f7bb363`), gemclean `~/Github/rang/core/target/release/gemclean` (main's build; this branch
changes no gemclean code), configuration as W2's run with `model: {source: setjy, standard:
Stevens-Reynolds 2016}`, `solint: int`, `freqint: 16`, image of J1939-6342.

| # | Criterion | Measured | Verdict |
| --- | --- | --- | --- |
| 11 | complex apply against the float64 reference | both partitions (scans 1 and 23), 184,320 cells each: 0.0 eps, flags exact; the other fields' CORRECTED_DATA equal to DATA, their FLAG unchanged; with 9.1 % and 10.4 % of the gains made invalid: 0.0 eps, flags exact | pass |
| 12 | MODEL_DATA and gains | MODEL_DATA bit-identical to `calmodels.set_model` on another copy; both partitions' gains and flags bit-identical to `core.solve_complex(model=MODEL_DATA)`, and all 80 files of the store byte-identical to the store `quartical_store` writes from that solve | pass |
| 13 | refusals (pytest) | E2-A and E2-B no longer name C3a; **both still name C4**, through `data.weights: uniform` for imaging, which this task does not make obsolete (section 10); no C7a (neither has a polarised model); `apply` to SIM-TARGET of a term solved on the calibrator refused naming C2a | **fail as frozen** (C4 remains) |
| 14 | end to end | `rang-core run` flag, calibrate, apply, image: exit 0, all four stages done, one receipt, `image.column: auto` resolved to CORRECTED_DATA | pass |

Reported, not gated (14): **the freqint-16 solve did not converge** (50 iterations, converged
fraction 0.0 on both partitions, as W2 found with the unity model), its gains have diagonal
amplitudes of median 0.32 and determinants down to 3e-4, and the image of the corrected
calibrator is nonsense (peak 23,533 Jy against the model's 15.09 Jy at the band centre; the image
of DATA peaks at 0.57 Jy, A1's corrupting gains being uncorrected). Run `-w2b-01`, the same
configuration before the store comparison was added and before the change after -04 of section 8,
gave the same verdicts and the same numbers. A second run with
`freqint: 1` (`c4b-20261106-w2b-02-freqint1`, labelled, 93 s) converged on 83 % and 87 % of
the solutions and its corrected image peaks at **14.71 Jy** (2.6 % below the model), every gate
passing again. A1's delays decorrelate a 16-channel bin; calibration quality is C2's and E1's.

## 10. Refusals after W2b

Removed: the C3a model refusal (`setjy`, `manual`, `lsm` now run) and the C4 refusal of the
`apply` stage. Added: a polarised `manual` model (Q, U or V not 0; `polindex`, `polangle`,
`rotmeas`) names **C7a** (a new key of `core_config.TASKS`); a written model while `secondary`
or `polcal` have terms names C2d; an apply target naming a K, G, B, F, Gpol, KCROSS, Xf or Df
term names that term's task; `interp` on a complex table names C2a; a complex term applied to a
field it was not solved on is refused before anything is written, naming C2a. Kept, because this
task does not make them obsolete: `data.weights: uniform` for imaging (still names C4: nothing
writes CARACal's uniform WEIGHT_SPECTRUM; C4b writes weights only as `calwt` does), `preapply`
on a complex term (names C4a: the solver does not pre-apply), `apply.parang` (C6a). E2-A now
waits for C2a, C2b, C2c, C2d, C4, C5a, G3, G4 and G6; E2-B for C2a, C2b, C2c, C2d, C4, C6a,
C6b, C6c, G3 and G9.

`rang-core calibrate` with a model source writes MODEL_DATA, so it is now a writing stage: it
saves `rang_original` (if absent) and `rang_calibrate_<time>` before the write, as W2's other
writing stages do. W2's frozen harness `tools/oracles/w2/run.sh` still expects `apply` to be
refused (steps `apply` and `run-apply-refused`); it was not changed and now contradicts the code.

## 11. What only the owner can decide

1. **C4a's two decisions stand** (copy CASA's Df substitution; accept the 1-2 ulp residual on
   random-phase per-channel B). C4b's cases have no such B table; on C4a's h-B-gaps exports
   the residual is unchanged (33.1 and 32.3 eps). One more case of the same size: 3 cells under
   input flags in C4a's h-Df-2slot-linear at 14.0 eps (5.9e-5 relative), unflagged cells 6.7.
2. **The complex term's flag rule.** rang follows CASA's general-Jones rule: any flagged
   correlation of a cell, or a bad gain of either antenna, flags all four; a bad side is the
   identity. It was not compared with QuartiCal's own apply.
3. **Transfer of complex gains to a target** (interpolating QuartiCal-style gains onto another
   field) is refused. CARACal's 1GC transfers CASA G tables (C2a). Whether rang should also
   interpolate complex gains is open.
4. **The `data.weights: uniform` refusal** names C4, which this task completes for the apply.
   It needs a step that writes CARACal's `prep.specweights: uniform` into the MS (a W-task, the
   coordinator's call), or the refusal stays as it is.
5. **Which fields get a written model**: the primary section's fields only (CARACal sets the
   model on fcal and bpcal); secondary models from `fluxscale` are C2d.
6. **The end-to-end configuration**: with W2's `freqint: 16` the complex solve does not converge
   on A1 small and the corrected image is nonsense (section 9); `freqint: 1` gives 14.71 Jy
   against 15.09 Jy. Which settings E2's matched arm uses is A0's and the owner's.

## 12. What was not checked

- **CASA tables through `rang-core apply`**: rang solves only the complex term, so the apply
  stage applies only complex terms. `rang.applycal.applycal` (CASA tables) is measured against
  CASA but no command calls it until C2 adds CASA tables.
- **Groups no table covers**: the rule of section 8 (after -04) and `calflagstrict` have no CASA
  comparison; every case had covering tables.
- `calwt=True` on an MS without WEIGHT_SPECTRUM (only a pytest by hand); `calwt` on T alone; B's
  weight scale with several time slots (it time-interpolates through `caltable._interpolate`,
  whose linear formula is the old one, not casacore's); SIGMA of 0; a zero unflagged gain (CASA
  flags it when inverting; the diagonal kernel would divide by it).
- CASA's float32 time reference per table slice against rang's per antenna series: A1's times are
  whole seconds, exact in float32, so a different reference could not show there; the slice's
  are not, but it has one field.
- Several spectral windows, `spwmap`, HISTORY rows (CASA writes one per `applycal`; rang none).
- QuartiCal's own application of a gain store: the complex apply is gated only against a float64
  NumPy reimplementation (0.0 eps there).
- Throughput and memory: no timing work. rang's `applycal` took 1.0-2.2 s per slice case and
  10-20 s per A1 case against CASA's 0.9-3.4 s; most of rang's A1 time is the flag version
  written on `/mnt/d` (W2 measured 9.2 s per version there), not measured further.
- The gain-hash replay (C1 section 4 rule 2) is not in check-all; this branch does not touch
  `solve.rs`, `jones.rs`, `correct.rs` or `core.solve_complex`.

## 13. Files, runs and timings

Code: `python/rang/applycal.py` (new), `python/rang/cal_apply.py` (table fields,
`apply_jones`), `core/src/cal/apply.rs` (one-sided substitution, pairwise tracking, casacore's
linear formula, `apply_jones`), the binding `cal_apply_jones` in `core/py/src/lib.rs`,
`python/rang/core_config.py`, `core_pipeline.py`, `core_cli.py`; tests
`tests/test_c4b_applycal.py`, `tests/test_w2_commands.py`; checkers `examples/check_apply_ms.py`
(host) with `examples/oracle_apply_ms.py` (CASA side), `examples/check_w2b.py`,
`examples/recheck_apply_ms.py`, `examples/recheck_c4a_under_flags.py`. Archive:
[results/c4b-apply-ms.json](results/c4b-apply-ms.json) (numbers only). Runs, ignored, under
`/mnt/d/rang/outputs/`: `c4b-20261106-00-probe` (the J Jones probe and scratch), `-01-dev` (C4a's
exports re-evaluated), `-02` (frozen), `-03` (post hoc), `-04` (held out, the verdict), `-w2b-01`,
`-w2b-02-freqint1`, `-w2b-03`; each CASA run keeps `c4b.json`, `synth/` and `export/` (the
compared columns of every output, about 0.5 GB per run); check-all logs in `c4b/`. Seeds:
20261109 (frozen set, weight edits, seeded gain flags), 20261110 (held out). Inputs read in
place: O-CASA's `c.ms`, E4's `x.{K,G,B,Df}`, A1 small. Image `rang-o-casa:6.7.6.14`. Timings are in
[tool-timings.md](tool-timings.md).

## For the coordinator

Do not apply until merged; all text proposed.

**`research/STATE.md`, new top entry:**

> C4b and W2b, 2026-11-06 (implemented; measured; frozen run failed, held-out run passed).
> [c4b-apply-ms.md](c4b-apply-ms.md): `rang.applycal.applycal` applies CASA tables to a
> Measurement Set as CASA `applycal`: row chunks through W1's write-back, CORRECTED_DATA, FLAG
> OR'd, `calwt` weights, CASA's three field maps. Against `applycal` 6.7.6 on O-CASA's slice
> and A1 small, the frozen run failed (WEIGHT's channel median, 12.7 eps on 86 cells, a
> field-map case that could not tell two maps apart); after three ports from CASA's and
> casacore's sources (the lower middle channel for WEIGHT, phase tracking per interpolated
> pair, casacore's linear formula), a held-out run passed every criterion on ten cases:
> CORRECTED_DATA class C on every cell including flagged ones (largest 9.17 eps), FLAG exact,
> FLAG_ROW untouched as CASA, WEIGHT and WEIGHT_SPECTRUM within 6.9e-7, K's `calwt` writing
> nothing. C4a's "values under solution flags differ" is resolved: CASA still applies the good
> side of a one-sided diagonal flag. W2b: `rang-core calibrate` writes setjy, manual and lsm
> models (bit-identical to `calmodels.set_model`) and solves against them; `rang-core apply`
> applies the complex term on its own bins (0 eps against a float64 reference); `rang-core run`
> flag, calibrate, apply, image runs end to end on A1 small. No novelty claim.

**`research/README.md`, index line (makes `test_every_note_is_in_the_research_index` pass):**

> [C4b, applying calibration to an MS](c4b-apply-ms.md): `rang.applycal` (CASA `applycal` on a
> Measurement Set: CORRECTED_DATA, FLAG, `calwt` weights, field maps) measured against CASA,
> and W2b: models in `rang-core calibrate`, the complex term in `rang-core apply`.

**`research/finish-plan.md`:** C4 row: C4b done (held-out run passed; the frozen run's
failure and the post-hoc ports recorded), C4 done apart from the owner decisions of C4a and
section 11 here. W2 row: W2b (apply and models in the commands) done. Section 7: add decisions 2
to 6 of section 11.

**The kernel changed numerically.** One-sided substitution under diagonal flags, phase tracking
per interpolated pair and casacore's linear formula change `rang.cal_apply`'s output at the ulp
level everywhere and by much more under one-sided flags. C2a pre-applies through this kernel, so
archives or hashes it made with C4a's kernel can shift after this merges. `caltable.correct` is
unchanged and differs further from the kernel (C4a's pytest bound of 32 eps still holds). C1
section 3.1's time-interpolation row ("tracked phase") should read "phase tracked over the two
bracketing slots" if C1 takes errata.

**Refusals:** `data.weights: uniform` for imaging still names C4 (section 10), so E2-A and E2-B
still wait for C4; criterion 13 fails as frozen on that point. Rename the task in that refusal
when it has an owner. `C7a` is new in `core_config.TASKS`. W2's `tools/oracles/w2/run.sh` still
expects `apply` to be refused.

**check-all and the index test.** At the head, `tools/check-all.sh` fails only on
`test_every_note_is_in_the_research_index`; with the index line above applied in the working
tree (not committed) it gave `overall: PASS` (log `/mnt/d/rang/outputs/c4b/check-all-4-index-applied.log`).

**Not removed:** `/mnt/d/rang/outputs/c4b-20261106-0{2,3,4}` (about 2.5 GB each, mostly the
uncompressed exports) and `c4b-20261106-w2b-*` (45 MB); `-02` and `-03` can go after merge,
`-04` once the archive is accepted. C4a's `c4a-20261106-*` exports were used here (section 6)
and can now go. `~/Github/rang/outputs/status/fp-c4b.md` can go after merge.
