# Deep learning in every stage: discovery plan for v0.4.0

Status, 2026-11-19: **direction set by the owner; the plan is proposed; nothing built, trained or
measured.** Owner, 2026-11-19, verbatim: "For the next release I want to make some progress on the
collaboration with landman. Actually, I want 0.4.0 to be focussed on deep learning. I want every step
in our imaging and calibration process to be able to be replaced with a neural network that is
trained with real tools and real images. We want to investigate where a neural network can be useful
for a fast approximation and/or computational speedup. We can experiment with every step individually
or combined. [...] The end result should be a plan or framework where we can easily interchange parts
of rang with deep learning and/or retrain specific aspects for a specific telescope. Note that every
observation could be different, since different dishes can be added or be flagged for maintenance."

So v0.4.0's theme is deep learning; `roadmap.md` and the milestones follow decision 1 of section 10
(taken 2026-11-19). v0.3.0 was released the same day; F5 moved from the v0.3.1
carry-overs to v0.4.0 (decision 2).

Architecture names and papers in sections 6 and 7 are **candidates from memory and from the two
digests, not verified claims**; task DL0 verifies them before any proposal is frozen.

## 0. Order (owner, 2026-11-19, second message)

"don't forget about landmans work, let's make that the first experiment that yields some success, but
make an overarching plan where we can expand our machine learning approach to every aspect of the
framework".

So the sequence is fixed in two tracks:

- **Track L, first result: Landman's flagger (F5, task DL3).** It runs ahead of everything else and
  does not wait for the framework. Success is his own definition (2026-11-06): one weights file for
  MeerKAT L-band, faster than the Tricolour port, fewer tunable parameters, comparable flags;
  calibrators first, targets as a second model. What is done to make a success likely, each from a
  recorded failure:
  - scope: the calibrator model alone can ship; targets cannot hold it back (F3, F4: targets stopped
    at the label audit);
  - F4's network already reached recall 0.954 at T's flag count on validation, and its held-out sets
    are unread; F5 adds the antenna terms from his review for the one morphology F3 missed;
  - his classical per-antenna OR fallback is pre-registered, so a missed morphology is covered by a
    rule, not by another protocol;
  - the cost gate has frozen headroom and one exclusive timing hold on glacier after 21:00 (F4
    stopped at 0.441-0.459 against 0.45 on a busy host);
  - labels by his scheme, `pfb hci` with his settings, gain TV as a reported validation measure.
  A failed gate is still recorded as failed; nothing here moves a bar after the fact.
- **Track F, the framework (DL0, DL1, DL2), in parallel and agent-heavy.** F5 is written against
  section 4's contract as soon as DL1 exists and becomes its first tenant; if DL1 is late, F5 ships
  as F2-F4 did (`f5flag.rs`) and is moved under the contract afterwards, bit-identical.

The other stages (sections 3 and 8) follow only after track L has reported.

## 1. What is already measured

Wall time per stage, `rang-core run`, from `tool-timings.md`:

| Stage | E2-A (61 ant, 4,096 ch, exclusive) | E2-N (62 ant, 1,024 ch, nash shared) |
| --- | --- | --- |
| flag | 2,738 s, 7 % | 1,984 s, 3 % |
| calibrate | 4,390 s, 12 % | 4,819 s, 7 % |
| apply | 578 s, 2 % | 1,319 s, 2 % |
| image | 5,280 s, 14 % | 11,985 s, 17 % |
| selfcal | 24,270 s, 65 % | 49,304 s, 71 % |
| total | 37,272 s | 69,527 s |

Inside selfcal on the ESO137 pilot the split is not settled: floor-5 G1 (one Sp round, 2,776 s) has
the solve at 1,695 s (61 %) and two GeMClean images at 782 s (28 %); the selfcal-memory default run
(Sp then Sa, 2,207 s) has the solves at 343 + 575 s (42 %). Both on shared nash. DL0 measures the
split (solver iterations, I/O, imaging, major cycles) on E2-A and E2-N before the DL4 pilots are
ordered.

Consequences:

- A flagger at zero cost saves at most 3-7 %. F2-F4 went there because of Landman's request, not
  because of cost. Selfcal (solve plus repeated imaging) holds 65-71 %.
