# Frequency-dependent gains: adequacy before compression

Smooth pointing recovery must survive actual spectral gain errors, not merely extra gain freedom in the fitter. Seven paired three-seed campaigns now test that distinction. All 168 fits converge; several are nevertheless badly wrong.

These are conventional joint-model controls, not a new calibration algorithm or a state-of-the-art comparison. Frequency-smooth polynomial calibration is established prior work; see [Yatawatta (2015), Distributed Radio Interferometric Calibration](https://academic.oup.com/mnras/article/449/4/4506/1203097). Our scalar log-gain parameterization is not a reproduction of that distributed Jones-matrix solver, but polynomial compression itself cannot support a novelty claim.

## Experiment

The same eight-antenna scalar katbeam fixture uses four frequencies, 24 times over six hours and four time-spline knots. Seeds 7, 11 and 19 each provide one pointing/gain realization and noise realization. Each is tested with physical common pointing zero or constant (+30, −30) arcsec in antenna coordinates. Six whole times are withheld; no model is fitted to those visibilities.

Injected log-gain slopes have independent knot standard deviations 0.02 in amplitude and 0.03 rad in phase, multiplying `x=(frequency−1.3GHz)/0.4GHz`. The curvature control adds independent coefficients with half those standard deviations multiplying `x²`. Both coefficient trajectories use the same cubic time basis. These scales are assumptions, not measured MeerKAT bandpasses.

Fits use zero-mean relative pointing plus an explicit common spline with 0.5 arcmin knot priors, smooth gain priors (0.1, 0.1), and optional 5% flux / 0.1 spectral-index priors. The supplied off-axis fluxes have ±2% errors. Known-sky, wrong-fixed-sky and gain/sky-only controls are retained in the [full archive](results/chromatic-gains.json). The table below summarizes the joint-flux case across three seeds and both common truths.

| Gain truth | Fitted gain model | Source spectra | Relative RMSE (arcsec) | Common RMSE (arcsec) | Held-out normalized mean square |
| --- | --- | --- | ---: | ---: | ---: |
| Linear | Achromatic | Fixed/correct | 18.92–26.43 | 13.05–60.38 | 543–619 |
| Linear | Independent channels | Fixed/correct | 0.76–1.09 | 0.20–0.29 | 1.054–1.065 |
| Linear | Independent channels | Fitted | 0.75–1.09 | 0.70–1.46 | 1.059–1.065 |
| Linear | Degree 1 polynomial | Fitted | 0.73–1.04 | 0.72–1.49 | 1.016–1.039 |
| Linear+quadratic | Degree 1 polynomial | Fitted | 4.75–6.28 | 1.85–10.43 | 17.20–32.40 |
| Linear+quadratic | Degree 2 polynomial | Fitted | 0.72–1.07 | 0.63–1.48 | 1.043–1.047 |
| Linear+quadratic | Independent channels | Fitted | 0.75–1.09 | 0.70–1.46 | 1.059–1.065 |

The normalized mean square divides complex squared residuals by twice the per-real-component noise variance; its noise-only expectation is 1. These are prediction errors, not deconvolved image metrics or reduced chi-square values.

Allowing uncertain spectra mainly weakens the common pointing estimate here. It does not remove the known Gaussian gauge under unrestricted sky/gain freedom: these experiments still have a matched non-Gaussian beam, power-law source spectra, restricted spline trajectories and explicit priors.

The degree 1 model reduces gain coefficients from 240 to 120 (total fitted parameters 312→192 when fitting spectra). With curvature, degree 2 uses 180 gain coefficients, 252 total. It restores the tested accuracy with fewer parameters than independent channels. However, the true gains were generated inside the corresponding polynomial family; this is an expected matched-family benefit, not novelty. Coefficient priors also differ between parameterizations. Timings include compilation and are not evidence of an end-to-end compute advantage.

## API and controls

```python
fit = solve_pointing(
    sky,
    observation,
    data,
    times,
    knots,
    antenna_count,
    noise_jy=0.001,
    zero_mean_pointing=True,
    gain_prior_sigma=(0.1, 0.1),
    gain_frequency_degree=1,
)
```

Log amplitude and phase are tensor products of time splines and Chebyshev polynomials on the observed frequency interval mapped to [−1, 1]. The reference antenna has zero phase at every time/frequency. `gain_prior_sigma` applies independently to polynomial coefficients; it is not a matched independent-channel prior. This option excludes `gain_per_channel=True` and requires a gain prior. Returned gains have shape (time, frequency, antenna), labelled by `gain_frequencies_hz`; `gain_frequency_basis` records the evaluated basis. No unseen-frequency prediction is reported by this interface.

Noiseless tests recover time-varying chromatic amplitude and phase together with sky and relative pointing, including the frozen-pointing baseline. Degree 0 is checked against the achromatic parameterization. Invalid degrees, missing priors and conflicting gain options are rejected.

## Reproduction and remaining test

Start with:

```sh
.venv/bin/python examples/relative_pointing.py --joint-gains --held-out \
  --common-prior-arcmin 0.5 --chromatic-gain-truth 1 \
  --gain-per-channel --spectral-index-prior 0.1
```

Replace `--gain-per-channel` with `--gain-frequency-degree 1` for linear compression. Add `--chromatic-gain-curvature 0.5` and compare degrees 1 and 2 with the independent-channel baseline. Omit both frequency-fit options for the deliberately inadequate achromatic control; omit the spectral prior for fixed/correct spectra. Default seeds are 7, 11 and 19.

This comparison does not select complexity independently: held-out scores characterize predetermined candidates. Next, test a separate train/validation/test selection rule on non-polynomial bandpass errors and heterogeneous beam errors, with matched priors or an explicit prior-sensitivity analysis. A novel method must outperform that conventional baseline at matched quality/cost, not just outperform an inadequate achromatic fit.
