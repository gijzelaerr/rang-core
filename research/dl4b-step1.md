<!-- SPDX-License-Identifier: MIT -->
# DL4b (#42) step 1: learned minor-cycle proposals at E2 scale (draft, not frozen)

**Status, 2026-11-20: a draft proposal for the owner's decision. Not frozen; nothing built or run.**

- Asked for by the coordinator on 2026-11-20, after step 0 was capped at 6 GPU hours ([dl4b-step0.md](dl4b-step0.md), amendment 1).
- It becomes a frozen note, with seeds, tolerances and run paths, only if the owner says go.
- Grounds:
  - [dl0-profile.md](dl0-profile.md) 2 and 4: the minor cycle and its resyncs are 63 % of E2-A's selfcal and 65 % of E2-N's;
  - [rml-gap.md](rml-gap.md) (#24 step 1): the truth skies and the comparison harness;
  - [dl-plan.md](dl-plan.md), stage 7, mode P.

## 1. Why step 1 exists

Step 0 cannot decide cost: on 256² point fields the minor cycle is about 1 % of a field's wall (dl4b-step0 section 0.6). At E2 scale the opposite holds. GeMClean's 4096² images, 8 joined output channels, 10 multiscale scales and an auto-mask spend:

| Part of selfcal | E2-A | E2-N |
| --- | ---: | ---: |
| minor cycle | 43 % | 46 % |
| resyncs | 20 % | 19 % |
| major cycles | 1.6 % | 2.3 % |

There are 390,000-950,000 components per image. A network that proposes most of the model in a few passes, with the exact major cycle between, could remove most of that work. That gain is decidable at this scale and not at step 0's.

## 2. Hypothesis (to be frozen)

On held-out simulated MeerKAT truth skies at E2 scale, mode P (a network proposes model increments, GeMClean's exact major cycle computes the residual, GeMClean finishes from the proposal to its usual stop) does two things:

- it reaches the quality of GeMClean's default (issue #28's metric: false flux and flux scale against truth, within the tolerances of [rml-gap.md](rml-gap.md) section 4);
- it does so at **≤ 0.5 × the minor-cycle plus resync wall of the best classical setting**, timed exclusively. The classical settings are:
  - GeMClean default multiscale;
  - cheaper multiscale (fewer scales, larger gain);
  - WSClean 3.7 multiscale at matched settings.

**Not claimed:** real-data quality. The real scans below check robustness only, since a student of a teacher cannot beat the teacher (dl-plan section 3).

## 3. Data needed

| Item | What | Source | Cost (estimate, not measured) |
| --- | --- | --- | --- |
| Truth skies, training | about 200 skies of the rml-gap recipes (points 0.05 mJy-2 Jy, Gaussians, curved tails, an ESO 137-006-like galaxy), fresh seeds | `examples/gemclean_bench_simulate.py` recipes; skies only, no visibilities | minutes on nash |
| PSFs (2N, exact) | one 8192² PSF per uv coverage. Coverages: full array at 4-6 declinations and 2-8 h tracks, plus sub-arrays for G-sub (core-only 16, random 40) | the core gridder on simulated uvw (no sky); built **through the operator**, as step 0 learned (section 0) | about 30 coverages × about 10 min on nash |
| Training pairs | dirty = PSF ⊛ truth + a noise image (image-domain synthesis), with an exact-cycle spot check per coverage | GPU, in training | none extra |
| Held-out truth skies, gated | rml-gap's H4, M1, N1, N2 (extended) at 4096², plus four new skies N3-N6 drawn after the freeze | core simulation with visibilities (2 h, 8 ch, as rml-gap); at E2's 512 channels if the owner wants the full shape (about 100 GB each) | 8-ch form about 1 h per sky on nash; 512-ch form about a day each |
| Real scans (robustness, not gated) | the 6 stage-7 held-out scans registered by C ([dl2-data.md](https://github.com/gijzelaerr/rang-core/blob/dl2-data/research/dl2-data.md) section 12); GeMClean default images of each as the teacher's reference | C's stage-7 teacher runner (not built yet: dl2-data defers stage 7 to #42) | about 3-4 h per scan per image on nash (E2-N image rate) |

## 4. What must be built

1. **A GeMClean warm start:** start the minor cycle from a given model, run the exact major cycle first, then continue to the usual stop. Without it mode P cannot be scored inside GeMClean. This is a Rust change in `core/src/gemclean.rs`, behind a flag; the default path stays byte-identical.
2. **The network inside GeMClean** through `learned_interp.rs` (B, Conv and Relu, already enough for step 0's bias-free CAN). Per pass, per joined channel, at 4096². CAN inference at 32 channels is about 3.1 TFLOP per channel image per pass (about 92,000 MAC per pixel × 16.8 M px). At an assumed 200-300 GFLOP/s on 16 CPU threads that is roughly 10-15 s, so 8 channels × 6 passes ≈ 10-15 min (estimate). Against about 3,500 s of minor cycle and resync per E2-A image, a 0.5 × rule is reachable only if the proposal leaves little for GeMClean to finish. The design question for the frozen note:
   - a per-channel network as in step 0; or
   - one network on the channel-joined image with the spectral fit left to GeMClean.
3. **Scale handling.** Training on 512² crops of the 8192² operator (shift-invariant PSF patch), inference fully convolutional at 4096². The receptive field must cover the PSF's main sidelobes, not its full extent. The far sidelobes are left to the exact cycle, which is mode P's point.

## 5. GPU hours and hosts

- **Training:** #42 keeps about 18 GPU hours after step 0's cap of 6. Proposed:
  - 3 seeds × 5 h for the chosen architecture;
  - 3 h for one ablation (with and without sub-array augmentation, scored on G-sub).
  - Total 18 h on glacier's RTX 4070 Ti through `gpu_run.py --owner rang`, inside the yield windows.
- **CPU:**
  - simulation, comparators and scoring on nash, shared;
  - **exclusive timing** of the gated runs on glacier after 21:00 (the owner's timing window), about 2-3 nights: 8 skies × (2 network arms + 3 classical) at about 1-2 h per 4096² run.
- **Data on glacier:** PSF patches and truth skies only (a few GB), copied to D: and removed after.

## 6. Decision rule (to be frozen; the shape only)

| Outcome | Rule |
| --- | --- |
| G | on ≥ 3 of 4 gated skies: quality within tolerance of the GeMClean default, and minor-cycle + resync wall ≤ 0.5 × the best classical setting, all three seeds |
| N | quality within tolerance, wall above 0.5 × |
| F | quality outside tolerance on ≥ 2 gated skies |

Reported, not gating: real-scan robustness against GeMClean's own image; G-sub; total stage wall including the network.

## 7. Owner decisions

1. Go or no-go for step 1 (needs about 18 GPU hours, about 2-3 nights of exclusive glacier timing, and nash simulation slots).
2. Gated skies at 8 channels (rml-gap's form, fast) or at E2's 512 channels (the true shape, about 100 GB each).
3. Whether the GeMClean warm start (section 4.1) may land in the core, behind a flag, before the measurement.
4. Whether C's stage-7 teacher runner is built for the robustness check, or the 6 real scans wait for a later step.
