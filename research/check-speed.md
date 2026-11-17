# check-speed: a faster full local check, same coverage

Task check-speed, 2026-11-11. Status: speed-ups **implemented and measured**;
the tiered rule (section 5) is **proposed** only, waiting for the owner.

## 1. Result

| | before (main 3eab67c) | after (this branch) | factor |
| --- | --- | --- | --- |
| warm tree, inside the lock | 784 s (outer `maturin develop -q` 1.1 s + check 783 s) | **94-97 s** (two runs) | 8.2× |
| cold worktree, inside the lock | 1,209 s (outer `maturin develop -q` 28.7 s + check 1,180 s) | **1,165 s** | unchanged (core-test alone varied 188-240 s over three cold runs) |
| pytest step | 180-190 s (serial) | 64-80 s (`-n 8`) | 2.4-2.8× |

The "about 50 min" per commit was mostly **lock wait**. Inside the lock a warm
check took 13 min, a cold one 20 min. Lock waits of 30-70 min appear in
`tool-timings.md` and in `heavy_lock` logs such as
`D:\rang\outputs\merge-v6-check.log` (eight jobs queued ahead).

Coverage is the same. The check has the same 18 steps and the same commands,
with two additions: pytest gains `-n 8`, and the two gpu steps gain
`CARGO_TARGET_DIR=core/target/feature-gpu`. The Rust test counts are
unchanged (23 + 268 + 274). pytest outcomes are identical per test: 1,104
report lines, 1,050 passed, 77 skipped and the same failures in the serial run
and in two `-n 8` runs (section 4).

## 2. Where the time went (before)

Per-step wall time from `rang.check --json`, main 3eab67c, detached checkout,
venv identical to the after-runs (section 6):

| step | cold | warm |
| --- | ---: | ---: |
| fmt ×3, ruff, ruff-format, diff-check | 1.6 | 0.6 |
| root-build / test / clippy | 12.6 | 0.5 |
| core-build | 231.8 | **225.5** |
| core-test | 188.1 | **103.4** |
| core-clippy, core-clippy-gpu | 34.3 | 0.6 |
| core-test-gpu | 306.7 | **258.8** |
| ext-build | 195.1 | 1.2 |
| ext-clippy | 9.1 | 0.2 |
| pytest | 189.8 | 179.5 |
| gain-hashes | 11.3 | 11.8 |
| **total** | 1,180.2 | 782.8 |

On a warm tree 588 s of the 783 s were rebuilds of the core. `core-test-gpu`
builds `core/target` with `--features gpu`. The next `core-build` sees
`rang-core` dirty with `FeaturesChanged { old: ["gpu"], new: [] }`, relinks
every binary and test under thin LTO with `codegen-units = 1`, and the gpu
build then rebuilds the other way. A probe in that state took
262.4 s; the same build again took 0.1 s (`cs-20261111-probe`, cargo
fingerprint log and `--timings`).

pytest: the 50 slowest phases (call, setup, teardown) add up to 127.6 s of
the 185 s durations run, and the slowest is 14.7 s (`test_pointing.py`). No
single test bounds an 8-way split, so the suite parallelises to about 2.5×.

## 3. What changed (implemented)

All of it is in `python/rang/check.py`, with tests in `tests/test_core_cli.py`.

1. **The gpu steps build in their own target directory**,
   `core/target/feature-gpu` (`CARGO_TARGET_DIR` on `core-clippy-gpu` and
   `core-test-gpu` only). The flip-flop is gone: warm core-build takes 0.1 s,
   core-test 7-8 s and core-test-gpu 7 s. On a cold tree the gpu steps compile
   their dependencies once more (core-test-gpu 307 → 355 s). This is the 8× win.
   Side effect: `core/target/release/gemclean`, which `test_g8_identity`
   compares with the extension, is now the feature-less build. Before, it was
   the gpu build that `core-test-gpu` uplifted last. The extension is built
   without `gpu`, so the test now compares like with like, as its docstring
   says. Disk cost: a second release tree per worktree, 947 MB for
   `core/target/feature-gpu` against 283 MB for the rest of `core/target`
   (after the warm runs). C: is nearly full, so worktrees should be removed
   once merged.
2. **pytest-xdist.** `pytest -q -n 8` when `xdist` is importable, serial
   otherwise. `pytest-xdist>=3.6` joins the `test` extra. Worker sweep, the
   full suite on an idle host: `-n 4` 90 s, `-n 8` 73 / 83 s, `-n 16` 72 s.
   8 is the knee, and it leaves half the host's 16 threads free.
