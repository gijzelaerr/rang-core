# Rang: `apply.calwt` on native MeerKAT L0 data (issue #48)

Status at freeze, 2026-11-20: **proposed; nothing run.** Branch `apply-calwt` from origin/main `be20d89c`.
Route: [docs/agents/propose-and-measure.md](../docs/agents/propose-and-measure.md). Host: **nash** for the
E2-N and simulation runs (`nice -n 19 ionice -c3`, main checkout's `tools/heavy_lock.py run`, booked by
measured use, at most two jobs at once). Run root `nash:~/rang-data/outputs/apply-calwt-20261120`; archive
`research/results/apply-calwt/`. Results go under "Measured result"; nothing above it changes except by a
dated, labelled amendment.

## 1. The report and what is not taken from it

Issue #48 (Killick, for Prof. O. Smirnov, rang-core 0.3.0, capture block 1680477139, raw L0 through
`mvftoms.py -f --chanbin 4`, E2-N's recipe with `apply.calwt: false`): katdal's raw `WEIGHT_SPECTRUM`
keeps the uncalibrated bandpass and gain shape; ⟨|V_res|² w⟩ by weight quintile is
[0.73 0.83 0.67 0.81 1.95]; the reporter estimates about 18 % image noise lost against 1/σ² weights; a
Stokes I+V snapshot search found its source at 10.2 σ with the raw weights, 11.4 with unity weights and
11.5 with empirical weights, against 13.0 σ on SDP's L1 product. **These are the reporter's numbers on a
block rang does not have; they are motivation, not data here.** Nothing posted on the issue is run.

## 2. What `calwt: true` does in rang now (code reading, before the freeze)

- `rang.applycal.applycal` (task C4b, [c4b-apply-ms.md](c4b-apply-ms.md)): when any G, T or B table has
  `calwt` true, WEIGHT and WEIGHT_SPECTRUM are **reset from SIGMA (or SIGMA_SPECTRUM)** and scaled as
  CASA's `VisJones::updateWt2`; K, Df, X and general Jones terms do not scale weights, as in CASA.
  `rang-core run` passes one `apply.calwt` for every table (`core_pipeline`, `calwt=[cfg["calwt"]]`);
  default `false`.
- CASA (`Calibrater::correct2`, `calWt()`): the same reset and scale; c4b's cases s-G-calwt, s-BT-calwt,
  s-K-calwt and a-chain-calwt matched CASA's weights (the last without SIGMA_SPECTRUM).
