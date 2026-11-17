# E5 final: the v0.2.0 release review, early pass

Status, 2026-11-12: **early pass done on local main `2899c23` (origin/main `9f5a0b7` plus the sliced-read merge), everything except E3's
results; fixes on branch `claude/e5-final-early-b94bc5`.** After E3 lands, the review needs only the delta of section 6.
Finish-plan task E5 ([finish-plan.md](finish-plan.md) section 3, E) follows [e5-prereview.md](e5-prereview.md) (52 findings, E5-01 to
E5-52) and [w4-review.md](w4-review.md) (0.1.0). Classes as in the pre-review: **release-blocking** (a user following the docs gets a
wrong result or loses data, the release states something false, or it is legally wrong), **should-fix** (wrong but recoverable, or a
clear message missing), **note**.

**Rule for fixes during E2.** E2's acceptance runs use the code of main at `0477e54`/`9f5a0b7` from their own wheel venv. Nothing here
touches `core_config.py`, `core_pipeline.py`, `cal_*.py`, `core_ms*.py` (apart from one SPDX comment line), `core_flag*.py`,
`core_writeback.py`, `core_cli.py` or the Rust code paths, so no stage hash and no E2 result can change; findings there are listed for
the coordinator (section 5). The Rust files touched (`core/src/ms.rs`, `ffi_ms.rs`, `grid.rs`, `weights.rs`, `wgridder.rs`) change in
comments only.

## 1. Method

- Two read-only review agents, as in the pre-review: (A) every pre-review finding not plainly closed, re-verified on the code by
  quoting it or running it, plus the section-3 statements; (B) the code new since the pre-review (`353e620..b6e8b52`: `average_time`,
  `average_freq`, the sliced read, `flagversions`, `simtruth_ms`, the docs and the tutorial) and a malformed-configuration sweep of
  46 cases. Their notes, with file:line and reproducers: [results/e5-final-notes/](results/e5-final-notes/)
  (`e5f-prereview-recheck.md`, `e5f-new-code.md`; local paths replaced by `~`, `<scratch>`, `<worktree>`). Each finding fixed here was
  reproduced first.
- By hand: the wheel built from this branch in a fresh uv venv on `D:\rang\scratch\e5b` (public PyPI), its contents and metadata, the
  tutorial's chain from the installed wheel (`tools/e2e/run.py --installed`, as the `e2e` CI job), the tutorial notebook, the CLI page
  check, and a venv with the bare wheel (no extras). Section 4.
- CI on origin/main `9f5a0b7`: wheels run 43193119397 green (sdist, five wheels, five e2e jobs, ten test cells); docs run
  43193119430 green (notebooks including the tutorial, CLI page check, `sphinx-build -W`).

## 2. The finish line (section 1 of the finish plan)