3. **ext-build stamp.** After a successful `maturin develop` the check writes
   `<venv>/rang-check-ext-build.json`. It records a digest of the build's
   inputs, taken before the build:
   - every tracked or untracked-unignored file under `Cargo.toml`,
     `Cargo.lock`, `src`, `core` (which includes `core/py`), `.cargo`,
     `pyproject.toml`, `rust-toolchain*`, `README.md`, `LICENSE` and `data`
     (the core does `include_str!("../../../data/meerkat.itrf.txt")`), with
     contents;
   - `rustc +1.93 -vV`, the maturin version, the argument list, the
     interpreter, and the `CARGO*`, `RUST*`, `PYO3_*`, `MATURIN*` variables.

   The list is checked, not assumed. After each build the check reads cargo's
   dep-info for the extension (`core/py/target/release/rang_core_py.d`, every
   file the compiler read). If any checkout file in it lies outside the list,
   no stamp is written and the next run rebuilds. Without `data` the guard
   reports `data/meerkat.itrf.txt`, which is how that input was found; with
   it nothing is reported. A test asserts this for the checkout's own build.

   It also records a digest of the installed result: `python/rang/_core*`
   and the `rang-core` METADATA, `direct_url.json`, `entry_points.txt` and
   RECORD. The next run skips `maturin develop` only when both digests are
   equal, prints `ext-build: ... not rebuilt`, and marks the step
   `"cached": true` in `--json`. Any other extension in place (for example a
   debug `maturin develop`) forces a rebuild, as does `--rebuild`. A failed
   build deletes the stamp. It saves little on a warm tree (1.2 → 0.1 s,
   because cargo is already fresh), but it makes a no-op step visibly a
   no-op and protects the installed release extension.
4. **Cheap steps first.** Order: the three `cargo fmt --check`, ruff,
   ruff format, `git diff --check`, then the builds. pytest and the gate stay
   after core-build and ext-build: `test_g8_identity` skips without the
   gemclean binary, so an earlier pytest would quietly lose a test. By
   default every step still runs. The new opt-in `--fail-fast` stops after
   the first failure: a lint error ends the run in about 2 s.
5. **`tools/check.py`**: the check from the source tree, for a venv without
   `rang-core`; `ext-build` then installs it. It replaces the coordinator's
   outer `maturin develop -q`, a debug build in another profile (28.7 s
   cold, 1.1 s warm) that the release `ext-build` overwrote at once.
6. **Not done: caching the gain-hash gate.** The gate takes 10.5-11.8 s,
   about 11 % of a warm run. Its key would need the extension, every
   imported module and the archive files on the WSL share, and a missed
   input would hide a changed solve. The saving does not justify that risk.

## 4. Coverage evidence

- Rust: identical `test result` lines before and after: 23 passed, 1 ignored;
  268 passed; 274 passed (gpu).
- pytest, per-test `-rA` lines (`cs-20261111-after`): the serial run and the
  `-n 8` runs 1 and 2 have the same 1,104 PASSED / FAILED / SKIPPED lines.
  The only text difference is the worker temp directory (`popen-gw7`) inside
  one symlink skip message. Each run: 1,050 passed, 77 skipped.
- The failures are not caused by this change:
  - `test_w4_unsupported.py::test_missing_weights` fails in the baseline too:
    casacure writes a table and Windows refuses `table.f3` ("Access is
    denied"). It shows up only in venvs with the `casacure` extra; the main
    mirror's venv has none.
  - `test_every_text_read_and_write_names_its_encoding` caught a
    `read_text` in the new stamp code; fixed before the final runs.
- After the rebase onto main bd15126, the six test files added or changed
  since 3eab67c (`cs-20261111-newtests`) gave the same outcomes serially
  (three times) and under `-n 8` (three times): 50 passed, 6 skipped.

  In two earlier `-n 8` runs, taken while other jobs held 12 of the 16
  shared slots, `test_heavy_lock_queue.py::test_waiters_acquire_in_ticket_order`
  failed. The error was WinError 32 in `heavy_lock.release()`: `owner.json`
  was unlinked while a waiter thread had it open. It passed in 6 of 6 serial
  and 4 of 4 `-n 8` runs of the file on a quieter host. This is a
  load-sensitive race in `tools/heavy_lock.py` on Windows, which xdist makes
  more likely to show but does not cause (follow-up for the owner of that
  file: retry or ignore the sharing violation in `release`).
- ruff 0.17.4 flags SIM102 in `tests/test_p11_extract.py`; 0.17.3, the
  main checkout's version, passes. Both venvs here pin 0.17.3 (follow-up:
  pin ruff in the `test` extra or fix the line).