- **What that means on a katdal L0 MS** (E2-N's, read on nash): SIGMA and WEIGHT are per-row
  constants (for example SIGMA 0.0778 and WEIGHT 165.4 = 1/SIGMA²), while WEIGHT_SPECTRUM varies
  across channels (6.2 to 128 on one row). So `calwt: true` discards katdal's channel shape and
  rebuilds it as `1/SIGMA² × |gains|²` per channel. Whether that tracks the noise better than
  katdal's raw shape is the question; the reporter's own variant (raw weights × |B·F|², no reset) is
  not what CASA or rang does.
- The E2 acceptance configurations set `calwt: false` explicitly (CARACal's crosscal choice), so a
  default change does not change any E2 gate.

## 3. Hypothesis

On native L0 data, after rang's 1GC chain, `calwt: true` weights track the visibility noise better than
the raw katdal weights: the natural-weighting image noise implied by them is lower by at least 5 %.

**Not claimed:** anything about the reporter's block, SNR of a transient search, or flagging; no
novelty (this is CASA's own behaviour).

## 4. Data

- **E2-N** (capture block 1735268787, SCI-20241101-KR-02, raw L0 through mvftoms without `--applycal`,
  [e2n-native.md](e2n-native.md)): a fresh copy of `nash:~/rang-data/outputs/e2n-20261116/e2n.ms` (the
  original input, read only) with its flags restored to `rang_calibrate_20261117T022650Z` (the flag
  stage's output, as DL0), then E2-N's frozen configuration, `run.stages: [calibrate, apply]`, once with
  `calwt: false` (arm F) and the WEIGHT_SPECTRUM saved, then `apply` again with `calwt: true` (arm T) on
  the same tables. Scored on the target ASKAPJ1745 (field 3, scans 6, 8, 10) and on the gain calibrator
  J1744-5144.
- **Simulation with a known bandpass**: A1 `small` (16 antennas, 64 channels, 104 integrations; noise
  σ = SEFD/√(2ΔνΔt) per part added after corruption, [a1-simtruth.md](a1-simtruth.md) section 3), its
  default seeds; `rang-core run` calibrate and apply on A1's chain configuration with `calwt` true. The
  true corrected weight of a cell is `|g_p g_q|²/σ²` with the true gains of `truth.npz` (B, G; K and Df
  change no weight).

## 5. Measures

- **N (noise efficiency), E2-N.** For each arm's weights w (F: raw; T: calwt; U: unity) and each
  scored field: Stokes V = (XY − YX)/(2i) of CORRECTED_DATA (V ≈ 0 on these fields); cell noise from
  consecutive-dump differences d = (V_t − V_{t+1})/√2 on the same baseline and channel, both flagged-free;
  σ² estimated per (baseline, 16-channel block, scan) as a robust variance of the **even** pairs; the
  natural-weighting image variance implied on the **odd** pairs, `S(w) = Σ w² σ² / (Σ w)²`, against
  the ideal `S(1/σ²)`. Reported: `e(w) = sqrt(S(w)/S(1/σ²))` (1 is ideal; 1.18 is the reporter's 18 %).
- **Q (quintile flatness)**, as the reporter's test, on the odd pairs: mean of |d|² w per quintile of w,
  normalised by its overall mean; reported, not gating.
- **O (oracle), E2-N.** CASA applycal (`calwt=True`, the same CASA tables rang writes, E2-N's gainfield
  and interp, CASA from the oracle container of `e2n_casa3b.py`) on a second copy of the target rows;
  rang's arm-T WEIGHT_SPECTRUM against CASA's: max relative difference ≤ 1e-5 over unflagged cells
  (float32 weights, the kernel's float64 scale).
- **S (simulation truth).** A1: rang's calwt weights against `|g_p g_q|²/σ²` with true gains; median
  relative error ≤ 2 % and p95 ≤ 5 % over unflagged target cells (the solved gains' own error sets the
  bound; C1's gain tolerances are at the per-cent level).

## 6. Decision rule (frozen)

1. **Failure:** O or S fails. The weight code is fixed first; no default changes.
2. **Switch the default to `true` (all data):** O and S pass; on E2-N `e(T) ≤ 0.95 × e(F)` on the target
   and on J1744-5144, and `e(T) ≤ e(U)` on both. Implementation: `apply.calwt` default `true`; configs
   that set it keep their value; a receipt line records the reset; `docs/limits.md` and the CHANGELOG
   say so.
3. **Opt-in documented, no default change:** O and S pass but the 5 % gain or the `e(T) ≤ e(U)` bar
   fails on either field. Then `docs/limits.md` describes the case and `rang-core config check` warns
   when `calwt` is false and the input has a per-channel WEIGHT_SPECTRUM that differs from its row
   WEIGHT by more than a factor 2 across channels (the L0 signature of section 2).
4. **Null:** `e(T) ≥ e(F)`: calwt does not help on L0 here; reported, nothing changes.

Why "all data" and not L0 only: on data already calibrated by SDP (L1), rang's solved gains are near
one and calwt then mostly rescales to 1/SIGMA² per row; the switch rule does not test L1 (no L1 block on
hand). This is stated as an untested case in the result and in `docs/limits.md`, not a reason to add an
L0 detector before data show it is needed.

## 7. Stages and stop rules

1. This note, committed and pushed. 2. Copies and the A1 simulation (shards with done-markers). 3.
   Calibrate and apply F, save weights; apply T. 4. CASA oracle. 5. The scoring script, committed before it
   is run on the arms. 6. Rule. 7. Code change only under rule 2 or 3, separate commit, with tests.

## Amendments

**Amendment 1, 2026-11-20 13:50 SAST, post hoc for S (after S's first score was read; before any E2-N
score).** Section 2's reading was incomplete, and S's truth formula was wrong for CASA's behaviour:

- Under `calwt`, CASA's B scale is **not per channel**: `BJones::calcWtScale` takes the mean of |B|² over
  the unflagged solution channels, per antenna and receptor ([c4b-apply-ms.md](c4b-apply-ms.md) lines
  40-47, read in CASA's source for C4b; rang follows it). With the reset from a per-row SIGMA, the
  weights after `calwt: true` are **flat across channels within a row** (A1: max/min within a row 1.000000
  on every row). So on katdal L0, `calwt: true` replaces katdal's raw channel shape by a channel-flat
  weight `|G_p G_q|² ⟨|B_p|²⟩ ⟨|B_q|²⟩ / SIGMA²`: per baseline and time it scales, per channel it is
  unity. It does not give per-channel 1/σ² weights.
- A1 adds its noise with a constant σ after corruption ([a1-simtruth.md](a1-simtruth.md), line 66), so
  its ideal corrected weight carries |B|² per channel. Real data do not: raw noise in correlator units
  scales with the gains. A1 therefore cannot say which weights are right for real data; it can only
  check CASA's formula against the true gains.
- **S, as frozen, fails** (median ratio 0.925, |ratio − 1| p95 15.6). S is re-read post hoc against
  CASA's formula with the true G and B: see "Measured result". The code check stays with O (CASA on the
  same tables).
- For the E2-N arms this means T is expected to sit near U (unity) in channel shape, differing by the
  per-row gain-power scale. The frozen rule 2 (`e(T) ≤ 0.95 e(F)` and `e(T) ≤ e(U)`) is unchanged.

## Measured result

### S, A1 small (2026-11-20, nash; rang-core 0.3.0; flags from the truth RFI mask, 12.05 % of cells)

`rang-core run` calibrate (11.1 s) and apply (4.0 s) on E1's configuration with `calwt: true`; target
SIM-TARGET, XX and YY, 378,193 unflagged cross cells each. Archive: `results/apply-calwt/a1/`.

| Truth formula | Hand | ratio rang/truth, median | \|ratio − 1\| median | p95 | max |
| --- | --- | ---: | ---: | ---: | ---: |
| as frozen: \|g_p g_q\|² \|B_p B_q\|²(channel) / SIGMA² | XX | 0.9252 | 0.136 | 15.6 | 187 |
| | YY | 0.9248 | 0.142 | 16.7 | 176 |
| post hoc (CASA's): \|g_p g_q\|² ⟨\|B_p\|²⟩⟨\|B_q\|²⟩ / SIGMA² | XX | 0.9987 | 0.0245 | 0.0637 | 0.118 |
| | YY | 1.0006 | 0.0229 | 0.0592 | 0.089 |

**S as frozen: fail (a design error, amendment 1).** Under CASA's formula the weights follow the true
gains to a median 0.1 %, scatter 2.3-2.5 % (p95 6 %): just outside the frozen 2 % / 5 % bounds, which
were set for the per-channel formula; the scatter is the solved gains' own error (interpolation of G
between the gain calibrator's scans, B over 64 channels). Not a code failure; O decides the code.

### E2-N

_Running._
