# Rang C1: a closure-invariant comparator arm

Protocol frozen 2026-10-30 on branch `c1-closure` (from main `06a59fc`),
before any C1 code was written. Task C1 of [big-plan.md](big-plan.md) (after
L1-M, before L4); recommendation 3 of
[literature-2024-2026.md](literature-2024-2026.md) §5.1.

Status: **proposed** (this section). Results are appended below the
protocol when measured; nothing above "Measured result" changes after this
commit except through a dated, labelled amendment.

Status (2026-10-30): **implemented and measured**, no amendment. Q1: the
closure-TV map is reproducible and unrelated to the gain map ("distinct";
GNSS RFI and per-antenna weight scale). Q2: null; no closure-guided mask
is accepted and every call is null. Q3: closure outliers coincide with the
first-pass additions and the GNSS band. Details in "Measured result".

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

## Measured result (2026-10-30)

Code as committed in `e3311f5` (protocol `73a7c19`); no amendment, no code
change after the frozen run. Runs:

- `outputs/c1-20261030-00-precondition`: L1's precondition, unedited
  (9.9 s, 0.35 GB). K's precondition and the group check pass; L1's own
  replay flag is false on the image hashes only (P2), and L2's tolerant
  comparison is all equal.
- `outputs/c1-20261030-00-smoke-4` and `-00-smoke-12`: labelled smokes
  (22 s, 0.87 GB; 66 s, 1.34 GB). No bug was found; the 12-station smoke
  timed the kernel (0.54 s for traces). `-00-smoke-check` exercised the
  checker (criterion 2 fails on a station subset, as it must).
- `outputs/c1-20261030-01`: **the frozen run**, 19 min 48 s wall, 10.9 GB
  peak RSS (`time -v`), MemAvailable 27.5 GiB at start, load 1–2,
  `RAYON_NUM_THREADS=4`, `OPENBLAS_NUM_THREADS=1`. L1's part took
  707 s, the C1 part 481 s.
- `outputs/c1-20261030-02-check`: the checker (8.8 s). Archive:
  [results/c1-closure-arm.json](results/c1-closure-arm.json) (61.7 KB).

### Criteria

| Criterion | Measured | Result |
| --- | --- | --- |
| 1 comparator precondition | K's precondition and the group check pass; replay equal under the tolerant comparison | **pass** |
| 2 L1 reproduced | every compared non-image, non-timing field of the run's L1 arms equals L1's run `-01` (0 differences) | **pass** |
| 3 gates | captured base gains = `original` gains (SHA256); the closure loop's three α = 0 trials equal the TV loop's (mask hash, objective); kernel against NumPy on 80 samples per family: max relative difference 7.8e-8 (trace), 7.7e-8 (phase), 8.6e-8 (log amplitude), counts and NaN pattern equal | **pass** |
| 4 L1's criteria | 1, 5, 7 pass; 2, 3, 4, 6 fail exactly as in L1 and L1-M (the derived FLAG_ROW clause; the replay flag on image hashes; convergence 0.83 and invalid predictions; the undecidable frozen headline) | evaluated, as L1 |
| 5 Q1–Q3 decidable | all decidable; the frozen first-pass pairs are undecidable as in L1, and decidable under amendment 1 and the A1 drop | **pass** |
| 6 outputs and archive | `c1.json` beside L1's files; archive 61.7 KB, numbers and hashes only | **pass** |
| 7 Rust lint, tests, check-all | standalone crate: rustfmt clean, 5 Rust tests, clippy `-D warnings` clean; 21 targeted pytest; `bash tools/check-all.sh` overall PASS (701 passed, 5 skipped) | **pass** |

### Closure statistics on the whole array

Training cells only (27.4 M); 53 stations, 1,378 baselines.

| Family | Scored samples | Mean closures per sample (survival of N − 2) | Median R² | R median (q99, max) | z ≥ 3 / ≥ 5 / ≥ 8 |
| --- | ---: | ---: | ---: | --- | --- |
| trace (primary) | 90.6 % | 22.6 (44 %) | 0.080 | 0.283 (0.51, 1.26) | 136,037 / **918** / 0 |
| phase | 88.9 % | 18.4 (36 %) | 0.076 | 0.276 (0.53, 1.32) | 73,123 / 75 / 0 |
| log amplitude | 90.6 % | 22.6 (44 %) | 0.081 | 0.284 (0.50, 1.20) | 109,462 / 391 / 0 |

