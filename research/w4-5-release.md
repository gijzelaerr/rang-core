# W4-5: release metadata for v0.1.0

Big plan wave 4 fix task W4-5 ([w4-review.md](w4-review.md), findings
W4R-07, W4R-08, W4R-13, W4R-14, the "Release readiness (v0.1.0)" checklist
and "Proposed fix tasks" W4-5), branch `w4-5-release` from main `ecccbf0`.
Status: **implemented; measured locally (versions, CLI, README rendering,
twine, sdist, a clean wheel venv, a wheel built from the sdist, actionlint,
a dry run of the tag-check and notes steps); the workflow has not run on
GitHub** (nothing pushed). Packaging only; no scientific claim. Nothing is
tagged or published: the user tags `v0.1.0`.

## What changed

- `python/rang/__init__.py`: `__version__` = `importlib.metadata.version("rang-core")`,
  else (a checkout on `sys.path` with no install) the `[project] version` of
  the checkout's `pyproject.toml`, read with a regex because Python 3.10 has
  no `tomllib`, and only when that section's `name` is `rang-core`;
  `"unknown"` otherwise.
- `python/rang/core_cli.py` (coordinator file; hunk below): `rang-core
  --version` and `-V` print `rang-core <version>` and exit 0. The check is
  the first thing `dispatch` does, before the global options (which reject
  unknown flags), thread pinning, NumPy and any receipt. `usage()` is
  unchanged, so `docs/cli.md` needs no regeneration (`gen_cli.py --check`
  passes).
- `docs/conf.py` (version only): the no-install fallback reads
  `pyproject.toml` instead of `"unknown"`.
- `pyproject.toml`:
  - classifiers: Linux, `MacOS`, `Microsoft :: Windows`, `3 :: Only`,
    3.10–3.14, `Implementation :: CPython` (no `License ::` classifier: the
    licence is a PEP 639 expression, which forbids one);
  - URLs: Documentation (`https://gijzelaerr.github.io/rang-core/`),
    Repository (`gijzelaerr/rang-core`, unchanged), Issues, Changelog;
  - keywords: `imaging` and `measurement set` added;
  - the `flagging` extra is dropped, with a comment: it pinned the frozen
    QuartiCal 0.2.7 / Stimela 2.1.4 / python-casacore 3.8.1 stack, which
    only `history/` used; `history/README.md` does not rely on it, and
    `history/tools/flagging/requirements.lock` keeps the pins;
  - `pointing` no longer repeats `numpy` (a core dependency; review
    checklist "Extras");
  - `[tool.maturin] exclude` (format `sdist`): `.cargo`, `.github`,
    `core/examples`, `data`, `docs`, `examples`, `formal`, `history`,
    `notebooks`, `outputs`, `recipes`, `research`, every `tools/`
    subdirectory but `tools/wheel`, `AGENTS.md`, `CONTRIBUTING.md`,
    `.gitignore`. Cause of the old size: the root crate `rang-toy` is a path
    dependency at the repository root, so cargo's package list was the whole
    tree. `.cargo/config.toml` (x86-64-v3 for local builds) is out on
    purpose: an sdist build must target the builder's baseline CPU.
- `README.md` (coordinator file; hunk below): every relative link is now
  `https://github.com/gijzelaerr/rang-core/blob/main/...` (files) or
  `.../tree/main/...` (directories), anchors kept; the logo is
  `https://raw.githubusercontent.com/gijzelaerr/rang-core/main/docs/logo/lockup.svg`
  (a `blob/` URL serves HTML; the raw URL answers `200`,
  `Content-Type: image/svg+xml`). The wheel paragraph names the five
  platforms, says the Tricolour masks are package data, and points at
  `rang-core --version` and the CHANGELOG. The sentences about every kernel
  being in the wheel are W4-3's and are left as they were.
- `CHANGELOG.md` (new): "Unreleased", then `## 0.1.0 (unreleased: dated the
  day v0.1.0 is tagged)` with one paragraph each on the Rust core, the
  simplification and speed work, wheels and CI, the documentation and the
  science verdicts.
