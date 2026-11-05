# W1: write-back to an existing Measurement Set

Task W1 of [finish-plan.md](finish-plan.md) (finish line, item 2): rang writes
`MODEL_DATA`, `CORRECTED_DATA` (and any other data column, such as C1's
proposed `CORRECTED_1GC`), `FLAG`, `FLAG_ROW`, `WEIGHT` and
`WEIGHT_SPECTRUM` into an existing MS, in row chunks, after a backup of the
original flags as a CASA flag version, so that a failed or interrupted run
leaves the original flags recoverable. Branch `fp-w1-writeback` from
`9423f13`. The general commands are W2, not this task.

Status: **implemented and measured** (code `2b51f81`, frozen runs
`/mnt/d/rang/w1/w1-20261106-01` and `m3-20261106-01`; supplementary run
`w1-20261106-02` at `9654678` for WEIGHT and WEIGHT_SPECTRUM, which `-01`
did not write). Oracle criteria 1 to 3 and 5 to 7 pass exactly: every
comparison is bit-identical, every flag round trip is equal by SHA-256, and
4 + 8 SIGKILL cases were recovered. Criterion 1 holds for WEIGHT and
WEIGHT_SPECTRUM only from run `-02`. Criterion 4 passes its two image
comparisons (difference 0). It **fails as frozen** in its third part, on
both conditions: the unit point model's image peaks 6 pixels from the
centre, and its peak, 1.0023, is 2.3e-3 from 1 (1.0010 at the centre).
This sparse 4-antenna MS has a broad PSF, and the PSF itself peaks at the
same pixel. The model image equals the PSF to 9.7e-4 (post hoc, labelled).
check-all at the head passes except `test_every_note_is_in_the_research_index`,
which needs the index line in "For the coordinator". Archive:
[results/w1-writeback.json](results/w1-writeback.json). The protocol below
was committed (`cb346d1`) before any comparison.

## Design (proposed in `cb346d1`; implemented in `2b51f81`)

- `python/rang/core_writeback.py`: `WriteBack(ms, flag_backup=..., stage=...)`,
  a context manager that holds the core writer's lock on the MS for the
  whole session, takes the flag backup before its first write, keeps a
  journal and offers chunked reads and writes. Helpers `add_imaging_columns`,
  `restore_flags`, `backup_flags`, `chunks`.
- Columns are added as CASA 6.7.6 `clearcal(addmodel=True)` adds them, as
  measured on a copy of the tv-caracal fixture before this protocol
  (pre-freeze probe, `/mnt/d/rang/w1/probe-20261106-00`): a TiledShapeStMan
  per column named `TiledModel` and `TiledCorrected`, tile
  `[ncorr, nchan, 8]` (1 MiB buckets), the comment of DATA,
  `CORRECTED_DATA` with DATA's column keywords (`UNIT = Jy`), `MODEL_DATA`
  without keywords; every row initialised (`CORRECTED_DATA = DATA`,
  `MODEL_DATA` 1 on the parallel hands and 0 on the cross hands, as
  clearcal leaves them). python-casacore's `addImagingColumns` instead
  leaves the rows undefined (reading row 0 failed in the probe), which
  CASA, WSClean and dask-ms do not accept.
- One deviation from CASA: the core writer adds tiled columns with a fixed
  shape (option 4) only, while CASA's are variable-shape. An MS whose DATA
  cells differ in shape (several spectral windows of different widths) is
  refused with a clear message (W4 owns that case).
- Flag backup: `<ms>.flagversions/flags.<name>` written in chunks under a
  temporary name, read back and compared, renamed, then listed in
  `FLAG_VERSION_LIST` (fsync), all before the first write to the MS. A
  journal `<ms>.flagversions/rang-writeback.json` (written through a
  temporary file and a rename) records an open session; a later session
  refuses to start while one is open, so a half-written FLAG is never taken
  as a new original. `restore_flags` writes a version back in chunks.
- Each chunk is flushed (the tiled writer keeps touched tiles until a
  flush), so memory follows the chunk, not the MS.

## Data

All copies under `/mnt/d/rang/w1/`; inputs read in place, never written.

