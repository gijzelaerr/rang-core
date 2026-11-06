# C6: the polarisation terms Gpol, KCROSS, Xf and Df, with the parallactic angle

Task C6 of [finish-plan.md](finish-plan.md), steps 8 to 10 of
[c1-calibration-chain.md](c1-calibration-chain.md) section 6 (C6a, C6b, C6c), in C1's frozen order (CARACal's
strategy 1, `xcal_model_fcal_leak`, C1 section 1.3 steps 12 to 15). Branch `fp-c6-polterms`, from main `5a6bd70`.
**Status: implemented and measured. P, class T and class C met; class B and the chain not met as frozen (a scan
with vanishing polarised cross hands, Df flags on RFI-heavy channels, a CASA Gpol interval missing on noise-free
data), the chain's composite met on CARACal's settings and the held-out set; held-out class T missed only by
KCROSS's estimator bias.** The protocol (sections 1 to 4) was committed (`3f7a917`) before the first comparison;
results are below it, and this status line is the only edit above section 5.

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

## 5. Runs and provenance (measured 2026-11-06)

Archive: [results/c6-polterms.json](results/c6-polterms.json) (every run's JSON: CASA task records, the
comparisons, class T, class C, A1's checks on both truths).

Runs `/mnt/d/rang/outputs/c6-20261106-NN`, each with a `.code/` snapshot (`head.txt`: `0940236`, the protocol
commit `3f7a917` with main `4daf85a` (C7a) merged; `diff.patch`, `untracked.tgz`, SHA-256 list) and a `.log`. The
CASA steps (`-sets`, `-01`, `-07`, `-08`, `-12`) held `~/.rang-heavy.lock`; the rang-only comparisons (`-02` to
`-06`, `-09` to `-11`; 4-390 s, under 0.62 GB each) ran without it after a long queue on the lock. Seeds:
`poldx` 20261146-49, `polholdout` 20261156-59; the KCROSS bias analysis and the unit tests use 20261106.

| Run | What | Wall | Result |
| --- | --- | ---: | --- |
| `-sets` | generate `poldx`, `polholdout` (noisy and twin), `tools/a1_checks.sh` on each | 4.5-5.0 s per MS; checks 56.6 s, 56.0 s | A1's round trip (class C, 12.8 M elements) and noise checks pass on both |
| `-01` | CASA: shared copies; the chains of B-poldx, B-poldx-uv, B-twin; O2; P | 69.0 s (CASA calls 0.2-4.9 s) | every task ran without error |
| `-02` | P against `applycal(parang=True)` | 3.6 s | pass |
| `-03` | class B and the chain, three cases | 388.1 s | not met (6) |
| `-04`, `-05` | class T, twin and noisy | 88.9 s, 79.6 s | pass |
| `-06` | the chain against the truth (reported) | 69.7 s | – |
| `-07` | class C readback | 12.4 s | **script error** after CASA's part (a path mapping in `readback`; fixed; no tolerance or library change) |
| `-08` to `-11` | **held out** on `polholdout`: CASA; class B and chain; class T noisy; class T twin | 52.7 s, 129.5 s, 71.5 s, 79.1 s | 9 |
| `-12` | class C readback, rerun of `-07` | 8 | 8 |

Run `-01`'s `.log` was truncated to zero bytes by a mistaken restart of the stage script (the restart waited on the
lock and was killed before it ran anything; its `.code/` snapshot was rewritten from the same commit and working
tree); its `casa.json` and `casa-tasks.json` hold the results and per-task times.

**A1's check 2 on the new truths (evidence for owner decision 1, not a gate):** with the truth's P in CASA's frame,
CASA's `applycal(parang=True)` reproduces it on the polarised calibrator to a median implied angle of 0.00029°
(p95 0.00048°, `poldx`), against 0.34° on A1 small in rang's frame; the flux calibrator now passes class C (it
failed on A1 small); the target's excess over class C remains (worst 28 times, as A1 found).