- The major cycle is exact gridding; the GPU did not make it faster ([gpu-grid.md](gpu-grid.md)).
  A network pays in imaging only by **reducing the number of major cycles or solver iterations**,
  not by replacing the gridder.

The record of learned or regularised methods here:

| Attempt | Outcome |
| --- | --- |
| F1, flagger trained on gain TV | NO-GO, nothing trained |
| F2, per-baseline CNN (6 planes, 5 dilated layers, 8 hidden) | 0.2 × Tricolour's wall; fails held-out morphologies and real LUNO |
| F3, 15 planes | 0.34 × wall; misses wide-band scan-long antenna-local RFI (0.024 against 0.907) |
| F4, 23 planes | trained (recall 0.954 on validation); stopped on a noisy cost gate (0.441-0.459 against 0.45); held-out unread |
| F5 | drafted from Landman's review, not frozen |
| pfb `sara`, DF5-O | not converged in 10 major cycles |
| rang's signed-ℓ1 solver | 3 × less false flux than GeMClean at 11-21 × the instructions |

Lessons that this plan builds in: features and network that miss a morphology by construction (F3);
labels from disagreeing tools (targets); a timing gate without headroom on a shared host (F4).

### 1.1 The owner's earlier attempt: Vacuum Cleaner (thesis, chapter 6, 2021)

Read 2026-11-19 from <https://pythonic.nl/thesis.pdf> (pages 85-97); a reading, nothing rerun. A
pix2pix conditional GAN (U-Net generator, PatchGAN discriminator, TensorFlow) maps a 256² dirty image
to the sky model in one pass, trained on ASTRODECONV2019 (10,000 simulated point-source fields,
MeerKAT AR1, 16 dishes, declination −55° to −65°). Result as stated there: close to WSClean limited
to one major cycle; the PSF as a second input channel and a PSF-convolution term in the loss gave no
improvement. It is deconvolution (stages 7 and 10 here), not calibration.

| What the chapter did | Why it limits the result (reading) | What this plan does instead |
| --- | --- | --- |
| One pass, dirty image to model; the data are never consulted again | Nothing corrects the output against the visibilities, so the best case is one image-domain pass: "one clean cycle" is the expected ceiling, not a training problem | Mode P: the network proposes, the exact major cycle computes the residual, the network runs again on the residual (stage 7) |
| PSF concatenated as an image channel | A convolutional layer combines values at the same pixel; the PSF acts as a kernel, not as a co-registered image, so the channel carries almost no usable signal. And with one 16-dish layout and 10° of declination the PSF hardly varied, so there was nothing to gain from it | The PSF enters through the exact operator (residual update); PSF variation is forced in training (sub-arrays, hour angle, declination) and tested (G-sub, G-drop) |
| Data term `‖PSF ∗ Î − I_D‖` in the training loss, weight 0.001 | With the truth already supervised the term adds no information on the training set; data consistency matters at inference, where it was not applied | Data consistency in the forward pass of every iteration, not in the loss |
| Adversarial loss, chosen because L1 gives blurry natural images | It rewards output that looks like the training set, not correct fluxes; it adds instability (the drop at 80,000 steps) and can invent sources | Regression on truth at beam resolution plus flux and false-source terms; samples only if uncertainty is the goal |
| Dirty image scaled linearly to (−1, 1), delta-function targets on the pixel grid | Sources at 10⁻³ of the peak fall below the network's precision; a one-pixel miss of a delta costs twice | Iterating on residuals renormalises each pass (the dynamic range comes from the loop); targets and losses at beam resolution |
| WSClean limited to one major cycle "for fairness"; scores are a beam-convolved L1 and the residual RMS | The comparator is a handicapped CLEAN; residual RMS does not penalise false flux; no flux scale, completeness or false-source count | The existing gates: false flux, flux scale, cycles to a stop, against unrestricted WSClean at matched cost |
| Speed: 0.2 s per 256² image on a GPU | The cost of imaging is gridding (the major cycles), which the network still needs; a 256² Högbom loop is also fast | Gain counted in major cycles and wall time of the whole stage, timed exclusively |
| One array, point sources only, no gain errors, no real data | No evidence about a changing array or real fields | Section 6's gates; real data through teachers (section 5) |

