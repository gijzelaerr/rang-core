# DF-IO: the file formats of the tools the core replaces

Task DF-IO of [big-plan.md](big-plan.md) (the user's decision of
2026-10-30: the core reads and writes the formats of the tools it replaces,
not just converts them for oracle runs), with the survey's sub-tasks
DF-IO-CT, DF-IO-H5 and DF-IO-SKY ([ecosystem-survey.md](ecosystem-survey.md)
sections 3.3, 5.2 items 3, 5 and 6, 5.3 and 5.4). Branch `dfio-formats`
from `main` `368e8ca`. Each format is judged by its own tool as the oracle.
A reimplementation of a file format is not a scientific contribution
(AGENTS.md); no archived result changes because of it.

Status: **implemented and measured (2026-10-30; runs
`outputs/dfio-20261030-01` to `-04`, archive
[results/dfio-formats.json](results/dfio-formats.json)).** Passing as
frozen: CASA caltables read (K, G, B, Df, T) and written (bytes equal to
CASA's except the masked gaps, `applycal` bit-identical); QuartiCal stores
read and written (metadata byte-identical, QuartiCal 0.2.7 `load_from`
applies the core's store bit-identically, a core-made store to 5.9e-8);
Tigger ASCII read and `.lsm.html` written and read; WSClean lists read and
predicted by Crystalball within the float32 bound (99.95 % of cells
bit-identical); DicoModel read; ClusterCat read and written; killMS
solutions written and merged by `MergeSols` (G identical); CASA flag
versions restored by `flagmanager`. Failing as frozen: the core's own
applycal model to 1e-6 relative (post hoc after three fixes: K, G, B, T
within 4.5e-7 on CASA's tables, Df and the chain off by up to 6.9e-5
relative where cross hands cancel, all within 10.3 float32 epsilons of the
cell), WSClean text shapes value-exact (9 axes 1-2 ulp; post hoc 4 at 1 ulp,
a limit of arcsec text), Tigger ASCII and BBS against Tigger (Tigger's own
writer and reader defects), and the H5parm (frozen run: a setup error in the
reference values and DP3 refusing a three-field MS; post hoc losoto reads
and writes it exactly and DP3 `applycal` applies it to 4.0e-7). Results are
added below the protocol; this status line is the only edit above it.

## Protocol (frozen before any DF-IO code)

Frozen in the commit that adds this file. Before freezing, the following
were read (sources, not measurements): the PyPI sdists of killMS 3.3.0,
DDFacet 1.0.0.0, Crystalball 0.4.3, astro-tigger-lsm 1.8.0, losoto 2.7.1
and QuartiCal 0.2.7 and the DP3 6.6.0 cp312 wheel listing (in
`~/Build/tmp/20261030-dfio/src`, untrusted, never executed); CASA's
`KJones.cc`, `DJones.cc`, `CTTimeInterp1.cc`, `CTMainColumns.cc` and
`VisCal.h` from the `dic-case-studies/casa6` mirror; the opcode list of
the trusted DDFacet `img.DicoModel` of
`outputs/ddfacet-feasibility-20261030-01/runs/clean-hmp` (`pickletools`,
nothing unpickled). One scratch measurement was made: CASA 6.7.6
`flagmanager(mode='save')` on a copy of O-CASA's `c.ms` (2.3 s,
`~/Build/tmp/20261030-dfio/fv`), to learn the layout of a flag version:
`<ms>.flagversions/FLAG_VERSION_LIST` (`name : comment` lines) and
`flags.<name>`, a table with FLAG in a TiledShapeStMan (hypercolumn
`TiledFlag`) and FLAG_ROW in a StandardStMan, `table.info` readme
`!TablePlot Flag Table : <name>`. Both managers are ones E4 creates.

### Oracles and data (frozen)

- **CASA 6.7.6.14**, `rang-o-casa:6.7.6.14` ([o-casa.md](o-casa.md)), run
  as E4 ran it (`--network none`, `--tmpfs /tmp -e HOME=/tmp`,
  `OMP_NUM_THREADS=4`, this user, inputs read-only, one fresh
  `outputs/dfio-20261030-NN` mounted writable). The same image has WSClean
  3.7 (`wsclean=3.7-1kern1`) and python-casacore 3.7.1.
- **`rang-formats-oracle:20261030`**, built from
  `tools/formats-oracle/Dockerfile` (Ubuntu 24.04 at O-CASA's base digest,
  Python 3.12, public PyPI): venv `/opt/qc` QuartiCal 0.2.7; `/opt/sky`
  astro-tigger-lsm 1.8.0 and Crystalball 0.4.3; `/opt/h5` losoto 2.7.1 and
  DP3 6.6.0 (the wheel bundles libDP3 with casacore and HDF5, entry point
  `DP3.py`); `/opt/ddf` DDFacet 1.0.0.0 and killMS 3.3.0
  (`CFLAGS=-Wno-error=incompatible-pointer-types`, as the feasibility
  study). The resolved closures are recorded in
  `tools/formats-oracle/*.lock` and the image digest in the archive. Runs
  with `--network none`, this user, `HOME=/tmp`, `--tmpfs /tmp`.
- **python-casacore 3.8.1** in `rang-ms-reader:local` for table dumps.
- **Data** (read in place, never written; copies are written):
  - O-CASA's `outputs/o-casa-20261030-01/c.ms` (J1939−6342, 4 stations,
    192 rows, 32 times, 2048 channels, linear feeds) and E4's CASA tables
    `outputs/e4-20261030-01/casa/x.{K,G,B,Df}` (made by CASA 6.7.6 on a
    copy of `c.ms`, O-CASA arm C settings);
  - the LUNO export `outputs/luno-solve-20261029-02/work.ms` and QuartiCal
    0.2.7's archived store `outputs/luno-solve-20261029-02/solve/gains.qc`
    (term G, complex, 16 × 64 × 4 × 1 × 4);
  - CARACal's `pks1934-638.lsm` as fetched by L1-M
    (`outputs/l1m-20261030-00-fieldmodel/pks1934-638.lsm`, SHA256
    `0964b9f4…d101`, checked before use). It is GPL-2.0 CARACal data and is
    not committed (as L1-M); tests use synthetic models;
  - DDFacet 1.0.0.0's `img.DicoModel` and `img.NodesCatImaged.npy` from
    `outputs/ddfacet-feasibility-20261030-01/runs/clean-hmp` (made on this
    host by the feasibility study: trusted).
