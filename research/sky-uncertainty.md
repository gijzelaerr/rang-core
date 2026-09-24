# Sky-model errors masquerading as pointing errors

## Result

On 20 paired realizations, 2% errors in off-axis source fluxes increase smooth-pointing trajectory RMSE from 2.40 to 30.24 arcseconds when calibration holds the sky fixed. Jointly fitting those fluxes reduces RMSE to 2.48 arcseconds. This is evidence for the importance of sky uncertainty, not a new joint-inference algorithm.

| Fit | Pointing RMSE (arcsec) | Held-out RMS (mJy/component) | Off-axis flux RMSE (mJy) |
|:--|--:|--:|--:|
| Correct sky, fixed fluxes | 2.402 ± 0.272 | 1.066 ± 0.041 | 0 (known) |
| Incorrect sky, fixed fluxes | 30.237 ± 0.187 | 3.682 ± 0.086 | 10.520 (imposed) |
| Incorrect sky, joint fluxes with 5% priors | 2.475 ± 0.268 | 1.067 ± 0.040 | 0.170 ± 0.071 |
| Incorrect sky, joint fluxes with 0.01% priors | 28.187 ± 0.196 | 3.353 ± 0.084 | 9.667 ± 0.011 |

Values are mean ± sample standard deviation across seeds 1–20; not confidence intervals or posterior uncertainties. The flux metric is RMSE across the three off-axis sources within each realization, then summarized across seeds. Noise is 1 mJy per real/imaginary visibility component. [Machine-readable summary](results/sky-uncertainty.json).

All 180 fits across three campaigns converged numerically; repeated control fits use identical data and are not independent additional evidence. Convergence does not establish correct pointing: the biased fixed-sky and tight-prior solutions also converge.

## Matched-sky control

With no imposed flux error, jointly fitting fluxes yields 2.475 arcsec pointing RMSE versus 2.402 arcsec when correct fluxes are fixed. The small degradation is the cost of fitting additional uncertain parameters. Joint inference is not inherently more accurate when its nuisance parameters are already known.

With 2% errors but a 0.01% flux prior, the solver cannot adjust fluxes sufficiently and infers strongly biased pointing trajectories. A formally joint fit can behave much like a fixed incorrect sky model if the prior is too confident.

## Setup

The observation is the existing eight-antenna scalar MeerKAT-core demonstrator: approximate geometry, four bright sources, four frequencies, 24 times and every fifth visibility retained. There are 403 training and 135 held-out complex rows. Interior times with index modulo four equal to two are reserved for interpolation checks. The prior and smoothness settings are declared, not tuned on those held-out data.

Pointing truth is a constant random per-axis offset plus a sinusoid of amplitude 0.25 arcmin over six hours, with independently drawn phase. The fit uses six natural cubic spline knots, a curvature weight of 0.01 and a 3 arcmin knot-value prior. Truth is not generated from the spline basis. Geometry, sky spectra and beam shape are correct in this experiment.

True source fluxes are [1.0, 0.7, 0.5, 0.3] Jy at 1.28 GHz. The incorrect model is [1.0, 0.714, 0.49, 0.306] Jy. The central source remains exactly known and fixed. This is an explicit favorable flux anchor; it does not test absolute calibration with an uncertain reference or fitted direction-independent gains.

The joint solver adds three time-independent, additive flux corrections to the 96 spline coefficients. Independent Gaussian priors are centred on the supplied incorrect fluxes, with standard deviation 5% of each model flux. A separate stress condition changes this to 0.01%. The reported fluxes are joint penalized estimates; there is no subsequent debiasing or unpenalized refit.

## API

```python
solution = solve_pointing(
    model_sky,
    training_observation,
    training_visibilities,
    times_s,
    knots_s,
    antenna_count=8,
    noise_jy=0.001,
    smoothness=0.01,
    flux_prior_jy=[0.0, 0.0357, 0.0245, 0.0153],
)
fitted_sky = model_sky._replace(flux_jy=solution["flux_jy"])
```

`None` retains the fixed-sky behavior. A zero prior sigma fixes that component; a positive sigma enables a fitted additive flux correction. Returned `flux_jy` and pointing trajectories must both be used in subsequent prediction. Negative fluxes are permitted for signed CLEAN-component models; this is not a positivity-constrained source catalogue fit. The data Jacobian rank now includes flux parameters, in prior-normalized flux coordinates, so singular values are parameterization-dependent.

## Reproduce

```sh
.venv/bin/python examples/sky_uncertainty.py --output outputs/sky-uncertainty-20
.venv/bin/python examples/sky_uncertainty.py --flux-error 0 --output outputs/sky-matched-20
.venv/bin/python examples/sky_uncertainty.py --flux-prior 0.0001 --output outputs/sky-tight-prior-20
```

Each campaign defaults to seeds 1–20 and saves all per-seed results, configuration, convergence status and aggregate statistics. Tests independently verify nearly noiseless joint recovery, the fixed central-source anchor, the additional parameter count, and invalid-prior rejection. Earlier fixed-sky tests remain in place.

## Limits and next test

Only one source layout and one fixed error-sign pattern are tested. Spectral indices, beam shapes, positions and the central source remain correct; no measured visibilities or image-domain metrics are used. Allowing a flexible flux model helps precisely because the introduced errors are in its fitted parameter family. These results cannot establish robustness to other model errors.

Next introduce spectral-index and measured-beam mismatch, sweep declared sky-prior scales, and assess whether additional pointing modes remain data-supported. The [dual-budget selection hypothesis](novelty.md) is still unimplemented and must improve on this stronger joint-inference baseline before a novelty claim.
