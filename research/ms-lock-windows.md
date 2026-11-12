# The table lock on Windows (2026-11-12)

Status: implemented and checked (native Windows, base `2899c23`).

## Cause

`tests/test_core_ms_write.py::test_the_lock_keeps_a_second_process_out`
failed natively on Windows: the second writable open did not raise.
- The import path and startup timing were not the cause: the holder prints
  "held" only after `open_table` returned.
- `core/src/ms_write.rs` had casacore's fcntl lock (`F_SETLK`, write lock on
  byte 0, "in use" read lock on byte 1 of `table.lock`) under
  `cfg(target_os = "linux")` only. Every other platform got a stub that
  always reported success.
- So on Windows `LockFile::acquire` never failed, and two processes could
  write one table at once. `research/e3-table-writer.md` item 5 stated this.
  It was a correctness gap for concurrent writers, not a test fault.
- The test skips on main because its fixture MS is not in the main
  checkout's `outputs/`, so it showed up only in worktrees that held the
  fixture (`research/sliced-read.md`, section 5).

## Fix

A Windows module next to the Linux one in `core/src/ms_write.rs`:
`LockFileEx` with `LOCKFILE_FAIL_IMMEDIATELY`, exclusive for lock 0 and
shared for the "in use" byte. Windows locks differ from fcntl in three ways,
and the module handles each:
1. **Mandatory, per handle.** A lock on bytes 0 and 1 would make every other
   handle's read of `table.lock` fail, even in the same process. That
   includes the readers' sync-record row count: `ms.rs` `lock_sync_rows`
   errors, and `ms_write.rs` `table_rows` and `array_records` fall back
   silently to `table.dat`. So the lock bytes are taken at `2^62 + start`,
   far past the end of the file; the file's own bytes stay readable.
2. **No implicit loss, no re-entry.** Closing another handle does not drop a
   lock, and a second exclusive lock of the same range from the same handle
   fails. `LockFile::reassert` is therefore a no-op on Windows; on Linux it
   still re-takes the lock that POSIX drops when any descriptor closes.
3. **Errors.** Only `ERROR_LOCK_VIOLATION` (33) counts as "locked". Any other
   failure (for example a share without byte-range locks) is reported as
   "lock of <path>: <error>", not as "locked by another process".

Other platforms (macOS) keep the stub.

### Scope

- The lock keeps a second rang writer out on Windows, in another process
  or, since the locks are per handle, in the same process. On Linux a second
  writable open in the same process still succeeds, as with fcntl.
- It does not interoperate with casacore's fcntl lock: a WSL casacore
  process and a Windows rang process writing the same file do not see each
  other's locks. Not tested, not claimed.
- Results: the lock touches no data path. Bytes written, the sync record and
  row counts are unchanged; E2 runs are unaffected.

## Tests

- Rust: `ms_write::tests::the_lock_file_keeps_its_bytes_readable_and_survives_reassert`.
  The file stays readable from another handle while locked; `reassert` and
  `write_sync` work while held. On Windows a second `acquire` is refused,
  and after drop it succeeds.
- Python, `tests/test_core_ms_write.py`:
  - `test_the_lock_keeps_a_second_process_out`, on the fixture MS. The
    fixture was copied from
    `\\wsl.localhost\Ubuntu\home\gijsm\Github\rang\outputs\tv-caracal-wsl-20261029-01\original.ms`
    (40 MB), as the sliced-read worktree held it.
  - `..._of_a_new_ms`, on a `default_ms` in `tmp_path`. It needs no fixture,
    so CI runs it on Linux and Windows.
  - `test_a_reader_sees_the_rows_while_the_writer_holds_the_lock`: the
    mandatory-lock trap of point 1.

## Check

- Writer tests on the fixture (`tests/test_core_ms_write.py`): 7 passed, 4
  skipped (the frozen E3 oracle run is not in the worktree). The extension
  imported, by the test and by the holder through its `sys.path`, was this
  worktree's `python\rang\_core.pyd`.
- Full local check (`python -m rang.check` after `maturin develop --release`,
  heavy lock shared, 4 slots, `RANG_ARCHIVE_OUTPUTS` the WSL archive):
  overall PASS. fmt, ruff, clippy, cargo tests (269 core, 275 GPU), 1248
  pytest passed and 74 skipped, gain-hash gate PASS.
  - Log: `D:\rang\outputs\ms-lock-windows-20261112-check2.log`, 29 min 44 s
    including the lock wait.
  - The first run, `-check.log`, failed on the research index entry only.
    Also, in Git Bash, `RANG_ARCHIVE_OUTPUTS` must be given as
    `//wsl.localhost/...`: a leading `\\` reached Python as one backslash,
    and the gain-hash gate then found no archive.
- Not checked: Linux. CI runs the fixture-free tests there; the Linux module
  changed only its return type and the `REASSERT` flag.
