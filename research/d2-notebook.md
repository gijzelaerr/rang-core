# D2 notebook tooling

Big plan task D2 ("Documentation, teaching and upstream fixes", 2026-10-30):
Jupyter tooling that lets students and professionals see what the core does
and steer calibration and imaging, including the project's science questions.
Status: **implemented; measured on the fixture and the four-station LUNO
slice; no science claim** (the tooling replays archived chains; it adds no
new result).

## What exists

`python/rangtoy/notebook/` (renamed with P12 to `rang.notebook`): plain
functions first, every plot a `matplotlib.figure.Figure` made without
pyplot (works headless, never shown twice in Jupyter), every table a pandas
DataFrame or a dict; a thin ipywidgets layer on top. Every heavy call goes to
the core wrappers; the modules only arrange inputs and draw.

| Module | What it does | Wrappers it calls |
| --- | --- | --- |
| `data` | Load the fixture scan 9 (zip or extracted MS; optional verified download of the public 45 MB archive into a cache) or the four-station LUNO slice (local copy, or range fetch with a byte-polling progress callback into a user-chosen cache); `summary` | `core_ms`, `core_fetch`, `core_campaign.build_state`/`decode_object`/`fetch_extra`, `flagging.split_holdout` |
| `survey` | Rank first: per gain bin, rank of the 32×32 normals against `8n−4`, label, tree test, native status code with explanations; frozen vs corrected crosscheck call; rank map, support graphs, failure shapes | `flagging_influence.training_normals`, `anchored_response` |
| `flags` | Waterfalls (amplitude, phase, weight, flags) per baseline, flag fraction per antenna and channel; Tricolour strategies step by step (per-step table: fraction, newly flagged, cleared; before/after/diff waterfalls); strategy library (a teaching strategy plus CARACAL's YAMLs when found) | `core_flag.flag_rows` (`want_stages`), `parse_strategy` |
| `gains` | Solve with chosen intervals, iteration cap and gauge; losses table; amplitude/phase/TV maps per antenna; spectra; the unitary-gauge caveat shown (raw vs polar-gauge phase, gauge-invariant ‖G‖_F); residual waterfall; iteration-cap sweep | `core_workflow.core_solve` |
| `image` | Corrected (or raw) Stokes I dirty image and PSF with chosen weighting, robustness and geometry, returning arrays; comparison of two images; metrics table; uv coverage; imaging weight against uv distance; robustness sweep | `core_campaign.apply_gains`, `image_metrics`; `core_grid.stokes_i_reader`, `invert`; `core_weights.imaging_weights` |
| `experiment` | Campaign arms with the frozen settings (original, comparator strategy, TV policy loop), their images, the frozen calls and a ratio plot against the 0.99–1.01 band; readers for the tracked archives (fixture pilot, task K, L1) and for L1's amendment 1 calls | `core_campaign.solve_arm`, `tv_loop`, `hypothesis`, `call` |
| `steer` | `SolvePanel` (integrations/bin, channels/bin, iteration cap, view, gauge), `FlagPanel` (strategy, step, baseline), `ImagePanel` (two flag sets, weighting mode, Briggs robustness, corrected or raw), `DecisionPanel` (comparator strategy → arms, loop, images, calls), `LoadPanel` (dataset, cache dir, fetch progress bar), `Explorer` (tabs). Each has `update(**params)`, cached per parameter set; widgets only call it | – |

"Robust weighting" in the brief maps to the imaging weighting mode
(natural/uniform/Briggs): the core's solver port has QuartiCal's robust
reweighting disabled as in every frozen campaign, so there is no solver
robustness knob to expose.

`notebooks/` (outputs stripped; a test enforces it):

| Notebook | What a student can do |
| --- | --- |
| `01-data-and-rank.ipynb` | Load the fixture and check the loader reproduces the archived split (73,720/9,115/9,169) and baseline solve (TV 0.1474369, validation MSE 25.20612, test 24.91961) to ten figures; read waterfalls, flag and weight distributions; learn the measurement equation, the normal matrix, `8n−4` and the U(2) gauge; run the identifiability survey, read the status codes, see why trees (bipartite graphs) fail with an `A`/`A^{-H}` argument; see the frozen-crosscheck trap and the random-gain-point check; rerun the LUNO survey and compare with the archive (skipped cleanly without the slice) |
| `02-flagging-step-by-step.ipynb` | Learn what RFI and SumThreshold are; run the teaching strategy and CARACAL's first pass step by step, see per-step counts (including steps that clear flags) and diff waterfalls; see what the strategy removes from training; check superset and correlation uniformity; steer strategy/step/baseline |
| `03-gains-and-tv.ipynb` | Solve, read the losses table (MSE, invalid predictions, convergence); amplitude, phase and TV maps; the unitary-gauge caveat with a figure; spectra and residuals; compare solution intervals by held-out error; the iteration-cap sweep (cap ≠ convergence); steer intervals and cap |
| `04-imaging.ipynb` | uv coverage; corrected vs raw dirty image and PSF; natural/uniform/Briggs weights against uv distance; robustness sweep; compare images of two flag sets; what to check before trusting a residual RMS; steer weighting, robustness and flag sets |
| `05-the-flagging-experiment.ipynb` | The science question, the policy and objective, the frozen decision rule printed from the code; an exploratory replay of the campaign on the fixture (labelled as such); the real results from the tracked archives (fixture pilot, task K, L1) and L1's amendment 1 matched calls when the run directory exists; a replay of task K's calls from the local slice that reproduces the archived headline ratio exactly (0.9999388271363914); what the null does and does not say; steer the comparator |

Tests: `tests/test_notebook_functions.py` (every plot and table function on
the fixture, headless (bare `Figure` objects), the loader's reproduction of the
archive, survey invariants, gauge invariance of ‖G‖_F, steering `update`
without a front end, committed notebooks have no outputs) and
`tests/test_notebook_execute.py` (all five notebooks executed with nbconvert,
concurrently, LUNO sections off; one more run of notebook 01 with LUNO on,
skipped without the local slice). Both skip without the fixture or the extra.

## How to run

```sh
pip install -e '.[notebook]'          # or the wheel with [notebook]
export RANG_NOTEBOOK_CACHE=/path/of/your/choice   # default ~/.cache/rang-notebook
export RANG_FIXTURE=/path/to/outer_scans.zip      # or let data.download_fixture fetch it
jupyter lab notebooks/
```

Optional: `RANG_LUNO_SLICE` and `RANG_LUNO_EXTRA` (a `fetch_slice` directory
and an objects root with the extra keys), `RANG_STRATEGY_DIR` (CARACAL
strategy YAMLs), `RANG_NOTEBOOK_LUNO=0` to skip LUNO sections. Without these,
the package searches the checkout's ignored `outputs/` (fixture
`outputs/ska-pointing/outer_scans.zip`, slice `outputs/core-g-20261029-01` with
`outputs/luno-solve-20261029-02/inputs`, strategies
`outputs/caracal-strategy-inputs-8f7bb363`). All paths are pathlib; no shell,
no `/tmp`; caches are created only under the directory the user names.

