# Verdict: gain-TV-guided flagging on MeerKAT L-band (closed: null)

Task L4 of [big-plan.md](big-plan.md), written 2026-10-30 on branch
`l4-verdict` from `46a319f`. Documents only: no new run. Every number below
comes from a committed archive under `research/results/`. The consolidated
table of every pre-registered call, with its ratio, its rule and the archive
path it comes from, is [flagging-verdict.json](results/flagging-verdict.json).
`examples/verdict_tables.py` rebuilds it from the campaign archives and checks
each archived call against its ratio.

**Verdict.** The evidence covers one MeerKAT L-band observation (two
calibrators, processed flags and weights) and a four-antenna pointing-scan
fixture. On it, gain-TV-guided flagging gives no measurable improvement in
calibration or imaging quality over the CARACal first-pass Tricolour
strategy, and it is not cheaper.

- Of the 90 pre-registered flagging calls, 64 are null and 26 undecidable.
  None is better and none is worse. The 90 are not independent: L1-M's
  stored run and C1 repeat L1, and the frozen and matched rules call the
  same pairs.
- The frozen policy never selected a TV-guided (α > 0) mask: on the fixture
  pilot and in every LUNO campaign the objective rejected each one. The only
  accepted non-empty fixture mask came from a later ranking search on an
  injected case, where the TV and residual rankings chose the same 56 cells
  (test MSE ratio 0.99994, null).
- On the parallel kernels the TV chain costs 4.6–5.9 times the first pass.

The experiment is closed as null, within the scope stated in section 8.

## 1. The hypothesis, and what a positive would have looked like

**Frozen on 2026-09-23** ([flagging.md](flagging.md); the experiment started
from the clean revision `39eeb53`, and the strategy and pilot were committed
as `35e763b`).

- **Inputs.** Full-Jones gains are solved per 2 integrations × 32 channels
  (QuartiCal `G.type=complex`). Their anisotropic Frobenius total variation
  (TV) in time and frequency, after fixing the common unitary gauge on a
  reference antenna, is mapped per antenna, time bin and frequency bin.
- **Hypothesis.** Where the gains are rough, the data are more likely to be
  bad, so the TV map should guide extra flags.
- **Policy.**
  - A training sample is proposed when its robust residual score z ≥ 2 and
    `z [1 + α min(h/median h, 5)] > τ`, with h the TV guidance and τ ∈
    {8, 5, 3}, α ∈ {0, 1, 3}.
  - At most 2 % of training samples are added. Original flags are an
    immutable lower bound.
  - α = 0 is the unguided ablation.
- **Selection.** Each candidate mask is re-solved and scored by
  `L = TV(F)/TV(F0) + 2f + 0.25 MSE_val(F)/MSE_val(F0)`, with the TV
  measured on a fixed edge support and f the added fraction. A candidate is
  admissible only if `MSE_val ≤ 1.01 MSE_val(F0)`. No change scores exactly
  1.25 and is always available.

`flagging.md` states no positive criterion. Read from the frozen rule, **a
positive** is a mask with α > 0 that the objective accepts (L < 1.25) and
that beats the best unguided mask.

**The decision rule was frozen later, per campaign, before each run.**

- **K** (protocol `c1aa882`) froze the three-way call used ever since. On
  the fixed test cells of the seed-7 split, a candidate is *better* if
  `MSE_test(candidate) ≤ 0.99 MSE_test(reference)`, *worse* if ≥ 1.01,
  *null* otherwise. The same call is made on the point-source residual RMS
  of a dirty image.
- **The headline pair** is the TV policy against the CARACal first pass, with
  a cost clause: the TV chain may take at most three times the wall of the
  first-pass port on the same cells.
- **The novelty rule** in [AGENTS.md](../AGENTS.md) needs higher quality at
  comparable cost, or comparable quality at materially lower cost, against a
  relevant state-of-the-art method.
- **A positive** was therefore a *better* headline with the cost clause met.
  The alternative route was a null headline at a cost ratio well below one.

Later layers, each committed before the run it governs:

| Rule | Commit | Added |
| --- | --- | --- |
| L1 amendment 1 | `e6e0d07` | matched-sample calls: MSE on held-out samples both arms predict, when the comparator leaves some unpredictable |
| L2 verdict rule | `ee74d6c` | positive only if *better* under both model arms, no residual-RMS call *worse*, cost comparable |
| A1 drop | C1 protocol `73a7c19` | drop the held-out samples of station-bins the Tricolour strategies empty, computed after the split and before any solve ([a1-rfi-audit.md](a1-rfi-audit.md)) |

## 2. The data

**The real data: LUNO.** `LBAND_LUNO_CALIBRATORS.zarr` in the anonymous RATT
bucket (`ratt-public-data`, af-south-1). Its metadata
([flagging-luno-candidate.md](flagging-luno-candidate.md)) identify it:

- a 2021-08-18 MeerKAT L-band Moon observation, schedule block
  `20210818-0008`, observer B. Hugo;
- calibrated in CASA 5.6 in 2022 and published as AfriCalim 2024 workshop
  data;
- 56 antennas and 4,096 channels over 856–1712 MHz, 8 s integrations.

The campaigns used channels 1024–3071 (1070.0–1497.8 MHz) of row chunk 0 of
two calibrator scans:

