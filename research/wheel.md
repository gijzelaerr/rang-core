# Distributable wheel (big plan task W1)

Status, 2026-10-30: **implemented; measured locally.** An abi3-py310
`manylinux_2_28_x86_64` wheel builds in the pinned manylinux container,
passes `auditwheel`, installs from public PyPI into fresh uv venvs on CPython
3.10–3.14, picks the extension backend with no cargo on `PATH`, passes
`tests/test_core_backends.py` against an independently built C ABI, and
reproduces task J's extension archive run through every driver (task I's
imaging replay included) with zero differences beyond run-path strings on the
NumPy release task J used. An aarch64 wheel cross-builds with zig and passes
`auditwheel show`, but was **not executed** (no arm64 emulation on the host).
The CI workflow is written and lints clean but **has not run on GitHub**
(nothing pushed), so the plan's "CI green on the branch" is not met yet.
Nothing was published. A packaging task under AGENTS.md, not a scientific
contribution; no archived result changed.

Row W1 of [big-plan.md](big-plan.md); the "CI, container update" half that
[core-j-packaging.md](core-j-packaging.md) left open (its wheel was tagged
`manylinux_2_35` from the host glibc and never checked by auditwheel).

## What was built

`tools/wheel/build.sh OUT [x86_64|aarch64]` (inner script
`tools/wheel/build-inside.sh`) runs everything in
`quay.io/pypa/manylinux_2_28_x86_64@sha256:e0adf185…88a3` (pulled
2026-10-30, image created 2026-10-26; glibc 2.28, auditwheel 6.8.2) as the
host user, with the checkout mounted **read-only** (and the main
repository's git directory, read-only, so a worktree's sdist can list files),
Rust 1.93.1 by rustup (minimal profile, the toolchain of `tools/check-all.sh`),
maturin 1.16.0 from public PyPI, `cargo --locked` throughout, the cargo
target directory in `OUT/target` (removed afterwards) and rustup/cargo/pip
caches in `~/Build/cache/rang-wheel`, and `RUSTFLAGS="-C target-cpu=x86-64"`
(aarch64: `-C target-cpu=generic`). The environment variable overrides any
`rustflags` from a `.cargo/config.toml`: main is gaining a repo-level config
with `target-cpu=x86-64-v3` for local builds, and distributable wheels must
not carry v3 instructions. The CI workflow sets the same per target. With
the explicit baseline the x86_64 `_core.abi3.so` is byte-identical to the
earlier builds without it (`0afb751c…`, build `-11`) and the aarch64 one too
(`947dc07d…`, build `-11-aarch64`), as expected, since the baseline is each
target's default. Steps:

1. `maturin build --release --locked --manylinux 2_28 -i /opt/python/cp310-cp310/bin/python`
   (one interpreter suffices for abi3; maturin applies its own manylinux
   policy check);
2. `maturin sdist`;
3. `auditwheel show`, then `auditwheel repair --plat manylinux_2_28_x86_64`
   into a separate directory;
4. the C ABI of `core/` (`librang_core.so`) and the root crate's library
   (`librang_toy.so`) from the same commit and toolchain, for the tests below;
5. the sdist unpacked and built again with maturin from its own
   `pyproject.toml`.