## 5. Proposed, not implemented: a tiered rule

Waiting for the owner's approval.

**Rule.** If every path changed since the last commit that passed the full check is
a Markdown file (`*.md` anywhere, except `docs/cli.md`, which is generated),
the commit may run the docs tier: the cheap steps, `core-build` (pytest's
`test_g8_identity` needs its gemclean binary and would otherwise skip),
`ext-build` (cached when fresh) and pytest. It skips root-*, core-test,
core-clippy, the gpu steps, ext-clippy and the gain-hash gate. Anything else
runs every step.

**Why this split.** No Rust source or Rust test reads Markdown: the one
`include_str!` reads `data/meerkat.itrf.txt`. The gate reads only the archive
and code. pytest cannot be cut down: 105 of the test files read `research/`
or other Markdown (the index, STATE structure, links, CLI page, receipts),
and those files alone take 40 s of the 64-80 s.

**Expected gain**, estimated from the per-step times above, not measured as a
run:

| tree | full check | docs tier |
| --- | ---: | ---: |
| warm | 95 s | about 75 s (saves about 15 s of Rust no-ops and the 11 s gate) |
| cold worktree | 1,165 s | about 510 s (core-build 240 + ext-build 195 + pytest 65-80; saves about 650 s) |

The cold case matters, because every new session starts in a fresh worktree.

**Alternatives for the cold case** (also proposed, each needs the owner):

- **One cargo target directory per repo, shared by the worktrees**, e.g.
  `~/Build/tmp/<date>-rang-target`. The global layout rules allow this when
  the build must be shared between worktrees, and the shared lock already
  serialises check runs. It also needs the feature-gpu split above, and
  branches would rebuild what differs.
- **sccache.**

**Usage that needs no rule change:**

- Run `rang-core check --only root-fmt,core-fmt,ext-fmt,ruff,ruff-format,diff-check`
  (2 s) before queueing for the heavy lock, so lint failures never cost a
  place in the queue.
- With the lock's shared slots (main's `tools/heavy_lock.py run --slots N
  --mem G`, added 2026-11-11 after these measurements), the check can run as
  a shared job, `--slots 8`, matching `-n 8`. Only timing runs need a plain,
  exclusive `run`. This is not measured. cargo uses all 16 threads by
  default, and the Rust kernels' pools are not capped per pytest worker, so
  `--slots 8` holds for pytest but not for a cold build. Peak memory was not
  measured either; the post-rebase check ran with `--mem 16`, which is a
  guess. Before relying on it, measure peak RSS and pass `-j 8` to cargo in
  shared mode.

## 6. Provenance

- Host: 16 logical CPUs, Windows 11, Rust 1.93, Python 3.14.
- Venvs: `uv venv -p 3.14`, then the dependencies of
  `[test,pointing,beam,imaging,formats,plot,casacure]` plus ruff 0.17.3,
  maturin 1.16.0 and pip, identical in both trees. The after tree also has
  pytest-xdist 3.8.0.
- Every timed run was taken through `tools/heavy_lock.py run` (exclusive). At
  the start of the final run (`cs-20261111-after2`), main's helper showed it
  as the exclusive owner with shared 0/16 slots, 0/48 GB. The earlier runs
  predate the shared slots.
- Archive: `RANG_ARCHIVE_OUTPUTS=\\wsl.localhost\Ubuntu\home\gijsm\Github\rang\outputs`.

| run | tree, commit | outputs (`D:\rang\outputs\`) |
| --- | --- | --- |
| before: outer maturin + check, cold then warm; `pytest --durations=50 -rA`; `--collect-only` | `~/Worktrees/rang/check-speed-base`, 3eab67c | `cs-20261111-base` |
| fingerprint probe: core-build after core-test-gpu | same | `cs-20261111-probe` |
| after, first code (no feature-gpu): cold, warm; serial and `-n 8` ×2 `-rA`; `-n 4`, `-n 16` | this worktree, bc4de3c | `cs-20261111-after` |
| after, final code: every target directory and the stamp removed; cold, warm ×2 | this worktree, 1c381f5 (rebased since, no code change) | `cs-20261111-after2` |
| post-rebase new test files, serial ×3 and `-n 8` ×5 | this worktree on bd15126 | `cs-20261111-newtests` |
| final check of the commit (shared job, `--slots 8 --mem 16`; not a timing run) | this worktree | `cs-20261111-final.log`, `.json` |

The scripts (`profile.ps1`, `after.ps1`, `after2.ps1`, `probe.ps1`) are
copied next to the outputs.
