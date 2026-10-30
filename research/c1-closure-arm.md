# Rang C1: a closure-invariant comparator arm

Protocol frozen 2026-10-30 on branch `c1-closure` (from main `06a59fc`),
before any C1 code was written. Task C1 of [big-plan.md](big-plan.md) (after
L1-M, before L4); recommendation 3 of
[literature-2024-2026.md](literature-2024-2026.md) §5.1.

Status: **proposed** (this section). Results are appended below the
protocol when measured; nothing above "Measured result" changes after this
commit except through a dated, labelled amendment.

## Why

K, L1, L2 and L1-M are null ([core-k-luno-campaign.md](core-k-luno-campaign.md),
[luno-array-campaign.md](luno-array-campaign.md),
[luno-1830-campaign.md](luno-1830-campaign.md),
[l1-model-completeness.md](l1-model-completeness.md)): the TV policy rejected
every TV-guided mask, and against the CARACal first-pass Tricolour flags
held-out error moved by well under 0.1 %. Gain TV measures structure in the
antenna-factorable part of the data, and it carries the gauge freedom of
the solve (`flagging.md`: raw against polar-gauge TV). A closure quantity is
invariant under every per-antenna gain, so a statistic on closures sees only
what no per-antenna Jones matrix can absorb: baseline-based errors, RFI that
differs between baselines, and model error. C1 asks whether that gauge-free
signal (i) carries structure the gain-TV map does not, (ii) changes the
policy's decision when it is used as the guidance, and (iii) flags the same
data as Tricolour.

## Pre-protocol probe (labelled scratch)

`outputs/c1-20261030-00-probes/probe1.py` and `probe1.out` (12.9 s,
0.54 GB). Stations 0–11 of chunk 0 (2,112 rows), every fourth channel,
training cells of the seed-7 split, stored model:

- Parallel-hand weights have a median of 4.07 (XX) and 4.04 (YY); |DATA|
  9.37 and 9.32 Jy (uncorrected, so |g|² ≈ 0.62 of the 14.98 Jy model);
  |XY|, |YX| 0.23 Jy, about 2.5 % of the parallel hands.
- **Closure phase** (XX and YY, all triangles of the 12 stations;
  3.2 M values): median |Δφ| 0.0185 rad against the model's closure phase.
  With σ² = 1/w per complex correlation the mean z² is **0.171**, and no
  |z| exceeds 5.
- **Closure trace** (a subset of the cyclic quadrangles defined below;
  0.73 M values): median |ΔT| 0.027 against the model's trace, mean
  |ΔT|²/σ² **0.180**, 99th percentile of |ΔT|/σ 0.92.

So σ² = 1/w overstates the closure noise by a factor of about 5.6, the
same factor that L1's χ²_train of 0.208 implies for the visibilities (the
weights are a QuartiCal product). On short baselines the closures are
consistent with noise and have no tail. That is the concrete basis for the
null prior below.

Polarisation (literature recommendation 8): Taylor and Legodi 2024
(arXiv:2405.04131, as summarised in the literature scan §4.3) give
0.16 % residual instrumental linear and 0.05 % circular polarisation for
MeerKAT calibrators. A fractional polarisation p perturbs a closure trace
by O(p) ≈ 0.002, an order of magnitude below the per-sample |ΔT| of 0.027.
The unpolarised-model closures are therefore valid references here.

## Question

On LUNO row chunk 0 (PKS 1934−638, 53 stations with rows, 1070–1498 MHz,
the stored MODEL_DATA, which L1-M found to fit best):

- **Q1.** Does the closure-TV map carry structure that the gain-TV map does
  not? Correlation between the two maps per antenna, per baseline and per
  channel block; variance of the closure map explained by the gain map; a
  split-half reliability of the closure map as the noise reference.
