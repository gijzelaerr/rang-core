# W1: write-back to an existing Measurement Set

Task W1 of [finish-plan.md](finish-plan.md) (finish line, item 2): rang writes
`MODEL_DATA`, `CORRECTED_DATA` (and any other data column, such as C1's
proposed `CORRECTED_1GC`), `FLAG`, `FLAG_ROW`, `WEIGHT` and
`WEIGHT_SPECTRUM` into an existing MS, in row chunks, after a backup of the
original flags as a CASA flag version, so that a failed or interrupted run
leaves the original flags recoverable. Branch `fp-w1-writeback` from
`9423f13`. The general commands are W2, not this task.

Status: **protocol frozen** (this section, committed before any comparison).
Results follow in later sections.

## Design (proposed; implemented in the commits after this one)

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
