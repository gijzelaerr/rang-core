# Changelog

All notable changes to rang-core (PyPI `rang-core`, package `rang`). The
version is set once, in `pyproject.toml`; the three `Cargo.toml`s, the
documentation and `rang.__version__` follow it, and
`tests/test_w4_5_release.py` checks that they agree. Pushing the tag `v<version>`
builds, tests and publishes that version (`.github/workflows/wheels.yml`);
the release notes are the section of this file for that version.

## Unreleased

Nothing yet.

## 0.1.0 (unreleased: dated the day `v0.1.0` is tagged)

First release. A research demonstrator for MeerKAT calibration and
flagging, not an operational calibrator; no advantage over the state of
the art is claimed.

**The Rust core.** The calibration chain of the gain-TV flagging
experiment runs in one Rust core, reached from Python through the PyO3
extension `rang._core`: fused visibility statistics, a QuartiCal-style
gain solver, the component predictor, blosc decoding of the public zarr
stores with HTTP range reads, the Tricolour strategies and SumThreshold,
WSClean imaging weights, a w-stacking gridder and the exact wgridder, a
read-only Measurement Set reader and a casacore table writer that creates
Measurement Sets and CASA calibration tables byte-identical to casacore
3.8.1 and CASA 6.7.6 (bar uninitialised memory). Every port is checked against its upstream oracle
(QuartiCal, Tricolour, AOFlagger, WSClean, python-casacore, casacure) or
against the archived results of the frozen campaigns.

**Simplification and speed.** The solver, the fused pass, SumThreshold and
the gridder run in parallel; the w-stacking gridder and FFT also run on the
GPU through `wgpu` behind the `gpu` feature. The ctypes backend is gone:
importing `rang` or calling a kernel never runs Cargo, and the extension
releases the GIL around every kernel. One command line, `rang-core STAGE
VERB`, writes a `rang.receipt` per call and a `rang.archive` per run. The
frozen QuartiCal and Stimela campaigns, their containers and modules moved
to `history/`; the package keeps verbatim extracts of what the core uses.
The package was renamed from `rangtoy` to `rang` (distribution
`rang-core`). `rang-core --version` and `rang.__version__` report the
version.

**Wheels and CI.** One abi3 wheel per platform for CPython 3.10 and newer:
Linux x86_64 and aarch64 (manylinux_2_28), macOS arm64 and x86_64, and
Windows x86_64, each tested on CPython 3.10 and 3.14 on its own OS with
Cargo absent, with casacure as a second oracle of the table reader and
writer. A `v*` tag that equals the `pyproject.toml` version attaches the
wheels and the sdist to a GitHub release and publishes them to PyPI by
trusted publishing. The sdist holds only the crates, the Python package
and the tests the wheel runs.

**Documentation.** A Sphinx site (<https://gijzelaerr.github.io/rang-core/>)
with installation, concepts, the command line, the API reference and the
research story; five executed tutorial notebooks (data and rank, flagging
step by step, gains and TV, imaging, the flagging experiment) and two
science notebooks (the gain-TV verdict; beam and pointing).

**Science verdicts.** The gain-TV-guided flagging experiment is closed as
null: on LUNO 1934−638 at four stations and across the whole array, on
PKS 1830−211 under a stored and a scalar model, under CARACal's field model
and with a closure-invariant arm, 90 pre-registered calls gave 64 null and
26 undecidable, none better or worse, and the method costs 4.6–5.9× the
baseline. The solver study changed no default (the QuartiCal issue 452
weight fix is opt-in through `RANG_SOLVE_OPTIONS`). For beam and pointing,
the SARAO holography beam is the reference and the SARAO/SKA Gaussian
pointing fit is ported bit-exact; the identifiability survey finds
per-antenna pointing and squint constrainable on the calibrator and ESO137
data, array-common pointing and ellipticity on the ESO137 track, and beam
width nowhere. Pointing self-calibration against those baselines is the
next step. Negative results are kept in `research/`.
