# Docs audit, 2026-11-13

Status: **implemented** on branch `docs-polish` (from origin/main `2a02470`); not merged. Documentation only: no code
behaviour changed. Scope: `docs/`, `notebooks/` (read, not edited), `README.md`, `CONTRIBUTING.md`, for the three
audiences of [vision.md](vision.md) section 1. Not touched, by instruction: `docs/cli.md` (generated),
`docs/agents/check-and-ci.md`, `AGENTS.md`, `tools/`, `python/rang/check.py`, `python/rang/core.py`.

Method: every page read; statements checked against the code (`core_cli.py`, `core_config.py` through `docs/cli.md`,
`core/src/gemclean/cli.rs`, `tools/e2e/run.py`, `rang.formats`), against the reports they cite, and against PyPI
(`rang-core` has one release, 0.1.0) and the `v0.1.0` tag. Numbers were copied from the reports, not from other pages.

## 1. The path per audience

| Audience | Before | After |
| --- | --- | --- |
| Beginner | Landing page bullet "New to radio astronomy?" to the tutorials index (a long catalogue); no glossary; no one-page overview; the agent procedure said the introductory track "does not exist yet" | Landing table, row 1 → `learn/index.md` (the I1–I9 route with the MS-to-image tutorial at step 7, how to ask an agent, how to run the notebooks) → `concepts/basics.md` (the chain in one page, each section pointing at its notebook) → `glossary.md` |
| Astronomer | Landing → installation (`pip install rang-core`, which installs 0.1.0 without the chain) → the tutorial notebook; the agent procedure was the only how-to; no page on calibration configuration, flag restore or checking results | Landing row 2 → `installation.md` (0.1.0 caveat, source install) → `quickstart.md` (commands only, A1 small, about a minute) → `howto/` (image your MS, calibrate incl. full polarisation, flag and restore, check results) → `limits.md` |
| Developer | Landing → contributing (PR route, check list); no architecture page; the claims rule only in AGENTS.md and the agent procedure | Landing row 3 → `developer/index.md` (the layers Python → PyO3 → C ABI → kernels, where things are, build, test, the conventions tests enforce, agents) → `developer/claims.md` (the four requirements, what counts as novelty, ports as parity with their measured gates, negative results, the digest) → `contributing.md` |

Navigation: the sidebar now has one caption per audience (Start, Learn, Astronomers, Developers), then Reference
and Project. Theme: furo with the logo's amber as brand colour (darkened to `#a8640f` in light mode for 4.5:1 link
contrast), keyboard navigation, view/edit buttons. No new Sphinx extension (a new one would change `pyproject.toml`
and trigger the wheels workflow); the landing table uses MyST's `list-table`.

## 2. Stale or wrong statements

| # | Where | Statement | Evidence | State |
| --- | --- | --- | --- | --- |
| S1 | `installation.md`, README, landing page | `pip install rang-core` gives the chain and `gemclean` | PyPI has only 0.1.0 (2026-11-02); the `v0.1.0` tag has no `core_pipeline.py`, no `flag`/`calibrate`/`run`/`config` commands, no `gemclean` script | **Fixed**: installation note, README install line (same line count), landing table, quickstart and how-to index say "from source until 0.2.0" |
| S2 | `limits.md` | "Table lock on Linux only" | [ms-lock-windows.md](ms-lock-windows.md): `LockFileEx` on Windows; macOS keeps the stub; WSL casacore does not see it; `concepts/ingest.md` already said so (E5 final, section 5, predicted this) | **Fixed** |
| S3 | `limits.md` | E2 and E3 "are running" | STATE and [handoff-2026-11-13.md](handoff-2026-11-13.md): paused; E2-B scored on an unmerged branch; E2-A and E3 not reported | **Fixed**; no E2 number quoted (none is on `main`) |
| S4 | `docs/research/index.md` section 2 | a flagger trained on gain TV "was not tested; it is the next experiment" | [f1-tv-flagger.md](f1-tv-flagger.md): NO-GO at go/no-go; [f2-flagger.md](f2-flagger.md), [f3-flagger.md](f3-flagger.md): outcome F | **Fixed**; new section 7 (F1–F3) with the reports' numbers |
| S5 | `docs/research/index.md` | the story stopped at the gridder; nothing on GeMClean or the user chain | G5, G6, G7, G9, E1, C5, C5b | **Fixed**: section 8, G7's figures as [g7-defaults.md](g7-defaults.md) gives them (1.52× at `-j 16`, 1.31× slower at `-j 1` natively; level and 1.24× slower on WSClean's OS layer; memory 2.0–2.4×), E1 "no gate met as frozen", selfcal model absorption |
| S6 | `installation.md` | Stimela needs "Python 3.13" | `pyproject.toml`: `python_version < '3.14'`; README says "3.13 or older" | **Fixed** |
| S7 | `installation.md` | "Native Windows runs the test suite; for campaign work use WSL2" | STATE 2026-11-09, CONTRIBUTING: development and the full check run natively on Windows; WSL only for the Linux-only oracles and `history/` | **Fixed** (macOS stated as built and tested in CI, not as a full-check host: not verified) |
| S8 | `docs/agents/answer-a-question.md` | the introductory track "is proposed ... and does not exist yet" | `notebooks/intro/` I1–I9 merged 2026-11-11 | **Fixed**: sources list now starts with basics, glossary, the track |
| S9 | landing page | status box named one learned flagger only | F1–F3 | **Fixed**: "three learned flaggers stopped or failed as frozen" |
| S10 | `docs/tutorials/index.md` | "Its section on real data is a placeholder until task E2 has results" | still true | Left (correct) |
| S11 | `docs/agents/image-a-meerkat-ms.md` | `gemclean` "not yet in a release: the 0.1.0 wheel on PyPI lacks it" | true; but the chain is missing from 0.1.0 too | Left (the procedure already requires a source install for `gemclean`); see L4 |

