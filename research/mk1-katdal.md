# MK1: the `[meerkat]` extra and an MVFv4 loader into the core's arrays

Status: **implemented; measured 2026-10-30: acceptance (a), (b) and (d)
pass exactly on a synthetic MVFv4 archive written by katdal's own writers
(local `.rdb` and over HTTP); (c) not runnable (no public MVFv4 archive
exists).** Protocol frozen in `f201c54` before any loader code. Run
`outputs/mk1-20261030-03`, archive
[results/mk1-katdal.json](results/mk1-katdal.json). Big plan task
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

- `pyproject.toml`: `meerkat = ["katdal==0.23", "katsdptelstate[rdb]==1.0.0"]`.
- `python/rang/meerkat.py`: `open_mvf`, `MvfLoader.select / metadata /
  iter_chunks / read / save_chunks`, `load_saved_chunk`, `flag_mask`,
  `public_source` (drops a URL's query string, where an archive token
  lives, from everything recorded) and `write_synthetic_mvf` (the fixture).
  It reads through katdal's dask path (`DaskLazyIndexer.get` on `vis`,
  `weights`, `raw_flags` at once, as `mvftoms.py`'s `load` does), then maps
  `(time, channel, corrprod)` to `(row, channel, corr)` with one NumPy
  fancy index per array. katdal is imported only when an archive is opened,
  so `import rang.meerkat` works without the extra. Iteration is scan by
  scan; a chunk is one stored dump chunk inside a scan (or `dumps=N`).
  Threads: katdal computes with dask's threaded scheduler; set
  `DASK_NUM_WORKERS` (the check runs used 4).
- `examples/fetch_meerkat_mvf.py OUT SOURCE [--scans --targets --antennas
  --channels a:b --autos --native-flags --dumps N]`: the L3 entry point;
  writes `OUT/chunk-NNNNN/<KEY>.npy`, `manifest.json` and `receipt.json`
  (timing, peak RSS, versions; the source without its token).
- `examples/check_meerkat_loader.py OUT [--large SCRATCH] [--archive]`:
  the acceptance. (a)1 rebuilds every array from the `.npy` files and the
  RDB (`katsdptelstate` only, no katdal `DataSet`), maps rows by antenna-name
  lookup one baseline at a time, and recomputes the weight power scale in
  float32; (a)2 compares with katdal's own `vis`, `weights`, `raw_flags`,
  `flags`, `timestamps`, `u/v/w`; the HTTP leg serves the archive from a
  thread on 127.0.0.1 that answers file GETs and an S3-style bucket listing.
- `tests/test_mk1_meerkat.py` (8 tests, 4.1 s): masks, row mapping and
  missing products without katdal; with katdal, the L0 and upgraded bits,
  vis and the weight product against the stored arrays, per-bit selection,
  katdal arrays under a scan/antenna/channel selection, chunk boundaries and
  the `save_chunks` round trip, and the mvftoms MS (skips without
  python-casacore or `pkg_resources`).
- The worktree venv also needs `python-casacore==3.8.1` and `setuptools<81`
  for `mvftoms.py` (see deviations); neither is in the extra.

## Measured results (run `outputs/mk1-20261030-03`, 21.4 s)

Environment: Python 3.14.8, NumPy 2.5.4, katdal 0.23, katsdptelstate 1.0.0,
katpoint 0.10.3, WSL2 Ubuntu. Fixture: 7 antennas (112 products, shuffled),
24 dumps × 64 channels, chunks 5 × 16, `int_time` 7.997 s, seed 20261030.
katdal partitions it into slew (2), track on 1934−638 (10), slew (3), track
on 3C 286 (9): 19 track dumps. The paths it was built to exercise all fire
inside the tracks: 80 lost (dump, channel) cells, 8,975 bad-weight cells
(the `2**-32` path, from the zero autocorrelation and the lost chunk) and
15,479 cells whose L0 and L1 bits differ.

