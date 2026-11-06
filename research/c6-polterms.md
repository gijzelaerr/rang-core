# C6: the polarisation terms Gpol, KCROSS, Xf and Df, with the parallactic angle

Task C6 of [finish-plan.md](finish-plan.md), steps 8 to 10 of
[c1-calibration-chain.md](c1-calibration-chain.md) section 6 (C6a, C6b, C6c), in C1's frozen order (CARACal's
strategy 1, `xcal_model_fcal_leak`, C1 section 1.3 steps 12 to 15). Branch `fp-c6-polterms`, from main `5a6bd70`.
**Status: protocol (sections 1 to 4), written and committed before the first comparison. Results go below it.**

## 1. Scope

Library functions only. The wiring into `rang-core calibrate` belongs to task C2e (running in parallel): this task
does not edit `python/rang/core_config.py` or `python/rang/cal_chain.py`; section "For the coordinator" proposes the
wiring. Polarised calibrator models are task C7a: here CASA and rang get the **same explicit model** (A1's
calibrator Stokes per channel, written into `MODEL_DATA` of the shared MS copy by one container step), to be
replaced by C7a's `rang.calmodels` later.

**Code (implemented before this protocol; unit tests only, no comparison with an oracle or a truth set):**

- `core/src/cal/parang.rs` (new): P for linear feeds, `P_p = [[cos a, sin a], [-sin a, cos a]]`, `a = q_p +
  RECEPTOR_ANGLE[0]` (A1 section 2.1); `corrupt` `P_p M P_q^T`, `correct` its exact inverse. The angle itself is
  computed in Python with astropy (`rang.cal_pol.parallactic_angles`), not in Rust as C1 proposed ("closed form, no
  IERS"): a departure, stated.
- `core/src/cal/crosshand.rs` (new): KCROSS and Xf from CASA's equations (`KcrossJones::solveOneSDB`,
  `XJones::solveOne`, read in the 2023 mirror for this task). Both terms are normalisable in CASA
  (`SolvableVisJones::normalizable` is `jonesType < GenLinear`; `XJones` says so explicitly), so each cell's cross
  hands are divided by the corrupted model and the weight multiplied by `|M|^2` (`VisEquation::divideCorrByModel`).
  KCROSS: per channel `S = (Σ w V_XY + conj(Σ w V_YX)) / Σ w`, 8x zero-padded FFT, first maximum of `|FFT|`,
  parabolic refinement, `τ = (k − n/2)/n/Δν`; one value for the array, written to X of every antenna, Y 0,
  `ANTENNA2 = −1`. Xf: per channel `wt = (w_XY + w_YX)/2`, `x = (Σ wt V_XY + conj(Σ wt V_YX)) / |·|` over cells
  with both cross hands unflagged; `ANTENNA2 = −1` (CASA forces refant to none for X).
- `core/src/cal/leakage.rs` (new): Df. CASA solves the linearised D on the cross hands only (`DJones::guessPar`
  zeroes the parallel-hand weights) with `VisCalSolver2`; the model is linear in the leakages, so rang solves the
  weighted least-squares problem directly per interval and channel (real normal equations, Cholesky). With an
  unpolarised calibrator the leakages have one free complex number (`d_x + z`, `d_y − conj z`); CASA removes it by
  its subtractive reference (`applyRefAnt` case D: `d_x,p −= d_x,r`, `d_y,p += conj(d_x,r)`), and rang fixes
  `d_x,r = 0` in the solve, which gives the same referenced values. `minblperant` by recursive elimination per
  channel; `SNR = 1/err` (`DJones::formSolveSNR`), `minsnr` on it.
- `core/src/cal/apply.rs`: KCROSS (K's form with the table's pivot; Y's parameter 0) and Xf (`diag(x, 1)`, one
  parameter per channel, its flag flagging both receptors as `XJones::calcAllJones`) are applied; P stays refused as
  a table and is applied by `parang.rs`. `formats/caltable.py` (the Python reference) gains the same two types.
