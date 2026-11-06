# C4b: applying calibration to a Measurement Set, and W2b: the apply stage

Task C4b of [finish-plan.md](finish-plan.md) (C4), step 7 of
[c1-calibration-chain.md](c1-calibration-chain.md) section 6, together with W2b:
wiring C3a's models and the apply into W2's commands. Branch `fp-c4b-apply-ms`
from main `66c2967`. The kernel underneath is C4a's `rang.cal_apply`
([c4a-apply.md](c4a-apply.md)); the write-back is W1's `rang.core_writeback`
([w1-writeback.md](w1-writeback.md)); the commands are W2's
([w2-commands.md](w2-commands.md)); the models are C3a's `rang.calmodels`
([c3a-models.md](c3a-models.md)).

**Status: implemented; frozen run -02 failed (section 5); post-hoc fixes (6); held-out run -04 pending (7).** Sections 1 to 4 are the design and the criteria, written
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
