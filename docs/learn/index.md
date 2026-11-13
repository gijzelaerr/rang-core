# Learn radio interferometry with rang

For readers who know physics but not radio astronomy. The introductory track
computes every number it quotes with rang's own functions, on the public
MeerKAT fixture or on A1, rang's simulated MeerKAT observation, whose truth is
known exactly. Each notebook runs on a laptop in under a minute, states its
learning goals and ends with exercises.

## The route

| Step | Read | You come away with |
| --- | --- | --- |
| 1 | {doc}`I1. The radio sky <../tutorials/notebooks/i1-radio-sky>` | jansky, synchrotron and thermal spectra, brightness temperature, flux standards, the radiometer equation |
| 2 | {doc}`I2. Interferometry and visibilities <../tutorials/notebooks/i2-visibilities>` | geometric delay, fringes, visibilities as Fourier components, the SEFD |
| 3 | {doc}`I3. The MeerKAT array <../tutorials/notebooks/i3-meerkat-array>` | baselines, resolution, primary beam, Earth-rotation synthesis, PSFs |
| 4 | {doc}`I4. The measurement equation <../tutorials/notebooks/i4-measurement-equation>` | $V_{pq} = J_p M_{pq} J_q^H$; the Jones terms K, B, G, D, X, P; the reference antenna |
| 5 | {doc}`I5. RFI and flagging <../tutorials/notebooks/i5-rfi-and-flagging>` | real RFI, static masks, SumThreshold scored against a truth mask |
| 6 | {doc}`I6. Calibration <../tutorials/notebooks/i6-calibration>` | K, G, B, F and apply with `rang-core`, every table against the truth |
| 7 | {doc}`The MS-to-image tutorial <../tutorials/notebooks/00-ms-to-image>` | the whole chain with one command, every output explained |
| 8 | {doc}`I7. Imaging and deconvolution <../tutorials/notebooks/i7-imaging-and-deconvolution>` | dirty image and PSF, Högbom's CLEAN by hand, GeMClean |
| 9 | {doc}`I8. Polarisation <../tutorials/notebooks/i8-polarisation>` | Stokes I, Q, U, V for linear feeds, Df, KCROSS, Xf, the parallactic angle |
| 10 | {doc}`I9. Time-domain basics <../tutorials/notebooks/i9-time-domain>` | dispersion, dedispersion, folding, why images average transients away |

Before I2, I3 or I7, the interactive
[MeerKAT, from voltages to an image](https://pythonic.nl/rang-core/interferometer/)
shows the array in 3D, a live correlator, the uv coverage and a Högbom CLEAN
you can step, in the browser.

After the track, notebooks 1–5 look inside each step on real MeerKAT data,
and notebooks 6–7 tell the two research questions from question to verdict
({doc}`../tutorials/index`). {doc}`../concepts/basics` is the same ground in
one page, and the {doc}`../glossary` defines the terms.

## Ask questions

Open an agent (Claude Code, Codex or another) in a checkout of the repository
and ask in plain words: "what is a visibility?", "why do we need a bandpass
calibrator?", "what did the flagging experiment find?". The procedure
{doc}`../agents/answer-a-question` tells it to answer from these notebooks, the
concepts pages and the research reports, and to name the files it used, so
every answer can be checked.

## Run the notebooks yourself

From a source checkout ({doc}`../installation`):

```sh
pip install --index-url https://pypi.org/simple -e '.[notebook]'
jupyter lab notebooks/intro/
```

I5–I7 read the tutorial's configuration from `examples/ms-to-image/`, so
they need the checkout; the others need only the package. I2, I3 and I5
download the 45 MB public fixture once (SHA256 checked) into
`RANG_NOTEBOOK_CACHE` (default `~/.cache/rang-notebook`).
