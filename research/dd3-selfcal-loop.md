# DD3: the direction-dependent self-calibration loop on a simulation

Issue #15, third piece (plan in [dd1-facet-gains.md](dd1-facet-gains.md),
section 2). Branch `dd3-selfcal`. Sections 1-5 are frozen 2026-11-23,
before any code that tests them; later changes are dated amendments,
labelled post hoc where they could have seen a result.

Status: **proposed**.

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

Not yet measured.

## Amendments

**A1, 2026-11-23, clarification before any code ran.** The shared minor
cycle (section 2, step 4) searches for peaks only over pixels at least
3 pixels inside their facet and the image edge. These are the same pixels
over which σ is taken and gate L's residual tolerance applies. DD2b's
boundary band (polygon rasterisation at feather size 0) differs between the
two codes by up to 4e-2, and would otherwise steer the components.
