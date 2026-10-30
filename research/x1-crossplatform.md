# Cross-platform build, CI matrix and portability (big plan task X1)

Status, 2026-10-30: **implemented; measured locally on native Windows and on
Linux (WSL); the CI matrix is written and lints clean but has not run on
GitHub** (nothing pushed; macOS was not available here, so the macOS jobs are
untested). A packaging and portability task under AGENTS.md, not a
scientific contribution; no archived result changed.

Summary:

- The Rust core, the root crate and the PyO3 extension build natively on
  Windows 11 with Rust 1.93.1 (MSVC) and maturin 1.16.0 with no source change.
  `import rangtoy._core` works, the extension backend is chosen, and the
  extension `.pyd` exports the C ABI just as the Linux `.so` does.
- `tests/test_core_backends.py` passes on Windows (10 passed, 1 skipped for the
  absent MS oracle). Of the whole suite, 529 tests pass, 17 fail and 3 modules
  (20 tests) do not collect. Every failure is a POSIX assumption in the
  Python or test code (`resource`, `st_blocks`, symlinks, path separators,
  console encoding), not a numerical one. They are listed below for
  P7/P9/P12 and were not fixed here.
- The task D Tricolour comparator ran natively on Windows against the
  archived inputs. Its numerical criteria 1–4 pass exactly: FLAG, the
  training proposal, every stage and the polarised intensity are bit-equal.
  All 56 output arrays are byte-identical to a Linux run of the same commit.
  Criterion 5 (input hashes unchanged) **fails as frozen** on Windows,
  because the receipt's tree hash feeds `str(Path.relative_to())` (with
  backslashes) into the digest. Post hoc, the same hash with POSIX path
  strings equals the archived record for all four controls.
- `wheels.yml` now builds and tests manylinux_2_28 x86_64 and aarch64,
  macOS arm64 (`macos-14`) and x86_64 (`macos-15-intel`), and win_amd64
  (`windows-2022`), all abi3-py310 at the baseline CPU. Each wheel is tested
  on CPython 3.10 and 3.14 on its own OS with cargo absent, through the new
  portable `tools/wheel/test.py`. The workflow keeps the release job and adds
  a trusted-publishing PyPI job on `v*` tags.
- New local scripts `tools/wheel/build.py` and `tools/wheel/test.py` build and
  test the native wheel without docker. Both were verified on Windows and on
  Linux. The docker path (`build.sh`, `test.sh`) is unchanged.

## How the work was split between the two checkouts

All edits and commits are in the WSL worktree
`~/Worktrees/rang/x1-crossplatform` (branch `x1-crossplatform`). The Windows
clone `C:\Users\gijsm\Build\tmp\20261030-rang-x1\ra-ng` was only for
building and testing. It was cloned from the main WSL repository
(`git -c safe.directory=* clone -b x1-crossplatform \\wsl.localhost\Ubuntu\home\gijsm\Github\rang ra-ng`);
a worktree path cannot be cloned from Windows, because its `.git` file
names a Linux path. Edited files were copied between the two checkouts and
verified on both before the commit. Nothing was pushed.
After the task, the Windows clone, the copied inputs and the wheel folders
(`C:\Users\gijsm\Build\tmp\20261030-rang-x1`, 1.6 GB) and the Linux
scratch (`~/Build/tmp/20261030-rang-x1-linux`, 269 MB) were removed; the
receipts are in `outputs/x1-crossplatform-20261030-01`. X2 can re-clone in
about 20 s.

## 1. Native Windows build

Host: Windows 11 Pro 10.0.26300, 16 logical cores, rustup with stable
1.99.1 and 1.93.1 (`x86_64-pc-windows-msvc`), CPython 3.14.7, uv 0.13.5. While
this ran, the WSL side carried a load of about 50 from sibling agents, which
shares the same CPUs. Windows wall times are therefore upper bounds.

