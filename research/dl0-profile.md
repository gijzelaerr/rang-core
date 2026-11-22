# DL0 (#37): literature check and stage cost profile

Status, 2026-11-20: **done.** E2-A split from receipts, E2-N split from one profiled run on nash
(section 2.2), literature checked, ASTRODECONV2019 regeneration specified (owner decision of
2026-11-19). No claim of a gain is made here: this note measures where the time goes and checks
what exists, so that #41-#44 are ordered by the record rather than by memory. Nothing was trained.

## 0. Result in five lines

- Self-calibration, minor cycle plus its image-domain resyncs: **63 %** of the stage on E2-A
  (24,270 s), **65 %** on E2-N (49,613 s). Exact major cycles (degrid and grid): **1.6 % and 2.3 %**.
- So dl-plan section 1's "a network pays in imaging only by reducing the number of major cycles" does
  not hold for GeMClean at E2's settings: the cost is the multiscale minor cycle, not gridding.
- Gain solves: 21 % (E2-A), 7.4 % (E2-N). On E2-N, py-spy puts **99.7 % of the selfcal solve in
  reading and averaging rows, 0.25 % in the solver's iterations** (about 9 s of 3,695 s; 0.02 % of
  selfcal), and 0.15 % of the calibrate stage (K, G, B, polarisation) in recognisable solver kernels.
  This holds for the E2 configuration, which solves on time-averaged rows (`calibrate.average_time`
  and `selfcal.average_time` true); rang's default for selfcal is `false`, and on the unaveraged
  pilot the iterations were most of the solve (section 2.3).
- The Sp and Sa solves start every interval at **identity** (`core/src/solve.rs`); no warm start
  exists, and in the E2 configuration none would pay in wall time.
- Order: **#42 (minor cycle) first, #43 (mask and settings) second, #44 (screenings) third, #41
  (gain warm start) last, reframed as a one-day screening.** Classical I/O fixes outweigh #41: every
  apply is read-bound, and on E2-N (only; E2-A 1.4 %, on a local disk) the selfcal input-column copy
  took about 5,530 s (11 %) under idle-class I/O on a shared disk.

## 1. Literature: verdicts on the candidates of dl-plan sections 3 and 6

Checked 2026-11-19 against primary sources (arXiv full text, GitHub API and LICENSE files, the
Heriot-Watt data portal, Zenodo). The full report with a URL for every statement is
`dl0-literature.md` in the session-notes folder of this wave (outside the repo); the table keeps what
decides the plan. "Stated" is the paper's claim, "inferred" this note's reading. Licence reading for
a GPL-3.0-or-later project: GPL-3.0, MIT, Apache-2.0, BSD code combine; CC BY weights and data are
usable with attribution; no licence means reimplement from the paper only.

### 1.1 Imaging (stages 7 and 10)

