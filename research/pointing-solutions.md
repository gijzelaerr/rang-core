# Smooth per-antenna pointing solutions

## Objective

Update: the solver now optionally fits component flux densities jointly with pointing. See [the sky-uncertainty experiment](sky-uncertainty.md) for the API, priors, controls and 20-seed results. Fixed-sky behavior remains the default described below.

Further extensions: `spectral_index_prior` enables index fitting, `beam_axis_ratio` selects an elliptical Gaussian, and `minimum_mode_information` enables experimental information truncation. See [spectral tests](spectral-pointing.md). The separate [shared-mode ambiguity solver](beam-rotation.md) allows free source/channel fluxes; it is not a replacement for the full spline solver.

Infer the two antenna-frame pointing offsets of each dish as continuous functions of time, directly from visibilities predicted from a sky component list. The current implementation is a small JAX reference solver, cross-checked against Rang's Rust predictor and analytic pointing derivatives.

Pointing self-calibration is established: [Bhatnagar & Cornwell (2017)](https://arxiv.org/abs/1709.08681) is a direct algorithmic precedent. [MeerKAT L-band beam measurements](https://arxiv.org/abs/2202.02101) identify pointing as a leading beam-response uncertainty. Neither splines nor automatic differentiation establish novelty. The open research question is reliable pointing recovery with uncertain sky/beam models; see the [contribution assessment](novelty.md).

## Forward model

`component_list(l, m, flux_jy, spectral_index, reference_hz)` produces a list of point components. Inputs use direction cosines relative to the phase centre, integrated flux density in Jy and power-law spectral indices. An extended source can be discretized into sufficiently resolved components.

`image_components(image_jy_per_pixel, l, m)` converts a model image without flux thresholding; zero pixels are omitted and negative components retained. It expects explicit Jy/pixel units and coordinate grids. FITS/WCS loading, CLEAN-table formats and Jy/beam conversion are not implemented.

For each visibility row, the direct sum is

```math
V_{pq}=\sum_j I_j(\nu) E_p(R_t(l_j,m_j)-\delta_p(t),\nu)
E_q(R_t(l_j,m_j)-\delta_q(t),\nu)
\exp[-2\pi i\,\nu/c\,(u l_j+v m_j+w(n_j-1))].
```

Here uvw is in metres, `n=sqrt(1-l²-m²)`, `R_t` is the supplied sky-to-antenna beam rotation and the baseline convention is p minus q. The current beams are real Gaussian voltage responses with power FWHM `1.02 λ / 13.5 m`. This scalar convention is not a full-polarization Jones implementation. Integrated component flux needs no additional `1/n` factor.

The observation arrays contain one row per baseline/time/frequency sample: `uvw_m`, `frequency_hz`, `antenna1`, `antenna2`, `time_index`, `beam_angle_rad`. `time_index` addresses the provided unique increasing times. The predictor accepts offsets with shape `(time, antenna, 2)` in arcminutes.

## Smooth solution model

Each antenna's two offsets are natural cubic splines through user-specified knots. The coefficients are the offsets at those knots. The solver minimizes

```math
\sum_i |V_i^{\mathrm{pred}}-V_i^{\mathrm{obs}}|^2/\sigma_i^2
+\lambda\sum_{p,d}\int_0^1 |\delta''_{p,d}(u)|^2du
+\sum_{k,p,d}c_{k,p,d}^2/\sigma_c^2.
```

The first term is implemented as stacked real and imaginary residuals; `noise_jy` is sigma per component. Time `u` is normalized by the knot span. The integrated curvature penalty is evaluated exactly for the spline using two-point Gaussian quadrature on each knot interval. It leaves constant and linear drift unconstrained, so a proper zero-centred knot prior regularizes those modes. The default prior scale is 3 arcmin; its strength depends on knot count. Knot count and smoothness must be treated as model choices, not silently tuned to truth.

JAX `jacfwd` differentiates the complete residual vector with respect to spline coefficients; SciPy's trust-region least-squares solver uses that Jacobian. There is no finite differencing in optimization. Finite differences are used only for derivative verification. Use [JAX 64-bit mode](https://docs.jax.dev/en/latest/config_options.html) before constructing inputs; the solver checks it rather than changing application-wide configuration on import. [JAX derivative reference](https://docs.jax.dev/en/latest/higher-order.html).

```python
import jax

jax.config.update("jax_enable_x64", True)
from rangtoy.pointing import solve_pointing

solution = solve_pointing(
    components,
    observation,
    visibilities,
    times_s,
    knots_s,
    antenna_count=8,
    noise_jy=0.001,
    smoothness=0.01,
)
offsets = solution["offsets_arcmin"]  # time × antenna × 2
```

Always inspect `success`, `message` and `optimality`. The solver also reports the numerical rank and singular values of the whitened data Jacobian, excluding prior rows. Numerical full rank does not establish good conditioning or physical identifiability; inspect weak singular directions and prior sensitivity. No posterior uncertainties or observability certificate are returned.

## Reproducible experiment

```sh
.venv/bin/python examples/pointing.py --seed 7 --noise 0.001 --knots 6 --smoothness 0.01 --output outputs/pointing
```

This uses every fifth visibility from the Rust toy geometry (eight approximate MeerKAT core positions; [provenance](../data/README.md)). Truth is sinusoidal pointing plus a constant offset, not a sample from the fitted spline basis. Every fourth interior time is held out; the reported prediction measures interpolation, not extrapolation. The component sky is exactly known and contains four bright sources. The result JSON records seed, settings, trajectories, solver termination and held-out residuals.

Initial seed-7 result with the command above: 2.005 arcsec pointing RMSE, and held-out residual RMS reduced from 2.635 to 0.950 mJy per real/imaginary component against 1 mJy injected noise. This is one realization with a correct sky and Gaussian beam, not an uncertainty interval or a robust-performance claim.

[Saved numerical summary](results/smooth-pointing.json) · [Trajectory plot](figures/pointing-trajectories.svg). The example regenerates both raw JSON and `trajectories.svg` without requiring Matplotlib.

Tests verify predictions and derivatives against independent Rust calculations, centered finite differences, baseline conjugacy, nonzero w effects, image flux conservation, spline linear null modes, time-unit invariance and noiseless spline-trajectory recovery.

## Limitations and next discriminating test

The current fit holds sky and beam shape fixed. Pointing solutions can absorb source-flux errors, spectral errors or beam-shape mismatch. Natural spline boundaries, a strong smoothness penalty, missing time coverage and weak off-axis structure can all bias trajectories. The demo is not evidence of recovery under these conditions.

Next compare fixed-sky and joint uncertain-sky pointing solutions on identical data, with time-variable truth and deliberately mismatched beams. Assess per-antenna trajectory error, flux bias, held-out prediction and prior sensitivity. Apply the proposed response/model-error budgets only after complete-estimator derivatives and observability checks are implemented.

DFT arrays and the dense Jacobian scale poorly with large datasets. This reference materializes row-by-component arrays and a dense residual-by-parameter Jacobian; it is not yet a full-array, full-resolution production pipeline. No acceleration or novelty claim is made solely from using JAX.
