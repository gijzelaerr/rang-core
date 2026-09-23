# MeerKAT calibration research

Updated 23 September 2026. Active scope; supersedes the original generic low-frequency experiment.

Current active experiment: [gain-TV-guided flagging](flagging.md) on small real
MeerKAT **L-band** data, using QuartiCal full complex 2×2 gains as the training
objective and TV maps as flagging guidance. Preserve every original `FLAG` and
`FLAG_ROW`, maintain recoverable backups, and express the workflow as a Stimela2
recipe. Input telescope metadata must identify MeerKAT and channel centres must
lie within the nominal 856–1712 MHz L band. The first public scan uses
1070–1497.8 MHz for training. This request supplements the previous pointing
research; its original question and controlled experiments are retained below.

Previous focus: [smooth time-varying per-antenna pointing offsets](pointing-solutions.md), using a component-list sky, direct Fourier prediction and JAX automatic differentiation. This explicit user-requested reference path complements the Rust implementation.

Implementation update: the [first runnable toy](../examples/README.md) now tests the pointing/sky ambiguity with Rust and Python. It is an intentionally reduced first stage: eight approximate core coordinates, a Gaussian beam, constant antenna-frame pointing offsets, known bright sky and one uncertain source amplitude. Measured beams, full-array survey geometry and real data remain future steps. Its initial result shows no added benefit from adaptive protection over joint fitting.

## Research question

Can MeerKAT science observations constrain small physical pointing and primary-beam corrections, selected according to their distinguishability from uncertain sky emission, while limiting distortion of faint emission and source spectra?

The project focuses on MeerKAT. L-band continuum imaging is the initial working choice for a focused experiment.

## Why this target