- Survival: re-routing keeps quadrangles at 44 % of N − 2 (the protocol
  estimated 41 % without re-routing); triangles, which are not re-routed,
  survive at 36 %, below the 51 % estimate, because the input FLAG also
  removes edges (34.2 M of 85.6 M cells are eligible).
- The weight scale: a per-sample median closure residual R of 0.28 and a
  median R² of 0.08 mean that σ² = 1/w overstates the closure noise
  several-fold, as the probe found (a median of medians is not the mean
  z², so 0.08 is not directly comparable with the probe's 0.17–0.18).
- **No closure is a gross outlier.** The largest per-sample R is 1.26 in
  units of the (overstated) propagated noise; the robust per-baseline z
  peaks at 6.8, and nothing reaches 8.

### Q1: the closure-TV map is reproducible and unrelated to the gain map ("distinct")

| Family | ρ_half (S-B) | ρ_half per antenna | ρ_bl | ρ_ant | ρ_chan | R²_bl | R²_add | Call |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| **trace** | **0.813** (0.897) | 0.889 | −0.103 | −0.009 | 0.224 | **0.0035** | 0.467 | **distinct** |
| phase | 0.859 (0.924) | 0.883 | −0.109 | −0.051 | 0.372 | 0.0059 | 0.516 | distinct |
| log amplitude | 0.795 (0.885) | 0.868 | −0.115 | −0.037 | 0.141 | 0.0063 | 0.461 | distinct |

657,404 baseline-bins compared (trace). The closure-TV map built from even
channels predicts the one built from odd channels (ρ = 0.81), so it is not
noise; the gain-TV guidance explains 0.35 % of its log-variance, and the
rank correlations with the gain map are near zero or slightly negative at
baseline and antenna level.

What the structure is:

- **Frequency.** The six frequency bins with the largest median closure TV
  are at 1164, 1190, 1217, 1230, 1237 and 1251 MHz (0.36–0.45 against a
  median of 0.29): the GNSS range of A1. The quietest are at 1465–1478 MHz
  (0.26).
- **Antennas.** About half of the map's log-variance (R²_add 0.47) is an
  antenna-additive pattern. A closure is blind to gains, so an
  antenna-additive pattern in normalised closure TV is per-antenna noise
  (the weights' per-antenna scale differs from the real noise), not gain
  structure. Per-antenna medians span 0.236–0.311.

So the frozen call "distinct" holds, with two explanations that are not
calibration signal: RFI in the GNSS band and per-antenna weight scale.

### Q2: no change to the decision; every call is null

**Closure-TV policy.** 148,227 candidate cells (fused-pass score ≥ 2, as
L1); 114,059 have a finite closure guidance; guidance scale 0.292.

| Trial | Mask cells | Objective | Accepted |
| --- | ---: | ---: | --- |
| base (`original`) | 0 | 1.25000 | — |
| α = 0, τ = 8 | 2 | 1.249782 | yes |
| α = 0, τ = 5 | 21 | **1.249740** | yes (selected) |
| α = 0, τ = 3 | 4,125 | 1.250666 | no |
| α = 1, τ = 8 / 5 / 3 | 624 / 32,778 / 115,522 | 1.249842 / 1.253250 / 1.261364 | no |
| α = 3, τ = 8 / 5 / 3 | 105,058 / 114,055 / 115,531 | 1.259949 / 1.260749 / 1.261365 | no |

All six closure-guided (α > 0) masks were admissible (validation within
1 %) and **none was accepted**: each has a higher objective than the
unguided τ = 5 mask, because the guidance adds flags (2 × flag fraction)
without lowering gain TV. The policy selects L1's unguided 21-cell mask,
so `closure-tv-policy` is `tv-policy` (same additions and gains; its image
metrics are reused).

**Closure-outlier arm.** 918 training cells (z ≥ 5; 0.0034 % of training,
well under the 2 % budget), solved (23 s) and imaged (15 s): MSE_test
0.2088877 against `original`'s 0.2088876, residual RMS 0.0164237 against
0.0164236, gain TV unchanged (0.026051).

Calls (MSE_test ratio and call; the residual RMS ratio from the frozen
images):

| Pair | Frozen | Amendment 1 (matched) | A1 drop | Residual RMS |
| --- | --- | --- | --- | --- |
| closure-tv-policy vs tricolour-firstpass | undecidable | 0.99943 null | 0.99943 null | 0.99542 null |
| closure-tv-policy vs original | 0.999998 null | 0.999998 null | 0.999998 null | 1.000000 null |
| closure-tv-policy vs tv-policy | 1 null | 1 null | 1 null | 1 null |
| closure-outlier vs tricolour-firstpass | undecidable | 0.99943 null | 0.99943 null | 0.99542 null |
| closure-outlier vs original | 1.000000 null | 1.000000 null | 1.000000 null | 1.000002 null |
| closure-outlier vs tv-policy | 1.000002 null | 1.000002 null | 1.000003 null | 1.000002 null |

- **A1 drop.** 691 first-pass and 325 mild emptied station-bins (A1's
  numbers), 726 in the union; 703 validation and 700 test samples are
  dropped from every arm. The first pass then predicts every remaining
  held-out sample, so the **matched fallback was not needed** and the
  first-pass pairs become decidable without the matched rule: null, as
  under amendment 1 (L1's own `tv-policy` against first pass under
  amendment 1 is 0.99943 too).
- **Positive by the protocol's definition: no.** No α > 0 mask was
  selected, and the outlier arm is not better than `original`.

### Q3: closure outliers sit where the first pass flags and in the GNSS band

| Set X (training cells) | \|X\| | trace M (918): \|M ∩ X\| / \|M\| | lift | coincides | phase set (75): \|M ∩ X\| / \|M\| | lift |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| tricolour-firstpass additions | 613,116 | 25.8 % | 11.5 | **yes** | 13.3 % | 6.0 (yes) |
| tricolour-mild additions | 299,575 | 5.9 % | 5.4 | no (< 10 %) | 4.0 % | 3.7 (no) |
| A1 emptied station-bins | 6,170 | 0 % | 0 | no | 0 % | 0 |
| GNSS range 1145.8–1301.0 MHz | 2,513,380 | 78.0 % | 8.5 | **yes** | 34.7 % | 3.8 (yes) |
| L1's residual candidates (fused score ≥ 2) | 148,227 | 33.6 % | 62 | **yes** | 50.7 % | 94 (yes) |
| tv-policy additions | 21 | 0 % | 0 | no | 0 % | 0 |

The trace and phase outlier sets share 10 cells. The closure outliers are
mostly GNSS-band cells (78 %), a quarter of them already flagged by the
first pass, and a third are cells L1's visibility-residual score already
proposes. None lies in A1's emptied bins, which the first pass had already
removed down to a residue.

### What this shows

- The gauge-free signal exists and is **not** what gain TV measures: the
  closure-TV map is reproducible (split-half 0.81) and the gain-TV map
  explains 0.35 % of it. Its structure is RFI in the GNSS band and
  per-antenna noise scale; neither is calibration structure.
- Used as guidance, it changes nothing: every closure-guided mask is
  rejected by the frozen objective, which rewards lower gain TV and
  charges for flags. Used directly as a flag mask (918 cells), it moves
  held-out MSE by 1.5e-7 and image residual RMS by 2e-6.
- Against the CARACal first pass, both closure arms are null under the
  matched rule and under A1's drop (0.99943), the same number as L1's TV
  policy: the 0.06 % comes from the first pass's own flags, not from the
  closure arms.
- The closure outliers that exist coincide with the first pass's flags
  and the GNSS band (lift 8–12), so the closure statistic re-finds RFI that
  Tricolour already handles, at about 6× the first pass's cost.

### What it does not show

- A closure statistic with correctly scaled weights. The weights overstate
  the noise several-fold (a QuartiCal product), and part of the "distinct"
  structure is per-antenna weight scale; the masks are scale-free (robust
  z per baseline), the maps are not.
- Other closure sets. Only the cyclic quadrangles (traces, log
  amplitudes) and all triangles (phases) were used, with the protocol's
  re-routing rule; not the construction of Kumar et al., and not checked
  against their text.
- Other policies. The objective is L1's; a closure-based objective (for
  example, minimising closure TV) was not pre-registered and was not run.
- A second calibrator. 1830−211 (L2) was not run with the closure arms.

### Cost (frozen run, four threads)

| Stage | Seconds |
| --- | ---: |
| kernel: trace / phase / log amplitude | 68.8 / 40.1 / 78.0 |
| NumPy gate (three families) | 0.3 |
| maps and Q1 (per family) | 2.9–3.0 |
| robust z and masks (per family) | 3.3–4.5 |
| A1 bins | 2.1 |
| closure-TV loop (9 solves) | 211.1 |
| closure-outlier solve / image | 23.2 / 15.5 |
| calls (6 pairs × 3 ways) | 18.2 |
| Q3 | 0.4 |
| closure chain (trace kernel + map + loop) | 283.0 |
| L1's TV chain (solve `original` + TV loop) | 240.2 |
| L1's first-pass Tricolour port | 45.3 |

The closure chain costs 1.18× the TV chain and 6.2× the first-pass port;
the trace kernel alone is 1.5× the port. The log-amplitude kernel is
slower than the trace kernel because it takes logarithms of eight
amplitudes per closure.

## For the coordinator

- **Shared files.** None edited. Added: `core/src/closure.rs`,
  `core/src/ffi_closure.rs`, `python/rangtoy/core_closure.py`,
  `python/rangtoy/core_campaign_closure.py`,
  `examples/{run,check,archive}_c1.py`, `tests/test_core_closure.py`
  (13 tests), `tests/test_core_campaign_closure.py` (8 tests), this report
  and `research/results/c1-closure-arm.json`.
- **`core/src/lib.rs`** (coordinator edit, additive, alphabetical):

      pub mod closure;
      pub mod ffi_closure;

  `closure.rs` uses `crate::jones` and rayon only; the C ABI is
  `rang_core_closure_scores(*const ClosureInputsC, *mut f32, *mut f32,
  *mut u16) -> i32` and `rang_core_closure_last_error(*mut u8, usize) ->
  usize`. Until then `core_closure.library()` builds the standalone crate
  `core/target/c1-standalone` (jones, closure, ffi_closure by path);
  `RANG_C1_LIB` selects a prebuilt library. After the merge,
  `core_closure.library()` should prefer the core library when it exports
  the symbols (as `core_wgridder.library()` does), and check-all's clippy
  and fmt will then cover the two files; until then they were checked on
  the standalone crate.
- **`STATE.md`**, new top entry:

  > C1 closure-invariant arm (big plan wave 3), 2026-10-30 (implemented;
  > measured; [c1-closure-arm.md](c1-closure-arm.md)). A Rust kernel
  > (`core/src/closure.rs`, standalone build until `lib.rs` lists it)
  > scores every training sample of LUNO 1934−638 chunk 0 (53 stations)
  > with closure traces (GL(2,C) invariant, Broderick & Pesce 2020; cyclic
  > quadrangles with re-routing around missing baselines), parallel-hand
  > closure phases and log closure amplitudes, normalised by noise from
  > WEIGHT_SPECTRUM; it matches a NumPy reference to 8.6e-8, and closure
  > traces are invariant under random 2×2 gains to 1e-10. L1's campaign
  > ran unedited (reproduced on every non-image field) with two added arms.
  > Q1: the closure-TV map is reproducible (split-half ρ 0.81) and
  > unrelated to the gain-TV map (R² 0.0035): "distinct", but its
  > structure is the GNSS band and per-antenna weight scale. Q2: every
  > closure-guided mask (α > 0) is rejected by the frozen objective; the
  > policy selects L1's 21-cell unguided mask; the 918-cell closure-outlier
  > arm moves MSE by 1.5e-7; against the CARACal first pass both arms are
  > null under amendment 1 and under A1's emptied-bin drop (0.99943,
  > decidable without the matched fallback). Q3: closure outliers coincide
  > with the first-pass additions (lift 11.5) and the GNSS range (78 %,
  > lift 8.5), not with A1's emptied bins. The closure chain costs 1.18×
  > the TV chain and 6.2× the first-pass port. Neither the
  > antenna-factorable (gain TV) nor the non-factorable (closure) statistic
  > improves on the first pass. Archive `results/c1-closure-arm.json`.

