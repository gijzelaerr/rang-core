# MSv4 from the command line: `rang-core flag CONFIG STORE`, flag versions for a store

2026-11-25, branch `msv4-cli`, gijzelaerr/rang-core issue #5 step M7 (v0.5.0;
the write path is [msv4-flag-write.md](msv4-flag-write.md), M6, pass).
Status: **measured, partial** (section 9: C1 to C5 and C7 hold on every
measured case of both arms; C6 misses on the xradio arm only, on the group
key, because xradio 1.3.1 names fields `<name>_<FIELD_ID>`). Sections 1 to 6
were frozen in the commit that adds this note, before any code; amendments
A1 and A2 before any run. Later changes are dated and labelled post
hoc. No performance or science claim: the step checks that the command line
on a store gives the bits of `rang.msv4.flag` and of the MSv2 command, keeps
flag versions that round-trip exactly, and handles an interrupted write as
the MSv2 journal does.

## 1. The step

M6 left `rang.msv4.flag(store, config)`, a Python call that keeps no flag
versions, no journal and no run directory. On an MSv2, `rang-core flag
CONFIG MS` keeps all three (`core_pipeline`, `core_writeback`):

- a run directory `<ms>.rang-run` (`state.json`, `config.resolved.json`,
  `lock`, `flag/summary.json`, `receipts/`), so a finished stage is skipped,
  a changed one refused unless `--force`, a failed or killed one rerun;
- the CASA flag version `rang_original` before the first write ever, and
  `rang_<stage>_<UTC>` before each attempt's write, in `<ms>.flagversions/`;
- a journal `<ms>.flagversions/rang-writeback.json`: a session that may have
  written FLAG and did not close cleanly makes the next write refuse, unless
  the run directory that saved the version reruns (it restores first) or
  the user restores.

This step gives a store the same: `rang-core flag CONFIG STORE` and
`rang-core run CONFIG STORE` with `run.stages: [flag]`.

## 2. Probe before the freeze (2026-11-25)

Read, not run:

- `flagversions.root`, `versions`, `exists` and `core_writeback.read_journal`,
  `flags_unfinished`, `_write_journal` take only a path (`str(ms) +
  ".flagversions"`); `core_pipeline._version_name`, `_version_lost` use only
  those. A store's versions in the same layout reuse them unchanged.
- `core_pipeline.execute` calls `inspect_ms` and `preflight` (MSv2 only),
  then the stage function; `restore_before` and `stage_version` call
  `core_writeback.backup_flags` and `restore_flags` (MSv2 tables).
- `rang.msv4.flag` raises `ValueError` for its refusals (column, fields,
  learned mode, flagger), which `execute` would let through as a traceback
  after the state says `running`.
- xradio 1.3.1 and xarray-ms 0.5.14 stores (M6 run root) are zarr 3; the
  telescope is `antenna_xds` attribute `overall_telescope_name`; xradio holds
  one FLAG chunk per partition, xarray-ms 2 to 20.

## 3. The piece built here (frozen scope)

**A store** is a directory with `zarr.json` (zarr 3) or `.zgroup` (zarr 2)
and no `table.dat`. `rang-core flag | run` on one goes to the store path;
anything else is unchanged.

**Stages:** only `flag` (coordinator ruling M5, 2026-11-16). `rang-core
calibrate | apply | image | selfcal CONFIG STORE`, and `run` whose
`run.stages` hold another stage, are refused (exit 2) before anything is
written: no run directory state, no `.flagversions`. The refusals of
`rang.msv4.flag` (column outside `DATA`, `CORRECTED_DATA`, `MODEL_DATA`;
field ids or roles; a learned mode; a flagger other than tricolour; a
missing strategy; partitions the reader refuses) are made `Refused` before
the stage starts. `rang-core config check CONFIG STORE` applies the same
checks.

**Run directory:** `<store>.rang-run` by default, `--run-dir` as on an MSv2;
the same `core_pipeline.RunDir`, `state.json` schema, skip, refuse, force and
rerun rules, the same `config.resolved.json`, `flag/summary.json` and
receipt. State `telescope` from `overall_telescope_name`.

**Flag versions of a store** (new module `rang.msv4_flags`): a sibling
directory `<store>.flagversions/`, laid out as the MSv2 one:

- `FLAG_VERSION_LIST`, one `name : comment` line per version (the MSv2
  format, written by the same rule: listed last, with fsync);
