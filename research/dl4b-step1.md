<!-- SPDX-License-Identifier: MIT -->
# DL4b (#42) step 1: learned minor-cycle proposals at 4096² multiscale

**Status, frozen 2026-11-21: proposed; nothing simulated, trained or run.**

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

## Measured result

(empty at freeze)
