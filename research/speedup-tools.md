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

## 4. Resume state (stopped on the owner's order, 2026-11-13 ~07:30 UTC+1)

Everything below is on branch `claude/speedup-tools-73baec`, pushed, not merged.

| Part | State |
| --- | --- |
| C, `heavy_lock.py --priority critical` | **implemented, unit-tested** (8 tests in `tests/test_heavy_lock_queue.py`, incl. the old loaded helper of 097588b serving critical tickets first). Critical tickets subtract 10**18 ns from the name's time and keep the `<20 digits>-<system>-<pid>.json` shape, so old copies honour them. Not yet used on the real queue. |
| D, `tools/check_all.py` | **implemented, unit-tested** (`tests/test_check_all.py`: UNC repair, archive default, stale-toolchain detection, quick test selection). `rang.check` gains `archive_outputs` (repairs/defaults `RANG_ARCHIVE_OUTPUTS`) and `--pytest-paths`. **Not yet run end to end** (`--dry-run` only): no venv in this worktree yet. |
| A, CI on pushed branches | **implemented**: `tests.yml` `push: branches-ignore: [main]`, concurrency group by branch name; `docs/agents/check-and-ci.md` + skill wrapper; AGENTS.md CI paragraph. The push of this branch triggered run 43368739920 (lint passed; rust and pytest were still queued when stopped). Free on a public repo: GitHub's Actions billing page says standard GitHub-hosted runners are free in public repositories. |
| B, sccache | **measured, null** (2026-11-13, coordinator): one exclusive hold, commit 2a02470, rustc 1.93.1, sccache 0.19.0, 3,323 s with exports. Totals A 980.3 s, B 973.2 s (-0.7 %), C 900.4 s (-8.2 %); C's hit rate 86.9 % (126/145) yet core-build fell only 240.7 -> 237.1 s: the wall time sits in the workspace's own crates and the link, which sccache does not cache. Rule (C >= 20 % faster, B <= 10 % slower): **not met**, so `RUSTC_WRAPPER` and `SCCACHE_DIR` stay unset. Archive `research/results/speedup-tools-bench.json`; bench scratch deleted. |

Found on the way (told the coordinator): `rang.check`'s own one-at-a-time lock
let a check hold 8 heavy-lock slots for hours while it waited behind another
check. `check_all.py` sets `RANG_CHECKALL_LOCKED=1` under the heavy lock.

Resume steps, in order:

1. Read CI run 43368739920 (`gh run view 43368739920`); fix if red.
2. `python tools/check_all.py --quick` in this worktree (creates `.venv` with uv),
   then the full `python tools/check_all.py` once; log both in tool-timings.
3. Bench (protocol section 3, frozen): `python <main>/tools/heavy_lock.py run --
   python tools/cold_build_bench.py --base ~/Build/tmp/<date>-rang-coldbench --commit <main head>`
   (exclusive, normal priority). Apply the decision rule; only then set the user env:
   `RUSTC_WRAPPER=sccache`, `SCCACHE_DIR=D:\rang\cache\sccache`, `SCCACHE_CACHE_SIZE=30G`,
   `CARGO_INCREMENTAL=0` (this invalidates every worktree's ext-build stamp once: `EXT_ENV`
   hashes CARGO*/RUST*). WSL: the same in `~/.profile`, cache `/mnt/d/rang/cache/sccache-wsl`.
4. Results into this note and `research/tool-timings.md`; CHANGELOG line for
   `rang-core check` (archive repair, `--pytest-paths`); hand to the coordinator,
   who merges (the heavy_lock change touches every session).
