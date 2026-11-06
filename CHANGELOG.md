# Changelog

All notable changes to rang-core (PyPI `rang-core`, package `rang`). The
version is set once, in `pyproject.toml`; the three `Cargo.toml`s, the
documentation and `rang.__version__` follow it, and
`tests/test_w4_5_release.py` checks that they agree. Pushing the tag `v<version>`
builds, tests and publishes that version (`.github/workflows/wheels.yml`);
the release notes are the section of this file for that version.

## Unreleased

- Changed: `rang-core flag`, `calibrate`, `apply`, `image` and `config check CONFIG MS` check the
  Measurement Set per stage before anything is written and report every problem at once, each
  naming its reason (`research/w4-unsupported.md`). Refused: several data descriptions in use
  (split one spectral window out first), circular, single or reordered correlations, two
  correlations for `calibrate` and `apply` (the complex term needs four), no FLAG or FLAG_ROW,
  no weights for `calibrate` (unless `data.weights: uniform`) or `image`, a FIELD_ID without a
  FIELD row, a named field or a `data.scans` selection with no rows, a FIELD name of several
  fields in `image.fields`, and `image` with `data.scans`, on a data description other than 0 or
  with a WEIGHT_SPECTRUM column whose cells were never written. Two linear correlations (XX, YY)
  are now flagged and imaged. Autocorrelations are flagged and corrected but left out of the
  `complex` solve; `calibrate` reads WEIGHT when WEIGHT_SPECTRUM has no cells, as gemclean does.
  `data.weights: uniform` for imaging is still refused, now naming W4 (an owner decision).
- New: `rang.applycal.applycal(ms, gaintable, interp, gainfield, calwt, field)`, CASA's
  `applycal` on a Measurement Set: row chunks through `rang.core_writeback` (a flag version first),
  the Rust kernel per field and data description, CORRECTED_DATA (added as `clearcal` does when
  absent), FLAG OR'd, and with `calwt` on a G, T or B table WEIGHT and WEIGHT_SPECTRUM reset from
  SIGMA and scaled as CASA does (K, Df and general Jones terms leave weights alone). Field maps
  `''`, a field name and `nearest` as CASA's. Measured against CASA 6.7.6 `applycal`
  (`research/c4b-apply-ms.md`).
- Changed: the apply kernel (`rang.cal_apply`) writes cells under a one-sided diagonal solution flag
  as CASA does (the good side still applied), tracks phases over the two slots it interpolates
  between, and uses casacore's linear-interpolation formula; new `cal_apply.apply_jones` applies
  a general 2×2 term on its own solution bins.
- New: `rang-core apply` applies the `complex` terms of `rang-core calibrate` to the fields they were
  solved on, into CORRECTED_DATA; `rang-core calibrate` writes `setjy`, `manual` and `lsm` models to
  MODEL_DATA through `rang.calmodels` and solves against them. Applying a complex term to another
  field and polarised models are refused, naming C2a and C7a.

- New: `rang.calmodels`, calibrator models written to `MODEL_DATA` as CASA's `setjy` writes them
  (C1 term T0). `set_model(ms, field, spec)` takes a flux-density standard of `rang.fluxstd`, a
  `manual` model (flux density, reference frequency, log10 spectral terms), per-channel Stokes rows
  (`PointStokes`), or a component list such as CARACal's `pks1934-638.lsm`, predicted through
  `core.predict_components`. It writes through `rang.core_writeback` and leaves other fields'
  rows as they are. Polarised `manual` models are refused until C7a (`research/c3a-models.md`).
- New: commands for your own Measurement Set, `rang-core flag`, `calibrate`, `apply`, `image`,
  `selfcal` and `run CONFIG MS`, driven by one YAML configuration (schema `rang-config`, version
  1; `rang-core config defaults` prints every key with its default, `rang-core config check`
  validates). `flag` runs the Tricolour port per field and scan and writes FLAG; `calibrate`
  solves the `complex` term and writes a QuartiCal gain store; `image` runs `gemclean`. The rest
  of CARACal's chain (K, G, B, F, polarisation terms, apply, self-calibration, multi-channel and
  polarised imaging) can be written in the configuration and is refused with the task that adds
  it. A run directory (`<ms>.rang-run`) keeps the state, so `run` skips finished stages and
  resumes at a failed one. Flags are saved as the CASA flag version `rang_original` before the
  first write, and as `rang_<stage>_<time>` before each stage writes (`research/w2-commands.md`).
- Changed: the research stages moved under `rang-core research` (for example `rang-core research
  flags compare`); the old top-level forms now say where they went. PyYAML is a dependency.