## Checks (measured 2026-10-30)

- Fixture loader against the frozen `flagging_workflow.prepare` archive
  (`results/gain-tv-flagging.json`): split counts equal; core solve TV
  0.1474368700725686 (archive 0.14743687007256862), validation MSE
  25.206122598826045 (25.20612259882604), test 24.919607595129243
  (24.919607595129268).
- LUNO loader against task K: split 94,047/11,742/11,767; original-arm TV
  0.018794641730921754 and losses identical to the archive.
- LUNO survey against `results/meerkat-luno-support.json` (identity point):
  432 bins with data, 389 identified, 43 underidentified, 592 no data;
  116,805 / 751 cells; failure shapes 17 × {0–3}, 15 × {0–3, 2–3},
  11 × star around 2, all trees; corrected call 389 × status 0 and 43 × 3
  (432/432 agree); frozen call 389 × status 4, as the post-hoc audit says.
- Fixture survey (7 × 128 bins): 288 with data, 287 identified, 1
  underidentified (baseline 0–2 only, 2 cells), 608 no data.
- LUNO decision replay with CARACAL's first pass: tv-policy vs comparator
  ratios 0.9999388 (test MSE), 0.9999582 (residual RMS), 0.9999676
  (validation), additions 0 and 128, equal to task K's archive.
