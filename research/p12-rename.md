# P12: rename the package `rangtoy` to `rang`, the distribution to `rang-core`

Big plan task P12 ([big-plan.md](big-plan.md), "Name (user, 2026-10-30,
final)"). Branch `p12-rename` from main `c21f6c5`, worktree
`~/Worktrees/rang/p12-rename`. Status: **protocol frozen; rename not yet
done.** The protocol below is committed before any file moves; the record
follows it. Evidence: `outputs/p12-rename-20261030-01`.

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
