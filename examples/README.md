# MeerKAT pointing-calibration toy

This section documents the original Rust toy, not the full current JAX solver.
Start with the [project overview](../README.md) for current results. The original
toy uses a JSON executable interface; newer information audits also use a Rust
C-ABI projection kernel. The Rust crate has no external dependencies.

## Run

From the repository, with Rust/Cargo and Python 3.10 or newer:

```sh
python3 examples/toy.py --seeds 7 11 19 --output outputs/demo
```

Matplotlib is required for plots. If needed, install the Python package and plotting/test dependencies in a virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip --isolated install --index-url https://pypi.org/simple -e '.[plot,test]'
.venv/bin/python examples/toy.py --seeds 7 11 19
```

Use `--no-plot` for a Python-standard-library-only run. The script runs the toy inside the installed extension `rangtoy._core` (no Cargo at run time), prints a comparison and writes `results.json`, `comparison.png`, and `comparison.pdf`. The JSON includes seeds, input settings, binary hash, runtime, metrics, true/fitted pointings and solver termination. Reusing an output directory replaces those generated files. Build dependencies for Python installation may require network access; running directly from the checkout does not require installation.

Python scripting interface, after installation (or with `PYTHONPATH=python`):

```python
from rangtoy import run_experiment, toy_output

result = run_experiment(seed=7, pointing=0.6, budget=0.01)  # in the extension
reference = toy_output("--pointing-reference")  # the binary's stdout, same bytes
for row in result["results"]:
    print(row["method"], row["flux_jy"])
```

The binary may also be run directly:

```sh
cargo run --offline --release -- --seed 7
```

## What the toy contains

- Eight antennas from an approximate published MeerKAT core layout; see [geometry provenance](../data/README.md). This is not full MeerKAT or current survey geometry.
- Scalar unpolarized direct-sum RIME, including `w(sqrt(1-l*l-m*m)-1)`; point components carry integrated flux, so there is no additional pixel-area factor.
- Four frequencies: 0.95, 1.15, 1.35 and 1.55 GHz. Twenty-four instantaneous samples span hour angles -3 to +3 hours at declination -45 degrees. They do not represent continuous integration; time/bandwidth smearing is omitted.
- A circular Gaussian voltage beam with power FWHM `1.02 lambda / 13.5 m`. Pointing offsets are fixed in antenna coordinates for the entire track; their apparent sky direction rotates with parallactic angle. This is not a measured MeerKAT beam or a streaming drift estimator.
- Four exactly known bright point sources, plus a faint extended component centred on the off-axis 0.7 Jy source. Its true flux defaults to 20 mJy at 1.28 GHz. All spectra are fixed power laws of index -0.7; no spectral indices are estimated.
- A roughly 71-arcsecond-FWHM Gaussian science component, truncated at three sigma in each coordinate. Simulation uses a 15x15 quadrature grid; fitting uses 11x11. A test compares this with 31x31 sampling to catch fringe aliasing. The fitted morphology is otherwise deliberately close to truth.
- Gaussian noise, default 10 mJy per real/imaginary visibility component. This is a chosen experimental noise level, not a sensitivity prediction. Antenna pointings have independently drawn components with 0.6 arcmin standard deviation.
- The first 18 time samples train the fits; the final six test extrapolation. There are 2,688 complex visibilities in total. No parameters are tuned using those held-out samples.

## Methods

| Label | Fit during calibration | Science flux measurement |
| --- | --- | --- |
| Fixed beam | Zero pointing offsets | Fit extended-source amplitude afterwards |
| Pointing only | Two pointing components per antenna; faint component omitted | Fit extended-source amplitude afterwards |
| Joint sky | Pointing plus one uncertain extended-source amplitude | Same final amplitude estimator |
| Protected modes | Joint fit restricted to information-supported modes satisfying a local response budget | Same final amplitude estimator |
| Known pointing | True offsets supplied, nominal beam retained | Same final amplitude estimator |

This first toy assumes direction-independent electronic gains and the bright-source flux scale are known. It does not implement general self-calibration, full Jones polarization, measured beam modes, an ionosphere, Measurement Set I/O, imaging/deconvolution or a production pipeline. It fits 16 pointing parameters and, in joint methods, one sky amplitude. Sky amplitudes are not positivity constrained, so noisy or mismatched models may return negative amplitudes.

All fitted pointing parameters have a fixed 1 arcmin Gaussian prior. The joint methods use a zero-mean 0.1 Jy prior for the uncertain component. These illustrative prior scales are not derived from an instrument observation. The optimizer profiles out its amplitude, uses the resulting Gauss–Newton Schur complement, and includes its prior gradient. This is joint MAP/variable projection, not a full marginalized Bayesian posterior.

Protected modes use generalized eigenvectors of the sky-adjusted information matrix relative to the known-sky matrix. Modes with information ratio below 0.05 are excluded. Additional modes are greedily removed until their combined local response satisfies `--budget`. Ridge regularization supplies the same pointing prior as the joint baseline. This is an initial heuristic implementation of the research idea, without a model-selection search or learned priors.

## Read the diagnostics carefully

`flux_jy` is the training-data least-squares amplitude of the extended template after subtracting the fitted bright model. It is a component estimate, not an aperture measurement on a deconvolved image.

`heldout_rms_jy` measures prediction residuals on the six reserved time samples, using the trained pointing and flux estimates. Values near the configured noise are desirable but do not prove unbiased imaging.

Each method is rerun after adding a 2 mJy source to the *already corrupted visibilities*, using the true forward model and identical noise. Both the target morphology and a source shifted by -0.18 degrees in l are tested. The reported `template_transfer` and `off_template_transfer` are normalized projections of the change in bright-model-subtracted residuals onto the injected visibility signal, across all samples. They measure finite local response, not the fraction of the original 20 mJy source recovered. The shifted source is not part of the fitted sky template.

`template_distortion` and `off_template_distortion` also measure the norm of the difference from the ideal injected response, including changes orthogonal to the input template. A response projection of one does not imply zero distortion.

`local_loss` is the operator-norm response for the single fitted science template at the last solver linearization, with basis, prior and Jacobians frozen. For joint fitting its calibration Jacobian includes the current sky amplitude. It is distinct from the finite bright-model-subtraction diagnostic. `retained_modes` refers to that last step. Basis changes, nonlinear refitting, model mismatch and sources outside the template invalidate any global interpretation of this local bound. `termination` distinguishes small-step stopping, failed line search, iteration cap and unfitted controls; it is not a global optimality certificate.

## Controls and stress experiments

```sh
# Exact zero-data-error control: no pointing, no noise, no faint source.
python3 examples/toy.py --pointing 0 --noise 0 --target-flux 0 --no-plot --output outputs/control