- `.github/workflows/wheels.yml`:
  - `release`: checks out the tagged commit (`persist-credentials: false`);
    a step "Check that the tag equals the version" fails unless
    `${GITHUB_REF_NAME#v}` equals the version in every wheel and sdist file
    name and the `pyproject.toml` version, and unless there are exactly 5
    wheels and 1 sdist; a step extracts the CHANGELOG section of the version
    (awk, heading prefix `## <version>` followed by a space or end of line,
    up to the next `## `) and fails when it is empty; `gh release create`
    uses `--notes-file`.
  - `publish`: the same file-name check before `gh-action-pypi-publish`
    (no checkout, so `id-token: write` stays the only permission; the file
    names carry the `pyproject.toml` version that maturin built).
  - actions at their current majors, all `node24`: `checkout@v7`,
    `setup-python@v7`, `upload-artifact@v7`, `download-artifact@v8` (errors
    on a digest mismatch by default), `cache@v6`. `PyO3/maturin-action@v1`
    is already `node24`; `pypa/gh-action-pypi-publish@release/v1` is a
    composite action.
- `.github/workflows/docs.yml` (action versions only): `checkout@v7`,
  `setup-python@v7`, `cache@v6`, `upload-pages-artifact@v5` (composite),
  `configure-pages@v6`, `deploy-pages@v5`.
- `docs/installation.md`: the platform table (`macos-15`, not `macos-14`)
  and the stale "macOS jobs not run" sentence; the tag-equals-version and
  CHANGELOG notes; what the sdist holds; the `flagging` row removed and the
  `recipes` row corrected (Stimela 2.1.4 for the core-native recipes); the
  frozen stack's pins; `rang-core --version` in "Check the install"; a new
  "Releases" section.
- `CONTRIBUTING.md`: a "Releasing" section (version once in
  `pyproject.toml`, the three `Cargo.toml`s and lock files, the CHANGELOG
  move, the tag, what the workflow refuses).
- `tests/test_w4_5_release.py` (13 tests): versions agree (pyproject, the
  three `Cargo.toml`s, the three `Cargo.lock` entries, `rang.__version__`,
  the installed metadata, `docs/conf.py` through `runpy`); the
  `PackageNotFoundError` fallback; `--version`/`-V`; the CHANGELOG section;
  no relative link, image source or reference-style target in the README
  (with a self-test of the detector) and none in the rendered HTML (skipped
  without `readme-renderer[md]`, i.e. `comrak`); the classifiers, URLs and
  no `flagging` extra; the sdist exclude list; the tag check before the
  upload in both jobs and the notes file in `release`; every `actions/*`
  at or above its first Node 24 major in both workflows.

The lock-file refresh after a version bump was checked on a scratch copy
of the three crates: bumping to 0.1.1 and running `cargo metadata --offline
--format-version 1 > /dev/null` in `.`, `core/` and `core/py/` rewrote the
six `rang-*` entries of the three `Cargo.lock`s to 0.1.1 (0.5 s).

## The sdist

`maturin sdist` (1.16.0) of this tree, before and after the exclude list:

