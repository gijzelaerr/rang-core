# P12: rename the package `rangtoy` to `rang`, the distribution to `rang-core`

Big plan task P12 ([big-plan.md](big-plan.md), "Name (user, 2026-10-30,
final)"). Branch `p12-rename` from main `c21f6c5`, worktree
`~/Worktrees/rang/p12-rename`. Status: **done, measured.** The protocol
below was committed (`a04b886`) before any file moved; the record follows it.
Evidence: `outputs/p12-rename-20261030-01` (Windows logs copied to its
`windows/`).

## Protocol (frozen before the rename)

### Names

| What | Before | After |
| --- | --- | --- |
| Project, GitHub repository | Rang, `gijzelaerr/rang` | rang-core, `gijzelaerr/rang-core` |
| PyPI distribution (`[project] name`) | `rangtoy` | `rang-core` (wheel and sdist files `rang_core-<v>…`) |
| Python package (`import …`) | `rangtoy` (`python/rangtoy/`) | `rang` (`python/rang/`) |
| PyO3 extension | `rangtoy._core` | `rang._core` (`[tool.maturin] module-name = "rang._core"`, `python-source = "python"`) |
| Console script | `rang-core = "rangtoy.core_cli:main"` | `rang-core = "rang.core_cli:main"` |
| CLI receipt (`rang.receipt`) | version 1, key `environment.rangtoy` (distribution version) | version 2, key `environment.rang_core` |
| `environment.json` of `STAGE environment` | key `rangtoy_modules_imported` | key `rang_modules_imported` (unversioned record; noted here) |

Cargo package names stay: the root crate `rang-toy`, the core crate
`rang-core`, the PyO3 crate `rang-core-py` (`[lib] name = "rang_core_py"`;
the `#[pymodule] fn _core` already gives the module its last component, so
only doc comments change). `RANG_TOY_LIB`, `rang_toy_lib` and `librang_toy`
are not the package name and stay (they name the retired ctypes path).
"rang" is also Dutch for rank, which the identifiability survey measures first.

### Inventory at `c21f6c5`

`git grep -l rangtoy` lists 431 files. By group (counts are files):

- **Archived, unchanged** (the historical record keeps the old name):
  `history/` 59 files; `research/results/` 69 files; the bodies of 72 dated
  research notes (`research/*.md` other than `research/README.md`), including
  `STATE.md`, `big-plan.md`, `p7-architecture.md`, `p9-cli.md`,
  `p11-extract.md`, `wheel.md` (except a dated pointer in its publish section,
  below).
- **Package directory**: `python/rangtoy/` (71 tracked files: the modules,
  the `notebook/` subpackage, `data/` package data with the two Tricolour
  static masks, its `README.md` and `TRICOLOUR-LICENSE`) moves with one
  `git mv python/rangtoy python/rang`; 38 of its files name `rangtoy`.
  (Precisely: 67 Python files, 9 of them in `notebook/`, and the 4 files of
  `data/`.)
- **Imports**: `from rangtoy import …` / `import rangtoy…` in 87 files under
  `examples/` (including `examples/README.md`), 64 under `tests/` (including
  `conftest.py`), and the package's own absolute imports (`fluxstd.py`).
- **Extension module and maturin config**: `pyproject.toml` (`name`,
  `[project.urls]`, `[project.scripts]`, `[tool.maturin] module-name`, the
  comments); `core/py/Cargo.toml` description; `core/py/src/lib.rs` doc
  comments (lines 1, 1299); `src/lib.rs:790` (`rangtoy._core.toy_cli`);
  doc comments in `core/src/ffi_{closure,correct,flag,grid,weights,wgridder}.rs`,
  `core/src/fluxstd.rs`, `core/src/robust.rs`; `python/rangtoy/core.py`
  (`extension()` error text), `projector.py` (the frozen-module shim's
  docstring; the shim itself moves with the package unchanged).
- **Console script and CLI self-references**: `core_cli.py` (17 hits: the
  engine name `rangtoy.core_compare` in comparator receipts, `_rangtoy_modules`
  and its `name.startswith("rangtoy")` filter, `find_spec("rangtoy._core")`,
  `importlib.metadata.version("rangtoy")`, help texts); `check.py` (docstring);
  `core_imaging.py` (`prog`); `tools/check-all.sh` (`-m rangtoy.check`);
  `CONTRIBUTING.md` (`python -m rangtoy.check`).