- **Q2.** Does a closure-guided policy select any mask that the frozen
  objective accepts, and does it, or a direct closure-outlier mask, move
  held-out MSE or residual RMS against the first pass (L1's decision rule)?
- **Q3.** Do closure outliers coincide with the Tricolour additions, with
  A1's emptied GNSS station-bins, or with L1's own residual outliers?

## Closure quantities (frozen)

**Cells.** A closure is formed at one (time, channel) cell from the DATA of
the run's state (the L1 decode), and from MODEL_DATA for the model's
closure. **A closure exists iff every baseline it uses is a training cell
at that (time, channel)** of L1's seed-7 split. Validation and test cells
never enter a closure, so the guidance and the comparator mask are chosen
without held-out data, as L1's candidates are. With an 80 % training
fraction a triangle survives about 51 % and a quadrangle about 41 % of the
time; the survival fractions are reported. Autocorrelations never enter.
One row per (time, baseline) is asserted.

**Conventions.** Correlations XX, XY, YX, YY (CORR_TYPE 9–12, checked),
row-major 2×2 as in `core/src/jones.rs`. The visibility of an unordered
pair is V_ab for ANTENNA1 = a < ANTENNA2 = b and V_ba = V_abᴴ. Gains act as
V_ab → G_a V_ab G_bᴴ, the core's convention.

**Stations.** The stations with rows, in index order (53 here), are a cycle;
`next(x; excluded)` is the next station in that cycle not in `excluded`.

Three families are computed:

1. **T, closure trace (primary; full GL(2,C) invariant).** Broderick and
   Pesce 2020: for a quadrangle (a, b, s, d),
   `T = ½ tr(V_ab V_sb⁻¹ V_sd V_ad⁻¹)`. Under any invertible per-antenna
   2×2 gains it is unchanged (the product is G_a X G_a⁻¹). **The cyclic
   quadrangle set:** for every baseline (a, b), a < b, and every station
   s ∉ {a, b}, d = next(s; {a, b}). (a, b) is the quadrangle's *lead*
   baseline. Each baseline leads N − 2 quadrangles; any other baseline
   appears in at most three of one baseline's set, so a median over the set
   isolates an error on the lead baseline.
2. **P, closure phase (secondary; invariant under diagonal gains only).**
   All triangles: for baseline (a, b) and every s ∉ {a, b},
   φ_h = arg(V_ab,h V_bs,h V_sa,h) for h = XX and YY. Under full Jones
   gains the leakage term (|XY| ≈ 2.5 % of |XX| here) enters, so P is not
   GL(2,C) invariant; it is reported, not used for a flagging arm.
3. **A, log closure amplitude (secondary; diagonal gains only).** On the
   cyclic quadrangles: `ln|V_ab,h| + ln|V_sd,h| − ln|V_sb,h| − ln|V_ad,h|`,
   h = XX, YY.

**Missing baselines.** Kumar, Nityananda and Samuel (2024) extend the
invariants to incomplete graphs, as flagged data are. C1 uses a practical
rule in that setting, not their construction (it has not been checked
against the paper's text): closures are formed only on cycles whose edges
all exist. For T and A, if (s, d) or (a, d) is missing, d advances to the
next station in the cycle, up to **3** further tries; if (s, b) is missing,
the quadrangle is skipped. Triangles are not re-routed. A matrix whose
determinant is zero or non-finite skips the closure.

**Residual and noise.** For each closure k the residual is r_k = data
closure − model closure: complex for T, real per hand for P (wrapped to
(−π, π]) and A. Noise is propagated to first order from WEIGHT_SPECTRUM
with σ² = 1/w per complex correlation:

- T: σ² = ¼ Σ_h |P_h|² Σ_e 1/(w_e,h |V_e,h|²), with P_h the parallel-hand
  product `V_ab,h V_sd,h / (V_sb,h V_ad,h)` and e over the four edges;
- P: σ_h² = Σ_e 1/(2 w_e,h |V_e,h|²) over the three edges;
- A: σ_h² = Σ_e 1/(2 w_e,h |V_e,h|²) over the four edges.

|V| is the data amplitude. The normalised closure residual is
z_k = sqrt(mean_j |r_kj|²/σ_kj²) over its m components (m = 1 for T, 2 for
P and A). The probe says the absolute scale is off by about 5.6 (QuartiCal
weights); the run reports the median z_k² per family as the calibration,
and every mask below is scale-free (a per-baseline robust z).

**Per-sample scores** (for baseline (a, b) at (time, channel); computed in
Rust, never storing per-closure arrays):

- **closure residual** R = median_k z_k over the baseline's closures (its
  lead quadrangles for T and A, its N − 2 triangles for P);
- **closure TV** V = median_k e_k, where e_k is the mean over the incident
  time and frequency edges of the same closure (same s, same d) of
  `sqrt(mean_j |r_kj(x) − r_kj(x')|² / (σ_kj(x)² + σ_kj(x')²))` (phase
  differences wrapped), x' the adjacent integration or channel;
- the closure count n. A sample with n < **5** has no score
  (min(5, N − 2) on a station subset).

The medians use NumPy's convention (mean of the two middle values).

## The closure-TV map and the closure-outlier score (frozen)

- **Closure-TV map (per baseline).** On L1's gain grid (2 integrations ×
  32 channels; 16 × 64 bins): the mean of V over the bin's training samples
  with a score, per (time bin, frequency bin, baseline); NaN when none.
