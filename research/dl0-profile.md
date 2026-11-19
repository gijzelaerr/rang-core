# DL0 (#37): literature check and stage cost profile

Status, 2026-11-19: **E2-A split measured from receipts; literature checked; E2-N profiled run
running on nash (section 2.2); DL4 order provisional until it reports.** No claim of a gain is made
here: this note measures where the time goes and checks what exists, so that #41-#44 are ordered
by the record rather than by memory. Nothing was trained.

## 0. Result in four lines

- In self-calibration on E2-A (24,270 s), **the GeMClean minor cycle and its image-domain resyncs are
  63 %** of the stage; the exact major cycles (degrid and grid) are **1.6 %**; the gain solves 21 %.
- So dl-plan section 1's "a network pays in imaging only by reducing the number of major cycles" does
  not hold for GeMClean at E2-A's settings: the cost is the multiscale minor cycle, not gridding.
- The Sp and Sa solves start every interval at **identity** (`core/src/solve.rs`); no warm start
  exists. Sp ran to the 50-iteration cap and Sa stopped at 37 with nearly the same wall (2,600 s,
  2,549 s), which suggests (inferred, two term types) that iterations are not the solve's main cost.
- Provisional order: **#42 (minor cycle) first, then #43 (mask and settings), #41 (gain warm start)
  after E2-N's read-versus-iterate split, #44 screenings on spare slots throughout.**

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
regeneration from the thesis's specification (spiel, MIT, or rang's simulator).

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
`GridMeasurement::residual`, a degrid and grid; `ct.minor` excludes resync time). The imaging data are
averaged to 512 channels and held in memory, which is why a major cycle costs 25 s.

Solves: Sp 50 iterations (the cap), converged fraction 0.0; Sa 37 iterations, converged 0.99; 4
intervals each. The wall barely moves between 50 and 37 iterations; with the data averaged in time
to 4 intervals the kernel's arrays are small, so the read of 850,950 rows × 4,096 channels of data
and model is the likely cost (inferred across two term types; section 2.2 measures it).

### 2.2 E2-N, profiled run on nash (running)

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

Result: _pending._

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
  (`cal_selfcal.py` line 300): no FFT delay start in selfcal, a zero start.
- Stop rule: `stop_criterion` 1e-7 on the relative update, `stop_fraction` 0.99, `max_iterations`
  50. On E2-A Sp never met it (0 of 4 intervals at 50); QuartiCal on E2-N's averaged inputs took 9-11
  (Sp) and 19-49 (Sa) iterations (`results/e2n/score/qc-selfcal.json`).

So DL4a's comparison arms (dl-plan stage 2: identity, previous interval, previous round, FFT start)
are all unimplemented except identity; the classical warm starts must be built before a network can
be compared with them.

## 4. Recommended order of #41-#44

1. **#42 DL4b, minor-cycle proposals (stage 7), first.** It holds 63 % of selfcal on E2-A and the
   same share of every image stage. Two changes to its framing follow from section 2.1: the gain is
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
3. **#41 DL4a, gain warm start (stage 2), third.** Solves are 21 % of selfcal, but the evidence so
   far (Sp at the cap costs no more than Sa at 37) says the solve is read-bound; a warm start saves
   iterations only. Its ceiling is the iteration share that section 2.2 measures; if the read
   dominates, the classical fix (one read shared by Sp and Sa, or solving on the averaged cells the
   predict already touches) beats any network, and #41 is screened rather than piloted. The classical
   warm starts of section 3 are built first either way.
4. **#44 DL4s, screenings (3, 4, 5a), on spare slots throughout.** One day each, light; 5a has no
   precedent and accuracy gates of 1e-4 to 1e-9.

To be confirmed when E2-N reports: whether E2-N's image (11,985 s for the image stage, 2.3 × E2-A's
at a quarter of the channels) is also minor-cycle bound, and the read-versus-iterate split of its
solves. If E2-N's solves turn out iteration-bound, #41 moves to second.

## 5. Open points for the owner

- Licences: R2D2-RI `main` has no LICENSE; AIRI's astro-trained shelf has none; rcGAN and
  astroNNomy have none. Asking the authors is the owner's call (nobody was contacted).
- Whether CC BY-NC MeerKAT survey images (MGCLS, MIGHTEE, SMGPS) may train weights that ship under
  GPL.
- ASTRODECONV2019: the owner's own copy (thesis: `/scratch/datasets/astro_deconv_2019`) or a
  regeneration.
