# V3: an introductory notebook track, outline

Task V3 of [vision.md](vision.md), 2026-11-11. Status: **implemented
(task V3b, 2026-11-11); runtimes measured.** The nine notebooks are in
`notebooks/intro/`, linked from [docs/tutorials](../docs/tutorials/index.md),
and executed by the docs workflow (I6-I8 nightly). Sections 1-5 are the
outline as written before the notebooks, with the estimates it made; section
6 records the coordinator's answers and section 8 what was built, measured
and left open. Where the outline and section 8 differ, section 8 holds.

## 1. What the track is, and what it is not

Nine notebooks, I1 to I9, take a reader who knows physics but not radio
astronomy from the radio sky to a calibrated, deconvolved image and to the
basics of pulsars and transients. Each one is a gentle step towards something
the repository already has: notebooks 01 to 05 (the chain on real data, look
inside), `notebooks/science/` 06 and 07 (the research record) and E4's
MS-to-image tutorial (the commands). Where 01 to 07 or `docs/concepts/`
already teach a topic, the intro notebook stops at the hand-over and links.
It does not repeat that material.

| Already taught, so the track links instead of repeating | Where |
| --- | --- |
| The measurement equation's rank, `8n − 4`, the U(2) gauge, identifiability | notebook 01; [concepts/gains](../docs/concepts/gains.md) |
| SumThreshold, the teaching strategy, CARACAL's first pass step by step | notebook 02; [concepts/flagging](../docs/concepts/flagging.md) |
| Gain solves, solution intervals by held-out error, TV maps | notebook 03 |
| uv coverage, dirty image and PSF, natural, uniform and Briggs weights | notebook 04; [concepts/imaging](../docs/concepts/imaging.md) |
| Experiments with frozen decision rules and their null results | notebooks 05, 06, 07 |
| Measurement Sets, zarr, HTTP range fetch | [concepts/ingest](../docs/concepts/ingest.md) |

New ground for the track: emission and noise, the two-element interferometer,
the MeerKAT array as a whole, Jones terms one at a time on simulated truth,
deconvolution (CLEAN and GeMClean), polarisation, and time-domain basics.

## 2. Data the track may use

| Set | Size | How it arrives | Licence | Teaches | Cannot teach |
| --- | ---: | --- | --- | --- | --- |
| SKA pointing fixture `outer_scans.zip` (scan 9: 4 antennas, J1939−6342, 4,096 ch, 140 rows) | 45 MB (45,452,147 bytes, SHA-256 pinned) | `rang.notebook.data.download_fixture(cache_dir)`, 5.9 s measured ([d2-notebook.md](d2-notebook.md)) | public SKA test data | real visibilities, real RFI, gains of a point source | deconvolution (one point source), polarisation (unpolarised calibrator) |
| A1 small (16 antennas, 64 ch, 104 integrations, 12,480 rows; with its noise- and RFI-free twin) | 43.5 MB each; 94.6 MB once a chain adds MODEL_DATA and CORRECTED_DATA | **simulated, generated locally from seeds**: `examples/a1_simtruth.py generate small OUT` (2.8 s each, measured) | rang's own | the chain against known truth (K, B, G, KCROSS, Xf, Df, RFI masks, σ exact) | real-sky surprises |
| `poldx` (A1 small's antennas and schedule, 256 ch; d_x ≠ 0 on the reference antenna) | not measured (rows as A1 small, 4× its channels, so about 170 MB by scaling; to be measured) | generated locally, `generate poldx` (4.5-5.0 s, measured) | rang's own | leakage, X−Y phase, parallactic rotation | – |
| Simulated filterbank (NumPy, in the notebook) | under 50 MB in memory, nothing on disk | generated in the cell | – | dispersion, dedispersion, folding | real pulsar data; that waits for V1 |

Not required inputs: the LUNO slice (755 MB, and its licence precondition is
open: [core-k-luno-campaign.md](core-k-luno-campaign.md)), the B1-0 holography
product (CC BY-NC 4.0), ESO137 (16.4 GB per primary scan). A notebook may offer
one of them behind an opt-in switch, as notebooks 06 and 07 do.

Two install facts that shaped the track (as outlined; both fixed by V3b,
section 8). `rang.simtruth` read `data/meerkat.itrf.txt` from the repository
root (it was not package data), so I3, I4 and every A1-based notebook needed
a checkout, not just `pip install rang-core`; the track's install line is the
one in [docs/tutorials](../docs/tutorials/index.md). Shipping the ITRF table
in `python/rang/data` would lift this.

## 3. The notebooks

Runtimes: none of these notebooks exists, so every runtime is an
**estimate**, built from measured timings of the functions it calls
([tool-timings.md](tool-timings.md), [d2-notebook.md](d2-notebook.md)).
Those timings are from the shared WSL host with outputs on `/mnt/d`; a laptop
on a local SSD is expected to be no slower for these sizes, but that is not
measured. Each notebook's runtime is measured when it is written and recorded
in `tool-timings.md`. Function names below exist on `main` unless marked
**proposed**.

### I1. The radio sky and its emission

- **Goals:** flux density and its units (Jy); synchrotron and thermal spectra
  and spectral index; brightness temperature; the calibrator J1939−6342 (PKS
  1934−638) and why flux standards exist; the radiometer equation
  σ = SEFD / √(2 Δν Δt) with MeerKAT's numbers (SEFD 420 Jy in A1: 0.0287 Jy
  per visibility in A1 small).