- **`README.md`**, one line: C1 adds a gauge-free closure kernel
  (closure traces, phases, log amplitudes; `rangtoy.core_closure`) and a
  closure-invariant comparator arm on L1's campaign
  (`rangtoy.core_campaign_closure`, `research/c1-closure-arm.md`):
  reproducible closure structure (GNSS RFI), but no change to the
  flagging decision.
- **`tool-timings.md`**: the rows of the timing table below.
- **`big-plan.md`**: C1 done 2026-10-30 (measured; Q2 null; Q1 "distinct",
  explained by GNSS RFI and weight scale; Q3 coincides with the first
  pass). L4 can be written.
- **What the L4 verdict can now say** (C1 is the last pre-registered arm
  before the verdict unless native data arrive):
  - on LUNO 1934−638, the TV policy, its closure-guided variant and a
    direct closure-outlier mask all make the same decision: no flag beyond
    L1's 21-cell unguided mask; every call against `original` and against
    the CARACal first pass is null (|1 − ratio| ≤ 0.06 %), now decidable
    under A1's drop as well as under amendment 1;
  - this holds under three calibrator models (L1-M) and for both an
    antenna-factorable (gain TV) and a gauge-free (closure) statistic;
  - the gauge-free statistic does see real non-factorable structure, but
    it is RFI in the GNSS band that Tricolour's first pass already targets
    (lift 11.5), plus per-antenna weight scale;
  - untested: a closure-based objective, a second calibrator with closure
    arms, correctly scaled weights.