Results (`outputs/wheel-20261030-06`, the build every test below used; source
`df42ea0` plus this branch's uncommitted `pyproject.toml` and `tools/wheel`):

| File | Size | SHA256 |
| --- | ---: | --- |
| `rangtoy-0.1.0-cp310-abi3-manylinux_2_28_x86_64.whl` | 820,593 B | `b5ce3ea9…c4c9e5` |
| `rangtoy/_core.abi3.so` inside it | 1,306,224 B | `0afb751c…4b30` |
| `rangtoy-0.1.0.tar.gz` (sdist, 461 files) | 2,131,099 B | `f213dec7…cd4cf9` |
| `rangtoy-0.1.0-cp310-abi3-manylinux_2_28_aarch64.whl` (`outputs/wheel-20261030-08-aarch64`) | 733,939 B | `b22e95f6…cea9a`; `.so` `947dc07d…6547` |

- **auditwheel show** (x86_64): "consistent with the following platform tag:
  manylinux_2_28_x86_64"; external versioned symbols only from
  system libraries: `libgcc_s.so.1` (GCC_3.0, GCC_3.3, GCC_4.2.0),
  `libpthread.so.0` and `libm.so.6` (GLIBC_2.2.5), `libc.so.6` (up to
  GLIBC_2.28). Nothing is grafted: `auditwheel repair` reports "No filename
  tags change needed" and writes an identical tag; the wheel holds exactly
  one shared object, `rangtoy/_core.abi3.so`, and nothing from the host.
- **aarch64 auditwheel show**: consistent with `manylinux_2_28_aarch64`;
  libc up to GLIBC_2.28, `libm`, `libpthread`, `libdl` at GLIBC_2.17.
- **Contents** (58 entries): the `rangtoy` package, entry point `rang-core`,
  `LICENSE`, and maturin's CycloneDX SBOM of the crate graph.
- **Reproducibility**: two clean builds (`-02`, `-03`) give a byte-identical
  `_core.abi3.so` and sdist; the wheel archives differ only in the SBOM's
  serial number/timestamp. The `.so` embeds absolute source paths (38 strings
  such as `/home/gijsm/Worktrees/rang/wheel/core/src/ms.rs`, from panic
  locations), so the wheel built from the sdist (`ceb44f5a…`) differs from the
  one built from the checkout; `RUSTFLAGS=--remap-path-prefix=…` would remove
  both the paths and the difference (not done).
- **sdist**: builds a working wheel on its own (step 5), but carries 461
  files (research notes, recipes, tests, examples) because the root crate
  `rang-toy` sits at the repository root and cargo packages its directory.
  Harmless; an `exclude` list in `[tool.maturin]` would trim it.

## Defect found and fixed: NumPy missing from the metadata

The first build (`outputs/wheel-20261030-01`, pyproject of `df42ea0`) had no
`[project] dependencies`. A bare `uv pip install` of that wheel into a fresh
3.10 venv imports `rangtoy._core` (the extension loads NumPy lazily) but
`import rangtoy.core` fails with `ModuleNotFoundError: No module named
'numpy'`. `dependencies = ["numpy>=1.26"]` fixes it; the "bare" step below
checks it on every interpreter.

## Tests on clean interpreters

`tools/wheel/test.sh outputs/wheel-20261030-06 outputs/wheel-20261030-09`
with `SUITE_ALL=1` (1,585 s wall; host load 15–22 from three sibling agents
throughout). Per version, uv-managed CPython (`--python-preference
only-managed`), public PyPI only:

1. **bare**: fresh venv, `uv pip install <wheel>` alone, then in a clean
   environment (`env -i HOME PATH=/usr/bin:/bin`, so no `~/.cargo/bin`)
   `python -I -c "import rangtoy._core, rangtoy.core"`, printing the backend.
2. **install**: a second fresh venv with `<wheel>[test,imaging]`.
3. **nocargo**: `tools/wheel/smoke.py` from outside the checkout with cargo
   absent (asserted): rangtoy and the extension come from site-packages,
   `backend_name() == "extension"` with neither `RANG_CORE_BACKEND` nor
   `RANG_CORE_LIB` set, one fused pass runs; prints import times and the
   extension's SHA256.
4. **pytest**: `tests/test_core_backends.py` from the source tree against the
   installed wheel, cargo absent, through the plugin
   `tools/wheel/pytest_wheel.py`, which fails the session unless `rangtoy`
   and `rangtoy._core` import from site-packages (`-o pythonpath=` clears
   pyproject's `pythonpath = ["python"]`, which would otherwise import the
   source tree), and points `core.build_core` at the container-built
   `librang_core.so`: the ctypes half of the test otherwise builds `core/`
   next to the package, a directory that does not exist in site-packages.
   So the comparison is the wheel's extension against an independently
   linked C ABI from the same commit and toolchain. Any skip other than the
   fixture-MS one fails the step; none occurred.
5. **suite**: every driver and comparator of `tools/core-j-suite.sh` through
   `tools/wheel/run_installed.py` (imports rangtoy from the wheel first and
   checks before and after the driver that the extension from site-packages
   is the active backend), cargo absent, then
   `examples/compare_core_backends.py outputs/core-j-20261029-02-extension
   <suite>` file by file, and `tools/wheel/classify_compare.py` on its
   receipt (`compare-classes.json`).

**Reading `test.sh`'s verdict.** The raw comparator always exits 1 here,
because it differs from task J's run in run-path strings (below); since
the final scripts its status is recorded but not gated, and the gate is
`classify_compare.py`, which fails only on missing files or differences it
cannot explain (path strings, version strings, the section 6 cost flags and
float leaves are classified, floats reported with their relative size).
The section 6 checker's cost criterion (2.0 s excluding decode) still fails
its step on a loaded host, so on a busy machine `test.sh` ends in `overall:
FAIL` even when everything else passes: read `timings.tsv` and each
`section6-check` result before concluding anything. In run `-09` (before
the classifier existed) the "compare" rows are FAIL for the path strings
alone; the classification below was produced afterwards by the same script
on its receipts.

| Python | NumPy | bare install / import | install with extras | import `rangtoy.core` | first fused pass | backend tests | suite gated criteria | comparator against task J |
| --- | --- | --- | --- | ---: | ---: | --- | --- | --- |
| 3.10.22 | 2.2.6 | 0.38 s / pass | 1.05 s | 18 ms | 0.39 ms | 11 passed | all pass (section 6 cost fails under load) | 165 numeric leaves differ at round-off, 25 path strings |
| 3.11.17 | 2.4.6 | 0.86 s / pass | 1.20 s | 18 ms | 0.41 ms | 11 passed | all pass (section 6 cost fails under load) | 157 numeric leaves at round-off, 25 path strings |
| 3.12.15 | 2.5.4 | 0.31 s / pass | 0.28 s | 9 ms | 0.33 ms | 11 passed | all pass (section 6 cost fails under load) | **0 numeric**, 25 path strings |
| 3.13.16 | 2.5.4 | 0.52 s / pass | 0.69 s | 7 ms | 0.33 ms | 11 passed | all pass, cost included | **0 numeric**, 25 path strings |
| 3.14.8 | 2.5.4 | 0.08 s / pass | 0.12 s | 8 ms | 0.31 ms | 11 passed | all pass, cost included | **0 numeric**, 25 path strings |

Install times are with a warm uv cache (the first run, `-04`, took 3.1 s
for the bare 3.10 install); NumPy itself takes 0.16–0.32 s to import. The
extension's SHA256 is `0afb751c…4b30` in every venv. "Import" is
`import rangtoy._core` plus `from rangtoy import core` after NumPy.

**Suite details.** On every version: phase 2 validator all eleven checks;
section 6 criteria 1–7 and 9–11 (criterion 8, 2.0 s excluding decode, failed
on 3.10–3.12 at 4.27, 4.00 and 2.60 s while the siblings held the load at
15–22; it passed on 3.13 and 3.14 at 1.52 and 1.90 s; task J's reference run
failed it too, on a cold cache. Attributed to the sibling load, not
re-measured on an idle host: 3.12 has the same NumPy as 3.13 and 3.14 and
still failed); actions 0 failures (61 exact, 102 floats, 24 differences); task B
criteria 1–5; task C criteria 1–3 and the pixel comparator; task D criteria
1–5 and flags equal on all four controls; task E criteria 1–3 on 15 tables;
**task I** both comparisons pass with 0 failures (532 exact; PSF 8.9e-8,
responses 1.3e-7), inputs and `git status` unchanged.

**Comparator.** 90 files, 4,162–4,331 JSON leaves, 58 `.npz` arrays and 60
FITS HDUs per version; every array and every FITS image equal on every
version. The remaining differences, classified by
`tools/wheel/classify_compare.py` in
`outputs/wheel-20261030-09/py<version>/compare-classes.json` (3.10: 165
numbers, 25 path strings, 3 version strings, 1 worst-leaf label, 1 missing;
3.11: 157, 25, 3, 1, 1; 3.12: 25 path strings, 1 missing; 3.13 and 3.14: 25
path strings, 2 cost flags, 1 missing):

- 25 path strings per version: task J ran with the drivers' default,
  checkout-absolute archive paths in another worktree
  (`/home/gijsm/Worktrees/rang/core-j-packaging/outputs/…`), this run with
  relative `outputs/…` paths and `ROOT` pointed at this worktree; the run
  directory names in `inputs`, `core_run`, `result`.
- one file only in the reference, `section6-warm-check/result.json` (task
  J's labelled warm repeat; the ignore list in `test.sh` now names it).
- on 3.13 and 3.14, `all_passed`/`8_cost` of the section 6 checker: true
  here, false in task J's cold-cache run.
- on 3.10 and 3.11 only, 157–165 float leaves (TV values, action scores,
  fitted coefficients of order 1e-17, comparator statistics; 15 of them
  above 1e-9 relative) that differ in the last bits, plus the name of one
  comparator class's worst leaf, which moves with them; the largest
  relative difference among physical quantities
  is about 1e-15, and the four with relative difference near 1 are
  round-off-sized values (1.9e-16 against 0, 7e-34 against 3e-33). These
  follow the **NumPy release**, not the interpreter or the wheel: NumPy 2.5
  needs Python ≥ 3.12, so 3.10 resolves 2.2.6 and 3.11 2.4.6, while task J
  and 3.12–3.14 have 2.5.4. Check (`outputs/wheel-20261030-10-numpy`): 3.12
  with `numpy==2.4.6` and the same wheel gives the phase 2 fixture's
  `polar_rel` 0.0 like 3.11, where 3.12 with 2.5.4 gives J's 1.88e-16.

**Repeat with the committed scripts (`-12`).** `bash tools/wheel/test.sh
outputs/wheel-20261030-11 outputs/wheel-20261030-12` (suite on 3.10 and
3.14, 435 s, load 5–16): bare install, import, nocargo and the 11 backend
tests pass on all five versions; every gated driver criterion passes on
3.10 and 3.14 except section 6 criterion 8 (2.08 and 2.48 s against 2.0 s);
`classify_compare.py` passes on both (3.14: 25 path strings and nothing
else; 3.10: 25 path strings, 165 NumPy-release numbers, 3 version strings,
1 worst-leaf label). `test.sh` therefore ends `overall: FAIL` on the cost
criterion alone.

**What the wheel does not carry (needed by drivers, recorded, not fixed).**
The wheel is the core and the Python package; three things the drivers need
live only in the checkout. `test.sh` supplies them explicitly per step and
says so; the code and kernels exercised are still the wheel's:

1. The root crate's kernels (`librang_toy.so`: `rang_gain_tv`, the
   projector), loaded by `rangtoy.projector` through `rangtoy.build()`
   (cargo in the checkout) unless `RANG_TOY_LIB` is set. Phase 2, section 6
   and actions call `flagging.gain_tv`, so they get `RANG_TOY_LIB` pointing
   at the container-built library.
2. The Tricolour static masks, found as `core.core_root() / "data"` by
   `core_flag` (task D), and the `ROOT = Path(__file__).parents[2]` constants
   of `core_imaging`, `core_campaign` and `core_cli` (default archive paths,
   the oracle path, `git status` cwd, code hashes). With
   `RANG_WHEEL_CHECKOUT` set, `run_installed.py` rewrites those module-level
   paths to the checkout (it prints each one) for actions, D and I; task I
   also gets its archive and export paths as arguments.
3. `examples/prototype_section6.py` calls `core.library()` (the ctypes
   handle) before timing even when the extension is active, which builds
   `core/` with cargo. Section 6 runs with `RANG_CORE_BACKEND=extension`
   (extension stays active) and `RANG_CORE_LIB` set to the wheel's own
   `_core.abi3.so`, which exports the C ABI (task J).

Without these, run `-05` showed the failures: phase 2, section 6 and actions
`RuntimeError: Run from the Rang checkout, or pass a binary / set
RANG_TOY_BIN`; D `Run from the Rang checkout or set RANG_CORE_LIB`
(`core_root`); I `archived imaging run required:
…/site-packages/../outputs/tv-next-imaging-wsl-20261029-01`. A user who
installs the wheel gets the full core API (`rangtoy.core`, `core_zarr`,
`core_weights`, `core_grid`, `core_flag` minus the static masks, `core_ms`)
without Rust; the flagging TV kernels and the archive drivers still need
the checkout.

## aarch64

`bash tools/wheel/build.sh outputs/wheel-20261030-08-aarch64 aarch64`: the
same container, `rustup target add aarch64-unknown-linux-gnu`, `ziglang`
0.13.0 from PyPI, `maturin build --release --locked --zig --target
aarch64-unknown-linux-gnu --manylinux 2_28`. The first attempt failed in
26 s ("Failed to find zig": maturin runs `python3 -m ziglang` with the first
`python3` on `PATH`, the image's, which lacks it); with the tools venv first
on `PATH` it built in 23.2 s (wheel step 11.4 s). `auditwheel show`
(x86_64 container, reading the aarch64 ELF) reports `manylinux_2_28_aarch64`.
**Not executed**: the host has no arm64 binfmt handler and registering one
(`tonistiigi/binfmt`) changes host kernel settings, so it was not done. CI
runs the aarch64 wheel's tests natively on `ubuntu-24.04-arm`. About 10
minutes of the hour's time box were used.

## CI: `.github/workflows/wheels.yml`

On push to `main`, tags `v*`, pull requests touching the build inputs, and
manual dispatch:

- `wheel` (matrix x86_64, aarch64): `PyO3/maturin-action@v1`,
  `manylinux: 2_28`, `rust-toolchain: 1.93.1`, `maturin-version: v1.16.0`,
  `--release --locked`, job environment `RUSTFLAGS="-C target-cpu=x86-64"`
  (aarch64: `generic`), which maturin-action passes into its container;
  artifact `wheel-<target>`. (maturin-action cross-compiles aarch64 in its
  own manylinux cross image, not with zig.)
- `sdist`: maturin-action `sdist`; artifact `sdist`.
- `test` (x86_64 on `ubuntu-24.04`, aarch64 on `ubuntu-24.04-arm`; Python
  3.10 and 3.14): installs rustup if the runner image lacks it, builds
  `librang_core.so` with Rust 1.93.1 and `-C target-cpu=generic`, installs the
  wheel with `[test,imaging]` into a fresh venv, asserts cargo is absent in
  a clean environment, runs `import rangtoy._core` and `tools/wheel/smoke.py`
  from outside the checkout, and `tests/test_core_backends.py` through
  `tools/wheel/pytest_wheel.py` (same skip gate as `test.sh`). The archive
  suite cannot run in CI: the archives are ignored `outputs/`.
- `release` (tags `v*` only, after all three): downloads every artifact,
  writes `SHA256SUMS` and runs `gh release create "$GITHUB_REF_NAME" dist/*
  --verify-tag` with `contents: write`.

Validated with `actionlint` 1.7.12 (`uv tool run --from actionlint-py`, with
`shellcheck-py` so the `run:` blocks are shellchecked): 0 errors.
`shellcheck` on `tools/wheel/*.sh`: clean. **Not run on GitHub**: nothing
was pushed and no tag or release was created.

## User item: publish

Not executed. After a tag `vX.Y.Z` (with `version` in `pyproject.toml` bumped
to match) has run the workflow green, download the release files and upload
them with a PyPI API token for the `rangtoy` project (the name was not
checked for availability on PyPI):

```sh
gh release download vX.Y.Z --repo gijzelaerr/rang --dir dist --pattern '*.whl' --pattern '*.tar.gz'
uv tool run --index-url https://pypi.org/simple twine check dist/*
uv tool run --index-url https://pypi.org/simple twine upload dist/*   # asks for __token__ / pypi-…
```

or, from a local build directory, `maturin upload --skip-existing
outputs/wheel-<date>-NN/dist/*`. A trusted-publishing job (`pypa/gh-action-pypi-publish`
with `id-token: write`) could be added to the `release` job once the PyPI
project exists.

## Files

- `tools/wheel/build.sh`, `tools/wheel/build-inside.sh`: step 2 above.
- `tools/wheel/test.sh`: the per-version tests; `SUITE_ALL=1` runs the
  archive suite on every version (default: 3.10 and 3.14).
- `tools/wheel/smoke.py`, `tools/wheel/pytest_wheel.py`,
  `tools/wheel/run_installed.py`, `tools/wheel/classify_compare.py`:
  helpers described above.
- `.github/workflows/wheels.yml`.
- `pyproject.toml` (metadata only; the list is under "For the coordinator").

Receipts (ignored `outputs/`): builds `wheel-20261030-01` (pre-metadata),
`-02`/`-03` (reproducibility pair), `-06` (tested in `-09`),
`-08-aarch64`, and `-11`/`-11-aarch64` (the committed scripts, with the
explicit `RUSTFLAGS`); tests `-04`, `-05`, `-07` (iterations whose failures
are described above), `-09` (the run reported in the table), `-10-numpy`
(the NumPy attribution check) and `-12` (the committed scripts on build
`-11`, see below). Each directory holds its driver log (`build-driver.log`
or `test.log`, copied from the scratch logs, which were then deleted;
`-12/check-all-first.log` is the first check-all run); the test venvs were deleted
afterwards; logs, freezes and results remain.

## Commands of the ad hoc checks

```sh
# bare install of the pre-metadata wheel (NumPy defect), in ~/Build/tmp
uv venv -q --python-preference only-managed -p 3.10 $d
uv pip install -q --python $d/bin/python --index-url https://pypi.org/simple outputs/wheel-20261030-01/dist/*.whl
cd /tmp && env -i HOME=$HOME PATH=/usr/bin:/bin $d/bin/python -I -c "import rangtoy._core; print('_core ok'); import rangtoy.core"
# NumPy attribution (outputs/wheel-20261030-10-numpy)
uv venv -q --python-preference only-managed -p 3.12 $o/venv312-np246
uv pip install -q --python $o/venv312-np246/bin/python --index-url https://pypi.org/simple outputs/wheel-20261030-06/dist/*.whl numpy==2.4.6
env -i HOME=$HOME PATH=/usr/bin:/bin LANG=C.UTF-8 RANG_TOY_LIB=$PWD/outputs/wheel-20261030-06/ctypes/librang_toy.so \
  $o/venv312-np246/bin/python tools/wheel/run_installed.py examples/validate_core_phase2.py $o/phase2
# aarch64 policy check, x86_64 container reading the aarch64 wheel
docker run --rm -v $PWD:/w:ro quay.io/pypa/manylinux_2_28_x86_64@sha256:e0adf185… \
  auditwheel show /w/dist/rangtoy-0.1.0-cp310-abi3-manylinux_2_28_aarch64.whl
# embedded source paths in the x86_64 extension
python3 -m zipfile -e outputs/wheel-20261030-06/dist/*.whl /tmp/w6
strings /tmp/w6/rangtoy/_core.abi3.so | grep -c "/home/gijsm\|/cache/cargo"   # 38
# workflow and script lint
uv tool run --index-url https://pypi.org/simple --from actionlint-py --with shellcheck-py actionlint .github/workflows/wheels.yml
uv tool run --index-url https://pypi.org/simple --from shellcheck-py shellcheck tools/wheel/*.sh
```

## Timings

| Date | Step | Wall | Peak RSS | Notes |
| --- | --- | ---: | ---: | --- |
| 2026-10-30 | `docker pull quay.io/pypa/manylinux_2_28_x86_64` | 115.8 s | – | 1.75 GB image |
| 2026-10-30 | `uv python install 3.10 3.11 3.12 3.13 3.14` | 46.1 s | – | 3.13 already present |
| 2026-10-30 | `tools/wheel/build.sh` x86_64, cold (rustup download 23.5 s, wheel 10.8 s) | 43.4 s | 32 MB (host side) | `-01` |
| 2026-10-30 | `tools/wheel/build.sh` x86_64, warm caches (wheel 7.5–10.5 s, sdist 0.2 s, repair 0.7–1.1 s, C ABI 1.4–2.3 s, root lib 0.9 s, wheel from sdist 7.5–11.4 s) | 23.0–34.6 s | – | `-02`, `-03`, `-06`; load up to 17 |
| 2026-10-30 | `tools/wheel/build.sh` aarch64 by zig, failed (zig not found) and succeeded | 26.4 s, 23.2 s | – | `-08-aarch64` |
| 2026-10-30 | `tools/wheel/test.sh` 5 versions, archive suite on 3.10 and 3.14 | 138 s, 273 s, 475 s | 262 MB | `-04`, `-05`, `-07` (iterations) |
| 2026-10-30 | `SUITE_ALL=1 tools/wheel/test.sh` 5 versions, full archive suite on each | 1,585 s | 442 MB (section 6 checker) | `-09`; load 15–22; task C 79–185 s and task I 56–178 s per version against 52–54 s in task J on an idle host |
| 2026-10-30 | `tools/wheel/build.sh` x86_64 and aarch64 with the committed scripts and explicit `RUSTFLAGS` | 35.2 s, about 25 s | – | `-11`, `-11-aarch64`; same `.so` hashes as before |
| 2026-10-30 | `tools/wheel/test.sh` 5 versions, suite on 3.10 and 3.14, with the classifier | 435.4 s | 439 MB (section 6 checker) | `-12`; load 5–16; overall FAIL on section 6 cost only |
| 2026-10-30 | `uv venv` + editable install `.[pointing,beam,test,imaging] ruff maturin` (worktree `.venv`) | 24.3 s | – | for check-all |
| 2026-10-30 | `actionlint` (first `uv tool run`, includes download) | 4.9 s | – | 0 errors |
| 2026-10-30 | `bash tools/check-all.sh` before the second commit (classifier, `RUSTFLAGS`) | 387.9 s (user 4,662 s) | 1.69 GB | overall PASS, 739 pytest passed in 380 s; `outputs/wheel-20261030-13-check-all` |
| 2026-10-30 | `bash tools/check-all.sh`, `CARGO_BUILD_JOBS=8`, before the first commit (this file still being written) | 901.7 s (user 6,711 s) | 1.77 GB | overall PASS: root 19 and core 47 Rust tests, clippy, fmt, `ext-build`, ruff, 739 pytest passed in 860 s; load 16–27 from the siblings (80 s on an idle host in task J) |

## For the coordinator

- **README.md** (install section, after "`pip install -e .` builds the core's
  PyO3 extension…"): add a "Without Rust" paragraph: a released wheel
  installs the core with no compiler, `pip install rangtoy-<v>-cp310-abi3-manylinux_2_28_x86_64.whl`
  (or `pip install rangtoy` once published; Linux x86_64 and aarch64, glibc
  ≥ 2.28, CPython ≥ 3.10, one abi3 binary for every version), and that the
  wheel covers `rangtoy.core` and the core wrappers only: the flagging TV
  kernels (`RANG_TOY_LIB`), the Tricolour static masks and the archive
  drivers still need the checkout and cargo. Building wheels locally:
  `bash tools/wheel/build.sh outputs/wheel-<date>-NN` (docker), testing:
  `bash tools/wheel/test.sh outputs/wheel-<date>-NN outputs/wheel-<date>-MM`.
- **CONTRIBUTING.md**: the same two commands under the local checks as an
  optional packaging check; note `pytest` of the source tree tests the
  editable build, and `tools/wheel/test.sh` the installed wheel.
- **STATE.md paragraph**: "Wheel (big plan W1), 2026-10-30 (implemented;
  measured locally; CI not yet run). `rangtoy-0.1.0-cp310-abi3-manylinux_2_28_x86_64.whl`
  (821 kB, built in the pinned manylinux_2_28 container with Rust 1.93.1 and
  maturin 1.16.0, auditwheel-clean, nothing grafted) installs from public
  PyPI on clean CPython 3.10–3.14 and runs the extension backend with no
  cargo; backend tests pass and task J's archive run reproduces through the
  wheel (task I included) with arrays and images identical on every version
  and JSON leaves identical on NumPy 2.5 (last-bit differences on 3.10/3.11
  follow their older NumPy). aarch64 cross-builds by zig but was not run.
  NumPy is now a declared dependency (a bare install was broken). The wheel
  does not carry the root crate's TV kernel, the Tricolour static masks or
  the archive drivers' checkout paths. Publication is a user item
  ([wheel.md](wheel.md))."
- **tool-timings.md**: the rows of the timing table above.
- **pyproject.toml, every line changed** (metadata and maturin only):
  - `requires = ["maturin>=1.7,<2"]` → `requires = ["maturin>=1.16,<2"]`
    (the version tested; PEP 639 `license-files` needs a recent maturin);
  - `license = {text = "GPL-3.0-or-later"}` → `license = "GPL-3.0-or-later"`
    (SPDX expression, PEP 639; METADATA now has `License-Expression`);
  - added `license-files = ["LICENSE"]`, `readme = "README.md"`,
    `authors = [{name = "Gijs Molenaar"}]` (no e-mail, deliberately),
    `keywords = [...]`, `classifiers = [...]` (Alpha, Science/Research,
    POSIX Linux, Python 3, Rust, Astronomy; no licence classifier, which PEP
    639 forbids beside an expression);
  - added `dependencies = ["numpy>=1.26"]` with a two-line comment (the
    defect above);
  - added `[project.urls] Repository = "https://github.com/gijzelaerr/rang"`.
  `version` stays `0.1.0`; bump it with the first tag.
- **Can the ctypes fallback be dropped (S1)?** For installed users, yes in
  effect: every run here chose the extension with no cargo and no
  `RANG_CORE_*` variable, and the wheel's binary also exports the C ABI. In
  the code, not yet, because three things still reach it: (a)
  `examples/prototype_section6.py` calls `core.library()` unconditionally
  (change it to `core.extension() or core.library()`, or drop the preload);
  (b) `tests/test_core_backends.py` uses the ctypes path as its oracle (it
  would become an extension-against-archive test, which
  `compare_core_backends.py` already is); (c) `RANG_CORE_LIB` is how archived
  receipts and the phase 2 validator's cost subprocess name a library. The
  root crate's ctypes path (`librang_toy.so`, `rangtoy.build()`) cannot go
  until its TV/projector kernels move into the core or the extension; that
  move would also make the wheel self-contained for the flagging chain.
  Recommendation for P6: keep `core.library()` for one release behind
  `RANG_CORE_BACKEND=ctypes`, fix (a), then delete `build_core()` and the
  import-time cargo build.
- **Small follow-ups (not done, outside this task's files)**: ship
  `core/data/*.staticmask` as package data (`python/rangtoy/data/` and
  `importlib.resources` in `core_flag`); let `core_imaging`, `core_campaign`
  and `core_cli` take their root from an environment variable or the working
  directory instead of `parents[2]`; `RUSTFLAGS=--remap-path-prefix` in
  `build-inside.sh` and the workflow for path-free binaries;
  `SOURCE_DATE_EPOCH` for a byte-reproducible wheel archive; an `exclude`
  list to trim the sdist; check the `rangtoy` name on PyPI before the first
  upload.
- **`.cargo/config.toml` with `target-cpu=x86-64-v3`** (coming on main):
  `tools/wheel/build-inside.sh` and the `wheel` job set `RUSTFLAGS` to the
  target's baseline, which overrides config-file rustflags; the CI test
  job's C ABI build uses `generic`. Not yet exercised against that config
  (it is not on this branch); after the merge, one `tools/wheel/build.sh`
  run should print `RUSTFLAGS=-C target-cpu=x86-64` and give a wheel whose
  `auditwheel show` is unchanged. New `core/` dependencies (rayon, rustfft)
  and `lto = "thin"` will change the `.so` hash; that is expected.
- **Merge order**: this branch touches only `pyproject.toml` among shared
  files (the lines above); nothing else in flight edits it as far as the big
  plan shows.

## First CI run (coordinator, 2026-10-30)

Run 41018751702 on the merge push: the three build jobs passed (x86_64 and
aarch64 wheels, sdist); all four test jobs failed in the skip filter, not in
the tests (10 passed, 1 skipped per job): the filter allowed the wording
"fixture MS not present" while `tests/test_core_backends.py:333` skips
with "MS oracle not present". Fixed by widening the filter; the next push
re-runs it.

## Open questions

- Is `rangtoy` the name to publish under, or should the distribution be
  renamed (for example `rang`) before the first upload? Renaming later
  costs a PyPI project transfer.
- Should a wheel without the flagging kernels be published at all, or wait
  for the root crate's kernels to move into the core?