- `flags.<name>/`: for every partition, a byte copy of the flag variable's
  directory (`<partition>/<flag variable>/`, its `zarr.json` and chunk
  files), plus `manifest.json` (partitions, variables, every file's size and
  sha256). Saved under `flags.<name>.rang-partial`, read back against the
  store by sha256, renamed, then listed; a killed save leaves no listed
  version (as `flagversions.save`);
- `rang-writeback.json`, the journal, with the MSv2 journal's keys and rules
  (`written: ["FLAG"]` recorded before the first put, `written_before_put:
  true`; states `open`, `closed`, `failed`, `restored`).

A sibling directory, not a variable in the store: a variable would change
the store's metadata and files (M6's O2, nothing else written) and its
schema-check record (O3); the sibling leaves both as they are.

**Restore** (`rang.msv4_flags.restore_flags(store, name)`): refused when a
partition or its flag variable's `zarr.json` differs from the version's
(another store). Each chunk file is written from the version through a
temporary file in `<store>.flagversions/` and `os.replace`; a chunk file
the store has and the version has not is removed; the variable's files are
then checked against the manifest. A killed restore is repeated by running
it again. It marks an interrupted journal `restored`, as
`core_writeback.restore_flags` does.

**The stage** (`core_pipeline`, store branch), in the MSv2 stage's order:
restore what this run directory's last attempt saved (saving
`rang_rerun_<UTC>` first), save `rang_original` if absent, record
`rang_flag_<UTC>` in the state, open the session (save that version, write
the journal), run `rang.msv4.flag` with a hook that marks `FLAG` written
before its first partition write, close the session. `rang.msv4.flag`'s
writes are unchanged (no hook: byte-identical to M6).

