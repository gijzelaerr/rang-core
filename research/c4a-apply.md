# C4a: the Rust apply kernel

Task C4a of [finish-plan.md](finish-plan.md), step 2 of
[c1-calibration-chain.md](c1-calibration-chain.md) section 6. Branch `fp-c4a-apply`, from main `9423f13`.
**Status: implemented and measured; class C not met on every case.** The protocol, tolerance and case list of
sections 1 to 3 were committed (`dc65fb2`) before the first comparison and are unchanged.

Summary. `core/src/cal/apply.rs` corrects and corrupts chunks in memory by K, G, T, B and Df tables, with CASA's
`linear` and `nearest` interpolation in time and frequency and `calflag` flags; it is bound as
`rang._core.cal_apply` and wrapped by `rang.cal_apply.apply`. KCROSS, Xf and P have their slots and refuse with
their C1 step. Against `applycal` in four runs:

- **Frozen run -01: fail** on Df flags (174,435 cells): a lone bad leakage flags one cross hand in CASA, not four.
- Run -02 (post hoc), CASA's source read: `JonesGenLin` flags cross hands from bad leakages *and* from flagged
  parallel hands, and sets both leakages of an antenna to −1 when either is bad.
- **Held-out run -03: fail** on values in 3 of 9 cases (up to 41.9 eps), flags exact on all 9 and equal to the
  predicted counts. Cause: CASA unwraps and tracks phases in float32 steps; ported.
- **Second held-out run -04 (the verdict): flags exact on all 13 cases; class C on 11 of 13.** The two failures
  are stress cases of B with phases uniform on the circle in each of 512 solution channels: 33.1 and 85.6 eps
  (3.98e-6 and 1.02e-5 relative). After a further post-hoc port (unwrap before `nearest`, casacore's linear
  formula) they are 33.1 and 32.3 eps; the residual is a 1-2 ulp difference in about 5-9 % of CASA's unwrapped
  phases, whose mechanism I did not find (section 7).
- Threads 1, 2, 4, 16 bit-identical in every run, and in the Rust and pytest tests. Round trip, corrupt then
  correct, within class C.

## 1. Scope (frozen)

A Rust kernel `core/src/cal/apply.rs`, bound in the extension, that corrects and corrupts one chunk of
visibilities `(row, chan, 4)` in memory, linear correlations `XX, XY, YX, YY`, by a list of terms.