- `core/py/src/cal_pol.rs`: bindings `cal_parang_rotate`, `cal_kcross_solve`, `cal_xf_solve`, `cal_df_solve`.
- `python/rang/cal_pol.py` (new): `gpol` (`rang.cal_gain.gaincal(calmode='p')` with the P-rotated model),
  `kcross`, `xf`, `df`, `clip_df` (CARACal's clip of the Df table at 0.6), `apply` (tables, then P), `load` (one
  field; P on the model first, then the earlier tables by `cal_gain._pre_apply`: lower VisCal types correct the
  data, the others corrupt the model; weights `1/SIGMA^2` when tables are pre-applied, as C2a measured for
  `gaincal`).
- `rang.simtruth`: two new versions, `poldx` and `polholdout` (section 3); the other versions are unchanged.

**Estimator differences stated before measuring.** (1) `polcal` pre-averages 300 s (`preavg`); rang solves the
cells. For KCROSS and Xf the sums are linear, so this changes nothing but rounding and the weighting when weights
differ between hands; for Df the least-squares answer is the same when the model is constant over the interval
(true for the point calibrators here). (2) CASA's Df is iterative (`VisCalSolver2` stops on its own criterion);
rang's is the exact least-squares solution. (3) CASA accumulates in float32 where rang uses float64.

**Not in scope:** CARACal's `extendflags` step and the `tfcrop` of the Xf table (C1 O2 is measured on CASA's side
only, section 4); strategies 2 and 3 (`Dflls`, `Xfparang+QU`, C1 O3); several windows; `preavg` as an option; the
wiring; QuartiCal class A (`crosshand_phase`, `leakage`; not part of this brief's gates).

## 2. Owner decisions taken provisionally (A1's two open decisions)

1. **The parallactic-angle convention: CASA's**, provisionally (`cal_pol` `frame='casa'`, the default): the
   hour-angle formula on astropy's apparent (TETE) place, apparent sidereal time, each antenna's geocentric
   latitude, from apparent north, which A1 measured to reproduce CASA 6.7.6.14's `parang=True` to a few 1e-4
   degrees. `frame='rang'` keeps rang's earlier frame (geodetic, ICRS north). The new truths use CASA's frame.
2. **A second simulated truth with `d_x ≠ 0` on the reference antenna: yes**, provisionally: `poldx` (class T and
   class B) and `polholdout` (held out) have nonzero leakages on both hands of every antenna, the refant included.
   With an unpolarised leakage calibrator (strategy 1) `d_x,r` is not observable: Df is compared in CASA's
   referenced gauge, and the chain's residual on the polarised calibrator (about `2 d_x,r Q`, A1 section 2.5) is
   reported.

## 3. Data and settings

- **`poldx`** (`rang.simtruth.design("poldx")`): A1 small's 16 antennas and schedule (23 scans; the polarised
  calibrator `3C286-SIM`, field 1, four scans of four integrations spanning about 115 degrees of parallactic angle),
  256 channels 856-1712 MHz, `τ_c = 2.2 ns`, `|τ|` 1-10 ns, P in CASA's frame, refant m000 (index 0) leaking on
  both hands. Seeds jones 20261146, sky 20261147, rfi 20261148, noise 20261149 (none used before). Generated with
  `examples/a1_simtruth.py generate poldx` with and without `--noiseless`, then `tools/a1_checks.sh` for its CASA
  truth tables `truth.{K,B,G,Kcross,Xf,Df}` (raw truth) and A1's checks; its check 2 (CASA's `parang=True` against
  a truth made in CASA's frame) is reported as evidence for decision 1, not gated.
- **`polholdout`**: the same with seeds 20261156-20261159 and `τ_c = −3.7 ns`. **Frozen here as the held-out set:
  generated with `poldx`, but no comparison on it runs until every other case of this protocol has been evaluated.**
- Directory `/mnt/d/rang/outputs/c6-20261106-sets/` (both versions, twins, truth, CASA truth tables); runs
  `/mnt/d/rang/outputs/c6-20261106-NN`, each with a `.code/` snapshot and a `.log`, heavy steps under
  `flock ~/.rang-heavy.lock`.
- **Shared inputs for CASA and rang:** a copy of the MS per case in the run directory on which one container step
  (`examples/oracle_pol.py edit`) writes `MODEL_DATA` = A1's sky-frame calibrator coherency (`XX = I+Q`,
  `XY = U+iV`, ...) on fields 0 (J1939−6342, unpolarised) and 1 (3C286-SIM, p 9.5 %, χ 33°, RM 0), and ORs the RFI
  mask (`any`) into FLAG on the noisy set. Both sides read DATA, FLAG, MODEL_DATA, SIGMA, WEIGHT_SPECTRUM from that
  copy. The C7a model is to be substituted later.
