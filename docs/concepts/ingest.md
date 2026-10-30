# Data ingest: Measurement Sets, zarr and HTTP range fetch

## Measurement Sets

`rang.core_ms` opens casacore tables read-only through the core's Rust reader
and returns columns as python-casacore's `getcol` does: a leading row axis,
then the cell axes in reversed casacore order, with the same NumPy dtypes.
StandardStMan, IncrementalStMan (scalars), TiledShapeStMan and
TiledColumnStMan columns are readable, which covers the MeerKAT fixture and
the LUNO exports. The reader was gated on column-exact reads of both
({gh}`research/core-e-ms-reader.md`).

`rang.core_ms_write` writes into existing tables (`putcol`, `putcell`,
keywords, `addcols`) holding casacore's lock, and its files are
byte-identical to casacore 3.8.1's apart from uninitialised padding
({gh}`research/e3-table-writer.md`). Creating new tables still needs
python-casacore.

## Zarr and the HTTP range fetch

The LUNO calibrator observation is a public zarr v2 store of blosc-compressed
chunks. `rang.core_zarr.read_rows` uses each chunk's block-start table to read
and decode only the blosc blocks that hold the requested rows, so a 205 MB
tile is never expanded in full ({gh}`research/core-section6.md`).

`rang.core_fetch` applies the same block arithmetic over HTTP: one ranged GET
for a chunk's header and block table, then one ranged GET per contiguous run
of needed blocks. For the four-station slice that is 752 MB in 2,124
requests instead of 4.87 GB of whole tiles, 6.5 times fewer bytes and 9.1
times faster, with every fetched byte hash-equal to the archived tiles
({gh}`research/core-g-http-fetch.md`). Decoding writes straight into the
final `(row, channel, correlation)` arrays, so no column is held twice
({gh}`research/p5-memory.md`). Fetched bytes are data: they are hashed,
decoded and never executed.

## The teaching datasets

`rang.notebook.data` loads the two datasets the tutorials use:

- the public SKA pointing fixture `outer_scans.zip` (45 MB, four antennas,
  scan 9), downloaded by `rang.notebook.data.download_fixture` into a cache
  directory you name and verified against its pinned SHA256;
- the four-station LUNO PKS 1934−638 slice, range-fetched as above (about
  755 MB) or read from a local copy.