**P, run -02 (gate 4.1):** on the twin's polarised calibrator, rang's angle in CASA's frame against CASA's
`applycal(parang=True)`: median 5.0e-6 rad, p95 8.0e-6, max 1.2e-5 (limit 1e-3): **met**. Rang's earlier geodetic
frame (`frame='rang'`, reported): median 0.0060 rad, p95 0.0094.

## 6. Results, class B and the chain against CASA, run -03 (frozen code): not met as frozen

| Case | Gpol products median / p95 (phase median) | KCROSS `|Δτ|` per interval (ns) | Xf `|Δ arg x|` median / p95 | Df gauge-free median / p95; referenced | Flags | Composite median / p95 | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B-poldx | 2.9e-5 / 8.9e-5 (0.0017°) | 0.0006, 0.0019, 0.0005, **0.022** | 0.013° / 0.11° | 1.8e-4 / 5.3e-4; 1.7e-4 / 5.6e-4 | **Df: 658 differ** (rang 8, CASA 666) | – | fail (KCROSS, Df flags) |
| C-poldx | as B | within 1.4e-5 of B | 0.014° / 0.11° | 4.2e-4 / 1.3e-3 | Df: 658 | **8.3e-5 / 2.8e-3**, flags exact | pass (4.2) |
| B-poldx-uv | 5.3e-5 / 1.7e-4 | 6.4e-5 (one interval) | **0.48° / 22.6°** | 1.8e-4 / 5.4e-4 | Df: 658 | – | fail (Xf, Df flags) |
| C-poldx-uv | as B | as B | 0.47° / 22.6° | 1.9e-4 / 5.9e-4 | Df: 658 | 1.0e-4 / **1.4e-2** | fail |
| B-twin | **CASA wrote 3 intervals, rang 4** | 0.0004, 0.0015, 0.0001, 0.015 | 0.0094° / 0.040° | 7.7e-8 / 2.5e-7; 5.2e-8 / 2.0e-7 | equal | – | fail (Gpol intervals) |
| C-twin | as B | 0.0004, 0.0090, 0.0001, 0.015 | 0.45° / 0.65° | 2.4e-4 / 7.3e-4 | equal | 2.7e-4 / **0.37** | fail |

