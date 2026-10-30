# Tutorials

Five notebooks teach the chain on real MeerKAT L-band data, four stations at a
time ({gh}`research/d2-notebook.md`). They run on the public SKA pointing
fixture (`outer_scans.zip`, 45 MB), which `rang.notebook.data.download_fixture`
downloads into a cache directory you choose and verifies against its pinned
SHA256. Sections that need the four-station LUNO slice (about 755 MB by HTTP
range fetch) are skipped when it is absent.

The pages below are rendered from notebooks executed by the documentation
workflow on every push, on the fixture alone (`RANG_NOTEBOOK_LUNO=0`) and
without CARACAL's strategy YAMLs, so the comparator sections use the teaching
strategy. The replays they show are exploratory; the real results are read
from the tracked archives.

| Notebook | What you do |
| --- | --- |
| 1. The data, and rank first | load the fixture and check it against the archive; waterfalls; the measurement equation, `8n − 4` and the U(2) gauge; the identifiability survey and its status codes |
| 2. Flagging, step by step | RFI and SumThreshold; the teaching strategy (and CARACAL's first pass when its YAMLs are present) step by step with per-step counts and difference waterfalls |
| 3. Gains, gauge and total variation | solve; losses; amplitude, phase and TV maps; the unitary-gauge caveat; solution intervals by held-out error; the iteration-cap sweep |
| 4. Imaging | uv coverage; dirty image and PSF; natural, uniform and Briggs weights; a robustness sweep; comparing two flag sets |
| 5. The flagging experiment | the question, the policy and the frozen decision rule; an exploratory replay; the real null results from the archives; what the null does and does not say |

## The two research questions

Two guided notebooks in `notebooks/science/` tell the project's research
questions from the question to the current record
({gh}`research/d3-science-notebooks.md`). Their live cells run on the public
fixture and on the Rust toy; every real-data number they show is read from the
frozen archives in {ghdir}`research/results`.

| Notebook | What it covers |
| --- | --- |
| 6. Gain-TV-guided flagging: the experiment and its verdict | the question, the policy and the frozen decision rule; the method live on the fixture (exploratory); every pre-registered call, the TV policy's selections and the cost clause from `flagging-verdict.json`; model completeness (L1-M), closure structure (C1), convergence (L5) and the GNSS bins (A1); what would reopen it (L3, native data); an optional replay of task K |
| 7. Beam and pointing: the original question | the forward model on the Rust toy with the JAX reference path checked against Rust; the Rust beam-width experiment; the smooth pointing solver; the observability audits (the Gaussian gauge, gains, thinned coverage, chromatic beam shape, the information budget); B1-0 (the holography reference beam against katbeam and EIDOS) and B1-1 (the SARAO/SKA Gaussian fit reproduced live on the fixture); B1-2 and B1-3 as proposed |

Four switches, all off on this site: `RANG_NOTEBOOK_LUNO=1` replays task K
from a local LUNO slice (notebook 6), `RANG_NOTEBOOK_SLOW=1` runs the katbeam
audit with its long JAX compile (notebook 7), `RANG_NOTEBOOK_HOLOGRAPHY=1`
draws maps of a local copy of the B1-0 holography product (notebook 7; SARAO
data under CC BY-NC 4.0, never published here), and `RANG_NOTEBOOK_CARTA=1`
opens notebook 4's dirty image in a running [CARTA](https://cartavis.org)
backend through `rang.notebook.carta` (Linux or macOS; the `carta` extra, the
CARTA wrapper installed from its pinned commit and a backend, e.g. the pinned
container: {gh}`research/nb-carta.md`). A gated cell prints its skip line
instead. Notebook 6's switch is opt-in (`=1`), unlike the
`RANG_NOTEBOOK_LUNO=0` opt-out of notebooks 1 and 5.

The frozen rules they quote, as `rang.core_campaign` and
`rang.notebook.science` hold them:

```{include} ../_generated/flagging_rules.md
```

```{include} ../_generated/b1_rules.md
```

## Running the notebooks

To run them yourself:

```sh
pip install -e '.[notebook,imaging]'   # from a checkout; rang-core[notebook,imaging] once released
pip install -e '.[pointing,beam]'      # notebook 7: JAX and katbeam
export RANG_NOTEBOOK_CACHE=/path/of/your/choice   # default ~/.cache/rang-notebook
jupyter lab notebooks/
```

Optional variables: `RANG_FIXTURE` (an existing `outer_scans.zip`),
`RANG_LUNO_SLICE` and `RANG_LUNO_EXTRA` (a local LUNO slice),
`RANG_STRATEGY_DIR` (CARACAL strategy YAMLs), `RANG_NOTEBOOK_LUNO=0` (skip the
LUNO sections). The interactive panels of `rang.notebook.steer` need a live
kernel; on these pages they appear as static output.

```{toctree}
:maxdepth: 1

notebooks/01-data-and-rank
notebooks/02-flagging-step-by-step
notebooks/03-gains-and-tv
notebooks/04-imaging
notebooks/05-the-flagging-experiment
notebooks/06-gain-tv-flagging-the-experiment
notebooks/07-beam-and-pointing
```