- **(a) pass.** Default selection (399 rows × 64 × 4) and a restricted one
  (scan 3, antennas m001/m003/m004/m006, channels 10–49: 54 rows × 40 × 4),
  local `.rdb`: ANTENNA1/2, DATA, FLAG_BITS, FLAG, WEIGHT_SPECTRUM and TIME
  bitwise equal to the raw-chunk rebuild and to katdal's arrays. UVW
  against katdal's `u, v, w`: 1.8e-12 m (default) and 9.1e-13 m
  (restricted), within 1e-6 m, not bitwise (katdal projects per baseline
  through a basis; mvftoms per antenna). Antenna names, ECEF positions and
  channel frequencies equal. Over HTTP (`http://127.0.0.1:<port>/
  1700000000/1700000000_sdp_l0.rdb`, katdal's `S3ChunkStore`): the same,
  in 210 requests and 4.35 MB, one 404 (the deleted chunk).
- **(b) pass.** `mvftoms.py -f --quack 0` (2.9 s) wrote 532 rows (2 track
  scans, autos kept); the loader with `autos=True` gives 532 rows, every row
  matched by `(TIME, ANTENNA1, ANTENNA2)` both ways. DATA, FLAG,
  WEIGHT_SPECTRUM, UVW, TIME, ANTENNA1/2, SCAN_NUMBER, FIELD_ID bitwise
  equal; CHAN_FREQ, CORR_TYPE (9, 10, 11, 12) and ANTENNA POSITION equal,
  NAME equal. Row order differs: mvftoms orders baselines by the archive's
  corrprod index of their HH product, the loader lexicographically.
  Recorded MS facts: FLAG_ROW is all false; WEIGHT is the channel mean of
  WEIGHT_SPECTRUM; SIGMA_SPECTRUM is `WEIGHT_SPECTRUM**-0.5` (and SIGMA the
  channel-mean weight to the −½). So an mvftoms MS carries no noise
  information beyond the archive weights.
- **(c) not run**: no public MVFv4 archive (see the protocol).
- **(d) pass.** `upgrade_flags=False`: FLAG_BITS equal the stored L0
  `flags` chunks with `data_lost` on the lost chunk; default: equal the
  `sdp_l1_flags` chunks with `data_lost`. For each of the 8 bits,
  `select(flags=[name])` gives FLAG = `(FLAG_BITS >> b) & 1`, in both
  modes. Native-flag fraction (bits 1–5) 0.238 (L0) against 0.222
  (upgraded), because the fixture's L1 stream clears half the
  `ingest_rfi` bits; `cal_rfi` occupancy 0.040 → 0.136. L3 must therefore
  open with `upgrade_flags=False` to see the observatory's own flags.
- **Cost.** Fixture: 5 chunks, 0.094 s, 1.66 MB in 79 files, VmHWM 283 MB.
  L-band-scale set (64 antennas, 8,064 cross products, 4 dumps × 4,096
  channels, 256 files of 1 dump × 256 channels × 8,320 products, 1.36 GB;
  written in 9.6 s, deleted after; every dump read, slews included, in a
  child process): 4 chunks of 2,016 rows × 4,096 × 4, 3.03 s, median
  0.75 s per chunk, of which katdal's dask read is 0.19 s (0.75 s for all
  four, against 0.06 s to `np.load` all 256 files from the page cache) and
  the loader's own mapping, flags and UVW 0.56 s; VmHWM 2.01 GB. **The
  dask path is not the bottleneck** (0.19 s of 0.75 s per dump chunk), so
  under the survey's rule the npy-chunk reader is not PORTed. The
  bottleneck is the loader's NumPy remap (two copies per array); a one-pass
  Rust permute (mvftoms uses a Numba `permute_baselines`) is the obvious
  next step if L3 needs it.

## Deviations from the protocol

1. **UVW sign premise wrong.** The protocol expected katdal's `u, v, w` to
   carry the opposite sign; katdal documents `u1 − u2` for `(ant1, ant2)`,
   the same CASA sign mvftoms writes, and the first trial measured exactly
   twice the coordinates after the "flip". The frozen 1e-6 m tolerance is
   applied to the direct difference (1.8e-12 m); both numbers are archived.
2. **TIME expression.** The protocol wrote `to_mjd() * 86400`; the loader
   uses mvftoms' own `to_mjd() * 24 * 60 * 60`, which rounds differently in
   general (left to right). (b) TIME is bitwise equal with it.