| | Entries (with directories) | Size |
| --- | ---: | ---: |
| Before (`ecccbf0`'s pyproject, `outputs/w4-5-20261031-01-sdist-before`) | 1,012 | 5,401,998 B |
| After (`outputs/w4-5-20261031-04-accept`, from `tools/wheel/build.py --sdist`) | 250 | 1,216,930 B |

The review counted 1,010 entries and 5.4 MB on `17653e4`. Before, the top
level held 395 `research/`, 134 `examples/`, 116 `history/`, 46 `tools/`,
41 `docs/`, 12 `formal/`, 7 `notebooks/`, 7 `recipes/`, 5 `data/` and 2
`.github/` files. After, the files are:

| Path | Files |
| --- | ---: |
| `pyproject.toml`, `PKG-INFO`, `README.md`, `CHANGELOG.md`, `LICENSE` | 5 |
| `Cargo.toml`, `Cargo.lock`, `src/` (`lib.rs`, `linalg.rs`, `main.rs`, `projector.rs`, `response.rs`, `trend.rs`, `tv.rs`) | 9 |
| `core/Cargo.toml`, `core/Cargo.lock`, `core/src/` (42 files, `gpu/` included) | 44 |
| `core/py/Cargo.toml`, `core/py/Cargo.lock`, `core/py/src/` (`lib.rs`, `clean.rs`) | 4 |
| `python/rang/` (the package, the two masks and the Tricolour notice included) | 88 |
| `tests/*.py` | 88 |
| `tests/data/` (`toy-golden.json`, `core-backends-golden.json`, `core-backends-golden.npz`) | 3 |
| `tools/wheel/` (build and test scripts, `pytest_wheel.py`) | 9 |

Full listing: `outputs/w4-5-20261031-04-accept/sdist-list.txt`.

What the sdist does on its own (measured): unpacked, `maturin build
--release --locked` builds a working wheel from it (194 s), and the
wheel's test subset of `.github/workflows/wheels.yml` (`test_core_backends`,
`test_toy`, `test_p7_architecture`, `test_p12_rename`,
`test_t1_casacure_oracle`) passes from the sdist's own `tests/` against
that wheel with `pytest_wheel`, apart from the skips that need casacure or
the fixture. `tests/test_w4_5_release.py` skips its `.github/` and `docs/`
cases there. The rest of the suite reads `research/`, `examples/` or
`history/` (69 of the 88 test files name `research/`) and runs from a
checkout only; this is recorded in `docs/installation.md`.

## Measured acceptance

| Check | Result |
| --- | --- |
| `rang-core --version` (editable install) | `rang-core 0.1.0`, exit 0; `-V` the same |
| `python -c "import rang; print(rang.__version__)"`, editable | `0.1.0` |
| the same with no install (checkout on `sys.path`, system Python) | `0.1.0` from the `pyproject.toml` fallback |
| clean venv (CPython 3.14) from the built wheel, cwd `/tmp` | `rang-core 0.1.0`; `0.1.0`, imported from `site-packages` |
| wheel built from the unpacked sdist | `rang-core 0.1.0` |
| wheel METADATA | 15 classifiers (Linux, MacOS, Windows, 3.10–3.14, CPython); Project-URLs Changelog, Documentation, Issues, Repository; no `flagging` extra |
| version-agreement test and the rest of `tests/test_w4_5_release.py` | 14 passed (editable, with `readme-renderer[md]`) |
| `twine check --strict` on the wheel and the sdist from `tools/wheel/build.py --sdist` | PASSED, both |
| `python -m readme_renderer README.md -o /tmp/w45-readme.html` | 35 `src`/`href` URLs, 0 relative |
| `actionlint` (`uv tool run --from actionlint-py`) on both workflows | exit 0, no output |
| dry run of the tag-check and notes steps (the `run:` blocks taken from `wheels.yml` by PyYAML, fake `GITHUB_REF_NAME`, dummy dist files) | 10 of 10 cases as expected: `v0.1.0` passes in both jobs; `v0.1.1` fails in both (file names; in `release` also pyproject); files at 0.1.1 with pyproject 0.1.0 fail; 4 wheels fail; the notes for `v0.1.0` are the 57-line section; `v0.1.1` and `v0.1` have no section and fail |
| `docs/gen_cli.py --check` | up to date (the help text is unchanged) |
| `bash tools/check-all.sh` | `overall: PASS` (pytest 745 passed, 19 skipped in 295 s; the rendered-README case skips there without `comrak`); log `outputs/w4-5-20261031-check-all.log` |
| `workflow_dispatch` run on the branch | not run: nothing pushed. `wheels.yml` has `workflow_dispatch`, so the coordinator can push `w4-5-release` and dispatch it; that run covers the bumped actions in `wheel`, `sdist` and `test`. The `release` and `publish` steps run only on a tag, so the dry run above is their test until `v0.1.0` |