| Name | Source | Layout | Size |
| --- | --- | --- | --- |
| M1 | `outputs/tv-caracal-wsl-20261029-01/original.ms` (MeerKAT, the CARACAL fixture) | 140 rows × 4096 ch × 4 corr; DATA, FLAG, WEIGHT_SPECTRUM TiledShapeStMan; IncrementalStMan scalars; no MODEL_DATA or CORRECTED_DATA | 40 MB |
| M2 | `outputs/o-casa-20261030-01/c.ms` (O-CASA arm C, written by CASA) | 192 rows × 2048 ch × 4 corr; StandardStMan, FixedShape; MODEL_DATA and CORRECTED_DATA present | 61 MB |
| M3 | written by `rang.core_ms_write.default_ms` in the run (seed 20261106) | 8,192 rows × 1,024 ch × 4 corr, StandardStMan FLAG, tiled DATA | about 0.5 GB |
| T | written by `default_ms` inside pytest (`tests/test_w1_writeback.py`) | small, both FLAG layouts | < 5 MB |

## Oracles and tolerances (frozen before the first comparison)

Storage is an exact round trip; that is the only meaningful bound (A0 gate 2).

1. **casacore read-back.** python-casacore 3.8.1 (`rang-ms-reader:local`)
   and 3.7.1 (`rang-o-casa:6.7.6.14`) read every written column on M1 and
   M2: values **bit-identical** to the arrays rang wrote (MODEL_DATA,
   CORRECTED_DATA, FLAG, FLAG_ROW, WEIGHT, WEIGHT_SPECTRUM); column
   descriptions as designed (value type, ndim, shape, manager type and
   name, comment); keywords equal to the design. Every column rang did not
   write has the same SHA-256 of its values before and after.
2. **Flag round trip.** Backup, then arbitrary FLAG and FLAG_ROW writes,
   then `restore_flags`: SHA-256 of FLAG and FLAG_ROW **equal** to the
   input's, on M1, M2 and T. The same after CASA's
   `flagmanager(mode='restore')` of rang's backup, and after rang's restore
   of a version CASA's `flagmanager(mode='save')` wrote. CASA's
   `flagmanager(mode='list')` lists rang's version.
3. **Interruption.** A writing process is killed with SIGKILL (a) after a
   flushed FLAG chunk, (b) after an unflushed one, (c) during the backup,
   (d) during the initialisation of an added column, and on M3 (e) at 8
   times spread over a FLAG write by an external timer. Pass: the MS opens
   with the core reader and python-casacore; in (a), (b), (e) FLAG differs
   from the input in at least one cell where the kill landed after the
   first write (shown, so the test is not vacuous); a new session refuses
   while the journal is open; after `restore_flags` the FLAG and FLAG_ROW
   hashes equal the input's. In (c): FLAG unchanged, no version listed, a
   rerun succeeds.
4. **WSClean** 3.7 (`rang-o-casa:6.7.6.14`), `-j 1`, `-niter 0`, the same
   other options for each run, on M1 and M2:
   - `-data-column CORRECTED_DATA` (initialised to DATA) against
     `-data-column DATA`: max |Δ| ≤ 1e-6 × max|I_DATA| (expected 0);
   - `-data-column MODEL_DATA` after rang writes `MODEL_DATA = 2·DATA` in
     chunks: max |I_MODEL − 2 I_DATA| ≤ 1e-6 × max|2 I_DATA|;
   - `-data-column MODEL_DATA` as initialised (unit parallel hands, a
     1 Jy point at the phase centre): the peak pixel is the centre pixel and
     |peak − 1| ≤ 1e-3.
5. **CASA** 6.7.6 (`rang-o-casa:6.7.6.14`) on M1:
   `listobs` runs; `split(datacolumn='corrected')` and `'model'` give a
   DATA column bit-identical to rang's CORRECTED_DATA and MODEL_DATA, and
   FLAG equal; `gencal(caltype='amp', parameter=[2.0])` then `applycal`
   writes into the CORRECTED_DATA column rang created: per cell
   |CASA − DATA/4| ≤ 1e-6 × |DATA/4| or ≤ 11 float32 epsilons of the
   cell's largest correlation (C1 class C).
