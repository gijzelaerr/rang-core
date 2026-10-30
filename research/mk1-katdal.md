# MK1: the `[meerkat]` extra and an MVFv4 loader into the core's arrays

Status: **protocol frozen 2026-10-30, before any loader code.** Big plan task
MK1 (wave 2 tooling; [big-plan.md](big-plan.md)), the DEPEND item 4 of
[ecosystem-survey.md](ecosystem-survey.md) section 5.2. Purpose: when the
observer's full-resolution L-band dataset arrives
([flagging-luno-candidate.md](flagging-luno-candidate.md), "Raw DATA and native
flags"), task L3 can read native FLAG/WEIGHT from a MeerKAT MVFv4 archive
straight into the core's `(row, channel, corr)` arrays without an MS.
A tooling task; under AGENTS.md not a scientific contribution.

## Protocol (frozen before implementation)

### Data available for the acceptance

- **No public MVFv4 archive is reachable (measured 2026-10-30).** SARAO archive
  RDB links carry a per-user JWT `?token=` (katdal README; SARAO ESDKB
  "Accessing and examining your data"); two web searches found no token-free
  `sdp_l0` RDB. The anonymous RATT bucket (`ratt-public-data`, af-south-1)
  lists `ESO137/`, `G330/`, `LBAND_LUNO_*.zarr`, `LUNO/`, `MGCLS_HI/`,
  `MeerKATbeams*/`, `scratch/`, `test-data/` (one ALMA tarball and
  `crystalball/`), `test/`, `vcpkg-cache/`, `wheels/`: no `.rdb`, no chunk store.
  katdal 0.23's wheel ships no test data. So acceptance (c) (LUNO zarr against
  the matching MVF) **cannot run** and is recorded as such; it is an open item
  for L3 if the observer's dataset arrives as MVF.
- **Acceptance (a), (b), (d) run on a synthetic MVFv4 archive** written with
  katdal's and katsdptelstate's own writers (`NpyFileChunkStore`,
  `katsdptelstate.rdb_writer.RDBWriter`), following katdal's test helpers
  `make_fake_data_source` and `put_fake_dataset`, extended until
  `katdal.open` builds a full `VisibilityDataV4` and `mvftoms.py` exports it.
  Layout as on the archive: `<root>/<cbid>/<cbid>_sdp_l0.rdb` and the chunk
  store `<root>/<cbid>-sdp-l0/<array>/<AAAAA>_<BBBBB>_<CCCCC>.npy`.
  The fixture is adversarial:
  - MeerKAT-like antennas (katpoint descriptions at the MeerKAT reference
    position, real-shaped ENU offsets), 7 antennas (autos and crosses,
    4 products each), a **shuffled, non-lexicographic `bls_ordering`**;
  - several chunks along dumps and channels (e.g. 24 dumps × 64 channels,
    chunks 5 dumps × 16 channels, so partial edge chunks);
  - two `track` scans on two targets (tags `bpcal`, `gaincal`) separated by
    a `slew`, `obs_activity`/`cbf_target` sensors and per-antenna aliases,
    `obs_label`, `sync_time` after 2019-03-15 (no SR-1625 shift);
  - random complex vis, uint8 `weights` and float32 `weights_channel`,
    `need_weights_power_scale = True`;
  - every one of the 8 flag bits set somewhere in `sdp_l0/flags`, and a
    **different** bitfield in an `sdp_l1_flags` stream;
  - one deleted `correlator_data` chunk file (katdal zero-fills it and sets
    `data_lost`) and one zero autocorrelation (the `2**-32` bad-weight path).
  - The same archive is also served by `python -m http.server` on 127.0.0.1 to
    exercise the RDB-URL and HTTP chunk-store path offline.
- Seeds: fixture RNG `numpy.random.default_rng(20261030)`; the fixture
  parameters are recorded in `research/results/mk1-katdal.json`.

### The extra (pins measured, not assumed)

- `[meerkat] = ["katdal==0.23", "katsdptelstate[rdb]==1.0.0"]`. Not
  `katdal[ms]`: python-casacore 3.8.1 ships Linux x86_64 wheels only; it is
  needed only for `mvftoms.py`, which the acceptance venv installs separately
  (the `[flagging]` extra already pins python-casacore 3.8.1).
