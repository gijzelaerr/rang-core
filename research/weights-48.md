# Weights that track the noise: a robust, efficient estimator for `apply.reweight` (issue #48)

Status at freeze, 2026-11-25: **proposed; nothing in this note is built or measured.** Branch `weights-k`
from origin/main `de22d05e`, committed before any code that tests it. Later changes are dated amendments
in section 9, labelled post hoc when they could have seen a result. Procedure:
`docs/agents/propose-and-measure.md`. The K item of the same branch (#60) has its own note,
[k-fallback-60.md](k-fallback-60.md), and its own gate.

## 0. Starting point (read, not measured here)

- **#48** (Killick for O. Smirnov, block 1680477139, raw L0 through `mvftoms.py -f --chanbin 4`):
  the raw `WEIGHT_SPECTRUM` does not track the noise after calibration (top weight quintile at 1.95);
  a Stokes I+V snapshot search found its source at 10.2 σ (raw), 11.4 σ (unity), 11.5 σ (empirical
  1/σ² from the Stokes V residual), 13.0 σ (SDP L1 reference). These are the reporter's numbers on a
  block that neither glacier nor nash holds; motivation, not data here.
- **calwt** ([apply-calwt.md](https://github.com/gijzelaerr/rang-core/blob/apply-calwt/research/apply-calwt.md),
  branch `apply-calwt`): rang equals CASA applycal calwt to 1.0e-6. CASA's rule takes ⟨|B|²⟩ over the
  band, so calwt weights are flat across channels; on E2-N they were worse than the raw weights (implied
  natural-weighting noise e: target raw 1.039, unity 1.078, calwt 1.083). Null.
- **#55** ([apply-reweight.md](apply-reweight.md)): `apply.reweight` is on main, off by default
  (`mode: off | residual | stokes_v`, per baseline × `chanbin` channels × scan or `timebin`, statistic
  `mad` or `classic`). G1, CASA statwt: **exact** (0.0) for `classic`. G2, known noise: **failed** as
  frozen and after its revision: `mad`, the default, misses e ≤ 1.01 on clean data (1.0116 against a
  block-ideal floor of 1.0071) because a MAD variance is inefficient, and its RFI bias is (a_ε/0.6745)²
  by construction; `classic` passes clean (1.0087) but collapses with 1 % RFI (median ratio 0.011).
  G3, E2-N held out: `stokes_v`/`mad` R beats raw by 3.2 % on the target (e 1.0060 against 1.0395),
  and gives **every** J1744−5144 cell weight 0 (14-15 dump scans: about 120 V samples per block on the
  fit dumps, below `minsamp` 200, nothing to fill from).
- **This E2-N target reading is seen.** The E2-N target (ASKAPJ1745, 1,024 channels) is development
  data in this note; it does not decide anything (section 6).

## 1. What the estimators in the field do (read 2026-11-25), and the choice

| Tool | Noise model | Statistic | Short blocks | What it cannot do here |
| --- | --- | --- | --- | --- |
| CASA `statwt` | per baseline × `chanbin` × `timebin` (or `combine='scan'`) | classic variance (divisor N); no robust option | weight 0 and flagged below `minsamp` | RFI residue biases it without bound (#55 G2: 0.011) |
| QuartiCal 0.2.7 `solver.robust` (`quartical/weights/robust.py`) | one inverse covariance per correlation per solver chunk, times a per-visibility Student-t factor η = (ν + n_corr)/(ν + rᴴΣ⁻¹r), ν fitted per chunk (start 5) | weighted mean of η·|r|² over the chunk | none (chunk-level) | follow a per-baseline or per-channel noise shape inside a chunk; its per-visibility η is itself noisy |
| CubiCal `robust-2x2` | as QuartiCal's (its origin) | as QuartiCal's | – | as QuartiCal's |
| WSClean 3.7 | none: it reads WEIGHT_SPECTRUM; `-weighting-rank-filter` acts on gridded weights | – | – | estimate the noise |
| Killick's `rederive_weights.py` (#48) | per baseline × 16 channels over time, Stokes V | MAD of re and im | dropped below 200; 5-block running median, then the baseline median | – (this is #55's `stokes_v`/`mad`) |

**Choice: keep statwt's structure (per baseline × channel block × time block, the structure the radiometer
equation and MeerKAT's per-antenna bandpasses give), on #55's Stokes V or residual samples, with a new
statistic `clipped`, and a fixed order of fills so no unflagged cell gets weight 0 while any baseline in
its scan has data in its channel block.**

- **Why not QuartiCal's model.** A covariance per chunk is constant across baselines and channels in the
  chunk; #48's mismatch is a per-baseline, per-channel shape (the raw weights' log-scatter 0.56 across
  channels within a baseline). QuartiCal's robust weights are a solver device against outliers, not a
  noise map. They are run as a comparison arm (section 4, Q), not a parity bar.
- **Why not a per-antenna factorised model** (σ²_pq = f_p f_q per block): it pools many more samples per
  parameter, but it forces every baseline onto the radiometer form and would hide baseline-dependent
  excess (short-spacing crosstalk, residual RFI on a few baselines), which a per-baseline estimate keeps.
  Not pursued; named so a follow-up can test it.
- **The statistic `clipped`.** For a circular complex Gaussian with per-part variance v, u = |z − m|²/(2v)
  is Exp(1). Per block, starting from the MAD variance and the per-part medians as centre m:
  1. keep the samples with u ≤ c, c = 9 (3 σ in amplitude of the complex noise);
  2. m = mean of the kept samples; v = (Σ_kept |z − m|² / (2 n_kept)) / k(c), with
     k(c) = 1 − c e^(−c) / (1 − e^(−c)) = 0.998890 the exact truncation factor of Exp(1) at c;
  3. repeat until the kept set does not change (at most 20 passes).
  For clean Gaussian data it drops 1.2e-4 of the samples, so its efficiency is close to the classic
  variance's (which passed #55 G2 on clean data); outliers above 3 σ amplitude, such as #55's 100×
  RFI, are removed whole, so the RFI bias is that of the residue below the threshold only. Divisor
  n_kept as statwt's divisor N. Rust kernel, beside `classic` and `mad` in `core/src/reweight.rs`.
- **Fills, in order** (`smooth` and `minsamp` keep their meaning; the kernel is called with `minsamp` 1
  and the counts decide):
  1. a block with at least `minsamp` valid samples keeps its own estimate;
  2. (existing) when `smooth > 0`, a running median of width `smooth` over the group's accepted blocks,
     then the group's median of accepted blocks;
  3. **new:** the same baseline and channel block pooled over the scans of the same field among the
     stage's rows: the count-weighted mean of the per-scan estimates of every scan in which the block has
     samples, accepted when the pooled count reaches `minsamp`;
  4. **new:** the median over the scan's baselines of the accepted estimates of that channel block;
  5. otherwise weight 0. The summary records the number of unflagged cells left at weight 0 and the
     cells filled at steps 2, 3 and 4.
  Step 3 is statwt's `combine='scan'` restricted to blocks that need it; step 4 is crude and is reported.
  For `timebin` in seconds, step 3 pools over the time blocks of the field's scans the same way.

Defaults after this change, if the rule (section 6) ships it: `statistic: clipped`; `mode` stays `off`.
`classic` and `mad` stay, unchanged; `classic` stays statwt's estimator for G1.

## 2. Hypotheses

- **H1 (truth).** On simulations with known per-channel, per-antenna noise, `clipped` weights follow 1/σ²
  within the bounds of section 5 T, clean and with RFI, and the fills leave no unflagged cell at weight 0
  on scans of 14 dumps.
- **H2 (real data).** On native MeerKAT L0 data after rang's 1GC chain, `stokes_v`/`clipped` weights
  give a lower Stokes V image noise than raw, unity and calwt weights, held out.

**Not claimed:** anything about 1680477139 (not on hand); novelty (statwt with a known robust estimator
is not new); any change in flagging or calibration.

## 3. Data

- **Simulations** ([rw_g12.py](results/rw-scripts/rw_g12.py) of #55, extended in a new script
  `results/w48-scripts/w48_sim.py`): 16 antennas, 3 scans, 256 channels over 856-1712 MHz,
  σ(p, q, ν) = σ0 s(ν) √(f_p f_q), #55's s(ν) and f_p (seed 55), 10 Jy on XX and YY, V of the sky 0.
  Cases: **clean** (20 integrations per scan); **rfi** (100× outliers in 1 % of cells, #55's);
  **rfi-low** (new: 3× to 5× the local σ, uniform, in 2 % of cells, a residue the clip partly misses);
  **short** (new: 14 integrations per scan, and on scan 2 only 8, so per-scan blocks fall below
  `minsamp` 200 for both `stokes_v` and `residual`); **baseline-excess** (new: the 10 shortest baselines
  at 1.5× σ, a per-baseline shape the per-antenna model would miss). Seeds `w48-<case>`.
- **E2-N, as converted** (capture block 1735268787, 1,024 channels, [e2n-native.md](e2n-native.md)):
  a fresh copy of `nash:~/rang-data/outputs/e2n-20261116/e2n.ms` into this task's run root, flags
  restored to E2-N's flag-stage version (`rang_calibrate_20261117T022650Z`, as apply-calwt and DL0 did),
  then `rang-core run` calibrate and apply with E2-N's frozen configuration (`calwt: false`). Fields:
  the target ASKAPJ1745 (**development**, seen in #55 G3), and **held out** J1744−5144 and J0408−6545
  (never scored with a re-weighted arm; J0408−6545 never scored for weights at all). This run is also
  arm A of #60 ([k-fallback-60.md](k-fallback-60.md)).
- **E2-N-c4, a second conversion** of the same block from the MVF already on nash
  (`e2n-20261116/mvf`), with `mvftoms.py -f --chanbin 4` (256 channels), as #48's reporter converted.
  #48's standing question is whether `--chanbin` leaves the raw weights mis-scaled (E2-N's own raw
  weights track the noise: top quintile 0.88). Flag stage, calibrate and apply with E2-N's configuration
  (`flag` included, since no flag version maps across conversions); `chanbin` 4 here (4 × 3.34 MHz =
  13.4 MHz, the reporter's 16 × 0.84 MHz). **Every field held out**; the target is the same sky as the
  development field, averaged, so its H2 reading is reported apart from the calibrators'.
  **Precondition, checked before any arm is scored:** the raw weights' quintile profile (measure Q below)
  on the c4 target. If its top quintile lies within [0.8, 1.25], c4 does not reproduce #48's symptom; it
  is then still scored, and the result says so.

## 4. Measures

All real-data measures are **held out**: R's weights are estimated from the dumps of even dump pairs only
(the `fit` argument of `rang.reweight.estimate`, as #55 G3), and only the dumps of odd pairs are scored.

- **N (implied noise), apply-calwt's measure** ([rw_g3.py](results/rw-scripts/rw_g3.py)): Stokes V of
  CORRECTED_DATA, consecutive-dump differences, e(w) = sqrt(S(w)/S(1/σ̂²)). It shares its noise source
  with the estimator, so it is reported and decides nothing (section 6). Quintile profile Q reported.
- **I (image noise), the gate on real data.** GeMClean dirty images (`-niter 0`) of Stokes V of the
  scored field's CORRECTED_DATA, 2048 × 2048 at 3″, natural weighting and Briggs −0.5 (the reporter's),
  with WEIGHT_SPECTRUM set per arm on the even-pair dumps to 0 (so only the held-out dumps are imaged)
  and to the arm's weights elsewhere. Arms: **raw** (as apply left it), **unity** (1 on unflagged
  cells), **calwt** (a second `apply` with `calwt: true` on the same tables; CORRECTED_DATA is unchanged
  by calwt), **R-mad** (#55's default) and **R-clip** (this note's). Noise per image: the robust rms
  (1.4826 × MAD) of each of the 16 tiles of a 4 × 4 grid over the inner 1536 × 1536 pixels. For an arm
  against a reference arm: the 16 tile ratios rms(arm)/rms(ref), their median r and mean ± standard
  error. The V sky is taken as empty; a tile whose raw-arm V peak exceeds 10× its rms is dropped from
  every arm and the drop is reported.
- **S (snapshot SNR on known sources), reported.** `rang-core lightcurve --weights ms --no-model` on the
  target's CORRECTED_DATA, Stokes I, one snapshot per held-out dump, at the 20 brightest compact sources
  of E2-N's target list within 0.5° of the phase centre (positions from the raw-arm natural Stokes I dirty
  image's peaks, chosen before any arm's light curve is read) and at 20 control positions (seed
  `w48-ctrl`, ≥ 30″ from any source above 5σ). σ_snap = robust rms over the control positions' snapshot
  fluxes; SNR per source = mean snapshot flux / σ_snap; reported per arm as σ_snap ratio and median SNR.
  This is #48's transient-search measure in rang's own tool.
- **T (truth, simulations).** Per case, `stokes_v` and `residual`, for `clipped` (and `mad`, `classic`
  for reference): median of w·σ² over unflagged cells, and e(w) = sqrt(S(w)/S(1/σ²)) with the true σ,
  against the block-ideal floor (weights 1/⟨σ²⟩ over each block), and the count of unflagged cells at
  weight 0.
- **G1 (statwt), regression.** #55's exact statwt comparison for `classic` re-run on the same simulated
  MS (tests on the public fixture keep it).
- **Q (QuartiCal robust weights), comparison arm.** QuartiCal 0.2.7 (the WSL venv of DD1,
  `~/Build/tmp/20261123-dd15/venv-qc027`) on the clean and rfi simulations: one `diag_complex` G term,
  `time_interval` 0 per scan chunk, `freq_chunk` 16, `solver.robust: true`, `iter_recipe [25, 25]`,
  `output.products [weight]`. Its weights against 1/σ²: median ratio after one global scale, and e.
  Reported, not gating. Not run on E2-N (the target has no model, so its residual holds the sky).

## 5. Tolerances (frozen)

- **T, clean** (both modes, `clipped`): median w·σ² within [0.98, 1.02]; e ≤ floor + 0.003 (floor 1.0071
  at #55's shape; `classic` reached floor + 0.0016 there, `mad` floor + 0.0045).
- **T, rfi** (100×, 1 %): median within [0.98, 1.02]; e ≤ floor + 0.005.
- **T, rfi-low** (3-5×, 2 %): reported, not gated; the expected bias from the residue below the clip is
  computed beside it.
- **T, short:** 0 unflagged cells at weight 0 with the defaults; e ≤ floor + 0.01.
- **T, baseline-excess:** median within [0.98, 1.02]; e ≤ floor + 0.003.
- **G1:** maximum relative difference against statwt ≤ 1e-5 for `classic` (unchanged: it was 0.0).
- **I, per real-data field:** R-clip **beats** a reference arm when the median tile ratio r ≤ 0.99 and
  mean + 2 × standard error < 1.00; it is **not worse** when r ≤ 1.005.

## 6. Decision rule (frozen)

1. **Estimator ships** (statistic `clipped` and the fills, `statistic: clipped` the new default of the
   off-by-default stage) when T (all gated cases) and G1 pass. If a T case fails, one dated revision is
   allowed (a change of c or of the fill order, re-run on every case), then the outcome stands; on
   failure `mad` stays the default and the fills ship only if `short` passes.
2. **H2, the documentation and the default question**, on the held-out real-data fields (E2-N
   J1744−5144 and J0408−6545, natural weighting; the E2-N-c4 fields reported apart):
   - R-clip beats raw and unity on every held-out field, at natural weighting: `docs/limits.md` and the
     apply how-to recommend `apply.reweight.mode: stokes_v` for native L0 linear-feed data, and the note
     **recommends** turning it on by default for native L0 data to the coordinator. It is **not** turned
     on in this branch: a default that changes every E2 image is the owner's decision.
   - R-clip not worse than raw and unity on every held-out field, and beats one of them on at least one:
     documented as an option with the measured numbers; no recommendation for a default.
   - R-clip worse than raw (r > 1.005) on any held-out field: recorded as null for that field, the docs
     say so, and the stage stays an option.
   The E2-N target (development) and the c4 fields, and Briggs −0.5, N and S are reported beside the rule
   and decide nothing.
3. Nothing in this rule changes `calwt`, flagging or calibration.

## 7. Hosts, runs and stop rules

- **nash** for E2-N, E2-N-c4 and the images (`nice -n 19 ionice -c3` through nash's main-checkout
  `tools/heavy_lock.py run --slots N --mem G`, booked by measured use; a job starts only with more than
  100 GB of RAM free and swap not growing). Run root `nash:~/rang-data/outputs/weights-k-20261125/`; the
  inputs are copied there (E2-N's MS and MVF are only read).
- **glacier** for the simulations and the tests (shared slots); QuartiCal in WSL with MS scratch on WSL's
  own disk, venv under `~/Build/tmp/20261125-weights-k`.
- Rows in [tool-timings.md](tool-timings.md) per run. Archive `research/results/weights-48/` (JSON, no MS
  or FITS). Scripts committed before they are run on scored arms.
- Order: this note; code and tests; simulations (T, G1, Q); E2-N and E2-N-c4 chains; the c4 precondition;
  R weights and arms; I, then N and S; rule.

## 8. Measured

### 8.1 Simulations: T, G1, Q (2026-11-25, glacier shared slots; WSL for CASA and QuartiCal)

Script [w48_sim.py](results/weights-k-scripts/w48_sim.py); run roots `D:ang\outputs\weights-k-20261125\sim`
(first run) and `...\sim-r1` (revision R1); archive [results/weights-48/](results/weights-48/). Arms at the
stage defaults (chanbin 16, minsamp 200, smooth 5, fill true), 256 channels; e is against the true σ,
floor 1.0071 (block-ideal), unity 1.2091 (1.2458 on baseline-excess).

| Case | Arm | First run: median, e | R1: median, e | R1 gate |
| --- | --- | --- | --- | --- |
| clean | stokes_v clipped | 1.0008, 1.0370 | 1.0026, **1.0087** | pass (floor + 0.0016) |
| | residual clipped | 1.0004, 1.0369 | 1.0016, 1.0087 | pass |
| | stokes_v classic / mad | 1.0006, 1.0368 / 1.0026, 1.0398 | 1.0022, 1.0087 / 1.0068, 1.0116 | – (mad floor + 0.0045) |
| rfi (100×, 1 %) | stokes_v clipped | 1.0025, 1.0370 | 1.0030, 1.0088 | pass |
| | residual clipped | 1.0000, 1.0369 | 1.0015, 1.0087 | pass |
| | stokes_v classic / mad | 0.0107, 1.14 / 0.958, 1.040 | 0.0108, 2.95 / 0.960, 1.0117 | – |
| rfi-low (3-5×, 2 %), reported | stokes_v clipped | 0.928, 1.0374 | 0.929, 1.0095 | – |
| | residual clipped | 0.972, 1.0371 | 0.973, 1.0091 | – |
| | stokes_v classic / mad | 0.769, 1.039 / 0.943, 1.040 | 0.772, 1.0130 / 0.947, 1.0117 | – |
| short (14, 8, 14 dumps) | stokes_v clipped | 1.0016, 1.0308 | 1.0019, 1.0091; 0 cells at weight 0 | pass |
| | residual clipped | – | 1.0029, 1.0091; 0 | pass |
| baseline-excess | stokes_v clipped | 1.0005, 1.0372 | 1.0018, 1.0087 | pass |
| | residual clipped | – | 1.0022, 1.0087 | pass |

- **First run (as frozen): T fails for every statistic** (section 9 R1: the smoothing, not the statistic).
- **R1: T passes for `clipped` in every gated case and both modes.** `classic` passes clean cases and
  collapses with RFI (0.011); `mad` misses e by 0.003 on clean data and the RFI median for `stokes_v`.
- rfi-low: the computed bias of the clip for that mixture is 1.029 per correlation (expected median
  0.972); `residual` reads 0.973, `stokes_v` 0.929, lower because V carries the outliers of both XY and
  YX (twice the outlier fraction). Reported, not gated.
- short: the 8-dump scan's blocks (128 V samples < 200) are filled from the same baseline pooled over the
  three scans (1,920 blocks for `stokes_v`, 7,680 per-correlation for `residual`); none reach the array
  median; no unflagged cell at weight 0.
- **G1, CASA statwt** (6.7.6.14 in `rang-o-casa:6.7.6.14`, WSL docker, `residual`/`classic`, minsamp 2,
  smooth 0, fill false): max relative difference **0.0** over 7,372,800 cells. Pass.
- **Q, QuartiCal 0.2.7 `solver.robust`** (diag_complex G, per-scan chunks of 16 channels, `iter_recipe
  [25, 25]`, 47 s for both): e **1.0509** (clean) and **1.0964** (rfi), against 1.0087 and 1.0088 for
  `clipped`; its weights carry one covariance per chunk, so they follow the channel shape but not the
  per-antenna one (raw scale 0.53 of 1/σ², removed before e).

**Rule 1: met (after R1).** `clipped` and the fills ship; `statistic: clipped` is the stage's default;
`mode` stays `off`.

## 9. Amendments

**R1, 2026-11-25 12:40 SAST, post hoc: the one revision rule 1 allows, after T's first score was read
(simulations only; no real-data arm has run).** T as first run, at the stage defaults (`smooth: 5`):
**every** statistic, `classic` included, sits at e = floor + 0.024 to 0.033 on every clean case
(clean: classic 1.0368, clipped 1.0370, mad 1.0398; floor 1.0071), so T fails for all of them, while
#55's revision 1 reached floor + 0.0016 with `classic` at `smooth: 0`. Cause, read in the code: #55's
`regularise` replaces **every** block by the 5-block running median, not only the short ones, although
its docstring ("Fill NaN blocks"), the config comment ("fills short blocks") and this note's section 1
(fill 2) all describe a fill. A 5 × 16-channel median cannot follow s(ν)'s bump at 256 channels. The
statistic is not the cause: `clipped` equals `classic` to 0.0002 in e on every case, and is the only
one near 1 in median ratio on `rfi` (1.0025, 1.0000; classic 0.011, mad 0.958 and 0.977).
**Revision:** `regularise` fills only the blocks below `minsamp` (the fill order of section 1, now as
the code does it); everything else, bounds and rule unchanged; T re-run on every case. The first
run's score is archived beside the revision's. This changes the stage's weights for any non-off mode
with `smooth > 0` (the off default is untouched); stated in the CHANGELOG.