A first run of the sdist test (`outputs/w4-5-20261031-03-accept`) failed
five cases of `tests/test_w4_5_release.py` that read `.github/` and `docs/`,
which the sdist does not carry, and the fallback test, which expects the
checkout's `pyproject.toml`. Both were fixed (`ee1b2e3`, `60bcf0e`): the
checkout-only cases skip, and the fallback test expects `"unknown"` when
`rang` is imported from an installed wheel. The fallback test was then
rerun against the installed wheel and passed.

## Deviations

- The `flagging` extra is dropped, not annotated. `history/README.md` does
  not use it. The frozen `history/recipes/tv-flagging.yaml` header comment
  and `research/flagging.md` still say "install the flagging extra"; both
  are frozen history and are left as they are. The pins are in
  `history/tools/flagging/requirements.lock`.
- The tag check is inline in the two jobs, not a script, because
  `tools/wheel/` is not an owner path here. `publish` checks the file
  names, which carry the version maturin read from `pyproject.toml`, so it
  needs no checkout and its permissions stay `id-token: write`. `release`
  also checks `pyproject.toml` itself.
- The actions are at the current majors on 2026-10-31 (`checkout` v7,
  `setup-python` v7, `upload-artifact` v7, `download-artifact` v8, `cache`
  v6, Pages v5/v6/v5), which is later than the v5/v6 named in the brief.
  All of them are `node24`.
- The rendered-README test skips without `comrak` (`readme-renderer[md]`);
  it is not in the `test` extra, so check-all may skip it. The grep test of
  the README source always runs.
- `README.md`'s other paragraphs were left alone. The sentences that the
  wheel "carries every kernel" belong to W4-3, and the closure and
  flux-standard kernels still need Cargo (W4R-06). `docs/installation.md`
  keeps its paragraph that says so.

## Timings

| Step | Wall | Notes |
| --- | ---: | --- |
| `uv venv` + editable install with extras | 245 s | includes the extension build |
| `maturin sdist`, before / after | 1.3 s / 1.0 s | |
| `tools/wheel/build.py OUT --sdist` | 179.6 s / 181.2 s | runs `-03` / `-04`; host wheel `manylinux_2_35_x86_64`, 3,181,048 B, 95 entries |
| `twine check --strict` (wheel and sdist) | 0.5–0.7 s | |
| `maturin build --release --locked` from the unpacked sdist | 196.4 s / 194.0 s | |
| pytest, wheel subset from the sdist | 20.8 s / 15.7 s | 44 passed, 7 skipped, 1 failed (since fixed) on `-04` |
| pytest `tests/test_w4_5_release.py` | 0.1 s | |
| pytest `test_core_cli`, `test_d1_docs`, `test_p12_rename`, `test_w4_5_release`, `test_p7_architecture` | 24 s | 49 passed, 1 skipped |
| `actionlint` | 0.7 s | |
| dry run of the workflow steps | 0.7 s | |
| `cargo metadata` in three crates after a scratch bump | 0.5 s | |
| `bash tools/check-all.sh` | 1278 s (lock wait included) | |

## For the coordinator

### Coordinator-file hunks

Both hunks are `git diff ecccbf0` output; blank context lines are stored
without their leading space (git diff --check), which `git apply` accepts.