What the chapter had right and this plan keeps: conditioning on the PSF because the uv coverage
changes per observation; physics in the objective; simulated truth because labels from a
deconvolution algorithm are biased by it; a public dataset; a recurrent, iterated network as the next
step (its section 6.7); and quick-look source finding as the use for a one-pass network (stage 10).
ASTRODECONV2019, if still downloadable, is a ready first benchmark for stage 7: reproduce the
chapter's one-pass score, then measure the iterated form on the same fields (DL4b, step 0).

## 2. Three ways a network enters a stage

| Mode | What the network outputs | Who decides the result | Gate |
| --- | --- | --- | --- |
| **P, propose** (default) | a warm start, a component list, a mask, a flag candidate set | the exact classical step, run from the proposal to its usual stop | result within the stage's existing oracle tolerance; cost lower by a frozen factor |
| **S, settings** | the stage's tunable parameters (solution interval, thresholds, scales, stop level) | the classical step with those settings | quality within tolerance of the hand-tuned settings on held-out observations; fewer user parameters |
| **R, replace** | the stage's output | the network | a frozen approximation class, looser than the oracle tolerance and written before training; the product is labelled approximate in its receipt |

P keeps every existing parity gate meaningful and bounds the damage of a bad network to lost time. R
is the "fast approximation" of the request (quick-look images, first-pass flags) and never feeds a
science-grade product silently. S is Landman's "fewer tunable parameters" generalised.

## 3. Stage table

Teacher: the tool whose output is the training target on real data. Truth: simulation with known
answer. A student distilled from a teacher cannot be shown better than the teacher; only truth
simulations and downstream gates (image RMS, gain error) can show that.

