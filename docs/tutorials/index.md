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

To run them yourself:

```sh
pip install -e '.[notebook,imaging]'   # from a checkout; rang-core[notebook,imaging] once released
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
```
