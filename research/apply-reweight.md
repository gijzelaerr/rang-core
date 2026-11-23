# An empirical re-weighting stage after apply (issue #55)

Status: **measured 2026-11-21 (sections 7-9): G0 and G1 pass, G2 fails after its one revision, so under section 5 the stage does not ship; G3: R 3.2 % below raw on the E2-N target (section 10). Frozen 2026-11-21 before any code.** Follows #48, closed null in
[apply-calwt](https://github.com/gijzelaerr/rang-core/blob/apply-calwt/research/apply-calwt.md)
(branch `apply-calwt`, 95b4d9f9). That note found that `calwt: true` is CASA's rule, which is
channel-flat, so it cannot remove the bandpass shape that katdal's raw L0 `WEIGHT_SPECTRUM` carries.
Procedure: `docs/agents/propose-and-measure.md`.

## 1. The report, and what is taken from it

An external tester (Killick, #48) reported on SARAO block 1680477139. With raw L0 weights, a snapshot
transient search lost about 17 % in noise against an L1 reference. Unity weights recovered most of
that, and empirical 1/σ² weights from the Stokes V residual about 2.5 % more (per baseline × 16-channel
block, a robust variance over time, regularised by a 5-block running median). The tester's
`rederive_weights.py` recipe was read as a description and not run. On E2-N (1735268787) the raw
weights already track the noise: in apply-calwt's measure the top weight quintile is at 0.88 and
`e(raw)` is 1.039 on the target. So E2-N may show little gain. That is the point of measuring it.

## 2. CASA `statwt`, the oracle (read 2026-11-21, casa6 `mstransform/TVI`, branch master)

For every block of one baseline × `chanbin` channels × `timebin` (within a scan unless `combine`
says otherwise), `StatWtVarianceAndWeightCalculator::computeVariance` takes the real and imaginary
parts of the chosen column (`datacolumn='residual'` is CORRECTED − MODEL). Per correlation it
computes their variances with the statistics algorithm (`classic`: the variance with divisor N,
weighted by exposure), and returns the mean, `(var_re + var_im)/2`. The weight is
`exposure / variance`. A block with fewer than `minsamp` unflagged points gets weight 0, and its
cells are flagged. With equal exposures, as on MeerKAT, the weight is `1 / variance`. statwt offers
no Stokes V mode and no MAD statistic.

## 3. The stage (proposed)

`apply.reweight`, off by default:

```yaml
apply:
  reweight:
    mode: off           # off | residual | stokes_v
    chanbin: 16         # channels per block
    timebin: scan       # one block per scan (or a time in seconds)
    statistic: mad      # mad | classic (classic: statwt's estimator)
    minsamp: 200        # unflagged samples per block; fewer: filled (smooth > 0) or weight 0
    smooth: 5           # running median over channel blocks, then the baseline's median (0: none)
```

- **`residual`:** per correlation, CORRECTED_DATA − MODEL_DATA. The variance is
  `(var_re + var_im)/2`, as statwt's, and the weight is `1/var`.
- **`stokes_v`:** for linear feeds with an empty V sky, V = (XY − YX)/(2i) of CORRECTED_DATA, with no
  model needed. The per-correlation variance is `σ² = 2 var(V)`, and one weight serves all four
  correlations.
- **`mad`:** `var = (1.4826 · MAD)²` of the real and imaginary parts, averaged. The scale is the
  Gaussian one, and it is robust to RFI residue. **`classic`** is statwt's estimator, for the oracle.
- The weights are written to WEIGHT_SPECTRUM, and WEIGHT gets the per-correlation mean, as statwt
  does. A cell of a block that stays empty gets weight 0, but its flag is not changed, unlike statwt;
  this is stated. The stage runs after `apply`, inside the apply stage when `mode` is not `off`.
- **Kernel in Rust** (`core/src/reweight.rs`): the per-block statistics over a dense block of
  values and flags. Python orchestrates by scan and channel slices, within `data.memory_limit_gb`.
- **Off is bit-identical.** With `mode: off` the apply stage runs as today. The stage hash includes
  `reweight` only when `mode` is not `off` (the `calwt` key's pattern), so no existing hash changes.

## 4. Gates (frozen)

- **G0, off:** with `mode: off` the apply output and the stage hash equal today's, bit for bit
  (tests; gain-hash gate; the quick check).
- **G1, statwt oracle** (CASA 6.7.6.14, `rang-o-casa_6.7.6.14.sif`): `statwt(datacolumn='residual',
  chanbin=16, timebin=<longer than any scan>, statalg='classic', minsamp=…)` on a copy of a simulated
  MS. Against rang's `residual`/`classic` weights over cells both leave unflagged, the maximum
  relative difference must be at most 1e-5 (float32 weights). The cells of blocks rang leaves at weight
  0 must equal the cells statwt flags.
- **G2, a simulation with known per-channel noise.** 16 antennas, 3 scans, 64 channels. The noise
  σ(p, q, ν) = σ0 · s(ν) · √(f_p f_q), with s(ν) a bandpass-like shape varying by 3× over the band and
  f_p per-antenna factors in [0.7, 1.4]; V of the sky is 0; 10 Jy on XX and YY. Per mode (`stokes_v`,
  `residual`) and statistic (`mad`, `classic`), against 1/σ²: the median ratio must lie within
  [0.98, 1.02], and the implied natural-weighting noise `e(w)` (section 5) at most 1.01. With
  injected RFI in 1 % of cells, `mad` must stay within these bounds and `classic` is reported.
- **G3, E2-N, held-out** (apply-calwt's measure N): Stokes V of CORRECTED_DATA. Consecutive-dump
  differences on even pairs estimate σ²; S(w) on odd pairs; `e(w) = sqrt(S(w)/S(1/σ̂²))`. Arms:
  raw (WEIGHT_SPECTRUM as apply leaves it, `calwt: false`), unity, and R. R is the stage's `stokes_v`
  and `mad` weights at the defaults, **estimated from even dumps only** (a research argument of the
  stage function), so no evaluation cell enters its estimate. Fields: the target ASKAPJ1745 and
  J1744-5144. Reported: `e`, the quintiles, and the implied image-noise change
  `e(R)/e(raw) − 1`.

## 5. Decision rule (frozen)

- G0, G1 and G2 pass: the stage ships behind `apply.reweight.mode` (off by default), documented in
  `docs/limits.md` beside `calwt`.
- G3 decides only the documentation. If R beats raw by at least 2 % on the E2-N target, the docs
  recommend `stokes_v` for native L0 data. If it is within 2 %, the docs say the gain depends on the
  conversion (as #48 found), and point to the quintile test to decide per data set. If R is worse
  than raw by more than 2 %, the stage ships anyway, but the docs advise against it on data like
  E2-N, and the result is recorded as null for E2-N.
- G0 fails: nothing ships. G1 or G2 fails: the failure is recorded; one dated revision is allowed,
  then the outcome stands as recorded.

## 6. Host and data

Simulation, kernel and tests on glacier or nash. E2-N on nash. CORRECTED_DATA is read from
apply-calwt's calibrated copy (`nash:~/rang-data/outputs/apply-calwt-20261120/`, read only; calwt
changes only the weights, so its CORRECTED_DATA is arm F's). The raw weights are read from the
original `nash:~/rang-data/outputs/e2n-20261116/e2n.ms` (read only), whose WEIGHT_SPECTRUM
`calwt: false` leaves unchanged. Any column the stage writes goes into my own copy in my own run
root.
nash jobs start only with more than 100 GB of RAM free and swap not growing (`free -g`). A timing
row goes in `research/tool-timings.md` per run.

## 7. Implementation notes (2026-11-21, before any measurement)

- `apply.reweight.mode` has the config kind `learned_mode`, because YAML reads a bare `off` as false
  (the defaults round trip found it). `timebin` is a string, `scan` or seconds.
- The stage estimates one scan at a time, in channel slices that fit half of
  `data.memory_limit_gb`. WEIGHT is the median of the new WEIGHT_SPECTRUM over each row's unflagged
  channels with a positive weight, as statwt sets it (`StatWtTVI::weight`). This was changed from a
  mean after reading statwt and before G1's WEIGHT comparison.
- **Limitation:** a block with fewer than `minsamp` valid samples and no fill (`smooth: 0`, or a
  baseline with no block at `minsamp`) gets weight 0, and its flags are not changed. On short scans
  at the defaults (`minsamp: 200` with 16 channels needs at least 13 unflagged dumps) whole baselines
  can get weight 0.

## 8. Measured (2026-11-21, nash; branch at b43b180e and its successors)

- **G0, off: pass.** With `mode: off` the apply summary and stage hash are unchanged
  (`tests/test_apply_reweight.py`). The quick check passed: 608 tests, the gain-hash gate, and Rust's
  319 core tests.
- **G1, CASA statwt: pass, exact.** `statwt(datacolumn='residual', chanbin=16, timebin='100000s',
  statalg='classic')` against rang's `residual`/`classic` weights: maximum relative difference
  **0.0** on WEIGHT_SPECTRUM over 1,843,200 cells (64 channels, `minsamp` 2) and 7,372,800 cells
  (256 channels). With flags (an addition after review, before scoring: 60 % of the cells on
  antenna 0's baselines in scan 2, all of baseline 1-2 in scan 3, `minsamp` 200 for both), the
  81,920 cells of short blocks that rang leaves at weight 0 are exactly the cells statwt newly
  flags, and WEIGHT agrees to 0.0. [results/apply-reweight/](results/apply-reweight/).
- **G2, known noise: fail as frozen, and still after the revision.** The G2 arms ran at `minsamp` 2
  and `smooth` 0, not the defaults.

| Channels | Arm | Clean: median ratio, e | 1 % RFI: median ratio, e |
| --- | --- | --- | --- |
| 64 (as frozen) | residual classic | 0.982, 1.040 | 0.011, 3.37 |
| | residual mad | 1.004, 1.047 | 0.981, 1.047 |
| | stokes_v classic | 0.983, 1.040 | 0.011, 2.24 |
| | stokes_v mad | 1.004, 1.048 | 0.960, 1.047 |
| | unity / block-ideal floor | –, 1.209 / 1.038 | |
| 256 (revision 1) | residual classic | 1.002, **1.0087** | 0.012, 3.23 |
| | residual mad | 1.003, 1.0116 | 0.981, 1.0116 |
| | stokes_v classic | 1.002, **1.0087** | 0.011, 2.65 |
| | stokes_v mad | 1.005, 1.0117 | 0.956, 1.0119 |
| | unity / block-ideal floor | –, 1.209 / 1.0071 | |

- **Revision 1** (dated 2026-11-21, after the 64-channel result; the one revision section 5
  allows). At 64 channels a 16-channel block spans a quarter of the band. The noise shape s(ν) then
  varies inside a block, and no block-constant weight can follow it: the ideal block-constant
  weights, 1/⟨σ²⟩ over the block, reach only e = 1.038, and every arm sits within 0.2-1 % of that
  floor. On MeerKAT 4k data a 16-channel block is 0.4 % of the band. So the revision reran G1 and G2
  at 256 channels, with the same shape, seeds and tolerances, and with the block-ideal floor
  reported. Classic then passes on clean data (e 1.0087, floor 1.0071). MAD fails narrowly
  (e 1.0116-1.0117, bound 1.01), because a MAD variance is less efficient than the classic one. With
  1 % RFI, `stokes_v` MAD gives a median ratio of 0.956, outside [0.98, 1.02].
- **A gate-design finding, not a re-score.** With a fraction ε of large outliers, MAD's variance is
  biased up by (a_ε/0.6745)², where 2Φ(a_ε) − 1 = 0.5/(1 − ε). V carries the outliers of XY and YX,
  so ε = 2 % and the expected median ratio is 0.954, against 0.956 measured. For `residual`, ε = 1 %
  gives 0.978, against 0.981. So the frozen RFI bound was out of reach for `stokes_v` with MAD by
  construction, and its failure does not depend on smoothing.

## 9. Outcome under section 5

G0 and G1 pass. **G2 fails**: MAD, the default statistic, misses e ≤ 1.01 on clean data by about
0.002, and the 1 % RFI bound, after the one allowed revision. So **the stage does not ship as
frozen**. The code is on the branch, behind an option that is off by default. Merging it would add
that option, which did not pass G2. That is the coordinator's and the owner's call. What a
follow-up would need is its own frozen note: classic as the default (it passes on clean data), or
a MAD bound set from MAD's efficiency, and an RFI clause that uses MAD's known bias. G3 (E2-N) is
recorded in section 10 for the issue's implied image-noise change; under section 5 it decides
nothing here.

## 10. G3, E2-N held out (2026-11-21, nash)

[rw_g3.py](results/rw-scripts/rw_g3.py) at b5bcbb84 on apply-calwt's calibrated E2-N
(`outputs/apply-calwt-20261120/e2n.ms`, CORRECTED_DATA) with raw weights from
`outputs/e2n-20261116/e2n.ms`; R is `stokes_v`, `mad`, the defaults, fitted on the dumps of even
pairs only. 2,446 s wall, 39.7 GB peak, `--slots 2 --mem 40`. Archive:
[g3.json](results/apply-reweight/g3.json).

| field | cells | e raw | e unity | e R | R vs raw |
|---|---|---|---|---|---|
| ASKAPJ1745 (target) | 141.1 M | 1.0395 | 1.0783 | **1.0060** | **-3.2 %** |
| J1744-5144 | 20.1 M | 0.7501 | 0.7755 | no cells | - |

- Quintiles of w|d|^2 over its mean on the target (flat = 1): raw 1.01, 1.21, 1.01, 0.89, 0.88;
  R 1.05, 1.00, 0.98, 0.98, 0.99. R's weights follow the noise; raw's do not.
- J1744-5144: its scans are 14-15 dumps, so a per-scan block of 16 channels holds about
  120 Stokes V samples on the fit dumps, below `minsamp` 200; with every block of a baseline empty,
  `smooth` has nothing to fill from, and every weight is 0. At the defaults the stage zeroes such
  fields' weights (section 7's limitation); a `timebin` longer than a scan, or a smaller `minsamp`,
  would be needed. Its e below 1 means the even-pair sigma estimate is a poor reference on 14-dump
  scans, not that raw beats ideal.
- Under section 5, R beats raw by more than 2 % on the target, so the docs would recommend
  `stokes_v` for native L0 data. The stage does not ship (section 9), so this changes nothing on
  `main`; it is the measured image-noise case for a follow-up with classic as the default (G2's
  passing statistic). The target number is MAD's; classic was not run on E2-N.

