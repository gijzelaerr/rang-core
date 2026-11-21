<!-- SPDX-License-Identifier: MIT -->
# DL4b (#42) step 0: one-pass anchor and iterated mode P on ASTRODECONV2019 (regenerated)

**Status at freeze, 2026-11-20: proposed; nothing trained, no comparator run.** **Outcome, 2026-11-21: F (fail): the iterated network's false flux misses the tolerance on all three seeds; anchor consistent with the thesis; minor-cycle cost null, as expected** ("Measured result").

- Branch `dl4b-step0` from main `0df6b5da`, with `origin/dl0-profile` (`6dd70c86`) merged.
- Route: [docs/agents/propose-and-measure.md](../docs/agents/propose-and-measure.md).
- Results go under "Measured result". Nothing above it changes except by a dated, labelled amendment.
- Data: [dl4b-astrodeconv.md](dl4b-astrodeconv.md).
- Plan: [dl-plan.md](dl-plan.md) 1.1, 2, stage 7, 6, 7, 9. Costs: [dl0-profile.md](dl0-profile.md) 2 and 4.
- Owner, 2026-11-20, through the coordinator: "utilise both nash and glacier".

## 0. Pre-freeze orientation (measured before this commit, recorded so it cannot be re-chosen)

The pre-freeze check is `results/dl4b-step0/operator_check.py` (seed 0, flux set 1000, nash). Its findings:

1. **The dataset's 512² PSF (`bigpsf`) is not the PSF of the 256² images.**
   - Uniform weights depend on the grid, so run P's 512² grid weights differently. Its centre crop differs from the 256² PSF by 29 % of the PSF's rms.
   - Consequently `dirty − bigpsf ⊛ model_b` misses WSClean's `residual_b` by 28 % of the residual rms.
   - The same holds for spiel's big PSF: the thesis (p. 92) says residuals "can be reconstructed" this way, which fails by that amount. All seeds share the cause; only seed 0 was measured.
2. **Exact major cycle.** The model goes through WSClean `-predict` into MODEL_DATA; DATA − MODEL_DATA is imaged with `-niter 0`, same weighting. This reproduces `residual_b` to **4.3e-5 of its rms** (max 6.9e-6 of the dirty peak).
3. **Remade dirty.** A dirty image from a remade MS matches the stored dirty to 4.3e-5 of the peak. It is not bit-identical: that check MS used column `DATA` and no `-reorder`.
4. **Re-weighting is not a usable route.** Writing WSClean's stored imaging weights, or my own uniform weights, into WEIGHT_SPECTRUM and WEIGHT and imaging with natural weighting left the PSF unchanged to 7 digits. The cause was not found; the route is dropped.
5. **A 512² PSF built from delta responses.** For each delta, a model with one 1 Jy pixel goes through `-predict` and a 256² uniform `-niter 0` inversion.
   - With nine deltas at {0, 128, 255}², each offset is taken from the delta that puts the output pixel nearest the image centre. The PSF peak is 1.00002 and the crop agrees with the 256² PSF to 0.0071.
   - `dirty − G ⊛ model_b` reproduces `residual_b` to **5.3 % of its rms** (max 0.86 % of the dirty peak). Four corner deltas alone give 7.9 % (edge pixels respond 1.066).
   - The rest is the operator's own shift variance at the edges (WSClean's taper correction, w).
6. **Cost on this benchmark** (from the manifest):
   - run B takes 4.38 s per field (median) for 4 major cycles and 285 Högbom iterations; run A takes 1.97 s for 2;
   - so about 1 s per inversion, and the 256² minor cycle is a small fraction of that.
   - [dl0-profile.md](dl0-profile.md) 4 frames #42's gain in minor-cycle work, which is 63-65 % of selfcal at 4096² multiscale. **That share does not exist on 256² point fields.**

## 1. Question and hypotheses

Mode P for stage 7: a network proposes the model, the exact major cycle computes the residual, and the network runs again on the residual ([dl-plan.md](dl-plan.md) 1.1, 2).