| Scan | Rows used | Baselines | Integrations | Originally flagged |
| --- | ---: | ---: | ---: | ---: |
| PKS 1934−638, `MAIN_1`, scan 2: four stations (K) | 192 | 6 | 32 | 70.10 % |
| PKS 1934−638: whole array (L1, L1-M, C1) | 41,786 | 1,378 (53 stations) | 32 | 59.99 % |
| PKS 1830−211, `MAIN_2`, scan 3, whole scan (L2) | 15,400 | 1,540 (56 stations) | 10 | 46.57 % |

**What was processed, not native.** Every LUNO number is conditional on
these.

- **FLAG** carries the 2022 processing: CASA `applycal` with `calflag`,
  manual band-edge flags, and whatever the processing removed. On the GNSS
  carrier blocks the input FLAG already covers 97–100 % of cells (A1).
- **WEIGHT_SPECTRUM** is a QuartiCal product. The observer said so on
  2026-10-29 at 15:37 SAST: "weight spectrum would have been modified by
  quartical".
  - The weights overstate the visibility noise. L1's training χ² is 0.208,
    and the C1 probe's closure z² is 0.17–0.18.
  - SIGMA_SPECTRUM does not match the DATA scatter either (scaled MAD
    0.09–0.20).
- **MODEL_DATA has no logged origin.**
  - For 1934−638 it is a field model: CARACal's lsm compact sources at
    coefficients near 1, more extended flux, A0 2.1″ from the phase centre
    (L1-M).
  - For 1830−211 it is offset, a few per cent resolved, with 1e-3 cross-hand
    terms (L2).
- **Native data were never received.** The observer offered a
  full-resolution dataset ("I can make a full resolution dataset available
  to you", 15:38 SAST). The user asked for L-band with the original FLAG,
  WEIGHT_SPECTRUM and SIGMA_SPECTRUM. Nothing has arrived, so L3 (the native
  campaign) did not run.

**The fixture.** The fixture era (2026-09-23 to 09-24) used scan 9 of the
official SKA pointing-offset archive `outer_scans.zip` (SHA256 `d4dae56f…`):

- four antennas, 140 rows, 4,096 channels, the same 1070–1498 MHz window;
- a real MeerKAT L-band reference-pointing scan with its published flags;
- not a science-field benchmark.

**Licence and acknowledgement.** The user settled the licence on 2026-10-30
([big-plan.md](big-plan.md)). The basis is the observer's permission, Ben
Hugo, 2026-10-29 15:36 SAST: "you can use it. Just cite the Sarao data usage
acknowledgement". Results are not provisional on that account. No visibility
is committed or redistributed. The wording recorded in the repository, to be
checked against SARAO's data policy before publication, is:

> The MeerKAT telescope is operated by the South African Radio Astronomy
> Observatory, which is a facility of the National Research Foundation, an
> agency of the Department of Science and Innovation.

## 3. The method

Every LUNO campaign ran in one process on the Rust core: no Measurement Set,
QuartiCal, Tricolour or WSClean in the loop. Every component was checked
against the tool it replaces before it was used.

- **Solver.** The core's port of QuartiCal 0.2.7's `complex` term
  ([core-phase2.md](core-phase2.md), all eight criteria pass). On the LUNO
  four-station slice K's precondition reproduces QuartiCal's archived gain
  flags exactly, its baseline gain products to 5.6e-16, and its converged
  fraction (0.9833234067897558). Settings throughout: 2 integrations × 32
  channels, 50 iterations, convergence 1e-7, stop fraction 0.99, reference
  antenna m000; held-out cells are excluded and predicted afterwards.
- **The seed-7 split.** Eligible cells (unflagged in every correlation,
  positive weights, finite data and model) split 80/10/10 into training,
  validation and test, grouped by gain bin × baseline, with two training
  cells reserved per group. Every arm of a campaign shares the split, so
  validation and test cells are identical across arms. Validation is used
  only inside the selection objective. Test is used only for the call.
- **TV map and policy.** Exactly the 2026-09-23 objective above, one round,
  nine masks, each distinct mask re-solved. One loop starts from the
  `original` solve (`tv-policy`), one from the first-pass solve
  (`tricolour-firstpass+tv`: does TV add anything on top of the
  comparator?).
- **Metrics.** Held-out weighted MSE, the mean over cells of the
  correlation-mean `w|r|²` (an invalid prediction makes it unavailable,
  never silently dropped); training χ²; fixed-support gain TV; and a
  Briggs-0.5 dirty image of the corrected Stokes I with its point-source
  residual RMS, `dirty − peak × PSF`.
- **Amendment 1.** On the whole array the first pass removes every training
  sample of some station-bins. The solver then flags those gains, and the
  held-out samples there cannot be predicted, so the frozen headline is
  undecidable. Amendment 1 calls each pair on the held-out samples both
  arms predict (678 of 3,418,059 test samples dropped on 1934−638; 63 and 67
  of 1,686,125 on 1830−211).
- **The A1 drop.** A1 showed the emptied station-bins are GNSS-band residue
  (section 5.4). C1 pre-registered dropping their held-out samples from
  every arm (703 validation and 700 test samples, from 726 bins in the
  union of the two Tricolour strategies). Under that rule the first-pass
  pairs become decidable without the matched fallback.

## 4. The comparators

**CARACal's calibrator flagging, ported** ([core-d-tricolour.md](core-d-tricolour.md)).

- The arms are the first-pass strategy
  `mk_rfi_flagging_calibrator_fields_firstpass.yaml` (the state-of-the-art
  comparator) and `calibrator_mild_flagging.yaml` (a milder control), from
  CARACal master `8f7bb363`, run through the core's port of Tricolour
  0.2.1's executor with the two shipped static masks.
- Task D verified the port against Tricolour 0.2.1 on four controls: final
  flags identical (2,293,760 elements each) and all 44 per-step window
  arrays identical to the oracle's. Every campaign checks that its output is
  a superset of its input, uniform over correlations and monotone over the
  `or`-accumulated steps (criterion 5, pass everywhere).
- Additions are taken on training cells only, so the comparator never
  touches the held-out cells.

**CASA/CARACal cross-calibration** ([o-casa.md](o-casa.md)). CARACal's own
cross-calibration is CASA (`setjy`, `gaincal` K and G, `bandpass`,
`applycal`), not QuartiCal. O-CASA ran it on the K four-station slice in a
pinned CASA 6.7.6 image.

- **CARACal's defaults do not run on four core stations.** The automatic
  reference antenna is empty, because all baselines are under its 150 m
  `minbase`, and `gaincal` K stops.
- **The smallest deviation that solves** needs three changes: `refant` set by
  hand, `minblperant=3`, and no `uvrange` cut. Arms D, E and F show each is
  necessary.
- **The matched comparison** is arm SH (stored model, seed-7 held-out cells
  flagged while solving):

| | Held-out MSE_test, parallel hands | Cross hands | All |
| --- | ---: | ---: | ---: |
| core QuartiCal port (K `original`) | 0.229422 | 0.322596 | 0.276009 |
| CASA K·G·B as CARACal issues it (arm SH) | 0.252925 (×1.10) | 0.510050 | 0.381487 (×1.38) |

The parallel-hand number is the matched one. CARACal's crosscal has no
leakage term by design, so its cross-hand prediction is zero. This is a
calibration baseline on four stations only, not a flagging arm.

**CASA flagging.** On the same four-station slice, `flagdata` only:

- tfcrop with CARACal's flag-worker defaults flags 1,756 new cells (1.49 %
  of unflagged cells);