- Seeds: 20261030 for every synthetic gain and model.

### Acceptance kinds (frozen)

- **bit-exact**: equal bytes (files) or equal values with dtype (arrays;
  NaN payloads and signed zeros count).
- **value-exact**: every value the oracle exposes equals the core's value
  (float64 equality), where the text or container round-trips values
  (`repr` floats) but its bytes are not deterministic or not reproducible.
- **float32-exact (predicted visibilities)**: for complex64 visibilities
  `V_core`, `V_oracle` of one model,
  `max |V_core − V_oracle| ≤ 2^-22 · Σ_k |S_k(ν)|` per channel (the sum of
  the component fluxes; two float32 roundings of a sum of that size),
  reported also as the maximum in ulps of `|V|`.
- **1e-6 relative**: `max |V − V_expected| / |V_expected|` over unflagged
  cells with `|V_expected| > 0`, as E4's criterion 4.

### Formats in scope, round trips and acceptance (frozen)

**F1 CASA calibration tables (DF-IO-CT), read and write.**
`rang.formats.caltable` reads a CASA `NewCalTable` (G, B, K, T, Df) into a
`CalTable`: per row TIME, INTERVAL, FIELD_ID, SPECTRAL_WINDOW_ID,
ANTENNA1, ANTENNA2 (the reference antenna, −1 when none), SCAN_NUMBER,
OBSERVATION_ID, the parameters (CPARAM or FPARAM, `[nchan, npar]`),
PARAMERR, FLAG, SNR, WEIGHT definedness; keywords (ParType, MSName,
VisCal, PolBasis, CASA_Version), `table.info` and the five subtables; and
the VisCal semantics: type from `VisCal`, parameter layout (G/B/T complex
diagonal, `npar` 2 or 1 for T; K float delays in ns; Df complex leakage
`[[1, d0], [d1, 1]]`), the solution frequency grid from the caltable's
SPECTRAL_WINDOW, the K reference frequency (`CHAN_FREQ[nchan // 2]` of the
caltable window, CASA ≥ 5.3 rule in `KJones::setApply`) and the reference
antenna. It writes a `CalTable` through E4's `create_caltable`.

- *CT-read*: the core's `CalTable` of each CASA table (K, G, B, Df from E4,
  and a T table made now by `gaincal(gaintype='T', solint='120s',
  calmode='p', gaintable=[K], refant='m000', minblperant=3)` on a copy of
  `c.ms`) equals python-casacore 3.8.1's dump of every column, cell
  definedness, keyword and `table.info`: bit-exact.
- *CT-write-identity*: each CASA table read into a `CalTable` and written
  back by `rang.formats.caltable.write` gives E4's byte rule (every file
  equal, only the masked `table.fNi` alignment gaps excepted) and
  `applycal` (E4's `casa-apply` settings: `applymode='calflag'`,
  `interp='linear'`, `gainfield='nearest'`, `calwt=False`, `parang=False`)
  with the core's K, G, B, Df gives CORRECTED_DATA and FLAG bit-exact
  against `applycal` with CASA's tables on another copy of the MS.
- *CT-semantics*: for each type alone (K, G, B, T, Df) and for the chain
  K, G, B, Df, the core's own correction from the read `CalTable` equals
  CASA `applycal`'s CORRECTED_DATA (same settings, one copy of `c.ms` per
  case) to 1e-6 relative, and the flags of flagged solutions are applied.
  The core's model, frozen from CASA's sources: VisCal order B, K, G, D,
  T (`VisCal::Type`), so corrected = `D_p⁻¹ (Π_diag)_p⁻¹ V (Π_diag)_q⁻ᴴ
  D_q⁻ᴴ`; K phase `2π τ[ns] (ν − ν_ref)[GHz]`, Jones `exp(iφ)`; time
  interpolation `linear` per (antenna, window): amplitude and phase with
  the phase tracked along the antenna's rows (`RIorAPArray::f(true)`),
  float32 times relative to `floor(t₀ − 1)`, nearest slot outside the
  solution range, exact slots taken as they are, the flag of either
  bracketing slot flags the result; B per channel on equal grids; G, K, T
  and Df constant across the window.
- *CT-synthetic*: G (several solutions per antenna across the scan,
  seeded, two flagged), B (per channel, seeded, a flagged channel range), K
  (seeded delays) and T written by the core from its own gain arrays with
  subtables from `c.ms`; `applycal` with each, and with G+B+K, equals the
  core's correction (the same model) to 1e-6 relative with solution flags
  applied.

**F2 QuartiCal gain store, read and write.** `rang.formats.quartical_store`
reads and writes the dask-ms zarr layout QuartiCal 0.2.7 writes
(`daskms.experimental.zarr.xds_to_zarr`): `<store>/<term>/<term>_<n>/` per
partition with `.zgroup`, `.zattrs` (`DATA_DESC_ID`, `FIELD_ID`,
`FIELD_NAME`, `SCAN_NUMBER`, `NAME`, `TYPE`, `GAIN_AXES`, `GAIN_SPEC`,
`__daskms_zarr_attr__`), consolidated `.zmetadata`, the coordinates
`gain_time`, `gain_freq`, `antenna`, `direction`, `correlation`,
`time_chunk`, `freq_chunk` (and `param_time`, `param_freq`, `param_name`
for parametrised terms) and the data variables (`gains`, `gain_flags`,
`jhj`, `conv_iter`, `conv_perc`, `params`, `param_flags`, ...). Reads use
the core's blosc decoder (`rang.core_zarr`); writes store each chunk as a
valid blosc frame without compression (the memcpyed flag), metadata JSON
as zarr writes it (indent 4, sorted keys).

- *QC-read*: every variable, coordinate and attribute of QuartiCal's
  archived store, and of a parametrised (delay, `K.type=delay`) store made
  now by QuartiCal 0.2.7 on a copy of `work.ms`, equals
  `xds_from_zarr` in `/opt/qc`: bit-exact values, equal attrs.
