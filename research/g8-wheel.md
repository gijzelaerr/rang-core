# Rang: GeMClean in the wheel (task G8)

Status, 2026-11-10: **implemented and measured; the five-platform CI gate waits for the push.**
`gemclean` ships in the wheel as a console script over `rang._core.gemclean_main`; no second
binary. Identity: the wheel's FITS files are byte-identical to the fat-LTO source build's on
every case (A0 and A1 natively: S1 at the defaults and at 1e-6, D1-C1, the pilot-512; A2 in
Linux: S1, D1-C1). Speed on the wheel, pilot-512, idle host: 140.0 s against 137.7 s at `-j 16`
(+0.5 %, paired median) and 798 s against 788 s at `-j 1` (+1.4 %, two pairs: +5.3 %, −2.6 %);
in Linux (WSL, the MS through 9p) 196.6 s against 189.9 s at `-j 16` (+3.3 %) and 730 s against
729 s at `-j 1`. Fat LTO for the wheel is not adopted (section 5's rule: 0.6 % slower at
`-j 16`, 0.2 % faster at `-j 1`). Ctrl-C ends the console script at once, as the binary. The
name check finds no clash. The protocol (sections 1-8) was committed before the first
comparison (`a17e7fc`).

Finish plan row G8: "In the wheel: extension binding and a `gemclean` console script, not a second
binary | oracle: source build | gate: `pip install` runs it on all five platforms; FITS identical
to the source build on S1; speed measured on the wheel, because current figures come from the
fat-LTO `gemclean` profile | timed | after G7". Owner decision 4 (section 7 of the finish plan):
a name clash check before `gemclean` reaches PyPI as a console script.

## 1. Binding design

