# MSv4 round trip: the flag stage on a processing set, FLAG written back

2026-11-25, branch `msv4-next`, gijzelaerr/rang-core issue #5 (v0.5.0; the
read path is [msv4-interop.md](msv4-interop.md), its M1 to M3 and M2 done).
Status: **proposed, frozen**. Sections 1 to 6 are frozen in the commit that
adds this note, before any code that writes an MSv4 store. Later changes are
dated and labelled post hoc. The note makes no performance or science claim:
it checks that a write path returns the same bits as the MSv2 path and as
the writers' own conversion.

## 1. What remains of #5, and the step taken here

The v0.5.0 done-when for #5 is "data round-trips through MSv4 against xradio
and xarray-ms"; the issue's gate adds "identical calibration and imaging
results from MSv2 and MSv4 input" and throughput from object storage. Done
so far: ra-ng reads an MSv4 store bit for bit (msv4-interop.md, 9 + 5 cases,
both writers), and the Tricolour kernel fed from the reader gives the
stage's flags on one case (M2, through a harness adapter). Open:

1. **Writing a product back into an MSv4 store** (nothing written yet).
2. **A stage that takes a store through #3's chunk tasks** (`ChunkSpec`,
   `plan_*`, `run`, the executor), not a harness adapter.
3. Calibration and imaging on MSv4 input: blocked by the coordinator's M5
   ruling (2026-11-16): no weighted stage takes MSv4 input until the
   base-weight convention is settled.
4. `FLAG_ROW` (M4: documented, writers drop it), a Rust `zarrs` reader,
   object storage, throughput, per-chunk parallel writes.

**This step does 1 and 2 for the one stage M5 allows, the flag stage:**
`rang.msv4.flag(store, config)` plans the flag stage's chunk tasks over a
processing set with `core_tasks.plan_flag`, runs them through
`core_tasks.Executor` (inline, a local process pool or a spool), and writes
the flags into the store's `FLAG`. The round trip is MSv2 → (xradio or
xarray-ms) → MSv4 → ra-ng flag → MSv4, checked against MSv2 → ra-ng flag →
(the same writer) → MSv4.

## 2. Probe before the freeze (2026-11-25)

Known before this note; no ra-ng code has written a store:

- xradio 1.3.1 installs natively on Windows from public PyPI without the
  `casacore` extra (scratch venv `~/Build/tmp/20261125-msv4-next/xradio-venv`,
  Python 3.12, with zarr 3.4.2, numcodecs 0.17.1, s3fs, xarray 2026.9.0); its
  `open_processing_set` opens both stores of c5 from
  `D:\rang\outputs\msv4-20261116\ps` (the converter still needs arcae, so WSL).
- `xradio.schema.check.check_datatree` on those stores: the xradio store of
  c5 has one issue (`pointing_xds` coordinate `time_pointing`, attribute
  `type` is `time`, expected `time_pointing`); the xarray-ms (`auto_corrs`)
  store has none. So the gate is "unchanged", not "none".
- Read, not run: `core_tasks.run(spec, source=None)` opens `core_ms` on
  `spec.ms`; `_run_flag` reads its rows through `core_chunks.read_rows`,
  which calls a source's `getcol_rows(name, rows, chans=...)`; the pipeline's
  flag stage (`core_pipeline.stage_flag`) groups rows by (`FIELD_ID`,
  `DATA_DESC_ID`, `SCAN_NUMBER`) and writes each partial as it arrives.
- xradio's stores hold one zarr chunk per variable for these cases (M1 probe),
  so a write rewrites the chunk that a worker may be reading.

## 3. The piece built here (frozen scope)

- **Entry point:** `rang.msv4.flag(store, config, config_path=None,
  max_rows=None)`, Python only. `config` is a ra-ng configuration (as
  `rang-core flag` reads it, resolved by `core_config`). It returns a summary
  (groups, fractions before and after, executor record, seconds). A CLI
  route (`rang-core flag CONFIG STORE`) is not built here: it needs the run
  directory, the journal and flag versions for a store, and is the next step.