- **Per antenna.** The median over the antenna's baselines of the baseline
  map, per bin: a (16, 64, nant) map, the shape of the gain-TV map.
- **Closure-outlier score (per sample).** Per baseline, over its training
  samples with a T score, with x = ln R:
  z = max((x − median)/max(1.4826 MAD, 0.05), 0), the estimator of
  `core_campaign_array.baseline_scores`, applied to the closure residual
  instead of the whitened visibility residual.

## Arms (frozen)

One process runs L1's `core_campaign_array.run` **unedited** on all
stations of chunk 0, then the C1 arms on its state:

- Two scoped hooks (each in a `try/finally` that restores the module
  attribute): `build_state` keeps a reference to the state and `extra`;
  `tv_loop` keeps a reference to the base solve of the `tv` loop (the
  `original` arm with its policy features). The run's arms, split, solver,
  policy, images and amendment 1 are L1's.
- **L1's arms**: `original`, `tricolour-firstpass`, `tricolour-mild`,
  `tv-policy`, `tv-unguided-best`, `tricolour-firstpass+tv` (expected
  unavailable as in L1), `tricolour-firstpass+tv-a1`.
- **(i) `closure-tv-policy`.** L1's `tv_loop`, unedited, on the captured
  `original` base, prefix `closure-tv`, with a copy of the base whose
  `features["guidance"]` is the T closure-TV baseline map at each candidate
  cell and whose `features["guidance_scale"]` is the median of the positive
  finite map values over all training cells (`guidance_scale`'s rule). The
  candidates (training cells with fused-pass score ≥ 2), the outlier
  scores, the thresholds (8, 5, 3), the weights α ∈ {0, 1, 3}, the 2 %
  budget and the objective (fixed-support gain TV + 2 × flag fraction +
  0.25 × validation ratio, 1 % validation tolerance) are unchanged. The
  α = 0 masks equal the TV loop's; they are re-solved and must reproduce the
  TV loop's α = 0 trials (mask hash, objective), a determinism check. **Only
  an α > 0 selection counts as closure guidance acting.**
- **(ii) `closure-outlier`.** The training cells with closure-outlier
  z ≥ **5**, cut to the 2 % budget of training cells by largest z (stable,
  ties by cell order), solved by L1's `solve_arm` at the `original` scale
  and imaged by L1's `image_arm` with the run's boxes. If the mask is
  empty the arm is the `original` solve and is reported as such, unsolved.
  The counts at z ≥ 3 and z ≥ 8 are reported.
- The P family's z ≥ 5 set is formed the same way for Q3 only (no solve).

## Decision rules and calls (frozen)

L1's rule throughout: a ratio candidate/reference ≤ 0.99 is *better*,
≥ 1.01 *worse*, else *null*; a missing value is *undecidable*. Pairs:

| Candidate | Reference |
| --- | --- |
| closure-tv-policy | tricolour-firstpass (headline) |
| closure-tv-policy | original |
| closure-tv-policy | tv-policy |
| closure-outlier | tricolour-firstpass |
| closure-outlier | original |
| closure-outlier | tv-policy |

Each pair is called three ways, all reported:

1. **Frozen** (L1's `available_hypothesis`): MSE_test, MSE_val and the
   residual RMS of the arm's image on all held-out samples.
2. **Amendment 1** (L1's matched rule): MSE on the held-out samples both
   arms predict validly.
3. **A1 drop** (pre-registered here, as A1 proposed): the emptied
   station-bins are computed after the split and before any C1 solve, from
   the run's `tricolour-firstpass` and `tricolour-mild` additions (a
   station-bin is emptied by an arm if it has training support in
   `original` and none in `train & ~additions`; the union of the two arms
   is used). Every validation and test sample on a row with either station
   emptied at its (time bin, frequency bin) is dropped from every arm, and
   the count is reported. If an arm still has invalid predictions on the
   remainder, the matched rule is applied on top (fallback) and that is
   stated. L1's frozen numbers are not changed; these are additional rows.

The residual RMS is the image metric of L1's `image_arm`; it is the same in
all three ways.

## Questions to numbers (frozen)

**Q1** (T primary; P and A reported the same way):

- ρ_ant: Spearman between the closure-TV per-antenna map and the gain-TV
  map of `original` (`gain_tv` of the polar-gauge gains, the map the TV
  policy uses), over bins where both are finite and the gain is valid.
- ρ_bl: Spearman between the closure-TV baseline map and the gain guidance
  max(map_p, map_q), per (bin, baseline).
- ρ_chan: Spearman between the 64 per-frequency-bin medians of the two
  maps (baseline level).
- R²_bl: squared Pearson correlation of ln(closure-TV baseline map) with
  ln(gain guidance): the variance explained by the gain map.
- R²_add: the fraction of the variance of ln(closure-TV baseline map)
  explained by an antenna-additive model a_p + a_q fitted per bin by least
  squares (how antenna-factorable the closure structure is; weight
  miscalibration per antenna would show here).
- ρ_half: split-half reliability, the Spearman between baseline maps built
  from the even and from the odd channels of each bin, and Spearman–Brown
  2ρ/(1 + ρ).

Calls: the closure map **carries structure the gain map does not** iff
ρ_half ≥ 0.5 and R²_bl ≤ 0.25; it is **redundant** iff ρ_bl ≥ 0.7;
**noise-dominated** iff ρ_half < 0.5 (then the correlations are reported but
not interpreted).

**Q2:** the `closure-tv-policy` selection (τ, α, count), the number of
admissible and accepted α > 0 candidates, and the three calls of each pair
above.

**Q3:** for the T outlier mask M (and the P set), against each set X —
`tricolour-firstpass` additions, `tricolour-mild` additions, the training
cells of A1's emptied station-bins, the training cells in A1's GNSS range
(1145.8–1301.0 MHz), L1's residual candidates (fused-pass score ≥ 2 on
`original`) and the `tv-policy` additions — report |M ∩ X|/|M|,
|M ∩ X|/|X| and the lift (|M ∩ X|/|M|)/(|X|/|train|). M **coincides** with X
iff |M ∩ X|/|M| ≥ 10 % and the lift ≥ 3.

## Comparator precondition and gates (frozen)

1. **L1's precondition** unedited into `outputs/c1-20261030-00-precondition`:
   K's precondition passes, the group check passes, and the four-station
   replay equals K's run `-01` under L2's `compare_replay_tolerant` (image
   hashes and image metrics at 1e-9 relative are exempt, P2's change).
2. **L1 reproduction:** the C1 run's L1 arms equal L1's run `-01` on every
   non-image, non-timing field (`core_campaign_fieldmodel.compare_with_l1`,
   imported, L1-M's checker, which exempts image-derived ratios). A failure
   is recorded and the C1 comparisons then stay within this run.
3. **Captured base:** its gains' SHA256 equals the run's `original`
   `gains_sha256`; the `closure-tv` loop's α = 0 trials equal the `tv`
   loop's (mask hash, objective).
4. **Kernel against NumPy in the run:** on 2 integrations × 2 channels × 20
   baselines of the run's data, a NumPy reference computes every closure of
   the three families and the per-sample R; max relative difference ≤ 1e-5.
5. **Unit tests** (offline, synthetic): the kernel equals a NumPy reference
   on small random arrays; closure traces are unchanged to 1e-10 relative
   under random per-antenna 2×2 gains (including reversed baselines);
   closure phases are unchanged under diagonal gains and changed under full
   gains (the test is sensitive); a planted baseline error is the maximum
   per-baseline score; T and A re-route around a missing edge.

## Acceptance criteria (frozen)

1. Gate 1 passes.
2. Gate 2 passes, or its failure is recorded and the comparison restricted.
3. Gates 3 and 4 pass.
4. L1's criteria 1–7 per run by L1's `check` unedited, recorded as they
   come out (L1 failed 2, 4 and 6 as frozen; the same is expected and is not
   this task's gate).
5. Q1–Q3 are decidable or explicitly undecidable, with the numbers.
6. Outputs: the run directory has L1's files plus `c1.json`; the checker
   writes `outputs/c1-20261030-02-check/result.json`;
   `research/results/c1-closure-arm.json` is under 250 KB, holds no
   visibilities and pins the hashes of the run's result files.
7. `cargo clippy -D warnings` and `rustfmt --check` on the C1 Rust files
   (built as a standalone crate until `lib.rs` lists them, so check-all does
   not see them), targeted pytest, and `bash tools/check-all.sh` once before
   the final commit.

Never modified: input FLAG and FLAG_ROW, the archived inputs (L1's
side-effect audit runs). Nothing is written outside `outputs/c1-20261030-*`
except the committed files.

## Runs and cost (frozen)

- `outputs/c1-20261030-00-smoke-4` (stations 0–3) and `-00-smoke-12`
  (stations 0–11, for the kernel's cost) are labelled smokes; they may fix
  bugs only.
- `outputs/c1-20261030-01`: the frozen whole-array run, started only if
  MemAvailable ≥ **16 GiB** (L1-M's 10.6 GB peak plus about 2 GB of
  per-sample scores), at `RAYON_NUM_THREADS=4`, `OPENBLAS_NUM_THREADS=1`.
- `outputs/c1-20261030-02-check`: the checker.

Every stage is timed. Expected: L1's part 12–15 min (L1-M); the T kernel
O(N³ × cells), estimated from the 12-station smoke before the run; the
closure-TV loop 6 new solves (α > 0) plus 3 repeats, about 5–10 min; the
outlier arm one solve and one image, 2–10 min. The cost line compares the
closure chain (kernel + map + loop) with the TV chain and with the
first-pass port, as L1's cost clause does.

## Expected outcome, stated before running

- **Q1: noise-dominated or distinct, not redundant.** The probe found
  closures consistent with noise on short baselines (no |z| > 5). The
  map's reproducible structure, if any, should come from RFI channels and
  long baselines, which per-antenna gains cannot follow, so R²_bl should be
  small (< 0.25) and ρ_bl well below 0.7.
- **Q2: null.** The closure guidance only re-weights the same fused-pass
  candidates within the same 2 % budget, and the objective still rewards a
  drop in gain TV, which a gauge-free guidance has no reason to produce.
  We expect every α > 0 closure-guided mask to be rejected or not to beat
  the unguided one, and every call against the first pass to be null
  (within ±1 %) under amendment 1 and the A1 drop. The closure-outlier arm,
  if non-empty, flags few cells and is expected null against `original`.
- **Q3: coincidence with Tricolour, if any.** Closure outliers that exist
  should sit where RFI differs between baselines, which is what the
  first pass removes, so a lift ≥ 3 against the first-pass additions is
  plausible; A1's emptied bins hold too few training cells (median 5 per
  bin) to say much.
- **What would count as a positive:** an α > 0 closure-guided mask
  selected and *better* (≤ 0.99) than the first pass in held-out MSE under
  amendment 1 or the A1 drop, with the residual RMS not *worse*; or a
  closure-outlier arm *better* than `original` and not *worse* than the
  first pass while flagging fewer cells than the first pass. Either would be
  the first non-null of the campaign series and would need a replication on
  1830−211 before any claim.
- A null here closes the last pre-registered arm before L4: neither the
  antenna-factorable (gain TV) nor the non-factorable (closure) statistic
  improves on the CARACal first pass on these data.

## Code to write after this commit (own files only)

- `core/src/closure.rs` (kernel, rayon over baselines, unit tests) and
  `core/src/ffi_closure.rs` (additive C ABI); built as a standalone cdylib
  (`core/target/c1-standalone`, with `jones.rs` by path) until `lib.rs`
  lists them; `RANG_C1_LIB` selects a prebuilt library.
- `python/rangtoy/core_closure.py`: loader, wrapper, NumPy reference, maps,
  robust z, Q1 statistics.
- `python/rangtoy/core_campaign_closure.py`: hooks, the C1 arms, the A1
  drop, the calls, Q3 overlaps, the checker and the archive.
- `examples/{run,check,archive}_c1.py`.
- `tests/test_core_closure.py`, `tests/test_core_campaign_closure.py`.