- **Terms implemented:** K (delay, `FPARAM` ns, pivot `CHAN_FREQ[nchan // 2]` of the table's window), G and T
  (diagonal; T one parameter on both receptors), B (diagonal per solution channel), Df (CASA's linear
  approximation, C1 section 3.1).
- **Terms with a slot and a clear error:** KCROSS (C1 step 9, C6b), Xf (C1 step 9, C6b), P (C1 step 8, C6a).
  The order and the interface hold them: the kernel sorts terms by CASA's `VisCal::Type` key
  `B, K (KCROSS), G, J, D, X, C, P, E, T, F`, so T sorts after P, which `caltable.py`'s `TYPES` does not show.
- **Interpolation.** Time `linear` and `nearest` as `caltable.py` (C1 section 3.1): float32 times relative to
  `floor(t0 − 1)`; complex parameters as amplitude and float32-tracked phase; exact slots taken as they are;
  nearest slot outside the range; either bracketing slot's flag flags the result; `nearest` ties go to the earlier
  slot. Frequency `linear` without the `flag` suffix: flagged solution channels are bridged, phase unwrapped,
  nearest beyond the end channels, an all-flagged parameter flagged. Frequency `nearest` is added (CASA's
  `'<time>,nearest'`); it has no Python reference and is measured against `applycal` only.
- **CARACal's per-term defaults** (`crosscal_worker.py` `RULES`, `polcal_worker.py` at `8f7bb363`): K, G, F, B,
  Gpol `linear`; KCROSS, Xf, Df `nearest`. CASA's `nearest` is nearest in time and linear in frequency.
- **Flags** as `applymode='calflag'`: the output flag is the input flag OR the term flags; a diagonal term flags
  only the correlations of a flagged receptor; Df flags all four. A flagged term leaves the cell without that
  term's division, as `caltable.correct`.
- **Corrupt** is the exact inverse of correct, term by term, in reverse order: diagonal terms multiply by
  `g_p,a conj(g_q,b)`; Df adds `d_x,p YY + conj(d_y,q) XX` to XY and `d_y,p XX + conj(d_x,q) YY` to YX, which
  inverts CASA's linear map exactly. This is not the second-order physical forward model `D_p M D_q^H`.
  `caltable.py` has no corrupt path (checked: no `corrupt` in `python/rang`), so corrupt is tested by the round
  trip only.
- **Out of scope:** weights and `calwt` (C4b's gate), writing to an MS (C4b, after W1), the `nearest` field map
  (Python selects the table rows per field and window, as `caltable._series`), throughput (the brief forbids
  timing work on this host now; C1 step 2's "throughput recorded" is left to the coordinator).
- **Unchanged:** `solve.rs`, `jones.rs`, `correct.rs`, `core.solve_complex`, `caltable.correct`.

Arithmetic: Rust ports `caltable.py`'s float32 steps one for one (relative times, the linear formula,
`searchsorted(side='right')`, `argmin` ties, phase tracking in float32, the float64 unwrap then the cast, the
`allclose(atol=1e-10 GHz)` same-grid copy) and applies in float64, writing complex64. Bit identity with
`caltable.correct` is **not** claimed: NumPy's float32 `sin` and `cos` may differ from Rust's by an ulp.

## 2. Tolerance (frozen before the first comparison)

Class C of C1 section 6. For a rang cell `r` and the oracle's cell `c` (correlations `k`):

- **Per-cell pass:** `|r_k − c_k| ≤ 1e-6 |c_k|` **or** `|r_k − c_k| ≤ 11 · eps32 · max_k |c_k|`, with
  `eps32 = 2^-23` and the scale taken from the oracle's own cell. Every correlation of every cell counts that is
  unflagged in both outputs. One failing correlation fails the case. Reported per case: cells compared, the maximum
  relative error, the maximum in float32 epsilons of the cell, and the count above 1e-6 relative.
- **Flags exact, gated:** CASA's FLAG equals the original FLAG OR rang's output flags on every cell of the field
  (not only "solution flags applied", as DF-IO gated).
- **Values under a solution flag:** reported against CASA, not gated (C4b gates them).
- **Rust against `caltable.correct`:** the same class C rule and flags exact, on every case below, with
  `caltable.correct`'s complex128 output rounded to complex64 as the oracle.
- **Round trip on simulated data:** corrupt then correct with K, G (several slots, flagged slots), B (flagged
  channel range) and Df, seeded; the corrected chunk against the original by the class C rule on cells unflagged
  in the output; the flags of corrupt and correct equal each other and equal the input OR the term flags.
- **Thread counts:** the output bytes (data and flags) bit-identical for 1, 2, 4 and 16 threads, in a Rust test
  and through the extension on the chain case.

## 3. Cases (frozen)

All CASA cases run `applycal` in `rang-o-casa:6.7.6.14` on a fresh copy of O-CASA's
`outputs/o-casa-20261030-01/c.ms` (J1939−6342, 4 stations, 192 rows, 32 times, 2048 channels), as DF-IO's
`casa-apply`: `applymode='calflag'`, `calwt=[False]`, `gainfield='nearest'`, `parang=False`,
`flagbackup=False`; container conventions of O-CASA. Run directory `/mnt/d/rang/outputs/c4a-20261106-NN`.

| Case | Tables | `interp` |
| --- | --- | --- |
| casa-K, casa-G, casa-B, casa-Df, casa-T | E4's `x.K`, `x.G`, `x.B`, `x.Df` (`outputs/e4-20261030-01/casa`) and DF-IO's `x.T` (`outputs/dfio-20261030-02/ct/casa`), each alone | `linear` |
| casa-chain | K, G, B, Df | `linear` ×4 |
| casa-caracal-pol | K, G, B, Df | `linear` ×3, Df `nearest` (CARACal's mix) |
| synth-G, synth-B, synth-K, synth-T | DF-IO's seeded tables (seed 20261030, `check_formats.seeded_tables`), written again by `caltable.write` | `linear` |
| synth-chain | G, B, K | `linear` ×3 |
| synth-G-nearest | synth G (4 slots, 2 flagged) | `nearest` |
| synth-Df, synth-Df-nearest | a new seeded Df (seed 20261106): leakages about 0.05, a flagged channel range on one antenna, one antenna's `d_y` flagged in every channel | `linear`; `nearest` |
| synth-B-freqnearest | synth B | `linear,nearest` |

Simulated round trip: seed 20261106, 6 antennas (15 baselines plus autocorrelations off), 20 times, 64 channels,
random model, random input flags; K up to ±5 ns, G at 5 slots with two flagged, B with a flagged range, Df.

## 4. Results of the frozen set

### 4.1 Run -01, the frozen verdict: FAIL on Df flags

`/mnt/d/rang/outputs/c4a-20261106-01`, image `rang-o-casa:6.7.6.14`, `examples/check_apply.py` with the worktree
venv. **The kernel was uncommitted when -01 and -02 ran**; the first commit with code is `95d85e5`, which already
holds the -02 fixes. The -01 kernel differed from `95d85e5` in two ways: Df flagged all four correlations for a bad
leakage (`caltable.correct`'s rule) and phases were tracked in time by float32 whole turns (`caltable.py`'s). The
-02 kernel had the one-cross-hand rule without propagation or substitution. Both runs' exports were re-evaluated
with the head kernel (`recheck-current-kernel.json`, section 6.2). 16 `applycal` calls in one container, 40.5 s;
the whole run 62.9 s.

| Case | Cells | Max relative | Max eps of cell | Flags exact |
| --- | ---: | ---: | ---: | --- |
| casa-K | 470,224 | 3.0e-7 | 2.52 | yes |
| casa-G | 470,224 | 2.7e-7 | 1.67 | yes |
| casa-B | 470,224 | 3.1e-7 | 2.62 | yes |
| casa-Df | 470,224 | 4.0e-5 | 0.22 | yes |
| casa-T | 470,224 | 2.4e-7 | 1.82 | yes |
| casa-chain | 470,224 | 1.6e-4 | 4.38 | yes |
| casa-caracal-pol | 470,224 | 1.6e-4 | 4.38 | yes |
| synth-G | 352,248 | 9.7e-7 | 8.15 | yes |
| synth-B | 470,224 | 3.1e-7 | 2.62 | yes |
| synth-K | 470,224 | 3.2e-7 | 1.96 | yes |
| synth-T | 470,224 | 9.2e-7 | 7.59 | yes |
| synth-chain | 352,248 | 1.1e-6 | 9.48 | yes |
| synth-G-nearest | 409,156 | 7.6e-7 | 6.34 | yes |
| **synth-Df** | 237,644 | 1.7e-3 | 9.54 | **no: 174,435 cells** |
| **synth-Df-nearest** | 237,644 | 1.7e-3 | 9.54 | **no: 174,435 cells** |
| synth-B-freqnearest | 470,224 | 3.1e-7 | 2.62 | yes |

Every case met the class C value rule (the larger relative errors are cross hands that cancel, inside the eps
branch). Rust against `caltable.correct`: class C and flags equal on every case it applies to (max 4.40 eps,
synth-chain). Threads 1, 2, 4 and 16 bit-identical on casa-chain. **Fail:** on synth-Df the kernel, like
`caltable.correct`, flagged all four correlations where antenna 1's `d_y` is bad; CASA flagged only XY on baseline
0-1 and only YX on baselines 1-2 and 1-3. The rule "a flagged Df flags all four" in C1 section 3.1 and in
`caltable.py` had never met a lone flagged leakage: E4's `x.Df` has none, and DF-IO had no synthetic Df.

`synth-B-freqnearest` cannot tell the frequency modes apart: synth B is on the data grid, and the cells of its
flagged range are flagged in `c.ms` anyway, so `linear` passes there too (shown in -02). Frequency `nearest` is
untested by this set.

### 4.2 Run -02, post hoc: the cross-hand flag rule alone is not CASA's

`c4a-20261106-02` (18 `applycal`, 47.6 s; run 73.7 s), with the Df flag rule changed to one cross hand per bad
leakage and two diagnostic cases added after -01 (`posthoc-synth-Df2`: antenna 0's `d_x` bad, both of antenna 2's
bad, antenna 3's `d_y` bad in channels 1000-1099; `posthoc-synth-Df2-chain`: G, B, K with it). Flags now matched on
synth-Df, but the cross hands that became unflagged were far off: max relative 1.40, 9.6e6 eps (synth-Df, Df2), and
the chain case missed 32,362 flags. Fitting the effective leakage on baseline 0-1 gave `d = -1.0000000` (spread 5e-8)
for both of antenna 1's leakages, the unflagged `d_x,1` included.

### 4.3 CASA's rule, read in its source

`casa6-mirror` (2023, C1 section 0), `synthesis/MeasurementComponents/Jones.cc` and `VisCal.cc`:

- `VisJones::syncJones` inverts and then calls `setMatByOk` [M]. `JonesGenLin::invert` negates the leakages;
  `JonesGenLin::setMatByOk` sets **both** elements to 1 if either is not OK [M]. In the formula of section 1 that is
  `d_x = d_y = -1` for that antenna, which is the fitted value. `JonesDiag::setMatByOk` sets only the bad receptor to
  1 (no division), as the kernel already did.
- `JonesGenLin::flagRight` and `flagLeft`, applied per row and channel before the values [M]:
  `XY |= !ok(d_x,p) | flag(YY) | !ok(d_y,q) | flag(XX)` and `YX |= !ok(d_y,p) | flag(XX) | !ok(d_x,q) | flag(YY)`,
  on the visibility flags as they stand, so input flags and earlier terms' flags propagate into the cross hands. Df
  never flags XX or YY.

The kernel now does both (`core/src/cal/apply.rs`). Flags are computed in correct order for both directions, so
corrupt and correct flag the same cells; values are applied in each direction's order. This changes the round-trip
clause of section 2, post hoc after -02: its flags are now the input OR the term flags OR the flags Df propagates
from the parallel hands, and the Rust and pytest round trips check exactly that. Re-evaluated on -02's CASA
exports without a new CASA run, every case of -01 and -02 passes class C with flags exact (largest 9.48 eps,
synth-chain; synth-Df 9.54; Df2-chain 9.41; `recheck-current-kernel.json` in the -02 directory). That is a fit to
the data it explains, so it is not the verdict; section 5 is.

`caltable.correct` is unchanged (C1 section 4 rule 3). It differs from CASA on Df flags in both ways: it flags all
four correlations for a bad leakage and does not propagate parallel-hand flags. From here the checker gates the
kernel against it on values only, where both are unflagged, and reports the flag differences by count.

The substitution means CASA writes unflagged cross hands corrected with `d = -1` on every baseline of an antenna
with one bad leakage. The kernel copies this because the class C gate is against CASA. Whether rang should instead
flag both cross hands there is an owner decision (section 7). It is not hypothetical: C1's chain clips Df to
[−0.6, 0.6] with `flagdata`, which can flag one leakage without the other.

## 5. Held-out confirmation (frozen before run -03)

Cases on the same `c.ms` and settings as section 3, seed 20261107, written by `check_apply.py --heldout`. The
predicted counts are the kernel's own output (`--predict`, `c4a-20261106-03-predict/predict.json`), written here
before CASA runs. "New" counts are flags added over the input FLAG, per correlation XX, XY, YX, YY.

| Case | Tables (`interp`) | What it tests | Predicted new flags |
| --- | --- | --- | --- |
| h-Df-2slot-linear | Df at two slots, 60 s inside the scan ends; slot 0 antenna 3 `d_y` bad, slot 1 antenna 0 `d_x` bad in channels 800-899 (`linear`) | the rule per antenna and time; bracketing | 0, 46,827, 0, 0 |
| h-Df-2slot-nearest | the same (`nearest`) | the same with nearest slots | 0, 31,433, 0, 0 |
| h-Df-dx | Df, antenna 3 `d_x` bad (`linear`) | a lone `d_x` on another antenna | 0, 0, 62,431, 0 |
| h-G-receptor-Df | G (3 slots, antenna 2 X bad at every slot), then an unflagged Df | G's flags propagating into the cross hands at D | 60,135, 60,135, 60,135, 0 |
| h-inputflags-Df | unflagged Df, on a copy whose FLAG has only XX flagged on baseline 0-1, channels 500-599, and only YY on 2-3, channels 700-799 (written with casatools) | input flags propagating | 0, 6,400, 6,400, 0 |
| h-inputflags-G | G, on the same edited copy | no propagation for a diagonal term | 63,335, 25,015, 38,320, 0 |
| h-B-coarse-freqnearest | B on every 8th channel (256 solution channels), antenna 1 bad in solution channels 50-59 (`linear,nearest`) | frequency `nearest` | 0, 0, 0, 0 |
| h-B-coarse-freqlinear | the same (`linear`) | frequency `linear` off the grid | 0, 0, 0, 0 |
| h-chain-caracal | B `linear`, G `linear`, the two-slot Df `nearest` | a chain with CARACal's interp mix; threads 1, 2, 4, 16 | 60,135, 80,566, 60,135, 0 |

Pass: class C against `applycal` and flags exact on every case, threads bit-identical on h-chain-caracal, and
for the two B cases the frequency mode not chosen fails against CASA (so each case can tell the modes apart). The
-03 result is the verdict reported for C4a.

### 5.1 Run -03, the held-out verdict: FAIL on values in three cases; flags exact everywhere

`c4a-20261106-03`, code at `95d85e5`; 9 `applycal`, run 34.5 s. **Flags exact on all nine cases**, every one
equal to the predicted counts above, so CASA's Df flag rule (per antenna and time, a lone `d_x`, propagation from G
and from input flags) holds on cases it was not fitted to. Values:

| Case | Max relative | Max eps | Class C |
| --- | ---: | ---: | --- |
| h-Df-2slot-linear | 8.1e-4 | **41.9** | **fail** |
| h-Df-2slot-nearest | 8.1e-4 | **34.1** | **fail** |
| h-Df-dx | 1.4e-5 | 0.91 | pass |
| h-G-receptor-Df | 4.1e-5 | 6.69 | pass |
| h-inputflags-Df | 5.7e-5 | 0.56 | pass |
| h-inputflags-G | 8.6e-7 | 6.69 | pass |
| h-B-coarse-freqnearest | 3.6e-7 | 2.51 | pass |
| h-B-coarse-freqlinear | 3.6e-7 | 2.90 | pass |
| h-chain-caracal | 3.4e-3 | **34.0** | **fail** |

Threads 1, 2, 4, 16 bit-identical on h-chain-caracal. Each B case failed with the other frequency mode, so both
frequency modes are now tested against CASA and pass.

The failures sat on XY of antenna 0's baselines at the times served by slot 1, whose `d_x,0` has a flagged range
that must be bridged. Bridging unwraps the phase over 2048 random leakage phases, which walks to hundreds of
radians, where float32 resolution is about 1.5e-5 rad. Read in the mirror [M]:

- `CTPatchedInterp::resampleInFreq` unwraps in float: the difference of two floats compared with π, and each 2π
  step rounded back to float (`mtresi(i) -= C::_2pi`). `caltable.py` unwraps in float64 and casts once.
- `RIorAPArray::trackPhase` tracks phases in time the same way, with `while (ph(j) > ph(j-1) + π) ph(j) -= 2π`.
  `caltable._track_phase` subtracts float32 whole turns, which can differ by an ulp.

### 5.2 Post hoc after -03: both float steps ported

The kernel now does both as CASA does (`core/src/cal/apply.rs`, `series` and `resample_freq`). Re-evaluated on the
exports of -02 and -03 without a new CASA run, every case passes class C with flags exact. The largest is 7.00 eps
(h-chain-caracal), and the frozen set's largest went from 9.48 to 5.97 eps (synth-chain); synth-G went from 8.15 to
4.33. These rechecks fit the data that found the problem, so section 6 holds out a further run.

## 6. Second held-out confirmation (frozen before run -04)

`check_apply.py --heldout --seed 20261108`: the cases of section 5 with new values (same flag structure, so the same
predicted counts), and four more that stress the two float steps of 5.1:

| Case | Tables (`interp`) | Predicted new flags (XX, XY, YX, YY) |
| --- | --- | --- |
| h-G-many-linear | G at 9 slots across the scan and 5 s beyond it, phases uniform on the circle, antenna 1 bad at slot 4 (`linear`) | 14,555 each |
| h-G-many-nearest | the same (`nearest`) | 7,315 each |
| h-B-gaps-linear | B on every 4th channel (512 solution channels), phases uniform on the circle, gaps: antenna 0 X channels 40-46, antenna 2 both 200-259, antenna 3 Y 400-402 (`linear`) | 0 |
| h-B-gaps-freqnearest | the same (`linear,nearest`) | 0 |
| the nine cases of section 5 | as there, seed 20261108 | as there |

Predictions from `--predict` (`c4a-20261106-04-predict/predict.json`). Pass as section 5, with the frequency-mode
check also on the two h-B-gaps cases. **The -04 result is the verdict reported for C4a.**

Changed against section 2, before -04: the kernel against `caltable.correct` is **reported, not gated**. After 5.2
the kernel ports two float32 steps that `caltable.py` does not, so the two can differ beyond class C where CASA and
the kernel agree. The pytest comparison with `caltable.correct` now allows 32 eps; it measured 12.4 eps on one
seeded G case.

### 6.1 Run -04, the verdict: flags exact on all 13; class C fails on two stress cases

`c4a-20261106-04`, code at `5406ff4`; 13 `applycal` in 34.7 s, run 48.9 s. Every case's new flags equal the
predictions above. Threads 1, 2, 4, 16 bit-identical on h-chain-caracal.

| Case | Cells | Max relative | Max eps | Class C | Other frequency mode against CASA |
| --- | ---: | ---: | ---: | --- | --- |
| h-G-many-linear | 412,004 | 1.2e-6 | 9.46 | pass | – (one channel) |
| h-G-many-nearest | 440,964 | 1.0e-6 | 7.28 | pass | – |
| **h-B-gaps-linear** | 470,224 | 4.0e-6 | **33.1** | **fail** | fails (modes told apart) |
| **h-B-gaps-freqnearest** | 470,224 | 1.0e-5 | **85.6** | **fail** | fails |
| h-Df-2slot-linear | 423,397 | 4.0e-5 | 6.68 | pass | – |
| h-Df-2slot-nearest | 438,791 | 4.7e-5 | 0.92 | pass | – |
| h-Df-dx | 407,793 | 3.3e-5 | 0.89 | pass | – |
| h-G-receptor-Df | 289,819 | 5.9e-5 | 5.08 | pass | – |
| h-inputflags-Df | 476,624 | 5.3e-5 | 0.48 | pass | – |
| h-inputflags-G | 362,754 | 1.0e-6 | 5.08 | pass | – |
| h-B-coarse-freqnearest | 470,224 | 3.5e-7 | 2.37 | pass | fails |
| h-B-coarse-freqlinear | 470,224 | 3.3e-7 | 2.56 | pass | fails |
| h-chain-caracal | 269,388 | 2.5e-5 | 6.33 | pass | fails |

The verdict for C4a is therefore **not met**: class C holds on 11 of 13 held-out cases and on every case of the
frozen set and of -03 after the fixes, flags are exact on every case of -03 and -04 and of -01 and -02 re-evaluated
with the head kernel, and the two failing
cases are the stress tables built to find float32 unwrap differences. Against `caltable.correct` (reported):
up to 97 eps on h-B-gaps-linear and 42.9 eps on the two-slot Df, where `caltable.py`'s float64 steps differ from
CASA's.

### 6.2 Post hoc after -04

- `nearest` in frequency skipped the unwrap; CASA unwraps first for both modes, and its edge values are the
  unwrapped ones. Ported: h-B-gaps-freqnearest 85.6 → 32.3 eps.
- Linear interpolation now follows casacore 3.7.1's `InterpolateArray1D<Double, Float>` (read in
  `rang-casacore-cpp:3.7.1`, `/usr/include/casacore/scimath/Mathematics/InterpolateArray1D.tcc`):
  `frac = (x − x1)/(x2 − x1)` in double, then `y1 + frac (y2 − y1)` with the difference in float. No measurable
  change on -04.
- Every case of -02, -03 and -04 re-evaluated with the head kernel (`recheck-current-kernel.json` in each run
  directory, and in the archive): all pass with flags exact except h-B-gaps-linear (33.1 eps) and
  h-B-gaps-freqnearest (32.3 eps).

## 7. The residual: 1-2 ulp in CASA's unwrapped phases

A post-hoc probe (`examples/probe_apply_unwrap.py`, `c4a-20261106-05-probe`) applied a B table in which only
antenna 0 has -04's random phases and antennas 1-3 are 1, so CASA's interpolated antenna-0 gain can be read on
baseline 0-1. At on-grid channels my float32 emulation of `resampleInFreq` matches CASA's phase within a quarter
ulp at 123 of 135 channels (X) and 129 of 135 (Y), against 106 and 102 for a float64 unwrap; the rest differ by
1-2 ulp, at unwrapped phases of tens of radians (an ulp is 1.9e-6 rad at 16-32). Not the cause, tested on the
exports: atan2 in float64, a float64 unwrap, a float 2π constant, `trackPhase` along channels before the unwrap.
CASA's `phase(Array<Complex>)` is compiled code that I could not read. With B amplitudes near 1, one ulp of
phase is about 16 float32 epsilons of the cell, which is why these cases exceed 11 eps at 4e-6 relative.

These stress tables are not what a bandpass solve writes: B phases are smooth in frequency, so the unwrap stays
within a few turns, as in every other case here (largest 7.0 eps at the head). Leakage tables do have phases that
are noisy in frequency, but the leakage amplitude (about 0.05) shrinks the effect, as the Df cases show.

## 8. What only the owner can decide

1. **Class C for per-channel tables with large unwrapped phases.** Either accept that the kernel misses class C
   there by 1-2 ulp of phase (measured 33 eps, 4e-6 relative, on random-phase B), or keep the gate and fund more
   work on CASA's compiled phase path. Proposed: accept, stated in the C4 acceptance, with the probe as the record.
2. **Copy CASA's Df substitution or flag both cross hands.** With one bad leakage CASA corrects the antenna's
   other cross hand with `d = −1` and leaves it unflagged. The kernel copies CASA (the gate is against CASA); the
   counts are in the archive (`cross_hands_unflagged_with_substituted_leakage`, for example 46,827 cells in
   h-Df-2slot-linear). Rang could instead flag both cross hands there. C1's Df clip can produce such cases.

## 9. What was not checked

- Weights and `calwt` (C4b), writing CORRECTED_DATA or FLAG to an MS (C4b, W1), FLAG_ROW, `calflagstrict`,
  `gainfield` other than one field per table, several windows, and the `nearest` field map.
- KCROSS, Xf and P (refused); T was checked only alone, against DF-IO's CASA T table.
- Values under solution flags are reported, not gated (C4b gates them): CASA's differ from the kernel's there, for
  example on synth-G 36,976 of 117,976 such cells equal DATA in CASA.
- Corrupt has no external oracle: it is the exact inverse of correct by construction, tested only by the round
  trip (Rust test and pytest, class C, flags equal). It is not CASA's `corrupt` for Df.
- No throughput or timing work (the brief forbids it on this host now); C1 step 2's "throughput recorded" is open.
  Kernel wall times per case (4-17 ms on 192 × 2048 × 4) are in the archive as logged, not measured.
- The gain hashes `4ed2aa89…` and `7b370c13…` were not replayed: no replay runs in `tools/check-all.sh`, and this
  branch changes none of `solve.rs`, `jones.rs`, `correct.rs`, `core.solve_complex` or `caltable.py`
  (`git diff --stat main` on those paths is empty).
- `check-all` passes every step but `test_every_note_is_in_the_research_index`, because this note is not in
  `research/README.md`, which this task may not edit (section 10).

## 10. Files, runs and timings

Code: `core/src/cal/{mod,apply,ffi_apply}.rs`, the binding `cal_apply` in `core/py/src/lib.rs`,
`python/rang/cal_apply.py`, `tests/test_cal_apply.py`, `examples/check_apply.py` (host checker),
`examples/oracle_apply.py` (CASA side, and the FLAG edit with casatools), `examples/probe_apply_unwrap.py`.
Archive: [results/c4a-apply.json](results/c4a-apply.json) (numbers only). Runs, ignored, under
`/mnt/d/rang/outputs/`: `c4a-20261106-01` (frozen), `-02` (post hoc), `-03-predict`, `-03` (held out), `-04-predict`,
`-04` (held out, the verdict), `-05-probe`, each with `c4a.json` (or `predict.json`, `probe.json`), the synthetic
tables, `export/<case>.npz` (CORRECTED_DATA and FLAG of the field) and `casa-apply.json`; check-all logs in
`c4a/`. Seeds: 20261030 (DF-IO's synthetic G, B, K, T), 20261106 (synthetic Df, tests), 20261107 (-03),
20261108 (-04, probe). Inputs read in place: `~/Github/rang/outputs/o-casa-20261030-01/c.ms`,
`e4-20261030-01/casa/x.{K,G,B,Df}`, `dfio-20261030-02/ct/casa/x.T`. Image `rang-o-casa:6.7.6.14`
(`sha256:24822b40…`). Timings are in [tool-timings.md](tool-timings.md).

## For the coordinator

Do not apply until merged; all text proposed.

**`research/STATE.md`, new top entry:**

> C4a, 2026-11-06 (implemented; measured; class C not met on two stress cases). [c4a-apply.md](c4a-apply.md):
> a Rust apply kernel (`core/src/cal/apply.rs`, `rang.cal_apply`) corrects and corrupts chunks by K, G, T, B and Df
> with CASA's interpolation and flags. Against `applycal` on O-CASA's slice, the frozen run failed on Df flags;
> CASA's `JonesGenLin` rules were read in its source and ported (cross hands flagged by bad leakages and by flagged
> parallel hands; both leakages −1 when one is bad), then CASA's float32 phase tracking and unwrap. In the second
> held-out run flags were exact on all 13 cases and class C held on 11; two random-phase B stress tables miss by
> 1-2 ulp of CASA's unwrapped phase (33 eps, 4e-6 relative), mechanism not found. Threads bit-identical. Owner
> decisions: accept that residual or not; copy CASA's Df substitution or flag both cross hands.

**`research/README.md`, index line:**

> [C4a, the apply kernel](c4a-apply.md): the Rust kernel that applies and corrupts K, G, T, B and Df tables as
> CASA `applycal`; CASA's Df flag and substitution rules and float32 phase steps, measured against `applycal`.

**`research/finish-plan.md`:** C4 row: C4a done with the two owner decisions of section 8 open; C4b unchanged
(MS write-back, weights gate, values under flags), after W1. Section 7: add the two owner decisions. Note that C1
step 2's "throughput recorded" was not done (no timing work allowed during C4a).

**`research/c1-calibration-chain.md` (frozen, so as an erratum line if wanted):** section 3.1's Df row, "a flagged
parameter flags all four", is wrong for CASA 6.7.6: see section 4.3 here.

**`caltable.correct`** is unchanged (C1 section 4 rule 3) and now differs from CASA on Df flags (all four instead of
CASA's rule) and on float32 phase steps (up to 97 eps on a stress table). C1 section 4 rule 4 ("the Rust kernel
must agree with `caltable.correct` on F1's CT-synthetic cases before it replaces it") should be restated as
"agree with `applycal`", or `caltable.correct` should get CASA's Df rules in a separate task with its own gate.

**Gain-hash gate (C1 section 4 rule 2):** no replay of `4ed2aa89…` and `7b370c13…` runs in `tools/check-all.sh`;
this branch touches none of the files that produce them. Adding the replay is still open.

**check-all and the index test.** At every commit of this branch `tools/check-all.sh` failed only on
`test_every_note_is_in_the_research_index`, because this note is not in `research/README.md`, which the brief
forbids editing. With the index line above applied in the working tree (not committed) it gave `overall: PASS`
(log `/mnt/d/rang/outputs/c4a/check-all-5-index-applied.log` and `-6-`). Any branch that adds a note has this
conflict, so a brief's "check for overall: PASS" cannot be met on it without the README line.

**Not removed:** `/mnt/d/rang/outputs/c4a-20261106-*` (about 0.64 GB of exports and tables) for C4b; they can go
once C4b has its own oracle run. `~/Github/rang/outputs/status/fp-c4a.md` can go after merge.