Every table layout equals CASA's (`VisCal`, `ParType`, parameter shapes `(1, 2)`, `(1, 2)`, `(256, 1)`, `(256, 2)`,
the window, `ANTENNA2` 0, −1, −1, 0); CASA writes `INTERVAL` 0 where rang writes the span, and Xf's and Df's `TIME`
differ by up to 13 s (rang's weighted centroid; reported, as C2a-C2c). Df's clip: rang 8 parameters, CASA 736.
KCROSS's second parameter is 0 in CASA's tables, as rang writes it.

**What the failures are (post hoc, probes `probe1.py`, `probe2.py`, `probe3.py` in `~/Build/tmp/20261106-c6`, run
after -03; their numbers are recorded here, they are not gates):**

1. **KCROSS and Xf on scan 4** (`B-poldx` 0.022 ns, `B-poldx-uv` Xf p95 22.6°, the twin's 0.015 ns). On the fourth
   polarised-calibrator scan the model's cross hands almost vanish: median `|M_XY| / I` = 0.00055 (scans 1-3:
   0.114, 0.031, 0.143), because `U'` passes through zero at that parallactic angle. The cross hands there are
   dominated by the 1-3 % leakage, which neither KCROSS nor Xf models, so a solution on that scan alone is
   ill-conditioned and moves with details far below the tolerances elsewhere (a 5e-6 rad difference in P moves
   `M_XY` by about 0.2 % there). On scans 1-3 KCROSS agrees to ≤ 0.0019 ns (noisy) and ≤ 0.0015 ns (twin), and Xf
   per scan to medians 0.16-0.33°, p95 ≤ 1.1°; with `combine='scan'` (CARACal's Xf) the scan carries little weight
   (`w |M|^2`) and Xf passes. The estimator is CASA's; the frozen KCROSS gate is missed on a scan that no setup
   should solve alone, which CARACal's per-scan KCROSS does.
2. **Df flags (658 parameters on `poldx`).** CASA flags, or leaves at `|d|` up to 1.02 (which its own clip then
   flags), the leakages in 23 channels whose leakage-calibrator cells are 68-88 % RFI-flagged (elsewhere 0 %);
   rang's least squares solves them. The values agree wherever both are unflagged. This is CASA's iterative solver
   failing on poorly sampled channels, not a rule rang misses; owner decision 3.
3. **Gpol on the twin.** On noise-free data CASA wrote no solution for the second scan (SNR about 2e7 on the
   others; the cause in CASA was not traced), so the intervals differ and the twin's composite fails through the
   missing scan. The noisy data do not show it.
4. **Composite.** On `poldx` with CARACal's settings the chain's composite passes; the `-uv` and twin composites
   fail through items 1 and 3.

**O2 (C1 section 5, reported):** `flagdata(mode='tfcrop')` on CASA's Xf table flagged nothing (0 added flags); the
corrected polarised calibrator's Q and U changed by a median 0 and p95 6.6e-5 relative (χ p95 0.0007°); the maxima
(0.28 relative, 5.5°) sit where `|Q + iU|` is near zero. Below Xf's tolerance: O2's omission stands on this data
(held out: also 0 added flags, p95 1.4e-4).

## 7. Results, class T, runs -04 (twin) and -05 (noisy): met

| Term | Twin (gate) | Noisy: median z (limit), std(z) |
| --- | --- | --- |
| P | 0 rad (1e-9) | – |
| Gpol | products within 9.7e-9 (1e-5) | Re 0.0008, Im −0.00005 (0.12); std 0.035 |
| KCROSS | 7.3e-5 ns (1e-3) | −1.08 (1.88), four intervals; std 1.24 |
| Xf | 1.6e-7 rad (1e-5) | −0.0048 (0.23); std 2.7 |
| Df | 1.3e-8 (1e-5) | Re 0.0037, Im 0.0125 (0.042); std 2.0, 1.6; reduced χ² 1.17 |

The error scales are not calibrated (reported, not gated): Gpol's CASA-style error is about 30 times too large (the
phase-only fit leaves G's amplitudes in the residual), Xf's and Df's too small by 2-3.

**The chain against the truth, run -06 (reported):** rang's chain on the twin in CARACal's order (crosscal truth
K, B, G; Gpol `60s`, KCROSS `inf` per scan, Xf `combine='scan'`, Df on the leakage calibrator) gives on the
polarised calibrator p = 0.0947 (truth 0.095), χ error median 0.58°, p95 1.11°, `|Δ(Q + iU)| / |Q + iU|` median
2.5 %; on the leakage calibrator residual cross hands of 5.5e-4 of I (p95 1.7e-3). KCROSS is 2.29 ns against the
truth's 2.2: it takes up the linear part of Xf's frequency structure. These are strategy 1's limits on a truth with
`d_x,r` of median 1.75 % (A1 2.5: about `2 d_x,r Q`) and with Xf solved without D, not rang errors: CASA's chain
gives the same composite within 4.2's tolerance (C-poldx).

## 8. Results, class C, run -12 (run -07 stopped on a script error)

`c6-20261106-12` (63.4 s, CASA `applycal` twice on one copy): CASA applies rang's Gpol, KCROSS, Xf and Df tables
of B-poldx (with the crosscal truth tables) and `rang.cal_pol.apply` the same tables. Polarised calibrator: 0 of
1,794,176 unflagged cells fail class C, worst 5.9 float32 epsilons of the cell's largest correlation; leakage
calibrator: 0 of 1,360,416 fail, worst 5.9 epsilons (the largest relative differences, 6.4e-3, are on cross hands
near zero, inside the epsilon clause); flags exact on both: **met**. With 6's layout comparison, CASA reads rang's
four polarisation tables as its own.

## 9. Held-out results, runs -08 to -11 (`polholdout`, run once)

| Case | Result |
| --- | --- |
| H-B | Gpol 2.1e-5 / 6.3e-5 pass; KCROSS `|Δτ|` 0.0034, 0.015, 0.0021, 0.0042 ns pass; Xf 0.014° / 0.094° pass; **Df flags: CASA flags 1,024 parameters in 32 channels with 75-83 % RFI, rang none** (values pass: gauge-free 1.5e-4 / 4.6e-4, referenced 1.3e-4 / 3.8e-4): fail as frozen, the cause of 6 item 2 |
| H-C | composite 5.8e-5 / 1.6e-3, flags exact: **pass** |
| H-T twin | P 0; Gpol 9.7e-9; KCROSS 2.1e-4 ns; Xf 1.4e-7 rad; Df 1.4e-8: **pass** |
| H-T noisy | Gpol, Xf, Df pass; **KCROSS fails: median z 4.8 (limit 1.88)**: the four delays are 0.0002-0.0008 ns short of −3.7 ns with errors of 5e-5 to 1.6e-4 ns, so CASA's FFT estimator's own bias (≤ 2.2e-4 ns on a pure delay; the twin shows 2.1e-4) exceeds the thermal error at this signal-to-noise. Rang reproduces CASA's estimator, and with it this bias |

No code changed between the frozen runs and the held-out runs except the readback's path mapping (`check_pol.py
readback`, not used by -08 to -11). No post-hoc change was made to a library, tolerance or case. After all runs,
for the commit, clippy's `needless_range_loop` rewrote two loops of `parang.rs` (iterators over the same arrays;
the same operations in the same order) and one Rust test, and C4a's test that KCROSS and Xf are refused became a
test that malformed KCROSS and Xf tables are refused.

## 10. What the owner decides

1. **The parallactic-angle frame** (A1 decision 1; provisional: CASA's). With it rang's P agrees with CASA's
   `parang=True` to 5e-6 rad median (run -02), where rang's previous geodetic frame differs by 0.006 rad. CASA's
   frame gives CASA's polarisation angles; rang's is the physical one for an alt-az mount against a J2000 image
   (A1 7.2). Proposed: CASA's by default, `frame='rang'` kept.
2. **A truth with `d_x,r ≠ 0`** (A1 decision 2; provisional: yes, `poldx`, `polholdout`). Measured: strategy 1's
   chain on it misses the polarised calibrator's angle by 0.58° median and `Q + iU` by 2.5 % (run -06), in rang and
   CASA alike, about half of E1's 1° χ budget.
3. **Df on RFI-heavy channels.** CASA flags (or diverges on) channels whose leakage-calibrator data are 68-88 %
   flagged; rang solves them. (a) keep rang's solutions (proposed: least-squares solutions with errors, and
   CARACal's clip removes CASA's diverged ones anyway); (b) add a minimum data fraction per channel to match CASA's
   flags. Either way the exact Df flag gate cannot hold against CASA on such data.
4. **KCROSS per scan on a weakly polarised scan.** CARACal solves KCROSS per scan; a scan where the calibrator's
   cross hands vanish gives an ill-conditioned delay in CASA and rang alike. Proposed for rang's config: KCROSS
   with `combine='scan'` (the sum is weighted by `w |M|^2`), CARACal's per-scan setting available.
5. **KCROSS's estimator bias.** CASA's FFT-and-parabola is biased by up to 2.2e-4 ns, above the thermal error on a
   bright calibrator (held-out H-T). A Gauss-Newton refinement after the FFT (as rang's K) would remove it but
   leave CASA's estimator. Proposed: keep CASA's (2e-4 ns is 0.03° at the band edge).

## 11. What was not checked

- QuartiCal class A (`crosshand_phase`, `leakage`): not in this brief's gates; not run.
- Real data: no LUNO 3C 286 scan (A0's question); the models are A1's, not C7a's `calmodels` (to be substituted).
- `refantmode='strict'`, an alternate refant for Df, `minblperant` eliminations and `minsnr` flags against CASA
  (no case reached them), several windows, `preavg` other than CASA's default, CARACal's `extendflags`, strategies
  2 and 3, and `frame='rang'` beyond run -02.
- Why CASA's noise-free Gpol drops an interval, and what the remaining 5e-6 rad P difference is.
- Timing (not claimed; wall times are in `tool-timings.md`).

## For the coordinator

Do not apply until merged; all text proposed.

**`research/STATE.md`, new top entry:**

> C6, 2026-11-06 (implemented; measured; class T and P met; class B, chain and C as in the note; held-out run done).
> [c6-polterms.md](c6-polterms.md): `rang.cal_pol` adds Gpol, KCROSS, Xf and Df in CARACal's order with the
> parallactic angle (Rust `cal/parang.rs`, `crosshand.rs`, `leakage.rs`; KCROSS and Xf apply in `cal/apply.rs`).
> P in CASA's frame (provisional) matches `applycal(parang=True)` to 5e-6 rad. Against CASA, Gpol, Xf
> (`combine='scan'`) and Df values agree well inside C1's tolerances and the chain's composite passes on the
> CARACal-like case and the held-out set; the frozen gates fail on a scan whose polarised cross hands vanish
> (KCROSS 0.022 ns), on Df flags in 68-88 % RFI channels (CASA flags, rang solves) and on CASA dropping a
> noise-free Gpol interval. Class T passes on a new truth with a leaking refant (`poldx`); the held-out noisy
> KCROSS shows CASA's estimator bias (2e-4 ns) above the thermal error. Strategy 1's chain misses χ by 0.58° on
> that truth, in CASA and rang alike.

**`research/README.md`, index line:**

> [C6, the polarisation terms](c6-polterms.md): Gpol, KCROSS, Xf, Df and the parallactic angle against CASA and a
> truth with a leaking reference antenna (`poldx`, held-out `polholdout`).

**`research/finish-plan.md`:** C6 row: done (this note); section 10's decisions 1-5 added to section 7 (1 and 2
answer A1's open decisions provisionally). C7: substitute C7a's `calmodels` for A1's explicit model; apply with
`rang.cal_pol.apply` (tables, then P). E1: strategy 1 alone uses about half of the 1° χ budget on a leaking refant.

**Proposed wiring for task C2e (not done here):** a `calibrate.polcal` block mirroring CARACal's (`xcal`, `fcal`,
`gain_solint: 60s`, `time_solint: inf`, `uvrange`, `refant`, `frame: casa`) that, after the crosscal steps, runs
`cal_pol.gpol` (xcal, crosscal tables), `cal_pol.kcross` (+ Gpol), `cal_pol.xf` (+ Gpol, KCROSS;
`combine='scan'`), `cal_pol.df` (fcal, crosscal + KCROSS, Xf) and `cal_pol.clip_df`, writes the four tables as CASA
tables, and applies with `cal_pol.apply(..., angles=cal_pol.row_angles(...))` (Gpol on xcal only; Gpol `linear`,
the others `nearest`). The receipt records the frame.

**Merge notes.** Edits `core/src/cal/apply.rs` (KCROSS and Xf apply; the old refusal test replaced),
`core/src/cal/mod.rs`, `core/py/src/lib.rs` (one `mod` line, four registration lines at the end),
`python/rang/formats/caltable.py` (Kcross, Xf types), `python/rang/simtruth.py` and `examples/a1_simtruth.py`
(two versions; the others unchanged), `CHANGELOG.md`, `research/tool-timings.md`. Does not edit `core_config.py`,
`cal_chain.py`, `cal_gain.py`, `solve.rs`, `jones.rs`, `correct.rs`. `test_every_note_is_in_the_research_index`
fails until the README line is applied.

**Left on disk:** `/mnt/d/rang/outputs/c6-20261106-sets` (2.9 GB; keep for C7 and E1: the truths and their CASA
tables), `-01` and `-08` (1.7 GB each: MS copies with the shared model; can go after review), the other runs
(small). `~/Github/rang/outputs/status/fp-c6.md` can go after merge.
