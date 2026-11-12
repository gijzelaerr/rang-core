# Sliced reads: channel chunks read only their channels

Finish-plan section 7 item 22 ([finish-plan.md](finish-plan.md)): W3b
([w3b-chainchunks.md](w3b-chainchunks.md) section 6) found that a channel
chunk of B, Xf or Df re-reads and re-prepares the whole interval's rows for
every chunk and both replay passes (Df four), because the pre-apply ran on
whole rows and the reader had no channel-sliced read. Its arms with one
channel per chunk took 16-32 min, and the whole-array calibrate 32 and 52 min.
E2 and E3 run whole-array data at 4096 channels, so this sits on the critical
path's wall time. Branch `sliced-read` from origin/main `bd15126`. Resource
work: no scientific novelty is claimed; the speed is measured against the same
code before the change on the same host.

**Status: proposed** (sections 0 to 4 are frozen before any code is written).

## 0. What the code does at `bd15126`

- The Rust reader (`core/src/ms.rs`, `Table::read_column`; Python
  `rang.core_ms.Table.getcol`, `core_ms_write.Table.getcol` through the
  writer, `core_writeback.WriteBack.read`) reads whole cells of a run of
  consecutive rows. `core_chunks.read_rows(source, name, rows, chans,
  block_rows)` reads runs of rows, then cuts the channels in NumPy.
- `cal_chunks.load` reads a channel chunk in blocks of whole rows (all
  channels), runs the field's `prepare` (pre-apply of the earlier tables,
  SIGMA to weights, P's rotation for the polarisation terms, each row's
  weight sum `row_w`) on each block, and cuts the result to the chunk's
  channels.
- Tile shapes of the sets (casacure `getdminfo`): `w3.ms` DATA and
  WEIGHT_SPECTRUM `[4, 4096, 2]`, FLAG `[4, 4096, 16]` (TiledColumnStMan);
  poldx, polholdout and A1 small DATA `[4, 256, 32]`, FLAG `[4, 256, 256]`
  (A1: 64 channels, its own tiles). **Every tile of these sets spans all
  channels**, so a channel slice cannot skip bytes on disk there: what it
  saves is the decode and copy of the other channels, and, with a sliced
  prepare, the pre-apply and NumPy work on them.

## 1. Design (proposed)

1. **Reader.** `Table::read_column_slice(name, start, count, slice)` with a
   per-cell-axis range (casacore order; for visibilities axis 1 is the
   channel). TiledShapeStMan and TiledColumnStMan visit only the tiles that
   intersect the slice and copy only its pixels; other managers read the
   cells and cut them in Rust. A list of ascending rows is read in one call
   (`read_rows`) sharing one tile cache across its runs. `read_column` is the
   slice over every axis. Exposed on `MsTable.read`/`read_rows` and
   `MsWriter.read`/`read_rows`, and in Python as `getcol(..., chans=)` and
   `read_rows(..., chans=)`; columns without a channel axis (WEIGHT, SIGMA,
   scalars) are read whole.
2. **`core_chunks.read_rows`** with `chans` reads the slice through the
   reader (no read blocks of whole rows are needed then).
3. **Pre-apply on a channel window.** `cal_apply.apply(..., channels=)`:
   the frequencies stay the whole band and the data hold the window's
   channels. The kernel builds each (antenna, time) table on the whole band
   exactly as now (CASA's frequency resampling has a shortcut, `same`, taken
   only when the solution channels equal the data channels, so a subset
   given as the band would change B's and Xf's pre-applied values) and loops
   the cells of the window only.
4. **`cal_chunks.load`** reads a channel chunk's channels only and prepares
   them on the window. The rows' weight sums (`row_w`, a sum over all
   channels after the pre-apply's flags; partial sums would not be
   bit-identical) come from one pass of whole-row blocks per interval,
   memoised and reused by the interval's other chunks and the second pass.
5. Nothing else changes: chunk plans, budgets, stop-test replay, kernels.

## 2. Data and arms (frozen)

Sets and configurations are W3b's (section 2 there), read-only sources:
O (O-CASA's slice, copied once from the WSL home to
`D:\rang\outputs\sliced-read-data\o-casa-work.ms` and hashed), C (A1 small),
P (poldx), H (polholdout), W (`w3.ms`, calibrate K, G, B only). Each arm runs
on a fresh copy. Runs native on Windows (W3b ran on WSL), under
`D:\rang\outputs\sliced-read-<date>-<nn>`.

