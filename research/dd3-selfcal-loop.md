# DD3: the direction-dependent self-calibration loop on a simulation

Issue #15, third piece (plan in [dd1-facet-gains.md](dd1-facet-gains.md),
section 2). Branch `dd3-selfcal`. Sections 1-5 are frozen 2026-11-23,
before any code that tests them; later changes are dated amendments,
labelled post hoc where they could have seen a result.

Status: **measured 2026-11-23**: gate L (loop parity) **passes** every cycle. Gate T fails in both arms alike, so the outcome is **truth failure of the loop, not of the port**: the facet d3 gain and model flux trade off (section 6).

## 1. What DD3 is

The pieces exist and each matches its oracle:

| Piece | Rang | Oracle | Measured |
| --- | --- | --- | --- |
| DD solve | `cal_gain.solve_dd` | QuartiCal 0.2.7 | [DD1](dd1-facet-gains.md), parity at 50 iterations |
| Facet predict | `dirty2vis` per facet, corrupted | WSClean 3.7 `-predict` with facet solutions | [DD2](dd2-facet-imaging.md), 3.7e-7 |
| Facet imaging | `fits_image` per facet, hard stitch | WSClean 3.7 with facet solutions and `-feather-size 0` | [DD2b](dd2b-facet-coupling.md), 7.3e-8 |

DD3 joins them into a loop. The same loop runs twice:

- **Arm R:** every step in rang.
- **Arm O:** the solve in QuartiCal and the predict and imaging in WSClean.

The deconvolution (section 2, step 4) is one shared deterministic rule,
applied to each arm's own image. Each arm is also scored against the
simulated truth.

**Hypothesis.** Arm R reproduces arm O cycle by cycle, and both recover the
truth gains to within 20 % of the error of a solve with the complete true
model.

**Not claimed:**
- a better DD calibration than QuartiCal and WSClean;
- a deconvolver (the shared rule is a plain Högbom minor cycle, not
  GeMClean with facets);
- real data (DD4);
- speed (cost is reported, not gated).

## 2. The loop (frozen)

Data: DD1's simulation (`dd1.ms`, seeds 1501-1503: four facets; 28 point
sources of 10 mJy to 2 Jy; DD gains per 4 × 8 s block; σ 0.11 Jy). The
column is `DATA` (noisy).

Grid: 3200 × 3200 pixels of 3″ (Nyquist; [DD2](dd2-facet-imaging.md) A3),
Stokes I, natural weighting. The facets and H5parm layout are DD2's.

**Start model M₀:** the four facet-centre sources (1.0, 2.0, 0.8 and 0.4 Jy)
at their true pixels, as a catalogue would give them. The 24 fainter
sources are missing.

**Major cycles k = 0, 1, 2, 3.** Each cycle runs these steps:

1. **Per-facet model columns:** the predict of `M_k` masked to each facet,
   uncorrupted.
   - Arm R: `dirty2vis`.
   - Arm O: four WSClean `-predict` runs without facets, on the facet-masked
     model image, each copied into `MODEL_Dd`.
2. **DD solve** with P1's intervals (4 × 8 s, all channels), reference
   antenna 0, no pinned direction, and the frozen DD cap (150 iterations,
   criterion 1e-7, stop fraction 0.99, [DD2](dd2-facet-imaging.md)).
   - Arm R: `solve_dd`.
   - Arm O: QuartiCal 0.2.7 with DD1's settings, except
     `solver.iter_recipe=[150]`, `G.direction_dependent=true` and
     `G.pinned_directions=[]`.
3. **Residual image.** Compute `R = DATA − Σ_f G_p,f M_f G_q,f^H` and image
   it to the flat-gain facet image: `1/c` per facet, hard stitch.
   - Arm R: rang's facet predict and facet image.
   - Arm O: WSClean `-predict` with `-facet-regions` and
     `-apply-facet-solutions` on the arm's H5parm. The model image is
     written as both `<name>-model.fits` and `<name>-model-pb.fits` (DD2
     A1). The residual column is formed with python-casacore, then imaged by
     WSClean with facet solutions and `-feather-size 0`, and
     `-image-pb.fits` is used.
