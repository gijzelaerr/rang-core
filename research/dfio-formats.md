# DF-IO: the file formats of the tools the core replaces

Task DF-IO of [big-plan.md](big-plan.md) (the user's decision of
2026-10-30: the core reads and writes the formats of the tools it replaces,
not just converts them for oracle runs), with the survey's sub-tasks
DF-IO-CT, DF-IO-H5 and DF-IO-SKY ([ecosystem-survey.md](ecosystem-survey.md)
sections 3.3, 5.2 items 3, 5 and 6, 5.3 and 5.4). Branch `dfio-formats`
from `main` `368e8ca`. Each format is judged by its own tool as the oracle.
A reimplementation of a file format is not a scientific contribution
(AGENTS.md); no archived result changes because of it.

Status: **protocol frozen; not yet implemented.**

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

(not started)

## Measured results

(none)