- Measured 2026-10-30 (installs into fresh uv venvs from public PyPI):
  - Linux x86_64 (WSL Ubuntu, gcc 15.2): Python 3.12 (7.9 s), 3.13 (2.4 s)
    and 3.14 (12.6 s) all install and import katdal 0.23, katsdptelstate
    1.0.0, katpoint 0.10.3, numba 0.68.1, dask 2026.8.0.
  - Native Windows (MSVC present): 3.13 (11.7 s) and 3.14.7 (14.6 s)
    install and import.
  - Wheel coverage from PyPI JSON for the 32 resolved packages
    (`uv pip compile --python-platform`): on Windows amd64, Linux x86_64
    and macOS arm64, `python-lzf 0.2.6` (C extension) and `rdbtools 0.1.15`
    (pure Python) are sdist-only on every Python; `cityhash 0.4.10` (C++)
    has no cp314 wheel. So the extra needs a C compiler everywhere, and a
    C++ compiler on 3.14. Python ceiling: none found up to 3.14 (numba 0.68.1
    and llvmlite 0.50 ship cp314 wheels; numba caps NumPy below 2.6).

### Loader interface (`python/rang/meerkat.py`)

- `open_mvf(source, *, ref_ant="", upgrade_flags=True, van_vleck="off",
  chunk_store=None, **katdal_kwargs)` opens an RDB URL (`http(s)://…rdb`,
  with token query if any) or a local `.rdb` through `katdal.open` and returns
  an `MvfLoader`. katdal is imported lazily; `rang` imports without it.
- `MvfLoader.select(scans=, targets=, antennas=, channels=, autos=False,
  flags="all")` wraps `DataSet.select` (cumulative reset each call).