4. **Minor cycle, shared:**
   - **Rule:** Högbom on the residual image with the unit-gain PSF.
     - The PSF is rang's `fits_image` PSF of the data's weights. It is one
       file, read by both arms, and is not each arm's own.
     - Loop gain 0.1; at most 5,000 components per cycle.
     - Stop at `5 σ` or 1 mJy, whichever is larger. `σ` is 1.4826 × the
       median absolute deviation of the residual, over pixels at least 3
       pixels inside the facets.
     - Components go on pixels and add to `M_k`, giving `M_{k+1}`.
   - **Why this rule:** the true flat-gain PSF differs by facet. Using the
     unit-gain PSF is part of the rule, the same in both arms.

After cycle 3, steps 1-3 run once more with `M_4`. That gives the final
gains and the residual.

## 3. Measures and frozen tolerances

**Gate L, loop parity (per cycle k, rang against the oracle):**
- Component lists equal: the same pixels, and per pixel the summed flux
  within `1e-5 + 1e-4 × |flux|` Jy.
- Gains: max abs difference of the per-direction baseline products at most
  `1e-5`; flags equal.
- Residual image: `≤ 1e-3 × max|I|` over pixels at least 3 inside the facets
  (DD2's arm I tolerance).

If the component lists first differ at cycle k, L fails from k on. The
cycle and the first differing component are recorded.

**Gate T, truth (final gains and model, each arm):**
- **T1 gains:** the median relative error of the per-direction products
  against the truth must be `≤ 1.2 ×` the same median for `solve_dd` with
  the complete true model under the same cap. That reference is
  `P1_under_cap_truth`, 3.10e-3 (DD2 `prepare.json`). The limit is
  `≤ 3.72e-3`.
- **T2 model flux:** the model flux within 2 pixels of each true source,
  against the source's flux.
  - The four bright sources within 2 %.
  - Sources of at least 30 mJy within 10 %.
- **T3 false flux:** the total `|model|` more than 2 pixels from every true
  source, at most 1 % of the total true flux.

Reported, not gated:
- T1 per direction and per cycle;
- the residual rms against the thermal expectation;
- the same T measures for the start model M₀ alone, which is the gain from
  self-calibration.

## 4. Decision rule (named before any result)

- **Pass:** L holds for every cycle, and T holds for both arms. The DD loop
  is ported, and DD4 (real data) starts from it.
- **Loop parity failure:** L fails at some cycle. The first divergence is
  recorded. If it is a tie or a near-threshold choice of the shared rule
  (two components within `1e-4` relative of each other or of the stop
  level), the outcome is **parity up to the rule**. In that case T is still
  read per arm.
- **Truth failure of the loop:** L holds and T fails in both arms. The loop
  (start model, rule, cycle count) does not reach the truth; this is not a
  port failure. Which of T1-T3 fails is recorded.
- **Setup:** a tool refuses an input, or an arm cannot run. Fix it as a
  dated amendment before any gate is read.

## 5. Cost

Wall time per cycle and per tool on glacier under `heavy_lock` (8 slots),
indicative.

## 6. Measured result

Run `D:/rang/outputs/dd3-20261123-01`:
- `R/` and `O/cycle-0..4` (models, gains, residuals, components), plus
  `armR.log`, `armO.log` and `compare.json`.
- WSClean 3.7 `4f395b28` and QuartiCal 0.2.7, in the venvs and images of
  DD1 and DD2.
- Rang from main `fe091771`, through the main checkout's environment.
- Archive: [results/dd3-selfcal/](results/dd3-selfcal/).
- Host glacier, shared, rang at 8 threads.

**Gate L: pass at every cycle.**

| Cycle | components (R, O) | same pixels, fluxes | max \|ΔP\| gains | flags | residual (rel.) | solver iterations (R = O) |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 69, 69 | yes | 1.6e-6 | equal | 1.8e-6 | 108 |
| 1 | 119, 119 | yes | 1.3e-6 | equal | 1.0e-5 | 90 |
| 2 | 119, 119 | yes | 1.3e-6 | equal | 4.6e-5 | 88 |
| 3 | 32, 32 | yes | 1.2e-6 | equal | 1.3e-4 | 88 |
| 4 (final) | – | – | 1.4e-6 | equal | 1.6e-4 | 88 |

QuartiCal at `iter_recipe=[150]` stops at the same iteration as `solve_dd`
in every cycle, which extends DD1's parity to the frozen cap.

The residual difference grows slowly with the cycle, from 1.8e-6 to
1.6e-4, against a limit of 1e-3. The likely cause is float32 rounding in the
model columns and images compounding through the model, not a diverging
choice.

**Gate T: fails in both arms, with identical numbers.**

| Measure | start model M₀ | final, R and O | limit |
| --- | --- | --- | --- |
| T1 median gain-product error | 3.79e-2 | **3.89e-3** | ≤ 3.72e-3: **fail** |
| T1 per direction d0-d3 | – | 3.4e-3, 2.2e-3, 3.9e-3, **2.5e-2** | – |
| T2 bright-source flux ratios | 1, 1, 1, 1 | 0.9992, 0.9985, 1.0000, **0.9777** | within 2 %: **fail** (d3) |
| T2 faint sources (≥ 30 mJy) | – | 0.985-1.044 | within 10 %: pass |
| T3 false flux | – | 0.42 % | ≤ 1 %: pass |

Self-calibration cuts the gain error tenfold, from the start model's 3.8e-2
to 3.9e-3. Facets d0 and d2 come within 1.15 × the complete-model reference and
d1 within 1.5 × (the d0, d1 and d2 medians are 3.4e-3, 2.2e-3 and 3.9e-3, against
the complete-model solve's 3.0e-3, 1.5e-3 and 3.7e-3, DD2 `prepare.json`).

Facet d3 (the 0.4 Jy centre, the faintest facet) does not.
- Post hoc, its gain products are 2.46 % high in amplitude against the
  truth (median `|P|/|P_true|` = 1.0246 at cycle 4; 0.997-1.003 at cycle 0
  and in the other facets).
- Its model flux is 2.2 % low (0.9777).
- The product 1.0246 × 0.9777 = 1.0018. The loop moved flux between the
  facet's gains and its model.

This is the amplitude degeneracy of a DD term: per direction, a common
scale of `|g|²` and the facet's model flux give the same visibilities.
Nothing in the loop pins the scale once the model is updated. It is
inherent in this loop (QuartiCal and WSClean do the same, to 1e-6), not a
port error.

**Outcome under section 4: truth failure of the loop.** L holds and T1 and
T2 fail in both arms, through facet d3's gain-flux degeneracy. The rang DD
self-calibration loop is QuartiCal and WSClean's, cycle for cycle.

**Cost (indicative):**
- Arm R: 4:32 for 5 cycles, each about 8 s solve, 11 s images and about
  30 s Högbom.
- Arm O: 9:29, each QuartiCal process 54-79 s, against 1.5-2 s for
  `solve_dd` in the same cycle. WSClean predicts and images take about
  10 s per cycle.

## 7. For the coordinator

- Mergeable as the DD loop with parity to QuartiCal and WSClean. Tools only
  (`tools/oracles/dd3/`); no core change.
- Owner decision for the loop itself: the per-facet flux scale is free.
  Candidates, each its own proposal:
  - hold facet amplitudes fixed (phase-only DD, as CARACal's first dE
    rounds do);
  - normalise each direction's mean `|g|` to 1 after each solve;
  - keep the start model's catalogue fluxes fixed.
  The decision belongs before DD4 (real data), where the d3-like facets are
  the faint ones.

## Amendments

**A1, 2026-11-23, clarification before any code ran.** The shared minor
cycle (section 2, step 4) searches for peaks only over pixels at least
3 pixels inside their facet and the image edge. These are the same pixels
over which σ is taken and gate L's residual tolerance applies. DD2b's
boundary band (polygon rasterisation at feather size 0) differs between the
two codes by up to 4e-2, and would otherwise steer the components.
