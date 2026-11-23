<!-- SPDX-License-Identifier: MIT -->
# DL4b (#42) step 1: learned minor-cycle proposals at 4096² multiscale

**Status, frozen 2026-11-21: proposed; nothing simulated, trained or run.** **Outcome, 2026-11-22: F (fail): P outside the tolerance on all 4 gated skies for all 3 seeds (relative L2 1.22-1.79 × W1's) and slower than W\* (minor cycle 1.10-1.93 ×); as stated before the read** ("Measured result").

- Branch `dl4b-step0`, after step 0's outcome F ([dl4b-step0.md](dl4b-step0.md)).
- Route: [docs/agents/propose-and-measure.md](../docs/agents/propose-and-measure.md).
- Results go under "Measured result". Nothing above it changes except by a dated, labelled amendment.
- Go-ahead: the coordinator on 2026-11-21, on the owner's word ("keep glacier and nash busy and keep going"), taken as approval of 18 GPU hours.

**The draft's four owner decisions, taken here as defaults** (the owner may overrule them before stage 2):

1. Go: as above.
2. Skies at 8 channels, rml-gap's form, not E2's 512.
3. **No GeMClean change.** GeMClean has no warm start (checked in `core/src/gemclean*`, 2026-11-21). WSClean's own `-continue` finishes from a given model, so every arm runs in WSClean 3.7 and the core is untouched. GeMClean's minor cycle, the 63-65 % of selfcal, is the motivation. The measurement is in WSClean, whose multiscale minor cycle has the same structure ([g5-multiscale.md](g5-multiscale.md)). A gain carries over to GeMClean only through a later port, which is not claimed here.
4. The 6 real stage-7 scans wait for C's teacher runner. No real data in step 1.

## 0. Pre-freeze orientation (measured before this commit; `results/dl4b-step1/orient.sh`, `orient_infer.py`)

Measured on glacier, 2026-11-21, with docker WSClean 3.7, `-j 16`, a shared host, and two throwaway skies. The skies use H4's and H5's recipes at 4096² with orientation seeds 990004 and 990005 (sky) and 991004 and 991005 (noise); the seed rule excludes them from every later set.

| Sky | Simulate | W1 wall | Deconvolution | Inversion | Prediction | Major cycles |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| H4 (extended) | 66 s | 524 s | 411 s (78 %) | 52 s | 26 s | 6 |
| H5 (200 points) | 90 s | 429 s | 296 s (69 %) | 64 s | 34 s | 8 |

- **The minor cycle dominates here**, unlike step 0's 1 %. The cost question is decidable.
- **One CAN-48 pass** at 4096² (random He weights, ONNX Runtime, 16 threads): **8.4 s**. K = 3 passes cost about 25 s of inference plus 3 exact cycles of about 30-40 s each (predict and invert at this size).
- **`-continue` needs MODEL_DATA.** A run with `-no-update-model-required` leaves none, and `-continue` then fails ("Table column MODEL_DATA is unknown"). P's exact cycle writes MODEL_DATA with `-predict` before `-continue`. Predict-then-continue (`cont2.sh`) on H5: W1 stopped after 1 major cycle, then `-predict` (115 s wall standalone), then `-continue` with W1's settings.
  - It ends at the full run's result: model flux 60.2646 against 60.2639 Jy, residual rms 2.66e-5 against 2.71e-5.
  - Continuing from a 1-major-cycle model **saved little**: still 8 major cycles and 279 s of deconvolution, against 296 s from zero. WSClean re-derives its mask and threshold schedule.
- **Expected outcome, stated now.** G needs a proposal that leaves `-continue` little to clean. The extra exact cycles, about 115 s of predict plus an inversion each, count against the total-wall clause, so G is reachable only with K = 1 or 2 and a strong proposal. N or F is the likelier outcome, as for most pilots in [dl-plan.md](dl-plan.md) 9.

## 1. Question and hypothesis

Step 0 could not decide cost: the minor cycle was about 1 % of a 256² field's wall. Here the fields are 4096² × 1.5″ with multiscale CLEAN and an auto-mask, E2's imaging shape at 8 channels. There the minor cycle dominates.

**Hypothesis.** On held-out simulated MeerKAT skies, arm P beats the cheapest WSClean setting of the same quality: it reaches unrestricted WSClean's quality at **≤ 0.5 × that setting's minor-cycle wall**, its own wall counting the network's inference. Arm P works in three steps:
- a network proposes the model in a few passes, with WSClean's exact major cycle between them;
- the proposal is thresholded;
- WSClean then finishes with `-continue` to its usual stop.

**What step 0 taught, built in here:**
- the networks put false flux on sidelobe structure, so P's proposal is thresholded and WSClean's auto-mask governs the finish;
- the stored PSF can be wrong, so every training pair comes from WSClean's own images;
- scale equivariance holds (bias-free network).

**Not claimed:**
- real-data quality;
- a GeMClean speed-up;
- E2's 512-channel shape;
- novelty, beyond what the rule below decides against WSClean ([dl-plan.md](dl-plan.md) 9);
- **PSF generalisation.** The simulator on this branch has no `--dec`, so training and gated skies share the recipes' declinations (H4 −45, H5, H6 and S3 −30, H7 −10, M1 −60) and their PSFs. Held-out here means held-out skies and noise, not held-out uv coverage. G-sub and G-drop are not tested.

## 2. Data

**All skies:**
- MeerKAT, 64 dishes, 2 h at 8 s, 8 channels 1.3-1.5 GHz, 20 µJy natural noise, flat spectra, continuous positions;
- 4096² × 1.5″ (1.7°);
- simulated by `examples/gemclean_bench_simulate.py` (exact DFT; recipes and declinations as listed there);
- seeds per the sky-seed rule below.

| Set | Skies | Recipes (count each) | Use |
| --- | --- | --- | --- |
| train | 160 | S3 (40), H5 (40), H6 (20), H7 (30), H4 (30) | training pairs only |
| validation | 4 | V1 = H4, V2 = H7, V3 = H6, V4 = H5 | checkpoint choice, threshold choice, W\* choice |
| **gated, held out** | 4 | G1 = H4 (dec −45), G2 = M1 (H4 at −60), G3 = H7 (−10), G4 = H6 (−30) | the decision, **read once** |

**Seeds.** For each sky name X (T001-T160, V1-V4, G1-G4), the sky seed and noise seed are the first and next 8 hex digits, as integers, of `sha256("<freeze commit> X")`. `<freeze commit>` is the full hash of the commit that adds this note. The rule is rml-gap's. They are recorded in a second commit before any sky is simulated; a collision with an existing seed moves on by 8 digits.

**Seed record** (2026-11-21, written after the freeze commit `bf11092215bc7a6c8fa49bb5668a042266c0e7bb`, before any sky is simulated): 168 skies, no collision. The table is `results/dl4b-step1/seeds.json`. Examples: G1 (H4) sky **1145306936**, noise **315645864**; T001 (S3) sky **2091146829**, noise **2507257797**. Nothing is redrawn.

**Products per sky,** WSClean 3.7 (`rang-wsclean-native:3.7`, docker on glacier, or native on nash; step 0 found them equal in 3,780 runs):
- dirty image and PSF, 4096², Briggs 0.5, MFS over the 8 channels (`-channels-out 1`);
- truth catalogue.

**Training pairs:**
- 512² crops: the dirty crop, the beam-convolved truth crop (`rml_gap_score.truth_on_beam`, analytic, continuous positions), and the central 1024² of the sky's 4096² PSF;
- that PSF patch is the exact operator for a model confined to the crop and output inside it. Flux outside a crop enters as its sidelobes, as out-of-field sources did in step 0;
- training MSs are deleted after imaging. Validation and gated MSs are kept on `D:/rang/dl4b-step1`.

## 3. Arms (WSClean 3.7, 4096² × 1.5″, Briggs 0.5, `-j 16`, `-niter 10000000`, `-no-update-model-required`)

| Arm | Settings |
| --- | --- |
| W1 | `-multiscale -auto-mask 5 -auto-threshold 3 -mgain 0.8` (E2's mask and threshold), WSClean's default scales and gain |
| W2 | W1 with `-multiscale-scales 0,4,16,64` |
| W3 | W1 with `-gain 0.2` |
| W4 | W2 with `-gain 0.2` |
| W5 | W1 with `-mgain 0.9` |
| **P** | network passes (below), then `-continue` with W1's settings to WSClean's usual stop |
| T, Z | truth and the empty model, through the scorer (ceiling, floor) |

**P in detail:**
1. Dirty image from WSClean (`-niter 0`).
2. Network passes p = 1, …, K. Each pass is `m ← max(m + s·f(r/s, m/s), 0)` at 4096², fully convolutional, with s the residual's robust rms (Jy per beam).
   - **Threshold on the beam-convolved proposal:** zero every model pixel where (b ⊛ m) ≤ τ·s, with b the clean beam (peak 1), so b ⊛ m is in Jy per beam like s. Extended emission survives where its beam-convolved brightness clears the threshold.
   - Then the exact major cycle: WSClean `-predict` of m (which also writes MODEL_DATA), DATA − MODEL_DATA, `-niter 0`. This is step 0's exact cycle, checked there to 4e-5.
3. `-continue` from m with W1's settings.

- **K and τ** are chosen on validation from K ∈ {1, 2, 3} and τ ∈ {3, 5}, before any gated sky is read. They are **common to all seeds**: the pair inside the tolerance on validation for every seed with the lowest median cost. If no pair passes, the gated skies are still run with the pair of lowest median relative L2, and outcome F is expected and stated before the gated read.

**W\*** is chosen on validation: the arm among W1-W5 with the lowest median deconvolution time whose quality is inside section 5's tolerance against W1.

## 4. Network and training

**Network.** Step 0's bias-free dilated CAN (Conv and Relu only; He init, zero output layer; dilations 1, 1, 2, …, 128, 1, 1; receptive field 517 px) at **48 hidden channels**, about 208,000 weights. Normalisation, update and threshold stay outside the ONNX graph (opset 17). The architecture is not searched.

**Training:**
- the NP form of step 0: K_train = 4 passes on crops, through the image-domain operator with the PSF patch;
- loss on the unclipped update: squared error at beam resolution against the beam-convolved truth, normalised by the crop's dirty robust rms;
- AdamW, learning rate 1e-3, cosine decay over the run's step count;
- batch the largest that fits (recorded);
- flips and transposes applied to dirty, truth and PSF together;
- bit-identical resume, 15-min checkpoints, validation on the 4 validation skies through the image-domain operator every 15 min;
- `best.pt` by the **relative L2 on the beam** over the validation crops (lower is better). Step 0's recovery-based score is undefined for extended sources.
- **Crops are sampled statelessly** from (seed, step), since the data no longer fit on the GPU. The resume test is rerun on this pipeline before budgeted training. The batch and step rate are probed first, and the schedule length is set from them and recorded.

**Budget:** 18 GPU hours (glacier RTX 4070 Ti, `gpu_run.py run --owner rang`):
- 3 seeds × 5 h;
- 3 h reserve for the resume test, the smoke runs and validation passes.
- Gates in the loop (step 0, amendment 3): validation at step 500, abort if the loss is above 0.9 of the empty model at step 1,000.
- Yield windows: Saturday 20:50 to Sunday 06:30 (#47) and daily 06:00-06:50.

## 5. Measures, tolerance and decision rule

**Measures:** `examples/rml_gap_score.py`, frozen in [rml-gap.md](rml-gap.md) section 4:
- common beam from W1's PSF;
- **relative L2 on the beam (primary)**;
- extended-group flux (measure 3) and positions (measure 4);
- **false flux** (measure 5: |model| outside every group, over the total true flux);
- exact residual.

The scorer's truth control must pass on every sky before its arms are scored.

**Cost:**
- **Minor-cycle wall:** WSClean's `deconvolution` time from its log, plus for P the network's inference. That inference is ONNX Runtime at 16 threads on glacier, the same host.
- **Inversions** and total wall are reported.
- **Gated timings are exclusive:** an exclusive heavy-lock hold on glacier, `-j 16`. Each arm runs **twice**, in a fixed order (W1, W\*, P seeds 1-3, then repeated), and the mean is used. A cost ratio inside 0.45-0.55 is flagged and counts as the cost clause failing.

**Tolerance (P against W1, per gated sky and seed):**
- relative L2_P ≤ 1.10 × relative L2_W1;
- false flux_P ≤ false flux_W1 + 0.01;
- extended groups failing measure 3: no more than W1's.

**Decision** (gated skies G1-G4, three seeds):

| Outcome | Rule |
| --- | --- |
| **G** (gain) | for every seed, on ≥ 3 of 4 gated skies: P inside the tolerance **and** P's minor-cycle wall (deconvolution plus inference) ≤ 0.5 × W\*'s **and** P's total wall (with its extra exact cycles) ≤ W\*'s total wall |
| **N** (null) | for every seed, P inside the tolerance on ≥ 3 of 4 skies, but the cost clause fails on 2 or more |
| **F** (fail) | for 2 or more seeds, P outside the tolerance on 2 or more skies |
| **mixed** | none of the above |

G is labelled "at 4096² multiscale in WSClean on simulated 64-dish skies"; it is not a GeMClean or a real-data claim.

**Reported, deciding nothing:**
- P's proposal alone, without `-continue`, scored;
- per-sky inversions;
- total stage wall;
- the image-domain against exact operator gap;
- W5 and the multiscale-scale arms against W1.

## 6. Stages and stop rules

1. Freeze (this commit), push. A second commit records the seeds.
2. Simulate validation and gated skies, then the 160 training skies:
   - glacier CPU at 15-16 slots when free, else nash under about 36 slots shared with D;
   - shards of 10 skies with done-markers;
   - MS deleted after the training skies are imaged.
3. Scorer control on V1-V4 and G1-G4; precondition dirty images. **Crop-operator gate**, with step 0's tolerance and a stop on failure: on V1-V4, the image-domain residual of W1's model through the 1024² PSF patch against WSClean's own residual, for 512² crops at the field centre and at a corner. Median relative rms error ≤ 0.10 at both.
4. Training crops built; resume test; smoke run (500 steps, gates); seeds 1-3.
5. Validation:
   - ladder W1-W5 → W\*;
   - P for K ∈ {1, 2, 3} × τ ∈ {3, 5} with each seed's `best.pt` → choose K and τ by the tolerance, then the lowest median cost;
   - recorded before stage 6.
6. Gated skies, read once: W1, W\* and P seeds 1-3 under exclusive holds; score; apply section 5.
7. Measured result, archive `research/results/dl4b-step1/`, timing rows, hand-back.

**Operations:**
- The trainer's yield windows are passed per launch. A launch before Saturday 20:50 carries 20:50-23:59 and 00:00-06:50.
- CPU pools have no yield, so they are stopped at their done-markers by 20:45 on Saturday.

**Stop rules:**
- A run that fails is repeated once, then recorded as the arm's result.
- If the smoke gate fails, stop and report before any budgeted training.
- If simulation of the 160 training skies exceeds 12 h of the host, train on what exists, with the count recorded.

## Amendment 1 (2026-11-21 07:35, post hoc: after seed 1 collapsed; before any budgeted seed, exact-cycle score or gated read)

**What failed.**
- Seed 1 (06:51 start, batch 8, learning rate 1e-3) stayed at the empty model: validation relative L2 1.000 at step 500.
- The abort gate stopped it at step 1,000: loss over the empty-model loss was 1.000.
- The smoke run (seed 99, same settings) had learned (0.159 at step 500, 0.138 at step 1,000), so the collapse is seed-dependent. The likely cause is dead ReLUs after large first updates; it was not diagnosed further.

**Changes to section 4**, for every seed:
- **Learning-rate warm-up:** linear over the first 500 steps, then cosine to 0 over the rest.
- **Gradient-norm clipping at 1.0.**
- Seed 1 is rerun from scratch; the failed run is kept as `runs/seed1-failed-collapse`.
- Test, seed 1, 700 steps: validation relative L2 0.128 at step 600; loss ratio 0.76 at step 50 and 0.015-0.08 from step 350. Script: `results/dl4b-step1/test-warm.sh`.

**Settings fixed by section 4's probes** (pre-registered there to be set after the probe):
- **Batch 8:** 1.47 s per step, 5.4 GiB peak. Batch 16 exceeded the card's memory.
- **Per-pass backward** (gradients identical to the summed loss, a quarter of the memory); the resume test passes bit-identically with it.
- **Schedule:** 12,000 steps, about 5 h at 1.43-1.47 s per step.

**GPU time so far** (counted against the 3 h reserve): smoke 24 min, failed seed 1 25 min, warm-up test 17 min, resume tests and probes about 15 min, so about 1.35 h. Seeds 1-3 at 5 h each bring the total to about 16.4 of 18 h.

## Measured result

### Outcome (gated skies G1-G4, read once, 2026-11-22; scored with every repeat 14:09)

**F (fail), as stated before the read.** For all three seeds, P is outside the tolerance on all 4 gated skies, so it fails the quality clause. It is also slower than W\*.

| Sky | W1 relative L2 | P relative L2 / W1 (seeds 1 / 2 / 3) | P false flux − W1's | Minor cycle, s: W1 / W\* / P (seeds 1 / 2 / 3) | Total wall, s: W\* / P (seeds 1 / 2 / 3) |
| --- | ---: | --- | --- | --- | --- |
| G1 (H4, dec −45) | 0.0041 | 1.46 / 1.79 / 1.51 | +0.0015 / +0.0085 / +0.0009 | 548 / 549 / 629, 691, 605 | 569 / 667, 727, 642 |
| G2 (M1, dec −60) | 0.0052 | 1.22 / 1.55 / 1.31 | +0.0010 / +0.0084 / +0.0021 | 456 / 536 / 610, 648, 589 | 557 / 647, 687, 626 |
| G3 (H7, dec −10) | 0.0028 | 1.39 / 1.76 / 1.60 | +0.0245 / +0.0354 / +0.0178 | 461 / 426 / 535, 558, 500 | 446 / 573, 594, 537 |
| G4 (H6, dec −30) | 0.0068 | 1.45 / 1.73 / 1.36 | +0.0011 / +0.0085 / −0.0001 | 167 / 160 / 252, 309, 185 | 178 / 287, 343, 219 |

**Reading the table.**
- **Quality.** Relative L2 is 1.22-1.79 × W1's against the 1.10 allowed. False flux stays inside its +0.01 allowance except on G3, the H7 sky with Gaussians on points, at +0.018 to +0.035. Extended groups fail measure 3 on no arm.
- **Cost.** P's minor cycle (`-continue` deconvolution plus one 8 s inference) is 1.10-1.93 × W\*'s, against the ≤ 0.5 × that G required. Its total wall is above W\*'s on every sky and seed.
- **Why it is slower.** Starting `-continue` from the network's thresholded proposal does not shorten WSClean's multiscale schedule. WSClean re-derives its mask and threshold and spends longer cleaning the proposal's errors than it would have spent from zero. The pre-freeze test (section 0) had shown that continuing saves little even from WSClean's own 1-cycle model; here the start is worse.
- **Repeat timings.** The two exclusive timings per arm agree to within a few per cent (`decision-gated.json`).
- **Seeds.** Seed 2 is the worst on every sky.
- **W\* on the gated skies.** W5, chosen on validation, is not cheaper than W1 on G1 and G2 (549 against 548 s, 536 against 456 s). The rule compares P against W\*, and P loses to both.

**Cost and provenance:**
- **GPU:** about 15.7 of 18 h. Training: 17,555 s, 17,146 s and 16,976 s for seeds 1-3, plus the smoke run, the failed seed 1 and the probes (amendment 1).
- **CPU (glacier, docker WSClean 3.7):**
  - simulation 50 min for 168 skies;
  - validation ladder about 2.3 h;
  - P validation about 12 lane-hours (4 threads);
  - gated read 08:35-13:08, plus the W repeats 13:09-14:09, in exclusive holds at `-j 16`.
- **Archive** (`results/dl4b-step1/`):
  - `score-gated.json`, `decision-gated.json` (every clause per sky and seed);
  - `score-val-P-s{1,2,3}.json`, `ktau-validation.json`, `wstar-validation.json`, `score-validation-ladder.json`, `opgate.json`;
  - the scripts (`decide_gated.py`, `choose_ktau.py`, `gated.sh`, `gated-wrepeat.sh`, the lane and waiter scripts) and the gated logs;
  - three ONNX weight files, `onnx/seed{1,2,3}.onnx`: Conv and Relu, 208,272 weights each.
- **Data:** the 168 skies stay on glacier's WSL disk (`~/Build/tmp/20261121-dl4b-step1`, 22 GB plus MS copies) and `D:/rang/dl4b-step1` (12 GB). They are removable on the coordinator's word.

**What it means for #42.**
- Neither step 0 (256² points) nor step 1 (4096² multiscale) shows a gain from mode-P proposals with this network family.
- At 256² the minor cycle was too cheap to matter.
- At 4096² the proposal is worse than WSClean's own model and makes the classical finish slower, not faster.
- A different design would be needed to revisit this, and is not proposed here:
  - a network that emits WSClean-compatible multiscale components;
  - a finish that keeps WSClean's schedule state;
  - or a learned mask instead of a learned model (#43).

### Validation choices (recorded 2026-11-22 07:35, before any gated sky is read)

**Validation ladder:**
- Scorer control passes on V1-V4 (band-limited truth relative L2 2.5e-8).
- Crop-operator gate passes: median 0.2 % at the centre, 1.4 % at a corner.
- **W\* = W5** (`-mgain 0.9`): the only arm cheaper than W1 inside the tolerance on all four skies. Median deconvolution 364.5 s, against W1's 433.5 s.
- File: `results/dl4b-step1/wstar-validation.json`.

**P on validation** (3 seeds × 4 skies × K ∈ {1, 2, 3} × τ ∈ {3, 5}; WSClean `-j 4` in lanes, inference at 4 threads; `results/dl4b-step1/ktau-validation.json` and `score-val-P-s{1,2,3}.json`):

| K, τ | Median relative L2 / W1 | Inside (of 12 seed-sky cases) |
| --- | ---: | ---: |
| 1, 3 | 1.53 | 0 |
| 2, 3 | 1.68 | 0 |
| 3, 3 | 1.69 | 0 |
| **1, 5** | **1.52** | 0 |
| 2, 5 | 1.62 | 0 |
| 3, 5 | 1.64 | 0 |

- **No pair is inside the tolerance for any seed on any validation sky.** Relative L2 runs 1.14-2.25 × W1's. False flux exceeds W1's by up to 0.04 (V2, V4).
- By section 3's fallback the gated read uses **K = 1, τ = 5**, the lowest median relative L2.
- **Expected outcome, stated now, before the gated read: F.**
- P's validation costs (median minor cycle 700-790 s) were measured in 4-thread lanes and do not compare with the ladder's `-j 15` times. The gated read times every arm alike, exclusively at `-j 16`.

**Operational record (not results):**

- **Gated read, timing order (operational amendment; method unchanged).** `gated.sh` passed `--tag "-r2"` to the ladder, and argparse read `-r2` as an option, so the second W1 and W5 timing on every gated sky never started. The second P timings ran as planned. The missing W repeats run after the main read, in a separate exclusive hold inside the same window (`gated-wrepeat.sh`, `--tag=-r2`). The order per sky becomes W1, W5, P × 3, P × 3 (repeat), and the W repeats come at the end. Every arm is still timed twice, exclusively, at `-j 16`.

- **Premature P validation, seed 1 (operator error).**
  - The P validation for seed 1 started at 08:18, while seed 1 was still training. Its trigger matched the old `seed 1 rc=4` line of the collapsed run in `runs/status.log` (amendment 1).
  - It used the `best.pt` of the training run then in progress, saved around step 1,100 (image-domain validation relative L2 0.22), not the run's final `best.pt`.
  - V1-V3 completed at WSClean `-j 16`; V4 was stopped at 11:58.
  - No choice uses it. Its 123 files are kept apart in `early-s1/` and its ONNX as `seed1-early.onnx`.
  - What was seen in its log: the `-continue` deconvolution times. On V3 they were 285-312 s against W1's 137 s.
  - The rerun waits for seed 1's `done.json` only.
- **Duplicate and concurrent lanes, seed 1 (operator error).**
  - The rerun started at 12:59, in two lanes, one per τ. A stopped waiter had already launched its lanes, and re-arming it launched duplicates; a leftover also started scoring partial results.
  - Worse, the lanes shared each validation sky's MS. P writes MODEL_DATA and reads it back, so concurrent lanes overwrite each other. A WSClean temporary-file clash on V1 exposed it at 13:12.
  - Everything from 12:59 is discarded (`discarded-s1-1259/`), unread.
  - From 13:20 each lane has a private copy of the four validation MSs (`lane-t3/`, `lane-t5/`), and lanes are started directly, never by a chained waiter.
- **Trainer killed by WSL's out-of-memory killer at 13:33.**
  - The trainer holds the training skies in memory (20 GB). With two P lanes (up to 15 GB each) and the lane MS copies, WSL's 43 GB was exceeded.
  - Seed 2 resumed from its 13:30 checkpoint (step 2,313), losing about 3 min. Resumes are bit-identical, so the run is unchanged.
  - From then on P runs one lane at a time while a trainer runs.

## For the coordinator

1. **Outcome F** (gated, read once), as stated before the read.
   - P is outside the tolerance on all 4 skies for all 3 seeds: relative L2 1.22-1.79 × W1's.
   - It is also slower than W\* = W5: minor cycle 1.10-1.93 ×, and a higher total wall.
   - Amendment 1 (warm-up and gradient clip, post hoc after a collapsed seed) is the only protocol change. The gated `--tag` fault changed the timing order only.
2. **#42 overall:**
   - step 0: F;
   - step 1: F.
   - Mode-P proposals from this network family do not beat WSClean at either scale. The findings to keep: ASTRODECONV2019's PSF error (step 0), and that `-continue` from a proposal does not shorten WSClean's multiscale schedule (section 0 and the gated read).
3. **Operator errors on this run, all recorded and none in the result:** a premature validation start on a mid-training checkpoint; duplicate lanes on shared MSs (discarded); a WSL out-of-memory kill (bit-identical resume); a launcher hung in `cmd.exe` (restarted).
4. **Clean-up on your word:**
   - glacier `~/Build/tmp/20261121-dl4b-step1` (about 40 GB with lane MS copies);
   - `D:/rang/dl4b-step1` (12 GB plus runs);
   - `D:/rang/dl4b-step0` (about 6 GB);
   - the torch venv `~/Build/tmp/20261120-dl4b-torch`.
   - Nothing of mine runs on glacier or nash. The GPU booking was yours and has expired.
