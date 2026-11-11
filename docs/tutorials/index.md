# Tutorials

## New to radio astronomy: the introductory track

Nine notebooks take a reader who knows physics but not radio astronomy from
the radio sky to a calibrated, deconvolved image, polarisation and the basics
of pulsars and transients ({gh}`research/v3-intro-track.md`). Each states its
learning goals, computes every number it quotes, uses rang's own functions,
and ends with exercises and links onwards. They run on a laptop in under a
minute each (times below: papermill on a Windows workstation, 2 threads, data
cached; the fixture's first download adds about 6 s).
Data: the public fixture (I2, I3, I5) and A1, rang's simulated MeerKAT
observation, written in the notebook from seeds by `python -m rang.simtruth_ms`
(I4-I8); I1 and I9 need no data.

| Notebook | What you learn | Time |
| --- | --- | --- |
| {doc}`I1. The radio sky and its emission <notebooks/i1-radio-sky>` | jansky, synchrotron and thermal spectra, brightness temperature, flux standards, the radiometer equation | 5 s |
| {doc}`I2. Interferometry and visibilities <notebooks/i2-visibilities>` | geometric delay and fringes, visibilities as Fourier components, real amplitudes and phases, the SEFD from autocorrelations | 4 s |
| {doc}`I3. The MeerKAT array <notebooks/i3-meerkat-array>` | the layout, baselines, resolution and primary beam, Earth-rotation synthesis, PSFs of 4, 16 and 64 antennas | 12 s |
| {doc}`I4. The measurement equation <notebooks/i4-measurement-equation>` | Jones terms one at a time on simulated truth, correction, the reference antenna | 12 s |
| {doc}`I5. RFI and flagging <notebooks/i5-rfi-and-flagging>` | real RFI, the static mask, `rang-core flag` scored against a truth mask, the project's null results | 17 s |
| {doc}`I6. Calibration <notebooks/i6-calibration>` | K, G, B, flux scale and apply with `rang-core`; every table against the truth | 16 s |
| {doc}`I7. Imaging and deconvolution <notebooks/i7-imaging-and-deconvolution>` | dirty image and PSF, Högbom's CLEAN by hand, GeMClean, noise and flux against the truth | 45 s |
| {doc}`I8. Polarisation <notebooks/i8-polarisation>` | Stokes parameters, parallactic angle, Df, KCROSS and Xf, calibrated p and χ against the truth, Stokes images | 26 s |
| {doc}`I9. Time-domain basics <notebooks/i9-time-domain>` | dispersion, dedispersion, DM search, folding, scattering, why images average transients away | 6 s |

The route: I1 to I6, then the MS-to-image tutorial below, then I7 to I9; the
notebooks 1-5 look inside each step on real data whenever the matching I
notebook is done. The documentation build executes I1-I5 and I9 on every
push; I6-I8 run nightly, and other builds show the latest nightly outputs
while the notebook's code is unchanged (otherwise the page has no outputs).
From a pip install, I1-I4, I8 and I9 run as they are; I5-I7 read E4's
configuration from `examples/ms-to-image/` and need a source checkout.

## Start here: from a Measurement Set to an image

{doc}`notebooks/00-ms-to-image` takes a MeerKAT Measurement Set to a
calibrated, deconvolved image with `rang-core run config.yaml my.ms` and
`gemclean` ({gh}`research/e4-tutorial.md`). It runs on A1 small, rang's
simulated L-band observation (16 antennas, 64 channels, 41 MB, written from
seeds in about 4 s; {gh}`research/a1-simtruth.md`), so every number is
checked against the truth, and the whole notebook takes under a minute on a
laptop. It explains each section of {gh}`examples/ms-to-image/config.yaml`.
It shows each output: the flag versions and their restore, FLAG against the
RFI mask, the CASA calibration tables, MODEL_DATA, CORRECTED_DATA, the FITS
images, the receipt and resume. It also shows two refusals, circular feeds
and an unimplemented setting. The CI job `e2e` of the wheels workflow runs
the same configuration on all five wheels ({gh}`tools/e2e/run.py`). Its
section on real data is a placeholder until task E2 has results.

## The chain on real data, step by step

Five notebooks look inside the chain on real MeerKAT L-band data, four stations at a
time ({gh}`research/d2-notebook.md`). They run on the public SKA pointing
fixture (`outer_scans.zip`, 45 MB), which `rang.notebook.data.download_fixture`
downloads into a cache directory you choose and verifies against its pinned
SHA256. Sections that need the four-station LUNO slice (about 755 MB by HTTP
range fetch) are skipped when it is absent.

The pages are rendered from notebooks executed by the documentation
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
fixture and on the Rust pointing simulation; every real-data number they show is read from the
frozen archives in {ghdir}`research/results`.

| Notebook | What it covers |
| --- | --- |
| 6. Gain-TV-guided flagging: the experiment and its verdict | the question, the policy and the frozen decision rule; the method live on the fixture (exploratory); every pre-registered call, the TV policy's selections and the cost clause from `flagging-verdict.json`; model completeness (L1-M), closure structure (C1), convergence (L5) and the GNSS bins (A1); what would reopen it (L3, native data); an optional replay of task K |
| 7. Beam and pointing: the original question | the forward model on the Rust pointing simulation with the JAX reference path checked against Rust; the Rust beam-width experiment; the smooth pointing solver; the observability audits (the Gaussian gauge, gains, thinned coverage, chromatic beam shape, the information budget); B1-0 (the holography reference beam against katbeam and EIDOS) and B1-1 (the SARAO/SKA Gaussian fit reproduced live on the fixture); B1-2 and B1-3 in outline, with their reports |

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
pip install -e '.[pointing,beam]'      # notebook 7 and I3's beam section: JAX and katbeam
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
:caption: The introductory track

notebooks/i1-radio-sky
notebooks/i2-visibilities
notebooks/i3-meerkat-array
notebooks/i4-measurement-equation
notebooks/i5-rfi-and-flagging
notebooks/i6-calibration
notebooks/i7-imaging-and-deconvolution
notebooks/i8-polarisation
notebooks/i9-time-domain
```

```{toctree}
:maxdepth: 1
:caption: Tutorials and science notebooks

notebooks/00-ms-to-image
notebooks/01-data-and-rank
notebooks/02-flagging-step-by-step
notebooks/03-gains-and-tv
notebooks/04-imaging
notebooks/05-the-flagging-experiment
notebooks/06-gain-tv-flagging-the-experiment
notebooks/07-beam-and-pointing
```