3. **mvftoms needs `pkg_resources`**: katdal 0.23's `ms_extra.py` imports
   it, and the setuptools 84.2.1 that katsdptelstate pulls in on Python ≥
   3.12 no longer ships it. The acceptance venv pins `setuptools<81`
   (80.10.2); the extra does not, because the loader does not use
   `ms_extra`.
4. **HTTP leg.** A plain `python -m http.server` is not enough: after a 404
   katdal lists the bucket and calls it inaccessible unless the answer has
   `<Contents>`. The check serves the archive with a small S3-style handler
   instead; as on the archive, the lost chunk then becomes `data_lost`.
5. **Scan rules made explicit**: the loader reads `track`/`scan` scans of at
   least 2 dumps by default (mvftoms' rule), and `corrprods="all"` is not a
   katdal selection (autos are kept by omitting `corrprods`).
6. **Cost-set shape.** 4 dumps make no track of ≥ 2 dumps under the fixture's
   sensor pattern, so the cost run reads every dump (`states` including
   `slew`, `min_scan_dumps=1`). Peak memory is VmHWM, because `ru_maxrss`
   carried the 5.6 GB forked parent's resident set across `execve`.
7. Check runs `-01` (bad-weight counter compared equality with `2**-32`,
   which a product never hits; empty large set) and `-02` (inherited
   `ru_maxrss`) were superseded by `-03` and deleted; acceptance verdicts
   were the same in all three.
8. **Row order is the loader's own, not LUNO's.** The protocol called the
   lexicographic `(ANTENNA1, ANTENNA2)` order "the dask-ms/LUNO layout".
   Measured afterwards on the LUNO calibrator store (`MAIN_1` row chunk 0,
   from `outputs/core-g-20261029-01`): time-major, the same baseline order in
   every dump, but not lexicographic (1,596 rows per dump, the 56 autos
   first). mvftoms is not lexicographic either. Nothing in the core depends
   on it: readers and `core_fetch.kept_rows` use the explicit ANTENNA1/2
   columns. Comparisons map rows by `(TIME, ANTENNA1, ANTENNA2)`.
9. The `compare` checker takes OUT as its first positional argument (it was
   `--out`), so `rang-core meerkat compare OUT` gets its primary with
   `_first`; tried with the hunk applied temporarily (pass; `core_cli.py`
   reverted).

## Open items for L3 (when the observer's data arrive)

- Ask for the dataset as MVF (an archive RDB link with token, or a
  `mvf_download.py` copy) if possible; an MS made by `mvftoms` keeps
  FLAG as a boolean (bits lost) and SIGMA_SPECTRUM is just `w**-0.5`.
- Then run (c): the LUNO zarr store's DATA/FLAG/WEIGHT for one row chunk
  against the loader on the matching MVF (expect DATA equal before
  calibration and different weights, which LUNO's QuartiCal rewrote).
- Open with `upgrade_flags=False` and `flags=NATIVE_FLAGS` for "native
  observatory flags"; keep the default upgrade only to compare with
  SARAO's katsdpcal (`cal_rfi`) flags.
- Check on the real archive what this fixture cannot: `need_weights_power_scale`
  and the `weights` encoding, van Vleck (`van_vleck="autocorr"` is off by
  default, as in mvftoms), the SR-1625 timestamp shift for pre-2019 data,
  and archive throughput (the cost here is from local disk; the archive
  serves one HTTP GET per chunk).
- katsdpcal's archived K/B/G solutions (`applycal`) as a free comparator:
  not exercised (the fixture has no `cal` streams).
- If 32k-channel data make the remap the bottleneck, port it to a Rust
  one-pass kernel.
- The missing-product path (a polarisation product absent from
  `bls_ordering`: DATA 0, weight 0, FLAG true) is covered only by a unit
  test of `to_rows`; the fixture has all four products on every baseline,
  so neither the acceptance nor the mvftoms comparison exercises it.

## Timings

| Date | Tool | Input | Wall | Peak memory | Notes |
| --- | --- | --- | --- | --- | --- |
| 2026-10-30 | `uv venv -p 3.14` + editable install (extension build) | worktree | 78.6 s | – | `[pointing,beam,test,imaging]`, ruff, maturin, pip |
| 2026-10-30 | `uv pip install katdal[ms]==0.23 katsdptelstate[rdb]==1.0.0` | Python 3.12 / 3.13 / 3.14, Linux | 7.9 / 2.4 / 12.6 s | – | 3.14 builds cityhash and python-lzf from sdist |
| 2026-10-30 | `uv pip install katdal==0.23 katsdptelstate[rdb]==1.0.0` | Python 3.13 / 3.14.7, native Windows | 11.7 / 14.6 s | – | MSVC builds python-lzf (and cityhash on 3.14) |
| 2026-10-30 | `mvftoms.py -f --quack 0` | MK1 fixture, 7 antennas, 19 dumps × 64 ch | 2.75 s (2.9 s in the check) | 316 MB | setuptools<81 for `pkg_resources` |
| 2026-10-30 | `examples/check_meerkat_loader.py --large` | fixture + 1.36 GB L-band-scale set | 21.4 s | 5.6 GB (writer), 2.0 GB loader child | run `outputs/mk1-20261030-03` |
| 2026-10-30 | `rang.meerkat` loader, one dump chunk | 64 antennas, 4,096 ch, 2,016 rows | 0.75 s (dask read 0.19 s) | 2.0 GB VmHWM | DASK_NUM_WORKERS=4 |
| 2026-10-30 | `examples/fetch_meerkat_mvf.py --native-flags` | fixture, 3 antennas | 0.78 s | 262 MB | 5 chunks, 57 rows |
| 2026-10-30 | pytest `tests/test_mk1_meerkat.py` | 8 tests | 4.1 s | 307 MB | |
| 2026-10-30 | `bash tools/check-all.sh` | worktree | 124 s | – | `overall: PASS`, 669 passed, 9 skipped; log `outputs/mk1-20261030-check-all.log` |

## For the coordinator

Shared-file changes, none applied here.

**`python/rang/core_cli.py`**, in the command table after `"ms"`:

```python
    "meerkat": {
        "help": "MeerKAT MVFv4 archives through katdal, task MK1 (research/mk1-katdal.md)",
        "fetch": _script("fetch_meerkat_mvf.py", _first),
        "compare": _script("check_meerkat_loader.py", _first, "the MK1 checker"),
    },
```

**`research/README.md`** index entry:

> New, 2026-10-30: MK1, the [MVFv4 loader](mk1-katdal.md): a `[meerkat]`
> extra (katdal 0.23) and `rang.meerkat`, MVF archives into core row chunks
> with native flag bits; exact against raw chunks, katdal and mvftoms on a
> synthetic archive (no public MVF exists); L3 is ready when data arrive.

**`research/STATE.md`** paragraph (top):

> MK1 MVFv4 loader (big plan), 2026-10-30 (implemented; measured;
> [mk1-katdal.md](mk1-katdal.md)). Protocol frozen first. An optional
> `[meerkat]` extra (`katdal==0.23`, `katsdptelstate[rdb]==1.0.0`; installs
> on Python 3.12–3.14 on Linux and 3.13–3.14 on native Windows; python-lzf and rdbtools
> are sdist-only, so a C compiler is needed everywhere, and cityhash has no
> cp314 wheel) and `rang.meerkat`, which opens an MVFv4 archive (RDB URL with
> token, or a local `.rdb` and `.npy` chunk store) through katdal and yields
> row chunks in the core's layout (ANTENNA1/2, TIME, FLAG_ROW, UVW, DATA,
> FLAG, WEIGHT_SPECTRUM, plus the uint8 FLAG_BITS) with mvftoms' column
> conventions (rows time-major, baselines in its own lexicographic order);
> `examples/fetch_meerkat_mvf.py` writes them to `.npy` without an MS. No
> public MVF archive exists (SARAO's are token-gated), so the acceptance ran
> on a synthetic archive written by katdal's own writers: shuffled baseline
> order, partial chunks, a lost chunk, a zero autocorrelation and an L1 flag
> stream. Against arrays rebuilt from the raw chunks, katdal's own arrays
> (local and over HTTP) and `mvftoms.py`'s MS read by the core, DATA, FLAG,
> FLAG_BITS, WEIGHT_SPECTRUM, TIME and ANTENNA1/2 are bitwise equal; UVW is
> within 1.8e-12 m of katdal and bitwise equal to mvftoms. Weights are
> `weights × weights_channel` divided (not multiplied) by both
> autocorrelation powers. katdal by default replaces the L0 ingest flags
> with katsdpcal's `sdp_l1_flags`; L3 must open with `upgrade_flags=False`
> to see native observatory flags (bits static, cam, data_lost, ingest_rfi,
> predicted_rfi). katdal's dask read is 0.19 s of 0.75 s per 64-antenna,
> 4,096-channel dump, so the chunk reader is not ported. Next: L3 when the
> observer's data arrive, preferably as MVF; then the LUNO cross-check (c).

**`research/tool-timings.md`**: the rows of the timings table above (the
check-all row with its measured wall).

**`research/big-plan.md`**, the wave 2 tooling line: "MK1 done 2026-10-30
(`mk1-katdal.md`): `[meerkat]` extra and `rang.meerkat`; exact on a
synthetic MVFv4 archive against raw chunks, katdal and mvftoms; (c) waits for
an MVF matching LUNO."

**`research/ecosystem-survey.md`** (shared; correction): in the MVFv4 format
row and section 5.2 item 4, "× autocorr power if `need_weights_power_scale`"
should read "÷ (auto_i × auto_j) power if `need_weights_power_scale`"
(`katdal/vis_flags_weights.py: weight_power_scale`, `divide=True` for
unscaled stored weights).

**`research/flagging-luno-candidate.md`**, under "Raw DATA and native flags":
"MK1 (2026-10-30, `mk1-katdal.md`) can read an MVF copy of the observer's
dataset directly; ask for MVF (an archive RDB link) rather than an mvftoms
MS, which reduces the flag bitfield to a boolean and derives SIGMA_SPECTRUM
from the weights."

**`research/non-ratt-observations.md`** rows (SARAO, `ska-sa`; not RATT):

| Software | Observation | Evidence | What a report would say | Status |
| --- | --- | --- | --- | --- |
| katdal 0.23 (`ska-sa`) | `katdal/ms_extra.py` line 30 imports `pkg_resources.parse_version`; with the setuptools 84.2.1 that katsdptelstate[rdb] pulls in on Python ≥ 3.12, `mvftoms.py` fails at import (`ModuleNotFoundError: pkg_resources`) | [mk1-katdal.md](mk1-katdal.md), deviation 3 | Use `packaging.version.parse` (packaging is already a katdal dependency) | not reported by decision |
| katsdptelstate 1.0.0 (`ska-sa`) | The `[rdb]` extra needs python-lzf 0.2.6 (C extension) and rdbtools 0.1.15, both sdist-only on PyPI, so every install of katdal needs a C compiler | `uv pip compile --python-platform` over Windows, Linux, macOS × 3.12–3.14 ([mk1-katdal.md](mk1-katdal.md)) | Wheels for python-lzf (not SARAO's), or an optional pure-Python LZF path | not reported by decision |
| katdal 0.23 (`ska-sa`) | Last PyPI release 2024-06-28 while the repository is active (push 2026-10-22); works unchanged on Python 3.14 and NumPy 2.5 for the paths MK1 uses | [mk1-katdal.md](mk1-katdal.md) | A new release would carry the fixes on main | nothing to report |
| katdal 0.23 (`ska-sa`) | After a chunk 404, `S3ChunkStore` lists the bucket and needs `<Contents>` in the answer, so a non-S3 static HTTP mirror of an archive turns one missing chunk into "store unavailable" | [mk1-katdal.md](mk1-katdal.md), deviation 4 | Documented behaviour for S3; a note for anyone mirroring MVF over plain HTTP | nothing to report |

(cityhash 0.4.10, not SARAO's, has no cp314 wheels; katdal needs it.)

**Ignored output directories**: `outputs/mk1-20261030-03` (17 MB: the
fixture archive, the mvftoms MS, `result.json`, `check.log`),
`outputs/mk1-20261030-check-all.log`. Scratch under
`~/Build/tmp/20261030-mk1/` is deleted at the end of the task.