- **Data:** none downloaded; the fixture's frequency axis if it is cached.
- **Runtime:** under 10 s (est.: arithmetic and plots).
- **rang:** `rang.fluxstd.standards`, `sources`, `flux`, `manual`;
  `rang.notebook.data.reynolds_flux` (the Reynolds 1994 model notebook 01
  uses).
- **Hands over to:** I2.

### I2. Interferometry and visibilities

- **Goals:** two-element fringe and geometric delay; a visibility as one
  Fourier component of the sky (van Cittert–Zernike); baselines in
  wavelengths (u, v, w); amplitude and phase of a point source at the phase
  centre and off it; autocorrelations against cross-correlations.
- **Data:** fixture (45 MB) for real amplitudes and phases; a DFT prediction
  for comparison.
- **Runtime:** 20-30 s (est.: fixture load 3.6 s first extraction, measured;
  plots).
- **rang:** `rang.notebook.data.download_fixture`, `load_fixture`, `summary`;
  `rang.notebook.flags.waterfall` (quantity `amplitude` and `phase`);
  `rang.simtruth.target_coherency` (DFT of point components).
- **Hands over to:** notebook 01 (the data and its checks), I3.

### I3. The MeerKAT array

- **Goals:** 64 dishes of 13.5 m, the core and the 8 km spokes; L band
  856-1712 MHz; baselines `n(n − 1)/2` = 2,016; Earth-rotation synthesis and
  uv tracks against declination; resolution λ/B_max against field of view
  λ/D; the primary beam; what four stations (the fixture) lose against 16 (A1
  small) and 64.
- **Data:** the repository's `data/meerkat.itrf.txt`; A1 small (43.5 MB,
  generated, 2.8 s).
- **Runtime:** 30-60 s (est.: generation 2.8 s measured; uv tracks for 2,016
  baselines by NumPy).
- **rang:** `rang.simtruth.antenna_table`, `design`, `schedule`, `geometry`;
  `rang.notebook.image.uv_coverage`; `rang.beams.voltage_beam` (a cosine
  taper); `rang.beams.load_katbeam` behind the `beam` extra, optional.
- **Hands over to:** notebook 04 (uv coverage of the fixture), I4.

### I4. The measurement equation

- **Goals:** V_pq = J_p B J_q^H; each Jones term as a physical effect (K
  delay, B bandpass, G gain, D leakage, P parallactic angle); corrupt a model
  term by term on A1 small's twin and correct it again with the truth; why a
  gain has a phase ambiguity (the reference antenna). Stops at the gauge and
  the count of degrees of freedom, which notebook 01 teaches.
- **Data:** A1 small and its twin (2 × 43.5 MB, generated).
- **Runtime:** 30-60 s (est.).
- **rang:** `rang.simtruth.jones`, `corrupt`, `correct`, `casa_gauge`,
  `stokes_coherency`.
- **Hands over to:** notebook 01 (rank, `8n − 4`, the U(2) gauge), I5.

### I5. RFI and flagging

- **Goals:** what RFI looks like at MeerKAT L band (GNSS, GSM, aircraft DME,
  satellites) in time, frequency and baseline; the static mask; why a flag is
  a decision with a cost (lost data against bias); flags against known truth:
  A1 small carries its RFI masks, so a flagger's misses and false flags can be
  counted. The record: the TV policy, F2 and F3 were null or failed their own
  test, and say so.