6. **QuartiCal's reader**, dask-ms in `/opt/qc` of
   `rang-formats-oracle:20261030`: `xds_from_ms` reads MODEL_DATA,
   CORRECTED_DATA, FLAG, FLAG_ROW and WEIGHT_SPECTRUM of M1 and M2
   **bit-identical** to rang's values.
7. **Memory.** On M3, rewriting FLAG and writing a new CORRECTED_DATA in
   chunks of 512 rows: peak RSS growth of the writing process (VmHWM after
   reset) ≤ 4 × the chunk's bytes of the widest column + 64 MiB, and below a
   quarter of the column's bytes. Reported, not gated: wall time (no timing
   work: the host is shared).

A failure is reported as measured and not reworded.

## Python API (implemented, `python/rang/core_writeback.py`)

For C4b, G6 and W2. Values are given as python-casacore takes them: rows
first, then (channel, correlation).

| Call | What it does |
| --- | --- |
| `WriteBack(ms, flag_backup="rang_original", stage="", comment=None, on_interrupted="refuse", chunk_rows=None, on_chunk=None)` | A context manager (or `begin()` and `close(error=None)`). It holds the core writer's lock for the session. Before the writer opens, it saves FLAG and FLAG_ROW as flag version `flag_backup` unless one with that name exists, then writes the journal. |
| `w.chunks(chunk_rows=None)` | `[(start, n)]` over all rows. The default is about 64 MiB of complex64 cells, a multiple of 64 rows (512 rows at 4096 × 4). |
| `w.read(name, start, n)` | Reads rows through the session's writer. Opening the MS with another reader in the same process would drop the fcntl lock. |
| `w.write(name, start, values)` | Writes any existing column and flushes. The cell shape is checked. FLAG and FLAG_ROW go to `write_flags`. |
| `w.write_flags(start, flag, flag_row=None)` | Writes FLAG and/or FLAG_ROW exactly as given. The caller decides the OR with old flags and the FLAG_ROW policy (C1 3.2); `flag_row_all(flag)` is a helper for the second. |
| `w.ensure_column(name, init="default")` | Adds `name` if it is missing, as a TiledShapeStMan column: complex64, or float32 for WEIGHT_SPECTRUM and SIGMA_SPECTRUM. It initialises the column with `"data"`, `"unity"`, `"zero"`, `"weight"`, `"sigma"`, a callable `(start, n)`, or None. The defaults by name: MODEL_DATA unity; CORRECTED_DATA and CORRECTED_1GC data; WEIGHT_SPECTRUM weight; SIGMA_SPECTRUM sigma. An existing column is checked for type and cell shape and kept, except one an interrupted session was still initialising, which is initialised again. Returns True when the column was added. |
| `add_imaging_columns(ms)` | MODEL_DATA and CORRECTED_DATA in one session. |
| `backup_flags(ms, name)`, `restore_flags(ms, name)` | Save if absent; write a version back in chunks, read back and compare each chunk, and mark an interrupted journal `restored`. |
| `layout(ms)` | Rows, the one DATA cell shape, CORR_TYPE, columns and descriptions. Raises `UnsupportedLayout` (W4) when the data descriptions differ in shape or correlations. |
| `read_journal(ms)` | `<ms>.flagversions/rang-writeback.json`: state (`open`, `closed`, `failed`, `restored`), backup name, stage, pid, host, times, columns written, and columns still being initialised. |

`rang.formats.flagversions` gains `restore`, `exists`, `spans` and `root`. Its
`save` now writes in chunks under `flags.<name>.rang-partial`, reads the
version back and compares it, renames it, and only then lists it (fsync).
`rang.formats._aipsio.column_descriptions` reads the column comments and
keywords from `table.dat`, with typed scalars. It also fixes the decoding
of version-3 `Array` keyword values (ndim and lengths, not an IPosition),
which the table keywords of a real MS use. The core writer now writes a tiled
manager's header `table.f<N>` through `table.f<N>_tmp` and a rename, so a
kill during a flush cannot leave it truncated. The bytes written are unchanged.

