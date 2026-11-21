# Rang: a learned clean mask and learned stage settings, staged on their headroom (#43, DL4c)

Status at freeze, 2026-11-20: **proposed; nothing run.** Branch `dl4c-mask` from origin/main `0df6b5da`.
Route: [docs/agents/propose-and-measure.md](../docs/agents/propose-and-measure.md). Plan:
[dl-plan.md](dl-plan.md) stage table rows 6, 9 and 10; order and cost basis:
[dl0-profile.md](dl0-profile.md) section 4 (final form in commit `6dd70c86` of branch `dl0-profile`). Host:
**nash** for every CPU job (`nice -n 19 ionice -c3`, main checkout's `tools/heavy_lock.py run --slots N
--mem G`, booked per phase); glacier's GPU only if stage 6C trains (`gpu_run.py run --owner rang`, short
runs, yielding at 20:50 and 06:05). Run root: `nash:~/rang-data/outputs/dl4c-mask-20261120`. Archive:
`research/results/dl4c-mask/`. Results go under "Measured result"; nothing above it changes except by a
dated, labelled amendment.

## 1. Question and what decides it

Self-calibration at E2 settings is 63-65 % GeMClean minor cycle plus resyncs (dl0-profile 2.1, 2.2). Can a
predicted clean mask (stage 6, mode propose) or predicted stage settings (stage 9, mode settings) cut that
cost at equal image quality? A network can only be as good as the best mask or the best setting it could
predict, so each stage is **bounded first, without a network**; a network is trained only where the bound
leaves room.

Priors read before this freeze (receipts and code, no new run):

- The minor cycle's cost is counted by GeMClean's `convolutions` (full-image FFT convolutions on the
  `n × n` grid). Minor seconds per convolution: 0.091-0.094 on all four E2-A images (glacier), 0.29-0.33 on
  the three E2-N images (nash), while components range 390,000-952,000 at near-equal time. Read in
  `core/src/gemclean/multiscale.rs`: each sub-minor loop convolves the 8 channel maps at the selected scale
  and `find_maxima` the integrated map at every active scale; the mask only selects pixels inside those
  full-grid convolutions (`peak_masked`, `positions`). **So a mask cannot make a convolution cheaper; it
  can only end the minor cycle after fewer sub-minor loops.** Resync time is about 300 s (E2-A) and
  510-540 s (E2-N) per major cycle, the end-of-cycle FFT resync.
- The time is spread over every cycle: E2-A round 1, cycle 0 (before the automatic mask exists) 469 s of
  3,321 s minor; the cycles inside the mask hold the rest. E2-N: cycles 2-5 hold 85-90 % of the minor time.
- The automatic-mask switch is a knife edge (automask-cycle: GeMClean finished one major iteration earlier
  than WSClean on ESO137 scan 4, not on scan 14; sdm03: scan 4 worse, scan 14 better for every form).
  Decisions here are therefore taken on several cases with a rule for mixed results.
- C5b: an oracle mask from the true sky did not improve calibration quality over CARACal's automatic masks
  (quality, not cost, was measured).
- gemclean-ms-mask: under `-multiscale` flux outside a mask is expected (scale shapes centred inside it), so
  "flux outside the mask" is not a quality measure here; false flux is scored against truth.
- Literature (dl0-profile 1.3): no learned CLEAN mask was found.

**Hypotheses.**

- H6 (mask). On E2's imaging settings the best mask a predictor could supply, given from the first cycle,
  ends the minor cycle with at least 20 % fewer convolutions than GeMClean's automatic mask, at equal
  quality.
- H9 (settings). Across the observations in the grids already run, the best setting differs between
  observations by more than each grid's own decision margin, so a per-observation choice beats the best
  fixed setting.

**Not claimed.** No novelty, no speed claim from wall time on shared nash (wall is reported), no change to
any default. A passed bound is not a result for a network; it only licenses stage 6C.

## 2. Stage 6A: the mask bound on real data

**Data.** E2-N's target field ASKAPJ1745 (SARAO capture block 1735268787, SCI-20241101-KR-02), after the
DL0 profile's two self-calibration rounds: `CORRECTED_DATA` of
`nash:~/rang-data/outputs/dl0-profile-20261119/e2n.ms`, hard-linked into this task's run root (`cp -al`;
small files copied, never written through), so the owner's pending decision on that directory cannot
remove the input. Cases R1, R2, R3: the three target scans, **each imaged alone** (`-scans`), scan numbers
taken from the MS's metadata before any image. Real data has no truth.

**Imaging (frozen): E2-N's selfcal argv** as recorded in its final image report: `-size 4096 4096 -scale
3asec -weight briggs 0.5 -niter 1000000 -mgain 0.9 -auto-threshold 3.0 -wgridder-accuracy 0.0001
-average-channels 2 -channels-out 8 -join-channels -fit-spectral-pol 2 -multiscale -data-column
CORRECTED_DATA -field 3 -unit-weights -no-update-model-required`, plus per arm:

- **A** (baseline): `-auto-mask 5.0`, as recorded.
- **P** (posterior mask, the best a predictor could know): `-fits-mask` of the pixels where A's restored
  MFS image exceeds 5 × A's final residual MAD-σ, dilated by one restoring-beam FWHM, from the first cycle,
  no `-auto-mask`. The mask is built by a script committed after this note, from A's products only.

GeMClean from rang-core 0.3.0 (PyPI wheel, as DL0), the binary's SHA-256 recorded.

**Regime check.** Each A must show minor plus resync ≥ 50 % of its wall; otherwise the case is not in E2's
regime and is reported apart.

**Measures per case.** Cost: `convolutions` (primary), sub-minor loops, major cycles, minor and resync
seconds, wall (reported only). Quality (no truth): P's final residual MAD-σ within 1.02 × A's; P's MFS model
flux within 2 % of A's; P's restored image minus A's, over A's 5σ region, rms within 0.1 × A's residual σ.

## 3. Stage 6B: the mask bound on simulations with truth

**Data.** `examples/gemclean_bench_simulate.py`, recipe H4 (30 points, 6 Gaussians of FWHM 20-200″, a
25-Gaussian curved tail), at E2's image geometry: `--size 4096 --scale 3 --nchan 64 --fmin 0.856e9 --fmax
1.712e9 --hours 2 --dt 8 --nant 64 --noise-ujy 20`. Three cases registered here before they are drawn: T1
dec −45, T2 dec −30, T3 dec −60; sky seeds 20262001-3, noise seeds 20262011-3. Imaging as section 2 with
`-data-column DATA -field 0` and no `-average-channels` (64 channels into 8).

**Arms.** A as section 2; **T** (truth mask): `-fits-mask` of the pixels where the truth image convolved with
the restoring beam exceeds 5 × the image noise (the simulator's), dilated by one FWHM, from the first cycle.

**Measures.** Cost as section 2. Quality with `examples/gemclean_bench_compare.py score` against truth: false
|flux| of T at most 1.1 × A's; recovered flux within 0.5 % of A's; Q/Q_truth within 0.2 % of A's.

## 4. Stage 6 decision rule (frozen)

Saving per case: `h = 1 − conv(arm) / conv(A)` (P on R cases, T on T cases). A case **counts** only if the
arm meets every quality bound of its section.

1. **Null, nothing trains:** median h over the six cases below 0.20, or fewer than four of six cases count.
2. **Headroom:** median h ≥ 0.20 with at least two counting cases among R and two among T. Stage 6C may
   start.
3. **Mixed:** median h ≥ 0.20 but rule 2's spread fails (for example the saving appears only on
   simulations). Recorded; nothing trains until a decision by the coordinator.

Failed runs are rerun once; a second failure is recorded as a failed case (it does not count).

## 5. Stage 9: settings, re-read of the grids already run (no new runs)

A re-read of results already seen (labelled as such): selfcal-defaults (13 cells, the pilot and its
held-out copy), sdm03-default (forms on ESO137 scans 4 and 14), stop28-default and gemclean-stop28
(ε on S1-S3, H5-H24), automask-cycle (scans 4 and 14). Per grid with at least two observations: the best
fixed setting (by the grid's own score), a perfect per-observation chooser, and the grid's own decision
margin as frozen in its note.

- **No headroom:** the chooser beats the best fixed setting by less than the margin on every grid.
- **Headroom, untrainable now:** it beats it by more on some grid, but no grid has more than four
  observations; a settings network waits for #39's blocks (nine capture blocks), and the grid is named.
- Grids with one observation are listed and not scored.

## 6. Stage 6C: the network, only after rule 2 (frozen now, not started)

- **Task.** Mode propose: input the dirty MFS image and the PSF at the run's cell (normalised to the
  image's MAD-σ), output a per-pixel mask probability; thresholded at 0.5 and dilated as P/T, given to
  GeMClean as `-fits-mask`. The exact major cycle and GeMClean's stop rule are unchanged.
- **Training data.** Simulations only (truth labels = T's mask), from the bench simulator with recipes S2,
  H4, H7 and new seeds, random declination −80° to +10°, sub-arrays of 16-64 dishes drawn at random, 1k
  and 4k channelisations; seeds registered before drawing. Held out, read once: T1-T3 and R1-R3 (their
  bound numbers are known; the network is scored against the bound, not tuned on it).
- **Architecture and budget.** The smallest U-Net that meets the contract (dl-plan 6, 7): fully
  convolutional, no antenna index (G-perm holds by construction on images), PyTorch, three seeds, 24 GPU
  hours in all, checkpoints every 15 minutes, ONNX export.
- **Gates (frozen).** On the six held-out cases: convolutions at most `1 − 0.5 h` × A's (half the bound's
  saving), the quality bounds of sections 2 and 3, major cycles not more than A's. G-sub: T1's sky
  re-simulated with a 16-dish core sub-array, saving within 0.5 × the full array's. G-drop: R1 with 1, 4
  and 8 antennas flagged at inference, mask IoU with the full-array prediction ≥ 0.8. G-chan: T2 at 1k
  channels. G-obs: the R cases are a capture block the network never saw.
- **Outcome.** Gain (every gate), null (gates missed), failure (no run converges).

## 7. Stage 10, quick-look: optional, last

Not started unless stages 6 and 9 have their outcomes and slots are spare; a note amendment before any run.

## 8. Cost and bookings

Each GeMClean image is one shard (one process, not checkpointable: a stated exception to the 15-minute
rule; an interrupted image is rerun). Booking per phase: images `--slots 8 --mem 48` (the E2 images used
about 6 cores on average, peak RSS under 40 GB; checked on the first image and corrected by amendment if
off); simulation `--slots 4 --mem 16`; mask building and scoring `--slots 1 --mem 8`. At most 24 slots
held by this task at once, leaving room for session D's shards. Estimated: 12 images × 1-3.5 h.

## 9. Stages and stop rules

1. This note, committed and pushed. 2. Scan metadata of E2-N's target; hard links; simulations T1-T3
   (`sha256` of each MS listing). 3. A on six cases. 4. Masks P and T built and committed (scripts and
   mask hashes) before any P or T image. 5. P and T images. 6. Scores; rule of section 4. 7. Stage 9 re-read,
   any time. 8. Stage 6C only under rule 2.

## Amendments

**Amendment 1, 2026-11-20 09:30 SAST (bookings; before any A image finished, no result seen).** The
coordinator's booking audit: R1-A and R2-A held 8 slots each at `-j 8` and used 2.2 and 4.8 cores
while nash was at 44 of 44 slots with critical work queued. Every later image runs at `-j 4`,
`RAYON_NUM_THREADS=4`, booked `--slots 4 --mem 40`; simulations used one core (100 % CPU, 6 min, 1.2
GB) and are booked `--slots 1 --mem 4`; the scorer's prepare `--slots 4 --mem 32`. At most two of this
task's jobs run or wait for the lock at once (a file-locked gate in `dl4c.sh`). The primary cost
measure (`convolutions`, sub-minor loops, major cycles) does not depend on the thread count (GeMClean
is identical across thread counts, [x1-crossplatform.md](x1-crossplatform.md)); minor and resync
seconds of R1-A and R2-A (8 threads) are not comparable with the other images (4 threads) and are
reported apart. The first prepare attempt failed on the driver's own directory (the scorer refuses an
existing output directory); it writes to `prep/<case>/out` now.

**Amendment 2, 2026-11-20 14:25 SAST (imaging settings; after R1-A and R2-A finished, their convolution
counts not read or scored).** Four of the six A images stopped at once: GeMClean refused "the PSF
convolved with scale 1651 (1608) has no positive peak" on R3 and T1-T3 (one scan, or a 2 h
simulation). The automatic scale list's tenth scale (n/2.5 pixels) took 0 components on every E2-A
and E2-N image and on R2-A. Every image of this note (A, P and T) now adds `-multiscale-max-scales 9`
to section 2's argv; the six A images run again under it. The 10-scale R1-A and R2-A are kept as
`img/R1-A10`, `img/R2-A10` and reported only. Two side findings for the coordinator, not acted on
here: GeMClean stops where radler may drop such a scale (not checked), and replacing `dl4c.sh` while
the first lanes were reading it made them end on a bash parse error (the lanes' own work had
finished; the driver is no longer edited while a lane runs).

**Amendment 3, 2026-11-21 00:50 SAST (component budget; component counts and stop reasons read, no
convolution count, saving or P/T number read).** R1-A (9 scales) and R1-A10 ended their last major
cycle on GeMClean's component budget (`Budget`, exactly 1,000,000 components = `-niter 1000000` of
section 2's argv), so R1's cost is truncated and not comparable with an arm that finishes below it.
R2-A (883,002), R3-A (884,936) and T1-A (68,469) stopped by the stop rule in every cycle. Every image
from now on runs with `-niter 10000000` (driver `dl4c2.sh`); GeMClean is deterministic, so for an image
that never reaches 1,000,000 components the result is identical under either budget, and the finished
R2-A, R3-A and T1-A (and T2-A, T3-A, running under the old driver) stand. R1-A runs again; the
truncated one is kept as `img/R1-A-budget`. R1-P had not started and is removed; R1's mask is rebuilt
from the new R1-A and committed before R1-P runs. Rule addition, written before any saving is read: a
case whose A or masked arm ends on the budget under `-niter 10000000` does not count (section 4).
R3-P mask (from R3-A): 1,092,478 pixels (6.5 %), level 106 µJy, SHA-256 in
[results/dl4c-mask/masks/R3-P.json](results/dl4c-mask/masks/R3-P.json).

**Amendment 4, 2026-11-21 20:30 SAST (a stop rule for R1-A; no saving, P/T or R1 number read).** R1-A
under `-niter 10000000` has run 18 h (GeMClean process since 02:30 SAST, about 3 cores) past its
earlier 1,000,000-component budget. Whether its residual peak and threshold still fall cannot be read:
GeMClean writes its per-cycle lines only when it ends, and R1-A's log holds the data-read line alone.
Rule (coordinator's proposal, written before deciding): R1-A stops at 24 h of GeMClean wall time
(2026-11-22 02:30 SAST) if it has not ended; it is then recorded as **not converged**, R1 does not
count (section 4), R1-P is not run, and #43 is scored on R2, R3 and T1-T3 under the frozen rule
unchanged (so at most five cases can count; "fewer than four count" still means null). If R1-A ends by
itself before the deadline, its components and stop reason decide as in amendment 3. Either way, R1-A's
behaviour is recorded as a GeMClean finding for the coordinator: the auto-masked multiscale clean of
E2-N's scan 6 at E2's settings did not reach its stop within 1,000,000 components, while scans 8 and 10
stopped at 883,002 and 884,936.

## Measured result

### Stage 9, settings (re-read of seen results, 2026-11-20; no run)

| Grid (note) | Observations | Setting choices | Best fixed (mean score) | Per-observation chooser | Margin (the grid's own) | Reading |
| --- | --- | --- | --- | --- | --- | --- |
| sdm03-default (reserve table) | 2: ESO137 scans 4 and 14 (one track) | A0, SDa, Sa, SDm03, Sm (GeMClean; WSClean arms excluded) | Sm, mean D 0.006 (A0 0, SDm03 −0.053, SDa −0.141, Sa −0.159) | scan 4 A0 (D 0), scan 14 SDa (0.398): mean 0.199 | D 0.10 (rule 4) | **headroom 0.193 > 0.10** |
| stop28-default (H9-H16, H17-H24) | 16 blind skies (+ seen S1-S3, H1-H8, pilot) | ε ∈ {0, 0.02} | 0.02: saving ≥ 0 cycles and Q-D on all 16 | 0.02 on every sky | saving ≥ 1 cycle mean | **no headroom** (chooser = fixed) |
| gemclean-stop28 | S1-S3, H5-H8 | ε | subsumed by stop28-default (same setting at the shipping accuracy) | – | – | not scored |
| selfcal-defaults | 1 (the pilot and its held-out copy) | 13 cells | – | – | – | one observation: not scored |
| automask-cycle | 2 scans | none (a diagnosis, one setting) | – | – | – | not a settings grid |

**Stage 9 outcome: headroom, untrainable now** (section 5, second rule), on sdm03's mask-form grid
alone: a per-scan choice of imaging form would beat the best fixed form by 0.193 in D against a 0.10
margin, but the two "observations" are two scans of one track, and a settings network has nothing to
learn from two samples. The grid that would make it trainable: sdm03's arms on #39's capture blocks
(at least the five training blocks), scored by the same D. Cost note: the form that wins scan 14 (SDa)
cost 9-12 × the default's wall, so a chooser trades wall for quality; it is not a cost lever for the
63-65 %. stop28's ε shows the opposite case: a setting that is right everywhere needs no predictor.

### Stage 6, mask bound

Issue for amendment 2's refusal: [gijzelaerr/rang-core#54](https://github.com/gijzelaerr/rang-core/issues/54).

Masks (step 4), built from the 9-scale A images and committed before any P or T image
([results/dl4c-mask/masks](results/dl4c-mask/masks), with SHA-256): R1-P 1,481,996 pixels (8.8 % of the
image; level 147 µJy = 5 × 29.4 µJy), R2-P 1,190,645 (7.1 %; 113 µJy), T1-T 55,316 (0.33 %; 117 µJy = 5 ×
the simulator's Briggs image rms 23.4 µJy). For T masks the noise is the scorer's `briggs_image_rms`
(the images use Briggs 0.5), read from the prepare step's meta.

T3-T (from T3-A, 107,486 components, stop rule): 52,605 pixels (0.31 %), level 117 µJy.

T2-T (from T2-A, 93,731 components, stop rule): 78,934 pixels (0.47 %), level 117 µJy.

_Running (A image R1; P/T images queued)._
