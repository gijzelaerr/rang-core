# Rang: the gap between CLEAN and a sparsity-regularised imager on MeerKAT truth skies (issue #24, step 1)

Status, 2026-11-13: **protocol frozen; amendment A1; stage 2 done (U\* = U-a); held-out runs in progress.** Issue
[gijzelaerr/rang-core#24](https://github.com/gijzelaerr/rang-core/issues/24), step 1, from the
stub [proposals/imaging-gap-comparators.md](proposals/imaging-gap-comparators.md). A comparison
with no rang code: GeMClean, WSClean and pfb-imaging run as released, scored against known truth.
No novelty claim; the outcome decides whether step 2 (an RML or plug-and-play loop in GeMClean,
a separate proposal) is worth writing. Branch `claude/rml-gap-cc5921` from main `30d9412`.

## 1. Question and hypothesis

Run to convergence, does a sparsity-regularised imager (pfb-imaging `sara`) recover MeerKAT skies
with extended emission with at least 2 × lower model error than GeMClean multiscale with automatic
masks, at no more than 5 × its wall time? What is not claimed: anything about learned imagers (arm
A is not run, section 3), real data quality (the pilot is timed only), or wall time on an idle host
(section 6).

## 2. Data

All MeerKAT, 64 dishes, simulated by the core with known truth, except the pilot.

| set | skies | sky | where | role |
| --- | --- | --- | --- | --- |
| tuning | S1, S2, S3 | `gemclean_bench_simulate.py` (S1 50 points; S2 S1 + a 2 Jy 40″ Gaussian; S3 500 points 0.1-100 mJy), dec −30 | `D:\rang\outputs\20261102-gemclean\bench\data\s{1,2,3}.ms` | tune U only |
| **gated, held out** | **H4, M1, N1, N2** | H4's recipe (30 points 5-300 mJy, 6 Gaussians FWHM 20-200″ and 0.1-2 Jy, a curved tail of 25 Gaussians holding 3 Jy); H4 dec −45, M1, N1, N2 dec −60 | H4 `D:\rang\outputs\20261103-gemclean-heldout\sim\data\h4.ms`; M1 `D:\rang\outputs\g5-20261107-03\data\m1.ms`; N1, N2 new (below) | the decision |
| reported, held out | H1, H2, H3 | points only (H1 dec −75, 60 points; H2 dec +10, 300 blended points; H3 4096² × 1.5″, 120 points) | `...\20261103-gemclean-heldout\sim\data\h{1,2,3}.ms` | reported, not gated |
| reported, held out | DF5-O | [df5o-deconv-oracles.md](df5o-deconv-oracles.md): 1024² × 2″, 16 channels, natural, 40 points 15 µJy-20 mJy, 4 Gaussians, an ESO 137-006-like radio galaxy, all on the grid | WSL `~/Github/rang/outputs/df5o-20261031-01/field` | reported; answers DF5-O's open item "sara at a converging budget" |
| runtime only | pilot | ESO 137-006, set A of [gemclean-heldout.md](gemclean-heldout.md) (`cal2.ms`, 256 channels, 4096² × 3″) | `...\20261103-gemclean-heldout\real\cal2.ms` | wall time, optional (section 7) |

Bench skies: 2 h at 8 s, 8 channels of 25 MHz from 1.3 GHz, 20 µJy natural noise, flat spectra,
circular Gaussians, positions continuous (not on pixel centres), predicted by direct Fourier sums.

**Why these four gate** (a reading of the stub, recorded here before any run): the stub's rule is
"3 of 4 held-out skies" and its hypothesis is about extended emission; H1-H3 hold points only, so a
rule over H1-H4 would be decided mostly by skies the hypothesis does not address. The four gated
skies are the four held-out skies with extended emission. H1-H3 and DF5-O are scored with the same
measures and the same rule, reported beside the decision, and cannot change it.

**New skies N1, N2.** `examples/gemclean_bench_simulate.py --sky M1 --sky-seed S --noise-seed T
--noise-out`, the seeds being the first 8 and the next 8 hex digits (as integers) of
`sha256("<protocol commit> N1")` and of `sha256("<protocol commit> N2")`, `<protocol commit>` the
full hash of the commit that adds this note; a seed equal to one in `python/rang/simtruth.py` or
the simulator's tables moves on by 8 digits (G4's `seeds.py` rule). Seeds are recorded in a second
commit before either sky is simulated. Nothing is redrawn.