- **One CLI, two front ends.** The whole command line of `core/src/bin/gemclean.rs` (argument
  parsing, `run`, every mode) moves into the library as `rang_core::gemclean::cli`, with
  `pub fn main(args: &[String]) -> i32`: the arguments without the program name, return 0 on
  success, 2 after printing `gemclean: <error>` on stderr (as the binary's `main` did). It calls
  `set_default_plane_group` first, as before. `env!("CARGO_PKG_VERSION")` stays rang-core's in
  both front ends. New: `-version` / `--version` prints `gemclean <version>` and exits 0
  (WSClean's flag name is `-version`); `-h` keeps its exit 2 with the usage on stderr.
- **The binary** (`core/src/bin/gemclean.rs`) becomes a wrapper: the Linux `HugePageAlloc` global
  allocator, `std::env::args().skip(1)`, `cli::main`, `std::process::exit` with its code. A panic
  still ends it with 101.
- **The extension** gets `rang._core.gemclean_main(args: list[str]) -> int` (new file
  `core/py/src/gemclean_cli.rs`): the GIL released, `cli::main` inside `catch_unwind` (a panic
  returns 101, the binary's code, after the default hook has printed the message on stderr), then
  Rust's stdout and stderr flushed. On 64-bit Linux the extension gets the same `HugePageAlloc`
  global allocator as the binary, so huge pages and the memory counters (`-memory-report`,
  `memory` in `-report.json`) behave as in the binary; it applies to every allocation of the
  extension (allocations from 4 MiB are mapped and advised `MADV_HUGEPAGE`; smaller ones go to
  the system allocator). `memory::counting()` is used for reporting only.
- **Threads.** `-j N` calls `rayon::ThreadPoolBuilder::build_global` as before. If the global pool
  already exists (a second call in one Python process), the run gets its own pool of N threads
  through `install` instead of failing. The thread count reported is `current_num_threads()` in
  both cases.
- **The console script** `gemclean = "rang.gemclean:main"` in `[project.scripts]`: the module
  sets SIGINT (and SIGBREAK on Windows) to the default action before importing the extension, so
  Ctrl-C ends the process at once as it ends the binary (otherwise Python defers the signal until
  Rust returns, minutes later); flushes Python's own stdout and stderr; returns the code, which
  the generated script passes to `sys.exit`. `python -m rang.gemclean` is the same entry. The
  wheel holds no gemclean executable: only the extension and `rang/gemclean.py`; the installer
  writes the script (`bin/gemclean`, or the `Scripts\gemclean.exe` trampoline on Windows).
- **How rang-core finds gemclean.** `image.gemclean: auto` (the default) runs
  `[sys.executable, "-m", "rang.gemclean", ...]` as a subprocess, so the imager is always the one
  in the installed `rang._core` of the running interpreter, whatever PATH holds or whether the
  venv is activated. A subprocess, not an in-process call, because the stage log captures the
  child's file descriptors, Ctrl-C needs its own process, and rayon's global pool and the
  plane-group setting are per process. The receipt records the command and the sha256 of
  `rang._core` (`core.library_path()`) as `gemclean_sha256`. **The PATH and `core/target`
  fallbacks are dropped**: a stale source build found silently is a provenance hazard. A source
  build is used only when `image.gemclean` names it. An extension without `gemclean_main` (built
  before G8) fails the stage with a message saying so. The stage hash covers configuration
  values only (`image.gemclean` stays `auto`), so existing runs need no `--force`.

## 2. Builds

| name | what | profile | CPU | toolchain |
| --- | --- | --- | --- | --- |
| SB | source build, `cargo +1.93 build --profile gemclean --bin gemclean` in `core` | fat LTO, 1 codegen unit | `x86-64-v3` (`.cargo/config.toml`) | rustc 1.93.1 |
| SB0 | the same from main `38cc96d` (before G8) | as SB | as SB | as SB |
| WH | the wheel as CI builds it: `maturin build --release --locked` (maturin 1.16.0), `RUSTFLAGS="-C target-cpu=x86-64"` | core/py `release`: thin LTO, 1 codegen unit | `x86-64` baseline | rustc 1.93.1 |
| WV3 | diagnostic: WH with `RUSTFLAGS="-C target-cpu=x86-64-v3"` | as WH | `x86-64-v3` | as WH |
| WF | candidate: WH with `CARGO_PROFILE_RELEASE_LTO=fat` | fat LTO, 1 codegen unit | `x86-64` | as WH |
| SBL | SB built in WSL (`git archive` of the same commit) | as SB | `x86-64-v3` | rustc 1.93.1 |
| WHL | the Linux wheel from `tools/wheel/build.sh` (manylinux_2_28 container, as CI) | as WH | `x86-64` | rustc 1.93.1 |

Each wheel is installed with `uv pip install` into a fresh venv (Python 3.14) under the output
directory and run as its console script. Native builds on this host (Windows 11, 16 threads);
build walls are recorded (CI time proxy: the LTO step is serial).

**What identity to expect, and why.** WH differs from SB in LTO (thin against fat) and CPU
baseline (`x86-64` against `x86-64-v3`). Neither changes floating-point results here: the hot
kernels (gridder, gather sums) choose AVX2/FMA or AVX-512 at run time in both builds; rustc does
not contract `a * b + c` into FMA; `f64::mul_add` is correctly rounded both as the FMA instruction
(v3) and as the C library's `fma` (baseline); the one compile-time AVX2 path (`zero_row`, streamed
zero stores) writes the same zeros. So FITS files are expected **byte-identical** on the same OS.
Across OSes they are not (G4: native Windows against Linux differ in every file).

## 3. Identity gates (FITS files, sha256 of every file)

- **A0, the move is a no-op:** SB against SB0 on S1 at the default settings: byte-identical.
- **A1, wheel against source build (native Windows):** WH against SB, byte-identical, on
  S1 at the defaults (coarse, G7), S1 at `-wgridder-accuracy 1e-6` (double precision, the form
  before G7) and G3's D1-C1 at the defaults (8 channels, joined, `-fit-spectral-pol 4`). The
  timed pilot-512 runs of section 4 are compared as well (repeat 1 of every arm keeps its files).
- **A2, Linux:** WHL against SBL on S1 and D1-C1 at the defaults.
- Reported, not gated: WV3 and WF against SB.

Settings as G7's `id_run.py` (G2's identity set): S1 `D:\rang\outputs\20261102-gemclean\bench\data\s1.ms`,
`-size 2048 2048 -scale 1.5asec -weight briggs 0.5 -niter 1000000 -gain 0.1 -nmiter 1000
-abs-threshold 0.0001 -data-column DATA -field 0 -j 16 -no-update-model-required`; D1-C1
`D:\rang\outputs\20261106-g3-spectral\data\D1.ms`, `-abs-threshold 0.00015 -channels-out 8
-join-channels -fit-spectral-pol 4`, otherwise the same. Any difference fails the gate; the cause
is then looked for (and reported), no rebuild is chosen to pass it.

## 4. Timing method (G7's)

- **Input and settings:** the pilot-512 (`D:\rang\outputs\20261103-gemclean-heldout\real\cal.ms`,
  512 channels, 823,500 rows), G2's settings `-size 4096 4096 -scale 3asec -weight briggs 0.5
  -niter 1000000 -gain 0.1 -nmiter 1000 -abs-threshold 0.003 -data-column DATA -field 0
  -no-update-model-required`, G7's new defaults (no precision flags: 1e-4, single).
- **Host and load:** every run under `tools/heavy_lock.py`; G7's probe before and after (Windows
  processes above half a core, WSL `top`, `/proc/loadavg`); wait up to 10 min for a clean probe,
  then run and mark it spoiled. Cells decided on clean runs when there are as many as planned.
- **Measures, Windows:** wall from process start to exit (the driver). The console script's
  `gemclean.exe` is a trampoline that starts `python.exe` (and a uv venv's `python.exe` starts
  the base interpreter), so the process handle alone misses the work: every native run (SB too)
  is started suspended inside a **Job Object**; user and kernel CPU are the job's totals, and the
  peak working set is the largest over the job's processes (handles opened while they run). The
  job's peak commit is recorded too. Phase times from the log.
  **Linux:** GNU `time -v` around the command (the script is exec'd, no trampoline).
- **Arms, order, repeats (Windows):** `-j 16`: 3 repeats of SB, WH, WV3, WF, interleaved in that
  order, reversed on even repeats. `-j 1`: 2 repeats of SB and WH, 1 of WV3 and WF, in the same
  order (repeat 2: WH, SB). All `-j 16` first. **Linux:** SBL, WHL, `-j 16` 3 repeats
  (interleaved), `-j 1` 1 each. Start-up: 10 runs each of `SB -version` and the console script's
  `gemclean -version` (wall), to separate the launcher's cost from the imager's.
- **Figures:** per repeat paired, `wall_WH / wall_SB` (and WV3, WF); medians over repeats; for the
  `-j 1` cells with one repeat, against the median of SB or WH. CPU/wall reported for every run.

## 5. Decision rule (written before any timing)

- **Fat LTO for the wheel (WF):** adopted as core/py's `release` profile if WF's median wall
  saving against WH is **at least 3 %** at both `-j 16` and `-j 1`, its FITS are identical to WH's,
  and its local wheel build takes at most twice WH's and at most 30 min. Otherwise not adopted,
  with the figures recorded. 3 %, not G7's 10 %: a build profile has no accuracy cost, only build
  time.
- **CPU baseline (WV3):** not adoptable for a distributable wheel (it would refuse CPUs without
  AVX2/FMA). Its gap to WH is reported as an owner decision (ship `x86-64-v3`, add run-time
  dispatch to the remaining kernels, or accept).
- The speed gate is met when WH's figures exist; the gap to SB is a finding, not a pass/fail.

## 6. Per-platform gate (CI)

Each `test <platform> py3.10` and `py3.14` job of `.github/workflows/wheels.yml` (linux-x86_64,
linux-aarch64, macos-arm64, macos-x86_64, windows-x86_64) installs the wheel built by its
`wheel <platform>` job into a fresh venv through `tools/wheel/test.py`, with cargo removed from
PATH, and gains a `gemclean` step: (1) the wheel holds no gemclean executable; (2) the venv's
console script `gemclean -version` exits 0 and prints `gemclean <version>`; (3) without arguments
it exits 2 with the usage on stderr; (4) a small imaging run (`-size 128 128`, 200 components) on
an MS written by the core writer (`examples/w1_writeback.py`'s `make_ms`, seed 20261180, a
1 Jy point source at the phase centre) exits 0 and writes the five FITS files and the report,
with the dirty image's peak at the centre. `tests/test_g8_gemclean.py` joins the wheel's pytest
subset (exit codes, stdout and stderr, `-j`, SIGINT on Linux and macOS and CTRL_BREAK on Windows
ending the run with the binary's status). The gate is met per platform when both Python versions
of its job pass. I cannot push: the coordinator pushes the merged branch and reads CI.

Locally: native Windows (WH) and WSL Linux (WHL, built by `tools/wheel/build.sh`) through the
same `tools/wheel/test.py`.

## 7. Name clash check (owner decision 4)

Before the console script ships: PyPI (`gemclean`, `gem-clean`, `gem_clean`), conda-forge,
Debian and Ubuntu packages, Homebrew, RubyGems (`gem clean` is close to RubyGems' own `gem
cleanup`), npm, crates.io, and a web search for imaging software of that name. Result and a
recommendation in this note; the owner decides.

## 8. Where things go

Outputs `D:\rang\outputs\g8-20261110-01` (`bin/`, `wheels/`, `venvs/`, `identity/`, `runs/`,
`load/`, `runs.tsv`, `.code/`). Scripts in [`results/g8-wheel-scripts/`](results/g8-wheel-scripts/).
Status: `C:\Users\gijsm\Github\rang\outputs\status\fp-g8.md`.

## 9. Implementation (`ed836ec`)

- `core/src/gemclean/cli.rs`: the binary's code moved by
  [`move_cli.py`](results/g8-wheel-scripts/move_cli.py) (paths `rang_core::` → `crate::`,
  `run(raw)`, `-version`, the pool fallback, `pub fn main(&[String]) -> i32`); the binary is 20
  lines. `core/py/src/gemclean_cli.rs`: `gemclean_main` (GIL released, `catch_unwind` → 101,
  stdout and stderr flushed). `core/py/src/lib.rs`: the Linux `HugePageAlloc` global allocator and
  the registration.
- `python/rang/gemclean.py` (`main`, SIGINT and SIGBREAK to `SIG_DFL`), `[project.scripts]
  gemclean`; `rang.core_pipeline.find_gemclean` returns a `Gemclean` (argv, hashed path, label);
  the `image.gemclean` text and `docs/cli.md` updated; `tests/test_p12_rename.py` lists the new
  script.
- Tests: `tests/test_g8_gemclean.py` (in the wheel subset: exit codes and streams, `-version`, a
  128×128 run on a core-written MS with the dirty peak 1 Jy at the centre, `-j 1` and `-j 3` FITS
  equal with `threads` reported, two runs in one process with `-j 1` then `-j 3`, Ctrl-C through
  the script and through `-m`, rang-core's `auto`, no gemclean executable in the package);
  `tests/test_g8_identity.py` (checkout only: the script against `core/target/release/gemclean`,
  FITS bytes, stdout with times masked, stderr, `-version`, usage and error exit codes). All pass
  natively (7 + 1 tests).
- `tools/wheel/test.py`: step `gemclean` (no gemclean entry in the wheel but `rang/gemclean.py`,
  no `.data/scripts/`; the venv's console script `gemclean -version`); `tests/test_g8_gemclean.py`
  in the pytest subset. `.github/workflows/wheels.yml`: comments only, since its test job runs
  `tools/wheel/test.py`.

## 10. Measured: identity (gates A0-A2)

All `-j 16`, files hashed then deleted; archive [`g8-wheel.json`](results/g8-wheel.json).

| gate | pair | case | files | result |
| --- | --- | --- | ---: | --- |
| A0 | SB0 (`38cc96d`) against SB (`ed836ec`) | S1, defaults | 5 | **identical** |
| A1 | WH against SB | S1, defaults | 5 | **identical** |
| A1 | WH against SB | S1, `-wgridder-accuracy 1e-6` (f64) | 5 | **identical** |
| A1 | WH against SB | D1-C1 (8 channels, joined, 4-term fit) | 45 | **identical** |
| A1 | WH against SB | pilot-512, every timed run (5 each) | 5 | **identical** (one hash set) |
| A2 | WHL against SBL | S1, defaults | 5 | **identical** |
| A2 | WHL against SBL | D1-C1 | 45 | **identical** |
| reported | WV3, WF against SB | S1; pilot-512 (4 runs each) | 5 | identical |

As section 2 expected: neither thin LTO nor the `x86-64` baseline changes a bit.

## 11. Measured: timings on the pilot-512 (native Windows)

Runs 2026-11-10 07:23-09:54 ([`g8_run.py`](results/g8-wheel-scripts/g8_run.py), plans `j16`,
`j1`), each under the heavy lock. The session was restarted at 08:16 during `WH-j1-r1`; that run
was deleted unfinished and rerun at 08:31; the finished `SB-j1-r1` (08:15) was kept, as the plan
resumes on `timing.json`. **One run spoiled:** `WV3-j1-r1`, with another user's `llama-server` at
109 % of a core for the whole 10-min wait (not mine, not stopped); reported and marked. CPU and
peak working set over the Job Object (three processes for a console-script run: the trampoline,
the venv launcher, Python).

| arm | `-j` | runs | wall, s, median (range) | CPU/wall | peak GB |
| --- | ---: | ---: | --- | ---: | ---: |
| SB (fat LTO, v3) | 16 | 3 | 137.7 (137.7-139.3) | 10.9 | 15.64 |
| WH (the CI wheel) | 16 | 3 | 140.0 (137.7-140.4) | 11.1 | 15.67 |
| WV3 (wheel, v3) | 16 | 3 | 137.7 (136.2-138.2) | 11.0 | 15.65 |
| WF (wheel, fat LTO) | 16 | 3 | 141.3 (140.8-141.4) | 11.1 | 15.65 |
| SB | 1 | 2 | 787.8 (783.5-792.1) | 1.00 | 15.20 |
| WH | 1 | 2 | 798.3 (771.9-824.8) | 1.00 | 15.21 |
| WV3 | 1 | 1 (spoiled) | 764.2 | 0.99 | 15.21 |
| WF | 1 | 1 | 796.6 | 0.99 | 15.21 |

Every arm: 5 major cycles, 58,369 components, Q/Q0 2.6497e-2; PSF 147-152 s at `-j 1`.

Ratios of wall (section 4: paired by repeat; one-repeat cells against the other arm's median):

| ratio | `-j 16` (pairs) | `-j 1` (pairs) |
| --- | --- | --- |
| WH / SB | **1.005** (1.005, 1.020, 1.000) | **1.014** (1.053, 0.974) |
| WV3 / WH | 0.985 (0.983, 0.985, 0.989) | 0.957 (spoiled run) |
| WF / WH | 1.006 (1.005, 1.006, 1.027) | 0.998 |
| WF / SB | 1.026 | 1.011 |

WH's two `-j 1` repeats differ by 6.6 % (SB's by 1.1 %; G7 saw up to 7.7 % on this host), so
the `-j 1` figures resolve no difference below about 5 %. G7's coarse arm GC: 132.4 s and
751.9 s (binary `c7ca268`, 00:42-05:32 today); the 4-5 % between those and SB here was not
traced (the move is excluded: A0's files are identical, and SB0 was not timed).

**Start-up** (10 runs of `-version`): SB 4.4 ms, the console script 144 ms (trampoline, Python,
`import rang._core`), 0.1 % of a `-j 16` pilot run.

**Build walls** (local, inside the lock): SB0 239 s, SB 172 s, WH 176 s, WV3 190 s, WF 176 s;
Linux SBL 109 s, WHL 111 s (the wheel step of `tools/wheel/build.sh`). Fat LTO cost no build time.

## 12. Measured: Linux (WSL 2, the MS on `/mnt/d` through 9p)

Runs 2026-11-10 10:03-10:53 (plans `lx16`, `lx1`), GNU `time -v`; no run spoiled. SBL is the
`gemclean` profile built in WSL, WHL the manylinux_2_28 wheel from `tools/wheel/build.sh` (the
pinned container), run as `bin/gemclean` of a fresh uv venv. Both read the MS through 9p (read
77 s, as G7's LX).

| arm | `-j` | runs | wall, s, median (range) | CPU/wall | max RSS GB | phases (rep. 1), s |
| --- | ---: | ---: | --- | ---: | ---: | --- |
| SBL | 16 | 3 | 189.9 (188.0-190.9) | 7.9 | 15.69 | read 77.1, PSF 23.9, major 49.0 |
| WHL | 16 | 3 | 196.6 (196.2-197.2) | 7.9 | 15.68 | read 77.2, PSF 26.2, major 51.2 |
| SBL | 1 | 1 | 729.0 | 0.92 | 15.22 | PSF 139.7, major 365.8 |
| WHL | 1 | 1 | 730.4 | 0.92 | 15.24 | PSF 145.4, major 356.7 |

WHL / SBL: **1.033** at `-j 16` (pairs 1.046, 1.033, 1.033), **1.002** at `-j 1` (one pair). The
3 % at `-j 16` sits in the PSF and major-cycle phases (gridding and FFT), not in the read; at
`-j 1` the PSF is 4 % slower and the major cycles 2.5 % faster. The Linux wheel's memory counters
work (`memory` in `-report.json`, heap within 1 kB of the binary's), so the allocator is in. Which
of LTO or the baseline CPU gives the 3 % was not measured on Linux (no WV3/WF arms there; post hoc,
not run).

## 13. Decisions under section 5

- **Fat LTO for the wheel (WF): not adopted.** Saving against WH: −0.6 % at `-j 16` (slower) and
  +0.2 % at `-j 1`; the rule needed 3 % at both. Build time was not the obstacle (176 s both).
- **CPU baseline (WV3):** 1.5 % faster than WH at `-j 16`, 4.3 % at `-j 1` on one spoiled run.
  The run-time-dispatched kernels already carry the hot loops; the rest is within the `-j 1`
  noise. Owner decision 2.
- **Speed gate: met** (measured on the wheel). The wheel is 0.5 % (`-j 16`) and 1.4 % (`-j 1`,
  noisy) slower than the fat-LTO profile: G7's and the speed run's figures hold for the wheel
  within those margins.

## 14. Ctrl-C, exit codes, streams, threads

- **A real Ctrl-C** ([`ctrlc_check.py`](results/g8-wheel-scripts/ctrlc_check.py): a new console,
  `GenerateConsoleCtrlEvent(CTRL_C_EVENT, 0)` 0.5 s after the first line of output, `-j 2`, 1024²
  on the test MS): the source binary, the console script `gemclean.exe` and `python -m
  rang.gemclean` all end with `0xC000013A` (`STATUS_CONTROL_C_EXIT`, the binary's) within 6-10 ms.
  Control: `gemclean_main` called without the SIGINT reset ends only when the run does, 76.7 s
  later. CTRL_BREAK (Windows) and SIGINT (POSIX) are in `tests/test_g8_gemclean.py`: both entries
  end with the binary's status within 10 s.
- **Exit codes and streams:** 0; 2 with `gemclean: …` on stderr and nothing on stdout (no MS, an
  unknown option, a missing MS); usage on stderr for `-h`; byte-equal to the binary's
  (`test_g8_identity.py`). Panic → 101 is implemented (`catch_unwind`) but not triggered (no input
  makes gemclean panic).
- **Threads:** CPU/wall 0.99-1.00 on every `-j 1` pilot run through the script; `threads` in the
  report equals `-j`, also for a second run in one process (the pool fallback).

## 15. Owner decisions

1. **The name (owner decision 4).** Checked 2026-11-10: no `gemclean`, `gem-clean` or
   `gemclean-cli` on PyPI, crates.io, RubyGems, npm, conda-forge or Homebrew (404 each; the same
   queries give 200 for numpy, serde, rails, wget); no Debian source package; on GitHub four
   unrelated repositories (three image-watermark removers called GemClean or gemclean, one
   empty); a web search finds no imaging software of that name. RubyGems' own command is `gem
   cleanup`. Recommendation: keep `gemclean`.
2. **CPU baseline:** ship `x86-64` wheels (now; 1.5 % behind `x86-64-v3` at `-j 16`), ship v3
   (refuses CPUs without AVX2/FMA), or add run-time dispatch to the remaining kernels.
   Provisional: keep `x86-64`.
3. **`image.gemclean: auto` no longer searches PATH or `core/target`** (provenance); a source
   build must be named. Provisional.
4. **The extension's allocator on Linux** is gemclean's huge-page allocator for every allocation of
   the extension, as in the binary. Provisional; six lines of `core/py/src/lib.rs` to revert.
5. **The sdist does not build** (found here, already so on main): the sdist-build step of
   `tools/wheel/build.sh` fails at `include_str!("../../../data/meerkat.itrf.txt")` in
   `core/src/gemclean/sim.rs`, since `data/**` is left out of the sdist. CI builds the sdist but
   never builds from it, so `pip install` from the sdist fails. Follow-up: put that file in the
   sdist or under `core/`. Not fixed here.

## 16. What was not checked

- macOS and Linux aarch64 only through CI (I cannot push); Windows and Linux x86_64 locally.
- A panic in gemclean; the 101 path is read in code only.
- `-j 1` differences below about 5 % (two repeats, 6.6 % spread).

## 17. CI: which job proves which platform

After the push, `.github/workflows/wheels.yml` runs `wheel <platform>` (build) and `test
<platform> py3.10` and `py3.14` (a fresh venv, cargo off PATH, step `gemclean`, pytest with
`tests/test_g8_gemclean.py`). A platform's gate is met when both of its test jobs pass:

| platform | jobs |
| --- | --- |
| linux-x86_64 | `test linux-x86_64 py3.10`, `test linux-x86_64 py3.14` |
| linux-aarch64 | `test linux-aarch64 py3.10`, `test linux-aarch64 py3.14` (native arm runner) |
| macos-arm64 | `test macos-arm64 py3.10`, `test macos-arm64 py3.14` |
| macos-x86_64 | `test macos-x86_64 py3.10`, `test macos-x86_64 py3.14` |
| windows-x86_64 | `test windows-x86_64 py3.10`, `test windows-x86_64 py3.14` (PYTHONUTF8=0) |

Locally, the same `tools/wheel/test.py`: Windows (WH, Python 3.14) PASS (46 passed, 16 skipped for the absent fixture, allowed without `--fixture-cache`); Linux (WHL,
Python 3.14) PASS (51 passed, 11 skipped, the same reason).

## 18. On disk

Kept: `D:\rang\outputs\g8-20261110-01` (0.37 GB: `bin/` with SB0, SB, SBL and the source
tar, `wheels/` with WH, WV3, WF, WHL and provenance, `venvs/` with the three Windows wheel venvs,
`identity/` and `runs/` with hashes, logs, reports and timings (FITS deleted), `startup/`,
`ctrlc/` with the test MS, `wheeltest-*`, `.code/`). Removed: the WSL build and venv directories
`~/Build/tmp/20261110-g8-{src,target,whl,venv-whl,wheeltest}`, the Windows target dirs.

## For the coordinator

- Push the branch; read the ten `test <platform> py…` jobs of `wheels.yml` (section 17) and
  record the five-platform gate.
- `research/README.md` index line: `[g8-wheel.md](g8-wheel.md) — G8: gemclean in the wheel as a
  console script over the extension; FITS byte-identical to the fat-LTO source build (S1, D1-C1,
  pilot-512; Windows and Linux); the wheel 0.5 % slower at -j16, 1.4 % at -j1; fat LTO not adopted.`
- `research/STATE.md`: "G8, GeMClean in the wheel, 2026-11-10 (measured;
  [g8-wheel.md](g8-wheel.md)). `pip install rang-core` gives `gemclean`, a console script over
  `rang._core.gemclean_main`; the command line lives in `rang_core::gemclean::cli` and the source
  binary wraps it. FITS byte-identical to the fat-LTO `gemclean` profile on S1 (defaults and
  1e-6), D1-C1 and the pilot-512 natively, and on S1 and D1-C1 in Linux. Pilot-512, idle host:
  the CI wheel 140.0 s against 137.7 s at -j16, 798 s against 788 s at -j1 (noisy); Linux (WSL, 9p) 196.6 s against 189.9 s at -j16 (+3.3 %), 730 s against 729 s at -j1; fat
  LTO for the wheel not adopted; x86-64-v3 wheels 1.5 % faster at -j16 (owner). Ctrl-C ends the
  script at once (0xC000013A, as the binary). `image.gemclean: auto` runs the extension. The sdist
  does not build (data/meerkat.itrf.txt left out; already so on main). Five-platform CI gate:
  read after the push."
- `research/finish-plan.md`: G8 done but for the CI read; owner decision 4 answered with a
  recommendation (keep the name, section 15 item 1); new open items: the CPU baseline and the
  sdist build (section 15 items 2 and 5).
- Branch `fp-g8-wheel`; outputs `D:\rang\outputs\g8-20261110-01`.