- rflag with CASA defaults flags 170 (0.14 %).

CARACal ships no rflag settings. For comparison, the first-pass port added
128 training cells there. Neither CASA mode was solved or scored on
held-out error: they are flag fractions, not calls.

**AOFlagger** was not run as a comparator. The literature scan (§2.1) found
its only algorithmic gap to the Tricolour port to be the Apertif strategy's
invalid-range handling and rank operator.

## 5. Results

Ratios are candidate / reference. Calls use the ±1 % band. "Matched" is
amendment 1, with dropped test samples in brackets. Every row is in
`flagging-verdict.json` with its archive path.

### 5.0 The fixture era (2026-09-23 to 09-24)

Scan 9, four antennas, run through QuartiCal itself
([flagging.md](flagging.md), [flagging-parallel.md](flagging-parallel.md),
[flagging-caracal.md](flagging-caracal.md)).

- **Pilot** (`results/gain-tv-flagging.json`, `final_whitened_reserved`).
  - Baseline gauge-fixed TV 0.14743687; validation MSE 25.20612; test MSE
    24.91961.
  - Five distinct non-empty proposals all raised TV (0.1480733–0.1535371).
  - No addition was selected.
- **Four parallel workstreams** (`results/gain-tv-parallel.json`):
  - on six seeded injections the TV policy selected no change in every
    case, although removing the injected cells helped the objective on the
    strong time burst;
  - genuine QuartiCal-MAD and Tricolour SumThreshold proposals sometimes
    lowered TV while worsening held-out prediction;
  - a learned patch-action predictor did not beat its constant control.

  So lower gain TV is not consistently better held-out prediction, and the
  learned policies select no extra flags.
- **CARACal's shipped strategies on the fixture**
  (`results/gain-tv-caracal.json`).
  - The first pass added 36.2 % of training samples and failed every guard:
    TV support lost, budget exceeded, validation unavailable.
  - Mild added 0.90–1.00 % and scored objectives 1.2702 and 1.2762, above
    no change.
- **The one accepted non-empty mask** was on an injected case
  (`results/gain-tv-next-prospective.json`, case `time-burst-seed109`).
  - A 56-cell mask reached objective 1.24957, with test MSE 25.03525 against
    25.03684 (ratio 0.99994, null under the later rule).
  - It recovered 9.4 % of the injected cells.
  - The TV ranking chose the same mask as the residual ranking (and the
    detrended one), so TV guidance added nothing over the residual score.
  - The signal guard abstained ([flagging-next-summary.md](flagging-next-summary.md)).

  It is not a positive.

### 5.1 K: PKS 1934−638, four stations ([core-k-luno-campaign.md](core-k-luno-campaign.md))

The split was 94,047 training, 11,742 validation and 11,767 test cells.
Original test MSE 0.2760093. First pass: 128 training additions (0.136 %).
Mild: 10. The TV policy selected no change: the 4 distinct guided masks
scored 1.2535 and above against 1.25.