**Held-out data are read once.** H1-H4, M1, N1, N2 and DF5-O enter only after U's configuration
is fixed on S1-S3 (section 3). Pre-freeze tooling probes: none were run on any sky.

**Seed record (2026-11-13, written after the freeze commit `292b2b2f42dd34fc4005ce97468c5a4e53616eed`,
before either sky is simulated; no collision):** N1 sky **1590775363**, noise **260180386**
(digest `5ed14e43…dbf12733`); N2 sky **2762275878**, noise **306332801** (digest `a4a4fc26…a05a1d`).

## 3. Arms

Common to every arm on the bench skies: Stokes I, 2048² × 1.5″ (H3 4096² × 1.5″), Briggs 0.5,
gridder accuracy 1e-6 with w-gridding, one deconvolved MFS image over the 8 channels (the skies are
flat-spectrum), **8 threads**.

| arm | tool, version | settings |
| --- | --- | --- |
| **G** | GeMClean, built from main `30d9412` (`cargo build --profile gemclean --bin gemclean`, native Windows; sha256 recorded with the first result) | G5's settings with G4's masks: `-size 2048 2048 -scale 1.5asec -weight briggs 0.5 -niter 1000000 -gain 0.1 -mgain 0.8 -nmiter 1000 -data-column DATA -field 0 -j 8 -multiscale -auto-mask 6 -auto-threshold 1` (no `-abs-threshold`; G4's run A2) |
| **W** | WSClean 3.7, `rang-wsclean-native:3.7` (WSL docker, `--network none`) | as G, plus `-gridder wgridder -no-min-grid-resolution -wgridder-accuracy 1e-6 -pol I -no-update-model-required` |
| **U** | pfb-imaging 0.0.11 `sara`, `rang-pfb-imaging:0.0.11` (DF5-O's image, `sha256:226e8e81…`) | `init` (`--channels-per-image 8`: one band, as G's single MFS image; `--data-column DATA --weight-column WEIGHT_SPECTRUM --precision double --product I --integrations-per-image -1 --bda-decorr 1.0`), `grid` (`--nx/--ny`, `--cell-size 1.5 --robustness 0.5 --psf-oversize 1.4 --epsilon 1e-6 --do-wgridding`), `sara` in the configuration fixed by tuning (below), `--tol 5e-4`, `--epsilon 1e-6`, `--nthreads 8`, `--backend native`, `LD_LIBRARY_PATH=/opt/pfb/lib` (DF5-O D4) |
| A | HyperAIRI or R2D2 | **not run: owner decision open** (the stub's decision 1). Recorded as not run, not as a null. |

**DF5-O field**, every arm: DF5-O's common settings (1024² × 2″, natural, 16 channels imaged and
deconvolved jointly, no spectral fit, gridder accuracy 1e-6) with `-channels-out 16 -join-channels
-multiscale -auto-mask 6 -auto-threshold 1 -mgain 0.8 -gain 0.1 -nmiter 1000 -niter 1000000`, 8
threads for G and W; U is DF5-O's `pfb-sara` arm exactly (16 bands, the recipe, section 2.2 there)
with `--niter` raised to the budget below and 8 threads. GeMClean's acceptance of this combination
is checked with `-niter 0` before the first run; if it refuses, G on DF5-O is recorded as not run.

**U's budget.** One `sara` run stops at `tol` (`norm(x − x_p)/norm(x) < 5e-4`), at pfb's
divergence check (`--diverge-count 5`, its default), or at the cap: **40 major cycles or 4 h of
wall time (init, grid and sara), whichever comes first** (DF5-O field: 40 cycles or 6 h). The cap
is not a convergence: a run stopped by it is recorded as "not converged". pfb writes the MFS model
and residual of every major cycle (`*_model_<k>.fits`); each is scored, with its cumulative wall
time from the file's modification time against the start of `init`.

**U's tuning, on S1-S3 only.** At most four configurations, each run on S1, S2 and S3 with a cap of
20 major cycles or 90 min:

| config | change from DF5-O's recipe (`bases self,db1,db2,db3`, `nlevels 2`, `l1-reweight-from 5`, `alpha 2`, `rmsfactor 1.0`, `gamma 0.99`, `eta 5e-4`, `positivity 1`, `init-factor 0.5`, `pd-tol 1.5e-4`, `pd-maxit 450`) |
| --- | --- |
| U-a | none (the recipe) |
| U-b | `nlevels 4` (larger wavelet scales for the extended emission) |
| U-c | `rmsfactor 0.5` (half the ℓ1 threshold) |
| U-d | `nlevels 4`, `rmsfactor 0.5` |

Selection: the lowest mean over S1-S3 of the primary measure (relative L2, section 4) at each run's
last cycle; ties (within 1 %) go to the earlier letter. The selected configuration, U\*, is the
gated arm; U-a (the recipe) runs on the DF5-O field only. **Contingency, fixed now:** if U-a's first
run (S2) takes more than 6 min per major cycle, only U-a and U-b are tuned, and H3 (four times the
pixels) is not run for U.

## 4. Measures (frozen)

`examples/rml_gap_score.py` (bench skies) and DF5-O's own `examples/compare_df5o.py measure` (DF5-O
field), the latter unchanged.