- **Receipts and their schema version**: `core_cli.RECEIPT_VERSION` 1 → 2 and
  the renamed key (table above); the docstring's "version 1"; the campaign
  `CODE_FILES` tuples (`core_campaign*.py`, `python/rangtoy/<f>.py` →
  `python/rang/<f>.py`, keys of `code_sha256`, which the comparators already
  exclude as provenance); `core_receipts.source_receipts` globs
  `python/rangtoy/*.py` (a line inside a verbatim P11 extract, see Tests);
  `tools/wheel/run_installed.py`'s copy of it; `tools/oracles/casa/receipt.py`
  `CODE`.
- **Recipes**: `recipes/core-{actions,cabs,imaging,injections,prospective,signal,trend}.yaml`
  (cab commands `rangtoy.core_cli.*`, `rangtoy.core_imaging.*`, comments).
- **Tests and golden/path normalisation**: `tests/test_p11_extract.py` (22
  hits: `PKG`, the import-blocker script, the frozen-import regexes, the
  `CODE_FILES` regex, `C1_FILE`); `test_core_cli.py` (21; the
  `rangtoy_modules_imported` and receipt-version assertions);
  `test_p7_architecture.py` (10); `test_core_backends.py` and
  `test_l5_solver.py` (`find_spec("rangtoy._core")`); the rest are imports.
  `tests/data/core-backends-golden.json` stores no package name (no `rang`
  substring at all): nothing to normalise, nothing regenerated.
- **Notebooks**: the five `notebooks/0*.ipynb` (`from rangtoy.notebook import
  …`, one prose mention); `python/rangtoy/notebook/steer.py`
  (`pip install 'rangtoy[notebook]'`).
- **Wheel tooling and CI**: `tools/wheel/{build.py,build.sh,build-inside.sh,
  pytest_wheel.py,run_installed.py,smoke.py,test.py,test.sh}`
  (`build-inside.sh` unpacks `rangtoy/_core.abi3.so` and the sdist directory
  `rangtoy-*`, which become `rang/_core.abi3.so` and `rang_core-*`);
  `.github/workflows/wheels.yml` (header comment; the publish comment still
  says repository `ra-ng` and "ra-ng after task P12"); `tools/core-j-suite.sh`;
  `tools/oracles/casa/{compare.py,receipt.py,run.sh}`.
- **Docs and logo wordmark**: `README.md` (17 hits, logo alt text `ra-ng`,
  pip lines naming the distribution); `CONTRIBUTING.md`; `AGENTS.md` (no hit);
  `research/README.md` (four dated index entries; gets a pointer paragraph,
  entries unchanged); `docs/logo/` (`README.md` titled "ra-ng logo";
  `wordmark.svg`, `wordmark-on-dark.svg`, `lockup.svg`, `lockup-on-dark.svg`
  read `ra`‿`ng`); `research/wheel.md` publish section (dated pointer to the
  `rang-core` names and the trusted-publishing tag).
- **`.gitignore`**: `/python/rangtoy/_core*.so`, `/python/rangtoy/_core*.pyd`,
  `/python/rangtoy/*.pdb`, `/python/rangtoy.egg-info/` → `rang` (plus
  `/python/rang_core.egg-info/`).

