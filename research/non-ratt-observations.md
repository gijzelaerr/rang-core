# Observations about non-RATT software

Recorded 2026-10-30 (big plan task U1). By the user's decision, observations about software
outside RATT (`ratt-ru`) are listed here and **not reported anywhere**; each entry says what a
report would contain if that decision changes. RATT items, filed or not, are in
[upstream-issues/](upstream-issues/); the running log is [upstream-notes.md](upstream-notes.md).

| Software | Observation | Evidence | What a report would say | Status |
| --- | --- | --- | --- | --- |
| WSClean 3.6-1 | `CalculateMsLimits` in `gridding/msprovidercollection.cpp` computes the y bound of the grid bounds test from `u` (x = u Δx W, y = u Δy H) instead of `v` | [core-c-gridder.md](core-c-gridder.md); ported as written, the w limits of rang's jobs are unaffected (measured) | The y bounds test should use `v`; affects `min_w`/`max_w` only for visibilities whose `u` and `v` place them differently relative to the image bounds | not reported by decision |
| WSClean 3.6-1 | `-store-imaging-weights` writes `IMAGING_WEIGHT_SPECTRUM` in both the PSF and the dirty pass with the same values; the flag must precede the MS argument | [core-b-weighting.md](core-b-weighting.md) | Write the column once (one pass's I/O saved); the ordering rule is documented, so nothing there | not reported by decision |
| dask 2026.8.0 | `ProgressBar._finish` joins a timer thread that is inside `time.sleep(dt)`, so a large `dt` delays every compute's return by up to `dt` and inflates the reported duration (300.0 s for a 1 s task with `dt=300`) | [upstream-issues/tricolour-nontty-progressbar.md](upstream-issues/tricolour-nontty-progressbar.md) (reproduction) | Wait on a `threading.Event` with timeout `dt` instead of `time.sleep(dt)`, so `_finish` wakes the thread at once. The Tricolour side (the caller choosing `dt=300`) is the RATT issue | not reported by decision |
| Zarr 2.18.7 / numcodecs 0.15.1 | Old dask-ms exports (ESO137) encode object columns with the `pickle` filter, and zarr decodes it without warning, which runs arbitrary code from an untrusted store | [upstream-issues/dask-ms-object-codec.md](upstream-issues/dask-ms-object-codec.md) | An opt-in allow-list of codecs when opening remote stores, refusing `pickle` by default | not reported by decision |
| blosc (via numcodecs) | LUNO DATA chunks hold 196 independently compressed 1 MB blosc blocks with a block-offset table, so a reader could fetch and decode only the blocks it needs; zarr and dask-ms fetch and decode whole chunks (rang's range-request reader moved 15.4 % of the bytes in 11 % of the time) | [core-section6.md](core-section6.md), [core-g-http-fetch.md](core-g-http-fetch.md) | A partial-chunk read path for blosc-compressed chunks; the public bucket serves single ranges only, so requests need coalescing | not reported by decision |
| Public LUNO zarr store (data layout, not software) | DATA chunked 50,000 rows × 128 channels × 4: keeping four stations' 192 rows decodes 3.28 GB to retain 12.6 MB (260×) | [stack-consolidation-feasibility.md](stack-consolidation-feasibility.md) | A row chunk aligned with integrations, or per-baseline grouping, for subset access; a question for the data publishers | not reported by decision |
| NumPy / OpenBLAS | NumPy's OpenBLAS pool keeps eight spinning threads during rang's single-threaded core work (17–18 % of perf samples) | [core-f-performance.md](core-f-performance.md) | Known OpenBLAS behaviour; the fix is rang-side (`OPENBLAS_NUM_THREADS=1` in drivers), nothing to report | rang-side item |
| Rang's own Jacobi eigensolver | The rank survey's 864 32×32 eigendecompositions take 0.51 s against 0.056 s in LAPACK | [core-f-performance.md](core-f-performance.md) | Not upstream at all: a rang optimisation | rang-side item |
| Crystalball 0.4.3 (not under `ratt-ru`) | `license = "GPLv2"` with a real GPL-2 `LICENSE`: metadata and licence text agree | [core-d-tricolour.md](core-d-tricolour.md) section 1 | Nothing to report; rang does not port it | nothing to report |
| katbeam, katsdpsigproc (`ska-sa`) | No defect observed; katsdpsigproc's BSD-3-Clause header covers the SumThreshold kernel rang ported | [core-d-tricolour.md](core-d-tricolour.md), [katbeam-pointing.md](katbeam-pointing.md) | Nothing to report | nothing to report |
| CARACal, Stimela (`caracal-pipeline`) | Developed with RATT people but not under `ratt-ru`; neither observation is a defect | [upstream-issues/caracal-firstpass-intermediate-flags.md](upstream-issues/caracal-firstpass-intermediate-flags.md), [upstream-issues/stimela-python314.md](upstream-issues/stimela-python314.md) | Nothing to report; if the user counts `caracal-pipeline` as RATT, the files there give the reasons | not filed (reason in file) |

## From the S1 review (2026-10-30; not reported by decision)

- **NumPy's bundled OpenBLAS (scipy-openblas64)** starts 16 spinning threads at
  import: a 0.07 s comparator process burns 0.7–0.9 CPU-s; with
  `OPENBLAS_NUM_THREADS=1` the same comparator used 0.09–0.12 CPU-s against
  0.37–0.50 (A/B at load 30). Rang pins it at entry in P9.
- **JAX/XLA on CPU** starts compile, Eigen and execute pools of 16 threads each
  (145 threads in one pytest process) and oversubscribes a shared host; the
  pointing tests slowed about 14× under load 16–33. Addressed in P10.
- **Extension `blosc_decode`** builds a fresh `bytes` per 205 MB DATA tile; 37 %
  of the section 6 checker's samples sit in that frame (first-touch page faults
  and fill), a cost of the decode-to-new-object API, not of LZ4. Rang's own;
  addressed in P5.

## From L1 (2026-10-30; not reported by decision)

- The public store's 50,000-row × 128-channel zarr chunking forces whole-tile
  decode for any station subset (38 s single-threaded for chunk 0); the
  blosc block tables allow partial reads only along rows.

## casacure 3.8.35 (2026-10-30; from the E2 evaluation; not reported by decision, casacure is outside the reporting rule)

Reproductions in `research/casacure-evaluation.md`: (1) invalid dminfo (TiledColumnStMan
on a variable-shape column) accepted and written, casacore refuses the result; (2)
FixedShape not set from a given shape; (3) measures relabel values (UTC→TAI/UT1
return the input; ITRF positions in metres labelled `rad`; `measures.rs:274` treats
UTC/TAI/UT1/UT2 as identical); (4) SIGBUS on a file truncated after open; (5)
`getcoldesc`/`getdminfo` misreport managers; (6) TaQL gaps (`BETWEEN`, bare `SELECT
FROM`, `ORDERBY DESC`, `rownumbers(parent)`); (7) a fabricated FLAG_CATEGORY for
never-written cells; (8) no LICENSE/COPYING file; (9) Windows and macOS wheels untested
in CI; (10) `celestial-eop-data` 0.1.12 build script calls `date` (non-reproducible,
needs POSIX `date` on Windows); (11) `addcols` rebuilds the StandardStMan the column
joins. The user may decide to report these to the author.

## From the ecosystem survey (2026-10-30; not reported by decision)

CASA 6.7.6.14 wheel licence metadata contradicts itself (`GPLv2`, an LGPL
classifier, LGPL-2.0-or-later headers) and ships no Windows wheels; IDG and
DP3 release records are incomplete; Aegean is AFL-3.0 (GPL-incompatible per
secondary sources); facetselfcal has no licence; the PyPI name `carta` belongs
to an unrelated package (carta-python is not on PyPI).

## From DF1 (2026-10-30; not reported by decision)

- ducc0 0.42: `vis2dirty` defaults `divide_by_n=True` and the opposite w sign
  from rang's DFT convention; the kernel and grid choice depends on the thread
  count and SIMD width (oracles must pin `nthreads=1`); the thread pool
  silently follows `OMP_NUM_THREADS`. No bug found.
- WSClean: the default padding 1.2 with the 7-tap Kaiser–Bessel kernel aliases
  sparse-array PSF sidelobes to about 20 % of the peak at the field edge
  (four-station LUNO slice; 2.1e-5 at padding 2 with kernel 15). A note, not a
  bug; WSClean 3.6+ defaults to the wgridder.

## From O-CASA (2026-10-30; not reported by decision)

- CASA casatools 6.7.6.14: the `manylinux_2_34` wheel bundles `libssl` 3.2 and
  `libldap` but relies on a system `libcrypto` ≥ 3.2 with MD2, so it does not
  import on Ubuntu 24.04 (the `manylinux_2_28` wheel does); `gaincal` K passes
  `minblperant` 4 with three baselines per antenna where G does not; tasks that
  write no table return without an exception; with `casaconfig` auto-updates
  off, Ubuntu's `casacore-data` works but CASA logs SEVERE notices on start.
- WSClean 3.7 wgridder: `-j 4` is not bit-reproducible (2e-6 relative); `-j 1` is.

## From P9 (2026-10-30; not reported by decision)

- maturin `develop` (through `uv pip install --force-reinstall`) cannot replace
  a console-script launcher that is running on Windows; uv's default cache on
  this Windows host hit "too many temporary files" (`UV_CACHE_DIR` moved it).

## From C1 (2026-10-30; data, not software)

- LUNO's QuartiCal-derived WEIGHT_SPECTRUM overstates the noise several-fold
  (closure z² of 0.17–0.18 against 1 expected), and normalised closure TV has
  an antenna-additive component (R² 0.47 against a 0.15 null) consistent with
  an uneven per-antenna weight scale.

## From E3 (2026-10-30; not reported by decision)

- casacore 3.8.1 writes uninitialised bytes into the 4-byte alignment padding of
  `table.fNi` (its output differs between runs; `MALLOC_PERTURB_` changes it);
  it rewrites `table.dat` every time it releases a write lock (a note).
- casacure 3.8.35: every column of a 0-row table reads back as an empty int32
  array (twelfth item).
- python-casacore: `DEFAULTTILESHAPE` is passed through unreversed (a note).

## From FS1 (2026-10-30; not reported by decision)

- CASA 6.7.6 `setjy`: returns `{}` without raising when coefficient tables are
  missing (stale MODEL_DATA stays); unknown source names get 1 Jy with only a
  SEVERE log line; SR2016 switches at the 11.1496 GHz crossing, not the
  documented 11 GHz; compiled coefficients are float32, about 3e-7 from the
  decimals; the "Baars" 1934−638 polynomial is not in Baars et al. 1977.

## From DF2a (2026-10-30; not reported by decision)

- ducc0 0.42: wide-field edge pixels are order-sensitive at 1e-11 to 1e-10 of
  the peak (rounding amplified by the gridding correction, up to 3 × 10⁵ in a
  0.3 rad field's corners), so bit-level comparisons need a matching tolerance;
  `do_wgridding=False` is the default, a second trap beside `divide_by_n`.

## From DF2b (2026-10-30; not reported by decision)

- WSClean 3.7 (KERN `3.7-1kern1`): the log does not state the wgridder's
  precision or kernel; agreement with an exact gridder stops at 2–4e-7 of the
  peak even at `-wgridder-accuracy 1e-8`, which points to float32 image
  buffers after the inversion (not verified in the source). The default
  accuracy 1e-4 leaves 1.5–4.2e-5 of the peak. The wgridder does not divide
  by n (ducc0's default is the opposite). On L1 accuracy 1e-4 took longer
  than 1e-6 (98 s against 68 s, one run each, load 10–13); not investigated.
  The certified-imaging study found the same day that O-CASA's archived
  `r1-*.fits` reference is 17 % off the exact transform through WSClean's
  default minimum-grid-resolution upsampling; DF2b's comparison did not use
  that file (its WSClean runs were made from the gridder inputs at
  accuracy 1e-6 and agree to 2.5–4e-7).

## From E4 (2026-10-30; not reported by decision)

- casacore 3.8.1 (E3's item, confirmed): `table.fNi` alignment gaps hold
  uninitialised heap bytes (4 of 18 cases differ under `MALLOC_PERTURB_=85`).
- casacore 3.8.1 (note): the bucket cache writes its scratch buffer (the last
  bucket read or written) into a freed StandardStMan bucket, and the string
  handler starts a new string bucket with the previous bucket's characters:
  file contents depend on access history (deterministic, unreferenced).
- CASA 6.7.6 (note): calibration tables name the columns' data-manager group
  `StandardStMan` where a casacore 3.8.1 deep copy keeps `MSMTAB`; rows are
  sorted with a non-stable heap sort.
- python-casacore 3.8.1 (note): Python int keywords become Int64, `getcell`
  returns Python scalars, uChar cells come back as uint16.

## From B1-2 and X2 (2026-10-30; not reported by decision)

- SARAO holography release: the array-average beam's on-axis gradient changes
  by 7–11 % between the halves of a 6.7 MHz interval at 1070–1284 MHz, so the
  beam centroid has real frequency structure at that scale (informational;
  it matters to pointing solves with coarse bandpass intervals).
- wgpu 30.0.1: the DX12 backend did not expose `Features::SHADER_F64` on an
  RTX 4070 Ti (driver 621.01) while Vulkan does on the same card (cause not
  investigated); naga rejects `active` as an identifier (reserved word);
  WGSL and SPIR-V GLSL.std.450 have no f64 `sin`/`cos`, so an f64 phasor
  needs its own polynomial; no portable query of free device memory, so a
  budget must be configured by hand on a shared GPU; on WDDM a modest
  oversubscription is paged silently and slows compute about 4×.

## From MK1 (2026-10-30; SARAO `ska-sa`, not RATT; not reported by decision)

| Software | Observation | Evidence | What a report would say | Status |
| --- | --- | --- | --- | --- |
| katdal 0.23 (`ska-sa`) | `katdal/ms_extra.py` line 30 imports `pkg_resources.parse_version`; with the setuptools 84.2.1 that katsdptelstate[rdb] pulls in on Python ≥ 3.12, `mvftoms.py` fails at import (`ModuleNotFoundError: pkg_resources`) | [mk1-katdal.md](mk1-katdal.md), deviation 3 | Use `packaging.version.parse` (packaging is already a katdal dependency) | not reported by decision |
| katsdptelstate 1.0.0 (`ska-sa`) | The `[rdb]` extra needs python-lzf 0.2.6 (C extension) and rdbtools 0.1.15, both sdist-only on PyPI, so every install of katdal needs a C compiler | `uv pip compile --python-platform` over Windows, Linux, macOS × 3.12–3.14 ([mk1-katdal.md](mk1-katdal.md)) | Wheels for python-lzf (not SARAO's), or an optional pure-Python LZF path | not reported by decision |
| katdal 0.23 (`ska-sa`) | Last PyPI release 2024-06-28 while the repository is active (push 2026-10-22); works unchanged on Python 3.14 and NumPy 2.5 for the paths MK1 uses | [mk1-katdal.md](mk1-katdal.md) | A new release would carry the fixes on main | nothing to report |
| katdal 0.23 (`ska-sa`) | After a chunk 404, `S3ChunkStore` lists the bucket and needs `<Contents>` in the answer, so a non-S3 static HTTP mirror of an archive turns one missing chunk into "store unavailable" | [mk1-katdal.md](mk1-katdal.md), deviation 4 | Documented behaviour for S3; a note for anyone mirroring MVF over plain HTTP | nothing to report |

(cityhash 0.4.10, not SARAO's, has no cp314 wheels; katdal needs it.)

## From DF-IO (2026-10-30; not reported by decision)

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

## From T1 (2026-10-30; not reported by decision, casacure is outside the reporting rule)

| Software | Observation | Evidence | What a report would say | Status |
| --- | --- | --- | --- | --- |
| casacure 3.8.35 (Tim Molteno) | A Direct fixed-shape string-array column (`makearrcoldesc(..., shape=[2], options=1)`) cannot be read at all: `getcol` and `getcell` raise `bad string reference: bucket 0, offset 8, length 0`, also for a table python-casacore 3.8.1 wrote; casacore and the rang core read it | `outputs/t1-20261030-01/sd-casacore.txt`, `sd-casacure.txt` | Read Direct string arrays (casacore stores them in the StandardStMan string buckets) | not reported by decision |
| casacure 3.8.35 | `getcol` of a variable-shape array column whose rows differ in shape returns an array in the first row's shape, silently dropping the rest of every longer row; casacore raises `StManIndArray::get/put shapes not conforming` | `outputs/t1-20261030-01/ragged-*.txt` | Raise, as casacore, or return per-row cells | not reported by decision |
| casacure 3.8.35 | `getcell`/`getvarcol` of an undefined cell return a 0-d `0.0` (casacore raises); no `iscelldefined` and no `info()` in the Python API | `outputs/t1-20261030-01/undefined-cells.json` | Raise or return None for undefined cells; add `iscelldefined` and `info` | not reported by decision (defaults by design, issue #8) |
| casacure 3.8.35 | `getvarcol(name, start, n)` numbers its keys from the first row read (`r1`…), python-casacore from row 0 (`r{start+1}`…) | this file, Implementation | Use python-casacore's numbering | not reported by decision |
| casacure 3.8.35 | No macOS x86_64 wheel and no cp310 macOS arm64 wheel on PyPI (Linux and Windows cover cp310–cp314) | PyPI JSON, 2026-10-30 | Publish them (the Windows/macOS wheels are not tested upstream either, E2 candidate 9) | not reported by decision |
