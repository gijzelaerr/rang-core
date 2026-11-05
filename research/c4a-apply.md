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

## 4. Results

Not yet measured.
