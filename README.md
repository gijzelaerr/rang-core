# Rang

Radio Astronomy Next Generation — experimental MeerKAT calibration and flagging.

Rang investigates smoothly time-varying antenna pointing errors together with
uncertain sky, gains and beam response. It combines component-list DFT prediction
and JAX automatic differentiation with Rust simulation and numerical kernels.

**Status: a tested research demonstrator, not an operational calibrator or a
demonstrated novel algorithm.** The objective is better calibration and imaging
at comparable cost, or comparable quality with substantially less computation.
Neither advantage over state of the art has yet been established.

[Research handoff/index](research/README.md) · [Latest progress](research/STATE.md).

The active real-data flagging experiment trains an interpretable policy using
the TV norm/maps of QuartiCal full 2×2 complex gains, with immutable original
flags, recoverable backups, a flag budget and held-out checks.
[Strategy, first negative result and reproduction](research/flagging.md) ·
[Stimela2 recipe](recipes/tv-flagging.yaml).

[Parallel diagnostic suite](research/flagging-parallel.md) now adds controlled
RFI/oracle tests, a verified SARAO calibrator sky, established flagger comparisons
and measured patch-action learning. These small MeerKAT L-band pilots retain
negative results; lower gain TV does not consistently mean better prediction,
and no flagging or imaging superiority is established.

[Latest flagging findings](research/flagging-findings.md): a TRAIN-only physical
gain-response surrogate predicts the counterfactual objective beyond the known
flag cost (7.26× smaller matched-coverage RMSE in the held-out seed group), while
legitimate smooth receiver phases change TV-guided decisions despite invariant
residual magnitudes. Signed-source controls also show substantial calibration absorption
when the sky is incomplete, even with lower TV and no added flags. These findings
reuse one four-antenna observation; they motivate safer candidate triage,
sky-completeness and signal-preservation controls, not an operational flagger.

## What we have learned

Small dish-to-dish beam differences can masquerade as pointing. In an
eight-antenna simulation with synthetic 1% log-width scatter before removing
the antenna mean:

| Beam treatment | Relative pointing RMSE |
| --- | ---: |
| Ignore antenna differences; fit one shared width | 6.33–9.19 arcsec |
| Fit shared width and seven relative antenna widths | 0.79–1.10 arcsec |
| Supply the exact antenna widths (oracle) | 0.73–1.07 arcsec |

Ranges cover three seeds and two shared-pointing settings. These are matched-family
synthetic tests, not measurements of MeerKAT beam errors. Joint sky/beam/pointing
inference has prior art; this result strengthens our baseline rather than proving
novelty. [Experiment, controls and reproduction](research/antenna-beam-widths.md).

Other findings:

- **Relative and shared pointing must be distinguished.** The solver can impose
  exactly zero antenna-mean relative pointing, following Oleg Smirnov's feedback.
  An optional prior-constrained common trajectory is separate; its physical value
  is not established by the zero-mean convention. [Common pointing](research/common-pointing-priors.md).
- **Gaussian beams admit an exact pointing–sky–gain ambiguity**, including rotating
  elliptical beams when the compensating sky and gain freedom is available.
  [Derivation and numerical controls](research/gaussian-gauge.md).
- **Good residuals do not guarantee accurate astronomy.** Beam mismatch can bias
  flux even with nearly perfect injected-signal response. Relative-pointing
  interval coverage improves when antenna widths are fitted, but shared-mode
  coverage remains less reliable. [Flux-bias control](research/first-results.md) ·
  [Coverage experiment](research/antenna-beam-widths.md#separate-relative-and-common-uncertainties).
- **Negative results are retained.** Earlier mode selection did not improve
  pointing accuracy over a fairly tuned joint fit. Polynomial gain compression
  fails when the fitted order is too low.
  [Mode selection](research/spectral-pointing.md) · [Chromatic gains](research/chromatic-gains.md).

## Scope and limitations

Main experiments use eight approximate MeerKAT core positions, scalar beams,
four frequencies and a small component sky. The DFT includes the non-coplanar
phase. The JAX solver supports smooth pointing, source fluxes/spectral indices,
complex gains and selected beam parameters; it is a reference implementation,
not a streaming or full-polarization pipeline.

The katbeam adapter provides a simplified holography-informed scalar response,
not complete measured antenna Jones beams. A public Measurement Set reader has
been exercised, but antenna-label and pointing-coordinate conventions remain
unresolved. The pointing demonstrator does not establish real-observation
pointing calibration or improved deconvolved images. Actual QuartiCal gain solves
in the separate flagging pilots are visibility-space research diagnostics.
Structured projection benchmarks are not end-to-end calibrator speedups.

[Geometry and provenance](data/README.md) ·
[Real-data inspection](research/measurement-set-inspection.md) ·
[Compute benchmark](research/frequency-blocking.md)

## Run a small example

Requires Rust with edition-2024 support and Python 3.10+ with compatible dependency
wheels. Install from public PyPI in an isolated environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip --isolated install --index-url https://pypi.org/simple -e '.[pointing,beam,test]' ruff
cargo build --offline --release
.venv/bin/python examples/pointing.py --output outputs/pointing
```

This smoke example fits smooth pointing with a fixed, correct Gaussian beam
and sky; it is not the joint antenna-width campaign above. That campaign's
command is in its [experiment report](research/antenna-beam-widths.md#implementation-and-reproduction).
Generated outputs belong in ignored `outputs/`; reusing a destination can replace
previous generated files.

The original Rust toy also runs without Python dependencies:

```sh
python3 examples/toy.py --seeds 7 --no-plot --output outputs/demo
```

[Experiment guide](examples/README.md) · [Full local checks](CONTRIBUTING.md)

## Next research decision

For the active flagging objective, test structured multiscale flag proposals,
noise/support-aware gain-TV diagnostics, signal preservation and independent
MeerKAT L-band transfer. [Flagging research questions and go/no-go criteria](research/flagging-next.md).

The earlier pointing research has enough infrastructure to test a focused hypothesis: can selecting
pointing/beam parameters using separate limits on signal distortion and
model-error contamination beat a well-tuned joint fit? The proposed decision rule
is not yet implemented or validated. The next phase prioritizes a falsifiable
quality/cost comparison, not further simulator expansion.

[Current assessment and verification](research/status.md) ·
[Future plan and go/no-go criteria](research/development-roadmap.md) ·
[Prior-art boundaries](research/novelty.md)

## Repository guide

- `src/`: Rust simulation, fitting and projection kernels.
- `python/rangtoy/`: Python interfaces and JAX inference/audit implementations.
- `examples/` and `tests/`: reproducible experiments and regression tests.
- `research/`: derivations, reports and compact result archives.
- `data/`: fixture provenance and limitations.