- New: `rang.cal_gain`, the gain term G in Rust (`core/src/cal/diag.rs`, `reference.rs`):
  diagonal complex (`calmode='ap'`) and phase-only (`'p'`) solves ported from QuartiCal 0.2.7's
  `diag_complex` and `phase` kernels, with CASA's solution intervals (`solint`, `combine`),
  `uvrange` (metres), `minblperant`, `minsnr` and reference antenna (`flex`, `strict`); earlier
  tables are pre-applied through `rang.cal_apply`, and the result is a CASA `G Jones` table
  (`research/c2a-gain.md`).
- `tools/check-all.sh` has a new last step, `gain-hashes` (`tools/gain_hash_gate.py`): it recomputes
  the archived `complex` gains (`4ed2aa89…`, `7b370c13…`) and core phase 2's LUNO convergence, and
  fails on any change. The archived inputs are found in `$RANG_ARCHIVE_OUTPUTS`, `outputs/` or
  `~/Github/rang/outputs`; `RANG_GAIN_HASHES=optional` skips the step on a host without them.

- New: `rang.core_writeback`, write-back to an existing Measurement Set. `WriteBack` adds
  `MODEL_DATA`, `CORRECTED_DATA` (or any data column) and `WEIGHT_SPECTRUM` as CASA's `clearcal`
  adds them, writes any column, `FLAG` and `FLAG_ROW` in row chunks, saves the original flags as a
  CASA flag version (`rang_original`) before the first write, and refuses to start after an
  interrupted session until the flags are restored (`restore_flags`). `rang.formats.flagversions`
  now saves in chunks, atomically, and gains `restore`. CASA, WSClean, python-casacore and dask-ms
  read the written columns (`research/w1-writeback.md`).
- The core table writer now writes a tiled column's header through a temporary file and a rename,
  so a process killed during a flush cannot leave it truncated. The bytes written are unchanged.

- New: `rang.simtruth` and `examples/a1_simtruth.py`, a simulated MeerKAT L-band observation in
  full polarisation with known truth. It has K, B, G, KCROSS, Xf, linear Df and parallactic
  rotation, a self-calibration residual, RFI with bit masks, and thermal noise of known σ, and is
  written as a Measurement Set through rang's table writer. There are two versions: small (16
  antennas, 64 channels, 41 MB) and full (64 antennas, 256 channels, 35.8 GB). CASA
  `applycal` with tables made from the truth inverts it within class C
  (`research/a1-simtruth.md`).
- New: `rang.cal_apply.apply`, a Rust kernel (`rang._core.cal_apply`) that corrects or corrupts
  visibilities in memory by CASA K, G, T, B and Df tables, with `applycal`'s `linear` and `nearest`
  interpolation in time and frequency and its `calflag` flags, including how Df flags and
  substitutes bad leakages (`research/c4a-apply.md`). KCROSS, Xf and the parallactic angle are
  refused until their steps. Weights are not changed and nothing is written to a Measurement Set yet.
- New: `gemclean -beam-band`, off by default. Resyncs use the beam's spectrum only as far as the
  longest baseline and the w-term reach. Images differ slightly from flag off. Over 12 interleaved
  pairs with coarse gridding (`-single -wgridder-accuracy 1e-4`) it saved 11-16 % of the wall on
  two simulated skies and 4-5 % on a third (`research/gemclean-speed.md`).
- The root crate and binary are now `rang-sim`, `rang.toy_output` is now `rang.sim_output`,
  `RANG_TOY_BIN` and `RANG_TOY_LIB` are now `RANG_SIM_BIN` and `RANG_SIM_LIB`, and
  `examples/toy.py` is now `examples/pointing_sim.py`. No aliases are kept. Output bytes are
  unchanged. Receipts are `rang.receipt` version 4.
- `gemclean` takes w-planes in groups of 4, within 2 GiB of grids. Results are unchanged; peak
  memory rises (2.84 to 3.38 GB on one simulated job). Other callers of the exact gridder stay at
  one plane, because larger groups were measured only on gemclean. `RANG_WGRIDDER_PLANE_GROUP`
  overrides either default.
- New: the reference imager `gemclean` and its binary, and the flagged Gram operator. Their
  speed figures are provisional.
- New: `gemclean -stop-rule certified`, a minor-cycle stop rule with Lean-proved consequences
  (`research/stop-rule-theorem.md`). It costs about three times the default's major cycles and a
  table of about 100 gridder calls, so it is not the default, and the default's images are unchanged.

## 0.1.0 (2026-11-02)

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

**Documentation.** A Sphinx site (<https://pythonic.nl/rang-core/>)
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
This covers a gain-TV-guided threshold policy; a flagger trained on gain TV
is a separate question, not yet tested.

**Provenance and the wheel (wave 4 fixes).** Receipts (`rang.receipt`
version 3) record every result-affecting `RANG_*` variable from one registry
and the package source; the solver takes its options as an argument; `commit`
is null outside a checkout (W4-1). The closure and flux-standard kernels run
in the extension, so no kernel call builds with Cargo and the wheel is
self-contained (W4-3).
