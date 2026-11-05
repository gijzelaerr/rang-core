# C4a: the Rust apply kernel

Task C4a of [finish-plan.md](finish-plan.md), step 2 of
[c1-calibration-chain.md](c1-calibration-chain.md) section 6. Branch `fp-c4a-apply`, from main `9423f13`.
**Status: protocol frozen (this section), nothing compared yet.** The protocol, tolerance and case list below are
committed before the first comparison against any oracle.

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

`/mnt/d/rang/outputs/c4a-20261106-01`, kernel as committed for the run (not yet in git; its Df flag rule was
`caltable.correct`'s, all four correlations), `examples/check_apply.py` run with the worktree venv, image
`rang-o-casa:6.7.6.14`. 16 `applycal` calls in one container, 40.5 s; the whole run 62.9 s.

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
corrupt and correct flag the same cells; values are applied in each direction's order. Re-evaluated on -02's CASA
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