| Pair | MSE_test | Call | Residual RMS | Call |
| --- | ---: | --- | ---: | --- |
| tv-policy vs tricolour-firstpass (headline) | 0.999939 | null | 0.999958 | null |
| tv-policy vs original | 1.000000 | null | 1.000000 | null |
| tricolour-firstpass+tv vs tricolour-firstpass | 1.000000 | null | 1.000000 | null |

Cost: 2.00 s against 1.54 s, ratio 1.30 (comparable). Criteria 1–7 pass as
frozen. Six baselines make the dirty image sidelobe-dominated, so only the
residual RMS is interpretable.

### 5.2 L1: PKS 1934−638, whole array ([luno-array-campaign.md](luno-array-campaign.md))

The split was 27,401,558 / 3,419,206 / 3,418,059.

- First pass: 613,116 training additions (2.24 %). Mild: 299,575 (1.09 %).
- The TV policy selected the unguided τ = 5, α = 0 mask of 21 cells. All six
  guided masks (8,422–147,850 cells) scored 1.2543–1.2759 and were
  rejected.
- The `original` test MSE is 0.2088876; on its valid samples the first
  pass's is 0.2089681.

| Pair | Frozen MSE_test | Residual RMS | Matched MSE_test |
| --- | --- | --- | --- |
| tv-policy vs tricolour-firstpass (headline) | undecidable | 0.995419, null | **0.999426, null** (678) |
| tv-policy vs original | 0.999998, null | 1.000000, null | 0.999998, null |
| tricolour-firstpass+tv vs tricolour-firstpass | undecidable (arm unavailable) | undecidable | undecidable |
| tricolour-firstpass+tv-a1 vs tricolour-firstpass | – | – | 1.000000, null (678); no change selected |

Criteria 2, 4 and 6 fail as frozen.

- 2: the derived row flag covers 571 rows that the input FLAG already
  flags completely.
- 4: the converged fraction is 0.833 at the cap, and the Tricolour arms
  have invalid predictions.
- 6: the headline is undecidable.

Cost: 1,416 s against 764 s, ratio 1.85 (comparable), on single-threaded
kernels on a contended host.

### 5.3 L2: PKS 1830−211, whole array, two models ([luno-1830-campaign.md](luno-1830-campaign.md))

The split was 13,480,057 / 1,683,974 / 1,686,125, hash-identical under both
model arms. First pass: 181,109 additions (1.34 %), identical under both
models.

| Model | Pair | Frozen MSE_test | Residual RMS | Matched MSE_test |
| --- | --- | --- | --- | --- |
| stored | tv-policy vs tricolour-firstpass (headline) | undecidable | 0.998345, null | **0.999770, null** (63) |
| stored | tv-policy vs original | 0.999995, null | 1.000041, null | 0.999995, null |
| stored | tricolour-firstpass+tv-a1 vs tricolour-firstpass | – | – | 1.000000, null (63) |
| scalar | tv-policy vs tricolour-firstpass (headline) | undecidable | 0.998158, null | **0.999691, null** (67) |
| scalar | tv-policy vs original | 1.000000, null | 1.000000, null | 1.000000, null |
| scalar | tricolour-firstpass+tv-a1 vs tricolour-firstpass | – | – | 1.000000, null (67) |

The frozen `tricolour-firstpass+tv` arm is unavailable under both models.

**The policy.**

- Stored model: the unguided τ = 5 mask of 2,302 cells. Every guided mask
  was inadmissible.
- Scalar model: no change. The guided masks were admissible but scored
  1.287–1.331.

**Convergence** at the cap: 5.2 % of gains passed the convergence test under
the stored model (its 1e-3 cross-hand terms leave the U(2) directions weakly
fixed), and 93.7 % under the scalar.

**The L2 verdict by its pre-registered rule: null** under both models.

**Cost: not comparable.** Ratios 4.63 (stored) and 5.92 (scalar) against the
limit of 3, on the parallel kernels at load average 46–97.

### 5.4 Cross-cutting findings

**Model completeness (L1-M, [l1-model-completeness.md](l1-model-completeness.md)).**
L1's campaign ran unedited under three 1934−638 models: the stored
MODEL_DATA; the lsm's A0 alone; and all 196 components of CARACal's
`pks1934-638.lsm`, predicted by the core without a beam, as CARACal's own
simulator call does.