Checked and correct (no change): the status box's null verdicts and their links; GeMClean memory 2.0–2.4× (F-03 had
already fixed the 3–5× figure); the Tricolour 530-cell difference (finish-plan item 33); receipt version 5; the e2e
numbers (flagged 0.364, peak 0.4957 Jy, residual 0.70 mJy, beam 29.0″ × 4.97″, from `tools/e2e/run.py` and
[e4-tutorial.md](e4-tutorial.md)); the config keys quoted on the new pages (from `rang-core config defaults` as
`docs/cli.md` prints it); gemclean's `-model-column` refusal (E5-02, in `core/src/gemclean/cli.rs`); the
`-report.json` fields; `rang.formats.flagversions.restore`. Absolute polarisation angle: the new calibrate page and
`limits.md` say only that it is under investigation.

## 3. Broken links

A script mirroring `tests/test_d1_docs.py::test_repository_links_exist` plus a `{doc}` resolver over every page:
none broken after the changes. One self-inflicted case (a literal `` `{gh}` `` in prose parsed as a link) was found
by it and reworded. `sphinx-build -W` and the tests: section 5.

## 4. New pages

| Page | For | Content |
| --- | --- | --- |
| `docs/quickstart.md` | astronomer | source install (Linux/macOS and Windows), A1 small, `config check`, `run`, the run directory, resume, CI's numbers, `gemclean` directly |
| `docs/learn/index.md` | beginner | the route I1–I9 with the tutorial, the interactive page, asking an agent, running the notebooks |
| `docs/concepts/basics.md` | beginner | instrument, measurement equation, flagging, calibration, self-calibration, imaging, checking, time domain; one notebook per section |
| `docs/glossary.md` | all | Sphinx glossary of the terms the pages use |
| `docs/howto/index.md`, `image-your-ms.md`, `calibrate.md`, `flag.md`, `check-results.md` | astronomer | configuration for your fields, refusals, run and resume, outputs; CARACal's 1GC and full-polarisation terms with their limits; strategies and flag restore; receipts, tables, images, comparing with WSClean and CARACal |
| `docs/developer/index.md`, `claims.md` | developer | architecture, layout, build, test, enforced conventions; the claims rule with the ports' measured gates and the negative record |

## 5. Checks

- GitHub `docs` workflow on `5bc8b0f` (run 43379688451, ubuntu, green): extension build 251 s, the notebooks on the
  public fixture (`RANG_NOTEBOOK_LUNO=0`, I6-I8 from the nightly cache) 112 s, the CLI page check 4 s,
  `sphinx-build -W --keep-going` 28 s, no warning. On `2a9378d` (run 43375892773) green too.
- Locally: `tests/test_w4_8_docs.py` README and research-index tests (6 passed); ruff and ruff format on `docs/conf.py`;
  the link script of section 3.
- **Not run locally:** the extension build in the worktree venv waited 64 min in `tools/heavy_lock.py` behind an
  exclusive `cold_build_bench.py` (pid 36400) and was withdrawn once CI had built and checked the same commit. So no
  local `sphinx-build`, no local notebooks job, and the quickstart commands were not run by hand; they are the
  commands of `tools/e2e/run.py` and `notebooks/00-ms-to-image.ipynb`, which CI runs.

## 6. Left

- L1. `limits.md` and the tutorial's real-data section stay placeholders until E2 and E3 report (E5 final, section 6).
- L2. No `rang-core flags restore` command (E5-25, code); `howto/flag.md` documents the Python and CASA routes.
- L3. No example configuration or strategy in the package (E5-31): the how-to pages point at the checkout's
  `examples/ms-to-image/` and E2-B's frozen configuration.
- L4. After the v0.2.0 release, remove the "0.1.0 lacks the chain" notes (installation, README, landing page,
  quickstart, how-to index, the agent procedure) and switch the quickstart to `pip install rang-core`.
- L5. CHANGELOG Unreleased is still the per-task log (E5-10, at E6).
- L6. The concepts pages (`ingest`, `gains`, `flagging`, `imaging`) describe the research-era ports; they do not yet
  cover the CASA-style calibration terms (C2–C6), which only `howto/calibrate.md` describes.
- L7. No figures were added: the executed notebooks carry the plots; no existing output figure fitted a page
  without copying a notebook's.
- L8. The macOS full local check is not verified anywhere; the installation page says only that CI builds and tests
  the macOS wheels.

## For the coordinator

- Branch `docs-polish` (pushed), commits `2a9378d` (stale-statement fixes, research story 7-8), `5bc8b0f` (new pages,
  landing, theme), and this note's completion. Not merged. Documentation and `docs/conf.py` theme options only.
- Merging: `research/README.md` and `research/tool-timings.md` take one line each (take both on conflict); no file
  that the speedup-tools branch touches was edited.
- Before merge, if wanted: a local `python -m rang.check` (not run here, see section 5); docs CI is green.
- At v0.2.0 (E6): L4, remove the "0.1.0 lacks the chain" notes; at E2/E3: L1.
