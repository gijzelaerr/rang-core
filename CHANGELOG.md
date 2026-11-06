# Changelog

All notable changes to rang-core (PyPI `rang-core`, package `rang`). The
version is set once, in `pyproject.toml`; the three `Cargo.toml`s, the
documentation and `rang.__version__` follow it, and
`tests/test_w4_5_release.py` checks that they agree. Pushing the tag `v<version>`
builds, tests and publishes that version (`.github/workflows/wheels.yml`);
the release notes are the section of this file for that version.

## Unreleased

- New: the Stimela2 recipe `recipes/rang-chain.yaml` runs `rang-core flag`, `calibrate`, `apply`
  and `image` in order on one configuration and MS, with the cabs `rang-flag`, `rang-calibrate`,
  `rang-apply` and `rang-image` in `recipes/rang-cabs.yaml`; each cab runs the console script
  (`research/w5-stimela.md`). The recipes `recipes/core-*.yaml` are unchanged in their steps and
  now start with `# rang-recipe: research`: they replay frozen campaigns. `tests/test_w5_recipes.py`
  checks the marker on every recipe and the cabs' arguments against the commands.
- New: `rang.cal_pol`, the polarisation terms in CARACal's order (`research/c6-polterms.md`): `gpol`
  (phase-only G with the parallactic angle), `kcross` (CASA's cross-hand delay FFT), `xf` (CASA's
  cross-hand phase), `df` (the linearised leakage by least squares with CASA's subtractive reference),
  `clip_df`, `parallactic_angles`/`row_angles` (CASA's frame by default, provisionally; `frame='rang'`
  keeps the geodetic one), `rotate` and `apply` (tables, then P). Rust kernels
  `core/src/cal/parang.rs`, `crosshand.rs`, `leakage.rs`; `cal/apply.rs` and `formats/caltable.py`
  now apply `Kcross Jones` and `Xf Jones` tables. Not wired into `rang-core calibrate` yet (task C2e).
  `rang.simtruth` gains the versions `poldx` and `polholdout` (CASA's parallactic frame, a leaking
  reference antenna); the other versions are unchanged.
- New: `rang-core calibrate` runs CARACal's cross-calibration terms K, G, B, A and F in C1's order
  (`research/c2e-calibrate.md`). The config's `calibrate.primary` and `calibrate.secondary` terms
  go to `rang.cal_chain.run`: K (`delay_and_offset`), G and B with their listed tables pre-applied,
  written as CASA tables in the run directory; F appends a G solved on the secondary against a
  unit point model to a copy of the primary's last G, then `fluxscale`, and the fitted flux densities
  go into the summary; A applies the section's last table of each type to its fields
  (CORRECTED_DATA, `calflag`) and runs the Tricolour port on the corrected data, OR-ing its flags
  into FLAG (CARACal runs tfcrop there). `rang-core apply` applies these tables through
  `rang.applycal` with each target's `interp` and `gainfield`. calibrate now saves and restores a
  flag version like the other writing stages. A K table applied without a G or F is reported:
  its phase offsets are left for G. Refusals no longer name C2a to C2d; what the `complex` term
  never takes is a configuration error pointing to the K, G and B terms. `refant: auto`,
  `solnorm: true` and `calmode: a` are refused as not ported.
- Changed: `rang.cal_gain.gaincal`, `rang.cal_delay.gaincal`, `rang.cal_bandpass.bandpass` and
  `rang.applycal.applycal` take `scan` (a list of SCAN_NUMBERs); the solves take
  `weight_column=None` for unit weights and read a WEIGHT column per channel. Defaults are
  unchanged. `rang.simtruth` has a held-out version `holdout128` (new seeds).
- Added: polarised calibrator models (task C7a, `research/c7a-polmodels.md`).
  `rang.calmodels.Manual` takes CASA `setjy(standard='manual')`'s full form, `fluxdensity=[I, Q,
  U, V]`, `polindex`, `polangle` and `rotmeas` (referenced to `reffreq`, as CASA), following
  CASA's tabular and spectral-index paths, and writes all four correlations in the sky frame
  (`XX = I+Q`, `XY = U+iV`, `YX = U-iV`, `YY = I-Q`; no parallactic angle, as `setjy`).
  With one `spix` term it copies CASA's TOPO-to-LSRK conversion of channel 0
  (`calmodels.lsrk_over_topo`, astropy; recorded in the receipt), within 1.5e-7 of CASA.
  `calmodels.NRAO_XCAL` and `caracal_xcal()` hold CARACal's 3C286 and 3C138 models.
  `rang-core calibrate` accepts `calibrate.model.flux_jy` with Q, U, V and the polarisation
  keys for `source: manual`; `polindex` without `polangle` (or the reverse) and the polarisation
  keys with another source are refused. Polarised sky-model components stay refused.
- New: `rang-core flag`, `calibrate` and `apply` run within `data.memory_limit_gb` (default 8 GiB of
  resident memory) by chunking by time and row (`rang.core_chunks`, `research/w3-chunking.md`):
  the flagger takes blocks of baselines of a field and scan on the group's whole time grid
  (`core_flag.flag_rows(time_grid=...)`), the `complex` solve takes chunks of whole solution
  intervals (time bins, or frequency bins of one time bin) and replays the solver's global stop
  test over them, so gains equal the one-call solve bit for bit, and apply and the models use row
  chunks of the limit. Results do not depend on the limit or on `data.chunk_rows` (now a cap on
  the rows of every chunk), so neither enters a stage's configuration hash. A limit too small for
  the process, one baseline of a scan or one solution interval is refused before anything is
  written, naming the GiB needed. No visibility column is read whole by the three stages;
  `cal_gain` and `cal_delay` read only the rows of the field they solve. The K, G, B, A and F
  terms are not chunked yet: a field they would read beyond the limit is refused, naming the GiB
  needed.
- New: A1's generator has a `w3` version (64 antennas, 4096 channels) and `--chunk-ints`.

- Changed: `rang-core flag`, `calibrate`, `apply`, `image` and `config check CONFIG MS` check the
  Measurement Set per stage before anything is written and report every problem at once, each
  naming its reason (`research/w4-unsupported.md`). Refused: several data descriptions in use
  (split one spectral window out first), circular, single or reordered correlations, two
  correlations for `calibrate` and `apply` (the complex term needs four), no FLAG or FLAG_ROW,
  no weights for `calibrate` (unless `data.weights: uniform`) or `image`, a FIELD_ID without a
  FIELD row, a named field or a `data.scans` selection with no rows, a FIELD name of several
  fields in `image.fields`, and `image` when `data.scans` leaves out a scan of an imaged field
  (gemclean has no scan selection), on a data description other than 0 or with a
  WEIGHT_SPECTRUM column whose cells were never written. Two linear correlations (XX, YY)
  are now flagged and imaged. Autocorrelations are flagged and corrected but left out of the
  `complex` solve; `calibrate` reads WEIGHT when row 0 of WEIGHT_SPECTRUM has no cell of the
  DATA shape, and `image` refuses such an MS because gemclean would stop on it.
  `data.weights: uniform` for imaging is still refused, now naming W4 (an owner decision).
- New: `rang.cal_fluxscale`, the flux-scale term F (`research/c2d-fluxscale.md`). `fluxscale(caltable,
  reference=..., transfer=...)` is CASA's `fluxscale` on a G table, with its statistics in the Rust
  core (`core/src/cal/fluxscale.rs`): per-antenna mean amplitudes, the median ratio to the reference
  (casacore's median rule), `fd = ratio²` and CASA's error, `gainthreshold`, several reference
  fields, `refspwmap`, and the weighted spectral fit across windows (`fitorder`); it returns the
  flux-scaled table and a record shaped as CASA's. `bootstrap(ms, primary, secondary)` runs
  CARACal's F step: G on the secondaries against a unit point model (`smodel_array`), appended to a
  copy of the primary's table (`append`), then `fluxscale`. Selections by antenna, time or scan and
  `incremental=True` are refused. Measured against CASA 6.7.6 `fluxscale`: the same flux densities,
  errors and F tables as CASA on CASA's own G tables (fit errors at `fitorder=2` within 2.6e-5), and
  within 4e-4 end to end.
- Changed: `rang.cal_gain.gaincal` takes `spw` to solve one window of a multi-window MS (tables are
  pre-applied on single-window data only).
- Changed: `examples/a1_simtruth.py generate` takes `--seeds` and `--gcal-flux`, `--gcal-spix`,
  `--gcal-reffreq` (the default versions are unchanged).

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

- Changed: `rang.cal_delay` solves K as QuartiCal 0.2.7's `delay_and_offset` by default (a delay
  and a free phase per antenna and hand, `core/src/cal/delay_offset.rs`), with rang's offset start
  (the FFT peak's phase, `offset_start=True`; `False` is QuartiCal's estimator exactly) and a delay
  error with the offset marginalised; `kind="delay"` keeps C2b's term. It meets CASA's
  `gaincal(gaintype='K')` with nothing pre-applied, as CARACal solves K. The `K Jones` table holds
  the delays only; the offsets are in `DelaySolution.offsets` and G absorbs them
  (`research/c2c-bandpass.md`).
- New: `rang.cal_bandpass`, the bandpass B: `diag_complex` per channel in Rust with CASA's rules per
  channel (`minblperant`, `minsnr`, the reference antenna) and CASA's `fillgaps`
  (`core/src/cal/bandpass.rs`), `bandpass(ms, ...)` as CASA's `bandpass(bandtype='B')` (defaults
  `combine='scan'`, `fillgaps=0`), writing CASA `B Jones` tables. `rang.cal_chain.primary` solves
  the primary calibrator's K, G, B in CARACal's order, each with the earlier tables applied.
  `rang.simtruth` has a `holdout256` version (new seeds, 256 channels) (`research/c2c-bandpass.md`).
- New: `rang.cal_delay`, the delay term K in Rust (`core/src/cal/delay.rs`): QuartiCal 0.2.7's
  `delay` kernel with its FFT initial estimate (FFT, then Gauss-Newton over all baselines).
  `solve(...)` on arrays; `gaincal(ms, ...)` as CASA's `gaincal(gaintype='K')`, with CASA's
  solution intervals, pre-applied tables through `rang.cal_apply` (SIGMA weights then, as
  `rang.cal_gain`) and CASA's K referencing (to the first refant, no flex or strict, no `minsnr`
  or `minblperant`, which CASA's K does not apply); `to_caltable` writes a CASA `K Jones` table
  (float32 delays in ns, the one-channel window at the band centre), which `rang.cal_apply`
  applies. It matches CASA only with a G pre-applied; without one, antenna phases bias it
  (`research/c2b-delay.md` section 6; the K model is an owner decision). `rang.simtruth` has a
  `delay50` version (delays of 1-50 ns, 256 channels) (`research/c2b-delay.md`).
- Changed: `gemclean` needs far less memory, with byte-identical images (task G2,
  `research/g2-memory.md`). It reads the Measurement Set at the exact size with Stokes I in single
  precision, compacts in place, keeps no copy of the gridding weights, holds single-precision
  visibilities as read, forms each residual in the gridder's sorted values instead of a
  visibility-sized buffer, forms the 2n PSF before the plan of the image grid and frees it after
  the beam is built. Peak RSS on the ESO 137-006 pilot at 512 channels went from more than 24 GB
  (about 32 GB estimated) to 19.7 GB; at 256 channels from 18.4 to 12.2 GB; on 2048² simulated
  skies from 3.46 to 2.99 GB.
- New: `gemclean -memory-report` prints the heap held per phase of a run (read, weights, PSF,
  beam, each major cycle) and the main buffers' sizes; `-report.json` carries the same under
  `memory` (`research/g2-memory.md`). Images are unchanged.
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