- **Upstream observations** (observed, not raised):
  1. Non-RATT (SARAO, LUNO store; QuartiCal weights): WEIGHT_SPECTRUM
     overstates the visibility noise several-fold (χ² 0.21 here, closure
     z² 0.17–0.18 in the probe), and its per-antenna scale is uneven
     enough to give normalised closure TV an antenna-additive component
     (R² 0.47). Anyone using these weights as inverse variances (closure
     noise, χ² tests) needs a per-antenna rescale. Not a bug claim: the
     weight convention is not documented in the store.
  2. RATT, caracal-pipeline: CARACal's strategies have no closure-based
     flagging step; C1 found no reason to propose one at calibrator SNR on
     these data (the outliers are GNSS RFI the first pass already
     targets).
  3. RATT, Tricolour: nothing new.
- **Evidence to keep:** `outputs/c1-20261030-00-probes`,
  `-00-precondition`, `-01` (L1's files plus `c1.json`, the closure arms'
  gains and flags, images) and `-02-check`, with their logs.
- **Evidence that may be deleted:** the smokes `-00-smoke-4`,
  `-00-smoke-12` and `-00-smoke-check` (keep their logs), and
  `core/target/c1-standalone` once `lib.rs` lists the kernel.

## Timings (every tool run of this task)