**Memory:** `data.memory_limit_gb` and `data.chunk_rows` act as on an MSv2
(`core_chunks.budget` with the store's rows and its largest partition
cell); `plan.rows("flag")` is the stage's `max_rows`, so a group larger
than it is flagged in blocks of baselines (M6's O4: same bytes).

**Summary** (`flag/summary.json`): the MSv2 stage's keys (`strategy`,
`strategy_sha256`, `steps`, `static_masks`, `write`, `column`,
`restored_before`, `groups`, `rows_flagged`, `flagged_before`,
`flagged_after`, `flag_sha256`, `flag_version`, `rang_original_saved_now`,
`chunking`) with the same definitions, plus `store`, `data_group` and
`partitions` (M6's per-partition record). A group has `field`, `scan`
(the store's names), `partition`, `rows`, the fractions and `core_seconds`;
not `field_id` or `ddid` (ids differ between formats). `flag_sha256` hashes
the store's FLAG, partition by partition, in the reader's row order (pads
dropped), so it equals the MSv2's only where the row orders agree.

**Not built:** calibrate, apply, image, selfcal on a store (M5); a command
for flag versions (as on an MSv2, `restore_flags` is Python; CASA's
flagmanager cannot read a store); the MCP server's write tools on a store;
`FLAG_ROW` (M4); object storage; parallel writes. No new `RANG_*` variable.

## 4. Oracle and cases (frozen)

**Run root** `D:\rang\outputs\msv4-cli-20261125` (new). M6's run root
`D:\rang\outputs\msv4-next-20261125` is read only: its `before`, `rang-p1`
and `oracle` stores, its flagged MSv2 copies and their run directories, its
configs `config-<column>-p1.yaml` and `strategy.yaml`. Every store or MS a
step writes is a copy in the new root.

**Oracles:**

- `rang.msv4.flag`: M6's `rang-p1` stores (code `78857afe`, merged).
- The MSv2 command converted: M6's `oracle` stores (each writer's conversion
  of the MS flagged by `rang-core flag`), read by xradio 1.3.1's
  `open_processing_set` (a Windows uv venv from public PyPI, M6's section 2
  versions) as M6's O1; schema issues by `check_datatree` (O3). No new
  conversion is needed, so no WSL writer venv.
- The MSv2 run directories of M6 (`msv2/<case>.ms.rang-run`, same configs).
- The MSv2 journal's behaviour: the same interruptions made on an MSv2 copy
  in this run, `rang-core flag` as shipped.

**Cases:** M6's (section 4 and amendment A1): c1 to c5, c6x, c8, c9, c11,
c11c (`column: CORRECTED_DATA`), c10 reported; c7 not measured (source
deleted). c9 has no MSv2 run (the MSv2 command refuses it) and no oracle:
its MSv2 measures are `not measured`. Arms `xradio` (deciding) and
`xms-auto` (reported).

**Command:** `python -m rang.core_cli flag <M6 config> <store copy>` in the
worktree's `.venv`, `--no-pin-threads` off, under the heavy lock.

**Measures** (bit-identical: every file of the store, path and bytes):

- **C1, CLI = API (deciding):** the store after `rang-core flag` equals M6's
  `rang-p1` of the case and arm.
- **C2, CLI = MSv2 converted (deciding):** M6's O1 between the CLI store and
  `oracle` (every data variable and coordinate of every node, `FLAG` too,
  bit-identical; attributes equal except the items that also differ between
  M6's `before` and `control`).
- **C3, schema (deciding):** `check_datatree` issues on the CLI store equal
  those on `before`.
- **C4, backup and restore (deciding):** after the CLI run,
  `<store>.flagversions` lists `rang_original` and `rang_flag_<UTC>`;
  restoring `rang_original` gives a store byte-identical to `before` (same
  file set); `rang-core flag ... --force` then gives `rang-p1` again (it
  restores `rang_flag_<UTC>` after saving `rang_rerun_<UTC>`); restoring
  that `rang_rerun_<UTC>` (the flagged store) gives `rang-p1` again.
- **C5, interrupted write (deciding)**, on c6x (4 partitions, so a kill
  between partition writes leaves a mixed store) and c5, both arms. A kill
  is `os._exit` from a harness wrapper (no cleanup, no exception):
  - K1, killed after the session opened and before any FLAG put: the next
    run (same or fresh run directory) is not refused and gives `rang-p1`
    (MSv2: E5-22, a session that wrote no flags is not refused).
  - K2, killed after the first partition's write (c6x): the store holds
    `rang-p1`'s FLAG files in partition 1 and `before`'s in the others
    (asserted). Then (a) a fresh `--run-dir` is refused, exit 2, its
    message names `rang.msv4_flags.restore_flags` and the version, and the
    store is unchanged; (b) the same run directory reruns, restores the
    version it saved and gives `rang-p1`.
  - K3, after a K2 kill, `restore_flags(store, <journal's version>)`: the
    journal says `restored`, the store equals `before`, and a fresh run
    directory then runs and gives `rang-p1`.
  - MSv2 side, the same K1 and K2 (after the first `FLAG` chunk write) and
    K3 on copies of c5 and c6x: the outcome classes (refused or run, exit
    code, final FLAG equal to the uninterrupted MSv2 run's) must be the
    store's.
- **C6, run directory products (deciding)**, against M6's MSv2 run
  directory of the case:
  - the same file set (`config.resolved.json`, `lock`, `state.json`,
    `flag/summary.json`, one `receipts/flag-*.rang-receipt.json`);
  - `config.resolved.json` byte-identical;
  - `state.json`: the same keys at the top and in the stage entry; equal
    `config_sha256`, `sections`, `status`, `attempts`, `previous`,
    `telescope`; the stage's brief summary has the MSv2 keys plus `store`
    and `data_group`;
  - `summary.json`: the MSv2 keys present, plus `store`, `data_group`,
    `partitions`; equal `strategy`, `strategy_sha256`, `steps`,
    `static_masks`, `write`, `column`, `restored_before`, `rows_flagged`,
    `flagged_before`, `flagged_after`, `rang_original_saved_now`; `groups`
    equal as a set keyed by (field name, scan as a string) in `rows`,
    `flagged_before`, `flagged_after`; `chunking` equal in every key except
    `blocks` (equal as a sorted list);
  - the flag versions: the same names (up to the UTC stamp) and comments in
    `FLAG_VERSION_LIST`; the journal has the MSv2 journal's keys, `state:
    closed`, `written: ["FLAG"]`.
  - Differ by design, not compared: paths (`ms`, `config_path` hold the
    store), times, `pid`, `seconds`, `core_seconds`, the version's UTC
    stamp, the receipt's hashes; `flag_sha256` is reported (equal or not).
- **C7, refusals (deciding):** on c5's store copy, `rang-core calibrate`,
  `apply`, `image`, `selfcal` and `run` with `run.stages: [flag,
  calibrate]` exit 2, the message names M5 or the store, and the store, its
  absent `.flagversions` and the absent run directory state stay so;
  `rang-core config check CONFIG STORE` exits 0 for the flag config and 2
  for `flag.fields: [0]`.
- Reported, no rule: wall seconds of each `rang-core flag` on a store and
  on the MSv2 copies, under the lock.

## 5. Decision rule (frozen)

- **Pass:** C1 to C7 hold on every measured case of the `xradio` arm. Then
  `rang-core flag CONFIG STORE` is offered for merge, the flag stage's MSv4
  route is complete, and the next steps (M5, a Rust reader, object storage)
  are proposed.
- **Partial:** C1, C2 and C4 hold; C3, C5, C6 or C7 does not. Offered with
  the miss named and a task opened.
- **Fail:** C1, C2 or C4 misses on any measured case. Not offered.
- `xms-auto` is read the same way and reported as met or not met.
- A bug found by a run may be fixed and the run repeated; runs are
  numbered from 01 and all recorded; the rule is read on the last run of
  the final code. A changed case, measure or tolerance is post hoc.

## 6. What a pass says, and what it does not

A pass says: the command line runs the flag stage on an MSv4 store with the
MSv2 command's run directory, flag versions and journal, writes exactly the
flags of `rang.msv4.flag` and of the MSv2 command converted, and gets back
any saved flags bit for bit. It says nothing about calibration or imaging
on MSv4 (M5), parallel writes, object storage or throughput, nor about
stores written by tools other than xradio 1.3.1 and xarray-ms 0.5.14.

## 7. Amendment A1: the exit code of a refused interrupted write (2026-11-25, post hoc, before any run)

Written while implementing, before any measurement run; nothing has been
compared. Section 4's K2(a) says a fresh run directory after an
interrupted write is "refused, exit 2". On an MSv2 the command does not do
that: `core_pipeline.stage_flag` calls `restore_before` after the stage is
marked `running`, its `Refused` becomes `StageFailed`, and the command
reports `rang-core flag: failed: flag: an earlier write-back ...`, exit 1,
the stage entry `failed`, nothing written. The store route is built to do
the same (the gate's other clause: the outcome classes are the MSv2
side's). K2(a) is read as: the exit code equals the MSv2 side's (1), the
message names `rang.msv4_flags.restore_flags` and the version, the store is
unchanged. Nothing else in sections 3 to 6 changes.

## 8. Amendment A2: C4's last step (2026-11-25, post hoc, before any run)

Found by the unit test, before any measurement run. C4 says restoring
`rang_rerun_<UTC>` "(the flagged store) gives `rang-p1`". It does not, by
the MSv2 rule section 3 copies: `rang_rerun_<UTC>` holds the flags a forced
rerun replaced, and in C4's order those are `rang_original`'s (restored
just before the rerun). C4's last step is replaced by two:
restoring `rang_rerun_<UTC>` gives `before`; and a version saved of the
flagged store after the forced rerun (`rang.msv4_flags.save(store,
"m7_flagged")`), restored after `rang_original`, gives `rang-p1` (a round
trip of a flagged state). Nothing else changes.

## 9. Measured result (2026-11-25)

**Outcome under the frozen rule: partial** on the `xradio` arm (C6 misses,
everything else holds); the `xms-auto` arm is **met** on every measure.
Receipt [results/msv4-cli/receipt-01.json](results/msv4-cli/receipt-01.json),
harness [msv4_cli.py](results/msv4-cli/msv4_cli.py), step logs beside it
(`cli.json`, `kill.json`, `refuse.json`, `products.json`, `xcheck-02.json`),
first-run run directories in [results/msv4-cli/products/](results/msv4-cli/products/).
Run root `D:\rang\outputs\msv4-cli-20261125` (1.7 GB), host glacier
(Windows), code `33d8b684`, the main checkout's `.venv` with `PYTHONPATH` at
the worktree's `python/` (extension copied from the main checkout; `core/`
and `src/` are unchanged on the branch), heavy lock 2 slots 4 GB,
`RAYON_NUM_THREADS=2`. M6's run root was only read (nothing in it newer than 08:50, before run 01). One run (01) of every step; xcheck run 01 stopped at
start-up (the rebuilt xradio venv lacked dask, which `open_processing_set`
needs; dask 2026.11.0 added), run 02 is the receipt's.

| measure | xradio | xms-auto |
| --- | --- | --- |
| C1 CLI = `rang.msv4.flag` (every file) | 11/11 match | 11/11 match |
| C2 CLI = MSv2 command converted (O1) | 10/10 match, c9 not measured | 10/10 match, c9 not measured |
| C3 schema issues unchanged | 11/11 match | 11/11 match |
| C4 versions round trip | 11/11 match | 11/11 match |
| C5 interrupted writes, c5 and c6x | match | match |
| C6 run directory products | **10/10 mismatch on `groups`** | 10/10 match |
| C7 refusals (c5 store) | match | |

(11 = c1 to c5, c6x, c8, c9, c10, c11, c11c; c10 is reported, c7 not
measured.)

- **C1:** every store `rang-core flag` wrote is byte-identical, file for
  file, to M6's `rang-p1`, c9 (two partitions, 4 and 8 channels) included.
- **C2, C3:** as M6: only the writers' timestamps differ from `oracle`
  (excluded: they differ between `before` and `control`); schema issues as
  on `before`.
- **C4:** `rang_original` restored gives `before` byte for byte; `--force`
  gives `rang-p1` again (restoring `rang_flag_<UTC>` after saving
  `rang_rerun_<UTC>`); `rang_rerun_<UTC>` restored gives `before`; a saved
  flagged version restored after `rang_original` gives `rang-p1` (A2).
- **C5:** K1 (kill before any put): journal `written: []`, store unchanged;
  the next run, same or fresh run directory, exits 0 with `rang-p1`; MSv2
  the same. K2 (kill after the first partition's write): c6x's store holds
  `rang-p1`'s FLAG in partition 0 and `before`'s in partitions 1 to 3, both
  writers; a fresh run directory exits 1 (A1), names
  `rang.msv4_flags.restore_flags` and the version, store unchanged; the same
  run directory exits 0 with `rang-p1`. The MSv2 copies of c5 and c6x give
  the same exit codes and end on the MSv2 run's FLAG (c6x's MSv2 FLAG is
  mixed after the kill too). K3: the restore gives `before`, journal
  `restored`; a fresh run directory then exits 0 with `rang-p1`; MSv2 the
  same.
- **C6:** with xarray-ms's stores the run directory matches the MSv2 run's
  in every compared item. With xradio's, every item matches except
  `groups`: xradio 1.3.1 writes `field_name` as `<name>_<FIELD_ID>`
  (`J1939-6342_0`), and the store route reports the store's names (section
  3), so the frozen key (field name, scan) differs. Post hoc, no rule: with
  the `_<digits>` suffix stripped, the groups are equal in rows and both
  fractions on all 10 cases (23 groups on c6x), and the suffix equals the
  MSv2 group's `field_id` in every group. `flag_sha256` differs from the
  MSv2's on every case (reported: the reader's row order is not the MS's).
- **C7:** `calibrate`, `apply`, `image`, `selfcal` and `run` with
  `[flag, calibrate]` exit 2 naming the store and M5; `flag.fields: ['0']`
  exits 2; `config check` exits 0, and 2 with `['0']`; the store, its absent
  `.flagversions` and absent run-directory state unchanged. Reported:
  `rang-core watch --once --json` on a store's run directory exits 0.
- **Cost** (reported, no claim): `rang-core flag` on a store 3.2-11.1 s wall
  per command (stage 0.6-7.4 s; c6x 7.4 s against its MSv2 run's 6.7 s; c8
  1.1 s against the MSv2 stage's 4.7 s, the gaps); the C4 sequence 3.4-12.6 s
  per case.

**For users:** on an xradio store `flag.fields` takes xradio's names
(`J1939-6342_0`), not the MSv2's; xarray-ms keeps the MSv2 names. The
how-to says so.

**Task (proposed, for the coordinator):** decide the group's `field` on a
store: keep the store's name (now), or report the MSv2 name and id where
the writer encodes them; and whether `flag.fields` should accept MSv2 names
on an xradio store. Either is a post hoc change with its own small gate.

## 10. Amendment A3: MSv2 field names on xradio stores (2026-11-25, **post hoc**, after run 01)

Written after section 9's run 01 and before any code of the fix (branch
`msv4-fields`), on the coordinator's decision of 2026-11-25: a store's
group reports the MSv2 field name and field id, with the `_<id>` suffix
stripped only when it equals the field's id; `flag.fields` takes the MSv2
name on an xradio store, the stored name staying an alias.

**Probe (read, not run).** xradio 1.3.1
(`measurement_set/_utils/_msv2/create_field_and_source_xds.py`) writes every
field name as `NAME + "_" + FIELD_ID` and then drops `field_id` from the
field-and-source dataset; for single-dish data it keeps a `FIELD_ID` data
variable over `field_name`. An interferometric xradio store therefore holds
the id only in the name's suffix: no attribute, coordinate or variable of
the partitions, their `field_and_source_base_xds` or the root carries it
(c6x's store checked). xarray-ms 0.5.14 keeps the MSv2 name and no id.
**Deviation:** "the id from the store's metadata" cannot be met on an
interferometric xradio store; the rule below takes the id from xradio's
documented naming, gated by the writer, anchored, and checked store-wide,
and C6 checks it against the MSv2 run's `field_id`.

**Rule** (`rang.msv4`, one map per store, from stored name to MSv2 name and
id):

1. Where a partition's field-and-source dataset has a `FIELD_ID` variable
   over `field_name`, that is the id; the suffix is stripped only where the
   stored name ends in exactly `_<that id>`.
2. Otherwise, only when every partition's `creator.software_name` is
   `xradio`: every field name of the store (the per-time `field_name` of
   every partition and the field-and-source `field_name`) must match
   `^(.+)_(0|[1-9][0-9]*)$`, and each id must have one stem in the whole
   store; then the stem is the MSv2 name and the digits the id. If any name
   or id fails, no name is changed (all or none) and the ids are null.
3. Any other writer (xarray-ms): the name as stored, id null.

**Group record:** `field` is the MSv2 name, `field_id` the id (null when
unknown), `store_field` the stored name; `scan`, `partition`, `rows`, the
fractions and `core_seconds` as before. Grouping, row order, the task plan
and the written bytes stay keyed on stored names (C1 cannot move).

**`flag.fields`:** a token selects every field whose MSv2 name or stored
name equals it (two fields with one MSv2 name are both selected, as
`core_pipeline.resolve_fields` does on an MSv2). A token that is one
field's MSv2 name and another field's stored name is refused (exit 2, both
named). Ids and roles stay refused on a store (C7 unchanged).

**Measurement (re-run of C1 and C6, rule restated).** New run root
`D:\rang\outputs\msv4-fields-20261125`; M6's root read only, every store a
copy in the new root; runs numbered from 01. Cases as section 4.

- **C1 (deciding):** every store `rang-core flag` writes is byte-identical,
  file for file, to M6's `rang-p1` of the case and arm.
- **C6 (deciding):** the run-directory products equal the MSv2 run's, as
  section 4 defines them, on every case with an MSv2 run (c9 has none), for
  **both** backends (`xradio` and `xms-auto` deciding); the comparator is
  M7's `products` step with its frozen keys, unchanged. Declared addition:
  on `xradio` every group's `field_id` equals the MSv2 group's of the same
  (field, scan); on `xms-auto` it is null (asserted).
- **Pass:** C1 and C6 hold on every measured case of both arms. **Fail**
  otherwise; then the fix is not offered.

**Caveat:** only c6x has field ids other than 0 (1, 2, 3); on every other
case C6 cannot tell an id read from the suffix from a stripped `_0`. Unit
tests cover nonzero ids, a stem that is itself `<x>_<digits>`, the
collision refusal and the xarray-ms pass-through.

## For the coordinator

Branch `msv4-cli`: note `e296b1e3` (frozen before code), A1 `26f69040`, A2 `c0153729`
(before any run), code `33d8b684`, records after. **Partial** under the
frozen rule. The command on a store gives `rang.msv4.flag`'s bytes and the
MSv2 command's flags converted (both writers, every measured case); flag
versions round-trip byte for byte; interrupted writes are refused and
recovered as on an MSv2 (same exit codes); other stages are refused. The
one miss is C6's group key on xradio stores (field names `<name>_<id>`).
New module `rang.msv4_flags`; `core_pipeline.inspect_store`,
`stage_flag_store`; `rang.msv4.flag` split into `prepare_flag` and
`run_flag` (bytes unchanged, C1). No new `RANG_*` variable. The xradio
reader venv in `~/Build/tmp/20261125-msv4-cli` is removed at hand-back; the
run root on D: is kept until merge (1.7 GB).
`rang-core run` with `run.stages: [flag]` on a store is covered by a unit
test on m05, not by the measurement. No GitHub issue was opened for the
task above.
