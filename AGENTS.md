# ra-ng working conventions

ra-ng is the project; `rang-core` is its first package. The project's
direction, audiences and scope are in `research/vision.md`.

This file is for every person and every coding agent (Claude, Codex or any
other) working in this repository. Part 1 applies to everyone. Part 2 applies
only to the owner and to agents working in the owner's checkout on the owner's
instruction; contributors can skip it. Task procedures for agents are in
`docs/agents/`; `.claude/skills/` holds thin wrappers that point there.

## Part 1: everyone

### Start here and leave a trail

- Read `research/README.md` for the research index and `research/STATE.md` for
  the latest progress before starting work. Gain-TV-guided flagging
  (`research/flagging-verdict.md`) and beam and pointing
  (`research/b1-3-pointing-selfcal.md`) are both closed as null.
- Save meaningful progress, exact run paths, seeds/settings, provenance, checks,
  rejected/null outcomes and next steps in the repository as work proceeds.
  Distinguish proposed, implemented and measured work. Link compact result
  archives; raw observations and generated checkpoints belong in ignored outputs.
- Record negative and null results as carefully as positive ones; do not drop a
  failed arm, seed or protocol. Keep scientific status and handoff links current.
- Wall-time pipeline tool runs and add a row to `research/tool-timings.md`
  (name the host when it is not the one in `research/STATE.md`).

### How changes reach main

- Contributors and their agents open a pull request against `main` from a
  branch or fork; `CONTRIBUTING.md` gives the route.
- CI on a pull request: `tests` (ruff, ruff format, cargo fmt, clippy with
  warnings as errors, cargo test for the root crate and `core/`, pytest on Linux
  and Windows against the branch's extension), `docs` (notebooks on the public
  fixture, the CLI page check, `sphinx-build -W`), and `wheels` when the pull
  request touches `core/`, `src/`, `Cargo.*`, `.cargo/`, `pyproject.toml` or
  `tools/wheel/`. CI has no archives or oracles (CASA, QuartiCal, WSClean), so
  their gates still need the full local checks (`python -m rang.check`, after
  `maturin develop --release`); report the result in the pull request.
- Never force-push a shared branch; never rewrite `main`.
- Commit under your own name and address. An agent commits as the person it
  works for, never under an agent or bot identity of its own.
- AI attribution trailers (co-author lines, generated-by footers): the project
  prefers commits without them; contributors decide for their own commits.

### Claims

- A change that claims a scientific or performance gain brings, before it is
  merged: a proposal note in `research/` (hypothesis, data, settings, decision
  rule) committed before the code that tests it; a frozen tolerance; an oracle
  (the upstream tool or reference path the result is checked against); and the
  measurement, with its run paths, seeds and receipts. Later changes to the
  protocol are dated and labelled post hoc. `research/f3-flagger.md` is a
  worked example.
- Novelty must target demonstrably higher calibration/imaging quality at
  comparable cost, or comparable quality with materially lower runtime/resource
  use than a relevant state-of-the-art method. Wins against weak baselines and
  software reimplementations alone do not establish novelty. Record matched
  accuracy/cost comparisons and negative results.
- Validate numerical correctness before claiming performance or scientific
  improvements.
- Share a host through `tools/heavy_lock.py` (the main checkout's copy): builds,
  tests, the full check and campaigns as shared jobs,
  `run --slots N --mem G -- <command>` with honest thread and memory figures;
  timing and tuning runs exclusive (`run -- <command>`), which waits for an
  otherwise idle host. Keep the host busy; don't oversubscribe it.

### Layout

| Path | Contents |
| --- | --- |
| `python/rang` | the Python package and the `rang-core` command line |
| `core/`, `src/` | the Rust core (`core/py` builds the extension `rang._core`); the root crate |
| `history/` | the frozen campaigns' recipes, containers and modules |
| `research/` | reports and compact result archives |
| `docs/`, `formal/` | the documentation site (task procedures in `docs/agents/`); Lean proofs |

`notebooks/`, `examples/`, `recipes/`, `tests/`, `tools/` and `data/` hold what
their names say. Raw data and run outputs go in ignored `outputs/`.

### Scope

- ra-ng aims to be the home for agentic radio astronomy: beginners learn from
  notebooks and by asking questions, astronomers make science-grade images and
  time series, algorithm scientists improve the code and contribute it back.
- MeerKAT first (`research/meerkat-scope.md`); keep LOFAR in mind, with
  telescope specifics behind the existing boundary, and do not generalise before
  a second telescope's data and oracle exist.
- Time series means pulsars and transients (FRBs, GRBs); new scope,
  scoped in a note before anything is built.
- Use GPU acceleration where it pays, but stay cross-platform: every GPU path has
  a CPU path with the same result within a written tolerance.
- Use simulations and comparisons to test research hypotheses; distinguish proposed methods, implemented methods and measured results.
- Preserve reproducible experiment settings, seeds, data provenance and relevant negative results.
- Inspect CARACAL's shipped MeerKAT strategies and flag-worker semantics when
  verifying flagging methods; a reduced kernel ablation is not a full CARACAL baseline.

### Implementation languages

- Use Rust for computational kernels and performance-sensitive simulation and calibration work.
- Use Python for astronomer-facing interfaces, experiment scripting and pipeline orchestration.
- Install Python packages from public PyPI only (`https://pypi.org/simple`).
- The owner explicitly requested JAX DFT prediction and automatic
  differentiation for the smooth pointing-solver reference path; retain it and
  the existing Rust baseline.

## Part 2: the owner only

These rules hold for the owner and for agents working in the owner's checkout on
the owner's instruction. They do not apply to contributors.

### Commits and pushes

- The owner commits to main directly and authorizes regular pushes of verified
  checkpoints to origin/main so astronomers can follow progress. Run the full
  local checks before every commit; push normally, never force-push.
- Always use `gijsmolenaar@gmail.com` for non-Spotify or public work, including
  this repository. Do not use a Spotify email for Rang commits.
- Commits use the owner's Git identity. Do not substitute an agent or bot identity.
- Never add agent signatures, AI attribution, generated-by footers or co-author
  trailers to commit messages. Never name Codex or OpenAI as a co-author. Never
  include a Spotify email address in a Rang commit message, author or committer
  identity.
- Use public PyPI only, never the Spotify package registry.
- Follow the owner's global Git and pre-commit verification rules.

### Coordinator habits

- The owner's main checkout stays on `main`; branch work goes in a worktree
  (`~/Worktrees/rang/<branch>`), merged and pushed by the coordinator.
- Plans and their open owner decisions live in `research/` (now
  `research/finish-plan.md` and `research/vision.md`); a task's report ends with
  a section for the coordinator. A background task keeps
  `outputs/status/<task>.md` (under 15 lines, updated at least every 30
  minutes) and hands back in about 15 lines.
- Development runs natively on Windows; WSL only for the Linux oracles. Large
  data goes on `D:\rang`, not C:.
