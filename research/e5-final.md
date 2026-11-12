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
| 1. One command: `pip install rang-core`, then `rang-core run config.yaml my.ms` flags, calibrates, applies, images and self-calibrates an unseen L-band MS in full polarisation | Default `run.stages` is the full chain since E5-28 (`b58c0d0`); five stages exist (flag, calibrate, apply, image, selfcal; the task brief's "six" counts none extra). E2-B and E2-A run from a wheel venv. **A bare `pip install rang-core` lacks astropy**, which every polarisation solve and `apply.parang` need (Stokes I runs bare, FITS included): E2's wheel smoke 1 failed with `ModuleNotFoundError: astropy` ([e2-acceptance.md](e2-acceptance.md), amendment 2026-11-12) | `2899c23` | **Pending E2**; packaging gap F-01 (release-blocking) |
| 2. Written back: FLAG with a backup, CORRECTED_DATA, MODEL_DATA, calibration tables, FITS, receipt; CASA, WSClean, QuartiCal read them | W1, C4b, G6 read-back; the e2e job checks every output on five platforms (run 43193119397); E5-01 to E5-03 fixed in the pre-review | `9f5a0b7` (CI) | Met on simulated data; real data with E2. Open: E5-02's gemclean part (F-02) |
| 3. Each stage against an oracle within a frozen tolerance | Tricolour (530 cells accepted, item 33), CASA and QuartiCal (C2a-C7, E0), WSClean (G3-G9); several gates "not met as frozen" are recorded in their notes and in [docs/limits.md](../docs/limits.md) | notes | **Pending E2** (A0's gates on E2-A, E2-B) |
| 4. Against CARACal on the same data | E3 running; not read here (firewall) | — | **Pending E3** |
| 5. Usable by someone else: tutorial, refusals, CI e2e on five wheels | Tutorial `notebooks/00-ms-to-image.ipynb` executes in docs CI; W4's 27 of 28 refusal cases; e2e green on all five wheels. The tutorial's real-data section is an E2 placeholder; the e2e chain has no selfcal stage | `9f5a0b7` | Met, with F-01 and the refusal-quality findings of section 5 |

## 3. Findings

New IDs F-01 onwards for this pass; pre-review IDs (E5-nn) and agent B's (NEW-nn) are kept where they apply.

### 3.1 Release-blocking

| ID | Finding | Where | State |
| --- | --- | --- | --- |
| F-01 | `pip install rang-core` (finish-line item 1, the README, the tutorial's "a plain `pip install rang-core` will do") does not run in full polarisation: astropy is only in the `imaging` extra, and every polarisation solve (Gpol, KCROSS, Xf, Df) and `apply.parang` calls `cal_pol.parallactic_angle`, which imports it (`cal_pol.py:66-69`). From the bare wheel this raises `ModuleNotFoundError: No module named 'astropy'` (reproduced, section 4), after flag has written; E2's wheel smoke 1 failed the same way. Stokes I runs: the bare wheel ran the tutorial's flag, calibrate, apply, image chain to FITS (gemclean writes FITS in Rust). The A1 generator (`simtruth`) and the `calmodels` spix path need astropy too | `pyproject.toml` `dependencies` | Open: proposed fix, astropy in `dependencies` (section 5); not changed during the full check |
| E5-02 | `gemclean -model-column DATA` overwrites DATA: `core/src/gemclean/cli.rs:485` takes it unchecked and gemclean writes the model column after imaging by default | Rust | Open, protected (rebuild); coordinator |
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
- **Malformed configurations:** agent B's 46-case sweep (`e5f-new-code.md`, item 7): clear exit-2 messages except NEW-05 to NEW-08.

## 5. For the coordinator

To be completed after section 4 and the full check.

## 6. After E3

The delta: read E3's report; fill the placeholders of `docs/limits.md` and the tutorial's section 6 from E2 and E3; finish-line items
1, 3 and 4 from E2's and E3's frozen reports; E5-09 and E5-10 at E6 (the 0.2.0 CHANGELOG section with Known limits linking
`docs/limits.md`); rerun section 4 on the release candidate's wheel.