- *QC-write*: (a) the core rewrites both stores from its reads: every
  `.zarray`, `.zattrs`, `.zgroup` and `.zmetadata` file is byte-identical
  to QuartiCal's, and `xds_from_zarr` of the core's store equals
  `xds_from_zarr` of QuartiCal's, bit-exact; (b) QuartiCal 0.2.7 applies
  each with `<term>.load_from=<store>/<term>`, `solver.iter_recipe=[0]`,
  `output.products=[corrected_data]`, `output.columns=[CORRECTED_DATA]`
  (the archived solve's other settings) on copies of `work.ms`, and
  CORRECTED_DATA is bit-exact against QuartiCal applying its own store;
  (c) a store the core writes from seeded gains on the archived grid is
  applied by QuartiCal the same way and equals the core's correction
  (`V / (g_p,a conj(g_q,b))` for the complex diagonal plus off-diagonal
  2×2: `G_p⁻¹ V G_q⁻ᴴ`) to 1e-6 relative.
- The comparators' existing dask-ms reads are unchanged.

**F3 sky models (DF-IO-SKY).** `rang.formats.sky` (absorbing
`rang.lsm`, which stays as a compatibility module re-exporting its whole
`__all__`) has one `Source` list for every text format.

- *SKY-tigger-read*: the core's read of CARACal's lsm (Tigger ASCII) equals
  Tigger 1.8.0's (`Tigger.load`) for every source: name, RA, Dec, I, Q, U,
  V, spectral terms, `freq0`, extents and PA, value-exact; a failure of an
  angle by at most 4 ulp (the h:m:s arithmetic order differs) is reported
  as such and does not fail the criterion.
- *SKY-html*: the core writes `.lsm.html`; Tigger loads it value-exact
  against the core's model; `tigger-convert core.lsm.html t.lsm.html` and
  the core's read of `t.lsm.html` is value-exact. Byte identity is not
  required: Tigger renders extra attributes from a Python `set`
  (hash-randomised order); reported under `PYTHONHASHSEED=0`.
- *SKY-ascii*: the core writes Tigger ASCII (`#format:` with `ra_rad`,
  `dec_rad`); Tigger loads it value-exact; `tigger-convert` of the core's
  html to ASCII is read by the core value-exact.
- *SKY-wsclean*: the core writes CARACal's model as a WSClean source list
  (`Format = Name, Type, Ra, Dec, I, SpectralIndex, LogarithmicSI,
  ReferenceFrequency, MajorAxis, MinorAxis, Orientation`); africanus'
  `file_model.load` (Crystalball's parser) reads it, and the values equal
  the core's within the text precision (positions to 1e-12 rad, the rest
  value-exact as `repr`). Crystalball 0.4.3 predicts it into MODEL_DATA of a
  copy of `c.ms` (field J1939−6342, 4 correlations), the core predicts the
  model read from the lsm with the same phase centre: float32-exact on XX
  and YY, XY and YX zero in both. A WSClean 3.7 `-save-source-list` list
  (made now from `c.ms`) is read by the core value-exact against
  africanus' load.
- *SKY-bbs (read)*: `tigger-convert -o BBS` of CARACal's lsm; the core's
  read equals Tigger's read of the same file value-exact.
- *SKY-dicomodel (read only)*: the restricted unpickler (globals allowed:
  `numpy._core.multiarray.{_reconstruct,scalar}`, their `numpy.core`
  aliases, `numpy.ndarray`, `numpy.dtype`, `collections.OrderedDict`;
  anything else refused) reads DDFacet's `img.DicoModel` into the same
  structure as `pickle.load` in `/opt/ddf` (keys, types, dtypes, values:
  bit-exact); a crafted pickle naming `os.system` is refused. Never used
  on untrusted files (documented).
- *SKY-clustercat (read/write)*: the core reads DDFacet's
  `img.NodesCatImaged.npy` bit-exact against `np.load`; the core writes a
  ClusterCat (dtype `Name S200, ra, dec, SumI, Cluster, l, m`)
  byte-identical to `np.save` of the same array in `/opt/ddf`.

**F4 H5parm (DF-IO-H5), read and write.** `rang.formats.h5parm` (h5py, the
`formats` extra) writes `solsetNNN/solNNN/{amplitude,phase}000` with
`val`, `weight` (AXES `time,freq,ant,dir,pol`), the axis arrays and the
`antenna` and `source` tables, with the PyTables attributes losoto uses
(TITLE as the soltab type, CLASS/VERSION).

- *H5-losoto*: losoto's `H5parm` API reads the core's file: soltab types,
  axes, values and weights value-exact; a reference h5parm made by
  losoto's API (`makeSoltab`) in `/opt/h5` is read by the core value-exact,
  and its group, attribute and dtype listing is compared with the core's
  (differences reported).
- *H5-dp3*: DP3 6.6.0 `applycal` (`ac.steps=[amp,ph]`,
  `correction=amplitude000/phase000`) of a core-written h5parm with
  seeded diagonal gains on `c.ms`'s exact time and channel grid
  (no interpolation enters) writes CORRECTED_DATA equal to the core's
  correction `V_pq,ab / (g_p,a conj(g_q,b))` to 1e-6 relative. If DP3
  cannot run in the image, H5-dp3 is recorded as open (losoto-only
  acceptance), as the task allows.

**F5 killMS solutions, read and write.** `rang.formats.killms` writes
`.npz` with `Sols` (record array `t0`, `t1`, `G` complex64
`(nchan, nant, ndir, 2, 2)`, `Stats` float32 `(nchan, nant, 4)`),
`StationNames`, `ClusterCat`, `SkyModel`, `SourceCatSub`, `ModelName`,
`MSName`, `FreqDomains`, `BeamTimes`, with no object arrays (so
`np.load(allow_pickle=False)` loads it); it reads killMS files with the
restricted unpickler for object members.

- *KMS*: two core files covering the two halves of a band (seeded gains,
  2 directions) are merged by killMS 3.3.0 `MergeSols.py` in `/opt/ddf`
  (run in a tmpfs working directory); the merged `G` equals the core's own
  merge (concatenation and `NormMatrices`, the SVD rotation to antenna 0)
  to 1e-6 relative, `FreqDomains`, `MaskedSols`, `t0`, `t1` bit-exact, and
  the core reads the merged file bit-exact against `np.load` in the
  container.

**F6 CASA flag versions (write, low priority).** `rang.formats.flagversions`
writes `<ms>.flagversions/flags.<name>` (FLAG TiledShapeStMan `TiledFlag`,
FLAG_ROW StandardStMan, the readme) and the `FLAG_VERSION_LIST` line.

- *FV*: the core saves the FLAG of a copy of `c.ms` modified by a seeded
  pattern as version `rang_dfio`; CASA `flagmanager(mode='restore')` on a
  copy with the original flags restores exactly the core's FLAG and
  FLAG_ROW (bit-exact), and `flagmanager(mode='list')` lists it. If time
  runs out, F6 is skipped and recorded as open.

Read-only by design: BBS, DicoModel. Out of scope (noted): MSv4 (xradio),
IDIA HDF5, FITS images and the MS/zarr stores (already covered).

### Rules

- Every criterion gates its format; a failure is recorded as measured and
  any later fix is a new run labelled post hoc, the frozen result kept.
- Every tool run is timed (Timings).
- `rang-core formats convert <in> <out>` and `rang-core formats check
  <path>` are tooling, not acceptance; their tests are unit tests.
- Implementation in pure Python plus the existing core writer; Rust only
  where Python is the measured bottleneck.

## Implementation

One package `python/rang/formats/`, pure Python over the core's table
writer (E4) and blosc decoder; `rang.lsm` is a shim over `rang.formats.sky`
(its whole `__all__` and the private helpers L1-M imports). No Rust was
added for speed; one core defect was fixed (below).

- `_aipsio.py`: the table keywords of `table.dat` (the core reader skips
  them), decoded as the Rust parser reads them.
- `caltable.py`: `read` (every MAIN and subtable cell with definedness,
  keywords, `table.info`) into `CalTable` (`kind`, `params`, `flags`,
  `snr`, `reference_antenna`, `solution_frequencies`,
  `k_reference_frequency`, `summary`); `write` through
  `core_ms_write.create_caltable`; `from_gains` (G, B, K, T, Df from the
  core's arrays); `subtables_from_ms`; `correct`, CASA's `applycal`
  (`calflag`, `linear`) as read in CASA's sources: time interpolation of
  amplitude and tracked phase in float32 (`CTTimeInterp1`,
  `RIorAPArray`), frequency resampling with flagged solution channels
  bridged, not flagged (`CTPatchedInterp::resampleInFreq`), the K pivot,
  per-receptor flags of the diagonal terms, and Df as CASA's linear
  approximation (`DflinJones` is `GenLinear`: `JonesGenLin::invert`
  negates the off-diagonals and `applyRight`/`applyLeft` change only the
  cross hands).
- `quartical_store.py`: `read` (every partition, variable and attribute;
  out-of-order blosc blocks included), `write` (metadata JSON as zarr writes
  it, chunks as uncompressed blosc frames), `complex_partition` from the
  core's 2x2 gains, `Partition.gains_2x2`.
- `sky.py`: Tigger ASCII (the L1-M reader) and `dumps_ascii`; Tigger HTML
  (`loads_html` without `eval`, `dumps_html` rendered as `ModelHTML.save`);
  WSClean lists (`loads_wsclean`, `dumps_wsclean` with zero-padded
  spectra and, post hoc, exact arcsec text); BBS read (`Format =` and
  `# (...) = format` headers, `SpectralIndex` lists and, post hoc, the
  numbered `SpectralIndex:k` columns); `load_dicomodel` through
  `RestrictedUnpickler`; `read_clustercat`/`write_clustercat`;
  `load_any`/`save_any`.
- `h5parm.py` (h5py): `write` with PyTables' attributes and NUL-terminated
  strings, `read`, `diagonal_solset`, `diagonal_gains`.
- `killms.py`: `write` (no object arrays), `read` (object members through
  the restricted unpickler), `merge` and `normalise_to_antenna0` (what
  `MergeSols.py` computes).
- `flagversions.py`: `save` (FLAG as a fixed-shape TiledShapeStMan column,
  FLAG_ROW, the description comment, `FLAG_VERSION_LIST`), `load`,
  `versions`.
- `cli.py`: `rang-core formats check PATH` (detect, read, JSON summary;
  a DicoModel only with `--trust`) and `rang-core formats convert IN OUT`
  (sky models among Tigger html/ASCII and WSClean; gain grids from a
  QuartiCal store, H5parm or killMS file to H5parm or killMS).
- Core fix: `core/src/blosc.rs` `block_span` took the next block's offset
  as a block's end, so a chunk whose blocks are stored out of order (as
  QuartiCal's multithreaded blosc writes its delay store's `gains`) failed to
  decode. A block now ends at the nearest larger start; a Rust test covers
  it. `core_zarr.read_rows` decodes such a chunk whole.
- Oracles: `tools/formats-oracle/Dockerfile` and its four locks
  (`qc.lock`, `sky.lock`, `h5.lock`, `ddf.lock`), image
  `rang-formats-oracle:20261030` (`sha256:6ddf0359…b89b`, 3.5 GB);
  `examples/oracle_formats.py` (container side) and
  `examples/check_formats.py` (host: steps `ct`, `qc`, `sky`, `h5`, `kms`,
  `fv`, `summary`). `tests/test_dfio_formats.py`: 16 unit tests on
  synthetic data and the archive's structure (no Docker; h5py optional).

## Runs

| Run | What | Label |
| --- | --- | --- |
| `outputs/dfio-20261030-01` | CT, FV and H5 (verdicts: H5 failed on a setup error in the reference values and on DP3 refusing three FIELD rows); first attempts of QC (stopped in the core decoder), SKY (stopped in Crystalball) and KMS (stopped in the core reader), none of which produced a verdict | frozen |
| `outputs/dfio-20261030-02` | CT after the three model fixes | post hoc |
| `outputs/dfio-20261030-03` | QC, SKY, KMS second attempts (no verdict existed before; `NOTE` lists why), and H5 after the setup fix, the CASA split and the measures data | frozen for QC, SKY, KMS; post hoc for H5 |
| `outputs/dfio-20261030-04` | H5 after the string fix; SKY after the shape-text writer and BBS columns | post hoc |

Images: QC, SKY `-03`, KMS and the first H5 attempts ran on
`rang-formats-oracle:20261030` `sha256:ff4b85b6…a26a` (with GLib); H5's last
`-03` run and `-04`, and SKY `-04`, on `sha256:6ddf0359…b89b` (the measures
data copied from `rang-o-casa:6.7.6.14`, `sha256:24822b40…69e8`). The venv
layers were cached across the rebuilds and the four locks are unchanged.

## Measured results

| Format | Direction | Oracle | Verdict (frozen) | Post hoc |
| --- | --- | --- | --- | --- |
| CASA caltable (K, G, B, Df, T) | read | python-casacore 3.8.1 dumps of CASA 6.7.6's tables | **pass**: every cell, definedness, keyword and `table.info` | – |
| CASA caltable | write (copy) | E4's byte rule; `applycal` with the core's copies | **pass**: all five identical but masked gaps; CORRECTED_DATA and FLAG bit-identical | – |
| CASA caltable | semantics | `applycal` per type and the K, G, B, Df chain, 1e-6 relative | **fail**: B and Df flags (flagged channels are bridged by CASA), Df values (0.13), chain (0.71) | K 2.5e-7, G 3.4e-7, B 4.5e-7, T 3.4e-7 pass; Df 6.2e-5 (6,622 cells above 1e-6) and chain 6.9e-5 fail: cross hands cancel (worst cell 1.4e-3 Jy from inputs of 9 Jy); all cells within 5.4 float32 eps of the cell's largest correlation; flags equal |
| CASA caltable | write (core gains) | `applycal` of core-made G (4 solutions, 2 flagged), B (flagged range), K, T and G+B+K | **fail**: G and chain (1.99, the flag-identity bug) | B 4.7e-7, K 2.7e-7, T 7.3e-7 pass; G 1.04e-6 (28 of 352,248 cells), chain 1.23e-6 (367 cells) fail; within 10.3 float32 eps; flags equal |
| QuartiCal store | read | `xds_from_zarr` (QuartiCal 0.2.7 venv), archived complex store and a new delay store | **pass**: every variable and attribute bit-exact | – |
| QuartiCal store | write | metadata bytes; `xds_from_zarr`; QuartiCal `load_from`, `iter_recipe=[0]` | **pass**: 29 and 39 metadata files byte-identical; CORRECTED_DATA bit-identical (complex and delay); seeded store 5.9e-8 | – |
| Tigger lsm (ASCII) | read | Tigger 1.8.0 `load` of CARACal's 196 components | **pass**: max 1 ulp in an angle | – |
| Tigger `.lsm.html` | write, read | Tigger `load`; `tigger-convert` round trip | **pass**: value-exact both ways; Tigger's own output is a fixed point under `PYTHONHASHSEED=0`; the core's file differs from Tigger's in 201 lines (Q/U/V as float 0.0 against Tigger's int 0, the `r` attribute) | – |
| Tigger lsm (ASCII) | write | Tigger `load`; the core's read of `tigger-convert`'s ASCII | **fail**: Tigger loads the core's file value-exact; `tigger-convert` writes multi-term spectra as a Python list in the `spi` column, unreadable by Tigger and the core | – |
| WSClean source list | write | africanus `load`; Crystalball 0.4.3 predict into a copy of `c.ms` | **fail** (value-exact text): 9 Gaussian axes off by 1-2 ulp; Crystalball **passes**: max 0.008 of the 2^-22 Σ\|S\| bound, max abs 3.0e-8 Jy, 99.948 % of cells bit-identical, cross hands zero | 4 axes at 1 ulp: no arcsec text reaches them through `deg2rad(x/3600)` |
| WSClean source list | read | WSClean 3.7 `-save-source-list` (69 components), africanus `load` | **pass** | – |
| BBS skymodel | read | Tigger's BBS `load` of `tigger-convert -o BBS` | **fail**: Tigger skips the four-term source of its own file; it writes MajorAxis, MinorAxis and Orientation in radians (BBS: arcsec, degrees) | the core reads all 196 sources; positions within 1e-9 rad, fluxes and spectra (A0's four terms) equal the lsm; shapes in Tigger's radians |
| DDFacet DicoModel | read | DDFacet 1.0.0.0 `MyPickle.Load` | **pass**: structure and 75 components bit-exact; a pickle naming `os.system` refused | – |
| DDFacet ClusterCat | read, write | `np.load`/`np.save` (DDFacet's NumPy 2.3.2) | **pass**: bit-exact, byte-identical | – |
| H5parm | write, read | losoto 2.7.1 `H5parm`; a losoto-made file | **fail** (`-01`): the checker wrote abs/angle of the complex gains and compared them with the amplitude and phase it drew (losoto's read of `-01`'s `core.h5` equals h5py's read of it: a setup error, not the format) | **pass** (`-03`): types, axes, values and weights exact both ways; listing: PyTables sees `antenna`/`source` as a different class, string attributes as bytes |
| H5parm | apply | DP3 6.6.0 `applycal` (amplitude000, phase000), 1e-6 relative | **fail** (`-01`): DP3 refuses a Measurement Set with three FIELD rows | `-03`, one-field split and measures data: fail, DP3 finds no `m000` (h5py's NUL-padded strings); `-04`, NUL-terminated strings: **pass**, 4.0e-7 over 470,224 cells |
| killMS solutions | write | killMS 3.3.0 `MergeSols.py` on two core files | **pass**: `np.load(allow_pickle=False)` reads them; merged G equal to the core's merge (0.0); FreqDomains, MaskedSols, t0, t1 exact | – |
| killMS solutions | read | `np.load(allow_pickle=True)` of the merged file | **pass**: bit-exact | – |
| CASA flag versions | write | CASA `flagmanager` restore and list | **pass**: FLAG and FLAG_ROW bit-exact after restore; listed | – |

## Deviations

- **The CASA model in the protocol was incomplete** (found by run -01):
  the protocol froze Df as `D_p⁻¹ … D_q⁻ᴴ` (an exact inverse); CASA's
  `Df Jones` is the linear approximation. It froze no rule for flagged
  frequency channels; CASA bridges them. The core's first `correct` also set
  both receptors to identity when one was flagged. All three are fixed in
  run -02 (post hoc); the frozen verdict is -01's.
- **1e-6 relative is the wrong yardstick where CASA's float32 result
  cancels** (Df cross hands; G interpolated over float32 times): the post
  hoc runs report the error in float32 epsilons of the cell, ≤ 10.3. The
  frozen tolerance stays the verdict.
- **DP3 needs one FIELD row**: `c.ms` has three; CASA `split` made a
  one-field copy (`examples/oracle_formats.py casa-split`). DP3 also needs
  the measures tables: the image copies O-CASA's (`casacore-data
  20250826-160001-5`).
- **The written WSClean spectra are zero-padded** to the longest list:
  Crystalball 0.4.3 stacks the lists into one array and stopped on lists
  of different lengths (first attempt). The comparator strips the padding
  (one SKY re-run in -03 after a comparator fix).
- **The CARACal lsm is GPL-2.0** (CARACal's pyproject; L1-M), not BSD as
  the task text says: it is read from L1-M's fetch by SHA256 and not
  committed; tests use synthetic models.
- **Flag versions**: FLAG is written fixed-shape (E4 does not create
  variable-shape tiled columns); CASA reads it as its own.
- **The restricted unpickler allows only the frozen globals**: a protocol 5
  NumPy pickle (`numpy._core.numeric._frombuffer`) is refused; DDFacet
  writes protocol 4.
- QC, SKY and KMS were measured in `-03` after first attempts in `-01`
  stopped before any verdict (two core-side defects, one Crystalball
  limitation), recorded in `-03/NOTE`. H5 has a frozen verdict in `-01`
  (fail); its `-03` and `-04` runs are post hoc.

## Open items

- Df and the chain: a float32 emulation of CASA's `JonesGenLin` and of
  the G interpolation would show whether the residual reaches 1e-6; the
  format itself is settled by the bit-identical copies.
- Variable-shape TiledShapeStMan (E5) for flag versions as CASA writes
  them; IncrementalStMan writes (E5) for restoring into an MS from the core.
- QuartiCal `param_*` stores are read and rewritten but `complex_partition`
  is the only builder from core gains; parametrised builders (delay, TEC)
  when the core solves them.
- H5parm: `fulljones` and `tec`/`clock` soltabs, more than one direction
  per DP3 apply (DDECal facets) are not exercised; PyTables' Table class
  for `antenna`/`source` (h5py writes plain compound datasets).
- killMS: DDFacet's `ClassJones` reading of a core file (`--DDESolutions`)
  needs a DDFacet run on an MS (DF3/DF4).
- DicoModel write (only if DDFacet must consume core models); BBS write;
  the Tigger ASCII multi-term writer (Tigger's).
- MSv4 (xradio) and IDIA HDF5 are out of scope (ecosystem survey 5.3).

## Timings

Wall from `/usr/bin/time` (whole host commands) and from the checker's
per-container timer; RSS is the host process's maximum (`%M`), `–` where
not recorded (container-only steps).

| Date | Tool | Input | Wall | RSS | Notes |
| --- | --- | --- | --- | --- | --- |
| 2026-10-30 | `docker build` `rang-formats-oracle:20261030` | four venvs, DDFacet and killMS built from sdists | 206.7 s | – | then 10.0 s (GLib layer), 1.0-1.1 s (measures data layers); one failed apt attempt 9.7 s |
| 2026-10-30 | `uv venv` + editable install with the extension build | worktree | 78.1 s | – | |
| 2026-10-30 | `cargo test --release --lib blosc` | core | 61.9 s | – | 7 tests |
| 2026-10-30 | `maturin develop --release` | core | 75.0 s | – | after the blosc fix |
| 2026-10-30 | CASA 6.7.6 `flagmanager(mode='save')` probe | `c.ms` copy | 2.3 s | – | before freezing |
| 2026-10-30 | `check_formats.py ct` (frozen `-01`; post hoc `-02`) | 5 CASA tables, 4 synthetic, 15 `applycal` | 24.3 s; 23.6 s | 765,512 KB; 642,584 KB | `applycal` ×15 18.4 s; `gaincal` T 1.7 s; python-casacore dumps 0.4 s; core read 0.01 s and write 0.06 s per table |
| 2026-10-30 | `check_formats.py qc` (`-03`) | 2 stores (16 × 64 × 4 × 1 × 4; delay 16 × 2048), 5 QuartiCal applies | 187.3 s | 350,812 KB | delay solve 46.6 s; `xds_from_zarr` ×5 11.5 s; `load_from` apply ×5 101.2 s; core read 3-10 ms, write 7-21 ms |
| 2026-10-30 | `check_formats.py sky` (`-03`; post hoc `-04`) | 196 components; 192 rows × 2048 ch × 4 | 36.6 s; 50.0 s | 88,664 KB; 89,704 KB | Crystalball 0.4.3 15.4 s; core predict 0.94 s; WSClean 3.7 clean + source list 3.3 s; DicoModel read 1 ms |
| 2026-10-30 | `check_formats.py h5` (frozen `-01`; post hoc `-03`, `-04`) | 32 × 2048 × 4 × 1 × 2 | 2.4 s; 9.4 s; 9.2 s | 193,432 KB; 184,480 KB; 245,876 KB | losoto read, make, list 3.1 s; CASA split 3.7 s; DP3 6.6.0 applycal 1.3 s; core write 0.07 s (16.8 MB) |
| 2026-10-30 | `check_formats.py kms` (`-03`) | 2 files, 3 × 2 × 4 × 2 × 2 × 2 | 2.1 s | 47,272 KB | killMS `MergeSols.py` 1.8 s (container) |
| 2026-10-30 | `check_formats.py fv` (`-01`) | `c.ms` copy | 6.2 s | 58,520 KB | `flagmanager` list + restore 5.8 s; core save 0.03 s |
| 2026-10-30 | `pytest tests/test_dfio_formats.py` | – | 0.3 s | – | 16 tests |
| 2026-10-31 | `tools/check-all.sh` | worktree | 587 s (first run: FAIL on a stale `docs/cli.md` and trailing blanks in this file, both fixed); the final run's time is in its log | – | final run `overall: PASS`, log `outputs/dfio-20261030-check-all.log` |

## For the coordinator

### Shared-file hunks (applied locally, committed because the tests and the CLI need them)

`python/rang/core_cli.py` and `pyproject.toml` (the `formats` extra), the
exact `git diff 368e8ca` of the branch:

```diff
diff --git a/pyproject.toml b/pyproject.toml
index e640b3b..707e394 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -35,6 +35,8 @@ beam = ["katbeam==0.1", "eidos==1.1.2"]
 flagging = ["quartical==0.2.7", "stimela==2.1.4", "python-casacore==3.8.1", "numpy>=1.26", "matplotlib>=3.8"]
 recipes = ["stimela==2.1.4"]
 imaging = ["astropy>=6"]
+# DF-IO (research/dfio-formats.md): the H5parm reader and writer.
+formats = ["h5py>=3.11"]
 notebook = ["matplotlib>=3.8", "pandas>=2.1", "ipywidgets>=8.1", "ipykernel>=6.29", "jupyterlab>=4", "nbformat>=5.9", "nbconvert>=7.16"]
 # The documentation site (research/d1-docs.md): Sphinx with MyST notebooks, executed by papermill.
 docs = ["sphinx>=9.2", "furo>=2025.12", "myst-nb>=1.4", "papermill>=2.7"]
diff --git a/python/rang/core_cli.py b/python/rang/core_cli.py
index 8a85222..c6df067 100644
--- a/python/rang/core_cli.py
+++ b/python/rang/core_cli.py
@@ -920,6 +920,7 @@ TOP_LEVEL = {
     "check": "[--rust | --python | --all]: the full local checks, portable",
     "compare": "STAGE RESULT ORACLE RECEIPT: legacy form (adds `comparator`)",
     "trend-mirror": "MIRROR SOURCE: legacy form of `trend mirror`",
+    "formats": "check PATH | convert IN OUT: read and write the tools' formats",
 }
 # The stage functions that `run` (and `trend mirror`) call, looked up at call
 # time; the cabs call the same functions.
@@ -1142,6 +1143,10 @@ def dispatch(argv=None):
         return _check(argv[1:], options, pinned)
     if argv[0] == "compare":
         return _legacy_compare(argv[1:], options, pinned)
+    if argv[0] == "formats":
+        from .formats import cli as formats_cli
+
+        return formats_cli.main(argv[1:])
     command = ["rang-core", *argv]
     if argv[0] == "environment":
         args = _parse("rang-core environment", _configure_environment, argv[1:])
```

`docs/cli.md`, regenerated by `python docs/gen_cli.py` (the D1 test
compares it with `rang-core --help`):

```diff
diff --git a/docs/cli.md b/docs/cli.md
index 64a7e9d..bfd78f8 100644
--- a/docs/cli.md
+++ b/docs/cli.md
@@ -68,6 +68,7 @@ other commands:
   check           [--rust | --python | --all]: the full local checks, portable
   compare         STAGE RESULT ORACLE RECEIPT: legacy form (adds `comparator`)
   trend-mirror    MIRROR SOURCE: legacy form of `trend mirror`
+  formats         check PATH | convert IN OUT: read and write the tools' formats

 `rang-core STAGE -h` describes a stage's verbs. `compare` takes the
 arguments of examples/compare_core_<stage>.py or of the stage's checker.
```

(Blank context lines of these diffs are written without their leading
space; `git apply` accepts them.)

Not in the owner list, changed because the oracle found a defect (please
review): `core/src/blosc.rs` (`block_span`: a block ends at the nearest
larger block start; test `blocks_stored_out_of_order_decode`) and
`python/rang/core_zarr.py` (`read_rows` decodes a chunk with out-of-order
blocks whole), commit `9fb3d19`, exactly:

```diff
diff --git a/core/src/blosc.rs b/core/src/blosc.rs
index c2263e4..957831e 100644
--- a/core/src/blosc.rs
+++ b/core/src/blosc.rs
@@ -265,8 +265,10 @@ fn unshuffle_sse2<const T: usize, const ROUNDS: usize>(
 }

 /// Byte range of block `j` within the chunk: from its start offset to the
-/// next block's start (or the end of the chunk). Lets a caller read only the
-/// blocks it needs from a file or an HTTP range request.
+/// nearest larger block start (or the end of the chunk). Lets a caller read
+/// only the blocks it needs from a file or an HTTP range request. Blocks
+/// need not be stored in order: multithreaded blosc writes them as they
+/// finish (QuartiCal's dask-ms stores have such chunks; research/dfio-formats.md).
 pub fn block_span(src_head: &[u8], h: &Header, j: usize) -> Result<(usize, usize), &'static str> {
     let nblocks = h.nblocks();
     if j >= nblocks {
@@ -277,13 +279,15 @@ pub fn block_span(src_head: &[u8], h: &Header, j: usize) -> Result<(usize, usize
         return Ok((start, (start + h.blocksize).min(HEADER + h.nbytes)));
     }
     let start = u32_at(src_head, HEADER + 4 * j)?;
-    let end = if j + 1 < nblocks {
-        u32_at(src_head, HEADER + 4 * (j + 1))?
-    } else {
-        h.cbytes
-    };
+    let mut end = h.cbytes;
+    for k in 0..nblocks {
+        let other = u32_at(src_head, HEADER + 4 * k)?;
+        if other > start && other < end {
+            end = other;
+        }
+    }
     if end < start {
-        return Err("blosc block offsets are not ascending");
+        return Err("blosc block offset beyond the chunk");
     }
     Ok((start, end))
 }
@@ -503,6 +507,29 @@ mod tests {
         assert_eq!(rows, [8, 9, 10, 11, 28, 29, 30, 31]);
     }

+    #[test]
+    fn blocks_stored_out_of_order_decode() {
+        // Two raw blocks of 8 bytes, typesize 1, the second stored first,
+        // as a multithreaded compressor may write them.
+        let a: Vec<u8> = (0..8u8).collect();
+        let b: Vec<u8> = (100..108u8).collect();
+        let second = HEADER + 8;
+        let first = second + 4 + 8;
+        let mut src = vec![2u8, 1, 0x20, 1];
+        src.extend((16u32).to_le_bytes());
+        src.extend((8u32).to_le_bytes());
+        src.extend(((first + 4 + 8) as u32).to_le_bytes());
+        src.extend((first as u32).to_le_bytes());
+        src.extend((second as u32).to_le_bytes());
+        src.extend((8u32).to_le_bytes());
+        src.extend(&b);
+        src.extend((8u32).to_le_bytes());
+        src.extend(&a);
+        let mut want = a.clone();
+        want.extend(&b);
+        assert_eq!(decode(&src).unwrap(), want);
+    }
+
     #[test]
     fn unshuffle_restores_element_order() {
         let shuffled = [1u8, 3, 5, 2, 4, 6, 9];
diff --git a/python/rang/core_zarr.py b/python/rang/core_zarr.py
index 44e23e7..48405f4 100644
--- a/python/rang/core_zarr.py
+++ b/python/rang/core_zarr.py
@@ -84,6 +84,23 @@ def read_rows(path, row_bytes, rows):
             head = head + table
             starts = np.frombuffer(table, "<u4").astype(np.int64)
             ends = np.append(starts[1:], cbytes)
+            if np.any(np.diff(starts) <= 0):
+                # Blocks stored out of order (multithreaded blosc, as in
+                # QuartiCal's stores; research/dfio-formats.md): decode the
+                # whole chunk and select the rows.
+                stream.seek(0)
+                whole = stream.read()
+                stats["bytes_read"] = len(whole)
+                stats["blocks_total"] = stats["blocks_decoded"] = nblocks
+                decode_started = time.perf_counter()
+                data = np.frombuffer(core.blosc_decode(whole), np.uint8)
+                stats["decode_seconds"] = time.perf_counter() - decode_started
+                if len(rows) and (rows[-1] + 1) * row_bytes > nbytes:
+                    raise ValueError("row beyond the chunk")
+                picked = data[: (len(data) // row_bytes) * row_bytes].reshape(
+                    -1, row_bytes
+                )
+                return picked[rows].tobytes(), stats
         stats["bytes_read"] += len(head)
         if len(rows) and (rows[-1] + 1) * row_bytes > nbytes:
             raise ValueError("row beyond the chunk")
```

### STATE paragraph

> DF-IO formats (big plan; [dfio-formats.md](dfio-formats.md)),
> 2026-10-30 (implemented; measured): `rang.formats` reads and writes the
> file formats of the tools the core replaces, each judged by its own tool.
> Passing as frozen: CASA caltables read (K, G, B, Df, T) and written
> (CASA's bytes but the masked gaps, `applycal` bit-identical); QuartiCal
> 0.2.7 gain stores read and written (metadata byte-identical, `load_from`
> bit-identical, a core-made store to 5.9e-8; a core blosc defect with
> out-of-order blocks fixed); Tigger ASCII and `.lsm.html`; WSClean lists
> read and predicted by Crystalball within the float32 bound (99.95 % of
> cells bit-identical); DicoModel read through a restricted unpickler;
> ClusterCat; killMS solutions merged by `MergeSols`; CASA flag versions
> restored by `flagmanager`. Failing as frozen: the core's own `applycal`
> model to 1e-6 (post hoc K, G, B, T pass; Df and the chain within 10.3
> float32 eps but up to 6.9e-5 relative where cross hands cancel), WSClean
> shape text (1 ulp, a format limit), Tigger's ASCII and BBS writers (Tigger
> defects), and the H5parm (a setup error and DP3's one-field rule; post hoc
> losoto reads and writes it exactly and DP3 `applycal` applies it to 4.0e-7
> after NUL-terminated strings). `rang-core formats check|convert`; image
> `rang-formats-oracle:20261030`; `outputs/dfio-20261030-01` to `-04`,
> `research/results/dfio-formats.json`.

### `research/README.md` index entry

> New, 2026-10-30: DF-IO, the [tools' file formats](dfio-formats.md):
> CASA caltables, QuartiCal stores, Tigger/WSClean/BBS sky models,
> DicoModel, ClusterCat, H5parm, killMS solutions and CASA flag versions,
> each judged by its own tool; `rang-core formats check|convert`.

### `research/tool-timings.md` rows

The Timings table above, as is: the same six columns as
`research/tool-timings.md` (Date, Tool, Input, Wall, RSS, Notes).

### Upstream observations (not filed)

RATT (reportable under the user's rule; reproduce on the latest release
first):
- **Tigger (tigger-lsm 1.8.0)**: `ASCII.save` writes a multi-term
  spectral index as a Python list repr into the `spi` column (`[-0.0977,
  -0.606, …]`), which its own loader cannot parse; `BBS.save` writes
  MajorAxis/MinorAxis and Orientation in radians where makesourcedb/LSMTool
  read arcsec and degrees (and `BBS.load` reads them back unconverted), and
  writes the list into `SpectralIndex:0`, so `BBS.load` skips that source;
  `ModelHTML.load` uses `eval` on `mdlval` (a crafted `.lsm.html` runs
  code); extra source attributes are rendered from a `set`, so `.lsm.html`
  bytes depend on `PYTHONHASHSEED`; many `SyntaxWarning: invalid escape
  sequence` on Python 3.12.
- **Crystalball 0.4.3**: `import_from_wsclean` stacks the SpectralIndex
  lists with `np.asarray`, so a list with components of different spectral
  orders fails under NumPy 2 ("inhomogeneous shape").
- **QuartiCal 0.2.7 / dask-ms**: chunks are written by multithreaded blosc
  with blocks out of order (valid blosc; noted because readers that assume
  ascending block offsets fail).

saopicc (DDFacet, killMS):
- **killMS 3.3.0** `MergeSols.py` writes `last_InterPol.obj` (a pickle of
  its options) into the working directory and reads it back with
  `pickle.load`; `ClassMergeSols` loads inputs with `allow_pickle=True`.
- **DDFacet 1.0.0.0** pins `numpy<=2.3.2`, `python-casacore<=3.7.1`,
  `tables<=3.10.2`, `dask<2024.11`, which conflict with QuartiCal 0.2.7 and
  Crystalball closures (four venvs were needed).

Non-RATT:
- **DP3 6.6.0 (PyPI wheel)**: needs the system GLib (`libglib-2.0.so.0`)
  and the casacore measures tables (Observatories) though `applycal` of a
  direction-independent H5parm uses neither; refuses a Measurement Set with
  more than one FIELD row; does not match antenna names stored as
  NUL-padded fixed-length HDF5 strings (h5py's default for `S` arrays),
  which losoto reads.
- **CASA 6.7.6**: `Df Jones` is applied in the linear approximation
  (parallel hands unchanged), and flagged frequency channels of B/Df
  solutions are bridged by interpolation under `interp='linear'`
  (documented behaviour, recorded for the core's model).
- **losoto 2.7.1**: reads h5py-written H5parms although PyTables classes
  the compound `antenna`/`source` datasets differently.

### Ignored output directories

- `outputs/dfio-20261030-01` (68 MB after trimming the `applycal` MS copies;
  CT, FV and the first attempts), `outputs/dfio-20261030-02` (3.7 MB, CT
  post hoc), `outputs/dfio-20261030-03` (103 MB: QC stores and dumps, SKY,
  H5, KMS), `outputs/dfio-20261030-04` (67 MB, post hoc H5 and SKY),
  `outputs/dfio-20261030-check-all.log` (the passing run) and `outputs/dfio-20261030-check-all-1.log` (the first, failing run).
- The image `rang-formats-oracle:20261030` (3.5 GB) stays on the host.
- Scratch `~/Build/tmp/20261030-dfio` (sdists, casa6 sources, probes) is
  deleted at the end of the task.
