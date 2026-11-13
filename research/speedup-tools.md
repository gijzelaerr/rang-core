# speedup-tools: less host time lost to checks, cold builds and the queue

Task speedup-tools, 2026-11-13 (owner: "Do all of them! We need to speed up").
Branch `claude/speedup-tools-73baec`. Status: **proposed** (this section,
committed before the code); results are added below as they are measured.

## 1. Diagnosis (from the task brief and the tool-timings log)

- About 22 local `python -m rang.check` runs on 12 Nov, each 20-50 min on 8
  slots: full checks hold half the host.
- A new worktree builds cold in about 1,165 s against 95 s warm
  (research/check-speed.md section 1). Of the cold time, core-build 232 s,
  core-test 188 s, core-test-gpu 307 s and ext-build 195 s are Rust compiles.
- Checks fail on setup, not code: Git Bash turns `\\wsl.localhost\...` in
  `RANG_ARCHIVE_OUTPUTS` into a single leading backslash; a stale target
  directory built by another rustc gives E0514; a stale `_core.pyd`.
- The heavy lock is FIFO, so critical-path E2/E3 jobs wait behind checks.

## 2. What is built

- **D.** `tools/check_all.py`: one wrapper any worktree runs. It fixes the
  archive path, clears target directories built by another rustc, builds the
  extension into the worktree's own venv, takes the heavy lock shared, logs to
  a known place and prints PASS or FAIL. `--quick` runs only the cheap gates
  and the tests the diff touches.
- **C.** `tools/heavy_lock.py --priority critical`: a ticket served before
  normal tickets, never preempting a running job, readable by the old code
  already loaded in running waiters.
- **B.** sccache 0.19.0 (official GitHub release, checksum verified) with its
  cache on `D:\rang\cache\sccache`, cap 30 GB.
- **A.** `tests.yml` also runs on pushes to agent branches; the agent
  procedure in `docs/agents/` uses CI instead of a full local check.

## 3. Measurement protocol for B (frozen before the measurement)

Hypothesis: with sccache warm, a cold build of a fresh checkout at a new path
takes materially less wall time than without sccache.

Known limits that bound the gain (sccache documentation): rlibs are cached,
but crates that link (bin, cdylib, proc-macro outputs that are dylibs, test
binaries) are not, and the cache key includes absolute paths, so the
workspace crates (rang-sim, rang-core, the extension) of a new worktree path
recompile. Only registry dependencies hit across worktrees.

Settings: `tools/cold_build_bench.py`, one exclusive `heavy_lock` hold
(queued normal, not critical), three fresh exports of the same commit
(`git archive`) at three different paths under
`~/Build/tmp/20261113-rang-coldbench/`, Rust 1.93.1, `--offline`, the
check's own cargo commands with `cargo test --no-run` in place of running the
tests:

1. root `cargo build --release`
2. core `cargo build --release`
3. core `cargo test --release --no-run`
4. core `cargo clippy --all-targets` (dev profile)
5. core `cargo test --release --no-run --features gpu`
   (`CARGO_TARGET_DIR=core/target/feature-gpu`)
6. extension `cargo build --release --manifest-path core/py/Cargo.toml`

Arms, in this order, in one hold: **A** no wrapper; **B** sccache with an
empty bench cache (`SCCACHE_DIR` a fresh directory, own server port);
**C** sccache warm from B, at a third path. `CARGO_INCREMENTAL=0` in all
three arms (it only changes the dev-profile clippy step; release builds are
never incremental). `sccache --show-stats` is recorded after B and C.

Decision rule: adopt sccache for the user if C is at least 20 % faster than
A in total wall time and B is no more than 10 % slower than A. Otherwise
record the result as null and leave `RUSTC_WRAPPER` unset. Numerics: sccache
returns the compiler's own output for the same inputs, and the release
profiles are not touched, so results are bit-identical by construction; the
full check at the end (pytest, gain-hash gate) confirms it.