`python/rang/core_cli.py` (version handling only; the rest of the file is
W4-1's):

```diff
diff --git a/python/rang/core_cli.py b/python/rang/core_cli.py
index 1a22a6d..093f746 100644
--- a/python/rang/core_cli.py
+++ b/python/rang/core_cli.py
@@ -1142,6 +1142,11 @@ def dispatch(argv=None):
     """Run one command line; return what the command returned (a stage
     function's summary or record, a comparator's verdict)."""
     argv = list(sys.argv[1:] if argv is None else argv)
+    if argv[:1] in (["--version"], ["-V"]):
+        from . import __version__
+
+        print(f"rang-core {__version__}")
+        return None
     options = _global_options(argv)
     # Before NumPy: nothing above imports it.
     pinned = pin_threads() if options["pin"] else []
```

`README.md`:

```diff
diff --git a/README.md b/README.md
index a99870f..0f86b83 100644
--- a/README.md
+++ b/README.md
@@ -1,4 +1,4 @@
-<p align="center"><img src="docs/logo/lockup.svg" alt="rang-core" width="520"></p>
+<p align="center"><img src="https://raw.githubusercontent.com/gijzelaerr/rang-core/main/docs/logo/lockup.svg" alt="rang-core" width="520"></p>

 # rang-core

@@ -13,7 +13,7 @@ demonstrated novel algorithm.** The objective is better calibration and imaging
 at comparable cost, or comparable quality with substantially less computation.
 Neither advantage over state of the art has yet been established.

-[Research handoff/index](research/README.md) · [Latest progress](research/STATE.md).
+[Research handoff/index](https://github.com/gijzelaerr/rang-core/blob/main/research/README.md) · [Latest progress](https://github.com/gijzelaerr/rang-core/blob/main/research/STATE.md).

 Documentation: <https://gijzelaerr.github.io/rang-core/> (installation,
 concepts, the command line, the executed tutorials, the API reference and
@@ -33,16 +33,16 @@ receipts and archives written before then keep that name
 The active real-data flagging experiment trains an interpretable policy using
 the TV norm/maps of QuartiCal full 2×2 complex gains, with immutable original
 flags, recoverable backups, a flag budget and held-out checks.
-[Strategy, first negative result and reproduction](research/flagging.md) ·
-[Stimela2 recipe](history/recipes/tv-flagging.yaml).
+[Strategy, first negative result and reproduction](https://github.com/gijzelaerr/rang-core/blob/main/research/flagging.md) ·
+[Stimela2 recipe](https://github.com/gijzelaerr/rang-core/blob/main/history/recipes/tv-flagging.yaml).

-[Parallel diagnostic suite](research/flagging-parallel.md) now adds controlled
+[Parallel diagnostic suite](https://github.com/gijzelaerr/rang-core/blob/main/research/flagging-parallel.md) now adds controlled
 RFI/oracle tests, a verified SARAO calibrator sky, established flagger comparisons
 and measured patch-action learning. These small MeerKAT L-band pilots retain
 negative results; lower gain TV does not consistently mean better prediction,
 and no flagging or imaging superiority is established.

-[Latest flagging findings](research/flagging-findings.md): a TRAIN-only physical
+[Latest flagging findings](https://github.com/gijzelaerr/rang-core/blob/main/research/flagging-findings.md): a TRAIN-only physical
 gain-response surrogate predicts the counterfactual objective beyond the known
 flag cost (7.26× smaller matched-coverage RMSE in the held-out seed group), while
 legitimate smooth receiver phases change TV-guided decisions despite invariant
@@ -66,26 +66,26 @@ the antenna mean:
 Ranges cover three seeds and two shared-pointing settings. These are matched-family
 synthetic tests, not measurements of MeerKAT beam errors. Joint sky/beam/pointing
 inference has prior art; this result strengthens our baseline rather than proving
-novelty. [Experiment, controls and reproduction](research/antenna-beam-widths.md).
+novelty. [Experiment, controls and reproduction](https://github.com/gijzelaerr/rang-core/blob/main/research/antenna-beam-widths.md).

 Other findings:

 - **Relative and shared pointing must be distinguished.** The solver can impose
   exactly zero antenna-mean relative pointing, following Oleg Smirnov's feedback.
   An optional prior-constrained common trajectory is separate; its physical value
-  is not established by the zero-mean convention. [Common pointing](research/common-pointing-priors.md).
+  is not established by the zero-mean convention. [Common pointing](https://github.com/gijzelaerr/rang-core/blob/main/research/common-pointing-priors.md).
 - **Gaussian beams admit an exact pointing–sky–gain ambiguity**, including rotating
   elliptical beams when the compensating sky and gain freedom is available.
-  [Derivation and numerical controls](research/gaussian-gauge.md).
+  [Derivation and numerical controls](https://github.com/gijzelaerr/rang-core/blob/main/research/gaussian-gauge.md).
 - **Good residuals do not guarantee accurate astronomy.** Beam mismatch can bias
   flux even with nearly perfect injected-signal response. Relative-pointing
   interval coverage improves when antenna widths are fitted, but shared-mode
-  coverage remains less reliable. [Flux-bias control](research/first-results.md) ·
-  [Coverage experiment](research/antenna-beam-widths.md#separate-relative-and-common-uncertainties).
+  coverage remains less reliable. [Flux-bias control](https://github.com/gijzelaerr/rang-core/blob/main/research/first-results.md) ·
+  [Coverage experiment](https://github.com/gijzelaerr/rang-core/blob/main/research/antenna-beam-widths.md#separate-relative-and-common-uncertainties).
 - **Negative results are retained.** Earlier mode selection did not improve
   pointing accuracy over a fairly tuned joint fit. Polynomial gain compression
   fails when the fitted order is too low.
-  [Mode selection](research/spectral-pointing.md) · [Chromatic gains](research/chromatic-gains.md).
+  [Mode selection](https://github.com/gijzelaerr/rang-core/blob/main/research/spectral-pointing.md) · [Chromatic gains](https://github.com/gijzelaerr/rang-core/blob/main/research/chromatic-gains.md).

 ## Scope and limitations

@@ -103,9 +103,9 @@ pointing calibration or improved deconvolved images. Actual QuartiCal gain solve
 in the separate flagging pilots are visibility-space research diagnostics.
 Structured projection benchmarks are not end-to-end calibrator speedups.

-[Geometry and provenance](data/README.md) ·
-[Real-data inspection](research/measurement-set-inspection.md) ·
-[Compute benchmark](research/frequency-blocking.md)
+[Geometry and provenance](https://github.com/gijzelaerr/rang-core/blob/main/data/README.md) ·
+[Real-data inspection](https://github.com/gijzelaerr/rang-core/blob/main/research/measurement-set-inspection.md) ·
+[Compute benchmark](https://github.com/gijzelaerr/rang-core/blob/main/research/frequency-blocking.md)

 ## Run a small example

@@ -121,14 +121,17 @@ python3 -m venv .venv   # or: uv venv -p /usr/bin/python3.14 .venv, where ensure
 .venv/bin/python examples/pointing.py --output outputs/pointing
 ```

-Without Rust: a released wheel installs the core with no compiler,
-`pip install rang_core-<v>-cp310-abi3-manylinux_2_28_x86_64.whl` (or
-`pip install rang-core` once published; Linux x86_64 and aarch64, glibc 2.28 or
-newer, CPython 3.10 or newer, one abi3 binary for every version). The wheel
+Without Rust: `pip install rang-core` installs a released wheel with no
+compiler. There is one abi3 wheel per platform for CPython 3.10 or newer:
+Linux x86_64 and aarch64 (manylinux, glibc 2.28 or newer), macOS arm64 and
+x86_64, and Windows x86_64; each is tested on CPython 3.10 and 3.14 on its
+own OS by `.github/workflows/wheels.yml`. The wheel
 carries every kernel, the root crate's included (gain TV, phase trend,
 anchored response, projector, the pointing toy): the flagging chain and the