- `MvfLoader.metadata()` antenna names, ECEF positions, diameters (the MS
  ANTENNA table's order is `dataset.ants`), channel frequencies and width,
  correlation names and MS corr types, dump period, scans and targets, the
  flag-bit table, katdal/katsdptelstate versions.
- `MvfLoader.iter_chunks(dumps=None)` yields one dict per block of whole
  dumps, by default the store's own dump chunking, with the core's chunk
  keys and dtypes as `core_fetch.decode_slice` returns them, plus extras:
  `ANTENNA1`, `ANTENNA2` `<i4`; `TIME` `<f8`; `FLAG_ROW` bool;
  `UVW` `<f8` (row, 3); `DATA` complex64, `FLAG` bool, `WEIGHT_SPECTRUM`
  float32, `FLAG_BITS` uint8, each `(row, channel, corr)`; `SCAN_NUMBER`,
  `FIELD_ID` `<i4`. No `MODEL_DATA` (MVF has none; nothing is invented).
- `MvfLoader.read()` is the concatenation of `iter_chunks()`;
  `MvfLoader.save_chunks(out)` writes each chunk as `.npy` files plus a
  manifest with provenance, the MS-free path for the L3 driver. No zarr
  writer: the core decodes blosc but has no encoder, and adding zarr or
  numcodecs for this is not justified.

### Conventions (frozen)

- **Rows**: time-major; inside a dump, baselines in lexicographic
  `(ANTENNA1, ANTENNA2)` order of `dataset.ants` indices, `ANTENNA1 < ANTENNA2`
  (plus `==` when `autos=True`). This is the dask-ms/LUNO layout the core reads.
- **Correlations**: `XX, XY, YX, YY` = katdal `hh, hv, vh, vv` (h→X, as
  `mvftoms.py` labels HH→9 … VV→12). A product missing from `bls_ordering`
  gives DATA 0, WEIGHT 0, FLAG true (mvftoms' rule).
- **DATA**: katdal `vis` (no applycal, `van_vleck="off"` by default).
- **WEIGHT_SPECTRUM**: katdal `weights`, i.e. stored `weights` (uint8) ×
  `weights_channel` (float32, broadcast over baselines), then, when
  `need_weights_power_scale` is true (stored weights unscaled), **divided**
  by `auto_i.real × auto_j.real` (computed as `(1/auto_i) × (1/auto_j)` in
  float32), with `2**-32` where that factor is not finite
  (`katdal/vis_flags_weights.py: weight_power_scale`). The survey's
  "× autocorr power" has the direction backwards: it divides.
- **FLAG_BITS**: the uint8 bitfield as katdal serves it (`raw_flags`): the L0
  ingest flags when `upgrade_flags=False`; the `sdp_l1_flags` stream
  (katsdpcal output) replacing them under katdal's default
  `upgrade_flags=True`, ORed with `data_lost` for missing chunks.
  Bits (`katdal/flags.py`): 0 reserved, 1 `static` (predefined static mask),
  2 `cam` (live CAM state), 3 `data_lost`, 4 `ingest_rfi`, 5 `predicted_rfi`,
  6 `cal_rfi` (calibration pipeline), 7 `postproc`.
  **Native observatory flags for L3** = `upgrade_flags=False` and bits
  `static, cam, data_lost, ingest_rfi` (and `predicted_rfi` if present);
  `cal_rfi` and `postproc` are processing products.
- **FLAG**: `(FLAG_BITS & mask) != 0`, `mask` from `select(flags=…)` (default all).
- **TIME**: `katpoint.Timestamp(t).to_mjd() * 86400` per dump, as
  `katdal/ms_async.py` writes it; `t` = katdal `timestamps` (dump centres from
  `sync_time + first_timestamp + n·int_time`).
- **UVW**: as `ms_async.py`: `target.uvw(ants, t, array_reference)` per
  antenna, then `uvw[ANTENNA1] − uvw[ANTENNA2]` (CASA sign), float64.
- **FLAG_ROW**: false everywhere (MVF has no row flag; mvftoms writes 0).
- **SCAN_NUMBER** counts `track`/`scan` scans from 1 in order (mvftoms'
  `scan_itr`); `FIELD_ID` indexes targets in order of first appearance.

### Acceptance (frozen; all "exact" means `numpy.array_equal`, bitwise for floats)

- **(a) katdal and raw chunks against the loader**, on the fixture, both the
  local `.rdb` and the HTTP URL:
  1. the loader's DATA, FLAG_BITS, WEIGHT_SPECTRUM, TIME equal arrays
     recomputed independently of katdal's `DataSet` from the raw `.npy`
     chunks and the RDB's telstate values (vis; flag bits with `data_lost` on
     the deleted chunk; the weight product and power scale above in float32;
     timestamps from `sync_time`, `first_timestamp`, `int_time`), exact;
  2. the same arrays equal katdal's own `vis`, `raw_flags`, `flags`,
     `weights`, `timestamps` after the frozen corrprod → (row, corr) mapping,
     exact, under one selection with scans, antennas and channels restricted;
  3. UVW against katdal's `u, v, w`: katdal's baseline vector has the
     opposite sign; agree within 1e-6 m after the sign flip (frozen tolerance;
     katdal computes it per baseline, mvftoms per antenna);
  4. antenna names, positions and diameters, channel frequencies equal
     katdal's, exact.
- **(b) mvftoms MS against the loader**: `mvftoms.py -f --quack 0` (full pol,
  autos kept, all flags) on the fixture; the MS read by `rang.core_ms` and the
  loader with `autos=True`, rows matched by `(TIME, ANTENNA1, ANTENNA2)`:
  DATA, FLAG, WEIGHT_SPECTRUM, UVW, TIME, ANTENNA1/2 exact; SPECTRAL_WINDOW
  CHAN_FREQ and POLARIZATION CORR_TYPE exact; ANTENNA NAME/POSITION exact.
  Also recorded: MS row order versus the loader's, FLAG_ROW (expected all 0),
  WEIGHT (expected channel mean), SIGMA_SPECTRUM (expected `w**-0.5`), which
  scans mvftoms writes.
- **(c) LUNO zarr against the matching MVF**: not runnable (no public MVF).
- **(d) flag bitfield**: with `upgrade_flags=False` the loader's FLAG_BITS
  equal the stored L0 `flags` chunks bit for bit; with the default they equal
  the `sdp_l1_flags` chunks (plus `data_lost`); for each bit alone,
  `select(flags=[name])` gives FLAG = `(bits >> b) & 1`, so L3 can separate
  native observatory flags from later processing.
- **Cost**, per stored chunk and per loader chunk on the fixture and on a
  larger synthetic set at MeerKAT L-band scale (64 antennas, 8,320 products,
  4 dumps × 4,096 channels, stored chunks of 1 dump × 256 channels × all
  products, 17 MB of vis each; about 1.4 GB on disk under `~/Build/tmp`,
  deleted after): wall, peak RSS (`resource.getrusage`), bytes
  read from the chunk store; the dask path is PORTed only if it is the
  measured bottleneck (survey rule).
- Pass = (a), (b), (d) all exact (with (a)3 within its tolerance). Any
  mismatch is a failure that is fixed in the loader's conventions or
  recorded as a documented difference; the tolerance is not changed after
  measurement.

## Implementation

(Filled after the protocol commit.)
