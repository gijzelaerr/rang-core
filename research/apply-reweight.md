# An empirical re-weighting stage after apply (issue #55)

Status: **proposed, frozen 2026-11-21 before any code.** Follows #48, closed null in
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