**Common beam.** A circular Gaussian `B` whose FWHM `b` is the major axis of the half-maximum region
of the MFS PSF around its peak (DF5-O's rule for its `b`), measured on W's MFS PSF of that sky (the
PSF does not depend on the deconvolution). DF5-O field: `b` = 11.58 px (23.2″, its `field.json`).

**Truth on the beam.** `B ⊛ T` is evaluated analytically at every pixel centre: each point
`S δ(x − x_j)` becomes a Gaussian of variance `σ_b²` and each catalogue Gaussian one of variance
`σ_b² + σ_g²`, flux preserved (Jy per pixel). It never passes through a pixelised truth. DF5-O's
truth is on the grid: `B ⊛ T` is the FFT convolution of `truth-mfs.fits`.

**Model on the beam.** `B ⊛ M` is the FFT convolution of the arm's MFS model image (Jy per pixel,
WSClean's FITS orientation; pfb's mapped by the orientation found in its precondition) with `B`'s
continuous transform.

**Apertures.** Every truth component gets a disc of radius `2 √(FWHM_g² + b²)` (points: `2b`);
overlapping discs are merged into groups (union of discs). A group with a Gaussian is extended. Noise
term of a group of `N` pixels `ε = 3 σ √(N / Ω)`, σ the Briggs (DF5-O: natural) image noise of the
noise-only visibilities from `gemclean_bench_compare.py prepare --noise` (M1, without a noise file:
σ from 1.4826 MAD of W's residual outside every group), Ω the area of `B` in pixels.

Per arm and sky:

1. **Relative L2 (primary)**: `‖B ⊛ M − B ⊛ T‖₂ / ‖B ⊛ T‖₂` over the whole image.
2. Relative L2 inside the extended groups and inside the point groups (reported).
3. **Extended flux**: for every extended group, `F_M` and `F_T`, the sums of `B ⊛ M` and `B ⊛ T`
   over the group; passes when `|F_M − F_T| ≤ 0.02 F_T + ε`.
4. **Positions (DF5-O's A2)**: the flux-weighted centroid of `B ⊛ M` against that of `B ⊛ T` in each
   group with `F_T ≥ 20 ε/3`: a single point within `0.1 b`, an extended group within `0.25 b`.
5. **False flux**: the model's (not convolved) flux outside every group, positive, negative and
   absolute.
6. **Residual**: the exact residual of the model through one gridder
   (`gemclean_bench_compare.py`'s `Exact`: the same Briggs 0.5 weights and quadratic for every arm),
   rms and peak over the inner `2N/3` box, in σ; and `Q/Q_0` (and `Q/Q_truth` where the noise file
   exists).
7. **Cost**: wall time (G natively from the job wrapper; W and U from the container's
   `/usr/bin/time -v`, which also gives peak RSS; G's peak RSS is not measured natively), threads,
   major cycles, and for U the reason it stopped.

DF5-O field: DF5-O's A1, A2, false flux, core-recomputed residual RMS and cost, as frozen there, plus
measure 1 with `b` above.

**Scorer validation, before any arm is scored** (on S1-S3, then on each held-out sky before its
arms are scored): the truth itself, rendered as a model by the inverse FFT of its analytic transform
on the grid (the band-limited truth), goes through the model path. **Control: every group's
`F_M/F_T` within 1.000 ± 0.002 and the relative L2 at most 0.002.** The nearest-pixel truth
(`gemclean_bench_compare.py`'s `truth_image`) is also scored and reported: it is the floor a model on
pixel centres reaches on off-grid skies. If the control fails the scorer is fixed before anything is
scored, and the fix is recorded.

**Preconditions.** W's and G's `-niter 0` dirty images against the core's exact dirty image from
`prepare` (L∞/peak ≤ 1e-5, G4's bound). U: pfb's dirty image (from `grid`) against the core's; the
orientation is the one of the eight symmetries that best matches, and must beat every other by at
least 0.5 of the peak; its L∞/peak is reported (pfb's Briggs weighting need not equal WSClean's). A
failed precondition marks that arm on that sky as not scored.

**Parity (W against G)**, on every sky: for every extended group, G5's C2 against WSClean,
`|F_G − F_W| ≤ 0.02 F_T + √2 ε`, and the relative L2 ratio W/G within 0.8-1.25. If parity fails on a
sky, that sky's comparison is void. (G4's residual criterion M3 failed on 2 of 25 apertures on H4 in
G4's run A2, for reasons unrelated to this question, so it is reported, not used for parity.)

## 5. Decision rule (frozen; every outcome named)

On each gated sky `s` (H4, M1, N1, N2): `r_s` = U\*'s relative L2 at its last cycle over G's;
`r5_s` = U\*'s relative L2 at the last cycle whose cumulative wall time is at most 5 × G's wall on
`s`, over G's (no such cycle: `r5_s` undefined, the sky fails every clause that uses it). "U\* meets
the conditions" on `s`: every extended group passes measure 3 and measure 4 holds, both at the
iterate the clause uses.

| outcome | rule |
| --- | --- |
| **void** | parity fails on two or more gated skies |
| **gap at comparable cost** | on ≥ 3 of 4 gated skies, `r5_s ≤ 0.5` and U\* meets the conditions at that iterate |
| **gap, not at comparable cost** | not the above; on ≥ 3 of 4, `r_s ≤ 0.5` and U\* meets the conditions at its last cycle |
| **better, below the bar** | neither gap; on ≥ 3 of 4, `0.5 < r_s < 0.8` |
| **no gap** | on ≥ 3 of 4, `0.8 ≤ r_s ≤ 1.25` |
| **U worse** | on ≥ 3 of 4, `r_s > 1.25` |
| **mixed** | none of the above |

Recorded with every outcome, per gated sky: whether U\* converged (`tol`) within 5 × G's wall
(the stub's "U does not converge within 5 × G's time" is reported as this count), within the cap,
or not at all. A void sky counts in no clause. The same rule is evaluated on H1-H3 and on DF5-O
(with U-a and G there) and reported, not gated.

## 6. Cost and the host

The host is shared (16 threads, 48 GB lock budget; v0.2.0's critical path holds it at critical
priority). Every arm runs under `tools/heavy_lock.py` (the main checkout's copy) as a shared job
with **8 slots** and honest memory (G 8 GB, W 6 GB, U 16 GB at 2048²), so wall times are under shared
load, at matched threads. G runs natively on Windows (MS read from D:); W and U run in WSL docker,
W reading the MS from `/mnt/d` read-only, U reading it from `/mnt/d` in `init` and writing its
zarr stores to WSL ext4 (`~/Build/tmp/20261113-rml-gap/`), FITS and logs then copied to D:. These
differences favour neither side by much compared with the factors the rule uses (2 × and 5 ×), but
a cost verdict within 4-6.25 × (5 × ± 25 %) is deferred to one exclusive hold agreed with the
coordinator and recorded as such.

Host-time estimate (before any run): G and W 3-5 min per 2048² sky, about 2 h for both over 11
skies; U's tuning at most 12 runs × 90 min, the gated U\* runs 4 × 4 h, H1-H3 3 × 4 h, DF5-O 6 h:
at most about 52 h at 8 slots, about 26 h of the whole host. Expected well under that if `sara`
converges; the contingency in section 3 removes H3 and halves the tuning.

## 7. Stages and stop rules

1. Commit this note (the freeze). Record N1/N2 seeds in a second commit.
2. Build G; `prepare` and the scorer control on S1-S3; tune U on S1-S3; record U\*.
3. Simulate N1, N2; `prepare` every held-out sky; the control on each.
4. Run G, W, U\* on the gated skies; then H1-H3; then DF5-O (G, W, U-a).
5. Score, apply section 5, write the outcome.
6. Optional, only if under 20 h of the host has been used: the pilot, G in full and U\* for three
   major cycles, wall time only.

A run that fails (tool error, out of memory) is recorded with its log and repeated once; a second
failure is recorded as the arm's result on that sky. No setting changes after stage 2 without a
dated, labelled amendment.

### Amendment A1 (2026-11-13, post hoc, before any held-out sky is simulated or read)

**What failed.** On S1-S3, G's dirty image against the core's exact dirty image gave L∞/peak
2.71e-5, 2.71e-5 and 2.98e-5, above section 4's 1e-5 bound. W's gave 2.5e-7, 2.5e-7 and 2.2e-7. As
frozen, G would be unscored on every sky.

**Cause.** Section 3 freezes G at GeMClean's default gridder accuracy. Since G7
([g7-defaults.md](g7-defaults.md)) that default is `-wgridder-accuracy 1e-4` in single precision.
The 1e-5 bound comes from G4, whose GeMClean ran at 1e-6, so sections 3 and 4 conflict.

**Check (run before the amendment).** G on S1 with `-wgridder-accuracy 1e-6` (arm `G6` in
`runs.tsv`, 119.6 s against 73.8 s at the default) gives L∞/peak 2.49e-7, equal to W's to the
digits printed. The mismatch is the gridder's accuracy, not the data, weighting or orientation.

**Change.**
- **Arm G** adds `-wgridder-accuracy 1e-6`, W's accuracy, on every sky including DF5-O. The
  bound stays 1e-5.
- **G at the default accuracy** is kept as a reported-only arm, **Gd**, on every sky G runs on.
  It shows whether the outcome depends on this choice. It cannot change the decision.
- **G's previous S1-S3 runs** become Gd's. G is rerun on S1-S3 at 1e-6 (on S1 the check run
  above), and parity is recomputed against the new G.

The change slows G, which only loosens U's 5 × G budget, so it cannot favour CLEAN. U's tuning
does not depend on G and is unchanged.

**Other changes in the same commit (scoring code; the rule is unchanged).**
- **Divergence:** U's "diverged" flag first matched the `diverge_count` row of pfb's option
  table. It now reads pfb's messages only, and each U run records its stop as tol, diverged,
  wall cap or cycle cap.
- **No U iterate within 5 × G's wall:** section 5 counts that sky as U not reaching a model at
  comparable cost (`r5` not defined). The sky cannot count towards "gap at comparable cost".
- **Dirty images:** the preconditions use each run's own dirty image, written by the cleaning
  run, not a separate `-niter 0` run. The dirty image does not depend on `-niter`.

## 8. Measured results

### 8.1 Stage 2: tuning skies S1-S3 (2026-11-13)

**Build.** GeMClean is built from main `30d9412` in 3 min 36 s of compile time (62 min 19 s
including the lock wait). The binary is
`D:\rang\outputs\rml-gap-20261113\bin\gemclean-30d9412.exe`, sha256
`74b4b3788492b4d9789aaf24efb74927092c4818cd2e315b4883cd43dcbb043c`.

**Scorer control.** It passes on S1, S2 and S3: every group ratio is within 1 ± 0.002 and the
band-limited truth's relative L2 is at most 0.002. The common beam is b = 6.736 px on all three
skies, the half-max major axis of W's PSF.

**Preconditions.** Dirty-image L∞/peak against the core's exact dirty image:

| arm | S1 | S2 | S3 | result |
| --- | --- | --- | --- | --- |
| G (`-wgridder-accuracy 1e-6`, amendment A1) | 2.49e-7 | 2.49e-7 | 2.20e-7 | pass |
| W | 2.49e-7 | 2.49e-7 | 2.20e-7 | pass |
| Gd (default accuracy, reported only) | 2.71e-5 | 2.71e-5 | 2.98e-5 | fail |

U's orientation is the identity on every sky, winning by a margin of 0.99, so it passes.

**Parity.** W/G relative-L2 ratios are 0.997 (S1), 1.007 (S2) and 1.005 (S3). C2 passes on the one
extended group, S2's Gaussian; S1 and S3 have none (49 and 362 groups, all point sources). Parity
holds on all three skies.

**G, W and Gd.** Relative L2 and wall time (8 threads):

| sky | G | W | Gd |
| --- | --- | --- | --- |
| S1 | 0.000810, 119.6 s | 0.000807, 261.0 s | 0.000835, 73.8 s |
| S2 | 0.000991, 190.3 s | 0.000997, 300.1 s | 0.000997, 152.6 s |
| S3 | 0.004069, 70.5 s | 0.004089, 181.2 s | 0.004077, 87.1 s |

**U's tuning.** Each configuration ran on S1-S3 with a cap of 20 cycles or 90 min, and every one
of the 12 runs hit the 20-cycle cap without converging: eps at the last cycle was about 3e-3,
against tol 5e-4. Relative L2 at the last cycle (unrounded means, as the selection rule uses
them):

| config | S1 | S2 | S3 | mean | over the lowest |
| --- | --- | --- | --- | --- | --- |
| U-a | 0.0537972 | 0.0527704 | 0.0539912 | 0.0535196 | +0.62 % |
| U-b | 0.0539860 | 0.0528411 | 0.0542046 | 0.0536772 | +0.92 % |
| U-c | 0.0538028 | 0.0526518 | 0.0531342 | 0.0531963 | +0.01 % |
| U-d | 0.0537660 | 0.0526067 | 0.0531976 | 0.0531901 | lowest |

**U\* = U-a**, DF5-O's recipe. U-d has the lowest mean, but all four configurations are within
1 % of it, and the frozen rule sends ties to the earlier letter. Tuning `nlevels` and `rmsfactor`
moves relative L2 by under 1 %.

On the tuning skies U's relative L2 is 13-67 × G's. The tuning skies do not enter the decision;
the held-out results are below.

Score files are in `D:\rang\outputs\rml-gap-20261113\scores\S{1,2,3}.json` and the runs in
`…\runs\{G,W,Gd,U-a,U-b,U-c,U-d}\S{1,2,3}`. Every run and its wall time is in `…\runs.tsv`.

## 9. For the coordinator

Not written yet.