- **U**: main `bd15126` unchunked (W3b's U rule), a detached checkout with
  its own release extension. O, C, P, H.
- **D, T, M**: W3b's default limit, `chunk_rows: 7`, and its low limit rule
  (`compare.py m_limit`), on this branch. O, C, P, H, W (no T on W).
- **B-D, B-T, B-M** ("before"): the same arms on main `bd15126`, for the
  timings and, on W (which has no U), as the identity reference.

## 3. Criteria (frozen)

Tolerance: **bit-identical**. The change moves no arithmetic, so any
difference is a failure, reported as measured.

1. **Identity** on O, C, P against U for D, T, M, with W3b's comparison
   (`tools/oracles/w3b/compare.py verdict`): every calibrate run-directory
   file byte-identical, every MS column (casacure SHA-256) and flag version
   equal after calibrate and apply, summaries equal after W3b's cleaner.
2. **W identity**: branch D against B-D and branch M against B-M (tables,
   columns, flag versions, summaries), and D against M.
3. **Held-out** H: criterion 1 on H, run once after 1 and 2.
4. **Reader unit tests**: sliced and row-list reads equal `getcol(...)[:,
   chans]` of whole reads, and casacure's `getcolslice`, on tables whose
   tiles split the channel axis without dividing it, for TiledShapeStMan and
   TiledColumnStMan, a Bool column with a slice starting off a byte, complex,
   float and int columns, big-endian and little-endian tables, StandardStMan
   arrays (the cut path), and the reader's existing casacore (task E dump) and
   casacure oracle tests unchanged. The pre-apply on a window equals the
   whole-band pre-apply cut, for K, G, B (solution channels equal to the data
   channels, and not) and Xf/Df. `cal_chunks.load` sliced equals the
   whole-row path for G, B and the polarisation terms.
5. **Memory** on W: peak working set of calibrate at or below the limit (D 8
   GiB, M its limit).

## 4. Timing (reported, frozen protocol)

Wall time and peak working set of each stage (`calibrate`, `apply`) for
B-T and T on C, P, H, B-D, D, B-M and M on W, and B-D and D on P. Each timing
run takes the heavy lock exclusively (`tools/heavy_lock.py run --`, from the
main checkout), and `heavy_lock.py status` is recorded at its start. One run
per arm: the ratio is reported as measured, not as a distribution. The
change is kept if criteria 1 to 5 pass, whatever the timing shows; a slower
arm is reported.

## 5. Results

### 5.1 Where a channel chunk's time goes (profile, run -01)

`D:\rang\outputs\sliced-read-20261111-01-profile`, `tools/oracles/sliced/profile_b.py`:
B on poldx field 0 (`combine: scan`, K and G pre-applied, unit model,
`chunk_rows: 7`, so 256 one-channel chunks, 512 loads over the two replay
passes, 50 iterations), under cProfile, one run each as a shared heavy-lock
job (4 slots; not a timing measurement).

| Cumulative s | `bd15126` | branch `63fed2e` |
| --- | ---: | ---: |
| `bandpass` (wall) | 26.3 | 10.4 |
| `cal_chunks.load` | 25.0 | 9.3 |
| reads (`core_chunks.read_rows`) | 11.8 | 7.6 |
| `prepare` (pre-apply, weights, flags) | 12.6 | 1.6 |
| of which the pre-apply | 4.2 | 1.5 |
| the solve kernel (`_kernel`) | 1.2 | 1.1 |
| rows' weight sums from whole rows | (in `prepare`) | 0.07 |

The reader's share falls least: poldx's tiles (`[4, 256, 32]`) hold every
channel, so a one-channel read still reads every tile of the field's rows
(from the page cache); what it saves is the copy and decode of the other 255
channels and the per-run calls. Most of the gain is the prepare on one
channel instead of 256.

### 5.2 Run -02 and a change of how the arms take the lock (2026-11-12)

`D:\rang\outputs\sliced-read-20261111-02`, `tools/oracles/sliced/all.sh`.
Run with every arm in its own heavy-lock ticket, as section 4 says. By
2026-11-12 08:10 the shared arms O, C, P (U, D, T, M) and the timing arms
C-BT, C-T, P-BT, P-T, P-BD, P-D, W-BD, W-D and W-BM had finished. On the
coordinator's request, the remaining arms (W-M, the first verdict, H-U, H-D,
H-M, H-BT, H-T, the last verdict) then ran back to back inside one exclusive
hold (`heavy_lock.py run -- bash tools/oracles/sliced/batch.sh`), because
each separate exclusive ticket drained the host's shared jobs first and left
it at about 14 % CPU. The per-arm W-M ticket was cancelled before it started.
Each arm still records `heavy_lock.py status` at its start
(`logs/lock-status.txt`). Post hoc for H-U, H-D and H-M, which section 4 left
shared: they now run exclusive, which changes none of their outputs; the
timing protocol of the timed arms is unchanged.