# Model mismatch: true beam 2% wider than the fitting model.
python3 examples/toy.py --seeds 7 11 19 --beam-error 0.02 --output outputs/beam-mismatch

# Exercise the pruning branch; this can underfit real pointing errors.
python3 examples/toy.py --budget 0.000001 --output outputs/strict-budget
```

The zero-error control's base fit should be exact. Its subsequent injection into the pointing-only method can still suffer suppression: introducing that source makes the calibration sky incomplete even when the telescope has no pointing error.

The known-pointing control still assumes the nominal beam. With `--beam-error`, it is not an oracle for every corruption; its bias is a diagnostic of beam-model error.

## Initial measured result

The matched-width runs with seeds 7, 11 and 19 on 11 September 2026 produced:

| Method | Mean recovered flux (mJy) | Mean held-out RMS (mJy/component) | Mean target injection response |
| --- | ---: | ---: | ---: |
| Fixed beam | 22.49 | 11.02 | 100.00% |
| Pointing only | 12.05 | 11.00 | 75.09% |
| Joint sky | 19.79 | 9.93 | 100.00% |
| Protected modes | 19.79 | 9.93 | 100.00% |
| Known pointing | 19.89 | 9.93 | 100.00% |

Truth is 20 mJy; noise sigma is 10 mJy/component. The plotted error bars are sample standard deviations across three seeds, not confidence intervals. All 16 modes survive at the default one-percent local budget. The protection method therefore demonstrates **no additional benefit over joint fitting** here. This is evidence for the familiar incomplete-sky failure mode, not evidence of a novel superior algorithm.

With a 2% beam-width mismatch, joint/protected fitting instead returns about 34.03 mJy and known-pointing returns 32.94 mJy. The joint method's injection response remains about 99.75%. This illustrates why signal preservation and absolute sky accuracy are separate requirements. Recovering the right flux accidentally in one comparator is not evidence of correct calibration either.

The strict-budget run at seed 7 returns about 27.78 mJy with protected modes, versus 19.43 mJy with joint fitting: aggressive protection underfits the pointing. Also, the default seed-7 shifted-source injection retains a projection of about 99.64% under joint fitting but has about 7.62% norm distortion. The current protected template does not cover that source. These negative results are part of the example, not exceptions to exclude from its evaluation.

## Verification

To separate visibility information from uncertain external flux constraints,
run `OPENBLAS_NUM_THREADS=1 .venv/bin/python examples/information_budget.py`.
The [information-budget note](../research/information-budget.md) defines the
matrix split and explains why prior-conditioned precision is not a standalone
pointing measurement.

The latest Gaussian ambiguity and synthetic non-Gaussian controls are reproduced
with `OPENBLAS_NUM_THREADS=1 .venv/bin/python examples/gaussian_gauge.py`.
See [the updated interpretation](../research/gaussian-gauge.md): allowing the
remaining common temporal modes changes the earlier identifiability conclusion.

For the frequency-dependent gain and differential-pointing identifiability
audit, run `OPENBLAS_NUM_THREADS=1 .venv/bin/python examples/gain_observability.py`.
This compares complete eight-antenna baseline coverage with the thinned
cross-language fixture and saves `outputs/gain-observability/results.json`.
See [the symmetry report](../research/beam-rotation.md) for interpretation.

```sh
cargo test --offline --release
cargo clippy --offline --all-targets -- -D warnings
cargo fmt --check
python3 -m pytest -q
ruff check python examples tests
ruff format --check python examples tests
```

Rust checks include beam normalization, uvw length preservation, baseline conjugacy, analytic derivatives, eigen decomposition, noiseless pointing recovery, quadrature convergence and the frozen linear budget. Python checks exercise the executable boundary, invalid inputs, reproducibility, zero-error control and the default recovery comparison.

## Beam-width extension

The experiment now also includes `joint_beam`: joint sky/pointing inference with
one shared log-width parameter and a 1% prior. The JSON field
`fitted_beam_width_error` is fractional (0.02 means 2%); `pointing_arcmin` remains
a 16-element array. The 20-seed results and limitations are in
[the first results note](../research/first-results.md). Older five-method results
above remain historical controls, not measurements of the new width-fitting model.