- **(a) Anchor, not a result.** A one-pass network (dirty → model, the thesis's form) is scored against WSClean limited to one deconvolution pass (run A). The thesis's direction: WSClean better at the centre of the distribution (p. 95, Fig. 6.4).
  - The thesis prints no table, only a per-image scatter of E2 whose axis labels and caption disagree. So "reproduced" means the direction of the paired median difference, not a number.
  - Differences from the thesis are stated, not corrected:
    - regenerated data (rang route b, WSClean 3.7);
    - run A is `-mgain 1.0` where the thesis used `-mgain 0.95` (both give one minor-cycle pass);
    - an L1 regression network, not a pix2pix GAN.
- **(b) Hypothesis.** On held-out ASTRODECONV2019 fields, the iterated mode-P network reaches the quality of unrestricted WSClean within the tolerance of section 5. It needs at least one inversion fewer than the cheapest classical setting that reaches the same quality.
- **Not claimed:**
  - **No minor-cycle wall gain.** On 256² point fields the minor cycle is negligible (section 0.6). Both arms' minor-cycle wall is measured on the same nash CPU and reported. The expected outcome there is null, written here before any result.
  - **No E2-scale cost claim.** A gain at 4096² multiscale needs step 1 on GeMClean data.
  - **No novelty.** Fewer inversions than WSClean on simulated 16-dish point fields is a benchmark result. [dl-plan.md](dl-plan.md) 9 applies.
  - **No section 6 gates.** One array, one band: G-sub, G-drop and G-chan cannot be tested on this dataset.

## 2. Data

Source: `nash:~/rang-data/outputs/dl4b-astrodeconv-20261119/astrodeconv-r`, manifest SHA-256 `1aab25ab…2a4f`, split by seed.

| Split | Seeds | Fields | Use |
| --- | ---: | ---: | --- |
| train | 2,820 | 8,460 | training only |
| validation | 90 | 270 | checkpoint choice, comparator ladder choice, operator tolerance |
| test | 90 | 270 | **read once**, after every choice is fixed and recorded |

Products used:
- `dirty` and `truth` (nearest-pixel, in-image sources);
- `components` (all 100 per field, for attribution);
- `psf` (256²);
- the clean beam of run A (manifest), median 3.9 × 3.0 px FWHM.

New products, made on nash before training:

1. **Grid PSF `G` per seed** (section 0.5), all 3,000 seeds.
   - Each seed: one MS remade as `examples/astrodeconv_sim.py` does (`DATA_F10` only), 9 predicts and 9 inversions, `-j 1`, `-reorder`.
   - Shards of 10 seeds with done-markers, as in the data note. 300 shards, 14 slots, `nice -n 19 ionice -c3`.
   - Run root `~/rang-data/outputs/dl4b-step0-20261120/psfg`, output `psfg-KKK.npz` (float32, 512²).
2. **Operator tolerance**, frozen, measured on the 90 validation seeds × flux 1000 against `residual_b`.
   - The image-domain residual must have a median relative rms error of **≤ 0.10**.
   - If it fails, stop and report before training.
   - The image-domain operator is for GPU training only. Every score in section 5 uses the exact cycle.
3. **Remade MS for validation and test seeds**, for the exact cycle, made per shard in `/dev/shm` and deleted after.
   - Each remade dirty must match the stored dirty to **≤ 1e-4 of its peak**. A field that fails is reported and excluded from both arms.

## 3. Networks

**Architecture.** A bias-free dilated context-aggregation network:

- No new ONNX operators; B's interpreter already runs it.
- Layers: 3×3 Conv with dilations 1, 1, 2, 4, 8, 16, 32, 64, 128, 1, 1, then a 1×1 Conv to one channel.
- 32 hidden channels, Relu between layers, no Conv bias, no normalisation layers.
- Receptive field 517 px, enough for the PSF's ±255 px.
- About 93,000 weights. ONNX opset 17, ops Conv and Relu only.
- Without biases the network is positively homogeneous (f(αx) = αf(x)). It therefore treats the three flux scales and the fainter later residuals the same, without learning them.
- Outside the graph:
  - inputs (residual, current model) are divided by s, the residual's robust rms (1.4826 × MAD), per pass;
  - the output is multiplied by s and added: m ← max(m + s·f(r/s, m/s), 0). The truth is non-negative.

**Arms** (one architecture, separate weights per arm and seed):

| Arm | Form | Training |
| --- | --- | --- |
| N1 | one pass: m₁ = max(s·f(dirty/s, 0), 0) | loss on m₁ |
| NP | iterated: pass k sees r_k = dirty − G ⊛ m_k (image domain in training), from m₀ = 0, K = 4 passes | loss summed over passes 1-4; m_k detached between passes (each pass learns from the states the current network produces) |

**Loss.** L1 of (m − truth) ⊛ b, where b is the field's clean beam (a Gaussian from run A's fitted beam, peak 1), divided by s₀ (the dirty image's robust rms). No adversarial term and no PSF term (dl-plan 1.1).

**Training:**
- AdamW, learning rate 3e-4 with cosine decay to 0, weight decay 0, batch 16.
- Augmentation: random flips and transposes, applied to dirty, truth, beam and G together, so the operator stays consistent.
- Data order and weight initialisation from the seed.
- Seeds 1, 2 and 3 for every arm.

**Budget** (glacier RTX 4070 Ti, 12 GB, through `gpu_run.py run --owner rang`): 24 GPU hours with three seeds.

- N1: 1 h per seed.
- NP: 5 h per seed.
- That is 18 h, with 6 h held for the anchor's and NP's validation passes, resumes and the resume test.
- Wall time to a checkpoint counts against the budget; time lost to a yield or a driver reset does not.
- If a seed reaches its cap, its best validation checkpoint is used. Nothing is extended.

**Data on the GPU:**
- training dirty images as float32 (2.2 GB);
- grid PSFs as float32 FFTs, one per training seed: about 3.0 GB for real-FFT halves of 512²;
- truth as sparse lists, beams as 3 floats per field.
- If that does not fit beside the model at batch 16, the PSFs move to pinned host memory, recorded. Only the shards a run needs are copied to `D:`, and removed after.

**Checkpoints:**
- Every 15 minutes, holding weights, optimiser, step, RNG states (torch, CUDA, numpy) and the data-order position.
- Resume must be bit-identical: a 200-step run, and a 100-step run that resumes from its step-100 checkpoint and runs 100 more, must give equal weights.
- That test passes before any budgeted run.
- A driver timeout or reboot resumes from the last checkpoint.
- The GPU is yielded at 20:50 today (D's timing reservation 20:55-22:30, then B's) and for the standing 06:05-06:45 slot. A hard stop in the loop does this, independent of `gpu_run.py check`, since D's reservation carries the same owner name.

**Validation during training:**
- Every 15 minutes, on the 270 validation fields, with the image-domain operator.
- Measure: the flux-weighted recovery minus the false-flux fraction, mean over fields (section 5 measures).
- Checkpoint choice: the best of these per arm and seed.

## 4. Classical comparators (nash, WSClean 3.7, `-j 1`, `-reorder`, `nice -n 19 ionice -c3`)

Common to every arm: the dataset's settings `-size 256 256 -scale 1.6asec -weight uniform -niter 100000000 -auto-threshold 0.125 -auto-mask 5`, unless the table changes them.

| Arm | Change | Why |
| --- | --- | --- |
| W-A | `-mgain 1.0` (run A) | the thesis's comparator (anchor) |
| W1 | `-mgain 0.8` (run B) | unrestricted WSClean, the reference quality |
| W2 | W1 with `-gain 0.2` | cheaper Högbom |
| W3 | W1 with `-auto-threshold 1` | shallower stop |
| W4 | W1 with `-mgain 0.9` | fewer major cycles |
| W5 | W1 with `-multiscale` (default scales) | multiscale as in E2 |
| W6 | W1 with `-multiscale -multiscale-scales 0,4 -gain 0.2` | cheaper multiscale (dl0-profile 4) |
| Z | empty model | floor |
| T | truth as the model, through the exact cycle | ceiling for flux and false flux; its residual is out-of-field sidelobes and noise |

- Validation and test fields only, 540 fields × 7 WSClean arms.
- Shards of 10 seeds with done-markers.
- Logged per call:
  - WSClean's reported major iterations;
  - minor iterations;
  - inversion, prediction and deconvolution times from its log (the format is checked on one kept log before the run and recorded);
  - wall time under `/usr/bin/time`.
- **Matched-cost classical comparator W\***: chosen on validation. It is the arm among W1-W6 with the fewest median inversions whose quality is within the section 5 tolerance of W1. Ties go to the lower median deconvolution time. W1 qualifies by definition.

## 5. Measures, tolerance and decision rule

**Measures per field**, always on the model and on the exact residual after the arm's last cycle:

- **recovery:** the model flux within one beam (major-axis FWHM) of an in-image true source, each model pixel given to its nearest true source among all 100. This is divided by the in-image true flux. The definition is from `examples/gemclean_bench_compare.py` `flux_metrics`; total-flux apertures, never 3×3 boxes.
- **false flux:** |model| farther than two beams from every one of the 100 sources, divided by the in-image true flux.
- **E1 (thesis eq. 6.9):** ‖(m − truth) ⊛ b‖₁, divided by the in-image true flux (also reported raw).
- **E2 (eq. 6.10):** rms of the exact residual.
- **inversions:**
  - for WSClean, its reported major iterations: run A reports 2, the dirty image plus one residual;
  - for a network with p passes, p + 1 (the dirty image, then one exact residual per pass).
- **minor-cycle wall:**
  - WSClean's deconvolution time;
  - the network's inference time summed over passes, as PyTorch on CPU with one thread on nash, the same shared conditions as WSClean `-j 1`;
  - also as rang's ONNX interpreter if B's runtime is available by then.
  - Reported, provisional (nash shared).

**NP's stop rule** (frozen): after pass p, stop if the model changed by less than 1 % (‖m_p − m_{p−1}‖₁ < 0.01 ‖m_p‖₁), or at p = 6. It is applied with the exact cycle.

**Tolerance** (paired per field, against W1, per training seed):

- median(recovery_NP − recovery_W1) ≥ −0.02;
- median(false_NP − false_W1) ≤ +0.01.

**Decision on the test split**, each NP seed scored separately:

| Outcome | Rule |
| --- | --- |
| **G** (fewer inversions at equal quality) | all three seeds inside the tolerance **and** median inversions of NP ≤ median inversions of W\* − 1 |
| **N** (null) | all three seeds inside the tolerance, inversion saving below one |
| **N-s** (seed-dependent) | one or two seeds inside the tolerance |
| **F** (fail) | no seed inside the tolerance |

- Outcome G is labelled "fewer inversions at equal quality on 256² simulated 16-dish point fields". It is not a cost claim at E2 scale and not novelty.
- The minor-cycle wall decides no outcome. Its expected result, NP slower than W1 on the CPU, is stated here.

**Anchor (a)**, test split, N1 against W-A, paired median E1 difference per seed. The outcome is only one of two labels:

- **consistent** with the thesis: WSClean better on all three seeds;
- **not reproduced**: otherwise.

**Also reported, deciding nothing:**
- NP against N1 (E1, recovery, false flux), and NP's measures per pass;
- the truth arm and the empty arm;
- the per-flux-set split (10, 100, 1000);
- the image-domain against exact operator gap at NP's passes.

## 6. Stages and stop rules

1. Freeze this note (this commit). Push. Send the op list to the coordinator; it was sent before the freeze.
2. nash: grid PSFs (section 2.1), then the operator tolerance (2.2). Stop if it fails.
3. glacier: the resume test (section 3). Fix before any budgeted run.
4. glacier: N1 seeds 1-3, then NP seeds 1-3, under the GPU budget and yield times.
5. nash, alongside: the comparator ladder on validation and test (section 4). Choose W\* from validation and record it before reading test scores.
6. nash: exact-cycle scoring of N1 and NP's chosen checkpoints on validation; record it. Then the test split, once.
7. Measured result, compact archive `research/results/dl4b-step0/`, a timing row per tool run, hand-back.

Every nash job runs under `~/Github/rang/tools/heavy_lock.py run --slots N --mem G` at `nice -n 19 ionice -c3`. Every glacier GPU job runs through `~/.gpu/gpu_run.py run --owner rang`. No job loses more than 15 minutes.

## Amendment 1 (2026-11-20, before any training; not post hoc)

The coordinator, 2026-11-20, after the op list and the two pre-freeze findings were sent: because step 0 cannot decide cost, keep it small.

- **Step 0 is capped at about 6 GPU hours with three seeds**, out of #42's 24. This replaces section 3's budget of 18 h:
  - N1: 20 min per seed (1 h);
  - NP: 90 min per seed (4.5 h);
  - 0.5 h reserve for the resume test and validation passes.
  - The cosine schedule length (`--steps-total`) is set per arm from the step rate measured in the resume test, so that the schedule ends at the cap. It is recorded with the run.
- Nothing else changes: measures, tolerance and decision rule stand, and the outcome is recorded even if null.
- The GPU hours not spent here (about 18) stay with #42. Step 1, at E2 scale where a cost claim is decidable, is drafted as a separate proposal ([dl4b-step1.md](dl4b-step1.md), not frozen), so the owner can decide.

## Amendment 2 (2026-11-20 08:55, before any budgeted training; not post hoc)

The coordinator asked for the GPU to be filled and N1 to start before the grid PSFs finish.

1. **Batch size.** Measured on glacier (N1, 40 steps):
   - batch 32: 0.20 s per step, peak 5.7 GiB;
   - batch 64: 0.43 s per step, 8.7 GiB.
   - The card is compute-bound from batch 32, at about 150 fields per second.
   - **N1 trains at batch 32** (section 3 said 16). Learning rate and schedule shape are unchanged.
   - NP's batch is set the same way (the largest of 16 and 32 that fits) when the grid PSFs land, and is recorded with the run.
2. **N1 steps.** `--steps-total 5500`, about 19 min of training at 0.20 s per step, inside amendment 1's 20 min per seed. Validation time is not counted against the cap.
3. **Packs.** The packs no longer carry G. The trainer reads G per seed from the psfg shards (`--psfg`), so N1 does not wait for them.
   - The pack build on nash (260 s, one core, I/O-light) ran outside the heavy lock: an error, recorded here.
   - Packs: 300 files, 2.2 GB, on glacier `D:/rang/dl4b-step0/packs`; removed after training.
4. **Load-time memory.** The load-time s₀ computation is chunked; computing it in one pass had peaked at 21 GiB through shared memory.
5. **Yield windows** (SAST), passed to the trainer: 20:50-23:59 and 06:00-06:50, on top of `gpu_run.py check`.

## Amendment 3 (2026-11-20 09:30, post hoc: after N1 seed 1 failed; before any usable model or any exact-cycle score)

**What failed.** N1 seed 1 (08:56 start) reached step 4,524 (900 s) with validation recovery 0, false flux 0, an empty model. Its loss had sat at the empty-model value (2,031) from the start, and so had the batch probe and the resume test. It was stopped by hand at 09:13.

Diagnosis (scripts `results/dl4b-step0/scripts/diag*.py`, glacier):
- torch's default Conv init gives a signal gain of 5e-6 through the 11 bias-free layers;
- the trained checkpoint's raw outputs were all negative, so the positivity clip passed no gradient;
- with He init alone, the output started 300 × above the empty model and Adam collapsed it back;
- with He init and a zero output layer, the L1 loss still could not fit one batch in 600 steps. Its constant-size gradient over about 65,000 empty pixels outweighs about 260 source pixels until the features are selective;
- a squared loss fits the same batch: the L1 ratio falls to 0.27-0.34 in 600 steps at learning rate 1e-3, with positive pixels falling to a few hundred.

**Changes to section 3**, for every arm and seed from here on:

1. **Init:** He-normal on the hidden 3×3 layers, zeros on the 1×1 output layer.
2. **Loss:** the squared error of the beam-convolved **unclipped** update, Σ((b ⊛ (m + s·f) − b ⊛ truth)/s₀)², per field, mean over the batch, mean over passes. The positivity clip stays for the state passed to the next pass and for every scored model, so section 5 is unchanged.
3. **Learning rate** 1e-3 (was 3e-4), chosen on one training batch.
4. **Gates in the loop:**
   - validation at step 500;
   - exit 4 if the loss over the empty-model loss is above 0.9 at step 1,000.
5. **Smoke result** (seed 99, full packs, 1,000 steps): validation at step 500 gave recovery 1.07, false flux 0.13, median 8,100 positive pixels; loss ratio 0.06 at step 1,000.

**GPU time spent outside the seeds:**
- about 0.45 h: the resume tests, the batch probes, the failed seed (15 min) and the diagnostics.
- The 6 h cap of amendment 1 stands. Remaining: N1 3 × 20 min, NP 3 × **80 min** (was 90), 0.25 h reserve.

The failed run is kept as `D:/rang/dl4b-step0/runs/N1-seed1-failed-clip`. Seed 1 is rerun from scratch under this amendment.

## Amendment 4 (2026-11-20 10:50, post hoc: after N1's image-domain validation scores were seen; before any exact-cycle score, any NP training and any test read)

N1's validation shows recovery above 1:

| Seed | Recovery | False flux | Median pixels > 0 |
| --- | ---: | ---: | ---: |
| 1 | 1.20 | 0.098 | 2,488 |
| 2 | 1.05 | 0.112 | 3,995 |
| 3 | 1.08 | 0.091 | 1,133 |

Two frozen rules reward over-recovery:

- the checkpoint score `recovery − false` (section 3), where seed 1's 20 % overshoot scores best;
- the one-sided recovery tolerance of section 5, `median(rec_NP − rec_W1) ≥ −0.02`, which a model that puts excess flux near sources passes.

Both become two-sided:

1. **Checkpoint score:** −|recovery − 1| − false. For N1, the checkpoint is chosen between `best.pt` and the final weights by this score from each run's recorded history. Both are kept.
2. **Recovery tolerance:** median over fields of (|rec_NP − 1| − |rec_W1 − 1|) ≤ +0.02. The false-flux tolerance is unchanged, and the anchor's E1 comparison is unchanged.

Not changed: the measures, the cycle counting, the outcome table, the test-once rule.

**Also recorded here** (measured since amendment 3):
- **Operator tolerance (section 2.2):** median 6.1 % of the residual rms over the 90 validation seeds. **PASS** against 10 %.
- **G-convolution check:** torch's image-domain operator against numpy's, all 8 augmentation codes, worst 4.0e-7 of the peak; equivariance to 3e-16.
- **NP batch:** 16 (peak 10.96 GiB, 0.57 s per step). Batch 32 did not fit in 12 GB. `--steps-total 8000`, 80 min per seed.
- **Grid PSFs:** all 300 shards. Shards 1-199 came from nash (copied when nash's account was locked at about 10:00, checksums checked); shards 200-299 were built on glacier with `rang-wsclean-native:3.7` in docker; shard 0 from nash. Cross-host agreement 1.2e-7 on two seeds.
- **Regeneration check on glacier:** 8 of 1,000 seeds missed the 1e-4 dirty-match by up to 1.1e-4. That MS carried one data column against the generator's three; G does not depend on the data.
- **Comparators and scoring move to glacier**, so one host times both arms: the ladder runs on glacier's CPU in docker WSClean 3.7. On seed 5 its scores, cycles and iterations equal nash's.

## Measured result

- **N1 seed 1, under amendment 2's rules (failed):**
  - 4,524 steps, 900 s, validation recovery 0 and false flux 0 (an empty model);
  - stopped by hand at 09:13 (exit 143);
  - superseded by amendment 3.

### Outcome (test split, read once, 2026-11-21 02:05)

**Decision (b): F (fail). No NP seed is inside the tolerance.**

- Every seed misses on false flux. The median false flux minus W1's is +0.122, +0.080 and +0.071 (seeds 1-3), against the +0.01 allowed. Every WSClean arm has a median false flux of 0.
- The two-sided recovery clause passes for all three seeds (median |rec − 1| − |rec_W1 − 1| = −0.05, −0.13, −0.07). This is because WSClean under-recovers: W1's median recovery is 0.83.
- Inversions: NP median 7, 7, 4 (6, 6 and 3 passes) against W\* = W4's 3. The stop rule (model change < 1 %) rarely fired.

**Anchor (a): consistent with the thesis.** One-pass N1 is worse than WSClean run A on E1 for all three seeds: median paired difference +3.05, +1.48 and +1.44 (WSClean run A's median E1 is 5.08).

**Test split, 270 fields** (medians; E1 per in-image flux; exact cycle for every arm):

| Arm | Recovery | False flux | E1 | E2 (residual rms) | Inversions | Minor cycle or inference, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Z (empty) | 0 | 0 | 13.05 | 0.0824 | 1 | – |
| WA (`-mgain 1.0`) | 0.863 | 0 | 5.08 | 0.0660 | 2 | 0.013 |
| W1 (`-mgain 0.8`) | 0.832 | 0 | 4.99 | 0.0562 | 4 | 0.022 |
| W4 = W\* (`-mgain 0.9`) | 0.857 | 0 | 4.95 | 0.0561 | 3 | 0.019 |
| W5 (multiscale) | 0.909 | 0 | 4.65 | 0.0558 | 4 | 0.081 |
| W6 (multiscale 0,4, gain 0.2) | 0.904 | 0 | 4.72 | 0.0559 | 4 | 0.063 |
| T (truth) | 1 | 0 | 0 | 0.0578 | – | – |
| N1 seed 1 / 2 / 3 | 1.23 / 1.08 / 1.10 | 0.081 / 0.094 / 0.075 | 8.25 / 6.46 / 6.53 | 0.057-0.058 | 2 | 0.078 |
| NP seed 1 / 2 / 3 | 1.12 / 1.01 / 1.10 | 0.129 / 0.085 / 0.078 | 6.67 / 4.92 / 5.94 | 0.056-0.057 | 7 / 7 / 4 | 0.47 / 0.47 / 0.24 |

**Also reported, deciding nothing:**

1. **Iteration helps.** NP beats N1 on E1 for every seed. NP seed 2 is the only arm close to WSClean on E1 (4.92 against WA's 5.08 and W1's 4.99), with recovery 1.01 against WSClean's 0.83-0.91. Its false flux is still 0.085.
2. **Minor-cycle cost is null, as expected** (section 1): network inference is 0.078 s per pass (ONNX Runtime, one thread, glacier, shared host) against WSClean's 0.013-0.022 s of deconvolution per field. That is 4-25 × more, with or without iteration.
3. **Scale equivariance holds.** The bias-free network gives the same medians for flux sets 10, 100 and 1000 to 4 significant figures, for every seed (`summary-test.json` `per_flux`).
4. **Residuals are set by out-of-field sources.** E2 is the same for every arm with a model, the truth arm included (0.056-0.066), so it does not separate the arms.
5. **Where the false flux comes from (reading, not measured).** The networks' false flux lies beyond two beams of any of the 100 sources, so it is flux placed on sidelobe structure. In WSClean, auto-masking at 5 σ (σ dominated by those sidelobes) prevents this; nothing in the networks does. A threshold or mask on the proposal is the obvious next lever; it is not tried here.
6. **Validation gave the same picture** (`summary-validation.json`): N1 false flux 0.08-0.10, NP 0.08-0.13.

**Cost and provenance:**

- **GPU** (glacier, RTX 4070 Ti): about 4.9 h of the 6 h cap.
  - N1: 3 × about 19.5 min.
  - NP: 4,845 s, 2,980 s and 4,138 s (seed 3 in two segments around the owner's 16:00-24:00 window, resumed bit-identically from step 4,542).
  - Plus the failed N1 seed 1 (15 min), the probes, the resume tests and the diagnostics.
- **CPU** (glacier, WSL, docker `rang-wsclean-native:3.7`):
  - grid PSFs 200-299: 1 h 17 min at 11 slots (1-199 from nash);
  - ladder: 18 groups;
  - exact-cycle scoring: validation 14 + 31 + 11 min, test 45 min at 15 slots.
- **Choices**, all fixed before the test read (`results/dl4b-step0/choices.json`):
  - W\* = W4, from validation;
  - N1: the final weights; earlier validated steps had been overwritten (amendment 4);
  - NP: `best.pt` at steps 2,081, 5,418 and 2,676.
- **Weights:** `results/dl4b-step0/onnx/` holds six ONNX opset-17 files. Each has the ops Conv and Relu only and 92,768 weights, and matches PyTorch to at most 1.3e-7.
- **Archive:** `results/dl4b-step0/`. It holds:
  - `summary-{validation,test}.json`, `wstar-validation.json`, `operator-tolerance.json`, `choices.json`;
  - `per-field-scores.tar.gz` (every field, arm and pass);
  - the scripts.
- **Cross-host check:** glacier's ladder against nash's, 540 fields × 7 arms. Major and minor iteration counts are equal in all 3,780 runs; recovery differs by at most 8e-4.

**Not done:**
- No G-sub, G-drop or G-chan gates: one array on this dataset.
- No E2-scale cost; that is step 1 ([dl4b-step1.md](dl4b-step1.md)).
- No rang-interpreter timing; ONNX Runtime was used.
- No threshold or mask on the networks' proposals (item 5 above).

## For the coordinator

1. **Outcome F** under the frozen rule, amended four times (dated, labelled; amendments 3 and 4 post hoc, before any exact-cycle or test score). The failure is false flux. The iterated form helps quality (NP seed 2 matches WSClean on E1) but adds inversions, and minor-cycle cost is null on 256² fields, as written before the run.
2. **Data finding, for #42 and anyone using ASTRODECONV2019:** the stored 512² PSF is not the 256² images' operator (section 0). The thesis's "residual = dirty − PSF ⊛ model" fails by 28 % of the residual rms. Any reuse must go through the exact cycle or the grid PSFs (`D:/rang/dl4b-step0/psfg`, 300 shards; not archived, regenerable with `dl4b_step0.py psfg`).
3. **Infrastructure that step 1 reuses:**
   - the bias-free CAN trainer with bit-identical resume and yield windows;
   - exact-cycle scoring with WSClean in docker;
   - the docker WSClean 3.7 on glacier, matching nash's native 3.7 in 3,780 of 3,780 runs.
4. **Host notes:**
   - heavy_lock sees ~0 cores for WSL jobs (it measures `wsl.exe`).
   - Git Bash rewrites `/mnt/...` in arguments: use `MSYS2_ARG_CONV_EXCL="*"`.
   - Git Bash's `date -u` is off by 2 h on glacier.
5. **Clean-up:**
   - nash's step-0 run root is removed. `nash:~/rang-data/outputs/dl4b-astrodeconv-20261119/{pilot-a,pilot-b,smoke-s0.npz}` (about 150 MB) remain, removable on your word.
   - glacier's `D:/rang/dl4b-step0` (packs 2.2 GB, PSFs 3 GB, eval 0.26 GB, runs) stays while step 1 may reuse the trainer and checkpoints. Remove after step 1.
   - Nothing of step 0 runs on glacier or nash now.
