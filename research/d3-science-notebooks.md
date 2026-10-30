# D3: the two research questions as guided science notebooks

Big plan task D3 ([big-plan.md](big-plan.md), "Documentation, teaching and
upstream fixes"), branch `d3-science-notebooks` from main `b49eac2`.
Status: **implemented; executed and built locally and on a clean export;
documentation only, no new scientific result.** Every number the notebooks
show is read from a committed archive under `research/results/` or computed
by a live cell; the frozen rules are quoted from module constants. Nothing
was pushed; the site renders the notebooks on the first workflow run after
the merge.

## What exists

| File | What |
| --- | --- |
| `notebooks/science/06-gain-tv-flagging-the-experiment.ipynb` | the flagging question to its verdict |
| `notebooks/science/07-beam-and-pointing.ipynb` | the original beam and pointing question, the toy, B1-0 and B1-1, B1-2/B1-3 as proposed |
| `python/rang/notebook/science.py` | archive readers, live helpers on the Rust toy and the fixture, plots (bare `Figure`s), the quoted B1 rules |
| `tests/test_d3_notebooks.py` | readers against the committed JSON, the quoted rules against the protocol text, JAX against Rust, one audit against its archive, both notebooks executed through papermill with every switch off (16 tests) |
| `docs/execute_notebooks.py`, `docs/conf.py` (`_copy_notebooks`, `_write_constants`), `docs/tutorials/index.md` | the science glob, the flat copy, two new quoted-constant snippets, the toctree and the switches |

No widgets: the science notebooks are read top to bottom; D2's steering
panels (notebooks 2–5) stay the interactive layer.

### Notebook 6: gain-TV-guided flagging, the experiment and its verdict

What it teaches, in order:

1. **The question and the method**: gains, the gauge-fixed TV map as
   guidance, the policy score and the selection objective written
   symbolically, with the frozen values printed from `rang.core_campaign`
   (`science.flagging_rules()`: split seed, grid, iterations, τ, α, budget,
   flag penalty, validation weight and tolerance, call band, Briggs
   robustness) and the decision rule from `experiment.DECISION_RULE`; the
   cost limit from task K's archive (`cost_clause.limit_ratio`).
2. **The method live on the fixture** (exploratory): the original solve's
   TV map, the arms (original, comparator, TV policy), the loop's
   candidates, the frozen calls on the replay, with a caveat cell on why a
   first-pass comparator makes the replay's test MSE undecidable.
3. **What the real data said** (archive): the wave 3 map (K, L1, L2, L1-M,
   C1, A1, L5, L4, L3 with archive and presence); a live run of
   `examples/verdict_tables.py --check`; the verdict in three sentences built
   from `flagging-verdict.json`; calls per campaign and outcome (checked
   against the archive's own summary); a figure of every decidable ratio
   against the null band with the undecidable counts; the headline pairs;
   the TV policy's selections; the cost clause table and figure.
4. **Was something else the cause?** (archive): L1-M's model calls, C1's
   closure-TV statistics, L5's whole-array solves, A1's emptied
   station-bins, O-CASA's matched crosscal baseline, with a generated
   paragraph that reads each number from `context`; the fixture era.
5. **What the null does and does not say**, and **what would reopen it**:
   L3, native flags and weights (text only, no numbers).
6. **Replay task K** from a local slice, behind `RANG_NOTEBOOK_LUNO=1`
   (needs the slice and CARACAL's strategy files; compares the replay's
   headline ratio with K's archived one).

Archives read: `flagging-verdict.json` (calls, `tv_policy_selections`,
`cost_clause`, `context`, `summary`), `core-k-luno-campaign.json`
(`cost_clause.limit_ratio`, `hypotheses` for the replay), and the presence of
`luno-array-campaign.json`, `luno-1830-campaign.json`,
`l1-model-completeness.json`, `c1-closure-arm.json`, `a1-rfi-audit.json`,
`l5-solver-science.json` for the wave 3 map; the verdict check reads every
archive `examples/verdict_tables.py` reads.

### Notebook 7: beam and pointing, the original question

1. **The forward model** with beams, rotation and pointing; the Rust toy
   fixture (`rang-toy --pointing-reference`) summarised; the JAX DFT and its
   `jacfwd` Jacobian against Rust's visibilities and analytic Jacobian
   (live: 1.1e-11 Jy and 2.1e-13 Jy/arcmin).
2. **The Rust experiment** (`rang.run_experiment`, live, seed 7, correct
   beam and a 2 % wider true beam) beside the 20-seed archive
   `beam-width-campaign.json`.
3. **The smooth pointing solver** (JAX, live) on examples/pointing.py's
   design, beside `smooth-pointing.json` (the live run reproduces the
   archived 2.005″ RMSE and 2.635 → 0.950 mJy held-out RMS to the printed
   digits), with a trajectory figure.
4. **Observability**: the Gaussian gauge and why rotation of an elliptical
   beam breaks it (`sky_locked_information`, live on five cases); gains and
   thinned coverage (live, compared with `gain-observability.json`: largest
   difference 2e-14″); the katbeam chromatic-shape ablations (archive
   `katbeam-observability.json`; live native/no-rotation cases behind
   `RANG_NOTEBOOK_SLOW=1`, about 30 s of JAX compilation); the information
   budget (archive `information-budget.json`).
5. **B1-0** (archive `b1-beam-product.json`): the B1 task table (B1-0 and
   B1-1 (i) measured, B1-1 (ii), B1-2, B1-3 proposed); the 30″-offset unit
   computed live from katbeam; the three gates; katbeam and EIDOS against
   the holography beam (table, per-channel figure, antenna spread figure).
6. **B1-1 (i)**: the ported SARAO/SKA Gaussian fit run live on the five
   fixture scans (gate G1a reproduced, 8.9e-16; the per-antenna estimate and
   its formal σ); G1b (the fit's bias against the measured beam) shown from
   `b1-baselines.json` when it is committed or its ignored run directory is
   present, otherwise a pointer to the report.
7. **The holography maps**, behind `RANG_NOTEBOOK_HOLOGRAPHY=1` and only if
   the product exists locally (array-average Stokes I beam at three
   frequencies and katbeam minus holography).
8. **B1-2 and B1-3, proposed**: the frozen B1-2 decision rule, the four
   B1-3 metrics and the B1-3 win and matched-cost rules, quoted from
   `science.B1_2_DECISION_RULE`, `B1_3_METRICS`, `B1_3_DECISION_RULE`,
   `B1_3_MATCHED_COST`; no result is reported (B1-2 runs in another task).

Archives read: `b1-beam-product.json`, `beam-width-campaign.json`,
`smooth-pointing.json`, `gain-observability.json`,
`katbeam-observability.json`, `information-budget.json`, and
`b1-baselines.json` when available.

### The switches

| Variable | Notebook | Default | Gates |
| --- | --- | --- | --- |
| `RANG_NOTEBOOK_LUNO=1` | 6 | off | task K's replay on a local slice |
| `RANG_NOTEBOOK_SLOW=1` | 7 | off | the katbeam audit (long JAX compile) |
| `RANG_NOTEBOOK_HOLOGRAPHY=1` | 7 | off; `docs/execute_notebooks.py` forces it off | maps of the local holography product (CC BY-NC 4.0) |

Each gated cell prints `skipped: set NAME=1 to …` when off.

## Measured (2026-10-30, WSL2 host)

**CI emulation** (script, log, maturin log and notebook timings kept in the
ignored `outputs/d3-20261030-ci-emulation/`; the scratch tree was deleted): a
clean `git archive` of `197477f` (no `outputs/` link, so no CARACAL strategy
files, no G1b archive, no holography product), a fresh `uv` venv on Python
3.14, then the workflow's steps in order with `CARGO_BUILD_JOBS=4`, load
average 4–7:

| Step | Wall | Peak RSS |
| --- | ---: | ---: |
| `maturin develop --release --locked --extras docs,notebook,imaging,pointing,beam` (cold) | 149.3 s | 1.09 GB |
| `download_fixture` (cached copy, hash verified) | 0.49 s | 41 MB |
| `execute_notebooks.py`, seven notebooks in series | 102.9 s | 870 MB |
| `gen_cli.py --check` | 6.2 s | 35 MB |
| `sphinx-build -W --keep-going` with executed notebooks | 33.4 s | 387 MB |

Notebooks: 01 10.7 s, 02 4.7 s, 03 7.9 s, 04 14.8 s, 05 9.3 s, **06 10.3 s,
07 40.3 s** (98.0 s in all; D1 measured 25.4 s for the five at load 1–4).
Sphinx: **0 warnings**; site 17 MB (D1: 14 MB). Both science notebooks
executed with no error output; 06 ran its replay on the `teaching` strategy
and printed the LUNO skip line; 07 printed the SLOW and HOLOGRAPHY skip lines
and the G1b pointer (no archive in a clean export), and ran G1a live (pass).
The science notebooks add about 51 s to the build job, inside its 20-minute
limit; not measured on GitHub.

**In the worktree** (the `outputs` link present, so CARACAL's first pass is
the replay's comparator and G1b is shown from the ignored archive):
papermill 06 11.6–12.5 s, 07 28.0–29.8 s, 0.83–0.86 GB.
`pytest tests/test_d3_notebooks.py`: 16 passed in 30.6 s (both notebooks
executed concurrently, 22–25 s); with `tests/test_d1_docs.py` (strict Sphinx
build included) 20 tests in 45–47 s.

**Every switch on** (once, in the worktree, into scratch; the executed
copies held holography maps and were deleted): notebook 06 in 15.6 s
(0.93 GB) with the task K replay printing the archived headline
0.9999388271363914 on both lines (additions 0 and 128, as archived); notebook
07 in 76.4 s (1.03 GB) with `katbeam_audit_live` giving 7.958/7.998″ (the
archive's native H case) and `holography_figure` drawing the array-average
beam at 950, 1284 and 1600 MHz and katbeam's difference (±0.6 % of on-axis
at 1284 MHz). No code changed after this run.

**Live against archive** (every live number with an archived twin): JAX
against Rust 1.1e-11 Jy and 2.1e-13 Jy/arcmin; smooth pointing 2.005199″,
2.635416 → 0.950358 mJy (archive identical to the digits shown); symmetry
and gain audits within 2e-14″ of `gain-observability.json`; katbeam native H
7.958/7.998″, and 5.395/5.706″ with flux priors (live in a probe, 23 s;
archive identical); G1a 8.9e-16 (as the B1 report).

## Deviations

- **Notebook 6's LUNO switch is opt-in** (`RANG_NOTEBOOK_LUNO=1`, as the
  brief asks), while notebooks 1 and 5 run their LUNO sections whenever a
  slice is found unless `RANG_NOTEBOOK_LUNO=0`. The tutorials page says so.
  The documentation workflow's `RANG_NOTEBOOK_LUNO=0` keeps all of them off.
- **The B1-1 (i) port is loaded from `examples/b1_baselines.py`** with
  `importlib` from the checkout (`science.b1_baseline_module`), not imported
  from the package: the port lives in `examples/` (not an owner file here).
  Outside a checkout the cell prints a skip line. Moving the port into the
  package (say `rang.pointing_baseline`) would make it importable from a
  wheel.
- **G1b is not on the public site yet**: its archive exists only in the
  ignored `outputs/b1-20261030-10-baseline-g1b/b1-baselines.json`. The reader
  looks in `research/results/` first, so committing the file (below) puts
  G1b on the site with no code change.
- **B1 rules as module constants copied from the protocol** (not extracted
  at run time), with a test that each is a verbatim (whitespace-normalised)
  substring of `research/b1-beam-pointing.md`, so a wheel user sees them and
  they cannot drift.
- **`docs/execute_notebooks.py` forces `RANG_NOTEBOOK_HOLOGRAPHY=0`**, so a
  stray environment variable can never publish the CC BY-NC maps.
- **The test executes with papermill** (as the site does), not nbconvert as
  D2's test does; it skips without the `docs` extra.
- Prose with numbers is generated by code cells from the archive values;
  markdown cells carry only design settings (noise levels, throws, frozen
  thresholds) and no results.

## Open items

- `rang.notebook.__init__` does not list `science` in `__all__` (a shared
  file); `from rang.notebook import science` works regardless, and the API
  pages pick the module up through autosummary's recursion. Hunk below.
- Notebook 5's closing section predates L2, L1-M and the verdict (hunk
  below).
- G1b on the site needs `b1-baselines.json` committed (hunk below).
- When B1-2 and B1-3 report, notebook 7's section 5 gains their archives
  and `science.B1_TASKS` their status; the readers follow the pattern of
  `b1_gates`/`b1_comparison`.
- The workflow has not run the science notebooks on GitHub; the emulation
  below is the evidence.

## Tool runs

WSL2 host, `OPENBLAS_NUM_THREADS=1`, `RAYON_NUM_THREADS=4`; wall and peak
RSS from `/usr/bin/time`.

| Date | Tool / stage | Input | Wall | Peak RSS | Notes |
| --- | --- | --- | ---: | ---: | --- |
| 2026-10-30 | `uv venv` + `uv pip install -e '.[pointing,beam,test,imaging,notebook,docs]' ruff maturin pip` | worktree | 175.0 s | 1.09 GB | builds the extension |
| 2026-10-30 | probe: JAX toy, Rust experiment, audits, `solve_pointing` | Rust toy fixtures | 26.5 s | 776 MB | gain audit on the complete fixture 4.2–6.0 s |
| 2026-10-30 | probe: katbeam audit, native and no rotation | complete toy, katbeam H | 31.3 s | 818 MB | native 22.9 s (JAX compile): gated behind `RANG_NOTEBOOK_SLOW` |
| 2026-10-30 | smoke test of `rang.notebook.science` | archives, toy, fixture | 41.8 s | 826 MB | every reader and figure |
| 2026-10-30 | papermill, notebook 06 | fixture, switches off | 11.6–12.5 s | 828 MB | two runs |
| 2026-10-30 | papermill, notebook 07 | toy + fixture, switches off | 28.0–29.8 s | 860 MB | two runs |
| 2026-10-30 | `pytest tests/test_d3_notebooks.py` | worktree | 33.6 s | 869 MB | 16 passed in 30.6 s |
| 2026-10-30 | `pytest tests/test_d3_notebooks.py tests/test_d1_docs.py` | worktree | 47.0 s | 855 MB | 19 passed, 1 failed: the link test, before this report existed |
| 2026-10-30 | CI emulation: `maturin develop --release --locked --extras docs,notebook,imaging,pointing,beam` | clean export, `CARGO_BUILD_JOBS=4` | 149.3 s | 1.09 GB | cold |
| 2026-10-30 | CI emulation: `execute_notebooks.py` | seven notebooks, LUNO off | 102.9 s | 870 MB | 06 10.3 s, 07 40.3 s |
| 2026-10-30 | CI emulation: `gen_cli.py --check` | | 6.2 s | 35 MB | |
| 2026-10-30 | CI emulation: `sphinx-build -W --keep-going` | executed notebooks | 33.4 s | 387 MB | 0 warnings, 17 MB site |
| 2026-10-30 | `bash tools/check-all.sh` | branch tree (the three code commits and this report) | 2,121.7 s | 2.06 GB | **overall: PASS**; pytest 652 passed, 3 skipped in 194.7 s; the wall includes about 30 min waiting on the shared lock behind four other tasks; log `outputs/d3-20261030-check-all.log` |
| 2026-10-30 | papermill, both notebooks, every switch on | worktree, LUNO slice, holography product | 15.6 s / 76.4 s | 0.93 / 1.03 GB | K replay exact; executed copies deleted (CC BY-NC maps) |

## For the coordinator

**Branch files** (all owner files): the two notebooks under
`notebooks/science/`, `python/rang/notebook/science.py`,
`tests/test_d3_notebooks.py`, `docs/execute_notebooks.py`, the
`_copy_notebooks` and `_write_constants` hunks of `docs/conf.py`,
`docs/tutorials/index.md`, this report.

**Shared-file hunks** (not applied here):

1. `python/rang/notebook/__init__.py`: in the docstring's module list, after
   the `experiment` line, add "- `science`: the two research questions (D3),
   archive readers and live demonstrations;" and set
   `__all__ = ["data", "experiment", "flags", "gains", "image", "science", "steer", "survey"]`.
2. `research/results/b1-baselines.json`: copy
   `outputs/b1-20261030-10-baseline-g1b/b1-baselines.json` (42 kB, derived
   statistics and fixture amplitudes, no beam maps; the B1 report already
   names it a candidate). `science.b1_baselines_archive` looks there first,
   so G1b appears on the site with no code change.
3. `notebooks/05-the-flagging-experiment.ipynb`, last markdown cell ("What
   the null result does and does not say"): its second and third bullets
   predate L2, L1-M and the verdict (L2 and L3 as "the open runs before the
   verdict", the 1934−638 model "about 1.5″ off centre", L1-M as a
   follow-up). Replace both with: "It **does not** cover native,
   unprocessed flags and weights (L3), a target field, another observation,
   or a closure-based or TV-regularised objective. The experiment is closed
   as null; notebook 6 follows it through L2, L1-M, C1, L5 and the verdict,
   reading every number from the archives."
4. `docs/index.md` line 43: "five tutorial notebooks on a public 45 MB
   MeerKAT fixture;" becomes "five tutorial notebooks and two science
   notebooks (the flagging verdict; beam and pointing) on a public 45 MB
   MeerKAT fixture and the Rust toy;".
5. `docs/api/index.md`, "Quoted constants" (optional): add a
   `rang.core_campaign` (frozen flagging policy) heading including
   `../_generated/flagging_rules.md` and a `rang.notebook.science` (B1
   rules) heading including `../_generated/b1_rules.md`; `_write_constants`
   already writes both and the tutorials page includes them.
6. `.github/workflows/docs.yml` line 6 comment: "executes the five
   notebooks" becomes "executes the seven notebooks (tutorials and
   science)". No functional change is needed: the workflow already installs
   `pointing,beam` and sets `RANG_NOTEBOOK_LUNO=0`.
7. `README.md`, after the Tutorials bullet: "- Science notebooks:
   `notebooks/science/` (06 the gain-TV flagging experiment and its null
   verdict; 07 beam and pointing: the toy, the JAX path, observability,
   B1-0 and B1-1); see `research/d3-science-notebooks.md`."

**STATE.md**, new top entry:

> D3 science notebooks (big plan, documentation track), 2026-10-30
> (implemented; executed and built locally and on a clean export;
> documentation only; [d3-science-notebooks.md](d3-science-notebooks.md)).
> Two guided notebooks in `notebooks/science/`, rendered on the site. 06
> tells the gain-TV flagging experiment from the question to the null
> verdict: the method live on the fixture, every real-data number read from
> `flagging-verdict.json` (the pre-registered calls, the TV policy's
> selections, the cost clause, L1-M, C1, L5, A1, O-CASA) and a live
> `verdict_tables.py --check`; L3 as the reopening item. 07 takes the
> original beam and pointing question through the Rust toy, the JAX
> reference path (agrees with Rust to 1e-11 Jy), the smooth pointing solver
> and the observability audits (live, equal to their archives), then B1-0
> from `b1-beam-product.json` and B1-1 (the SARAO/SKA fit reproduced live on
> the fixture), with B1-2 and B1-3 as proposed and their frozen rules
> quoted. Switches `RANG_NOTEBOOK_LUNO`, `_SLOW` and `_HOLOGRAPHY` are
> opt-in; the site never renders the CC BY-NC holography maps. Readers in
> `rang.notebook.science`. A clean export ran the workflow's steps with 0
> Sphinx warnings; the science notebooks take 10 s and 40 s.

**`research/README.md`** index line:

> New, 2026-10-30: D3, the [science notebooks](d3-science-notebooks.md):
> the flagging verdict and the beam and pointing question as guided
> notebooks on the site, every number from an archive or a live cell.

**A discrepancy with the L4 report** (not edited here): notebook 6's
generated summary says the residual RMS of every decidable call against the
first pass agrees within **0.59 %**; `flagging-verdict.md` (§5.4 "Scale of the effects",
and §8) says 0.5 % and cites 0.995419 (L1, stored model). The largest deviation
in its own table is L1-M's `tv-policy` vs `tricolour-firstpass` frozen
residual-RMS call, 0.9940951 (point model) and 0.9940953 (field model),
`l1-model-completeness.json:models/{point,field}/hypotheses/0/residual_rms`,
both null. The verdict's "0.5 %" should read "0.6 %" (or name the stored
model); no call changes.

**`research/tool-timings.md`** rows: the "Tool runs" table above.

**Ignored output directories:** `outputs/d3-20261030-ci-emulation/` (CI
emulation script, log, maturin log, notebook timings) and
`outputs/d3-20261030-check-all.log`. Nothing else was written under
`outputs/`. The scratch `~/Build/tmp/20261030-d3/` (probes, the notebook
builders, the clean export) is deleted.
