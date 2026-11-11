# E5 review: write-back safety of a user's MS

Checkout `<worktree>`. The review started at 3eab67c. While it ran, another session committed these on top:

- 2bac745: msvcrt run-directory lock.
- 25e1809: a stale stage no longer restores.
- 47e5520 and 1c8a617: config errors.

Line numbers below are at **1c8a617**; the tree was clean when checked. In scope, only core_pipeline.py, core_config.py and tests changed. This is a read-only review: no repository file was edited.

Demos are in `<scratch>\e5-wb\` (`demo.py` to `demo9.py`, `child.py`, `cfg.py`, `readd.py`). They run on Windows with the Python 3.14 venv. The MSs come from `examples/w1_writeback.py:make_ms` (150 rows, 16 channels, 4 correlations, tiled FLAG) and `tests/test_w2_commands.py:make_ms` (240 rows, 2 fields).

Labels: **[run]** means demonstrated here; **[code]** means traced from the code only.

**Counts: 3 release-blocking, 6 should-fix, 5 later.**

## Answers to the review questions, in brief

- **Original FLAG backed up before the first write, and never re-taken (including `--force`)?** Yes [code + test]. See "Verified OK".
- **Atomic per chunk or column?**
  - No. Each `putcol` is followed by a flush, but a chunk is not atomic, and the data column and FLAG are separate puts.
  - [run] demo E: an exception mid-session left 4635 of 9600 cells flagged.
  - [run] demo6: a failed `addcols` left orphan `table.f3*` files. They are harmless: the MS opens, and re-adding the column works.
  - FLAG recovers through the journal and backup. Other columns are rewritten by the rerun (apply) or not at all (WB-05).
- **Consistent after interruption?** The MS opens after every kill and exception tried [run]: 4 hard exits on Windows, exceptions, KeyboardInterrupt, sharing violations.
- **Restore path?** `rang.core_writeback.restore_flags` works and is tested (test_w1). It has no CLI verb or doc (WB-08). An interrupted restore leaves no record (WB-14).
- **Locks released?** [code] `close` runs `table.close()` in a `try/finally`, and `__exit__` runs for BaseException too. demo E's instant re-open proves nothing on Windows, because the lock is a no-op there (WB-03).
- **Read-only MS refused clearly?** No (WB-07).
- **DATA ever written?** Yes, by configuration (WB-01).
- **Existing CORRECTED_DATA or MODEL_DATA of another shape?** Refused before writing [run] demo F; gemclean refuses too [code] predict.rs:393. The journal side effect is WB-04.
- **Resume detects a partly written stage?**
  - Yes for FLAG: the journal `open`/`failed` state, plus `state.json` `running`/`failed`, triggers `restore_before`.
  - No for a partly initialised column after a restore (WB-05).
  - Misdirected for model-only sessions (WB-04).
- **CASA flagmanager layout?** Compatible; W1 measured it.
- **Windows specifics:**
  - Hard exits recover [run].
  - A sharing violation fails cleanly, but with a raw message (WB-09).
  - `_fsync_dir` is a no-op on Windows (WB-11).
  - The table lock is a no-op (WB-03).

## Verified OK (no finding)

- **The backup is taken once and never overwritten** [code + test]:
  - `WriteBack.begin` saves `flag_backup` only when it is not listed (core_writeback.py:259).
  - `flagversions.save` refuses a listed version (flagversions.py:132) and an unlisted one that exists (:155).
  - The pipeline's `backup_flags(ORIGINAL)` saves only when missing.
  - `--force` restores the stage's own `rang_<stage>_<time>` and saves a new, uniquely named one (`_version_name`, core_pipeline.py:793); `rang_original` is never re-taken.
  - Covered by `test_existing_columns_are_kept_and_backup_not_retaken`.
- **Hard kill on Windows** [run] `demo5.py`:
  - The W1 child with `os._exit(9)` in place of SIGKILL, at four points: after the 6th flush, before the 7th flush, in the 2nd backup chunk, and in the 3rd CORRECTED_DATA init chunk.
  - Each time the MS opens, and `restore_flags` gives back FLAG and FLAG_ROW with the pristine SHA-256.
  - A kill in the backup leaves only `flags.rang_original.rang-partial` and no journal; the rerun takes the backup again.
- **All Python writes to a user MS go through `WriteBack` or `flagversions`** [code]:
  - A recursive grep of `python/rang` for `readonly=False`, `.putcol(`, `.putcell(` and `create_table(` hits only core_ms_write, core_writeback and flagversions.
  - `flag_extend.extend_ms` writes FLAG through `WriteBack` (flag_extend.py:135, :239).
  - In Rust, the only writer of a user MS is gemclean's predict (WB-01c). `gemclean/input.rs:write_ms` only creates new MSs.
- **Stale rerun after a forced flag stage**: fixed in 25e1809, with a test. [run] demo4 against 3eab67c/2bac745 showed the bug, and demo8 shows the fix holds. The residual problem is WB-02.

---

## Release-blocking

### WB-01: DATA can be overwritten, while the docs say it never is

- **Class:** release-blocking (irrecoverable loss of the user's data; false safety claim).
- **Where:**
  - core_writeback.py:386-406 (`write` accepts any existing column) and :462-465 (only *adding* DATA is refused).
  - core_config.py:290 (`apply.column`), :433-442 (`selfcal.input_column`, `model_column`); only `selfcal.output_column` is checked against DATA (:909).
  - core_pipeline.py:2141-2149 (`_copy_column`).
  - core/src/gemclean/predict.rs:384-399 with cli.rs:484 (`-model-column`).
- **What is wrong:**
  - (a) The configuration accepts `apply.column: DATA`, `selfcal.input_column: DATA` and `selfcal.model_column: DATA`.
    - apply then writes the corrected visibilities into DATA [code]: `ensure_column("DATA")` returns False, then `w.write("DATA", ...)`.
    - selfcal copies CORRECTED_DATA over DATA [run], or predicts the model into DATA [code].
  - (b) `WriteBack.write("DATA")` succeeds [run].
  - (c) `gemclean -model-column DATA` predicts into DATA [code]. The Rust `ensure_column` returns `Ok(false)` for any existing complex array column, then `put_column` runs.
  - Only FLAG is backed up. research/w1-writeback.md:233-234 says no other column is backed up "because the input DATA is never written". That claim is false.
- **Evidence:**
  - [run] `cfg.py`, at 1c8a617, on tests/data/w2/e2b.yaml with image.pol I and selfcal.refant 0: `('apply','column') =DATA accepted`, `('selfcal','input_column') =DATA accepted`, `('selfcal','model_column') =DATA accepted`.
  - [run] `demo.py` C: `w.write("DATA", 0, zeros)` gives `DATA rows 0-3 now zero: True`.
  - [run] `demo7.py`: `core_pipeline._copy_column(w, "CORRECTED_DATA", "DATA")` gives `DATA hash unchanged: False | DATA now all 7+0j: True`.
  - `calibrate.model.column: DATA` is also accepted, but it is only read. That is not a finding.
- **Proposed fix:**
  - (1) In `WriteBack.write` and `WriteBack.ensure_column`, raise `ValueError("DATA is never written")` when `name == "DATA"`.
  - (2) In core_config, extend the :909 check to `apply.column`, `selfcal.input_column` and `selfcal.model_column`.
  - (3) In gemclean's argument checks, refuse `-model-column DATA`.
  - (4) A test per key, plus one for `WriteBack.write("DATA")`.
- **Small and unambiguous:** yes (about 20 lines Python, 5 Rust, and tests).

### WB-03: the docs claim a table lock that does not exist on Windows or macOS

- **Class:** release-blocking (false safety claim in user docs).
- **Where:**
  - docs/concepts/ingest.md:13-14 ("writes into existing tables ... holding casacore's lock").
  - core_writeback.py:16 ("`WriteBack` holds the core writer's lock on the MS for the whole session").
  - The implementation: core/src/ms_write.rs:104-113 (`#[cfg(not(target_os = "linux"))]`, where `write_lock` always returns true).
- **What is wrong:**
  - On Windows (the primary platform since 2026-11-09) and macOS, nothing stops a second writer. 2bac745 locks the run directory, so two `rang-core` commands with the same run directory are refused.
  - That does not cover:
    - a different `--run-dir`;
    - Python API sessions (`applycal`, `set_model`, `extend_ms`);
    - `gemclean -predict` beside rang.
  - Two writers would also share one journal file and one `.rang-partial` path. `flagversions.save` runs `rmtree(partial)` at :157 [code].
  - research/w1-writeback.md:247 states the limit. The user-facing page does not.
- **Evidence:** [run] `demo2.py`: a child process holds `core_ms_write.open_table(ms, readonly=False)`. A `WriteBack(ms, lock_attempts=2)` in the parent then opens, writes and closes with `no error`, and the journal says `closed`.
- **Proposed fix:**
  - Now: correct both sentences ("on Linux only; on Windows and macOS nothing stops a second writer; rang-core refuses a second command on the same run directory").
  - Later: a real lock off Linux.
- **Small and unambiguous:** the doc fix, yes (2 sentences). The lock is not small.

### WB-06: a rerun's restore discards flags made outside rang, without a backup

- **Class:** release-blocking (irrecoverable loss of the user's own flags; no flag version holds them).
- **Where:** core_pipeline.py:805-822 (`restore_before` writes `prior` straight over FLAG; it is called first by flag, both calibrate variants, apply and selfcal).
- **What is wrong:**
  - The user flags by hand (CASA `flagdata`, or their own script) after a rang stage ran, then reruns that stage: `--force`, or a plain resume after it failed.
  - `restore_before` puts the stage's pre-version back, and the user's flags are gone, with no copy anywhere.
  - `--force` warns that it "first restores the flags saved before it". A resume of a failed stage does not.
- **Evidence:** [run] `demo8.py` B:
  - Steps: `rang-core flag`, then rows 100-139 flagged through the core writer, then `rang-core flag --force`.
  - Result: `restored_before: rang_flag_...`, `hand rows 100-139 still flagged: False`, `versions holding the hand flags: []`.
- **Proposed fix:**
  - In `restore_before`, before `restore_flags(ms, prior)`, compare the current FLAG and FLAG_ROW with `prior` chunk by chunk.
  - If they differ, save the current ones as `rang_before_restore_<UTC time>` (`backup_flags` with `_version_name`). Record the name in the summary and log it.
  - The cost is one FLAG-size copy (1 byte per cell) only when something changed.
- **Small and unambiguous:** yes (about 10 lines and a test).

---

## Should-fix

### WB-02: residual problem of 25e1809, where a rerun after an upstream stage that wrote no flags keeps the stage's old flags

- **Class:** should-fix (the 25e1809 fix is too broad; rang's own flags only).
- **Where:** core_pipeline.py:2493-2504 (`execute` pops `flag_version` from every later stage when any stage finishes).
- **What is wrong:**
  - The pop is right when the finished stage restored flags (flag, chain calibrate).
  - It is wrong when the finished stage wrote no flags (complex calibrate). The later stage's previous flags are still in the MS, and its rerun adds to them instead of starting from its input.
  - Example: apply's calflag flags from the old solutions survive a calibrate rerun.
- **Evidence:** [run] `demo8.py` A:
  - Steps: flag, calibrate (complex), apply, with rows 0-29 set as a stand-in for apply's own flags (apply ORs; this fixture adds none). Then `calibrate --force`, then apply.
  - Result: `apply flag_version after calibrate: None`, `apply restored_before: None`, `apply1's rows 0-29 still flagged: True | were in apply's input: False`.
- **Proposed fix:** pop the later stages' `flag_version` only when this attempt's `restore_before` returned a version. The stages already put it in `summary["restored_before"]`, so check `summary.get("restored_before")` at :2493. Extend the 25e1809 test with the complex-calibrate case.
- **Small and unambiguous:** yes (about 3 lines and a test).

### WB-04: the journal turns dirty when FLAG was never written, and its restore advice wipes every rang flag

- **Class:** should-fix (rang's flags are lost if the advice is followed; the original is safe).
- **Where:**
  - core_writeback.py:239-257, :246-252 (refusal text), :285-302 (journal written *before* the table is opened), :375-384 (`written` is marked only after the flush).
  - core_model.py:188 (the default `flag_backup="rang_original"`).
  - core_pipeline.py:812-818 (`restore_before` Refused text).
  - core_cli.py:1314-1318 (`InterruptedWriteBack` is not caught).
- **What is wrong:** one cause, three symptoms. The journal goes `open` or `failed` whenever a session ends early, even when FLAG and FLAG_ROW were not touched. The refusal then says to `restore_flags(ms, <journal flag_backup>)` "to go back to the flags saved before it".
  1. *Model writes* [run at WriteBack level, pipeline route code].
     - `core_model.write_model_data` (image `write_model`, selfcal `_selfcal_model`) uses `rang_original`, which already exists, so nothing new is saved.
     - After a Ctrl-C or exception in a MODEL_DATA predict, the journal names `rang_original`.
     - `rang-core image` then ends in an uncaught `InterruptedWriteBack` traceback [code].
     - `rang-core selfcal` is refused by `restore_before` ("was not made by this run directory", which is false) [code].
     - Both say to restore `rang_original`. That reverts the flag, calibrate and apply flags to the pre-rang state, while state.json still marks those stages done.
  2. *Failure in `begin` before any write*: a read-only MS, or on Linux a lock busy for 10 × 1 s. The journal stays `open` for good [run, read-only case].
  3. *Refusals inside a session* (`UnsupportedLayout` from `ensure_column`) mark it `failed` [run].
- **Evidence:**
  - [run] `demo.py` A:
    - A flag session took the flag count from 915 to 9600.
    - A later `stage="image"` MODEL_DATA session was interrupted (KeyboardInterrupt). The journal reads `failed rang_original ['MODEL_DATA']`.
    - The refusal says to call `restore_flags(..., 'rang_original') to go back to the flags saved before it`. Following it leaves 915.
  - [run] D: read-only MS, journal `open`.
  - [run] F: different-shape CORRECTED_DATA; journal `failed`, and the next session is refused.
- **Proposed fix:**
  - (a) In `_put`, call `_mark("written", name)` *before* `putcol`, so the list never misses a partly written column.
  - (b) In `begin`, and in the pipeline's `restore_before` and its three "unfinished write-back" guards (core_pipeline.py:835, :855, :874): if the prior journal's `written` has neither FLAG nor FLAG_ROW, carry `initialising` (WB-05) and continue instead of refusing.
  - (c) Open the table before writing the journal.
  - (d) Correct the message ("the flags saved before the first rang session that used this version name").
  - (e) Map `InterruptedWriteBack` to `Refused` in the CLI.
  - (f) Optionally, pass the stage's version into `write_model_data` (WB-13).
- **Small and unambiguous:** small (about 25 lines and 3 tests). (b) is a design choice, but the obvious one.

### WB-05: an interrupted column initialisation is forgotten after `restore_flags`

- **Class:** should-fix (wrong visibilities left in CORRECTED_DATA or MODEL_DATA rows).
- **Where:** core_writeback.py:239-240 (`initialising` is carried only while `open`/`failed`), :566-570 (`restore_flags` sets `restored`), :511-515 (`ensure_column(init=None)` drops the mark without initialising); core_pipeline.py:819-820.
- **What is wrong:**
  - Once the journal says `restored`, the next session starts with `initialising=[]`, and `ensure_column` returns False without re-initialising.
  - Pipeline route [code]: apply is killed during `ensure_column("CORRECTED_DATA", init="data")`. The rerun runs `restore_before`, then `restore_flags`, and the journal says `restored`.
  - apply then rewrites only the rows it selects (applycal.py:399-505). Rows outside `data.scans` or the applied fields keep zeros instead of DATA.
- **Evidence:** [run] `demo.py` B:
  - The MODEL_DATA init was interrupted at row 64 (journal `failed ['MODEL_DATA']`).
  - After `restore_flags(ms)`, `ensure_column("MODEL_DATA")` returns False.
  - 96 of 150 rows are unity and the rest are 0, and the journal's `initialising` is `[]`.
- **Proposed fix:**
  - In `begin`, take `dirty = prior.get("initialising", [])` for any prior state except `closed`.
  - In `ensure_column`, a dirty column with `init=None` gets the name's default before the mark is dropped.
  - Test: demo B.
- **Small and unambiguous:** yes (about 6 lines and a test).

### WB-07: a read-only MS is not refused clearly

- **Class:** should-fix.
- **Where:** core_writeback.py:232-302; there is no writability check in `core_pipeline.preflight` or `inspect_ms`.
- **What is wrong:**
  - With the MS files read-only, `begin` first saves `rang_original` and writes the journal, then fails with a raw OSError on `table.lock`.
  - The journal stays `open` (WB-04).
  - With the parent directory read-only as well [code], it fails at the `mkdir` of `<ms>.flagversions` with a raw PermissionError.
- **Evidence:** [run] `demo.py` D: `raised OSError ...\d.ms\table.lock: Access is denied. (os error 5)`; the flagversions directory holds `FLAG_VERSION_LIST, flags.rang_original, rang-writeback.json`; `journal open`.
- **Proposed fix:**
  - At the top of `begin`, check `os.access(..., os.W_OK)` on `ms`, `ms/table.dat` and `flagversions.root(ms).parent`.
  - Raise `PermissionError(f"{ms} is read-only: rang writes FLAG and adds columns in place; copy it (with {ms}.flagversions) somewhere writable")`.
  - Call the same check from `preflight` for writing stages.
- **Small and unambiguous:** yes (about 12 lines and a test).

### WB-08: no user-facing restore route

- **Class:** should-fix.
- **Where:** core_cli.py (no restore verb); docs/cli.md:21-23 (backups are named, restoring is not explained); core_writeback.py:559-571.
- **What is wrong:**
  - The only restore path is the Python function `rang.core_writeback.restore_flags`, and only error messages name it. A grep of docs/, notebooks/ and README finds no other mention.
  - CASA `flagmanager(mode='restore')` works on the layout (W1-measured), but it does not update rang's journal. After a CASA restore rang still refuses with "FLAG may be partly written" [code]: the journal is only updated in `restore_flags`, :565-570.
- **Proposed fix:**
  - Add `rang-core restore-flags MS [--version NAME] [--list]`. The default version is the unfinished journal's `flag_backup`, else `rang_original`.
  - Add a docs/cli.md paragraph covering the verb, the CASA flagmanager alternative, and that the verb also clears the journal.
- **Small and unambiguous:** small (about 30 lines and a test). The verb name is the owner's choice.

### WB-09: Windows sharing violations give a raw "Access is denied"

- **Class:** should-fix (message only; the state stays recoverable).
- **Where:** the core writer's flush and `addcols` (core/src/ms_write.rs); core_writeback.py:297-302, :375-384.
- **What is wrong:**
  - If another process holds an MS file open without delete sharing (a plain `open()`; on Windows also indexers, antivirus or sync clients), `addcols` or `flush` fails mid-session with `OSError io: Access is denied. (os error 5)`.
  - The message names neither the file nor the cause.
  - A `core_ms` reader in another process does not block the writer.
- **Evidence:** [run] `demo6.py`:
  - core_ms reader held: OK.
  - `open()` of table.dat: `addcols` fails. The journal says `failed`, there is no CORRECTED_DATA, and orphan `table.f3*` files are left.
  - `open()` of the `table.f*` files: fails during the FLAG writes (4635 of 9600 cells).
  - Both MSs open afterwards and `restore_flags` works. Re-adding CORRECTED_DATA gives CORRECTED_DATA == DATA (`readd.py`).
- **Proposed fix:** in core_ms_write, catch OSError with winerror 5 or 32 and re-raise with "another program has a file of {ms} open; Windows does not allow it to be replaced. Close it and rerun (the journal is marked failed)".
- **Small and unambiguous:** yes (about 10 lines).

---

## Later

### WB-10: kill between the version rename and the list line

- **Where:** flagversions.py:195-201, :155-156.
- **What is wrong:** the version is complete and verified, but not listed. Every later `save` then refuses with "remove it first", which needs a hand step (documented, research/w1-writeback.md:262-264).
- **Proposed fix:** if `flags.<name>` exists unlisted, with `nrow` rows and no `.rang-partial`, append its list line instead of refusing.
- **Small and unambiguous:** small (about 8 lines).

### WB-11: no kill test on Windows

- **Where:** tests/test_w1_writeback.py:146-151 (skipped off POSIX); flagversions.py:57-67.
- **What is wrong:**
  - `demo5.py` [run] shows recovery works on Windows with `os._exit`, but no test keeps it so.
  - `_fsync_dir` is a silent no-op on Windows [run]: `os.open(dir, O_RDONLY)` raises PermissionError 13. Power loss is not covered (documented).
- **Proposed fix:** a CHILD variant with `os._exit(9)` on `nt`.
- **Small and unambiguous:** yes (about 10 lines).

### WB-12: a missing recorded version is skipped silently

- **Where:** core_pipeline.py:819.
- **What is wrong:** a `flag_version` in state.json that no longer exists (`.flagversions` deleted, or the MS copied without it) is skipped. The rerun then builds on the modified flags without a word [code].
- **Proposed fix:** Refused, or a logged warning plus `restore_missing` in the summary.
- **Small and unambiguous:** yes.

### WB-13: "before each stage writes" does not hold for model writes

- **Where:** docs/cli.md:22-23 and core_pipeline.py:18-20 versus core_model.py:188.
- **What is wrong:** image's and selfcal's MODEL_DATA writes save no `rang_<stage>_<time>`. They touch no flags.
- **Proposed fix:** reword to "before each stage writes flags", or pass `stage_version(ctx, ...)` into `write_model_data`, which also removes WB-04 symptom 1.
- **Small and unambiguous:** yes.

### WB-14: an interrupted manual restore leaves no record

- **Where:** core_writeback.py:559-571, flagversions.py:213-249.
- **What is wrong:**
  - `restore_flags` writes nothing to the journal until it has finished.
  - If it is interrupted with the journal `closed` (a manual restore, or `restore_before` before a forced rerun), FLAG is half-restored, and the next `WriteBack` starts without refusing.
  - In the pipeline it heals: the stage's rerun restores `prior` again [code].
- **Evidence:** [run] `demo9.py`: KeyboardInterrupt after the first 32-row chunk of `flagversions.restore` gives `flags after interrupted restore: 5880 (pristine? False) journal: closed` and `next WriteBack starts without refusal`.
- **Proposed fix:** in `restore_flags`, write the journal state `restoring` (with `restored_from`) before the first chunk and `restored` after. `begin` treats `restoring` like `failed`.
- **Small and unambiguous:** yes (about 8 lines and a test).