- **Crosscal pre-applied (not solved here):** the truth tables. On the polarised calibrator `[truth.K, truth.B]`
  (no G, so Gpol has the G phases to find); on the leakage calibrator `[truth.K, truth.B, truth.G]`. All `linear`.
- **CASA** (`rang-o-casa:6.7.6.14`, O-CASA's container conventions), CARACal's calls (C1 section 2.2), refant
  `m000`, `minsnr=3`, `minblperant=4`, `refantmode` flex:
  - Gpol: `gaincal(field='1', gaintype='G', calmode='p', solint, combine='', parang=True, uvrange,
    gaintable=CC)`;
  - KCROSS: `gaincal(field='1', gaintype='KCROSS', solint, combine, parang=True, uvrange, gaintable=CC + [Gpol],
    interp=... + ['linear'])`;
  - Xf: `polcal(field='1', poltype='Xf', solint, combine, uvrange, gaintable=CC + [Gpol, Kc],
    interp=... + ['linear', 'nearest'])`;
  - Df: `polcal(field='0', poltype='Df', solint='inf', combine='scan', uvrange, gaintable=CCL + [Kc, Xf],
    interp=... + ['nearest', 'nearest'])`; then rang's `clip_df` and CASA's `flagdata(mode='clip')` are both
    applied and their flags compared.
- **rang:** `rang.cal_pol` with the same settings, `frame='casa'`. Term by term (C2c's rule, finish plan item 13):
  each rang term is solved with **CASA's own earlier tables** pre-applied (B-cases); separately, rang's own chain
  (each term with rang's earlier tables) is compared with CASA's chain on the composite (C-cases).

## 4. Gates (frozen)

Notation: products and cells "both leave unflagged"; flags differing near `minsnr` (either side's SNR within a factor
2 of it) or at exactly `minblperant` baselines are reported, not gated (C1 section 2.1).

### 4.1 Class B against CASA 6.7.6.14 (term by term, CASA's earlier tables pre-applied)

| Term | Quantity | Gate |
| --- | --- | --- |
| P | the angle rang applies against `applycal(parang=True)` with no tables, on the polarised calibrator of the noiseless twin: per cell `δ = |arg((Q + iU)_rang / (Q + iU)_casa)| / 2` from the corrected correlations | median and p95 `≤ 1e-3` rad (C1 step 8) |
| Gpol | parallel-hand products `g_p conj(g_q)` (C2a's class B) | median `≤ 7e-4`, p95 `≤ 3e-3` relative; flags exact; intervals and `ANTENNA2` equal |
| KCROSS | `τ_c` per interval | `|Δτ| ≤ 0.02` ns (C1 step 9); intervals and flags equal |
| Xf | per channel `|Δ arg x|` | median `≤ 0.5°`, p95 `≤ 2°` (C1 step 9); flags exact |
| Df | the gauge-free `d_x,p + conj(d_y,q)` and `d_y,p + conj(d_x,q)` over antenna pairs and channels, and the referenced table values | median `|Δ| ≤ 1e-3`, p95 `≤ 5e-3` (C1 step 10), both; flags exact; clip flags equal |

Maxima are reported, not gated.

### 4.2 The chain against CASA's chain (C-cases, composite)

rang's chain Gpol → KCROSS → Xf → Df (each with rang's earlier tables) and CASA's chain, each side's four tables
evaluated by `rang.cal_pol.apply` in the corrupt direction (Gpol `linear`, the others `nearest`, as CARACal) on two
probe models per row of fields 0 and 1, `I = 1` and `(I, Q, U, V) = (1, 0.06, 0.08, 0)`; Gpol on field 1 only:
per cell and correlation `|V_rang − V_casa| / max_k |V_casa,k|`, **median `≤ 7e-4`, p95 `≤ 3e-3`**, flags exact.
KCROSS of the chain by 4.1's KCROSS gate. Per-term values of the chain are reported, not gated (C2c section 8.2).

### 4.3 Class T against the truth (term by term, the truth's other terms pre-applied)

Each term is solved with the raw truth tables of every other term pre-applied in CASA's way (lower types correct
the data, higher types and P corrupt the model), so that it alone carries the difference:

| Term | Truth | Pre-applied | Noise-free twin | Noisy: unbiased with an error scale |
| --- | --- | --- | --- | --- |
| P | `truth.npz` `parallactic_angle` + receptor angle (CASA frame) | – | rang's angles within `1e-9` rad of the truth's | – |
| Gpol | G phases in CASA's gauge (`gauge0_gain` / its amplitude) | K, B, KCROSS (data); Df, Xf, P (model) | products within `1e-5` | C2a's product test: `z = (P_rang − P_truth)/s`, `|median Re z|`, `|median Im z| ≤ 3 x 1.2533/√N` |
| KCROSS | `τ_c` raw | K, B, G (data); Df, Xf, P (model) | `|Δτ| ≤ 1e-3` ns (the estimator's own bias on a pure delay was computed at `≤ 2.2e-4` ns for 64 and 256 channels over ±12 ns, before any comparison) | `z = Δτ / err` (rang's error, `crosshand.rs`), `|median z| ≤ 3 x 1.2533/√N` |
| Xf | `x(ν)` raw | K, B, G, KCROSS, Df (data); P (model) | `|Δ arg x| ≤ 1e-5` rad every channel | `z = Δφ / err` per channel, as KCROSS |
| Df | leakages in CASA's referenced gauge (`gauge0_leakage`) | K, B, G, KCROSS (data); Xf, P (model) | every `|Δd| ≤ 1e-5` | `z` of the real and imaginary parts with `sqrt(var)` (unscaled, weights `1/σ²`), over every parameter but the refant's fixed `d_x`; both medians `≤ 3 x 1.2533/√N` |

`std(z)` is reported, not gated. "Noisy" cases flag the RFI mask (`any`).

**The chain against the truth (reported, not gated):** rang's chain in CARACal's order on the twin, its corrected
polarised calibrator against the truth sky model (P inverted): the error in `Q + iU` relative to `|P|`, and on the
leakage calibrator the residual cross-hand power, which show strategy 1's known limits (Xf solved without D; the
unobservable `d_x,r`).

### 4.4 Class C: CASA reads rang's polarisation tables

`applycal(parang=False, calwt=False, applymode='calflag')` with rang's Gpol, KCROSS, Xf and Df tables of case
B-poldx (with the crosscal truth tables), interps as CARACal, on fields 0 and 1, against `rang.cal_pol.apply` with
the same tables: per cell `≤ 1e-6` relative or `≤ 11` float32 epsilons of the cell's largest correlation, flags
exact. The table layouts (`VisCal`, `ParType`, parameter shapes, the window, `ANTENNA2`) equal CASA's own tables'
of the same case; `TIME` and `INTERVAL` reported.

### 4.5 Cases

| Case | Data | Settings | Gates |
| --- | --- | --- | --- |
| P-twin | poldx twin, field 1 | `applycal(parang=True)`, no tables | 4.1 P |
| B-poldx | poldx noisy, RFI flagged | Gpol `60s`; KCROSS `inf`, `combine=''`; Xf `inf`, `combine='scan'`; Df `inf`, `combine='scan'`; `uvrange=''` | 4.1 all terms |
| B-poldx-uv | as B-poldx | Gpol `int`; KCROSS `inf`, `combine='scan'`; Xf `inf`, `combine=''`; `uvrange='>150'` everywhere | 4.1 all terms |
| B-twin | poldx twin | as B-poldx | 4.1 all terms |
| C-poldx, C-poldx-uv, C-twin | as the B-cases | rang's own chain | 4.2 |
| T-twin, T-poldx | twin, noisy | as B-poldx | 4.3 |
| T-chain-twin | twin | as B-poldx | 4.3 chain (reported) |
| R-poldx | B-poldx's rang tables | – | 4.4 |
| O2 | B-poldx's CASA chain | with and without `flagdata(mode='tfcrop')` on the Xf table (C1 O2's call) | reported: the change of corrected Q and U on field 1 against 4.1's Xf tolerance |
| **H-B, H-C, H-T** | **polholdout** noisy (H-T also twin) | as B-poldx, C-poldx, T-poldx | 4.1, 4.2, 4.3, **held out** |

The held-out cases (prefix H) run once, after every other case has been evaluated; any change after that is
labelled post hoc and needs a further held-out case. Results are added below; this protocol is not edited except
for its status line.