## Results (frozen run, code `2b51f81`)

Run `tools/oracles/w1/run.sh /mnt/d/rang/w1/w1-20261106-01`, 192 s.
Run `tools/oracles/w1/m3.sh /mnt/d/rang/w1/m3-20261106-01`, 296 s.
Seeds: write flags 7, M3 20261106, the kill times 20261106, and the kill
child 1. On M1 and M2, `run_writes` used chunks of 48 rows, which cross
the 8-row data tiles and the 64-row flag tiles.

| # | Criterion | M1 (columns added) | M2 (columns present) | Verdict |
| --- | --- | --- | --- | --- |
| 1 | python-casacore 3.8.1 and 3.7.1: SHA-256 of every readable column equals rang's | 25 of 25 columns, 0 mismatches | 26 of 26, 0 | pass |
| 1 | value checks (MODEL = 2 DATA, CORRECTED = DATA, FLAG and FLAG_ROW as written, backup = pristine flags) | all true | all true | pass |
| 1 | WEIGHT and WEIGHT_SPECTRUM written and read back | not exercised in `-01` (see run `-02` below) | not exercised | – |
| 1 | columns rang did not write unchanged (casacore's hash = rang's hash before the writes) | true | true | pass |
| 1 | descriptions | MODEL_DATA and CORRECTED_DATA: complex, TiledShapeStMan `TiledModel` and `TiledCorrected`, ndim 2, shape [4096, 4], option 4, comment "The data column", keywords {} and {UNIT: Jy} | CASA's own StandardStMan columns kept | pass |
| 2 | CASA `flagmanager(restore)` of rang's backup: FLAG and FLAG_ROW hashes equal the pristine ones | equal | equal | pass |
| 2 | rang `restore_flags` of a version CASA `flagmanager(save)` wrote, after inverting all flags | equal | equal | pass |
| 2 | CASA `flagmanager(list)` lists `rang_original` with its comment | yes | yes | pass |
| 4 | WSClean, `-data-column CORRECTED_DATA` against `DATA` | max abs difference 0 (DATA peak 3.18) | 0 (peak 9.29) | pass |
| 4 | WSClean, `MODEL_DATA` against 2 × `DATA` image | 0 | 0 | pass |
| 4 | WSClean, the unit model as initialised: peak at the centre pixel and within 1e-3 of 1 | peak 1.00230 (2.3e-3 from 1) at (256, 262); centre (256, 256) 1.00097 | – | **fail as frozen**, both conditions |
| 5 | CASA `split` of `corrected` and `model`: DATA, FLAG and FLAG_ROW bit-identical to rang's columns (rows 140 and 192) | equal | equal | pass |
| 5 | CASA `gencal` amp 2 then `applycal` into rang's CORRECTED_DATA, against DATA/4 | 2,293,760 cells, all exactly equal | 1,572,864 cells, exactly equal | pass |
| 6 | dask-ms 0.2.32 (QuartiCal 0.2.7's venv), `xds_from_ms`: hashes of DATA and the 5 written columns, value checks | 0 mismatches, all true | 0, all true | pass |
| 3 | SIGKILL, pytest (`tests/test_w1_writeback.py`, both FLAG layouts in the other tests): (a) after a flushed FLAG chunk, (b) before a flush, (c) during the backup, (d) during CORRECTED_DATA's initialisation | MS opens; FLAG differs in (a) and (b); refused while open; restore gives the input's hashes; (c) unchanged, no version listed, rerun saves one; (d) `continue` initialises the column again | – | pass |
| 3 | (e) M3, 8 kills at 0.064 s to 0.374 s of a 0.50 s FLAG write (chunks of 256 rows) | all 8: core reader and python-casacore 3.8.1 open the MS and read FLAG; journal open; FLAG differs; refused; restored hashes equal | – | pass |
| 7 | M3 memory: CORRECTED_DATA added (268 MB column) and FLAG rewritten in 512-row chunks | VmHWM growth 53.1 MB; bounds 134 MB (4 × 16.8 MB chunk + 64 MiB) and 67 MB (a quarter of the column) | – | pass |

Reported, not gated: QuartiCal 0.2.7 `goquartical` solved a G
`diag_complex` term on rang's CORRECTED_DATA (= DATA) against rang's
MODEL_DATA (= 2 DATA). The median |g| on the parallel hands was
0.70710678118575 on M1 and M2, against 1/√2 = 0.70710678118655 (largest
deviation 8.0e-13, 8 solutions each). M3 measured 274 MB on disk, not the
"about 0.5 GB" estimated in the data table. The memory session took 22.6 s.
The trial run (`-00-trial`, the same code before the post-hoc PSF lines and
the QuartiCal step) gave the same verdicts.

**Supplementary run `-02`** (`tools/oracles/w1/run.sh
/mnt/d/rang/w1/w1-20261106-02`, code `9654678`, 182 s, the same committed
tolerances). It exists because `-01` wrote neither WEIGHT nor
WEIGHT_SPECTRUM: both MSs already had WEIGHT_SPECTRUM, and WEIGHT was never
touched.
- On M1 and M2, `run_writes` now also writes a seeded WEIGHT_SPECTRUM
  (uniform 0.5 to 2, seed 7) and WEIGHT as its channel median. These go
  into M1's variable-shape TiledShapeStMan `TiledWgt` and M2's
  variable-shape StandardStMan WEIGHT.
- M0, an MS written by `make_ms` (300 rows × 64 ch × 4, tiled FLAG, seed
  20261106) without WEIGHT_SPECTRUM, exercises the add path: WEIGHT_SPECTRUM
  is added (TiledShapeStMan `TiledWgtSpectrum`, float, [64, 4], comment
  "Weight for each data point") and initialised from WEIGHT.
- Results:
  - python-casacore 3.8.1 and 3.7.1 and dask-ms: 0 hash mismatches on M1
    (25 columns), M2 (26) and M0 (24, dask-ms 7).
  - `WEIGHT_SPECTRUM == written` and `WEIGHT == written` are true on M1
    and M2, and `WEIGHT_SPECTRUM == WEIGHT over channels` is true on M0.
  - Every other verdict is as in `-01`: CASA split and applycal exact,
    WSClean differences 0, and the same failure of 4c.
- The first compare of `-02` reported "m1/m2 casacore: false". Its list of
  written columns lacked WEIGHT, so WEIGHT counted as changed although
  unwritten. That was a harness error, not a data difference.
  `compare.py` was fixed and rerun on the same outputs; no tool was rerun.
  CASA and WSClean were not run on M0, because its subtables are minimal.

**Criterion 4c, post hoc (labelled).** M1 is a snapshot from 4 antennas.
WSClean's PSF from the same weights and flags (`-make-psf`) also peaks at
(256, 262), with 1.00132, and it stays at or above 0.9896 within 8 pixels of
the centre. The unit model's image equals that PSF to 9.7e-4. So the column
is read as written. The frozen criterion assumed a PSF that peaks at one
pixel, and it is recorded as failed. A useful version for later tasks: the
image of the unit model against the PSF, ≤ 1e-3.

## Deviations, limits and what was not checked

- **Fixed shape.** Added columns have a fixed shape. CASA's are variable-shape
  (TiledShapeStMan, option 0). An MS with spectral windows of different
  widths is refused (W4).
- **Rows written in place.** Rows are not reordered and the MS is not
  copied. A kill can leave a partly written CORRECTED_DATA or MODEL_DATA
  column. The journal names it, and `ensure_column` initialises it again in
  a `continue` session. Only FLAG and FLAG_ROW are backed up. No other
  column is backed up, because the input DATA is never written.
- **Flush windows.**
  - `table.dat` and the tiled headers are replaced by rename.
  - StandardStMan and IncrementalStMan headers and indexes are rewritten in
    place, as casacore does. A kill inside those writes was not targeted;
    the timed kills (e) hit wherever they landed, in an SSM FLAG.
  - No fsync is issued on the MS files themselves. A power loss, as opposed
    to a killed process, is not covered.
- **Not checked.**
  - CASA `applycal` with rang's own calibration tables: that is C4b.
  - Weights written with `calwt`: the C4 gate.
  - Multi-field MSs beyond M2's single selected field.
  - Big-endian and MultiFile MSs.
  - Windows and macOS: no fcntl lock (e3-table-writer.md), and the SIGKILL
    tests skip off POSIX.
  - MSs above 274 MB.
  - Concurrent writers: the fcntl lock refuses them, but this was not
    re-tested here.
- **The header change in the core writer.** After the change, every frozen
  E3 case was written again with the current core and its files compared
  with casacore's frozen tree (`outputs/e3-20261030-01`, post hoc). Every
  tiled case is identical: F-flag, F-ws, F-data, F-sigma, F-uvw, F-multi,
  F-add-tcs and F-add-tss. 19 of 24 cases are identical in all, as before.
  The 4 that differ are the same StandardStMan padding-only cases E3
  recorded; they are untouched by the change. F-antenna-strings was not run,
  because the recheck harness opened MAIN instead of ANTENNA. The E5 and E6
  cases, MultiFile among them, were not rerun.
- **One untested window.** A kill between the rename of `flags.<name>` and
  its line in `FLAG_VERSION_LIST` leaves a complete version that is not
  listed. FLAG is untouched at that point. A rerun's `save` then refuses
  with "remove it first", so this needs a hand step.
- **Whole rows only.** Writes cover whole rows. A channel-selected
  `applycal` (C4b) reads the row, changes it and writes it back.
- **Old flags.** `flagversions.save` and `load` keep their signatures. A
  version that exists but is not listed is now refused, not overwritten.
- **Not done.** No HISTORY rows are written. CASA writes them; rang's
  receipts (W2) replace them.

## Timings

Rows added to [tool-timings.md](tool-timings.md); per-step wall and peak RSS are in the archive (`timing`).

## For the coordinator

- **research/README.md**, after the C1 line:
  `- [W1, write-back](w1-writeback.md): MODEL_DATA, CORRECTED_DATA and FLAG written into an existing MS in chunks, with a CASA flag-version backup and recovery after an interrupted run; CASA, WSClean, python-casacore and dask-ms read them bit for bit.`
  This line also makes `test_every_note_is_in_the_research_index` pass. It is
  the only check-all failure at the branch head.
- **research/STATE.md**, log, newest first:
  `W1, 2026-11-06 (implemented and measured; [w1-writeback.md](w1-writeback.md)). rang.core_writeback writes into an existing MS. It adds MODEL_DATA and CORRECTED_DATA as CASA's clearcal does (TiledShapeStMan, initialised, but with a fixed shape) and writes any column, FLAG and FLAG_ROW in flushed row chunks. Before the first write it saves the flags as the CASA flag version rang_original. A journal refuses a new session after an interrupted one until the flags are restored. python-casacore 3.8.1 and 3.7.1, dask-ms, CASA (split, flagmanager, applycal into the new column) and WSClean read every written column bit for bit (WEIGHT and WEIGHT_SPECTRUM by casacore and dask-ms, run -02). Flags round-trip exactly through rang and CASA versions both ways. 12 SIGKILL cases all recovered. Peak memory grew 53 MB while a 268 MB column was written. One frozen criterion failed: the unit model's image peaks off-centre on the 4-antenna fixture's broad PSF, which peaks at the same pixel (post hoc). No novelty claim.`
  In "Current status", Running: `Done: A0, C1, G1, W1.`
- **A shared check changed.** `tests/test_w4_6_portability.py`: `NOT_FILES`
  now includes `"os"`, because `os.open` returns a descriptor and decodes no
  text; it is used for the directory fsync. The method `WriteBack.begin` is
  named so that the same check does not take `self.open()` for a text open.
- **research/finish-plan.md**, row W1: `**Done 2026-11-06** ([w1-writeback.md](w1-writeback.md)).` before the task text. C4b, G6 and W2 can call the API above.
- **Owner decisions.**
  - Whether added columns should be variable-shape like CASA's. That needs
    a variable-shape `addcols` in the core writer. Today such an MS is
    refused.
  - The default backup name `rang_original`, and whether W2 takes one
    version per stage (CASA style) or keeps one original.