| When (UTC) | Tool run | Wall | Peak RSS | Note |
| --- | --- | ---: | ---: | --- |
| 13:54 | `uv venv -p /usr/bin/python3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` (public PyPI) | 45.2 s | 0.93 GB | |
| 13:54 | `maturin develop --release --offline` | 0.3 s | 37 MB | already built |
| 13:55 | probe 1 (closure SNR and weight scale, stations 0–11), run twice (scratch, then archived) | 12.1 s; 12.9 s | 0.54 GB | |
| 14:00 | standalone crate: rustfmt, `cargo test`, clippy `-D warnings`, build | 9.0 s | 0.29 GB | one test assertion was wrong (wrap at ±π); fixed, rerun 3.0 s, 5 passed |
| 14:03 | `pytest tests/test_core_closure.py` | 3.6 s | 0.30 GB | the log-amplitude planted test needed diagonal gains (that family is only diagonal-invariant); then 13 passed |
| 14:08 | **L1 precondition** unedited (`-00-precondition`) | 9.9 s | 0.35 GB | replay false on image hashes only; tolerant comparison all equal |
| 14:12 | four-station smoke (`-00-smoke-4`, labelled) | 22.1 s | 0.87 GB | all paths ran |
| 14:12 | R²_add debug on the four-station data (scratch) | about 3 s | 0.3 GB | 0 at four stations is exact: complementary baselines share quadrangles |
| 14:13 | twelve-station smoke (`-00-smoke-12`, labelled) | 1 min 06 s | 1.34 GB | trace kernel 0.54 s, extrapolated 57 s for 53 stations (measured 69 s) |
| 14:15 | `check_c1.py` and `archive_c1.py` on the smoke (`-00-smoke-check`, labelled) | 3.1 s | 55 MB | criterion 2 fails on a subset, as it must; archive 57 KB |
| 14:15 | targeted pytest (both C1 test files) | 0.4 s | 0.3 GB | 21 passed |
| 14:16 | **frozen run `-01`** (`run_c1.py` under `time -v`; MemAvailable 27.5 GiB, load 1–2) | **19 min 48 s** | **10.9 GB** | exit 0; L1 part 707 s, C1 part 481 s |
| 14:37 | `check_c1.py` (`-02-check`) | 8.8 s | 0.21 GB | criteria 1–6 pass |
| 14:37 | `archive_c1.py` | 0.1 s | 40 MB | 61.7 KB |
| 14:40 | `bash tools/check-all.sh` (plain; it takes the host lock itself), once before the final commit (`outputs/c1-20261030-check-all.log`) | 4 min 18 s (pytest 701 passed, 5 skipped in 2 min 06 s) | 1.66 GB | **overall PASS** |