| Step | Command | Wall | Result |
| --- | --- | ---: | --- |
| clone | `git clone -b x1-crossplatform \\wsl.localhost\...\rang ra-ng` | 21.2 s | **CRLF checkout** (Git for Windows `core.autocrlf=true`: 523 of 526 files CRLF); switched to LF in place (`git config core.autocrlf false; git rm -rq --cached .; git reset --hard`) before any test or hash |
| toolchain | `rustup toolchain install 1.93` | not timed | Git Bash has no `/usr/bin/time` (the first timing wrapper failed; bash `time` used after that). The toolchain was auto-installed by the first `+1.93` call; with clippy and rustfmt |
| core | `cargo +1.93 build --release --locked --manifest-path core/Cargo.toml` | 56.3 s (cold, including the crate download) | `rang_core.dll` 1.59 MB, plus `.dll.lib`/`.dll.exp` |
| root | `cargo +1.93 build --release --locked` | 8.1 s | `rang_toy.dll`, `rang-toy.exe`; **warning: output filename collision `rang_toy.pdb`** between the bin `rang-toy` and the lib `rang_toy` (cargo issue #6313; harmless, only the debug-symbol file of one is kept) |
| venv | `uv venv -p 3.14 .venv`; `uv pip install --python .venv\Scripts\python.exe --index-url https://pypi.org/simple -e ".[pointing,beam,test,imaging]" ruff maturin` with `RUSTUP_TOOLCHAIN=1.93` | 0.2 s; 83.7 s | jax, katbeam, astropy and scipy all install on Windows. The editable install builds the extension |
| extension | `maturin develop --release` (venv active, `RUSTUP_TOOLCHAIN=1.93`) | 3.8 s failed; 2.1 s warm | The first attempt failed inside uv (`too many temporary files exist at path ...\AppData\Local\uv\cache`), a state of this host's default uv cache. With `UV_CACHE_DIR=~/Build/cache/uv` it passed. Result: `python\rangtoy\_core.pyd` 2.05 MB **and `python\rangtoy\rang_core_py.pdb`**, both untracked (see the `.gitignore` fix) |
| import | `python -c "import rangtoy._core"`; `core.backend_name()`; `ctypes.CDLL(_core.__file__).rang_core_fused` | <1 s | pass; `extension`; **the `.pyd` exports the C ABI** (MSVC with thin LTO keeps the `#[no_mangle]` symbols of the `rang-core` rlib) |
| backend tests | `pytest -q -rs tests/test_core_backends.py` | 52.1 s | **10 passed, 1 skipped** ("MS oracle not present", as in CI). The ctypes half built `core/` through `core.build_core()` (cargo), which finds `rang_core.dll` |
| suite | `pytest -q -rfEs --continue-on-collection-errors --junitxml=...` | 414.5 s | **529 passed, 17 failed, 5 skipped, 3 collection errors** (571 tests on Linux; 20 of them in the 3 modules that do not collect) |

### Windows test results, failure by failure

Receipts: `outputs/x1-crossplatform-20261030-01/windows-pytest/` (log and
JUnit XML). None of these failures is numerical. Each one names its cause and
the portable replacement; they belong to P7, P9 and P12, which own these
files.

| Test(s) | Cause, file:line | Portable replacement |
| --- | --- | --- |
| collection: `tests/test_core_campaign.py`, `tests/test_core_campaign_array.py`, `tests/test_p3_flags.py` (20 tests) | `import resource` at module level: `python/rangtoy/core_campaign.py:17` (used at :141), `python/rangtoy/core_campaign_array.py:27` (used at :123), the latter also reads `/proc/meminfo` at :129 | One helper, `peak_rss_mb()`: `resource.getrusage` on POSIX (note that `ru_maxrss` is KiB on Linux but **bytes on macOS**, so every `/ 1024` in the tree is wrong on macOS), `psutil.Process().memory_info().peak_wset` or `GetProcessMemoryInfo` through ctypes on Windows; `psutil.virtual_memory()` for `/proc/meminfo` |
| `test_flagging_caracal.py::test_native_command_matches_caracal_polarisation_and_preserves_flags` | `python/rangtoy/flagging_caracal.py:57` builds the command with `str(Path(interpreter).with_name("tricolour"))`, which gives backslashes on Windows; the test (`tests/test_flagging_caracal.py:30`) expects `/isolated/bin/tricolour` | The command targets a POSIX container: build it with `PurePosixPath`. The test is right |
| `test_flagging_equivariance.py::test_checked_checkpoint_is_exclusive_and_stops_before_budget_breach`; `test_flagging_imaging.py::test_budget_refuses_symlinks_and_reserve`, `::test_every_native_column_write_has_exclusive_previous_backup`, `::test_post_wsclean_checks_exact_written_arrays_and_native_columns[*]` (7 parameters) | `os.stat_result.st_blocks` does not exist on Windows: `python/rangtoy/flagging_equivariance.py:66`, `python/rangtoy/flagging_imaging.py:291` | The fallback that `python/rangtoy/flagging_response.py:69` already uses: `getattr(st, "st_blocks", (st.st_size + 511) // 512) * 512` |
| `test_flagging_next.py::test_invalid_dispatch_refused_before_import_or_cache_write[symlink]` (:118), `test_flagging_response.py::test_copy_budget_rejects_source_symlinks_before_writes` (:336), `::test_nested_existing_and_dangling_outputs_refused_before_source_reads` (:379), `test_flagging_signal_guard.py::test_existing_dangling_and_nested_outputs_refused_before_reads` (:194) | `Path.symlink_to` raises `WinError 1314` without Developer Mode or administrator rights | Test-side: a fixture that tries a symlink in `tmp_path` and calls `pytest.skip("symlinks need Developer Mode on Windows")` on `OSError`. The guards themselves (`is_symlink()`) are portable |
| `test_ms_inspection.py::test_unsafe_archive_paths[a\\b]` (:21) | `zipfile.ZipInfo("a\\b")` converts `os.sep` to `/` on Windows, so the test input becomes `a/b` and the reader's backslash check (`examples/inspect_measurement_sets.py:37`) never sees it. The reader is right, because real archive members are not converted | Test-side: `info = ZipInfo("x"); info.filename = "a\\b"` |
| `test_pointing_example.py::test_pointing_example_exports_results` (:16) | `examples/pointing.py:167` prints `→` to a console whose encoding is cp1252: `UnicodeEncodeError` | `PYTHONUTF8=1` (or `sys.stdout.reconfigure(encoding="utf-8")`) in the CLI entry point; or ASCII `->`. The code also has 189 `read_text()`, 106 `write_text(` and 48 `open(` without `encoding=`, which use cp1252 on Windows until Python 3.15. Use `encoding="utf-8"` everywhere, or run under UTF-8 mode |

The 5 skips are those of Linux without the archived oracles: the MS oracle
and fixture dumps are not present. python-casacore is not installed on
either platform (the `flagging` extra), so the casacore-dependent paths are
untested on both, not just on Windows. The other 529 tests, which include
every core wrapper, the gridder, weights, zarr and blosc, the MS reader on
synthetic tables, flagging and pointing (jax), pass on Windows.

## 2. Comparator reproduced natively on Windows: task D

Choice: task D (the Tricolour port). It needs neither bash nor
`/usr/bin/time` nor `resource`. The core-j suite route needs
`tools/core-j-suite.sh`, `validate_core_phase2.py` (`/usr/bin/time`,
`resource`) and section 6 (`resource`), so it cannot run natively by
design. Inputs were copied read-only from WSL into
`C:\Users\gijsm\Build\tmp\20261030-rang-x1\inputs\outputs\`:
`core-d-oracle-20261029-01`, `tv-caracal-wsl-20261029-01` (457 MB),
`caracal-strategy-inputs-8f7bb363`. The copy used
`cp -r --no-preserve=mode` from WSL to `/mnt/c` and took 116.0 s.

```sh
# Windows, from the inputs folder, the clone's venv (Rust 1.93.1 MSVC extension)
python ra-ng/examples/run_core_flags.py outputs/core-d-oracle-20261029-01/run \
  outputs/tv-caracal-wsl-20261029-01 outputs/caracal-strategy-inputs-8f7bb363 outputs/x1-d-20261030-01
python ra-ng/examples/compare_core_flags.py run outputs/x1-d-20261030-01 \
  outputs/tv-caracal-wsl-20261029-01 outputs/core-d-oracle-20261029-01/run outputs/x1-d-compare-20261030-01
```

| Criterion (frozen, `core-d-tricolour.md`) | Windows | Linux, same commit (WSL, `~/Build/tmp/20261030-rang-x1-linux/x1-d-wsl-01`) |
| --- | --- | --- |
| 1 FLAG exact (4 × 2,293,760 elements) | pass, 0 differences | pass |
| 2 training proposal = archive (26,692 / 26,637 / 662 / 735) | pass | pass |
| 3 every stage exact | pass, 0 differences at every step | pass |
| 4 polarised intensity bit-equal | pass | pass |
| 5 input hashes unchanged | **fail as frozen**: `hashes_equal_to_oracle_record` false, `hashes_equal_to_core_record` true | pass |
| all 56 arrays of `flags.npz`, `intensity.npz` and `stages.npz` | byte-identical to the Linux run (`tobytes()` equality; the `.npz` files themselves differ only in zip metadata) | |
| port wall, 4 controls | 1.56 s (0.31, 0.28, 0.21, 0.20 s); run 2.8 s, compare 1.1 s | 3.17 s (0.97, 0.92, 0.60, 0.68 s) under load 50; run 6.5 s, compare 2.1 s |

**Criterion 5 failure, diagnosed (post hoc, labelled).** `run_core_flags.py`
and `compare_core_flags.py` hash a Measurement Set tree as
`sha256(str(p.relative_to(path)).encode() + bytes ...)` over `sorted(paths)`
(`examples/run_core_flags.py:41`, `examples/compare_core_flags.py:69`,
`examples/oracle_tricolour.py:53`). On Windows `str()` gives backslash
separators, so the digest differs while every byte is the same. A post-hoc
recomputation with `relative_to(...).as_posix()` and POSIX ordering equals
the oracle's archived `host_hashes` for all four `diagnostic.ms` trees, and
the `.npz` file hashes match directly. The inputs were therefore unchanged,
and criterion 5's intent holds. As frozen, it fails on Windows only. This
is a portability defect of the receipts, not of the port. 21 call sites
share the pattern (inventory, item 9).

Floating point: MSVC (Windows) and GCC/LLVM-on-Linux builds of the same
Rust code give identical bits here, as expected. Rust emits its own LLVM IR
on both, the code is the same, and the SumThreshold/Stokes kernels use no
platform libm. Tolerances were not needed.

Receipts: `outputs/x1-crossplatform-20261030-01/task-d-windows/`
(`run-receipt.json`, `compare-result.json`, the log) and `task-d-linux/`.

## 3. CI matrix: `.github/workflows/wheels.yml`

Jobs (actionlint 1.7.12 with shellcheck, `uv tool run --from actionlint-py
--with shellcheck-py`: 0 errors, 11.7 s including the download):

- `wheel` (5 entries): `PyO3/maturin-action@v1`, `--release --locked`,
  Rust 1.93.1, maturin 1.16.0, `RUSTFLAGS=-C target-cpu=<baseline>`, which
  overrides `.cargo/config.toml`:
  - `linux-x86_64`: ubuntu-24.04, manylinux 2_28, `x86-64`;
  - `linux-aarch64`: ubuntu-24.04, cross-built in maturin-action's container,
    `generic`;
  - `macos-arm64`: `macos-14`, `aarch64-apple-darwin`, `apple-m1` (that
    target's default);
  - `macos-x86_64`: `macos-15-intel`, `x86_64-apple-darwin`, `x86-64`;
  - `windows-x86_64`: `windows-2022`, `x86_64-pc-windows-msvc`, `x86-64`.

  Each job uploads its wheel as artifact `wheel-<platform>`.
- `sdist`: unchanged.
- `test` (5 platforms × CPython 3.10 and 3.14 = 10 jobs), each on its own
  hardware (`ubuntu-24.04-arm` for aarch64):
  - On Windows, `core.autocrlf=false` is set before checkout, as in the
    `wheel` job. Without it, the published `win_amd64` wheel would carry CRLF
    `.py` files, whose hashes would then differ from Linux installs. The local
    Windows wheels were built from the LF clone: 46 `.py` files, none with
    CRLF.
  - The C ABI of `core/` is built with Rust 1.93.1 and `generic` as
    `librang_core.so`, `librang_core.dylib` or `rang_core.dll`.
  - `python tools/wheel/test.py <wheel> $RUNNER_TEMP/wheel-test --python
    <setup-python's interpreter> --ctypes-lib ...` runs import, smoke and the
    backend tests. PATH is stripped of every directory that holds cargo, and
    the absence is asserted. The `env -i` of the Linux job could not carry
    over: it drops `SYSTEMROOT` on Windows.
  - Logs and timings are uploaded as `test-logs-*`.
- `release` (tags `v*`, after wheel, sdist and test): as before. It now
  downloads only the `wheel-*` artifacts and `sdist`, so the test logs are not
  attached.
- `publish` (new; tags `v*`, after wheel, sdist and test): `environment:
  pypi`, `permissions: id-token: write`, a fresh download of the `wheel-*` artifacts and `sdist`
  (so the release job's `SHA256SUMS` is not uploaded), then
  `pypa/gh-action-pypi-publish@release/v1` with `packages-dir: dist/`.

Choices:

- **Per-architecture macOS jobs rather than universal2.** `RUSTFLAGS`
  carries one `target-cpu`, which cannot be right for both halves of a fat
  binary, and each wheel is then tested natively on its own architecture.
  `pip` prefers the thin wheel anyway.
- **`macos-15-intel`, not `macos-13`.** GitHub retired the macos-13 image on
  4 December 2025 (changelog 2025-09-19), so a job pinned to it never starts.
  `macos-15-intel` is the Intel replacement until the macOS 15 image retires
  (announced for autumn 2027). After that, x86_64 macOS wheels can only be
  cross-built from arm64 and tested under Rosetta.
- Wheel tags: expected from maturin's default deployment targets,
  `macosx_10_12_x86_64` and `macosx_11_0_arm64`; not built here.

**Not run on GitHub.** The workflow runs on push to main or on a pull
request after the merge. The macOS jobs in particular have never executed
anywhere. **The publish job cannot be exercised** until the user registers
the pending publisher on pypi.org and pushes a tag. The publisher needs:
owner `gijzelaerr`, repository `ra-ng`, workflow `wheels.yml`, environment
`pypi`, and the project name in `pyproject.toml` at the tag. That name is
`rangtoy` today; P12 renames it to `ra-ng`, so a tag before P12 would publish
under the old name. The GitHub environment `pypi` must exist, optionally
with required reviewers.

## 4. Local scripts without docker

- `tools/wheel/build.py OUT [--sdist] [--no-ctypes]` runs
  `maturin build --release --locked` through `uv tool run
  maturin==1.16.0` (falling back to `python -m maturin`).
  - It sets `RUSTUP_TOOLCHAIN=1.93.1`, the baseline `RUSTFLAGS` (`x86-64`,
    `apple-m1` on Apple silicon, `generic` on other aarch64) and
    `CARGO_TARGET_DIR=OUT/target`, which is removed afterwards.
  - It also builds core's C ABI library into `OUT/ctypes/` for the backend
    test.
  - It writes `build.log`, `timings.tsv`, `sha256.txt` and the source
    commit and status.
  - On Linux it produces a wheel tagged for the host glibc (here
    `manylinux_2_35`), so `build.sh` stays the way to make distributable
    Linux wheels.
- `tools/wheel/test.py WHEEL_OR_BUILD_DIR OUT [--python V] [--ctypes-lib P |
  --no-ctypes]` runs the same steps as the CI job.
  - It creates a fresh venv: `uv venv` from public PyPI when uv is present,
    else `python -m venv` and pip.
  - It installs `<wheel>[test,imaging]`.
  - Import, smoke and the backend tests then run without cargo on PATH.
  - With `--no-ctypes`, `tools/wheel/pytest_wheel.py` (new
    `RANG_WHEEL_NO_CTYPES=1`) makes the comparisons against ctypes skip
    with "no C ABI library", and only that skip is allowed.

| Run | Wall | Result |
| --- | ---: | --- |
| Windows `build.py ../wheel-win-01 --sdist` | 127.4 s (rustc 24.1 s, which includes rustup fetching the `1.93.1` name; wheel 63.4; sdist 4.8; ctypes 33.5) | `rangtoy-0.1.0-cp310-abi3-win_amd64.whl` 1,394,279 B, **which contained a stray `rangtoy/rang_core_py.pdb`** (1.36 MB) left in `python/rangtoy` by `maturin develop`, because maturin packs untracked files under `python-source` unless git ignores them |
| Windows `build.py ../wheel-win-02 --no-ctypes`, after the `.gitignore` fix | 64.9 s | 1,067,890 B, `_core.pyd` only (`7646737…`). MSVC binaries are not byte-reproducible between two builds (`603ef189…` against `7646737…`: 24 bytes differ, at offset 264–265, the PE header timestamp, and at 1,749,300–1,749,763, the debug directory with the PDB GUID; consistent with the MSVC linker's timestamp and GUID, which `/Brepro` would fix, not checked further) |
| Windows `test.py` on `wheel-win-01`, py3.10 / py3.14 / py3.14 `--no-ctypes` | 4.5 / 3.3 / 4.2 s | PASS: import, smoke (extension from site-packages, cargo absent; NumPy 2.2.6 and 2.5.4; first fused pass 1.1 ms), backend tests 10 passed and 1 skipped; `--no-ctypes`: 2 passed, 9 skipped |
| Windows `test.py` on `wheel-win-02`, py3.10 / py3.14, ctypes from `-01` | 4.6 / 3.1 s | PASS, 10 passed, 1 skipped |
| Windows `test.py` on `wheel-win-02`, py3.14, **uv removed from PATH** (the CI path: `python -m venv` and pip, `PIP_INDEX_URL` public PyPI) | 49.0 s (install 37.0 s) | PASS, 10 passed, 1 skipped |
| Linux (WSL) `build.py` | 271.7 s (wheel 139.3 s, ctypes 104.4 s, load about 50) | `…-manylinux_2_35_x86_64.whl` 1,214,601 B |
| Linux `test.py`, py3.10 / py3.14 / `--no-ctypes` | 5.9 / 7.5 / 6.0 s | PASS: 11 passed / 11 passed / 2 passed, 9 skipped |

Receipts: `outputs/x1-crossplatform-20261030-01/wheel-windows/` and
`wheel-linux-native/` (logs, timings and hashes; venvs deleted).

## 5. Portability inventory for P7, P9 and P12

Scope: `python/rangtoy`, `examples`, `tests`, `tools` (`history/` excluded,
since it is frozen). **There is no `shell=True` and no `os.fork` anywhere.**
Every `subprocess` call passes an argument list. Where one runs bash or a
POSIX tool, that is listed below. `multiprocessing`, `signal`, `fcntl`,
`pwd` and `os.getuid` are not used.

1. **`resource` (Windows has none).**
   - Live paths, at module level: `python/rangtoy/core_campaign.py:17`
     (:141) and `python/rangtoy/core_campaign_array.py:27` (:123).
   - Examples: `validate_core_phase2.py:15` (:321), `prototype_section6.py:15`
     (:268), `bench_p1_solver.py:29` (:225), `bench_p2_gridder.py:31` (:349,
     :395, :411, :434), `bench_p3_flags.py:25` (:47, :52),
     `fetch_luno_slice.py:11` (:42), `projector_scaling.py:11` (:72).
   - Replacement: one `rangtoy` helper `peak_rss_bytes()`. It uses
     `resource` on POSIX, multiplying by 1024 on Linux and by 1 on macOS
     (today every call site is wrong on macOS). On Windows it uses
     `psutil.Process().memory_info().peak_wset`, or `GetProcessMemoryInfo`
     through ctypes to avoid the dependency. Import lazily.
2. **`/proc`.**
   - `core_campaign_array.py:129` (`/proc/meminfo`) → `psutil.virtual_memory()`.
   - `bench_p1_solver.py:48`, `bench_p2_gridder.py:90`, `bench_p3_flags.py:56`,
     `bench_core_f.py:64` (`/proc/loadavg`) → `os.getloadavg()` on POSIX,
     `psutil.getloadavg()` on Windows, or `None` recorded.
3. **`/usr/bin/time`.** `examples/validate_core_phase2.py:387` wraps the cost
   subprocess in `/usr/bin/time -f "%e %M"`. Replacement: time the child
   with `time.perf_counter()`, and have the child report its own
   `peak_rss_bytes()` in its JSON (or use `psutil.Process(pid)` from the
   parent). `tools/wheel/test.sh` uses it too, but that is Linux-only by
   design.
4. **`/tmp` defaults.**
   - `flagging_next.py:97` (`NUMBA_CACHE_DIR` default `/tmp/numba`),
     `flagging_comparators.py:423` (`/tmp/tricolour-cache`),
     `flagging_caracal.py:179` (`/tmp/caracal-tricolour`) →
     `Path(tempfile.gettempdir()) / ...` or a directory under the run
     directory.
   - `flagging_imaging.py:371` passes `/tmp/rang-imaging-parser-only` and
     `/tmp` into a WSClean command for a parser-only check. That is a
     container path and can stay POSIX, but should be built with
     `PurePosixPath`.
5. **Container and POSIX command paths built with `Path`.**
   - `flagging_caracal.py:57` (`Path(interpreter).with_name("tricolour")`) →
     `PurePosixPath`. This is a real Windows test failure.
   - `flagging_imaging.py:344` (`/missing/wsclean` placeholder): harmless.
6. **`st_blocks`.** `flagging_equivariance.py:66`, `flagging_imaging.py:291` →
   the `getattr(..., "st_blocks", ceil(size/512))` fallback of
   `flagging_response.py:69`. These are real Windows test failures.
7. **Symlinks.**
   - The guards (`is_symlink()` in `flagging_response.py:66,78,116,548`,
     `flagging_imaging.py:289,309,619`, `flagging_influence.py:207,507`,
     `flagging_signal_guard.py:335`, `flagging_equivariance.py:196`,
     `flagging_next.py:95`, `examples/compare_core_backends.py:177`) are
     portable.
   - The tests that create links (`test_flagging_next.py:118`,
     `test_flagging_response.py:336,379`, `test_flagging_signal_guard.py:194`,
     `test_flagging_imaging.py:412`) need a skip-on-`OSError` fixture.
   - The checkout's own `outputs` symlink (worktree convention) is
     invisible to Windows. Use a directory junction (`mklink /J`) or an
     environment variable (`RANG_OUTPUTS`) that the drivers read instead of
     `ROOT / "outputs"`.
8. **bash and shell scripts.**
   - `tools/check-all.sh` (item 11), `tools/core-j-suite.sh`,
     `tools/wheel/build.sh`, `tools/wheel/build-inside.sh` and
     `tools/wheel/test.sh` (Linux and docker by design; keep),
     `tools/flagging/*.sh` (fetch helpers referenced by
     `examples/build_luno_ms.py`, `check_luno_sigma.py` and
     `extract_luno_support.py`).
   - `core-j-suite.sh` should become a Python driver list. That is P9's one
     CLI: the CLI already runs each step with `sys.executable` and an
     argument list.
9. **Path strings in hashes and receipts (the criterion 5 failure).**
   - `str(p.relative_to(...))` feeds digests or JSON keys in:
     `flagging_workflow.py:43`; `examples/run_core_flags.py:41`,
     `compare_core_flags.py:69`, `oracle_tricolour.py:53`; the key maps in
     `core_campaign.py:165,1099`, `core_campaign_array.py:1436`,
     `core_cli.py:69,367`, `core_imaging.py:365`, `flagging_equivariance.py:190`;
     and `examples/check_ms_reader.py:32`, `export_ms_arrays.py:36`,
     `oracle_ms_columns.py:54`, `prototype_section6.py:292`,
     `run_core_campaign.py:28`, `run_core_injections.py:22`,
     `survey_luno_support.py:22`, `validate_core_phase1.py:324,352`,
     `validate_core_phase2.py:459,503`.
   - Replacement: `.as_posix()`, sorting by the POSIX string. The output is
     identical on Linux, so archived hashes stay valid.
10. **Text encoding.**
    - `examples/pointing.py:167` prints `→` (a real failure on a cp1252
        console).
    - 189 `read_text()`, 106 `write_text(` and 48 `open(` calls have no
      `encoding=`. On Windows before Python 3.15 they read and write
      cp1252.
    - Replacement: `encoding="utf-8"` (ruff rule `PLW1514` can enforce it),
      or set `PYTHONUTF8=1` in the CLI entry points.
    - `write_text()` and text-mode `open()` on Windows also translate `\n` to
      `\r\n` (`newline=None`). This task tripped on it: a report edited by
      a Windows Python script was committed with CRLF in `1aed9a3` and
      converted back in the next commit. Use `newline="\n"` wherever a
      written file is hashed or committed.
    - `tests/test_core_imaging.py` is committed with CRLF line endings, the
      only text file in the index that is.
    - A `.gitattributes` with `* text=auto eol=lf` (plus `*.staticmask
      binary`, `*.png binary`) would make Windows checkouts byte-identical to
      Linux ones without per-clone configuration. That matters for every
      code hash in a receipt (`ROOT` file digests) and for `ruff format
      --check` and `git diff --check`.
11. **Other.**
    - `subprocess.run(["git", ...])` (`core_cli.py:78`, `core_imaging.py:374`,
      `core_campaign.py:174`, examples) and `["cargo", ...]` (`core.py:82,89`,
      `__init__.py:32,45`) are portable as argument lists (git and cargo are
      `.exe` on PATH).
    - `rangtoy.build()` and `core.build_core()` already name `rang-toy.exe`,
      `rang_toy.dll` and `rang_core.dll`.
    - The test `tests/test_ms_inspection.py:19` builds `ZipInfo("a\\b")`, which
      Windows rewrites; that needs a test-side fix only.

### Proposed `rang-core check` (replaces the body of `tools/check-all.sh`; design only, not implemented)

- **Module.** `python/rangtoy/check.py`, run as `python -m rangtoy.check`
  and exposed by P9's CLI as `rang-core check`.
  - It refuses to run outside a checkout. It finds the root by walking up
    from the working directory to a directory that holds `Cargo.toml`,
    `core/Cargo.toml` and `pyproject.toml`, so the installed wheel cannot
    run it by accident.
  - `tools/check-all.sh` shrinks to `exec .venv/bin/python -m rangtoy.check
    "$@"`; a two-line `tools/check-all.ps1` does the same with
    `.venv\Scripts\python.exe`.
- **Steps.** A table of `(name, argv, env)` with the same 17 steps as today:
  root and core build, test, clippy and fmt; ext-build, ext-clippy and
  ext-fmt; ruff; ruff-format; diff-check; pytest.
  - argv lists only, no shell.
  - Cargo gets `RUSTUP_TOOLCHAIN` (default `1.93`) instead of `+1.93`.
  - Python tools run as `sys.executable -m ruff`, `-m maturin develop
    --release --offline` and `-m pytest -q`.
  - Each step's output goes to a `tempfile.TemporaryDirectory`. On failure
    the log is printed, on success its last line, as today.
  - The `rust_test` helper's `grep "^test result"` becomes a Python regular
    expression.
- **Options.**
  - `--only` and `--skip` (step names), `--offline` (default on, as today),
    `--jobs N` (sets `CARGO_BUILD_JOBS` and `pytest -n` once P10 adds xdist).
  - `--json PATH` writes a receipt: every step's argv, wall time, peak RSS
    through the item 1 helper, exit status, toolchain versions, `git
    rev-parse HEAD` and `git status --porcelain`. The tool-timings rows
    come from that receipt instead of being copied by hand.
- **Portability.** Paths come from `pathlib`. The venv's tools are found as
  `Path(sys.executable).parent / ("ruff.exe" if os.name == "nt" else
  "ruff")`, or better through `-m`. `git diff --check` is unchanged, and on
  Windows it relies on the `.gitattributes` above. The exit status is
  non-zero when any step fails. The last line stays `## overall: PASS|FAIL`,
  so existing habits and logs still read the same.
- **maturin in a uv venv.** `ext-build` calls `maturin develop`, which
  needs pip in the venv. A venv made by `uv venv` (as the WSL memory note
  recommends) has none, so the step fails (first check-all run below). The
  entry point should pass `--uv` when `uv` is on PATH and the venv has no
  pip, or install with `uv pip install -e .` instead.
- **CI.** One job (Linux, Windows and macOS) runs `python -m rangtoy.check
  --skip ext-build` after `maturin develop`. That would make the plan's
  "checks run natively everywhere" testable.

## Changes outside the task's own files

- `.cargo/config.toml`: `[build] rustflags = [x86-64-v3]` is now
  `[target.'cfg(target_arch = "x86_64")'] rustflags = [...]`, with two comment
  lines.
  - Without this, a native build on Apple silicon or aarch64 Linux passes
    an x86 CPU name to rustc.
  - Verified on Windows: `cargo build -v` still shows
    `target-cpu=x86-64-v3` for every unit, and `RUSTFLAGS=-C
    target-cpu=x86-64` still overrides it.
- `.gitignore`: `/python/rangtoy/_core*.pyd` and `/python/rangtoy/*.pdb`
  (`maturin develop` on Windows). Without them, a later `maturin build`
  from the same checkout packs the stale `.pdb` into the wheel (measured
  above). The `.pyd` and `.pdb` are also simply clutter.
- No change to `Cargo.toml`, `core/Cargo.toml`, `core/py/Cargo.toml`,
  `pyproject.toml`, Rust sources or Python live paths. None were needed for
  the build.
  - `pyproject.toml`'s classifier `Operating System :: POSIX :: Linux`
    should become `Operating System :: OS Independent` (or list Windows
    and macOS) once the matrix is green. That is left to P12, which
    rewrites the metadata for the rename.

## Timings

| Date | Step | Wall | Notes |
| --- | --- | ---: | --- |
| 2026-10-30 | Windows: clone from WSL main repository | 21.2 s | CRLF by default; converted to LF |
| 2026-10-30 | Windows: `cargo +1.93 build --release --locked` core, cold | 56.3 s | includes the crate download |
| 2026-10-30 | Windows: `cargo +1.93 build --release --locked` root | 8.1 s | pdb collision warning |
| 2026-10-30 | Windows: `uv pip install -e ".[pointing,beam,test,imaging]" ruff maturin` | 83.7 s | includes the extension build |
| 2026-10-30 | Windows: `maturin develop --release`, warm | 2.1 s | after one failure (uv cache) |
| 2026-10-30 | Windows: `pytest tests/test_core_backends.py` | 52.1 s | 10 passed, 1 skipped; includes the cargo build of core |
| 2026-10-30 | Windows: full pytest | 414.5 s | 529 passed, 17 failed, 5 skipped, 3 collection errors |
| 2026-10-30 | WSL → `/mnt/c` copy of the task D inputs (585 MB) | 116.0 s | |
| 2026-10-30 | Windows: task D port run / comparator | 2.8 s / 1.1 s | criteria 1–4 pass, 5 fails as frozen (path separators) |
| 2026-10-30 | WSL: task D port run / comparator, same commit | 6.5 s / 2.1 s | all pass; load about 50 |
| 2026-10-30 | Windows: `tools/wheel/build.py --sdist` | 127.4 s | |
| 2026-10-30 | Windows: `tools/wheel/build.py --no-ctypes` | 64.9 s | |
| 2026-10-30 | Windows: `tools/wheel/test.py`, per Python version | 3.1–4.6 s | 15.8 s on the first run (cold uv cache) |
| 2026-10-30 | WSL: `tools/wheel/build.py` | 271.7 s | load about 50 |
| 2026-10-30 | WSL: `tools/wheel/test.py`, per run | 5.9–7.5 s | |
| 2026-10-30 | actionlint with shellcheck | 11.7 s | 0 errors |
| 2026-10-30 | WSL: `uv venv` + editable install for check-all | 89.3 s | |
| 2026-10-30 | WSL: `bash tools/check-all.sh`, first run, started before the coordinator's lock rule and without it | 4,709 s (78 min 29 s; pytest 4,350 s) | overall FAIL on `ext-build` only: `maturin develop` found no pip in the uv-created venv ("if working with a uv venv try `maturin develop --uv`"); every other step passed: root 19 and core 55 Rust tests, clippy, fmt, ruff, ruff format, diff-check, **570 passed, 1 skipped**; load 50-96 from five concurrent check-all runs. Fix of the environment, not the tree: `uv pip install pip` into `.venv` |
| 2026-10-30 | WSL: `flock /home/gijsm/.rang-checkall.lock bash tools/check-all.sh` (coordinator's load rule), `OPENBLAS_NUM_THREADS=1 RAYON_NUM_THREADS=4`, after pip was added to `.venv` | lock wait 1,803 s (requested 13:25:24, acquired 13:55:27, load 80 then 22); run 229.3 s (pytest 153.6 s) | **overall PASS**: root 19 and core 55 Rust tests, clippy, fmt, `ext-build`, ruff, ruff format, diff-check, 570 passed and 1 skipped; the first run's FAIL was the venv. Logs in `outputs/x1-crossplatform-20261030-01/check-all/` |

## Upstream observations (not RATT)

- **cargo**: the lib and bin of one package with the same crate name
  (`rang_toy` and `rang-toy`) collide on `rang_toy.pdb` under MSVC (cargo
  issue #6313, open for years). It only matters for debugging. A `[[bin]]
  name` that differs after `-`/`_` normalisation (for example
  `rang-toy-cli`) avoids it. That is P12's call, since it renames anyway.
- **maturin**: `maturin develop` on Windows leaves the `.pdb` next to the
  `.pyd` in `python-source`, and a later `maturin build` packs any
  untracked file there that git does not ignore. Arguably maturin should
  exclude `*.pdb` by default or warn. Worth an issue on PyO3/maturin, after
  checking the latest release; not filed.
- **maturin and uv**: when uv is present, `maturin develop` inspects the
  interpreter through uv, so a broken uv cache fails the build with a uv
  error ("too many temporary files"). The cause is local to this host; not
  an upstream bug as such.
- **PyO3 0.30 / abi3 on Windows**: no issue. maturin generated the Windows
  import library itself ("Not using a specific python interpreter
  (automatically generating windows import library)"), and the abi3 `.pyd`
  imports on 3.10 and 3.14.
- **RATT and caracal-pipeline**: none of the RATT stack (Tricolour,
  QuartiCal, CARACAL, stimela, python-casacore wheels) runs natively on
  Windows. python-casacore has no Windows wheels, which is why the casacore
  paths stay Linux and container only. The Rust ports (task D Tricolour,
  task E MS reader) are what make the Windows path possible at all. Not an
  upstream issue to file; recorded as a constraint.

## For the coordinator

- **STATE.md paragraph**: "Cross-platform (big plan X1), 2026-10-30
  (implemented; measured on native Windows and Linux; CI not yet run). The
  core, the root crate and the PyO3 extension build natively on Windows with
  Rust 1.93.1 (MSVC) and maturin with no source change, and the extension
  `.pyd` exports the C ABI. The backend tests pass on Windows (10 passed, 1
  skipped). Of the full suite, 529 tests pass on Windows, 17 fail and 3
  modules do not collect, all from POSIX assumptions (`resource`,
  `st_blocks`, symlinks, path separators, console encoding), listed for
  P7/P9/P12 in [x1-crossplatform.md](x1-crossplatform.md). The task D
  Tricolour comparator ran natively on Windows on the archived inputs:
  criteria 1–4 exact, and all 56 arrays byte-identical to Linux. Criterion 5
  fails as frozen only because the receipt hashes `str()` paths with
  backslashes; with POSIX path strings the input hashes equal the archive.
  `wheels.yml` now builds and tests manylinux x86_64 and aarch64, macOS arm64
  and x86_64, and win_amd64 wheels with cargo absent, and publishes to PyPI by
  trusted publishing on `v*` tags (user: register the pending publisher;
  the project name at the tag is still `rangtoy` until P12). New
  `tools/wheel/build.py` and `test.py` build and test the native wheel
  without docker."
- **tool-timings.md**: the rows of the timing table above.
- **Files changed outside the task's own**: `.cargo/config.toml` (x86_64
  scope) and `.gitignore` (two lines); details above.
- **Suggested follow-ups**:
  - a `.gitattributes` (LF; binary masks and PNGs);
  - fix criterion 5's hash portability in the examples' hashing helpers
    with `as_posix()`, which leaves archived Linux hashes unchanged;
  - the `peak_rss_bytes()` helper (item 1) before P9's CLI, because
    `core_campaign` is imported by the CLI and by `test_p3_flags`;
  - `rang-core check` as designed above;
  - after the first green CI run, change the `Operating System`
    classifier.
- **Merge order**: this branch touches `wheels.yml`, `tools/wheel/` and
  `.cargo/config.toml`. P7, P9 and P12 may touch `pyproject.toml` and the
  CLI. No overlap is expected, except that P12 must update the workflow's
  publish comment (project name) and `tools/wheel` scripts that name
  `rangtoy`.

## Open items

- First CI run on GitHub (after the merge): the macOS jobs, the Windows wheel
  built by maturin-action, and `test.py` under `setup-python` with pip
  instead of uv.
- PyPI: register the pending publisher (user), create the `pypi`
  environment, and tag after P12.
- macOS was not tested locally (no Mac). The `ru_maxrss` unit difference
  (item 1) will show up there first.
- WSL stays the data host for the LUNO runs. This task reproduced one archive
  (task D) natively on Windows, which the cross-platform rule names as the
  condition for leaving WSL. The LUNO drivers themselves still need item 1
  (`resource`) and item 7 (`outputs` symlink) first.