- **Keys read:** `flag.strategy`, `flag.static_masks`, `flag.write`,
  `flag.column`, `flag.fields`, `data.scans`, `data.executor`,
  `data.processes`, `data.threads`, `data.spool`. `flag.column` maps to a
  data group: `DATA` → `base`, `CORRECTED_DATA` → `corrected`, `MODEL_DATA`
  → `model`; any other is refused. `flag.fields` is `all` or field names as
  the store's `field_name` holds them; roles and numeric ids are refused
  (ids differ between formats). `data.scans` is matched against `scan_name`
  as strings.
- **Groups:** per partition (one MSv2 `DATA_DESC_ID` in both writers), per
  (`field_name`, `scan_name`) of each time: the MSv2 stage's (field, ddid,
  scan) groups. Rows are the reader's (time-major, `baseline_id` order, pads
  dropped). `max_rows` (default: no split) cuts a group into blocks of
  baselines as the MSv2 stage does.
- **Chunk tasks:** the specs come from `core_tasks.plan_flag` and run with
  `core_tasks._run_flag`, unchanged. A spec of a store carries its partition
  and data group in `params`, and `core_tasks.run` opens an MSv4 row source
  for it when it has no source (worker processes and spool workers). That is
  the one change to `core_tasks`. The row source reads `DATA`, `FLAG`
  (`getcol_rows`) of the group's variables; a uint8 `FLAG` is read under the
  M1 rule.
- **Metadata from the store:** antenna positions (`antenna_xds`
  `ANTENNA_POSITION` in `antenna_name` order), `frequency` and its
  `channel_width`, correlation codes from the `polarization` names (`XX` 9 to
  `YY` 12, `RR` 5 to `LL` 8). A store without them is refused.
- **Write:** the single writer is the parent. **No store write happens while
  tasks are in flight:** the partials are kept (one byte per cell of the
  selected rows) until the map ends, then written into the group's `FLAG`
  variable with zarr (opened `r+`), one time range per write. The stored
  dtype is kept (bool, or uint8 0/1 for xarray-ms). Pad cells and cells
  outside the selection keep their stored values. Nothing else in the store
  is written: no attribute, no metadata, no new variable.
- **Not built:** flag backups or versions for a store (flag a copy; the
  docstring says so), the journal, `FLAG_ROW` (lost at conversion, M4),
  weighted stages (M5), object storage, parallel per-chunk writes, a Rust
  reader or writer.

## 4. Oracle and cases (frozen)

**Writers (WSL, uv venv `~/Build/tmp/20261125-msv4-oracle/venv`, Python 3.12,
public PyPI, msv4-interop.md's versions):** xradio 1.3.1 (`xradio[casacore]`,
arcae 0.5.9, zarr 3.4.2, numcodecs 0.17.1, toolviper 0.1.13), xarray-ms
0.5.14 (xarray 2026.9.0). Arms `xradio` (`convert_msv2_to_processing_set`,
defaults) and `xms-auto` (`open_datatree(engine="xarray-ms:msv2",
auto_corrs=True)`, `to_zarr`), as msv4-interop.md sections 4 and 10.

**Reader of the round trip (Windows):** xradio 1.3.1's
`open_processing_set` in the scratch venv of section 2 for both arms' stores;
`rang.msv4` beside it.

**MSv2 side:** `rang-core flag CONFIG MS` as shipped, on a fresh copy of each
case MS, in the worktree's `.venv`. CONFIG: `flag.strategy` CARACal's
`mk_rfi_flagging_calibrator_fields_firstpass.yaml` (sha256
`ce9ac66aba75c62e778eabbc951e8f9760447f7824f8fd37b26b91974ec71774`, as M2),
every other key at its default (static masks `tricolour`, `write: replace`,
`column: DATA`, `fields: [all]`); case c11 also with `column:
CORRECTED_DATA`. The same CONFIG goes to `rang.msv4.flag`.

**Stores, per case and arm (run root `D:\rang\outputs\msv4-next-20261125`;
`msv4-20261116` is read only):**