| Comparison (`original` arm) | MSE_test ratio | Call | Fixed-support TV ratio | Call |
| --- | ---: | --- | ---: | --- |
| field vs stored (primary) | 1.030769 | worse | 1.006901 | null |
| field vs point (Heywood's question) | 0.980594 | better | 0.992829 | null |

- The stored model fits best. The point model is 4.9 % worse than it
  (0.2195760 against 0.2088876).
- The field model's gain over the point is largest under 200 m (0.962) and
  at the bottom of the band.
- The flagging decision did not move. The matched headline is 0.999426,
  0.999401 and 0.999421 (stored, point, field), all null, and the policy
  chose the unguided τ = 5 mask (21, 30 and 18 cells) under every model.

**The calibrator model is not why the experiment is null**, and model
error goes mostly to the residual, not to the gains.

**Closure structure (C1, [c1-closure-arm.md](c1-closure-arm.md)).** Closure
traces are invariant under every per-antenna 2×2 gain (Broderick and Pesce
2020), so they see only what gain TV cannot.

- **Q1.** The closure-TV map is reproducible: split-half ρ 0.813, against a
  post-hoc noise-only null of 0.37. The gain-TV map explains 0.35 % of its
  log-variance (R² 0.0035): the call is "distinct".
  - Its structure is the GNSS band. The six roughest frequency bins lie at
    1164–1251 MHz.
  - About half of it (R²_add 0.467, against 0.149 on the null) is an
    antenna-additive pattern. That pattern is consistent with per-antenna
    weight scale, but it was not separated from closure survival or RFI
    exposure.
- **Q2.** Used as guidance, the closure map changed nothing. All six
  closure-guided masks were admissible and none was accepted. Used directly
  as a 918-cell outlier mask, it moved held-out MSE by 1.5e-7.

| Pair | Frozen | Matched (678) | A1 drop (700) | Residual RMS |
| --- | --- | --- | --- | --- |
| closure-tv-policy vs tricolour-firstpass | undecidable | 0.999426, null | 0.999429, null | 0.995419, null |
| closure-tv-policy vs original | 0.999998, null | 0.999998, null | 0.999998, null | 1.000000, null |
| closure-outlier vs tricolour-firstpass | undecidable | 0.999428, null | 0.999432, null | 0.995421, null |
| closure-outlier vs original | 1.000000, null | 1.000000, null | 1.000000, null | 1.000002, null |

- **Q3.** The closure outliers coincide with the first-pass additions (lift
  11.5) and the GNSS range (78 % of them, lift 8.5). The closure statistic
  re-finds RFI that Tricolour already removes.

**Convergence (L5, [l5-solver-science.md](l5-solver-science.md)).**

- The 50-iteration cap ends the whole-array solve with 83.3 % of gains
  converged. The held-out error is within 1e-4 of a 300-iteration solve by
  iteration 12–16.
- Safeguarded Anderson acceleration (m = 3) converges the array to the 0.99
  criterion in 65 iterations (converged fraction 0.9906).
  - Test loss 0.2088875 against 0.2088876: −6.1e-7 relative.
  - Gain TV 0.026174 against 0.026051: +0.47 %.
- The issue 452 weight fix changes no held-out error (|Δ| ≤ 8e-9).
- No default changed. The flagging loop was **not** rerun on converged
  gains.

**The GNSS bins (A1, [a1-rfi-audit.md](a1-rfi-audit.md)).** The station-bins
the first pass empties are exactly the campaigns' unpredictable bins: 691 on
1934−638 and 122 on 1830−211.

- 682 of 691 and all 122 lie on GNSS carriers: 1176, 1207, 1268 and
  1279 MHz. None lies in 1304–1498 MHz.
- The input FLAG had already removed 99.6 % and 99.8 % of their cells. The
  first pass cuts a long-baseline residue, a median of 5 training samples
  per bin.
- Mild and a mask-free first pass empty the same blocks. The strategy also
  flags 1,542 of 1,553 (L1) and 149 of 151 (L2) held-out cells in those
  bins.
- This is RFI excision as intended. A method should get no credit for
  keeping these bins, and the undecidable frozen headlines are a property
  of the GNSS band, not of the comparator.

**Scale of the effects.**

- The largest difference any flagging arm made against the first pass is
  0.06 % in held-out MSE (0.999426) and 0.5 % in residual RMS (0.995419) on
  the stored model; 0.6 % over every decidable call, the largest being L1-M's
  point and field models (0.994095; corrected 2026-10-30 from notebook 06's
  generated summary, no call changes).
  Both are inside the ±1 % band.
- Calibration choices on the same data move held-out error thirty times
  more or more:
  - the calibrator model, 1.9–4.9 % (L1-M);
  - the solver chain and solution interval, 10 % on the parallel hands
    (O-CASA);
  - the model arm on 1830−211, 38 % (descriptive, L2).

## 6. Cost

The cost clause, as archived (`cost_clause` in each archive; C1's row is
derived from its `l1_stages`):

| Run | Kernels, host | TV chain (s) | First pass (s) | Ratio | Clause |
| --- | --- | ---: | ---: | ---: | --- |
| K | single-threaded | 2.0 | 1.5 | 1.30 | comparable |
| L1 | single-threaded, load 28 | 1,416.0 | 763.5 | 1.85 | comparable |
| L2 stored / scalar | parallel, load 46–97 | 205.3 / 325.4 | 44.4 / 55.0 | 4.63 / 5.92 | fails |
| L1-M stored / point / field | parallel, 4 threads, load 3–7 | 283.0 / 241.0 / 247.8 | 50.0 / 47.5 / 44.7 | 5.66 / 5.07 / 5.55 | fails |
| C1's rerun of L1 | parallel, 4 threads, load 1–2 | 240.2 | 45.3 | 5.30 | fails |

**Why the ratio flipped.**

- The TV chain is a reference solve plus one re-solve per distinct
  candidate mask: nine on 1934−638.
- Task P3 made the Tricolour port parallel over baselines. The first pass
  now takes about 45 s (C1, idle host), against 764 s in L1's
  single-threaded run on a contended host.
- P1 parallelised each solve, but the chain still needs about ten of them
  plus serial Python stages.
- On single-threaded kernels the clause passed. On the current kernels it
  fails by a factor of about two.

**What the kernels cost now.** One whole-array 1934−638 campaign took 707 s
wall on an idle host at four threads (C1's `l1_stages`), against 7,659 s in
L1's frozen run. Per stage:

| Stage | Seconds |
| --- | ---: |
| decode | 4.8 |
| split | 21.2 |
| one solve | 24.6–28.9 |
| Tricolour first pass / mild | 45.3 / 29.8 |
| TV loop | 211.3 |
| one image | 12.2–13.3 |

The closure chain cost 283 s, 1.18× the TV chain and 6.24× the first pass.

**Neither novelty route is open.** Quality is null, so the first route fails.
The TV chain is two to six times more expensive than the first pass, so the
second route (same quality at lower cost) fails too.

## 7. What would still change the answer

Each item gives what supports reopening, what argues against, and what
would test it. Literature items were read at abstract level
([literature-2024-2026.md](literature-2024-2026.md), [abs]).

**7.1 Native flags and weights: the observer's offer (L3).**

- **For.** All LUNO inputs are processed: 46.6–70.1 % of cells were flagged
  before either method started, including 97–100 % of the GNSS carrier
  blocks, and the first pass found only 0.14–2.24 % of training samples to
  add. The weights, on which the objective and the residual scores are
  built, are QuartiCal products. A method that finds bad data has most to
  find in raw data.
- **Against.** The fixture carried its published flags and was null in the
  same way. Where the first pass did find 613,116 cells to flag (L1), every
  TV-guided mask was still rejected.
- **Test.** The frozen campaign, unchanged, on the observer's full-resolution
  L-band set with native FLAG, WEIGHT and SIGMA. This is the first
  reopening item.

**7.2 Correctly scaled weights.**

- **For.** σ² = 1/w overstates the noise about 5.6-fold (C1 probe; L1 χ²
  0.208). Half of the closure-TV structure is antenna-additive (R²_add 0.467
  against 0.149 on noise), which fits an uneven per-antenna weight scale.
  The whitened residual scores and the held-out MSE use these weights.
- **Against.** A global scale cancels in every ratio and in the robust
  per-baseline z. The antenna-additive part was not separated from closure
  survival or RFI exposure.
- **Test.** A frozen protocol that estimates per-antenna noise from the data,
  or from native SIGMA_SPECTRUM after a numeric check, and reruns L1.

**7.3 A converged solver (L5).**

- **For.** At the cap, 16.7 % of gains on 1934−638 and 94.8 % on 1830−211
  (stored model) have not passed the convergence test, so part of their TV
  may be iteration noise. Anderson m = 3 converges the array at the same
  held-out error.
- **Against.** Held-out error has settled to 1e-4 by iteration 12–16, and
  converging moves gain TV by +0.47 %, inside the band. Under the scalar
  model on 1830−211 (93.7 % converged) the result was the same null.
- **Test.** Rerun L1 and L2 (stored) with
  `RANG_SOLVE_OPTIONS=qp_weights=transposed,anderson=3` and a cap of about
  70. Not done.

**7.4 Solution interval and regularisation.**

- **For.** Mbou Sob et al. (2021, arXiv:2103.12508) show that the solution
  interval trades noise fitting against gain variability, depending on SNR,
  model incompleteness and RFI, and call for regularised calibration
  instead: the TV of a 2 × 32 solution mixes noise fitting and model error,
  neither of which is RFI. Brackenhoff et al. (2025, arXiv:2504.02483) find
  smooth spectral constraints fail near beam nulls and weight them by the
  station's expected response. O-CASA measured an interval effect directly:
  CASA's 120 s × full-band G with per-channel B is 10 % worse on held-out
  parallel hands than 2 × 32 full-Jones bins.
- **Against.** These are reasons TV may be the wrong guide for flags, not
  evidence that another interval would make TV-guided flagging positive.
- **Test.** What the literature points to is a TV-*regularised* solve, a
  calibration method rather than a flagger. That, or a held-out comparison
  of interval choices, is a new protocol, not a reopening of this one.

**7.5 Model completeness: tested, closed.** Heywood et al. (2020,
arXiv:2004.00454) show a point model of 1934−638 imparts 0.2–0.5 %
structured amplitude errors at MeerKAT. The literature scan's premise that
K and L1 solved against a point model was wrong. L1-M measured the effect:
the field model beats the point by 1.9 % in held-out MSE, the stored model
beats both, and the TV decisions are unchanged. Still open: a beam-applied
model, with the beam rotating with parallactic angle. That belongs to B1.

**7.6 A closure-based objective.**

- **For.** C1 showed a reproducible gauge-free signal that gain TV does not
  see (R² 0.0035). C1 used L1's objective, which rewards lower *gain* TV, so
  a closure-guided mask could not win on it even if it removed real bad
  data. Kumar, Nityananda and Samuel (2024, arXiv:2407.00583) extend the
  invariants to incomplete graphs, so they stay usable with flags; C1's
  re-routing rule was not checked against their construction.
- **Against.** The closure outliers are GNSS RFI that the first pass already
  targets (lift 11.5), and the 918-cell outlier mask moved MSE by 1.5e-7.
- **Test.** Not pre-registered and not run: an objective that minimises
  closure TV or closure residuals under the same held-out rule.

**7.7 A target field rather than a calibrator.**

- **For.** Every LUNO test used a bright calibrator with a known model,
  where the residual is noise-dominated and the processing had already
  cleaned the data. Flagging matters most for faint emission, and the
  fixture-era imaging controls showed that sky completeness dominates signal
  absorption: known-source response 49–78 % with omitted sky against
  98.6–99.7 % with complete sky (`results/gain-tv-next-imaging.json`,
  `conditional_response_vs_fixedG0`).
- **Against.** The LUNO target store is the Moon, and its FIELD direction
  does not track it (44′ to 149′ off over the track). It is not a usable
  science target as stored, and no target-field run exists.
- **Test.** A science field with an independent signal-recovery check (B1's
  data, or a native set), with an image-domain fidelity metric in place of
  the held-out rule.

**7.8 A different telescope or band.** The RFI environment differs by band
(UHF holds GSM below 960 MHz, outside this window), and Brackenhoff's
constraints were developed on LOFAR-HBA. There is no evidence here either
way. The project's scope ([meerkat-scope.md](meerkat-scope.md)) is MeerKAT
L-band, and the drivers reject UHF and S-band, so this is out of scope.

## 8. The verdict in plain words, and what comes next

We asked whether the roughness of calibration gains in time and frequency
can tell a flagger where the bad data are.

- **Fixture.** On a four-antenna MeerKAT pointing scan, the frozen policy
  never selected a flag. A later ranking search accepted one 56-cell mask
  on an artificially injected burst, but the residual ranking chose the same
  mask, so TV added nothing, and the held-out change was null (0.99994).
- **Real data.** On the public LUNO observation (both calibrators, four
  stations and the whole array, three calibrator models for 1934−638 and
  two for 1830−211, an antenna-gain statistic and a gauge-free closure
  statistic) the result is the same:
  - the frozen objective rejected every TV-guided (α > 0) mask;
  - against CARACal's first-pass Tricolour flags, held-out error and image
    residuals agree within 0.06 % and 0.6 %;
  - on the current kernels the TV method costs two to six times as much.

**Gain-TV-guided flagging is closed as null. It is neither better nor
cheaper than the state of the art on these data.**

The negative result does *not* cover native, unprocessed flags and weights
(section 7.1), a target field, another observation, band or telescope, or a
closure-based or TV-regularised objective. The first would reopen this
experiment; the others would be new experiments.

**What the project does next: B1.** Per [big-plan.md](big-plan.md), the
original research question: can small pointing and beam corrections be
constrained on LUNO's calibrator and target scans, selected by
distinguishability from the sky, without distorting faint emission?

- B1-0 freezes SARAO's 2023 holography cubes (DOI 10.48479/wdb0-h061) as the
  reference beam, with katbeam as a control.
- B1-1 freezes the SARAO/SKA Gaussian pointing-offset fit and physical
  pointing self-calibration as the baselines to beat at matched cost.
- The model-completeness and beam items above (7.5, 7.7) carry over into B1.
- L3 stays open as a standing item: when the observer's native set arrives,
  the frozen campaign runs on it unchanged.

## 9. Reproduction

**Rebuild the consolidated table** from the committed archives (stdlib only,
no data):

```sh
.venv/bin/python examples/verdict_tables.py           # print the tables
.venv/bin/python examples/verdict_tables.py --check   # committed JSON is current
```

**Archives and runs.** Each campaign archive records its run directory,
receipts and the SHA256 of its `result.json`. The run directories live under
the ignored `outputs/`.

| Campaign | Archive | Frozen run(s) | Commands (each script's docstring has the arguments) |
| --- | --- | --- | --- |
| Fixture | `gain-tv-flagging.json`, `gain-tv-parallel.json`, `gain-tv-caracal.json`, `gain-tv-next-prospective.json` | `outputs/tv-flagging-pilot-06`, `outputs/tv-flagging-parallel-01` | `history/` recipes (Stimela2, QuartiCal 0.2.x container); see `history/README.md` |
| K | `core-k-luno-campaign.json` | `outputs/core-k-20261030-01` | `examples/precondition_luno_campaign.py`, `run_luno_campaign.py`, `check_luno_campaign.py`, `archive_luno_campaign.py` |
| L1 | `luno-array-campaign.json` | `outputs/luno-array-campaign-20261030-01` | `examples/precondition_luno_array.py`, `run_luno_array.py`, `check_luno_array.py`, `archive_luno_array.py` |
| L2 | `luno-1830-campaign.json` | `outputs/l2-1830-20261030-02-{stored,scalar}`, fetch `-01-fetch` | `examples/fetch_luno_1830.py`, `precondition_luno_1830.py`, `run_luno_1830.py --model {stored,scalar}`, `check_luno_1830.py`, `archive_luno_1830.py` |
| L1-M | `l1-model-completeness.json` | `outputs/l1m-20261030-{01-stored,02b-point,03-field}` | `examples/fetch_l1m.py`, `run_l1m.py --model …`, `check_l1m.py`, `archive_l1m.py` |
| C1 | `c1-closure-arm.json` | `outputs/c1-20261030-01` | `examples/run_c1.py`, `check_c1.py`, `archive_c1.py` |
| A1 | `a1-rfi-audit.json` | `outputs/a1-rfi-audit-20261030-01/{l1,l2}` | `examples/audit_emptied_bins.py run {l1,l2}`, `summarise` |
| L5 | `l5-solver-science.json` | `outputs/l5-solver-20261030-{08,09,15,18,19}` | `examples/run_l5_solver_study.py sweep/select/confirm` |
| O-CASA | `o-casa-crosscal.json` | `outputs/o-casa-20261030-{01,02}` | `bash tools/oracles/casa/build.sh`, `bash tools/oracles/casa/run.sh outputs/o-casa-<date>-NN` |

**Inputs.** Inputs are public and checksum-pinned:

- the RATT bucket objects listed in the receipts
  `outputs/luno-solve-20261029-02/inputs/receipt.txt` and
  `outputs/luno-support-20261029-01/slice/receipt.txt`, and L2's fetch
  receipt;
- the CARACal strategies at `8f7bb363` (`results/caracal-strategies.json`);
- CARACal's lsm (SHA256 `0964b9f4…`, GPL-2.0, downloaded, not committed).

Everything is deterministic: the split uses seed 7, and the solver is
bit-identical at any thread count. Images since P2 match the archived ones
to about 2e-15 of the peak, not by hash.

**Discrepancies in the record found while writing** (not edited here; for
the coordinator):

- L1's archive has no amendment-1 calls, only a timing stub. Its matched
  numbers come from C1's archive (`l1_amendment_1_pairs`). C1 reproduced L1
  on every non-image field, and the numbers agree with
  `outputs/luno-array-campaign-20261030-01/result.json` (`amendment_1`).
  D2 had noted the gap.
- K's and O-CASA's archives still carry "provisional: SARAO confirmation
  pending" strings. `flagging-luno-candidate.md` still says K's results
  "wait on the licence confirmation". All three predate the user's licence
  decision.
- The "14.96 Jy point about 1.5″ off" description of the 1934−638 model
  survives in STATE's L1 entry and `flagging-luno-candidate.md` beside
  L1-M's correction (a field model, A0 2.1″ off).
- L1 reports a "12.46 GB" peak; P5 found the unit was MiB.
- L1's and L2's texts say "intervals converge"; the converged fraction
  counts gains (L5).
- A1 proposed dropping the first pass's emptied bins (1,358 held-out
  samples on L1). C1 implemented the union of first pass and mild (726
  bins; 703 + 700 samples).
- K's first pass added 128 *training* cells while flagging 166 cells in all.
  O-CASA's tfcrop and rflag fractions count all unflagged cells, so they
  are not on the same footing as the 128.

## For the coordinator

- **Files.** Added `research/flagging-verdict.md`,
  `research/results/flagging-verdict.json` (90 calls, about 41 KB, numbers
  and archive paths only) and `examples/verdict_tables.py`. No shared file
  was edited.
- **STATE.md**, new top entry:

  > L4 gain-TV flagging verdict, 2026-10-30: **closed: null**
  > ([flagging-verdict.md](flagging-verdict.md)). Gain-TV-guided flagging
  > was tested on the SKA pointing fixture (2026-09-23/24) and on the public
  > LUNO MeerKAT L-band calibrators. That covers PKS 1934−638 at four
  > stations (K) and on the whole array (L1), under three calibrator models
  > (L1-M) and with a gauge-free closure arm (C1), and PKS 1830−211 under
  > two models (L2). All LUNO runs used the core with the seed-7 split
  > against the CARACal first-pass Tricolour strategy.
  >
  > Of 90 pre-registered calls, 64 are null and 26 undecidable; none is
  > better or worse. The frozen policy selected no TV-guided (α > 0) mask
  > on the fixture or on LUNO. Against the first pass, held-out MSE agrees within 0.06 %
  > (matched 0.99943) and residual RMS within 0.6 %. On the parallel
  > kernels the TV chain costs 4.6–5.9× the first pass, so neither novelty
  > route holds.
  >
  > Model completeness (L1-M), closure structure (C1), convergence (L5) and
  > the GNSS-band bins (A1) do not change the answer. Calibration choices
  > (model, solver chain) move held-out error 30× or more than any flag.
  > Scope: one observation, processed FLAG and weights. Native data (L3)
  > would reopen it. Table `results/flagging-verdict.json`. Next: B1.
- **`flagging.md`**, opening status. Replace "No scientific improvement has
  yet been measured." with: "Closed 2026-10-30 as null: no scientific
  improvement was measured on the fixture or on the LUNO calibrators, and
  the method is not cheaper than the CARACal first pass; see the
  [verdict](flagging-verdict.md)."
- **`big-plan.md`**, status line for L4: "L4 done 2026-10-30
  (`flagging-verdict.md`): closed as null; 90 pre-registered calls, 64 null
  and 26 undecidable, none better or worse; cost clause fails on the
  parallel kernels (4.6–5.9×). L3 stays a standing reopening item. B1
  starts."
- **`research/README.md`**, index line: "New, 2026-10-30: L4, the
  [flagging verdict](flagging-verdict.md): gain-TV-guided flagging is
  closed as null on the fixture and both LUNO calibrators (90 calls, none
  better or worse; not cheaper than the CARACal first pass); what would
  reopen it, and the move to B1." Also mark the "Active objective: MeerKAT
  L-band flagging" heading as closed, pointing at the verdict.
- **Discrepancies** for the owners of those files: the list at the end of
  section 9.
- **Timings** for `tool-timings.md`: `verdict_tables.py --check` 0.04 s,
  20 MB (stdlib, reads 11 archives); `bash tools/check-all.sh`, once before
  the commit, 8 min 25 s wall including the host-lock wait (pytest 726
  passed, 5 skipped in 150.6 s), 1.6 GB peak, overall PASS.
