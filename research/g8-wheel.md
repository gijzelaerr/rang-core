# Rang: GeMClean in the wheel (task G8)

Status, 2026-11-10: **protocol** (written and committed before the first comparison).

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