| # | Stage | Cost share | Candidate | Mode | Teacher / truth | Go/no-go rule to freeze | Prior |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Flag | 3-7 % | F5: per-baseline network plus antenna terms | R (flags are the product), with Tricolour OR as fallback | Tricolour port, CARACal strategy, `pfb hci`, injections | F5's own, plus the sub-array gate of section 6 | F1-F4 above |
| 2 | K, G, B solve | 7-12 % | gains predicted from data/model ratio as the solver's start | P | rang/QuartiCal solutions; A1 truth | same solution within the C2 tolerances; wall ≤ 0.7 × the **best classical start** (identity, the previous interval's solution, the previous round's, the FFT start for K), all arms in the same run | solves take 13-37 iterations (selfcal-memory); `cal_selfcal.py` passes `initial_estimate=False`; classical warm starts unmeasured |
| 3 | Solution quality (minsnr, bad intervals, fillgaps) | < 1 % | a classifier of bad solutions; a smoother across gaps | P, S | CASA's and rang's solution flags; A1 truth | screening pilot only (one day): gain error against truth no worse, CASA's flags reproduced on held-out sets; continue only if a failure class is found that the rules miss | calchain-floor, e2a-3b-k: the misses were single bad solutions |
| 4 | Polarisation terms | < 1 % | as 2, for Gpol, KCROSS, Xf, Df | P | CASA, `poldx` truth | screening after 2: reuse 2's network class; no gain possible in wall time, so only a robustness result counts | Gpol intervals CASA drops at its iteration limit (xf-gap) |
| 5a | Predict, degrid (model to visibilities) | inside the major cycles | approximate predict | R only | the exact wgridder | screening pilot: error against the exact predict in a frozen class, for quick-look and for network training only; never in a gated product | gpu-grid: GPU not faster; accuracy gates 1e-4 to 1e-9 exclude modes P and S here |
| 5b | Apply | 2 % | none: an exact per-cell matrix product | – | – | hook present; no candidate known (DL0 checks once); skipping is owner decision 3 | – |
| 6 | Clean mask | inside 14-17 % | mask from residual and PSF | P | radler's auto-mask, truth skies | major cycles and false flux no worse than auto-mask on held-out skies | automask-cycle, sdm03: the auto-mask switch is a knife edge |
| 7 | Minor cycle | inside 14-17 % and inside selfcal | a network proposes model increments from residual and PSF; exact major cycle between (R2D2-like), or a learned denoiser as regulariser (AIRI-like) | P | GeMClean/WSClean deep models; truth skies S, H, M, X | fewer major cycles at equal false flux and flux scale (issue #28's metric), against WSClean at matched cost | #24 step 1 not run; stop28: 1 cycle saved classically |
| 8 | Selfcal loop | 65-71 % | 2 and 7 together; predicted final-round gains as the first round's start; skip rounds | P | the converged classical loop; simulated gains | held-out D of selfcal-defaults within 0.01 at ≤ 0.5 × the wall of the classical loop with its best classical starts (rule of row 2) | selfcal-defaults: 13 runs, D 0.87-0.92 |
| 9 | Stage settings | – | data statistics to solint, thresholds, mask levels | S | the grids already run (selfcal-defaults, stop28, sdm03) | section 2 | defaults rarely moved: three "default unchanged" outcomes |
| 10 | Quick-look image | new product | dirty image and PSF to restored image | R | GeMClean images | frozen class: flux of sources > 10σ within x %, false sources per field ≤ y; seconds on a CPU | POLISH and RI-GAN in the digest, simulations only |
| 11 | Image QA | new product | artefact and RFI-residual detector on images and waterfalls | scoring only | the frozen gates' pass/fail history, injections | agreement with the gates on held-out runs | Landman: an agent reviews waterfalls |
| 12 | Whole chain | 100 % | raw visibilities to image in one network; or 1 + 2 + 7 trained jointly through the exact operators | R (first form), P (second) | `rang-core run`'s products | not before two single stages pass: a joint form must beat the same stages trained apart; the one-network form is a quick-look arm of 10 | none |

Every stage, 5b included, gets the `learned` hook of section 4, so "can be replaced" holds for all of
them; the table says where a pilot is planned and what it must show. Provisional order of pilots by
possible gain: 8 (through 2 and 7), then 6, 10, 9, with 3, 4 and 5a as one-day screenings; DL0's
selfcal split fixes the order. Stage 1 runs first anyway: it is the live thread with Landman and the
first tenant of the framework.

## 4. The swap contract (the framework)

Every learned stage, existing or future, meets the same contract:

1. **Same interface as the classical stage.** Same inputs, outputs and chunk plan; selected per stage
   by configuration: `<stage>.learned: {mode: off | propose | settings | replace, weights: <name or path>}`,
   default `off`. With `off` the stage is bit-identical to today (gated).
2. **One weights file per stage, telescope and band** (Landman, 2026-11-06), separate files where the
   data class differs (calibrator, target). The header carries: stage, architecture id and
   hyperparameters, normalisation constants, training manifest hash, teacher versions, the scores at
   its gates, licence, and a **validity envelope** (antenna count range, baseline length range,
   channel width, dump time, band).
3. **Refusal outside the envelope**, in the style of W4: mode P falls back to the classical start and
   logs it; mode R refuses unless forced.
4. **Receipts** record the weights file's SHA-256, mode and envelope check. The stage hash includes
   them only when the mode is not `off`, so no existing stage hash changes (as with the `calwt` keys).
5. **Training in JAX, inference in Rust** (the `cnnflag.rs` / `f3net.py` pattern): a parity test per
   architecture, CPU the reference, GPU (wgpu, X2's context) within a written tolerance. No heavy
   runtime in the five wheels.
6. **A registry**, `rang.learned`: `Stage` (features, forward, loss, teacher runner, gates) so that
   "retrain stage X for telescope Y" is one command with a manifest, not a new research branch.
7. **A retrain procedure**: `docs/agents/retrain-a-stage.md` with a thin skill: build the manifest,
   run teachers, train three seeds, score the frozen gates, write the weights header and a report.

Inference runtime is the open engineering choice. Hand-written kernels are fine for a 5-layer CNN and
not for U-Nets or attention. Recommended: a small declarative op graph (convolution, linear,
normalisation, activation, set pooling, attention) that the JAX trainer and one Rust interpreter both
implement, with per-op parity tests; DL1 measures it against pure-Rust runtimes (candidates: tract,
burn, candle; licence and wheel size checked first) before choosing.

## 5. Training-data factory

- **Real data, labelled by the real tools.** Teachers run through the existing oracle containers:
  Tricolour, CARACal's strategies, `pfb hci` (Landman's settings), CASA, QuartiCal, WSClean, GeMClean.
  On hand: the fixture, LUNO, ESO137 (reserve scans 6 and 8 unread), E2-A, E2-N (89 GB), and F2's
  simulations (`D:\rang\outputs\f2-20261106-*` present on 2026-11-19; size and completeness not
  rechecked since D: filled on 2026-11-14). More capture blocks from the SARAO archive are needed for splits by observation
  (section 10, decision 6).
- **Simulated truth**, for what teachers cannot give: A1 (known K, B, G, KCROSS, Xf, Df), the S, H, M
  and X skies, RFI injections with F5's label scheme. Skies with realistic extended emission are a gap
  (DL0 lists public sources).
- **Manifests.** Every sample traces to a capture block or seed, a teacher version and a SHA-256.
  Splits are by observation, never by cell or baseline. Held-out sets are registered before training
  and read once.
- **Hosts.** Training on glacier's RTX 4070 Ti (12 GB) through `gpu-run`, exclusive runs from 21:00;
  CPU training on nash is proven (F4: 47 min per seed). Inference timings only in exclusive holds,
  with headroom frozen in the gate (the F4 lesson). Data on `D:\rang` and nash, each campaign with its
  own input copies.

## 6. A changing array: how the parameter space is tamed

Each observation differs in antenna set (any subset of 64, more with MeerKAT+), flags, uv coverage
(declination, hour angle, duration), channelisation (1k, 4k, 32k), dump time and RFI. That space
cannot be sampled densely (2^64 antenna subsets alone). It does not need to be: the physics has
symmetries, and the design rule is to **build each symmetry into the stage instead of learning it**.

1. **Never index antennas or baselines.** No input or weight has a fixed slot per antenna. A network
   with an input of shape (64, …) is rejected at review.
2. **Keep the array inside the exact operator.** The measurement equation, the gridder and the PSF
   already hold the full geometry of this observation. In stages 6-8 and 10 the network sees images:
   residual and PSF (or model and data ratio). A missing dish changes the PSF it is given, not the
   network. This is the structure of plug-and-play imaging and of mode P in general. Caveat:
   [literature-2024-2026.md](literature-2024-2026.md) 3.3 records that R2D2 needs training per
   telescope; DL0 checks whether its networks take the PSF as input and over which uv samplings it
   was trained. The rule removes the antenna index, not the dependence on the PSF distribution
   (gate G-sub).
3. **Share weights over what varies, pool with permutation-invariant operations.** Per-baseline
   networks (F2-F4 already run on any number of baselines) and per-antenna encoders, combined by
   mean, median or attention over the set. F3/F4's antenna medians and F5's robust factorisation
   `log|V_pq| ≈ γ_p + γ_q + s` are hand-made instances.
4. **For stages that need antenna structure (1, 2, 8): a graph.** Antennas are nodes, baselines are
   edges, a flagged baseline is a masked edge, a missing antenna is a missing node. Gain solutions are
   equivariant under antenna permutation; a message-passing or set-attention network is equivariant
   by construction. Cost is O(N_bl) per layer; attention over 64 antennas is 4,096 pairs.
5. **Condition, do not memorise.** Geometry enters as features: antenna position, baseline (u, v, w)
   in wavelengths, elevation, parallactic angle. Band, channel width and dump time enter as global
   conditioning. A per-antenna identity embedding (receiver quirks) is optional, dropped at random in
   training, with a shared "unknown" embedding so a new or swapped dish degrades to the shared model.
6. **Fully convolutional in time and frequency, in physical units.** Inputs normalised to noise units
   (as F2 does), positions in MHz and seconds, so one network serves 1k and 4k and any scan length.
7. **Train on the variation.** Random sub-arrays (4 to all), antenna and baseline dropout, random
   flag masks, random time and channel crops, several declinations and hour-angle ranges.
8. **Test what the architecture does not guarantee.** Permutation and count are guaranteed by 1-4;
   the distribution of PSFs and of RFI is not. Gates frozen before training, for every stage:
   - **G-sub:** a held-out sub-array size and layout (for example core-only 16 and a random 40 when
     training used 48-64 full-array draws); score within a frozen factor of the full-array score.
   - **G-drop:** remove 1, 4 and 8 antennas from a held-out observation at inference only; the output
     on the remaining baselines changes by less than a frozen bound.
   - **G-perm:** antenna order shuffled; output equal to float rounding.
   - **G-chan:** a held-out channelisation.
   - **G-obs:** observations (capture blocks) never seen, other dates and fields.
9. **Mode P bounds the rest.** Outside the envelope the exact step still converges; the cost of a
   poor proposal is time, and the receipt shows it.

Per telescope: the architecture and the contract are shared; the weights file, the envelope and the
telescope features (dish or station type, band) are not. Retraining is section 4's procedure.
MeerKAT sub-arrays and its two channelisations stand in for "another instrument" until LOFAR data and
an oracle exist; nothing is generalised before that (AGENTS.md).

Candidate architecture families to verify in DL0 (from memory): Deep Sets and Set Transformer for
pooled sets; message-passing graph networks with edge features for antenna and baseline structure;
dilated CNNs and U-Nets for time-frequency planes and images; FiLM-style conditioning for global
parameters; unrolled and plug-and-play schemes (R2D2, AIRI, HyperAIRI) for stage 7; POLISH and RI-GAN
for stage 10. Transformers over all visibilities are out by cost (10^9 cells per observation).

## 7. Finding architecture and parameters

One frozen search protocol for every stage, small enough to finish:

- A ladder of at most three families from section 6 and three sizes each; the baseline is the
  smallest network that meets the contract (F2's 5 layers, 8 hidden).
- The same data, loss and training budget for every arm (a cap in GPU hours, frozen); three seeds;
  selection on validation only.
- Reported per arm: the stage's quality score, **inference cost measured in Rust on the CPU**,
  weights count, the section 6 gates. The choice rule is frozen: the cheapest arm inside the quality
  tolerance, not the best score.
- Hyperparameters by random search with successive halving inside the budget; no architecture-search
  machinery.
- Ablations that decide the design questions: with and without antenna terms; with and without
  geometry conditioning; with and without sub-array augmentation (scored on G-sub and G-drop).

## 8. Tasks

Each task follows `docs/agents/propose-and-measure.md`: note frozen before code, oracle, tolerance,
held-out read once, nulls recorded. Sizes as in `roadmap.md`.

| ID | Task | Done when | Size | Heavy |
| --- | --- | --- | --- | --- |
| DL0 (#37) | Literature and cost profile | A note verifies or drops each candidate of sections 3 and 6 (released weights, licences, MeerKAT evidence), gives the selfcal split (solver iterations, I/O, imaging, major cycles) on E2-A and E2-N from receipts or one profiled run, and names the solver's present starting point; it fixes the DL4 order | S | light |
| DL4s (#44) | Screenings: stages 3, 4, 5a | one day each, outcome recorded | S | light |
| DL1 (#38) | Swap contract, weights format, `rang.learned`, runtime choice | F3's network runs through the contract bit-identical to `f3flag`; `off` bit-identical on the quick check; runtime comparison recorded | M | light |
| DL2 (#39) | Data factory | Manifests, teacher runners, sub-array and dropout augmentation; one manifest per stage 1, 2, 7 with registered held-out sets | M | host time |
| DL3 (#40) | **First, track L:** F5 flagger (section 0) | F5 frozen, trained, scored, with G-sub, G-drop, G-perm added before the freeze; calibrator weights shipped behind the option if its gates pass; result to Landman on issue #1 | M | yes |
| DL4a (#41) | Gain warm start (stage 2) | pilot outcome by the stage table's rule | M | yes |
| DL4b (#42) | Minor-cycle proposals (stage 7): step 0 on ASTRODECONV2019 (section 1.1), then #24's comparison | pilot outcome; WSClean and released R2D2/AIRI weights as comparators where they exist | M, then L | yes |
| DL4c (#43) | Mask (6), quick-look (10), settings (9) | one outcome each; started only on spare slots | S-M each | yes |
| DL5 (#45) | Combined selfcal (stage 8) | only if DL4a or DL4b passes; outcome by the stage table's rule | L | yes |
| DL6 (#46) | Retrain procedure | An agent retrains one passed stage for a held-out configuration (other channelisation or sub-array class) from the procedure alone and meets the gates | M | yes |

DL0, DL1 and DL2 are agent-heavy and can start now on branches. DL3 needs F5's freeze. DL4 pilots
queue on the heavy lock and the GPU.

**v0.4.0 done when:** the contract and the retrain procedure are on main with `off` bit-identical;
stages 1, 2 and 7 each have a recorded outcome (weights shipped behind the option, or null); every
shipped weights file passed G-sub, G-drop, G-perm and G-obs; DL6 has run.

## 9. What would count as a result

- Speed claims: against the classical rang stage **and** the state of the art (WSClean, QuartiCal,
  Tricolour) at matched accuracy, timed exclusively.
- Mode P wins only if the end result is inside the existing oracle tolerance; mode R only inside its
  class frozen before training.
- A network that matches its teacher is a reimplementation, not novelty (AGENTS.md). Novelty needs
  truth simulations or downstream gates showing equal quality at materially lower cost.
- Expected from the record: most pilots null. The contract, the data factory and the gates are the
  part of v0.4.0 that is certain to remain.

## 10. Owner decisions

1. **Where Scale goes. Decided 2026-11-19:** "Move #3, #4, #5 to v0.5.0, we just released 0.3.0. #4
   sounds potentially useful for 0.4.0 though, so include that there." #3 and #5 are on the v0.5.0
   milestone; #4 (the multi-node executor) stays in v0.4.0 and serves DL2's teacher runs; `roadmap.md`
   edited the same day.
2. **Issues. Decided 2026-11-19:** "F5 in v0.4.0, move #24 into 0.4.0. lets reevaluate if #6 sould
   become part of 0.4.0 later, first see how quick we can make progress. so that one is a maybe. make
   new issues for all these actions. make milestones, attaches iissues to milestones." Done the same
   day: issues #37-#46 (section 8) on the v0.4.0 milestone, with #1, #4 and #24; F5 is #40 and leaves
   the v0.3.1 carry-overs. v0.3.1 was cancelled the same day: its milestone is deleted and #7 and #34 are
   on v0.4.0. Joint gain-and-image solving (#6's
   arm 3; #6 and #21 are closed) is a maybe, re-evaluated at DL5 (#45).
3. **Modes. Decided 2026-11-19:** "agree with decision 3, but we can make all 3 modes optional right?"
   Yes: every mode is an option per stage, everything `off` unless switched on. Propose is the
   documented default when learning is on; replace only for products labelled approximate; stages 3, 4
   and 5a as one-day screenings (#44); apply gets the hook and no experiment. A mode is selectable only
   if the weights file records that it passed that mode's gates; otherwise refused, with a force flag
   for experiments.
4. **Training framework:** stay on JAX (approved 2026-11-02, existing code) or add PyTorch (released
   R2D2/AIRI weights are likely PyTorch; DL0 confirms). Recommended: JAX for rang's own stages,
   PyTorch only inside an oracle container for comparators.
5. **Inference runtime:** own op graph and Rust interpreter, or a Rust runtime crate. Recommended:
   decide from DL1's measurement.
6. **Data:** how many more SARAO capture blocks to fetch for splits by observation (recommended: at
   least 8 L-band blocks on different dates with different antenna sets, chosen by a frozen rule from
   metadata only), and on which host.
7. **Compute cap** per pilot (recommended: 24 GPU hours on glacier after 21:00, 3 seeds, before a
   go/no-go).
8. **Landman:** post the summary below on issue #1, and ask whether he wants a stage beyond flagging
   (his `pfb` imaging, or the gain solve) as a shared pilot.

Draft for issue #1 (not posted; the owner sees it first):

> v0.4.0 of rang-core is planned around learned stages
> ([dl-plan.md](https://github.com/gijzelaerr/rang-core/blob/main/research/dl-plan.md)). Flagging is
> 3-7 % of our wall time, selfcal 65-71 %, so beside F5 we will test networks as warm starts for the
> gain solve and as component proposals between exact major cycles, each verified by the classical
> step. No antenna-indexed inputs; sub-array, antenna-dropout and permutation gates frozen before
> training. One weights file per telescope and band, as you asked. Two questions: (1) would you take
> part in the minor-cycle pilot with `pfb` as a comparator or teacher; (2) any architecture you would
> rule in or out for variable antenna sets?

## For the coordinator

- Proposed only. `roadmap.md`, the milestones and issue #1 are untouched until decisions 1, 2 and 8.
- DL0-DL2 need no heavy slots; briefs can be cut from section 8 once decision 1 is taken.
- F5 ([f5-flagger.md](f5-flagger.md), branch `f5-draft`) should gain G-sub, G-drop and G-perm before
  its freeze, whatever the answer to decision 1.