- Fixture replay (exploratory, not a frozen result): the policy selects no
  flag; the first pass adds 26,692 training cells and makes test MSE
  undecidable; its residual-RMS ratio 0.84 reflects fewer imaged cells
  (62,553 vs 92,008), as notebook 05 explains.

## Tool runs

Host shared with three CPU-heavy sibling tasks; load average 46–61 on 16
threads during every measured run, so walls are upper bounds.
`RAYON_NUM_THREADS=4` throughout.

| Date | Tool | Input | Wall | RSS | Notes |
| --- | --- | --- | --- | --- | --- |
| 2026-10-30 | `uv venv` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` + notebook packages | public PyPI | 132 s | – | Python 3.14 |
| 2026-10-30 | `maturin develop --release` | `core/py` | 82 s | 606 MB | – |
| 2026-10-30 | `core_ms` probe (`probe1.py`) | fixture scan 9 MS | 0.23 s read | – | every needed column and subtable readable |
| 2026-10-30 | loader probe (`probe2.py`) | fixture + local LUNO slice | 62 s | 222 MB | includes the root crate's first cargo build, 33.6 s, triggered by `gain_tv`; fixture load 3.6 s (first extraction), LUNO load 17.0 s (cold 724 MB decode), LUNO solve 0.67 s |
| 2026-10-30 | function smoke (`probe3.py fixture`) | fixture | 145 s | 1.28 GB | survey 2.5 s, strategies 0.8–3.5 s, solve 0.9 s, image 2.0 s each, robust sweep (3 images) 15.7 s, arms 9.1 s, arm images 12.3 s; first attempt stopped on a widget constructor bug (fixed) |
| 2026-10-30 | function smoke (`probe3.py luno`) | local LUNO slice | 110 s | 1.05 GB | load 20.5 s, survey 5.6 s, arms 3.9 s, arm images 6.1 s |
| 2026-10-30 | nbconvert, five notebooks in series, LUNO on | fixture + slice | 755 s | 1.16 GB (children) | 01 22.3 s, 02 8.9 s, 03 20.9 s, 04 636.8 s, 05 66.3 s; 04's cells summed 37 s, the rest was a kernel-shutdown stall ("KeyboardInterrupt caught in kernel") not reproduced on rerun |
| 2026-10-30 | nbconvert, 04 alone | fixture | 37.4 s | 809 MB | – |
| 2026-10-30 | `pytest tests/test_notebook_functions.py tests/test_notebook_execute.py` | fixture + slice | 78 s | 839 MB | 15 passed; the concurrent notebook fixture 47.6 s |
| 2026-10-30 | `data.download_fixture` + `data.load_luno(fetch=True)` (`fetchcheck.py`) | public LFS fixture; RATT bucket | 116 s | 179 MB | fixture 45,452,147 bytes in 5.9 s, hash verified; slice and extra objects 754.9 MB fetched and loaded in 101.9 s with the polled progress line every 10 s; `.partial` renamed, nothing left over; split, original-arm TV 0.018794641730921754 and losses equal to the local copy; the 769 MB cache was deleted afterwards (log `outputs/d2-notebook-20261030-02/fetch.log`) |
| 2026-10-30 | `bash tools/check-all.sh` | branch tree | 4,755 s | 2.28 GB | **PASS**; pytest 585 passed, 1 skipped in 4,276 s at load 70–100; started before the coordinator's `flock` rule, so no lock wait; log `outputs/d2-notebook-20261030-01/check-all.log`. After it, only notebook 05's markdown changed (the model-limited caveat); the no-outputs test passes on the rebuilt notebooks |

The probe scripts live in the session scratchpad; their outputs are in
`outputs/d2-notebook-20261030-01/` (ignored).

## Wish list for the wrappers

1. `core_fetch.fetch_slice`: a progress callback (bytes, requests). The
   notebook polls bytes on disk from a thread instead.
2. `core_campaign.decode_extra`: accept an objects root (the local copy in
   `luno-solve-20261029-02/inputs` has no `objects/` prefix), or let
   `fetch_slice` fetch the extra keys; `data._luno_extra` repeats its
   field logic through `decode_object`.
3. `core_campaign` imports `resource` at module top (POSIX only, breaks X1 on
   Windows; also `core_campaign_array`). Guard `rss_mb` (psutil or a
   platform check). The notebook imports `core_campaign` lazily so that the
   fixture paths work without it.
4. `core_campaign.image_arm`: return the arrays and take mode, robustness
   and geometry; write FITS only when asked. `solve_arm`: take the grid and
   iteration cap. The notebook composes `image` from the same calls.
5. The gain TV kernel (`flagging.gain_tv`) and the response normals
   (`flagging_influence.training_normals`, `anchored_response`) live in the
   root crate, built by `cargo` on first use (33.6 s; its "Finished" line
   appears in notebook output) and absent from the wheel. Move them into the
   core extension; until then a wheel-only install cannot run notebooks 01,
   03 or 05.
6. The fixture's state (`data.fixture_state`) repeats about 25 lines of
   `flagging_workflow.prepare` because `prepare` needs casacore and writes
   MS copies; it is validated against the archive, but a shared
   `core_workflow.prepare_state(columns)` used by both would remove the copy.
7. `core_flag.flag_rows`: also return the input window and the
   row-presence mask, and key stages by the strategy's `name`.
8. CARACAL's strategy YAMLs exist only in ignored
   `outputs/caracal-strategy-inputs-8f7bb363`; shipping them (or fetching
   them pinned) in `core/data` would make notebooks 02 and 05 complete on a
   fresh install (check CARACAL's licence first).
9. `results/luno-array-campaign.json` lacks the amendment 1 matched-sample
   calls on which L1's verdict rests; they are only in the ignored
   `outputs/luno-array-campaign-20261030-01/result.json` and the markdown
   table. Adding the `amendment_1` block to the tracked archive lets
   notebook 05 show them on any checkout.

## For the coordinator

**pyproject** (already in this branch, the only `pyproject.toml` change):

```toml
notebook = ["matplotlib>=3.8", "pandas>=2.1", "ipywidgets>=8.1", "ipykernel>=6.29", "jupyterlab>=4", "nbformat>=5.9", "nbconvert>=7.16"]
```

Tested with matplotlib 3.11.2, pandas 3.1.0, ipywidgets 8.1.9, nbformat
5.11.1, nbconvert 7.17.2, ipykernel 7.4.0 on Python 3.14.

**STATE paragraph:**

> D2 notebook tooling (big plan, documentation track), 2026-10-30
> (implemented; measured; no science claim). `rangtoy.notebook` gives plain
> plot and table functions over the core wrappers (`data`, `survey`,
> `flags`, `gains`, `image`, `experiment`) and an ipywidgets steering layer
> (`steer`); five tutorial notebooks in `notebooks/` teach the data and the
> identifiability rank first, Tricolour step by step, gains/gauge/TV,
> imaging, and the flagging experiment with its null results read from the
> archives. The fixture loader reproduces the archived split and baseline
> solve to ten figures without casacore; the LUNO survey reproduces 389/43/592
> and the decision replay reproduces task K's calls exactly. On a host at
> load 46–61, notebooks 01–04 ran in 9–37 s each (series, LUNO on for 01),
> 05 in 66 s with its LUNO replay, and all five on the fixture alone in
> 48 s when executed together; the new tests take 78 s. The range fetch
> (755 MB, 102 s) and the fixture download were exercised once.
> Wish list (progress hook in `fetch_slice`, POSIX-only `resource` import in
> `core_campaign`, TV and normals kernels outside the wheel, amendment 1
> calls missing from the L1 archive) in [d2-notebook.md](d2-notebook.md).

**README line** (under usage or documentation):

> Tutorials: `pip install -e '.[notebook]'` and open `notebooks/`
> (01 data and rank, 02 flagging step by step, 03 gains and TV, 04 imaging,
> 05 the flagging experiment); see `research/d2-notebook.md`.

**For D1 (documentation site):** execute the five notebooks in CI on the
fixture (`RANG_NOTEBOOK_LUNO=0`; the fixture is a public 45 MB LFS object,
`data.download_fixture` verifies its hash) and render them as tutorials;
the module docstrings and `survey.STATUS`, `gains.GAUGE_NOTE`,
`experiment.DECISION_RULE` are written to be quoted. CI needs the root
crate (`cargo`) until wish 5 is done, and the CARACAL YAMLs for the
comparator sections (wish 8; the notebooks fall back to the teaching
strategy). Rename imports with P12.

**For D3 (science notebooks):** build on `experiment` (arms, calls, archive
readers) and `survey`; the wave 3 protocols map onto it: L2 needs
`load_luno` generalised to group 2 (1830−211) and `survey`'s over-rank /
status 6 path (already handled), L3 a loader for the native set, B1 the
pointing solver and JAX path, which this package does not touch. Keep
replays labelled exploratory and verdicts read from frozen archives.

**A compiled expression language for user-defined scoring rules** (Rik
Arends's Rust JIT from Makepad): the rules a user would write here are
per-cell expressions like the policy score
`z * (1 + a * min(h / median, 5)) > t` and the objective. At array scale
(342 M cells) the NumPy version costs a few memory-bound passes, seconds
against the 1,418 s TV loop, which is dominated by re-solves; so a JIT would
not speed up the experiment. Where it could matter is letting a user's rule
run *inside* the core's fused pass (residuals, scores and the rule in one
sweep, no Python arrays of the cube), and letting students change a rule
without rebuilding the extension. A benchmark is worth doing only in that
form: the same rule as NumPy, as `numexpr`, as a Rust closure compiled into
the fused pass, and through the JIT, on the whole-array chunk, measuring
wall, RSS and compile latency. Not implemented here; not a priority before
wish 5 (moving the kernels into the core).

## Open items

- The notebooks need the root crate (`cargo`) for TV and the survey until
  the kernels move into the core (wish 5).
- One nbconvert run of notebook 04 stalled for about 600 s at kernel
  shutdown under load 58; not reproduced (37 s on rerun, and in the test
  run). If it recurs, the test's 300 s cell timeout does not cover
  shutdown.
- Coordinator input (2026-10-30, literature scan): held-out error floors on
  1934−638 may be model-limited (a point model leaves 0.2–0.5 % structured
  amplitude errors, Heywood et al. 2020, arXiv:2004.00454; CARACAL ships a
  196-component field model; follow-up L1-M re-solves with it). Notebook 05
  states this under "does not say"; the tooling keeps the frozen point model
  so replays stay comparable with K and L1. The same message's Anderson
  acceleration notes are for the solver protocol L5, not this task; so is
  U2's QuartiCal#455 input (on scan 9 chi-squared settles by iteration 10
  while gains and the gauge-invariant products keep moving), which agrees
  with what notebook 03's iteration sweep shows students.
- The fixture's teaching replay uses CARACAL's strategies tuned for 64
  dishes on a four-antenna pointing scan; notebook 05 labels it exploratory.