-notebooks run with no compiler. The Tricolour static masks and the archive
-drivers still read files from the checkout. Build wheels locally with
+notebooks run with no compiler. The Tricolour static masks are package data
+(`rang/data/`, with Tricolour's BSD notice); the archive drivers and
+comparators still read archived inputs from a checkout. `rang-core --version`
+prints the installed version ([CHANGELOG.md](https://github.com/gijzelaerr/rang-core/blob/main/CHANGELOG.md)). Build wheels locally with
 `bash tools/wheel/build.sh outputs/wheel-<date>-NN` (docker) and test them
 with `bash tools/wheel/test.sh outputs/wheel-<date>-NN outputs/wheel-<date>-MM`
 (`research/wheel.md`).
@@ -142,7 +145,7 @@ their archive). The Stimela recipes' Python 3.13 environment gets the same

 This smoke example fits smooth pointing with a fixed, correct Gaussian beam
 and sky; it is not the joint antenna-width campaign above. That campaign's
-command is in its [experiment report](research/antenna-beam-widths.md#implementation-and-reproduction).
+command is in its [experiment report](https://github.com/gijzelaerr/rang-core/blob/main/research/antenna-beam-widths.md#implementation-and-reproduction).
 Generated outputs belong in ignored `outputs/`; reusing a destination can replace
 previous generated files.

@@ -152,13 +155,13 @@ The original Rust toy also runs without Python dependencies:
 python3 examples/toy.py --seeds 7 --no-plot --output outputs/demo
 ```

-[Experiment guide](examples/README.md) · [Full local checks](CONTRIBUTING.md)
+[Experiment guide](https://github.com/gijzelaerr/rang-core/blob/main/examples/README.md) · [Full local checks](https://github.com/gijzelaerr/rang-core/blob/main/CONTRIBUTING.md)

 ## Next research decision

 For the active flagging objective, test structured multiscale flag proposals,
 noise/support-aware gain-TV diagnostics, signal preservation and independent
-MeerKAT L-band transfer. [Flagging research questions and go/no-go criteria](research/flagging-next.md).
+MeerKAT L-band transfer. [Flagging research questions and go/no-go criteria](https://github.com/gijzelaerr/rang-core/blob/main/research/flagging-next.md).

 The earlier pointing research has enough infrastructure to test a focused hypothesis: can selecting
 pointing/beam parameters using separate limits on signal distortion and
@@ -166,9 +169,9 @@ model-error contamination beat a well-tuned joint fit? The proposed decision rul
 is not yet implemented or validated. The next phase prioritizes a falsifiable
 quality/cost comparison, not further simulator expansion.

-[Current assessment and verification](research/status.md) ·
-[Future plan and go/no-go criteria](research/development-roadmap.md) ·
-[Prior-art boundaries](research/novelty.md)
+[Current assessment and verification](https://github.com/gijzelaerr/rang-core/blob/main/research/status.md) ·
+[Future plan and go/no-go criteria](https://github.com/gijzelaerr/rang-core/blob/main/research/development-roadmap.md) ·
+[Prior-art boundaries](https://github.com/gijzelaerr/rang-core/blob/main/research/novelty.md)

 ## Repository guide

@@ -241,7 +244,7 @@ quality/cost comparison, not further simulator expansion.
 ## Licence

 Rang is free software under the GNU General Public License, version 3 or (at
-your option) any later version; see [LICENSE](LICENSE). The user chose GPL on
+your option) any later version; see [LICENSE](https://github.com/gijzelaerr/rang-core/blob/main/LICENSE). The user chose GPL on
 2026-10-29 so that GPL-3 radio-astronomy tools such as WSClean and AOFlagger
 can be ported into the core. GPL-2-only upstreams cannot be combined with GPL-3
 code, so each upstream's exact licence is checked before porting it. Ported code keeps
```

### STATE paragraph

W4-5, the release metadata (big plan wave 4 fix task;
[w4-5-release.md](w4-5-release.md)), 2026-10-31 (implemented; measured):
`rang.__version__` and `rang-core --version` (`rang-core 0.1.0`) read the
one version in `pyproject.toml`, and a test checks that the three
`Cargo.toml`s, the lock files and `docs/conf.py` agree. The classifiers list
all five wheel platforms and Python 3.10–3.14; Documentation, Issues and
Changelog URLs are added; the frozen `flagging` extra is dropped. The
README renders on PyPI with no relative URL. `CHANGELOG.md` has a 0.1.0
section, and the release job uses it as notes. `release` and `publish`
refuse a tag that differs from the version before any upload. The actions
are on their Node 24 majors, and actionlint is clean. The sdist is 250
entries and 1.2 MB, down from 1,012 and 5.4 MB; it builds a wheel and runs
the wheel test subset on its own. check-all `overall: PASS`. The workflow has
not run on GitHub; a `workflow_dispatch` of the pushed branch is the next
check. v0.1.0 still waits on W4-1 and W4-3.

### `research/README.md` index entry

- [w4-5-release.md](w4-5-release.md): W4-5 release metadata for v0.1.0. It covers the version source and `--version`, the classifiers and URLs, the PyPI-safe README, the CHANGELOG, the tag-equals-version guard, the Node 24 actions, the sdist exclude list (250 entries, 1.2 MB) and the release procedure.

### User item for `research/big-plan.md` (replaces the PyPI/tag item)

- **Release v0.1.0** after W4-1, W4-3 and W4-5 are merged and `main`'s
  `wheels` run is green:
  1. In `CHANGELOG.md`, change the heading
     `## 0.1.0 (unreleased: dated the day v0.1.0 is tagged)` to
     `## 0.1.0 (<YYYY-MM-DD>)`.
  2. Commit that change and push it to `main`.
  3. From the `main` checkout, run
     `git tag v0.1.0 && git push origin v0.1.0`.

  The tag starts `wheels.yml`, which:
  - builds the five abi3 wheels and the sdist;
  - tests every wheel on CPython 3.10 and 3.14 on its own OS, with Cargo
    absent;
  - in `release`, checks that `v0.1.0` equals the version of every file
    and of `pyproject.toml`, extracts the `## 0.1.0` section of
    `CHANGELOG.md` and creates the GitHub release `v0.1.0` with the files
    and `SHA256SUMS`;
  - in `publish`, repeats the file-name check and uploads to PyPI as
    `rang-core` by trusted publishing (environment `pypi`, publisher
    already registered).

  A tag that does not equal the version fails before any upload. Check the
  result at <https://pypi.org/project/rang-core/>, then run
  `pip install rang-core && rang-core --version`.

  For a later release:
  1. Bump `pyproject.toml` and the three `Cargo.toml`s.
  2. Run `cargo metadata --offline --format-version 1 > /dev/null` in `.`,
     `core/` and `core/py/`.
  3. Move the "Unreleased" entries into a dated `## <version>` section.
  4. Commit, run check-all, push, tag `v<version>` and push the tag.

### `research/tool-timings.md` rows

| 2026-10-31 | big plan W4-5: `uv venv` + `uv pip install -e ".[pointing,beam,test,imaging]"` + tools | worktree | 245 s | – | includes the extension build |
| 2026-10-31 | big plan W4-5: `maturin sdist` (1.16.0) before / after the exclude list | worktree | 1.3 s / 1.0 s | – | 1,012 → 250 entries, 5,401,998 → 1,216,930 B |
| 2026-10-31 | big plan W4-5: `tools/wheel/build.py OUT --sdist` | worktree | 179.6 s / 181.2 s | – | host wheel (manylinux_2_35_x86_64) and sdist; `twine check --strict` 0.5 s, PASSED |
| 2026-10-31 | big plan W4-5: `maturin build --release --locked` from the unpacked sdist | sdist | 196.4 s / 194.0 s | – | then the wheel test subset from the sdist's tests, 15.7 s |
| 2026-10-31 | big plan W4-5: `actionlint` both workflows | worktree | 0.7 s | – | 0 errors |
| 2026-10-31 | big plan W4-5: `tools/check-all.sh` | worktree | 1278 s (lock wait included) | – | `overall: PASS`, log `outputs/w4-5-20261031-check-all.log` |

### `research/wheel.md`

Add one line under its remaining items: the sdist `exclude` list it asked
for is in place (W4-5, 250 entries).

### Ignored output directories

- `outputs/w4-5-20261031-01-sdist-before`: the sdist before the list, and
  its listing.
- `outputs/w4-5-20261031-02-sdist-after`: the first after-build, before
  `CHANGELOG.md` existed.
- `outputs/w4-5-20261031-03-accept` and `-04-accept`: the wheel, the sdist,
  `build.log`, `sha256.txt`, `sdist-list.txt`, and `*.timings.tsv` beside
  each. `-04` is the final run.
- `outputs/w4-5-20261031-check-all.log`.

Scratch in `~/Build/tmp/20261031-w4-5` is deleted.