| Candidate | Verdict | Inputs (stated) | Weights | Licence code / weights | MeerKAT evidence |
| --- | --- | --- | --- | --- | --- |
| R2D2 v1 (Aghabiglou et al., ApJS 273, 3, 2024, [arXiv:2403.05452](https://arxiv.org/abs/2403.05452)); robust R2D2 (ApJS 280, 63, 2025, [arXiv:2503.02554](https://arxiv.org/abs/2503.02554)); ensembles ([arXiv:2403.18052](https://arxiv.org/abs/2403.18052)) | **verified, limited** | two channels: current estimate and its residual dirty image; **the PSF is not an input**; residual recomputed by the exact operator between networks (the plan's mode P shape) | VLA A+C only, Dec 5°-60°, **512² fixed**; 1.6-10 GB zips | [R2D2-RI](https://github.com/basp-group/R2D2-RI): README badge GPL-3.0 but **no LICENSE on `main`** (GitHub: none; GPL-3.0 text on older branches) / CC BY | none: training is "telescope-specific" by the authors; no other array tested |
| S-R2D2 ([arXiv:2503.01462](https://arxiv.org/abs/2503.01462)); transformer R2D2 to 4096² (ApJS, in preparation) | **dropped for now** | – | none | none | none |
| AIRI, cAIRI, uSARA (Terris et al., MNRAS 518, 604, 2023; [arXiv:2312.07137](https://arxiv.org/abs/2312.07137); Wilber et al. 2023, [arXiv:2302.14148](https://arxiv.org/abs/2302.14148), [2302.14149](https://arxiv.org/abs/2302.14149)) | **verified** | a denoiser inside forward-backward with the exact operator; trained on images only, any image size | ONNX shelves of 8, 18.9 MB | GPL-3.0 ([AIRI](https://github.com/basp-group/AIRI), [uSARA](https://github.com/basp-group/uSARA)) / MRI-trained shelf CC BY; **astro-trained shelf has no licence field** | **real**: ESO 137-006 at 2560² ([arXiv:2207.11336](https://arxiv.org/abs/2207.11336), 2312.07137) |
| HyperAIRI ([arXiv:2510.15198](https://arxiv.org/abs/2510.15198)) | **verified, limited** | target channel, two neighbours, spectral index map | 6 ONNX, 2.65 MB each | MATLAB code "in BASPLib", not found / CC BY | none (ASKAP real, VLA simulated) |
| POLISH (Connor et al., MNRAS 514, 2614, 2022, [arXiv:2111.03249](https://arxiv.org/abs/2111.03249); Wu et al. 2026, [arXiv:2603.09162](https://arxiv.org/abs/2603.09162)) | **dropped** | dirty image only; 2026 trains on one DSA-1650 PSF | none | [polish-pub](https://github.com/liamconnor/polish-pub): no licence | none |
| RI-GAN (Mars et al., [arXiv:2507.21270](https://arxiv.org/abs/2507.21270)) | **verified, limited** | dirty image, **PSF as a channel and in a PSF-convolution gradient at every level**, latent code; 360² | 5.07 GB ([Zenodo 16529320](https://zenodo.org/records/16529320)) | [rcGAN](https://github.com/astro-informatics/rcGAN): no licence / CC BY 4.0 | **simulated** MeerKAT uv coverages only |

Also found: aim-resolve on real MeerKAT ESO 137-006 ([arXiv:2512.04840](https://arxiv.org/abs/2512.04840)), no code, dropped;
Chiche et al. 2023 on simulated MeerKAT ([arXiv:2306.13909](https://arxiv.org/abs/2306.13909)), code unverified; radionets (MIT,
VLBI-oriented), no MeerKAT. Training cost stated for R2D2 v1: 160 GPU h plus 4,757 CPU h, about 7 ×
v0.4.0's 24-GPU-hour pilot budget.

**R2D2's inputs (the check dl-plan section 6.2 asked for):** the PSF is not an input; the networks
see estimate and residual, the measurement operator holds the array. Training was over VLA A and C
samplings only (robust version: random integration time 4-32 s, 1-8 scans, Briggs −1 to 1). So
"keep the array inside the exact operator" removes the antenna index but the weights still encode
the PSF distribution they were trained on; G-sub stays necessary, and a MeerKAT series has to be
trained by rang. Released VLA weights are a comparator only after a 512² MeerKAT test.

### 1.2 Calibration (stages 2, 3, 4, 8, 9)

| Candidate | Verdict | Note |
| --- | --- | --- |
| Learned gain warm start or amortised solver start | **none found** | arXiv API query (calibration or selfcal × neural, deep, machine learning or RL × interferometer, LOFAR, MeerKAT, HERA, visibilities): 95 results, 31 newest read; none predicts or initialises gains. No ML calibration on MeerKAT found. |
| Smart calibration, Yatawatta & Avruch (MNRAS, [arXiv:2102.03200](https://arxiv.org/abs/2102.03200)) | **verified, limited** | RL picks directions and iteration limits; [smart-calibration](https://github.com/SarodYatawatta/smart-calibration) Apache-2.0; LOFAR simulations, SAGECal; no trained agents. Fits stage 9, not stage 2. |
| LOFAR selfcal stop classifier, de Jong et al. (MNRAS 542, 3253, 2025, [arXiv:2508.12115](https://arxiv.org/abs/2508.12115)) | **verified, limited** (new) | DINOv2 classifies each selfcal image "continue" or "stop", 0.94 on 360 held-out LOFAR images; weights fetchable, code ([astroNNomy](https://github.com/LOFAR-VLBI/astroNNomy)) no licence. The closest precedent for stage 8 (skip rounds) and 11 (image QA). |
| Kirk, Rau, Ramyaa (AJ 169, 43, 2025, [arXiv:2410.17135](https://arxiv.org/abs/2410.17135)) | **dropped** | RL sequencing calibration; no code. |
| Xue et al. ([arXiv:2610.07357](https://arxiv.org/abs/2610.07357)) | **dropped** as code | XGBoost on ALMA bandpass anomalies beats pipeline rules; no code; precedent for stage 3. |

### 1.3 Other stages

Mask (6): no learned CLEAN mask found (nearest: Radio U-Net segmentation, [arXiv:2408.10871](https://arxiv.org/abs/2408.10871), no code).
Approximate predict (5a): no neural degridder found; learned imagers keep the exact operator. Apply
(5b): none, as the stage table expected. Quick-look (10): RI-GAN closest. QA (11): the LOFAR
classifier.

### 1.4 Architecture families (section 6)

All primary citations confirmed: Deep Sets ([arXiv:1703.06114](https://arxiv.org/abs/1703.06114), reference code Apache-2.0), Set
Transformer ([arXiv:1810.00825](https://arxiv.org/abs/1810.00825), MIT), MPNN with edge features ([arXiv:1704.01212](https://arxiv.org/abs/1704.01212); PyG `NNConv`,
MIT), graph networks ([arXiv:1806.01261](https://arxiv.org/abs/1806.01261), Apache-2.0), dilated CNN ([arXiv:1511.07122](https://arxiv.org/abs/1511.07122), MIT; PyTorch
built in), U-Net ([arXiv:1505.04597](https://arxiv.org/abs/1505.04597); nnU-Net Apache-2.0). FiLM ([arXiv:1709.07871](https://arxiv.org/abs/1709.07871)): reference code
CC BY-NC, so reimplement (one per-channel affine layer). **No graph or set network over radio
antennas or baselines was found**; the nearest is DeepSets over VLBI visibilities ("Grid or Set?",
NeurIPS 2026, no code). Section 6 item 4 has no published radio precedent.

### 1.5 Sky models for simulation (dl-plan section 5 gap)

T-RECS (code GPL-3.0, parametric shapes), SKA Data Challenge 1 images (CC BY 4.0,
[Zenodo 4328029](https://zenodo.org/record/4328029)); MeerKAT MGCLS DR1, MIGHTEE continuum DR1 and SMGPS images: **CC BY-NC 4.0**.
Whether weights trained on NC images may ship under GPL is an owner decision (section 5).

### 1.6 ASTRODECONV2019

The thesis (chapter 6, p. 92) gives `https://archive.kernsuite.info/data/`, 12 GB compressed.
2026-11-19: **the host does not resolve** from glacier (NXDOMAIN) or nash (`curl -sI` rc 6, could not
resolve); it is a CNAME to `kern.astron.nl`, which does not exist. No headers were obtainable; no
Zenodo copy; Wayback not checked (the archive was offline). DL4b step 0 needs the owner's copy or a
regeneration from the thesis's specification.

**Regeneration, scoped 2026-11-19 (coordinator's request; nothing generated).**

What the thesis states (pp. 91-93): spiel (simms, MeqTrees) made the data; MeerKAT AR1, 16 dishes;
channel width 200-300 MHz; declination −55° to −65°; pointing and integration time vary; unresolved
point sources; no gain errors; products dirty image, PSF, WSClean model, sky model; "10 000 image
products". Two inconsistencies to carry, not resolve: p. 93 splits the data 94,000 / 3,000 / 3,000
(100,000 in all), and the image size is not stated on these pages (dl-plan 1.1 says 256²).

The job file. [spiel](https://github.com/gijzelaerr/spiel) (MIT, last commit `c4a8e315`, 2019-10-08)
has seven MeerKAT-16 job files. The three `jobs/meerkat16_oleg_flux{10,100,1000}.yaml` match every
stated number: `nant` 16, `dfreq` 200e6-300e6 (one channel at `freq0` 1,049.8 MHz), `dec_min` −55 to
`dec_max` −65, `gain_errors` 0, 256² at 1.6″, `nsrc` 100, synthesis 7.5-8 h at `dtime` 10 s, `sefd`
520, uniform weighting, WSClean `auto_threshold` 0.125 and `auto_mask` 5. They differ only in
`flux_scale` (10, 100, 1000) and seeds (0-999, 1000-1999, 2000-2999): 3,000 fields, not 10,000.
`meerkat16_oleg_512.yaml` is the same at 512² (seeds 0-3999). `meerkat16.yaml` (full band, gains on,
Dec −30°) and both `deep2` files (Dec −85° to −75°, or −90° to 0°, 3-7 MHz) do not match. So the
pinned specification is the `oleg_flux` triple, with the seed lists extended to the count wanted;
which seeds made the published 10,000 is not recoverable from the repository.

Semantics read from the steps: `randomize.cwl` draws dec, synthesis time and channel width uniformly
(numpy legacy seeding; the job file's "10**" comment on `flux_scale` is stale, the code draws it
uniformly, and min = max here); `skymodel.cwl` draws 100 fluxes as `pareto(8) × noise × flux_scale`
with `noise = sqrt(2 Srms)`, `Srms = SEFD / sqrt(2 dt Δν N(N−1)/2)`, positions Gaussian around the
pointing with σ = `pb_fwhm`/2 = 0.125°, spectral index −0.7 ± 0.01; `simulator.cwl` adds noise of
`SEFD / sqrt(2 dt Δν)` per visibility through MeqTrees, unseeded. The 16 antennas
(`data/MeerKAT16_ANTENNAS`, read with rang's table reader on nash) are m000, m002, m005, m011,
m012, m018, m020, m042, m049, m057-m063, 29 to 7,698 m baselines; all are in rang's
`rang/data/meerkat.itrf.txt`.

Route (a), spiel's container: `docker.io/gijzelaerr/spiel` still exists, tags `latest`
(2019-03-30, 1.12 GB compressed), `meerkat16` (2018-07-02), `add-gains`, `hdr`, `randomise_pos`;
podman 4.9.3 on nash lists the tags and reads `latest`'s manifest (schema 2), so a pull should work
(layers not pulled). Costs of this route: the image is KERN-3 (Ubuntu 18.04, Python 2, MeqTrees,
WSClean of 2019); the workflow needs a CWL runner (the Makefile builds a Python 2 virtualenv for
toil; nash has no Python 2, so cwltool with `--podman` would have to run CWL v1.0 unchanged, not
tested); `latest` predates the repository's last commit, and which tag made the dataset is unknown;
the noise is unseeded.

Route (b), rang: every part exists. `examples/simulate_df5_field.py` (DF5-O) builds tracks from
ITRF positions, predicts exactly (DFT or the core degridder), adds seeded radiometer noise and writes
the MS through `rang.core_ms_write`; WSClean is in the oracle container and GeMClean in the wheel.
Spiel's `randomize` and `skymodel` formulae are ten lines of numpy each (MIT, the owner's) and can be
called with the same seeds, so with numpy's legacy `RandomState` (stable across versions; inferred,
to be checked on one seed) the regenerated parameters and sky models equal spiel's draw for draw;
uvw, noise realisation and WSClean version differ.

Cost on nash, estimated, nothing timed: a field is 120 baselines × about 2,800 dumps = 3.4e5 rows
× 1 channel. Route (b): DFT of 100 sources about 1 s, MS write under 1 s, WSClean or GeMClean on 256²
a few seconds (the 0.125σ threshold is the unknown): about 10 s per field per core, so about 30
core-hours for 10,000, 2-3 h at 12-16 slots; products about 1 MB per field (10-25 GB), MS about
30-40 MB each, deleted per shard after imaging (350 GB if kept). Route (a): MeqTrees turbo-sim,
simms and container start-up per step, about 1-3 min per field per core, 170-500 core-hours, 11-30 h
at 16 slots, plus runner set-up. Shards of 100 seeds with done-markers either way.

**Recommendation: route (b)**, matched to the thesis's numbers, not bit-identical: the `oleg_flux`
specification, spiel's own draw formulae and seeds (0-2999 as published, extended to the count the
DL4b protocol freezes), rang's exact predict and seeded noise, WSClean limited to one major cycle as
the thesis's comparator plus unrestricted WSClean. Route (a) only if a bit-for-bit match of the old
sky models is ever needed and route (b)'s seed check fails. First step, before the 10,000: one seed
through both formulae (spiel's code and rang's port), compared; then 100 fields timed.

**Owner decision, 2026-11-19** (through the coordinator), verbatim: "go with all three flux sets,
seeds 0-2999". Route (b). So **9,000 fields**: `meerkat16_oleg_flux10`, `flux100` and `flux1000`,
each over seeds 0-2999 (the published files gave each flux set its own 1,000 seeds). The thesis's
count stays unresolved (10,000 on p. 92, 94,000 / 3,000 / 3,000 on p. 93); the decision fixes the
set rang regenerates, not what the thesis meant. Consequence of the shared seeds (from the code
below): for one seed, `randomize` and `skymodel` draw the same declination, synthesis time, channel
width, positions, spectral indices and Pareto shape in all three sets, so the three are one field
at three flux scales (10, 100, 1000 × the noise unit), differing only in their noise draw. Splits
by observation must therefore be by seed, never by (seed, flux set). Generation and the one-seed
identity check belong to the #42 session (wave 2); nothing was generated here.

**Specification for the #42 session (route b), runnable from this note.**

1. Source: spiel commit `c4a8e315ae65176dda4871fabd1c241904ef5232` (MIT); job files
   `jobs/meerkat16_oleg_flux{10,100,1000}.yaml`, steps `steps/randomize.cwl`, `steps/skymodel.cwl`,
   `steps/simulator.cwl`, `steps/simms.cwl`, `steps/wsclean.cwl`. Fixed inputs from the job files:
   `nant` 16, `dtime` 10 s, `freq0` 1,049,833,007.8125 Hz, `nchan` 1, `ra` 63.36°, `nsrc` 100,
   `pb_fwhm` 0.25, `sefd` 520, `synthesis` 7.5-8 h, `dfreq` 200e6-300e6, `dec` −55 to −65 (spiel's
   `dec_min` −55, `dec_max` −65, passed to `uniform` in that order), `flux_scale` 10, 100 or 1000.
2. Per (seed s, flux set f), draws with numpy's legacy global `RandomState`, in spiel's order:
   `randomize`: `seed(s)`; `dec = uniform(−55, −65)`; `synthesis = uniform(7.5, 8)`;
   `dfreq = int(uniform(200e6, 300e6))`; `flux_scale = uniform(f, f)`. `skymodel`: `seed(s)` again;
   `Srms = 520 / sqrt(2 · 10 · dfreq · 16·15/2)`; `noise = sqrt(2 · Srms)`;
   `fluxes = pareto(8, 100) · noise · flux_scale`; `ras = 63.36 − randn(100) · 0.125`;
   `decs = dec − randn(100) · 0.125`; `spi = −0.7 + randn(100) · 0.01`; reference frequency `freq0`.
   Port these lines unchanged (Python 3: `range` for `xrange`), keep the draw order.
3. Identity check before any generation: run spiel's two snippets (from the CWL files, under
   Python 3 with `xrange` replaced, current numpy) and rang's port for seeds 0, 1, 2999 and each
   flux set; parameters and sky-model text equal to the printed precision (`%.5g`, `%.3g`, `%.3f`)
   or the port is wrong. Record numpy's version.
4. Observation: antennas m000, m002, m005, m011, m012, m018, m020, m042, m049, m057, m058, m059,
   m060, m061, m062, m063 from `rang/data/meerkat.itrf.txt` (spiel's table lists the same names;
   positions not compared, do it once); phase centre (63.36°, dec); `synthesis` hours of 10 s dumps
   centred on transit (spiel's `simms.cwl` passes `--ra`, `--dec`, `--synthesis-time`, `--dtime`,
   `--freq0`, `--dfreq`, `--nchan`, `--type casa` and no start hour angle or date, so simms's own
   defaults applied; that they centre the track on transit is inferred, unverified: state the choice); one channel of width `dfreq` at `freq0`; XX, XY, YX, YY; tracks, uvw and
   exact prediction as in `examples/simulate_df5_field.py` (`track`, the core DFT for point sources),
   spectral index applied at `freq0` (a no-op for one channel); no gain errors, no smearing (state it).
5. Noise: complex Gaussian per visibility and correlation, σ = 520 / sqrt(2 · 10 · dfreq) per real
   and imaginary part as spiel's `noise_stddev`; seeded per (s, f) by a recorded rule (spiel's was
   unseeded); `WEIGHT_SPECTRUM` from σ, imaged with uniform weighting as spiel did.
6. Products per field, as the thesis lists: dirty image, PSF, sky model (a 256² image at 1.6″ with
   the 100 components on the grid, plus the component list), WSClean model, residual and restored
   images at 256², `-scale 1.6asec -weight uniform -niter 100000000 -mgain 1.0 -auto-threshold 0.125
   -auto-mask 5` (spiel's settings, one major cycle per thesis p. 93 when `-mgain 0.95` is used for
   the comparator: run both, labelled), the clean beam. WSClean from the oracle container, its
   version recorded.
7. Shards of 100 seeds × 3 flux sets with a done-marker and SHA-256 per product; the MS deleted
   after imaging; outputs on nash under `~/rang-data/outputs/<task>-<date>/astrodeconv-r`, every job
   under the heavy lock at `nice -n 19 ionice -c3`. Time one shard first and add a row to
   `tool-timings.md`; estimate above: about 30 core-hours for 10,000 fields, so about 27 for 9,000.
8. Label: "ASTRODECONV2019 regenerated (rang, route b)": matched to the thesis's stated numbers
   and to spiel's draws, not bit-identical to the published set (different uvw, noise draw,
   WSClean version).

## 2. Self-calibration cost split

### 2.1 E2-A, from receipts (glacier, exclusive, 16 threads, 2026-11-15)

Source: the run directory `D:\rang\outputs\e2a-20261115\rang-run` of the E2-A rerun (rang-core 0.2.0
wheel); its selfcal summary, the four GeMClean image reports and logs are archived in
[results/dl0-profile/e2a](results/dl0-profile/e2a) (file hashes stripped). Two rounds (Sp, then Sa;
solint 120 s, `average_time`), three images (4096², 3″, 8 output channels joined, multiscale, auto-mask
5σ, auto-threshold 3σ), 850,950 rows × 4,096 channels.

| Part of the 24,270 s stage | Seconds | Share |
| --- | --- | --- |
| three GeMClean images (5,300; 5,368; 6,020) | 16,689 | 68.8 % |
| - minor cycle (multiscale, image domain) | 10,468 | 43.1 % |
| - resyncs (an FFT pair on the 2n grid, no visibilities) | 4,798 | 19.8 % |
| - major cycles (exact degrid and grid of the in-memory visibilities) | 399 | 1.6 % |
| - read, weights, PSF and beams, write | 910 | 3.7 % |
| two solves (Sp 2,600; Sa 2,549) | 5,149 | 21.2 % |
| two model predicts into MODEL_DATA (640; 643) | 1,283 | 5.3 % |
| two applies (405; 402) | 808 | 3.3 % |
| rest (input column copy, stores) | 341 | 1.4 % |

Per image: major cycles 2.3-2.5 % of the wall (5-6 cycles, 25 s each), minor cycle 62-63 %, resyncs
28-29 %, I/O and PSF 5-6 %. What the code calls each part was read in `core/src/gemclean.rs`
(module docs, `resync`) and `core/src/gemclean/joined.rs` (`ct.major` brackets the per-channel
`GridMeasurement::residual`, a degrid and grid; `ct.minor` excludes resync time; the joined
`resync` makes each channel's map exact with one FFT convolution per channel on the 2n grid, no
visibilities). The reports' resync counters (drift, tau, every, threshold) read 0 while resync time
is 1,500-1,800 s: the counters count resyncs inside a minor cycle, and the time is the resync at
the end of each cycle (`if since[0].steps > 0 { resync!() }`), which no counter records. The imaging data are
averaged to 512 channels and held in memory, which is why a major cycle costs 25 s.

Solves: Sp 50 iterations (the cap), converged fraction 0.0; Sa 37 iterations, converged 0.99; 4
intervals each. The wall barely moves between 50 and 37 iterations; with the data averaged in time
to 4 intervals the kernel's arrays are small, so the read of 850,950 rows × 4,096 channels of data
and model is the likely cost (inferred across two term types; section 2.2 measures it on E2-N,
which takes the same `average_time` path).

### 2.2 E2-N, profiled run on nash (2026-11-19/20)

E2-N's run directory is no longer on nash (only `e2n.ms` remains, 105 GB, without CORRECTED_DATA,
MODEL_DATA or CORRECTED_1GC; its flags had been put back to the input state, 0.315 flagged), so no
receipt below the stage totals exists. One profiled run, started 2026-11-19 09:31 SAST:

- run root `nash:~/rang-data/outputs/dl0-profile-20261119`; own copy of `e2n.ms` (5 min); the
  source directory is never written;
- flags restored to version `rang_calibrate_20261117T022650Z` (saved before calibrate's first flag
  write, so the flag stage's output): 0.315 → 0.638 flagged, 2,229,489 rows (`restore.json`);
- E2-N's frozen configuration with `run.stages: [calibrate, apply, selfcal]` (no flag, no image stage);
- rang-core **0.3.0** from PyPI (the original ran the 0.2.0 wheel), 16 heavy-lock slots, 64 GB,
  `RAYON_NUM_THREADS=OMP_NUM_THREADS=16`, nice 19, ionice idle, shared host;
- py-spy 0.4.3 at 1 Hz on every thread and subprocess (`--idle`, Python frames only, raw stacks), to
  split each solve into read and iterate and calibrate into its terms;
- driver and shards: [results/dl0-profile/scripts](results/dl0-profile/scripts); done-markers per shard;
  `rang-core run` resumes per stage, but the selfcal stage is one unit (its round directories are made
  fresh), so an interruption loses up to the stage's progress: a stated exception to the 15-minute rule.

Ran 09:31:39 to 01:34:41 SAST, 57,780 s wall (`/usr/bin/time`), one attempt, rc 0: calibrate
4,131 s, apply 3,998 s, selfcal 49,613 s (the original 0.2.0 run: 4,819, 1,319 and 49,304 s). Peak
RSS 33.5 GiB. CPU 256,826 s (user 215,104, system 41,722), **4.4 cores on average against 16
booked**. py-spy: 94,673 samples, 0 errors; main thread 57,923, three GeMClean subprocesses
11,740-13,023 each. Archive: [results/dl0-profile/e2n](results/dl0-profile/e2n) (state, summaries,
image reports and logs with file hashes stripped, the receipt, the py-spy raw stacks, the time file).

| Part of the 49,613 s selfcal stage | Seconds | Share |
| --- | --- | --- |
| three GeMClean images (12,925; 11,791; 11,947) | 36,662 | 73.9 % |
| - minor cycle (multiscale, image domain) | 22,897 | 46.2 % |
| - resyncs | 9,466 | 19.1 % |
| - major cycles (exact degrid and grid) | 1,155 | 2.3 % |
| - read, weights, PSF and beams, write | 2,734 | 5.5 % |
| input-column copy CORRECTED_DATA → CORRECTED_1GC (py-spy: 5,327 samples in `Table.getcol` under `_copy_column`) | about 5,530 | 11.1 % |
| two solves (Sp 1,971; Sa 1,724) | 3,695 | 7.4 % |
| two model predicts (1,030; 915) | 1,945 | 3.9 % |
| two applies (855; 614) | 1,470 | 3.0 % |
| rest (writeback sessions, stores) | about 310 | 0.6 % |

Per image: major cycles 3.1-3.2 % of the wall (6 cycles each), minor cycle 60-64 %, resyncs
24-27 %; 932,000-952,000 components (E2-A: 390,000-722,000), which with nash's slower, shared cores
likely explains the 2.0-2.4 × longer images at a quarter of E2-A's channels (both image 512
channels; not measured apart).

Inside the solves (py-spy, main thread, 3,649 samples at 1 Hz): `load_averaged` 3,640 (reading the
rows, 737 of them in `read_rows`, and averaging them into the 9 intervals; `_Field.prepare` 255),
`_kernel` 9. **Iterations are 0.25 % of the solve, 0.02 % of selfcal.** Sp took 10 iterations
(converged 0.996), Sa 39 (0.991), 9 intervals, 1,596,004 rows each; QuartiCal on the original
averaged inputs took 9-11 and 19-49. Calibrate (4,131 s, 4,070 samples): G-type `gaincal` 1,448
(1,417 in `load_averaged`), `gpol` 626 (556), `applycal` and model column set-up 611, `df` 228, `xf`
190, `kcross` 178 (these three almost all in table reads), `bandpass` 175 (173). Over the stage:
3,134 samples (77 %) in reads and averaging, 6 (0.15 %) in recognisable solver kernels (`_kernel`,
`solve.<locals>.kernel`, `_df_kernel`), the other 930 in writes (`Table.putcol` 547), flag rows and
Python glue; a solver call without a Python frame of its own would sit in those 930, so 23 % is the
upper bound of calibrate's compute. Apply (3,998 s): 3,149 samples in `Table.getcol`.

Caveats: the run used ionice idle on a shared disk, so its I/O phases (copy, apply, solves' reads)
are upper bounds; E2-A's copy took 341 s on glacier's local D:. GeMClean's own threads are not in
py-spy's Python stacks; its split comes from its reports. Booking: about 20,800 s of the run (calibrate,
apply, the column copy, solves, predicts and applies) ran on about one core; by subtraction the
images averaged about 6 cores of the 16 booked (derived, not measured per phase).

### 2.3 What the pilots already said

Floor-5 G1 (one Sp round, ESO137 pilot, nash shared): solve 1,695 s (61 %), images 782 s (28 %).
selfcal-memory default (Sp then Sa, unaveraged, streamed): solves 343 + 575 s of 2,207 s, the
streamed read pass 134 s of each, iterations 13 and 37. On the 256-channel pilot images are small
(2,048²-class, 230-320 s each), so the solve dominates there; at E2 size the image dominates. The DL4
pilots must be scored at E2 size, not on the pilot, or they optimise the wrong part.

## 3. The gain solver's present starting point

- `rang.cal_selfcal.solve` sends Sp and Sa to `rang.cal_gain._solve_gain_field` →
  `_kernel` → `ext.cal_gain_solve` (Rust, `core/src/solve.rs`, a port of QuartiCal 0.2.7's complex
  solver). `solve_traced` initialises every gain state with `gain: IDENTITY, km1_gain: IDENTITY`
  (`core/src/solve.rs` around line 1330); flagged or diverged gains are reset to identity. No
  previous interval, previous round or calibrator solution is passed in, and the Python layer has no
  argument for one.
- Sd (delay and offset) goes through `cal_delay._solve_field` with `initial_estimate=False`
  (`cal_selfcal.py` line 300): no FFT delay estimate in selfcal; `offset_start=True` is passed but
  applies "with the initial estimate only" (`cal_delay.py` docstring), so delays and offsets start
  from zero (read from the docstring and `zero_start = zero_start and initial_estimate`, not traced
  into the kernel).
- Stop rule: per gain `|g_k − g_{k−1}|² / |g_{k−1}|² < stop_criterion²` (`core/src/solve.rs`,
  `stop_criterion` 1e-7), an interval passes when `stop_fraction` 0.99 of its gains do,
  `max_iterations` 50. On E2-A Sp never met it (0 of 4 intervals at 50); on E2-N rang took 10 (Sp) and 39 (Sa);
  QuartiCal on E2-N's averaged inputs took 9-11 (Sp) and 19-49 (Sa) iterations
  (`results/e2n/score/qc-selfcal.json`).

So DL4a's comparison arms (dl-plan stage 2: identity, previous interval, previous round, FFT start)
are all unimplemented except identity; the classical warm starts must be built before a network can
be compared with them. With `average_time` the iterations cost seconds (section 2.2), so a warm start
can matter for robustness (E2-A's Sp at the cap) but not for wall time.

## 4. Recommended order of #41-#44

1. **#42 DL4b, minor-cycle proposals (stage 7), first.** It holds 63 % of selfcal on E2-A, 65 % on
   E2-N, and the same share of every image stage. Two changes to its framing follow from section 2.1: the gain is
   counted in **minor-cycle work and wall** (components, sub-minor loops, resyncs), not major cycles
   alone, since major cycles are 1.6 %; and the classical comparator includes cheaper multiscale
   settings (fewer scales, larger gain), because 10 scales on 4096² with 35,605 convolutions is where
   the time is. Mode P keeps the exact major cycle between network passes, as R2D2 does. Step 0 needs
   ASTRODECONV2019 regenerated (section 1.6). AIRI's MRI shelf is the one released learned arm with
   real MeerKAT evidence (quality arm, not a cost arm).
2. **#43 DL4c, mask (6) and settings (9), second.** The auto-mask decides where the minor cycle works
   (major iteration 4 of 5 continues in the mask at reduced gain, E2-A round 1); a mask that stops
   the minor cycle earlier at equal false flux saves from the same 63 %. Settings (solint, scales,
   cut-offs) are cheap to score on the grids already run. Quick-look (10) stays last of the three.
3. **#44 DL4s, screenings (3, 4, 5a), third, on spare slots.** One day each, light; 5a has no
   precedent and accuracy gates of 1e-4 to 1e-9; stage 3 has a precedent (the ALMA classifier).
4. **#41 DL4a, gain warm start (stage 2), last, as a one-day screening, not a pilot.** In the E2
   configuration (time-averaged solves, the configuration of the acceptance runs and of CARACal's
   estimator) the rule of dl-plan stage 2 (wall ≤ 0.7 × the best classical start) cannot be met:
   iterations are 0.25 % of the selfcal solve and 0.15 % of the calibrate stage (23 % at most, if
   every unattributed sample were solver compute), the rest is reading and averaging rows. What
   remains is robustness (E2-A's Sp ran to the 50-iteration cap with converged fraction 0.0) and
   unaveraged solving (`selfcal.average_time: false`, rang's default), where iterations dominated on
   the pilot; the screening states which configuration it serves. The classical warm starts of
   section 3 come before any network.

Classical follow-ups found by the profile, outside DL4 and larger than #41's ceiling (for the
coordinator to issue or not): the selfcal input-column copy (5,530 s, 11 % of E2-N's selfcal, read-
bound in `Table.getcol`), the solves' read of all rows once per round (Sp and Sa read the same input
column; one averaged read could serve both), and the heavy-lock booking of a pipeline run, which held
16 slots for phases that use one core.

## 5. Open points for the owner

- Licences: R2D2-RI `main` has no LICENSE; AIRI's astro-trained shelf has none; rcGAN and
  astroNNomy have none. Asking the authors is the owner's call (nobody was contacted).
- Whether CC BY-NC MeerKAT survey images (MGCLS, MIGHTEE, SMGPS) may train weights that ship under
  GPL.
- ASTRODECONV2019: decided 2026-11-19, route (b), 9,000 fields (section 1.6). Still open, and not
  blocking: which count the thesis meant (10,000 on p. 92, a 100,000 split on p. 93).

## For the coordinator

- Wave-2 order: **#42, #43, #44, #41** (#41 as a one-day screening). Basis: minor cycle plus resyncs
  63 % (E2-A) and 65 % (E2-N) of selfcal; major cycles 1.6-2.3 %; solver iterations 0.25 % of E2-N's
  selfcal solve, 0.15 % of its calibrate stage (time-averaged configuration).
- dl-plan section 1 needs one amendment: "A network pays in imaging only by reducing the number of
  major cycles or solver iterations, not by replacing the gridder" should read that GeMClean imaging
  at E2 settings is minor-cycle bound (multiscale, 4096², 8 joined channels), so stage 7's gain is
  minor-cycle work and wall, and that solver iterations are negligible in the time-averaged
  configuration. Stage table row 2's prior can cite section 2.2.
- #42 step 0: ASTRODECONV2019 regenerated by rang (route b), 9,000 fields, specification in 1.6.
- Classical follow-ups, not DL (issue or not): the selfcal input-column copy (E2-N 11 %, E2-A 1.4 %),
  one averaged read shared by Sp and Sa, read-bound apply, and heavy-lock bookings of whole pipeline
  runs (16 slots held for single-core phases; 4.4 cores used on average).
- Owner points: section 5.
- Left on nash, not deleted: `~/rang-data/outputs/dl0-profile-20261119` (326 GB: the MS copy with
  CORRECTED_DATA, MODEL_DATA and CORRECTED_1GC, the run directory, py-spy file); the worktree
  `~/Worktrees/rang/dl0-profile` (206 MB, venv, branch `dl0-profile-nash` at origin/main, scripts
  uncommitted copies of this branch's). Everything needed is archived in
  [results/dl0-profile](results/dl0-profile); both can be removed.