Deliberately left: the 20 extract headers in `python/rang/core_*.py`
("Verbatim extract of the frozen `rangtoy.flagging_…` … from
python/rangtoy/flagging_….py at commit 2da566c"), which state where the code
came from at that commit, and the `SOURCE` regex of `test_p11_extract.py`
that parses them.

### Method

1. Commit this protocol.
2. `git mv python/rangtoy python/rang` alone in one commit; `git show -M
   --name-status` must list only `R100` entries. Delete the untracked
   leftovers (`python/rangtoy/_core*.so`, `__pycache__`, `*.egg-info`) so no
   namespace package `rangtoy` survives.
3. Edits: `sed s/rangtoy/rang/g` over the live files above, except the
   extract headers and the `SOURCE` regex; then by hand: distribution names
   (`rang-core`, `rang_core-*` files), `importlib.metadata.version("rang-core")`,
   the module filter `name == "rang" or name.startswith("rang.")`, the receipt
   key and version, the `.gitignore`, `pyproject.toml`, the workflow comment.
   `test_p11_extract.py`'s verbatim check maps one more line back:
   `(root / "python/rang")` → `(root / "python/rangtoy")` inside the copied
   `source_receipts` (the package path, like the in-body import lines it
   already maps). A test asserts `importlib.util.find_spec("rangtoy") is None`.
4. Docs: README "Names" section, `research/README.md` pointer, the logo
   wordmark re-cut to `rang`‿`core` (same fringe hyphen path and stroke, ink
   `#10131a`, on-dark `#f2f2f2`, amber `#e8a33d`, Inter 500 at 120;
   viewBoxes widened; `logo.svg`, `icon.svg`, `icon-mono.svg` byte-unchanged).
5. `rm -rf .venv`, recreate with uv, reinstall editable; run the acceptance.

### Baselines (before, at `c21f6c5`, old venv)

In `outputs/p12-rename-20261030-01`: `manifest-before.txt` (sha256 of every
tracked file under `history/` and `research/results/`), `targeted-before.log`
(`pytest -rs` of the preconditions, notebook, P11 extract, receipts and CLI
tests), `console-before/` (the P9 identity suite through the `rang-core`
launcher: `identity.py`, copied from `outputs/p9-cli-20261030-01` with the
cli-phase module parameterised), `pytest-full-before.log`.

### Acceptance

| # | Criterion |
| --- | --- |
| A1 | `bash tools/check-all.sh` PASS (plain, it locks itself) |
| A2 | `rang-core check` PASS |
| A3 | `python -c "import rang, rang._core"` succeeds; `find_spec("rangtoy") is None` (asserted by a test) |
| A4 | the P9 identity suite through `rang-core` (console phase) after equals before: every exit, verdict and count identical; stdout and comparator receipts equal after `rangtoy`→`rang` and P9's volatile keys; CLI receipts equal on verdict and inputs, differing only in version 1→2, the env key and paths/hashes (`p12diff.py`, every residual difference listed) |
| A5 | K/L1/L2 preconditions pass (`tests/test_pc1_preconditions.py`), run, not skipped (`-rs`) |
| A6 | notebooks execute (`tests/test_notebook_execute.py`), run, not skipped |
| A7 | a wheel from `tools/wheel/build.py` is named `rang_core-<v>-cp310-abi3-*.whl`, installs into a fresh venv with cargo absent, passes `tools/wheel/test.py` (import `rang._core`, smoke, backends golden) |
| A8 | A7 on native Windows (LF clone of the branch), plus `rang-core check` there |
| A9 | every moved file is a `git mv` with history (`R100`; `git log --follow` works) |
| A10 | no pre-existing path under `history/` or `research/results/` changed (sha256 manifests before/after identical) |
| A11 | every `rangtoy` left in the tree is deliberate (history, results, dated notes, extract headers, the `SOURCE` regex, the mapped line), listed in the record |
| A12 | the full pytest counts after equal before (passed/skipped), apart from the new test |

## Record

Commits on `p12-rename`: `a04b886` protocol; `8a0f024` the move (`git mv
python/rangtoy python/rang`, 71 entries, all `R100`; `git log --follow
python/rang/core_cli.py` reaches P11's `2223f05`); `8648648` the rename edits;
`86e2a8d` docs and logo; `2e03366` and `0085b36` Windows portability (see
Deviations); the commit adding this record.

### Acceptance

| # | Result | Evidence |
| --- | --- | --- |
| A1 | **PASS**: `bash tools/check-all.sh` at `0085b36`, all 15 steps, pytest 632 passed, 3 skipped (also PASS at `86e2a8d`) | `check-all-final.log`, `check-all.log` |
| A2 | **PASS**: `rang-core check` (Linux, `86e2a8d`; the same module as A1) | `rang-core-check.{log,json,rang-receipt.json}` |
| A3 | **PASS**: `import rang, rang._core` loads `python/rang/_core.abi3.so`; `find_spec("rangtoy")` is `None`; `tests/test_p12_rename.py` (4 tests: no `rangtoy`, the module names, the distribution `rang-core` with the one console script `rang-core = rang.core_cli:main`, and no `rangtoy` in a fresh interpreter) | `targeted-final.log` |
| A4 | **PASS**: P9's 20 cases through the `rang-core` launcher, before (`c21f6c5`, old venv) and after (`86e2a8d` and `0085b36`, fresh venv). Every exit status (17 × 0; `trend-frozen`, `campaign-check` and `backends` 1, as at P9), stdout and comparator receipt is identical. Volatile timing keys differ only where P9 listed them. No `rangtoy` occurred in any stdout or comparator receipt, so the name mapping was never needed. In the CLI receipts, verdict, stage, verb, exit and every input (path, kind, bytes, digest) are identical; version 1 → 2 and `environment.rangtoy` → `environment.rang_core` in all 20. stderr is identical apart from the line numbers in `campaign-check`'s `core_cli.py` traceback (+2, the version comment) | `p12diff.py`, `identity-diff.txt`, `identity-diff-final.txt` |
| A5 | **PASS**: `tests/test_pc1_preconditions.py`, both tests ran (no skip) | `targeted-{before,after,final}.log` |
| A6 | **PASS**: `tests/test_notebook_execute.py` ran (no skip) | same |
| A7 | **PASS**: `tools/wheel/build.py` built `rang_core-0.1.0-cp310-abi3-manylinux_2_35_x86_64.whl` (2,817,491 B, `801b25d4…efca1`, at `0085b36`; 2,817,298 B at `86e2a8d`). It has 79 entries: package `rang/` with `_core.abi3.so` and `data/`, no `rangtoy`, no `__pycache__`. `tools/wheel/test.py` passed venv, install, import (cargo absent, asserted), smoke and pytest (37 passed: backends golden, toy, P7, P12) | `wheel-linux{,-2}*` |
| A8 | **PASS**: native Windows, in an LF clone of `p12-rename`. The clone came from the main repository because a worktree's `.git` file cannot be cloned from Windows, as X1 found. `rang_core-0.1.0-cp310-abi3-win_amd64.whl` (2,702,285 B, `33d037e1…a7cad`, at `0085b36`): `test.py` PASS (31 passed, 6 skipped: the MS oracle and P7's five libm-digit toy cases). `rang-core check` PASS at `0085b36` (pytest 591 passed, 44 skipped). At `86e2a8d` it failed 18 tests, all pre-existing (see Deviations) | `windows/` |
| A9 | **PASS**: 71 `R100` renames in `8a0f024` | `git show -M --name-status 8a0f024` |
| A10 | **PASS**: the sha256 of all 270 tracked files under `history/` and `research/results/` is identical before, after and at the end | `manifest-{before,after,final}.txt` |
| A11 | **PASS**: every remaining `rangtoy` is deliberate (listed below) | `git grep rangtoy` |
| A12 | **PASS**: full pytest 628 passed, 3 skipped before; 632 passed, 3 skipped after (the 4 new P12 tests; the same 3 skips: casacure, ducc0, the K fetch) | `pytest-full-{before,after}.log` |

### What changed besides the sed

- `pyproject.toml`: `name = "rang-core"`, the description, the repository URL
  `gijzelaerr/rang-core`, `rang-core = "rang.core_cli:main"`,
  `module-name = "rang._core"`.
- `core_cli`: `RECEIPT_VERSION = 2` with a comment. `environment.rang_core`
  holds `importlib.metadata.version("rang-core")`. The module filter of
  `environment` is `name == "rang" or name.startswith("rang.")`, because a
  bare `startswith("rang")` would also catch any other `rang…` module. The
  `environment.json` key is `rang_modules_imported`. Neither key has a reader
  outside `tests/test_core_cli.py`; `core_compare` finds receipts by file name
  only.
- `tests/test_p11_extract.py`: `PKG`, the frozen-import regexes, the
  `CODE_FILES` regex, the blocker script and `C1_FILE` follow the package.
  The `SOURCE` regex keeps `python/rangtoy/` because it parses the historical
  headers. The verbatim check maps `(root / "python/rang")` back to
  `(root / "python/rangtoy")`. That is the one copied line that names the
  package directory (`source_receipts` in `core_receipts.py`).
- Distribution names: `notebook/steer.py` says `pip install
  'rang-core[notebook]'`; the README pip lines name `rang-core` and
  `rang_core-<v>-…whl`; `tools/wheel/build-inside.sh` unpacks `rang_core-*`
  (the sdist directory) and `rang/_core.abi3.so`.
- `tools/wheel/test.py`, `test.sh` and the workflow comment add
  `tests/test_p12_rename.py` to the wheel test, so it also checks the
  installed wheel's metadata.
- `.gitignore`: the `python/rang/…` entries plus `/python/rang_core.egg-info/`.
- `.github/workflows/wheels.yml`: the publish comment names the registered
  pending publisher (`rang-core`, owner `gijzelaerr`, repository
  `rang-core`, workflow `wheels.yml`, environment `pypi`).
- Logo, `wordmark{,-on-dark}.svg`: they read `rang`, fringe, `core`. The
  fringe path moved from x 150 to 298, the second word from x 216 to 364, and
  the viewBox width from 380 to 636. The fringe sits after `rang` at the old
  `ra`→fringe offset plus the width of `ng`, so its spacing is the old one in
  any font.
- Logo, `lockup{,-on-dark}.svg`: widened from 760 to 940 with the same group.
  All four keep their committed CRLF line endings.
- Logo, unchanged files: `logo.svg`, `icon.svg` and `icon-mono.svg` are
  byte-identical (`30b51b53…`, `f5ac62f7…`, `6c364544…`).
- Logo measurements: Inter is not installed here, so the widths were measured
  with Segoe UI and Arial. At 120 px, `rang` is 248–257 px and `core` 238–243
  px. The fringe gap is therefore 41–50 px (`ra`→fringe was 39–43), and the
  word ends inside the viewBox. The README shows the lockup at width 520 (was
  420).
- Docs: the README has the title `rang-core` and a "Names" section;
  `research/README.md` has a dated rename pointer; `research/wheel.md` has a
  dated pointer in its publish section; `docs/logo/README.md` is titled
  "rang-core logo".

### Remaining `rangtoy` (all deliberate)

| Category | Files | Occurrences |
| --- | ---: | ---: |
| `history/` (frozen modules, tests, recipes, tools) | 59 | 108 |
| `research/results/` (archives, suites, receipts) | 69 | 1,115 |
| research notes, including this note, the `research/README.md` index entries and pointer, and the `wheel.md` pointer; bodies of dated notes unchanged | 74 | 574 |
| P11 extract headers (lines 3 and 5 of 20 `python/rang/core_*.py`) | 20 | 40 |
| `tests/test_p11_extract.py` (`SOURCE` regex, the mapped line) | 1 | 2 |
| `tests/test_p12_rename.py` (asserts that `rangtoy` is absent) | 1 | 4 |
| `python/rang/core_cli.py` (the version-2 comment) | 1 | 1 |
| `README.md` (Names: "was called `rangtoy`") | 1 | 1 |

Also unchanged by design: `RANG_TOY_LIB`, `rang_toy_lib` and `librang_toy`
(the retired ctypes path, not the package), and the Cargo package names
`rang-toy`, `rang-core` and `rang-core-py`.

### Deviations from the protocol

- **Windows fixes (two commits, not in the protocol).** The first Windows
  `rang-core check` (at `86e2a8d`) failed 18 tests. The same 18 fail at main
  `c21f6c5` in a separate Windows clone (`windows/main-pytest.log`), so
  none of them comes from the rename. There were two causes:
  1. `test_p11_extract` read sources in the Windows locale encoding (2 tests;
     two extracts contain `×`). It now uses `read_text(encoding="utf-8")`.
  2. `core_closure`, `core_wgridder` and `fluxstd` generate a standalone crate
     (16 tests). Its `#[path = "…"]` attributes used native paths, which
     rustc reads as escape sequences on Windows, and the library was then
     loaded as `lib*.so` by name. The paths are now POSIX, and the file names
     are `rang_*.dll`, `librang_*.dylib` or `librang_*.so` per platform.

  Linux behaviour and the files generated on Linux are unchanged: check-all
  and the identity suite were rerun at `0085b36`. Because these modules'
  text changed, their `code_sha256` changes in new C1/FS1 receipts; every
  comparator already treats that field as provenance.
- **Clone source.** The Windows clone was made from `~/Github/rang` with `-b
  p12-rename` (a worktree's `.git` is a file), with `core.autocrlf=false`.

### Open items

- The user tags `v0.1.0` to publish `rang-core` through the `publish` job;
  nothing was tagged or pushed here.
- Before that tag, the GitHub repository must be `gijzelaerr/rang-core`
  (renamed or created), or the trusted publisher will not match. The
  workflow and `[project.urls]` already name it.
- The wheels grew from about 0.8 MB (`outputs/wheel-20261030-13`, this
  morning) to 2.8 MB. The extension has gained FS1, E3, DF1, C1 and B1 code
  since then, and nothing stray is packed (79 entries listed), so this is not
  a P12 effect.

## Timings (every tool run of this task)

| Run | Wall |
| --- | ---: |
| venv + editable install, before / after (WSL, uv) | 69 s / 64 s |
| targeted pytest (pc1, notebooks, P11, receipts, CLI), before / after / final | 31.7 s / 29.6 s / 24.6 s |
| P9 identity suite through `rang-core`, before / after / final | 6.2 s / 6.2 s / 8.1 s |
| full pytest, before / after | 168.2 s / 165.0 s |
| `bash tools/check-all.sh` at `86e2a8d` (cold extension build) / `0085b36` | 334.9 s / 134.8 s |
| `rang-core check` (Linux) | 132.5 s |
| `tools/wheel/build.py` Linux, `86e2a8d` / `0085b36` | 73.8 s / about 70 s (maturin step 67.2 s) |
| `tools/wheel/test.py` Linux | 11.1 s |
| Windows clone / venv / editable install (MSVC extension) | 11.5 s / 0.1 s / 124.8 s |
| Windows `rang-core check`, `86e2a8d` (FAIL, pre-existing) / `0085b36` (PASS) | 339.8 s / 112.3 s |
| Windows `build.py` / `test.py`, at `86e2a8d` and at `0085b36` | 102.9 s and 102.2 s / 8.7 s and 8.7 s |
| Windows clone of main, install and the 4 failing test files | 140.5 s |

## For the coordinator

- **STATE paragraph.** "P12 merged. The package is `rang` (`import rang`,
  extension `rang._core`, `python/rang/`); the project, repository and PyPI
  distribution are `rang-core`; the CLI is still `rang-core`. The move used
  `git mv` with history (71 × R100). On P9's 20-case suite through
  `rang-core`, every comparator verdict, count, stdout and receipt is
  identical. CLI receipts are now `rang.receipt` v2 (`environment.rang_core`).
  The wheel is `rang_core-0.1.0-cp310-abi3-*` and passes the cargo-absent
  test on Linux and Windows, and check-all passes on both. Archived notes,
  results and `history/` keep `rangtoy` (research/p12-rename.md). Windows
  `rang-core check` is green again: 18 pre-existing failures, from the
  C1/DF1/FS1 standalone builds and the P11 test's encoding, are fixed."
- **Timing rows**: the table above.
- **Plan status line** (`research/big-plan.md`): "P12 rename: done
  (`p12-rename`, research/p12-rename.md)".
- **PyPI**: the pending publisher matches the tree (`[project] name =
  "rang-core"`, workflow `wheels.yml`, environment `pypi`, repository
  `gijzelaerr/rang-core`). The user tags `v0.1.0` (the version in
  `pyproject.toml` is already `0.1.0`) and pushes the tag. The workflow then
  builds, tests, releases and publishes. The GitHub repository has to be
  `gijzelaerr/rang-core` first.
- **Remaining `rangtoy`**: history, results, dated notes, the 20 extract
  headers and the test lines listed above. Each records what was true when it
  was written.
- **Upstream**: none (RATT/caracal or otherwise).