| Item | Evidence | Verified at | State |
| --- | --- | --- | --- |
| 1. One command: `pip install rang-core`, then `rang-core run config.yaml my.ms` flags, calibrates, applies, images and self-calibrates an unseen L-band MS in full polarisation | Default `run.stages` is the full chain since E5-28 (`b58c0d0`); five stages exist (flag, calibrate, apply, image, selfcal; the task brief's "six" counts none extra). E2-B and E2-A run from a wheel venv. **A bare `pip install rang-core` lacks astropy**, which every polarisation solve and `apply.parang` need (Stokes I runs bare, FITS included): E2's wheel smoke 1 failed with `ModuleNotFoundError: astropy` ([e2-acceptance.md](e2-acceptance.md), amendment 2026-11-12) | `2899c23` | **Pending E2**; F-01 fixed on this branch |
| 2. Written back: FLAG with a backup, CORRECTED_DATA, MODEL_DATA, calibration tables, FITS, receipt; CASA, WSClean, QuartiCal read them | W1, C4b, G6 read-back; the e2e job checks every output on five platforms (run 43193119397); E5-01 to E5-03 fixed in the pre-review | `9f5a0b7` (CI) | Met on simulated data; real data with E2. Open: E5-02's gemclean part (F-02) |
| 3. Each stage against an oracle within a frozen tolerance | Tricolour (530 cells accepted, item 33), CASA and QuartiCal (C2a-C7, E0), WSClean (G3-G9); several gates "not met as frozen" are recorded in their notes and in [docs/limits.md](../docs/limits.md) | notes | **Pending E2** (A0's gates on E2-A, E2-B) |
| 4. Against CARACal on the same data | E3 running; not read here (firewall) | — | **Pending E3** |
| 5. Usable by someone else: tutorial, refusals, CI e2e on five wheels | Tutorial `notebooks/00-ms-to-image.ipynb` executes in docs CI; W4's 27 of 28 refusal cases; e2e green on all five wheels. The tutorial's real-data section is an E2 placeholder; the e2e chain has no selfcal stage | `9f5a0b7` | Met, with F-01 and the refusal-quality findings of section 5 |

## 3. Findings

New IDs F-01 onwards for this pass; pre-review IDs (E5-nn) and agent B's (NEW-nn) are kept where they apply.

### 3.1 Release-blocking

| ID | Finding | Where | State |
| --- | --- | --- | --- |
| F-01 | `pip install rang-core` (finish-line item 1, the README, the tutorial's "a plain `pip install rang-core` will do") does not run in full polarisation: astropy is only in the `imaging` extra, and every polarisation solve (Gpol, KCROSS, Xf, Df) and `apply.parang` calls `cal_pol.parallactic_angle`, which imports it (`cal_pol.py:66-69`). From the bare wheel this raises `ModuleNotFoundError: No module named 'astropy'` (reproduced, section 4), after flag has written; E2's wheel smoke 1 failed the same way. Stokes I runs: the bare wheel ran the tutorial's flag, calibrate, apply, image chain to FITS (gemclean writes FITS in Rust). The A1 generator (`simtruth`) and the `calmodels` spix path need astropy too | `pyproject.toml` `dependencies` | **Fixed** `4cf782f`: astropy in `dependencies`; test. A decision for the coordinator (section 5) |
| E5-02 | `gemclean -model-column DATA` overwrites DATA: `core/src/gemclean/cli.rs:485` takes it unchecked and gemclean writes the model column after imaging by default | Rust | **Fixed** on the coordinator's instruction (2026-11-12: E2 and E3 run from frozen wheel venvs): `model_column_error` refuses `-model-column DATA` and the column being imaged, explicit (`-data-column`) at parsing, chosen at run time (CORRECTED_DATA when present) before anything is read; exit 2, the message names the option; `-no-update-model-required` writes nothing and stays allowed. `gemclean -h` says so. Rust unit test and `tests/test_e5_final.py` (four refused forms, MS columns unchanged, the default still writes MODEL_DATA) |
| F-05 | `docs/licence.md` said fluxscale and applycal follow CASA's "documented behaviour" and "CASA's licence not checked", but the C2a-C2d, C4 and C6 ports and `core/src/flag_extend.rs` read CASA's C++ source (C1's 2023 mirror; V8 section 5) | `docs/licence.md`; the derived files | **Fixed**: the licence of every CASA file read, checked in the mirror `dic-case-studies/casa6` at `9269a52` (the one the ports read): `Calibrater.cc` GPL-2.0-or-later; `SolvableVisCal.cc`, `SolveDataBuffer.cc`, `StandardVisCal.cc`, `DJones.cc`, `XJones.cc`, `KJones.cc`, `VisCal.cc`, `Jones.cc`, `VisEquation.cc`, `CTPatchedInterp.cc`, `RIorAParray.cc` LGPL-2.0-or-later; `FlagAgentExtension.cc` LGPL-2.1-or-later (with ESO); casacore's `LSQFit.cc` LGPL-2.0-or-later; casatools' and casatasks' `LICENSE.txt` LGPL-2.0. All "or any later version", so compatible with GPL-3.0-or-later (the LGPL allows a copy under the GPL). `licence.md` lists CASA as ported; each derived file (8 Rust, 7 Python) names CASA under its SPDX line; `THIRD-PARTY-NOTICES.txt` has each file's notice verbatim. Not checked: casa6 6.7.6.14's own headers (`fluxscale.rs` cites that release; the 2023 files carry the same AUI notices) |
| E5-09 | Known limits stated nowhere a user reads | docs | **Fixed in part** `25329b5`: [docs/limits.md](../docs/limits.md) from the owner decisions, linked from the README and the docs toctree; the E2/E3 results are its placeholder |
| E5-10 | CHANGELOG Unreleased is the per-task log, with statements later entries undo (:289 "not chunked yet", :388 "until C7a", `core/target`, `extendflags`) | `CHANGELOG.md` | Open, editorial at E6. Three omissions added here (NEW-02, NEW-03, NEW-12) |
| E5-12 | The GPL ports carried no upstream copyright line, though README and `licence.md` say they do | `core/src/grid.rs`, `weights.rs`, `wgridder.rs` | **Fixed** `81e4cf8`: WSClean's lines from `debian/copyright` of wsclean 3.6-1 (its source files carry none), ducc0's verbatim from the 0.42.0 sources (PyPI sdist, SHA256 `4e11c59b…52ef`), in the headers and `THIRD-PARTY-NOTICES.txt`; test |
| E5-08 | `docs/concepts/imaging.md` and `concepts/index.md`: the wgridder "is not yet bound in the extension" | docs | **Fixed** `61c15a8` |

### 3.2 Should-fix

| ID | Finding | State |
| --- | --- | --- |
| F-03 | README status block, its question table, the landing page and `concepts/imaging.md` gave GeMClean's memory as 3-5 × WSClean's, the pre-G2 figure; G7's is 2.0-2.4 × on the pilot, and the table's speed figures predated G7 | **Fixed** `27a2e2c` |
| E5-17 | `docs/installation.md` hard-codes `rang-core 0.1.0`, untested | **Fixed** `61c15a8`: under `test_docs_version_agrees`, so the E6 bump fails until it changes |
| E5-29 | `docs/cli.md` has no `formats` or `config check` section; its intro promised refusals "naming the task" | **Fixed** `397ab0c` |
| E5-32 | `ingest.md`: creating tables needs python-casacore | **Fixed** `61c15a8` |
| E5-35 | README and landing page: "CPU and GPU", "carries every kernel"; the wheels have no `gpu` feature | **Fixed** `61c15a8` |
| F-04 (agent A NEW-1) | A build from a checkout targets x86-64-v3 (`.cargo/config.toml`) and crashes on CPUs without AVX2; the install docs did not say so (the sdist excludes `.cargo/`, so `pip install` from the sdist is not affected) | **Fixed** `61c15a8` |
| E5-49 DOC-17 | From-source steps POSIX only | **Fixed in part** `53ad094` (Windows form); recipe selfcal, carta and the meerkat compiler note open |
| NEW-04 | The tutorial says receipt version 4; the code writes 5 | **Fixed** `af5e038`; test |
| NEW-13 | `simtruth_ms.git_facts` crashes without git and, from a wheel, records whatever repository encloses site-packages | **Fixed** `af5e038`; test |
| NEW-02, NEW-03, NEW-12 | CHANGELOG: selfcal `refant: auto` "refused" (it runs); item 27's defaults missing (unset `calibrate.refant` = auto, selfcal refant, `image.niter` 1,000,000); the sliced read missing | **Fixed** `25329b5` |
| E5-16 | `test_w4_5_release.py` not run in the release job | Open (workflow; `publish` already needs `release`) |
| E5-25, E5-31 | No `flags restore` command; no example configuration or strategy in the package | Open (E5-25 touches `core_cli.py`) |
| E5-36 | `pypi` environment has no protection rule (`gh api`: `protection_rules: []`) | **Owner** (GitHub settings) |
| Protected | E5-19, 21, 22, 23, 24, 26, 27, 30, WB-14, NEW-05 to NEW-08, NEW-03's stage-hash part | Coordinator, after E2 (section 5) |

### 3.3 Notes

E5-44, 46, 47, 48, 50, 51, 52 (open, later; E5-52 now stated in `docs/limits.md`); agent A's NEW-2 (WSClean's licence written three
ways) and NEW-3 (`rang-core -h` does not list `--version`); agent B's NEW-09 to NEW-11, NEW-14, NEW-15; E5-33's CARACal follow-up and
E5-34's casacore-data licence, both external.

## 4. Hands-on checks

All under `tools/heavy_lock.py` in shared slots, on `D:\rang\scratch\e5b`, Python 3.14.10, uv venvs from public PyPI, no `PYTHONPATH`
(`rang.__file__` is the venv's site-packages). Commit: the branch at `7a3080a` (code identical to `2899c23` apart from comments).

- **Wheel build** (`maturin build --release`, local x86-64-v3 flags, so not the distributable baseline): 236 s;
  `rang_core-0.1.0-cp310-abi3-win_amd64.whl`, 4.5 MB, 125 files. Package data: both static masks, `TRICOLOUR-LICENSE`,
  `casacore_observatories.json`, `meerkat.itrf.txt`, `data/README.md`. `licenses/LICENSE` and `licenses/THIRD-PARTY-NOTICES.txt`
  (with E5-12's lines), a CycloneDX SBOM. Console scripts `rang-core = rang.core_cli:main`, `gemclean = rang.gemclean:main`;
  `rang-core --version` and `gemclean -version` print 0.1.0. `Requires-Dist`: numpy, pyyaml only (F-01).
- **sdist** (`maturin sdist`): `.gitattributes`, CHANGELOG, `CITATION.cff`, `Cargo.*`, LICENSE, PKG-INFO, README,
  `THIRD-PARTY-NOTICES.txt`, `pyproject.toml`, `core/`, `src/`, `python/rang`, `tests/`, `data/README.md`, `data/meerkat.itrf.txt`;
  no `.cargo/`, as E5-37 intended.
- **Tutorial chain from the installed wheel** (`tools/e2e/run.py --installed`, the `e2e` CI job): passed, 17 s (generate 5.8 s, run
  7.3 s). Peak 0.4957 Jy of 0.500, flagged 0.364, residual 0.70 mJy, beam 29.0″ × 4.97″, circular feeds refused with exit 2 and the
  MS unchanged; the same numbers as E4's CI runs.
- **CLI page check** (`docs/gen_cli.py --check` with the installed wheel): exit 0.
- **Tutorial notebook** (`notebooks/00-ms-to-image.ipynb`, nbconvert, installed wheel with `[imaging,notebook,plot]`): exit 0, 35 s.
- **Bare wheel** (no extras: numpy, PyYAML, rang-core): `rang-core run` with the tutorial's configuration on an A1 small MS (written
  with the full venv, since the generator needs astropy) exits 0; flag, calibrate, apply and image done, all five FITS files written.
  `rang.cal_pol.parallactic_angle` raises `ModuleNotFoundError: astropy` (F-01).
- **Wheel after F-01** (`0bb0109`, 232 s, `D:\rang\scratch\e5b\dist2`) in a bare venv (`venv-bare2`, `uv pip install` of the
  wheel only, public PyPI): `Requires-Dist` numpy>=1.26, pyyaml>=6, astropy>=6; astropy 8.0.2 resolved;
  `rang.cal_pol.parallactic_angle` runs (2.072 rad on a MeerKAT position). F-01 closed on Windows; only the CI cells show astropy
  resolving on every platform and Python.
- **Bare `pip install` chain after F-01:** `tools/e2e/run.py --installed` with `venv-bare2`'s `rang-core` (the wheel and its three
  required dependencies only, nothing else): passed, 14 s (generate 3.5 s, run 8.7 s: flag 0.9, calibrate 1.6, apply 1.1, image
  4.3), residual 0.705 mJy as in the CI runs. The first run of the whole chain from a bare install; output
  `D:\rang\scratch\e5b\e2e-bare2`. The wheel's `licenses/THIRD-PARTY-NOTICES.txt` has the CASA section.
- **Skip audit** (`pytest -rs -n 8`, worktree venv, run in the first final hold on `0bb0109`'s tree; the `a6ed448` check shows the
  same 78): every skip is an absent input or oracle run (ignored `outputs/`, E2/E3/E4 run directories, archived fixtures, Docker),
  an optional dependency this venv lacks (`[meerkat]`, python-casacore, casacure, pandas, nbconvert, ducc0, comrak), a platform
  (5 POSIX only, Windows symlinks, Linux-archived libm digits, the Linux deploy job), the GPU feature not compiled, or
  `RANG_NOTEBOOK_CARTA` unset. The skips that guard files this branch changed were run by hand: with comrak and readme_renderer
  installed for the run, `test_rendered_readme_has_no_relative_url` passed (README); with ducc0, `test_matches_ducc0_when_available`
  passed (`wgridder.rs`, comments only); the tutorial notebook (nbconvert, pandas) was executed from the `7a3080a` wheel (above),
  and the one cell changed since is text. The E5-02 and F-01 tests ran in the check. The tally keeps reasons, not test names. Not
  explained here: the sliced-read check's 1,282 passed against these 1,245 (another venv and head; its skip list was not compared).
- **Malformed configurations:** agent B's 46-case sweep (`e5f-new-code.md`, item 7): clear exit-2 messages except NEW-05 to NEW-08.
- **Docs site:** `sphinx-build -W --keep-going` of `docs/` (worktree venv, sphinx 9.2.0, notebooks not executed): no warning;
  `limits.html` built.

### 4.1 Full local check

First run on `4cf782f` (`RANG_ARCHIVE_OUTPUTS=\\wsl.localhost\Ubuntu\home\gijsm\Github\rang\outputs`, reachable, 828 entries;
heavy lock shared, 8 slots, because pytest runs 8 workers): 1,125 s, overall FAIL on two tests of this branch's own making, README at
161 lines and `e5-final.md` missing from the research index (fixed in `1a97c39`). Every other step passed: fmt, ruff, ruff format,
`git diff --check`, root build, test (23) and clippy, core build, test (268) and clippy, GPU clippy and test (274), extension build and
clippy, gain hashes; pytest 1,239 passed, 81 skipped. An earlier attempt was stopped before it ran: a heredoc had collapsed the UNC
path's leading `\\`.

Final run on `a6ed448` (the same archive, reachable; heavy lock shared, 8 slots, 12 GB), after E5-02 and F-05: **overall PASS**,
2,488 s (the host shared with queued work). fmt (root, core, extension), ruff, ruff format, `git diff --check`; root build, test
(23 passed, 1 ignored) and clippy; core build, test (269) and clippy; GPU clippy and test (275); extension build and clippy; pytest
1,245 passed, 78 skipped (section 4's skip audit); gain-hash gate PASS (5 hashes). Run record
`D:\rang\scratch\e5b\check-final2.json`. The run before it, on `0bb0109`, failed only
core clippy (`collapsible_if` on E5-02's two new `if` blocks), fixed in `a6ed448` with let-chains, no change of behaviour.

## 5. For the coordinator

**Branch** `claude/e5-final-early-b94bc5`, cut from local main `2899c23`; not pushed, not merged. Commits, one per fix:
`b6e8b52` SPDX, `81e4cf8` E5-12, `61c15a8` docs (E5-08, 17, 32, 35, F-04), `397ab0c` E5-29, `af5e038` NEW-04, NEW-13,
`27a2e2c` F-03, `25329b5` limits page and CHANGELOG, `53ad094` DOC-17, `4cf782f` F-01, `1a97c39` index, `47559c9` E5-12's
further notices, `86edab1` and `a6ed448` E5-02, `0bb0109` F-05; the rest are this note, its CHANGELOG lines and tool timings. The
full check passed on `a6ed448`; later commits touch `research/` and `CHANGELOG.md` only.

**E2 safety.** `git diff 2899c23 HEAD -- python/rang core src` touches `core_ms.py`, `ms.rs`, `ffi_ms.rs`, `grid.rs`,
`weights.rs`, `wgridder.rs` in comment lines only, and `simtruth_ms.py` (A1's generator, not on E2's or E3's path). No configuration
module changed, so no stage hash can change. F-01 changes the wheel's metadata, not E2's frozen wheel. Since then, on the coordinator's word
(E2 and E3 run from frozen wheel venvs): E5-02 changes `core/src/gemclean/cli.rs` (a refusal before imaging; nothing else in
gemclean's path) and F-05 adds comment lines under the SPDX line of `core/src/cal/*.rs`, `flag_extend.rs`, `rang.cal_*`,
`rang.applycal` and `rang.formats.caltable`; still no configuration module, so no stage hash.

**Stale after other merges.** `docs/limits.md`'s "Table lock on Linux only" goes stale if the ms-lock-windows worktree's branch
merges; update that line with it.

**Merging.** `CHANGELOG.md` will conflict with any branch that adds to Unreleased (take both). `docs/cli.md` is generated: run
`python docs/gen_cli.py` after merging anything that changes a help text or `config defaults`. `tests/test_spdx_headers.py` now has
no `PENDING` files, so a merged branch that adds an unstamped source file fails it.

**Decisions:**
1. **F-01, astropy required** (`4cf782f`): decided, the coordinator kept it (2026-11-12). It adds three wheels (astropy, pyerfa,
   astropy-iers-data).
2. **E5-36** (owner): the `pypi` environment still has no protection rule.
3. **E5-12's WSClean lines** come from Debian's `debian/copyright` (WSClean's files carry none) and include the Debian packager's
   line, the owner's own; kept verbatim.

**Protected findings, for after E2** (each would change code E2 runs; evidence in the two notes):
- E5-02 is no longer here: fixed on the branch (`86edab1`) on the coordinator's instruction.
- **Should-fix, Rust:** E5-30, `gemclean -h` to stdout with exit 0, then update `docs/gen_cli.py`'s `_gemclean_help`, which
  expects exit 2.
- **Should-fix, refusal quality:** NEW-05 (strategy YAML in flow style or a misspelt task: bare `KeyError`, `core_flag.parse_strategy`
  is a line parser; `config check` says valid), NEW-06 (missing strategy file, directory as strategy or mask pass `config check`),
  NEW-07 (unknown `refant` name passes `config check CONFIG MS`, calibrate tracebacks), NEW-08 (non-UTF-8 config: traceback).
- **Should-fix, stage hash** (each changes every stage hash once, so `--force`): E5-21 (referenced files by path only) and NEW-03's
  second part (the selfcal stage hash does not cover `calibrate.refant`, which now sets selfcal's default refant).
- **Should-fix, write-back and messages:** E5-19 (task IDs in refusals; receipt docstrings say version 3), E5-22, 23, 24, 26, 27,
  WB-14.
- **Notes:** NEW-09 (an empty strategy runs zero steps, exit 0), NEW-10 (`average_freq` with a `complex` term silently ignored, where
  `average_time` is refused), NEW-11 (`reader_slice` past the end).

**Environment.** At this review's start the main checkout's `python/rang/_core.pyd` was older than the sliced-read merge
(`2899c23`), so every MS read from `~/Github/rang/.venv` raised `TypeError: MsTable.read() takes 3 positional arguments but 4 were
given` (agent B, NEW-01). A `rang.check` was running in that venv later, which rebuilds it; check before using it. E2 runs from its own
venvs.

**CI.** No wheels run covers `2899c23` yet (the sliced-read merge is ahead of origin/main, and it changes `core/src/ms.rs`); the
push will run it.

**Full check:** section 4.1.

**Not done here:** E3's results (firewall); the CHANGELOG rewrite (E5-10, at E6); E5-25, E5-31, E5-16's release-job test.

## 6. After E3

The delta: read E3's report; fill the placeholders of `docs/limits.md` and the tutorial's section 6 from E2 and E3; finish-line items
1, 3 and 4 from E2's and E3's frozen reports; E5-09 and E5-10 at E6 (the 0.2.0 CHANGELOG section with Known limits linking
`docs/limits.md`); rerun section 4 on the release candidate's wheel.