- **Data:** fixture (45 MB) for real RFI; A1 small (43.5 MB) for truth
  masks.
- **Runtime:** 1-2 min (est.: `rang-core flag` on A1 small 19.5-22 s
  measured, most of it flag versions on `/mnt/d`; fixture strategies 0.8-3.5
  s measured).
- **rang:** `rang.notebook.flags.waterfall`, `flag_fraction_by_channel`,
  `flag_fraction_by_antenna`; `rang.notebook.data.read_ms`;
  `rang-core flag CONFIG MS` (the Tricolour port); the static mask
  `python/rang/data/4k_lband_meerkat.staticmask`; truth masks read from A1's
  output (**proposed helper**: a reader for A1's RFI truth, if none fits).
- **Hands over to:** notebook 02 (SumThreshold step by step), notebook 05/06
  (the flagging experiment), I6.

### I6. Calibration

- **Goals:** cross-calibration in order: models of the flux calibrator, K, G,
  B, flux scale F, then apply; solution intervals and the reference antenna;
  checking each solved term against A1's truth in its gauge; what
  self-calibration is and its known limit here (C5: the unmasked CLEAN model
  absorbs gain errors).
- **Data:** A1 small (43.5 MB generated; 94.6 MB after the chain).
- **Runtime:** 2-3 min (est.: `rang-core calibrate` 21.8-27.4 s and `apply`
  25.5 s on A1 small, measured).
- **rang:** `rang-core calibrate` and `apply` (C2e, C4b); in Python
  `rang.cal_chain.run`, `rang.fluxstd.flux`; `rang.notebook.gains.solve`,
  `gain_maps`, `residual_waterfall` for the look inside.
- **Hands over to:** E4 (the same steps as commands on a real MS),
  notebook 03 (gains, gauge, TV).

### I7. Imaging and deconvolution

- **Goals:** dirty image = PSF ⊛ sky; why CLEAN: Högbom's loop, gain and
  threshold, major and minor cycles, the model, residual and restored image;
  the stop rule (GeMClean's default `-stale-floor 0.01`, [stale-floor.md](stale-floor.md));
  multiscale for extended emission; reading an image: noise against σ from I1,
  dynamic range, artefacts from bad calibration (image I6's uncorrected and
  corrected data side by side).
- **Data:** A1 small after I6 (94.6 MB); its target field has the simulated
  sky with known components.
- **Runtime:** 1-2 min (est.: `rang-core image` 6.3 s on A1 small, measured;
  three or four GeMClean runs).
- **rang:** `gemclean` (`-size`, `-scale`, `-weight`, `-niter`, `-mgain`,
  `-auto-threshold`, `-auto-mask`, `-multiscale`); `rang-core image`;
  `rang.notebook.image.image_figure`, `compare`, `metrics_table`;
  `rang.simtruth.target_sky` for the truth.
- **Hands over to:** notebook 04 (weights and the robustness sweep), E4,
  [clean-theory.md](clean-theory.md).

### I8. Polarisation

- **Goals:** linear feeds and the four correlations XX, XY, YX, YY; Stokes I,
  Q, U, V; polarisation fraction and angle (3C 286: 9.5 %, 33°); leakage Df,
  cross-hand delay KCROSS and X−Y phase Xf; parallactic rotation as the
  handle that separates source from instrument; Stokes images.
- **Data:** `poldx` (generated, 4.5-5.0 s; size to be measured).
- **Runtime:** 2-4 min (est.: `rang-core calibrate` with the polcal section
  56.3 s and `apply` 62.0 s on poldx, measured on `/mnt/d` under load).
- **rang:** `rang.cal_pol.parallactic_angle`, `gpol`, `kcross`, `xf`, `df`,
  `apply`; `rang.simtruth.calibrator_stokes`; `rang-core calibrate` and
  `apply` with the polcal section; `gemclean -pol IQUV -join-polarizations`.
- **Hands over to:** [c6-polterms.md](c6-polterms.md),
  [g9-stokes.md](g9-stokes.md).

### I9. Time-domain basics: pulsars and transients

- **Goals:** pulsars, FRBs and GRB afterglows by time scale; dispersion delay
  Δt = 4.149 ms × DM × (ν_lo⁻² − ν_hi⁻²) with ν in GHz; dedispersion by
  shifting channels; signal-to-noise against trial DM; folding at a known
  period; scattering; why an imager averages transients away and what
  image-plane light curves and dynamic spectra recover.
- **Data:** a simulated filterbank in the notebook (NumPy: a dispersed,
  periodic pulse in noise over MeerKAT L band's frequencies); no public data
  is named until V1 picks the first product, its data and its oracle.
- **Runtime:** under 1 min (est.).
- **rang:** **none yet.** rang has no time-domain functions. The notebook
  starts in NumPy and switches to rang's functions when V1's product exists
  (proposed: dedispersion, folding, per-integration images).
- **Hands over to:** V1's scoping note.

## 4. How the track joins E4 and notebooks 01-07

The vision puts E4's tutorial at the centre of the beginner's route:

```
I1 sky → I2 visibilities → I3 array → I4 measurement equation
  → I5 flagging → I6 calibration → E4: MS to image with rang-core run
  → I7 imaging and deconvolution → I8 polarisation → I9 time domain
look inside (any time after the matching I notebook): 01 ← I2/I4, 02 ← I5, 03 ← I6, 04 ← I7, 05
research record: 06, 07
```

- I1-I6 give the concepts E4 assumes. E4 then runs the commands
  (`rang-core flag`, `calibrate`, `apply`, `image`, `run`) on an MS without
  explaining radio astronomy.
- **Proposed for E4:** let its small end-to-end CI job run on A1 small, so
  that I5-I7 and E4 share one MS and the reader recognises the image. E4's
  data is E4's decision; if it picks another set, I6 and I7 keep A1 small and
  E4 is linked rather than repeated.
- E4 is unwritten and waits on E2 (running again). Until it exists, I6 links to
  [docs/cli.md](../docs/cli.md) and [w2-commands.md](w2-commands.md).

## 5. Execution in CI

The track runs on what the docs workflow already has: the fixture
(downloaded and hash-checked) and locally generated A1 sets, no LUNO. Expected
total under 15 min on CI (est.: the sum of the estimates above; I6-I8 dominate).
If that is too long for every push, I6-I8 can run nightly or behind a switch,
as `RANG_NOTEBOOK_SLOW` does for notebook 07.

## 6. Owner decisions before writing

1. **Names and place:** `notebooks/intro/i1-radio-sky.ipynb` … `i9-time-domain.ipynb`,
   so they do not collide with 01-07 and `notebooks/science/`.
2. **E4's data:** A1 small (section 4), or another set.
3. **CI cost:** all nine on every push, or I6-I8 nightly.
4. **ITRF table as package data** (section 2), so A1-based notebooks run from a
   pip install.

Answered by the coordinator for V3b (2026-11-11): (1) yes, these names;
(2) A1 small and poldx, generated in the notebook as E4's tutorial does, plus
the public fixture; (3) I1-I5 and I9 on every push, I6-I8 nightly; (4) yes:
the coordinates are facts (owner decision E5-11, `docs/licence.md`).

## 7. Follow-ups found while outlining (V3b fixed the one listed)

- [docs/concepts/imaging.md](../docs/concepts/imaging.md), section
  "Deconvolution", said rang has no production deconvolver; GeMClean is on
  `main`. **Fixed in V3b**: the section now describes GeMClean and links I7.

## 8. V3b: what was built and measured (2026-11-11)

**Implemented.** `notebooks/intro/i1-radio-sky.ipynb` … `i9-time-domain.ipynb`,
linked from [docs/tutorials](../docs/tutorials/index.md) and the docs index.
Each starts with learning goals, computes every number it quotes (or reads
it from a tracked archive: I5 reads
`research/results/e4-tutorial/flag_variants.json`), and ends with exercises
and "where next" links to the concepts pages, notebooks 00-07 and research
notes. Committed without outputs (`tests/test_v3_intro.py`).

**Package changes for owner decision 4.**

- `python/rang/data/meerkat.itrf.txt`: a byte copy of `data/meerkat.itrf.txt`
  (SHA-256 `cbca5dbe…9e638`); `rang.simtruth.ITRF` points to it. The copy under
  `data/` stays because GeMClean's simulator compiles it in; a test keeps the
  two identical.
- The A1 generator moved from `examples/a1_simtruth.py` into the package as
  `rang.simtruth_ms` (`python -m rang.simtruth_ms generate small DIR`; its
  history before V3b is that of `examples/a1_simtruth.py`, as git does not
  record a rename when the old path stays). `examples/a1_simtruth.py` is a
  shim, so every
  command, tool and note that names it still works. Checked: A1 small written
  by the moved module has DATA and `truth.npz` identical to the old script's
  (same seeds, compared array by array).
- Without the first change the second would not run from a wheel; without
  the second the first would not help the notebooks.

**Runtimes, measured** (2026-11-11, papermill through
`docs/execute_notebooks.py`'s `execute`, native Windows, 2 threads, fixture
cached, host shared with E2, no heavy lock: CPU-light). The outline's
estimates are in section 3.

| Notebook | Data | Measured | Outline's estimate |
| --- | --- | ---: | ---: |
| I1 radio sky | none | 5.0 s | under 10 s |
| I2 visibilities | fixture | 4.3 s | 20-30 s |
| I3 MeerKAT array | ITRF table, fixture (no A1 needed) | 12.3 s | 30-60 s |
| I4 measurement equation | A1 small and its twin | 12.1 s | 30-60 s |
| I5 RFI and flagging | fixture, A1 small and twin, E4's archive | 16.7 s | 1-2 min |
| I6 calibration | A1 small | 15.6 s | 2-3 min |
| I7 imaging and deconvolution | A1 small | 45.4 s | 1-2 min |
| I8 polarisation | poldx (157,301,861 bytes, measured; the outline scaled about 170 MB) | 25.8 s | 2-4 min |
| I9 time domain | NumPy filterbank, 41 MB in memory | 6.0 s | under 1 min |
| total | | 143.2 s | under 15 min |

**CI** (owner decision 3). `docs/execute_notebooks.py` runs I1-I5 and I9
always and I6-I8 only with `RANG_NOTEBOOK_INTRO_SLOW=1`. The docs workflow
gains a nightly schedule that sets it, saves the executed I6-I8 to the
Actions cache and deploys; every other build restores them and renders them
while their code cells equal the source's (`keep_executed`), else without
outputs. Checked on the branch: docs run 43047655873 (push: I1-I5 and I9 in
1.9-9.7 s each, I6-I8 not executed, Sphinx with `-W` passed) and run
43048923411 (`workflow_dispatch`: all nine, I6 6.4 s, I7 28.3 s, I8 14.9 s,
cache `intro-nightly-43048923411` saved), both green on ubuntu-24.04.

**Departures from the outline.**

- I3 needs no A1 file: uv tracks come from the ITRF table by the standard
  hour-angle formula, the PSFs by a direct Fourier sum.
- I5 scores two strategies live (E4's tutorial strategy, SumThreshold
  alone) and shows E4's archived table; the live tutorial row reproduces the
  archive (36.4 % flagged, recall 90.2 %, false flags 29.0 %). No new helper
  was needed: the truth masks are `a1-small.rfi_mask.npz`.
- I6 runs `rang-core flag`, `calibrate` and `apply` on E4's configuration;
  `rang.cal_chain.run` and `rang.notebook.gains` are not used (notebook 03
  covers the look inside).
- I8 flags RFI with the truth mask (an oracle), as C6w did, so that it is
  about polarisation; it calibrates with the default `frame: casa`.
- I9 uses NumPy only, as planned; rang has no time-domain functions.

**Measured along the way** (simulated or the public fixture; teaching
checks, not claims):

- The simms ITRF table and the fixture's ANTENNA table (m000-m003) differ by
  a common 35.27-35.29 m; positions relative to m000 agree within 4 cm (I3).
- The SEFD from the fixture's autocorrelations against cross-correlations
  and the Reynolds model: 398-497 Jy per baseline and hand, median 438 Jy
  (I2). A1 assumes 420 Jy.
- I4: the true chain reproduces the twin's DATA to 1.3e-6 Jy (single
  precision); DATA − twin outside the RFI mask has σ = 0.0287 Jy, the
  design's value.
- I6: |K − truth| median 61 ps, max 146 ps; `fluxscale` 4.295 Jy against the
  band-averaged true 4.292 Jy; corrected SIM-GCAL within 0.996-1.009 of its
  true spectrum.
- I7: the brightest source (0.500 Jy) restores to 0.496 Jy/beam; CLEAN model
  2.465 Jy of a true 2.837 Jy. Residual robust σ 0.698 mJy/beam with Briggs
  0, 0.937 natural, 0.358 after correcting with the true Jones terms (S
  included), against I1's thermal 31 µJy/beam (natural, no flags). The
  residual is therefore not thermal, and calibration error (S included) accounts
  for about half of it; the rest is not separated (follow-up below).
- I8: 3C286-SIM after strategy 1: p median 0.0945 (truth 0.095), χ median
  33.55° (33°), per-channel |Δχ| median 0.55°, 95th percentile 0.62°; the
  IQUV image gives p 0.0944, χ 33.47°. KCROSS·Xf phase against the truth:
  median −0.20°, median |.| 1.02°.

**Open and follow-ups.**

- I5-I7 read E4's configuration from `examples/ms-to-image/`, so they need
  a checkout; I1-I4, I8 and I9 run from a pip install. Shipping E4's
  configuration (or a `rang-core config example`) would close that.
- I7's residual gap after truth correction (0.358 mJy/beam against 31 µJy
  thermal) is not decomposed into unflagged RFI, weighting, flags and
  deconvolution error; I7's exercise 5 starts on it.
- `tools/e2e/run.py` could call `python -m rang.simtruth_ms` and drop its
  checkout requirement for generation (it still needs `examples/ms-to-image`).
- Notebook 04 stalled twice (kernel and client idle, minutes) when run after
  01-03 in one `execute_notebooks.py` process on this Windows host while E2
  ran; alone it ran in 14 s. Not investigated; docs CI on Linux is the
  check.

## 9. The interactive MeerKAT (2026-11-11)

Status: **implemented; checked in a browser; no measurement claimed.** Asked
for by the owner as part of the track: a three.js page that explains
interferometry from voltages to an image.

- **Where:** `docs/_extra/interferometer/index.html`, one self-contained page
  copied to the site by `html_extra_path` and served at
  <https://pythonic.nl/rang-core/interferometer/>; linked from
  [docs/tutorials](../docs/tutorials/index.md) above the notebook table.
  three.js r128 and its OrbitControls load from cdnjs and jsDelivr, the fonts
  from Google Fonts; nothing else is fetched.
- **Chapters:** one dish (λ/D), geometric delay of a chosen pair, the two
  voltages, a lag correlator, the fringe and visibility of one baseline, the
  uv plane of all pairs, Earth rotation, dirty image and PSF, Högbom CLEAN.
  It covers I2, I3 and the first half of I7 in pictures and hands over to
  them.
- **What is computed, not drawn:** ENU positions from the 64 ITRF rows of
  `python/rang/data/meerkat.itrf.txt` (copied into the page); source
  direction, azimuth and elevation, (u, v, w) and the delay w/c from hour
  angle, declination and latitude −30.713°; 1284 MHz; the uv sampling on a
  256² grid of 3″ cells with a 15° elevation limit and 4-minute steps; PSF
  and dirty image by FFT of the sampled Fourier transform of a made-up sky
  (nearest-cell gridding, natural or uniform weights, no noise); Högbom
  CLEAN with loop gain 0.2 to 2 % of the dirty peak or 5,000 iterations and
  a circular Gaussian restoring beam from the PSF's half-maximum width; the
  correlator on band-limited noise streams with a shared part delayed by
  the geometric delay.
- **Stylised, and said on the page:** the dish (offset Gregorian from the
  published 13.5 m and 3.8 m, not a survey model), the wavefront spacing and
  speed, the source strength and correlation width in the voltage chapters.
  The sky is invented. Nothing in the page is checked against an oracle; it
  is a teaching picture, and the notebooks hold the numbers.
- **Checked (Chrome, Windows, 1280 × 800 and 375 × 812):** all nine chapters
  without console errors; a dish click changes the pair; the longest pair
  (7,698 m, M048-M060); defaults (64 dishes, 2 h, δ −40°, uniform) give
  62,439 visibilities, 21.2 % of the Fourier cells, a 6.6″ beam, and CLEAN
  ends at 3,184 iterations. Not checked: other browsers, a phone's GPU.
- **Default track 2 h, not 8 h:** at 8 h with uniform weights the dirty image
  was hard to tell from the sky, which left the CLEAN chapter nothing to
  show.
- **Open:** vendoring three.js instead of the CDNs; a link from I2, I3 and
  I7 themselves; a share video is in ignored `outputs/interferometer-demo/`.
