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
[Stimela2 recipe](history/recipes/tv-flagging.yaml).

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

Requires Rust 1.93 (edition 2024) on `PATH` and Python 3.10+ with compatible
dependency wheels. `pip install -e .` builds the core's PyO3 extension
`rangtoy._core` through maturin, so `cargo` must be on `PATH` at install time
(`RUSTUP_TOOLCHAIN=1.93` pins it when a newer default is installed). Install
from public PyPI in an isolated environment:

```sh
python3 -m venv .venv   # or: uv venv -p /usr/bin/python3.14 .venv, where ensurepip is missing
.venv/bin/python -m pip --isolated install --index-url https://pypi.org/simple -e '.[pointing,beam,test]' ruff maturin
cargo build --offline --release
.venv/bin/python examples/pointing.py --output outputs/pointing
```

The core wrappers (`rangtoy.core*`) use the extension when it is importable
and otherwise build and load the C ABI through ctypes at import time, as
before. `RANG_CORE_BACKEND=extension` or `=ctypes` forces one; `RANG_CORE_LIB`
selects ctypes on that library. Both backends give bit-identical results
(`research/core-j-packaging.md`). The Stimela recipes' Python 3.13
environment gets the same `abi3` extension from the same install.

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
- `core/`: the Rust core loaded through ctypes (`rangtoy.core*`): fused
  statistics, the QuartiCal-style solver, the component predictor, blosc
  decoding, WSClean imaging weights and w-stacking gridder, the Tricolour
  strategies (`rangtoy.core_flag`; `core/data/` carries Tricolour's static
  masks under its BSD notice) and a read-only Measurement Set reader
  (`rangtoy.core_ms`; python-casacore is still needed to write tables and
  for the oracle). Reports: `research/core-*.md`.
- `recipes/`: core-native Stimela2 recipes `core-*.yaml`
  (phase 3 stages and the imaging track) driven by `rang-core`
  (`python -m rangtoy.core_cli`), which need no QuartiCal. Stimela 2.1.4 needs
  a Python 3.13 environment; its native backend fails on 3.14.
- The first real-data campaign on the LUNO calibrator slice ran entirely on
  the core (`rangtoy.core_campaign`, `rang-core campaign`;
  `research/core-k-luno-campaign.md`) with a null result, provisional while
  the other caveats of `research/core-k-luno-campaign.md` (licence settled
  by user decision 2026-10-30, `research/big-plan.md`).
- `python/rangtoy/`: Python interfaces and JAX inference/audit implementations.
- `examples/` and `tests/`: reproducible experiments and regression tests.
- `research/`: derivations, reports and compact result archives.
- `data/`: fixture provenance and limitations.
- `history/`: the frozen campaigns' Stimela recipes, container builds,
  wrappers and recipe-only modules, retired from the live tree by task P8
  (`history/README.md`, `research/p8-history.md`).

## Licence

Rang is free software under the GNU General Public License, version 3 or (at
your option) any later version; see [LICENSE](LICENSE). The user chose GPL on
2026-10-29 so that GPL-3 radio-astronomy tools such as WSClean and AOFlagger
can be ported into the core. GPL-2-only upstreams cannot be combined with GPL-3
code, so each upstream's exact licence is checked before porting it. Ported code keeps
its upstream copyright notices. Tricolour 0.2.1 is treated as BSD-3-Clause on
the strength of its `LICENSE` file (`research/core-d-tricolour.md`); Crystalball
is GPL-2.0-only and is not ported.