- `before`: the writer's conversion of the unflagged MS;
- `control`: a second conversion of the unflagged MS (writer determinism);
- `oracle`: the writer's conversion of the MS copy flagged by `rang-core
  flag`;
- `rang-p1`, `rang-p2`: copies of `before` flagged by `rang.msv4.flag` with
  `data.processes` 1 and 2 (local executor); for c5 also `rang-blocks`,
  `max_rows` 40 (c5's group of 140 rows in blocks of baselines of at most 40 rows), processes
  1.

**Cases:** c1 to c9 of msv4-interop.md section 4 (fixture scans 1, 4, 5, 8,
9; c6, several fields and scans; c7, heavy flags; c8, pads; c9, two
partitions), and c11 of section 11 (`CORRECTED_DATA`) with `column:
CORRECTED_DATA` as case c11c. c10 (`FLAG_ROW`) is reported, not deciding:
both writers drop `FLAG_ROW` (M3), so it is a writer outcome either way. A
case whose MSv2 side `rang-core flag` refuses or fails is booked `not
measured` with the message.

**Measures, per case and arm (bit-identical: dtype, shape, bytes; NaN
payloads count):**

- **O1, round trip (deciding):** every data variable and coordinate of every
  node of `rang-p1`, read by xradio's `open_processing_set`, equals
  `oracle`'s, `FLAG` included; attributes equal. A variable, coordinate or
  attribute that also differs between `before` and `control` is writer
  nondeterminism: it is excluded from O1 by name and listed.
- **O2, nothing else written:** every file of `rang-p1` is byte-identical to
  `before`'s, except the chunk files of the flag variable (`<partition>/<flag
  variable>/c/...`).
- **O3, schema:** `check_datatree`'s issues on `rang-p1` equal those on
  `before`, as strings.
- **O4, executor:** every file of `rang-p2` (and c5's `rang-blocks`) is
  byte-identical to `rang-p1`'s.
- **O5, not vacuous:** the MSv2 side's `FLAG` after differs from before
  (cells set, counted). Required on c1 to c5 for a pass.
- Reported, no rule: `FLAG` of `rang-p1` read by `rang.msv4`, mapped by key
  to the flagged MS copy (`rang.core_ms`); pad cells' `FLAG` before and
  after; wall seconds of `rang-core flag` on the MSv2 and of
  `rang.msv4.flag`, under the heavy lock at the booked threads, no claim.

## 5. Decision rule (frozen)

The `xradio` arm decides; `xms-auto` is reported beside it with the same
measures.

- **Pass:** O1 to O4 hold on every deciding case of the `xradio` arm that is
  not `not measured`, and O5 on c1 to c5. Then `rang.msv4.flag` is offered
  for merge as ra-ng's first MSv4 write, the "round-trips through MSv4"
  done-when is met for the flag stage and xradio, and the CLI route is
  proposed next.
- **Partial:** O1 holds everywhere, and O2, O3 or O4 does not (something
  besides `FLAG` written, a schema issue added, or the executor changes the
  bytes but not the values). Offered with the miss named and a task opened.
- **Fail:** O1 misses on any deciding case, or `rang.msv4.flag` refuses a
  case the scope of section 3 says it flags, or O5 misses on c1 to c5. Not
  offered; the note records why.
- **`xms-auto`:** the same reading, reported as met or not met for
  xarray-ms; where it differs from `xradio` and the MSv2 side matches one of
  them, a writer difference (msv4-interop.md section 6).
- A bug found by a run may be fixed and the run repeated; every run is
  numbered (from 01) and recorded; the rule is applied to the last run of
  the final code. A changed case list, measure or tolerance is post hoc.

## 6. What a pass says, and what it does not

A pass says: ra-ng's flag stage, run through the chunk tasks on an MSv4
store, writes into the store exactly the flags that the same writer stores
when it converts the MS ra-ng flagged as MSv2, and touches nothing else. It
does not say that calibration or imaging run on MSv4 (M5), that writes are
parallel or scale, that object storage works, or anything about throughput.

## 7. Measured result

Not run yet.