The original MeerKAT array comprises 64 dishes of 13.5 m effective diameter with baselines extending approximately 8 km. Use actual antenna positions, flags and observation metadata for any dataset-based simulation, rather than an invented array or MeerKAT extension layout. [SARAO telescope description](https://www.sarao.ac.za/science/meerkat/about-meerkat/)

L-band primary-beam measurements identify pointing as a leading source of uncertainty in the presumed response. Frequency-dependent beam shape and antenna-to-antenna differences are also relevant. This supports a beam/pointing-first experiment; it does not establish which error dominates a dataset that we have not inspected. [MeerKAT L-band beam measurements](https://arxiv.org/abs/2202.02101)

Holography provides full Jones beam measurements across MeerKAT bands, including antenna-dependent features and elevation/temperature effects. EIDOS provides an existing compact representation of the L-band beam using measured and simulated responses. These are physical starting points, not parameters to rediscover unconstrained from the science sky. [Holography](https://arxiv.org/abs/2301.06752), [EIDOS](https://arxiv.org/abs/1904.07155)

Begin with Stokes-I continuum science over the usable L-band channels. Distinguish nominal digitized coverage (approximately 856–1712 MHz) from the usable, flagged channels of a specific observation. The holography paper describes the band coverage; exact frequencies and channel widths must come from the selected data. Full polarization, spectral-line science and UHF/S-band experiments remain later MeerKAT extensions.

## Physical calibration model

Retain the spherical sky geometry and w-term. Known beam rotation with parallactic angle belongs in the forward model. Neither is an unknown effect that unconstrained gain fitting should compensate for.

In antenna beam coordinates u, model a perturbed voltage Jones beam as

```math
E_p(u,t,\nu)=E_{p,0}(u-\delta_p(t),\nu)
+\sum_k c_{pk}(t)\,\Psi_{pk}(u,\nu).
```

Here E_p,0 is a measured/model reference beam, delta_p is a two-component pointing offset, and Psi contains a small number of justified residual beam modes. Coordinate and polarization basis rotations must be applied consistently with the beam convention. For small pointing offsets,

```math
\delta E_p\simeq
-\delta_{p,1}\partial_{u_1}E_{p,0}
-\delta_{p,2}\partial_{u_2}E_{p,0}.
```

Start by fitting only pointing offsets. Introduce residual beam modes in a separate ablation. Exclude constant gain-like modes and modes duplicating the pointing derivatives, or explicitly constrain the resulting degeneracies. A flexible beam expansion can otherwise make instrumental gain and pointing estimates uninterpretable.

Combine E_p with direction-independent gains in the RIME. Anchor flux scale and bandpass using conventional calibrator information; represent their residual uncertainty rather than assuming that first-generation calibration is perfect. Begin with an unpolarized simulated sky, using the diagonal beam responses consistently. Polarization leakage must be checked before making real-data accuracy claims.

Use smooth time models or state-space priors for pointing corrections, with scales tested against held-out data. A single on-axis calibrator is generally insufficient to constrain both pointing components: informative off-axis sources and time/angle coverage are required. Sky flux and spectral-index uncertainty must participate in the identifiability analysis.

Treat residual phase errors as a diagnostic and controlled nuisance. Add a simple dispersive model when supported by the data, especially in a later UHF experiment. Three-dimensional atmospheric tomography is not a prerequisite. This is prioritization, not an assumption that MeerKAT is unaffected by the ionosphere.

## What might be new

The [current contribution assessment](novelty.md) sharpens this question following the beam-mismatch experiment: selection must consider model-error contamination separately from science-signal distortion. The original single-budget prototype below has not demonstrated an advantage.

Use the uncertain-sky elimination, information comparison and estimator-response constraint derived in the [initial report](calibration-research-2026-09-11.md), now with pointing and beam derivatives in the calibration Jacobian B. Select and regularize combinations that the current observation supports; retain uncertainty for combinations constrained mostly by priors.

Pointing self-calibration is already established, including discussion in Smirnov's RIME treatment. Compact MeerKAT beam models also exist. The candidate contribution is the adaptive selection and explicit science-distortion criterion, not estimating pointing or representing beams with a low-dimensional basis. [RIME calibration and DDEs](https://arxiv.org/abs/1101.1765), [EIDOS](https://arxiv.org/abs/1904.07155)

A December 2025 study applies direction-dependent calibration and visibility-plane mosaicing/beam correction to MeerKAT observations. It is a relevant recent comparator for a later mosaic experiment; the first test stays with a single pointing so mosaicing does not confound the calibration comparison. [Mosaicing paper](https://arxiv.org/abs/2512.16440)

## First experiment

Implementation convention: Rust for simulation and calibration kernels; Python for astronomer-facing APIs, experiment configuration, analysis and pipeline scripting. The simulator is a research instrument for testing the hypothesis. Its first deliverable should be a reproducible baseline-versus-candidate comparison with known truth and controlled errors.

1. Simulate a MeerKAT L-band track using verified antenna positions, broad frequency sampling and changing parallactic angle. Include off-axis compact sources with uncertain fluxes/spectra and faint extended emission. Choose the field from the beam response and relevant contaminating sources; do not inherit the original arbitrary ten-degree field.
2. Generate visibilities with per-antenna beam differences, small time-dependent pointing errors, gain residuals and thermal noise. Use different sky/beam representations for simulation and fitting. Test zero pointing error and accurately known beams as controls.
3. Compare fixed-beam self-calibration, tuned direction-dependent gains, physical pointing self-calibration with uncertain sky, and the same physical model with adaptive mode selection and the response budget. Keep the imager, sky prior, weights, initialization and tuning budget matched where possible.
4. Inject unseen compact/extended sources and spectral perturbations before calibration. Refit and image paired injected/uninjected data. Report flux, spectral-index and morphology recovery, astrometry, residuals, held-out prediction, runtime and memory. A local visibility budget is not automatically an image-domain accuracy guarantee.
5. Stress-test sparse off-axis calibrators, inaccurate source spectra, beam-model mismatch, rapid pointing changes and phase corruption. Reject the claimed benefit if ordinary physical joint inference performs equally well, or if reduced artifacts conceal suppressed emission.

QuartiCal is a natural candidate for gain-calibration comparisons because its published demonstration uses MeerKAT. Choose a wide-field imager with the required beam application and keep it fixed for the first algorithm comparisons. Merely listing software does not establish that a custom pointing solver is implemented in it. [QuartiCal](https://arxiv.org/abs/2412.10072)

After the controlled result, select a public MeerKAT observation with available visibilities and appropriate calibrator/field coverage. Record the observation ID, access terms, beam version and complete calibration/imaging recipe before running the comparison. No observation has been selected or downloaded. Toy results are documented separately and do not establish real-telescope performance.
