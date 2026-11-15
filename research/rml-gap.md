# Rang: the gap between CLEAN and a sparsity-regularised imager on MeerKAT truth skies (issue #24, step 1)

Status, 2026-11-15: **protocol frozen; amendments A1-A4. Outcome: "U worse at our settings on
4 of 4 gated skies, and at upstream's preset (without its averaging) on N2"** (sections 8.2 and
8.5). A3's U-up failed its precondition and is not scored (section 8.4); A4's U-up2 gives
`r_up2` = 5.05. Issue
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

### Amendment A2 (2026-11-14, post hoc, before any held-out score is read)

**Why.** The held-out runs did not share one host state. A power cut (about 17:30), D: filling
(about 19:55, E2-A's MS) and WSL memory fragmentation (9p reads failing with ENOMEM) forced
re-runs, and the lock bookings changed mid-stage. Wall times under these loads are not a clean
cost basis: U-a took 3,254 s on H1 and 2,408 s on H2, with the same settings and the same sky size.
AGENTS.md wants timing runs exclusive. The coordinator asked on 2026-11-14 for CPU seconds as the
cost measure, with walls labelled as shared-host. This amendment is written while the first
held-out scoring job runs, and before any of its output is read.

**Change.**
- **Primary cost:** CPU seconds (user + system).
  - W and U: from the container's `/usr/bin/time -v`. U's cost is the sum over init, grid and
    sara.
  - U's iterates: pfb gives no per-cycle CPU time. An iterate's cumulative CPU is init + grid +
    sara's CPU × (the iterate's file time since sara started) / (sara's wall). This assumes a
    constant CPU rate inside sara, which the measured 3.8-4.2 cores per run supports.
- **G's CPU:** not measured in the runs already done (native Windows, no `time`). G is re-run on
  every sky as timing-only arm **Gt**: the same binary and options, with the process's user and
  kernel time read through `GetProcessTimes`, at 8 slots. Gt's model must be identical to G's,
  which also checks that G is deterministic. Its images are not otherwise scored.
- **`r5_s` with CPU:** section 5's `r5_s` uses U\*'s last iterate whose cumulative CPU is at most
  5 × Gt's CPU on `s`. The wall-based `r5_s` (section 5 as frozen) is reported beside it, labelled
  shared-host.
- **Exclusive timing subset** (pre-registered here, run only if needed):
  - When: the outcome differs between the CPU-based and wall-based `r5_s`, or the deciding
    iterate's cost ratio on any gated sky is within 4-6.25 × on either basis.
  - What: G, W and U-a on H4, one exclusive hold each (`heavy_lock.py run -- <cmd>`, no
    `--slots`), once the queue is quiet. U-a runs to its 40-cycle cap.
  - Use: their CPU and wall ratios are reported. If H4's exclusive wall ratio puts H4 on the other
    side of 5 × from its CPU ratio, the outcome is recorded as cost-ambiguous, not decided by
    either basis.
- **Bookings:** from 2026-11-14 about 19:30, W and U book 4 slots (measured use 2.1-3.5 and
  3.8-4.2 cores). Their thread counts stay 8, so their settings are unchanged. Applies to W H1-H3
  and U-a H1, H3. G still books 8 (about 7.4 cores used).
- **Repeats** (section 7, a failed run is repeated once):
  - W H1 failed with rc 125 (D: full).
  - W H2 and W H3 failed with rc 255 (ENOMEM on a 9p read). WSL's page cache was dropped before
    the repeat.
  - U-a H1 was repeated: its first run's last writes hit the full disk.
  - The failed attempts' logs are kept (`runs\W\H2-enomem`, `runs\W\H3-enomem`, `runs.tsv`).

**Clarification A2.1** (2026-11-14, post hoc). Written after the first held-out scoring pass,
whose `r_s` values were read. A2 as written does not say two things.
- **The trigger.** The `r5_s` iterate is by construction the last one at or under 5 ×, so its own
  cost ratio is almost always in 4-6.25 ×. A2's trigger is read as "a clause that uses `r5_s` or
  the 5 × budget decides the outcome, and the result depends on the basis". Those clauses are the
  two gap clauses and the converged-within-5 × count. Outcomes decided by `r_s` alone (better,
  below the bar; no gap; U worse; mixed) do not use cost, and do not trigger the exclusive subset.
- **"Cost-ambiguous"** qualifies only the comparable-cost clause and the converged-within-5 ×
  count. It never relabels an outcome that `r_s` decides.

The coordinator may still order the exclusive H4 subset; it is pre-registered above either way.

### Amendment A3 (2026-11-14, post hoc: U-a's gated scores are read; before the run below)

**Why: baseline strength.** U-a's `r_s` is 7-14 on the gated skies. The coordinator asked whether
pfb sara ran as its authors recommend before that is stated (AGENTS.md: wins against weak
baselines establish nothing). The check, from pfb 0.0.11 itself:
- **Upstream preset.** The image ships a stimela recipe, `pfb_imaging/recipes/sara.yml` (`gosara`),
  that fixes the sara step at `bases self,db1,db2,db3`, `nlevels 2`, `pd-tol 1.5e-4`,
  `pd-maxit 450`, `tol 5e-4`, `gamma 0.99`, `eta 5e-4` and `positivity 1`. U-a's sara step matches
  these. U-a departs from the recipe's defaults on:
  - `l1-reweight-from`: 5 (recipe 7);
  - `psf-oversize`: 1.4 (recipe 1.6);
  - `robustness`: 0.5 (recipe -0.3), chosen to match G's weighting;
  - `chan-average`: 1 (recipe 4); `bda-decorr`: 1.0 (recipe 0.98);
  - gridder `epsilon`: 1e-6 (recipe: the cab default, 1e-7);
  - `niter`: 40 (recipe 15).
- **Deprecation.** pfb 0.0.11 prints a deprecation notice for `pfb sara` ("Migrate to: pfb
  deconv"), but its shipped recipe still calls `sara`.
- **Not converged.** On every gated sky:
  - the outer `eps` is 2.3-2.5e-3 at cycle 40 against `tol` 5e-4, falling only from about
    3.1e-3 at cycle 10; at that rate, reaching `tol` would take about 160 more cycles;
  - the residual rms is 106-162 µJy (σ ≈ 23 µJy) and still falling slowly;
  - the primal-dual inner solve stops at `pd-maxit` in each of the first four cycles, and
    converges after the l1 reweighting starts.

So the gated result is, at most, **"U worse at our settings"** (U-a, 40-cycle cap, not converged).

**Pre-registered test (run once, after this commit).**
- **Arm `U-up`** on **N2**, the gated sky with the lowest `r_s` (7.4), where U was closest to G.
  - The settings are the `gosara` recipe's own values: `robustness -0.3`, `psf-oversize 1.6`,
    `chan-average 4`, `bda-decorr 0.98`, `l1-reweight-from 7`, `alpha 2`, `rmsfactor 1.0`, and
    the cab default gridder `epsilon` (1e-7, in `grid` and `sara`). The sara step is unchanged.
  - Kept fixed: the image geometry (2048² × 1.5″), Stokes I, one band, 8 threads, and `tol` 5e-4.
  - Budget: until `tol`, or a cap of **200 major cycles or 12 h** of wall time.
  - Booking: 4 slots.
- **Scoring:** section 4 as for U-a, at its last cycle and at its last cycle within 5 × Gt's CPU.
- **Rule** on `r_up` = U-up's last-cycle relative L2 over G's on N2:
  - **`r_up > 1.25`:** "U worse" holds on N2 at upstream's preset as well. The outcome is stated
    as "U worse at our settings on 4 of 4 gated skies, and at upstream's preset on N2".
  - **`r_up ≤ 1.25`:** the outcome is stated only as "U worse at our settings". U-up is then run
    on H4, M1 and N1 under a further dated amendment before any claim about upstream settings.
  - **Convergence:** whether U-up reaches `tol` within the cap is reported either way.
- **Not tested:** `pfb deconv` (the successor command), and upstream settings on the other gated
  skies unless the rule above calls for them.

### Amendment A4 (2026-11-15, post hoc: U-up's result in section 8.4 is read; before the run below)

**Why.** U-up was not scored. The recipe's `chan-average 4` merges this MS's 25 MHz channels into
100 MHz ones and smears the sky (section 8.4). A "U worse" verdict is only worth something against
pfb at its own best settings. The coordinator decided, at the owner's request, to run the recipe
again without its averaging.

**Pre-registered test (run once, after this commit).**
- **Arm `U-up2`** on **N2**: U-up's settings with `chan-average 1` and `bda-decorr 1.0` (U-a's
  values; this MS has no fine channels to average). Everything else as U-up:
  - `robustness -0.3`, `psf-oversize 1.6`, `l1-reweight-from 7`;
  - gridder `epsilon` 1e-7 in `grid` and `sara`;
  - the recipe's sara step;
  - `tol` 5e-4, 8 threads, a cap of 200 major cycles or 12 h, booked at 4 slots.
  
  Code: `runs.py`, `CONFIGS["U-up2"]` and `UP_BY_CONFIG`.
- **Scoring:** section 4 as for U-a, at the last cycle and at the last cycle within 5 × Gt's CPU.
- **Precondition.** Section 4's precondition applies unchanged. If it fails only on the
  orientation margin (robust -0.3 against the core's natural-weighted dirty image may do that),
  this secondary check decides, and the result is labelled "scored under A4's secondary
  precondition". It requires both:
  1. **Orientation.** The Pearson correlation of pfb's dirty image with the core's exact dirty
     image is higher in the chosen orientation than in each of the other seven, by at least 0.5.
  2. **No smearing.** For N2's isolated point sources (nearest other component at least 40 px
     away), the median of pfb's dirty-image peak (5 × 5 px box) over catalogue flux lies within
     0.9-1.1 in each radius bin: under 10′, 10-20′ and over 20′ from the phase centre. This is the
     section 8.4 test, on which U-a gives 0.97-0.99.
  
  If neither check passes, U-up2 is not scored, and the outcome stays "U worse at our settings".
- **Rule** on `r_up2`, U-up2's last-cycle relative L2 over G's on N2:
  - **`r_up2 > 1.25`:** the outcome is stated as "U worse at our settings on 4 of 4 gated skies,
    and at upstream's preset (without its averaging) on N2".
  - **`r_up2 ≤ 1.25`:** the outcome is stated only as "U worse at our settings". U-up2 is then run
    on H4, M1 and N1 under a further dated amendment before any claim about upstream settings.
  - Convergence (`tol` within the cap) and `r5_s` on the CPU basis are reported either way.

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

### 8.2 Gated skies H4, M1, N1, N2 (2026-11-14/15)

**Controls and preconditions.**
- The scorer control passes on all four skies.
- **Preconditions:**
  - G's and W's dirty-image L∞/peak is 1.1e-7 to 2.4e-7, so both pass.
  - Gd's is 8.4e-6, 1.6e-5, 1.3e-5 and 1.8e-5 on H4, M1, N1 and N2. Gd is reported only, and the
    bound is 1e-5.
  - U's orientation is the identity, winning by a margin of 0.99-1.00.
- **Parity:** W/G is 0.977, 0.988, 0.988 and 0.980, and C2 passes on every extended group (4, 4, 4
  and 6). Parity holds on 4 of 4, so the outcome is not void.

**Relative L2** and cost. Walls are shared-host. CPU is user + system; G's CPU comes from its Gt
re-run, whose model is bit-identical to G's on every sky.

| sky | G | W | Gd | U-a (cycle 40) | `r_s` | `r5_s` wall | `r5_s` CPU | U/G CPU, 40 cycles |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H4 | 0.004888 | 0.004777 | 0.004802 | 0.0468 | 9.58 | 11.12 (cycle 4) | 9.58 (cycle 40) | 4.90 |
| M1 | 0.003806 | 0.003761 | 0.003800 | 0.0524 | 13.77 | 14.81 (cycle 9) | 13.77 (cycle 40) | 3.67 |
| N1 | 0.004348 | 0.004298 | 0.004333 | 0.0430 | 9.88 | 12.61 (cycle 3) | 9.88 (cycle 40) | 4.60 |
| N2 | 0.003777 | 0.003701 | 0.003753 | 0.0279 | 7.38 | 7.90 (cycle 12) | 7.38 (cycle 40) | 3.95 |

| sky | G wall / CPU | W wall / CPU | U-a wall / CPU | U-a eps at 40 | U-a exact residual (G's) |
| --- | --- | --- | --- | --- | --- |
| H4 | 145.9 s / 1,272 s | 270.3 s / 858 s | 1,676 s / 6,230 s | 2.47e-3 | 6.74σ rms (1.06σ) |
| M1 | 181.4 s / 1,609 s | 286.4 s / 891 s | 1,579 s / 5,901 s | 2.49e-3 | 10.06σ (1.04σ) |
| N1 | 132.3 s / 1,397 s | 382.1 s / 1,321 s | 1,739 s / 6,422 s | 2.30e-3 | 7.51σ (1.06σ) |
| N2 | 209.7 s / 1,645 s | 413.2 s / 1,376 s | 1,785 s / 6,502 s | 2.37e-3 | 6.63σ (1.06σ) |

**Outcome (section 5):**
- **`r_s` > 1.25 on 4 of 4 gated skies, so the outcome is "U worse".** That clause uses `r_s`
  only; the cost basis (A2, A2.1) cannot change it, and the exclusive timing subset is not
  triggered.
- **Neither gap clause holds** on either cost basis, because `r5_s` ≥ 7.9 everywhere.
- **Convergence:** U\* reached `tol` on 0 of 4 skies, within 5 × G's wall or CPU or within the
  cap. Every run stopped at the 40-cycle cap.
- **Extended groups:** U\* fails measure 3 on every gated sky. A2 positions pass.
- **A3 and A4 scope:**
  - The upstream-preset run on N2 (U-up, section 8.4) failed its precondition and is not scored,
    so A3's rule does not fire.
  - A4's U-up2, the preset without its averaging, gives `r_up2` = 5.05 > 1.25 (section 8.5). The
    outcome is therefore stated as **"U worse at our settings on 4 of 4 gated skies, and at
    upstream's preset (without its averaging) on N2"**.

**Why U is worse (diagnosis, not a measured cause).**
- **Not a scorer artefact.** pfb's own peak residual, from its log, matches the scorer's exact
  residual peak within 1 % on every sky (for example H4: 10.25 against 10.19 mJy).
- **Biased fluxes.** U's median group flux ratio is 1.07-1.08 on every sky. The total-flux ratio
  is 0.96-1.08.
- **A floor near 0.05.** U's relative L2 is 0.043-0.054 on every sky except N2 (0.028), at every
  setting tried, while G's ranges from 0.0006 to 0.0049. U reaches 0.05 by cycle 3-5 and then falls
  about 1 % per 4 cycles.
- **Not converged.** The outer `eps` is 2.3-2.5e-3 at cycle 40, falling only from about 3.1e-3 at
  cycle 10. The primal-dual inner solve stops at `pd-maxit` in cycles 1-4.

The pattern fits a sara solution stalled by its regularisation and Hessian approximation at this
recipe, not by data or noise. That is a reading, not a measured cause.

### 8.3 Held-out skies H1-H3 and DF5-O (reported, not gated)

| sky | b (px) | groups (extended) | G | W | U-a | `r` | U/G CPU | U-a exact residual |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H1 | 9.067 | 56 (0) | 0.000593 | 0.000595 | 0.0525 | 88.6 | 17.1 | 35.2σ |
| H2 | 8.661 | 224 (0) | 0.002411 | 0.002455 | 0.0533 | 22.1 | 7.3 | 15.7σ |
| H3 (4096²) | 6.792 | 119 (0) | 0.000761 | 0.000754 | 0.0515 | 67.7 | 13.2 | 23.3σ |

Parity holds on H1-H3, at W/G 1.003, 1.019 and 0.990. U-a never converges: eps is 2.33-2.43e-3
at cycle 40. On H1 no U iterate falls within 5 × G's wall (`r5` undefined, A1).

**DF5-O field** (1024² × 2″, 16 channels, natural weighting). Scored with DF5-O's own
`compare_df5o.py measure` (floor and P2 from `outputs/df5o-20261031-01`), plus relative L2 at
b = 11.58 px (`df5o_l2.py`):

| arm | relative L2 | A1 / A2 | exact residual (inner) | total flux | wall / CPU |
| --- | --- | --- | --- | --- | --- |
| G | 0.003835 | pass / pass | 0.92σ | 0.99983 | 1,180 s / 6,952 s |
| Gd | 0.003718 | pass / pass | 0.94σ | 0.99955 | 1,421 s / 7,758 s |
| W | 0.003820 | pass / pass | 0.92σ | 0.99969 | 3,142 s / 7,520 s |
| U-a (40 cycles) | 0.05284 | fail (29 of 39) / fail (5) | 29.2σ | 1.03244 | 11,086 s / 45,203 s |

- **`r` = 13.8;** `r5` is 13.1 within 5 × G's wall (cycle 6) and 13.8 within 5 × G's CPU
  (cycle 22). U-a is not converged (eps 2.3e-3 at cycle 40).
- **This answers DF5-O's open item** "sara at a converging budget": four times DF5-O's 10 cycles
  leave the residual where it was (30σ in DF5-O, 29σ here) and do not reach `tol`.
- GeMClean accepted `-channels-out 16 -join-channels -multiscale -auto-mask` (the `-niter 0`
  check, 362 s with lock wait).

**Gd (amendment A1, reported only):** Gd's relative L2 is within 4 % of G's on every sky (largest: H1, -3.4 %), so the
outcome does not depend on G's gridder accuracy.

### 8.4 Upstream-preset test U-up on N2 (amendment A3)

**Result: not scored.** U-up fails section 4's precondition on N2, so A3's rule on `r_up` does not
fire. The outcome stays **"U worse at our settings"**, with no claim about upstream's preset.

- **Precondition.** pfb's dirty image against the core's has L∞/peak 0.955 (U-a: 0.014). The best
  orientation, the identity as for U-a, wins by 0.077 of the peak, against the required 0.5.
- **Stop.** pfb ended the run itself at cycle 107 ("Algorithm is diverging. Terminating.").
  - Its stop test fires when the peak residual stops falling: 1.901e-3 at cycle 106, 1.903e-3 at
    cycle 107. The values did not blow up, and none of A3's stops was reached (`tol`, 200 cycles,
    12 h).
  - Not converged: `eps` is 2.51e-3 at cycle 107 against `tol` 5e-4, down from 6.1e-2 at cycle 10
    and 4.4e-3 at cycle 50.
  - The primal-dual inner solve hit `pd-maxit` in most cycles.
  - pfb logs "cannot access local variable 'xfit'" in its model-fit step every cycle, here and in
    U-a (40 of 40), so the message does not separate the two runs.
- **Cost.** Wall 18,150 s (shared-host); CPU 69,112 s, 42 × Gt's CPU.
- **Diagnostic values (not scored):**
  - Relative L2 is 0.439 (`r` = 116). It is 0.470 at cycle 1 and stays at 0.439 from cycle 9 on,
    while pfb's own residual falls 40 ×.
  - Points 0.79, extended 0.19; total flux 0.98 of truth.
  - pfb's own peak residual is 1.9e-3 Jy, against the scorer's exact 0.219 Jy. For U-a these agree
    within 1 %.

**Why: the preset's averaging does not transfer to this MS** (post hoc diagnosis, measured on the
run's own dirty images).
- **Coarse channels.** N2's MS has 8 channels of 25 MHz at 8 s integrations. `chan-average 4`
  makes two 100 MHz channels, about 7 % fractional bandwidth each. The recipe's averaging suits
  MeerKAT's native 209 kHz channels (the 4k mode), which these simulated MSs do not have.
  `bda-decorr 0.98` adds averaging in time on top.
- **Point sources smear with radius.** Median dirty-image peak over catalogue flux, for 25
  isolated point sources:

  | distance from phase centre | U-up | U-a |
  | --- | --- | --- |
  | under 10′ | 0.29 | 0.99 |
  | 10-20′ | 0.15 | 0.97 |
  | over 20′ | 0.065 | 0.99 |

  Weighting cannot lower a point source's peak in Jy/beam; averaging can.
- **The orientation is not in doubt.** pfb's dirty images under the two settings correlate at 0.86
  in the identity orientation, and below 0.03 in the other seven. The L∞ margin fails because the
  averaged data give a different image.

So U-up fits pfb's averaged data, not the MS. **It says nothing about SARA's quality at upstream's
sara-step settings.** Amendment A4's U-up2 (section 8.5) is that test.

Files: `runs\U-up\N2\` (logs, iterates, `/usr/bin/time` output) and `scores\N2.json`, whose U-up
arm has `precondition_pass: false`.

### 8.5 U-up2 on N2: upstream's preset without its averaging (amendment A4)

**Result: `r_up2` = 5.05 > 1.25.** A4's rule fires, so the outcome is stated as **"U worse at our
settings on 4 of 4 gated skies, and at upstream's preset (without its averaging) on N2"**.

**Precondition: passes under A4's secondary check** (`a4_precondition.py`, written to
`scores\N2-a4-precondition.json`).
- Section 4's check fails on the margin alone: scaled L∞/peak is 1.00 in every orientation, with a
  margin of 6e-6, and analyse.py's first pass picked orientation 6. Robust -0.3 against the core's
  natural-weighted dirty image gives no L∞ match in any orientation.
- **Secondary check 1, orientation:** the correlation with the core's exact dirty image is 0.795 in
  the identity orientation, ahead of the next by 0.775, so it passes. (U-a: 0.997 and 0.963; U-up:
  0.855 and 0.829.)
- **Secondary check 2, no smearing:** median point-source peak over flux, 25 isolated point sources:

  | distance from phase centre | U-up2 | U-a | U-up |
  | --- | --- | --- | --- |
  | under 10′ | 0.985 | 0.986 | 0.293 |
  | 10-20′ | 0.968 | 0.969 | 0.154 |
  | over 20′ | 0.982 | 0.993 | 0.065 |

  So it passes. U-up would have failed this check (section 8.4).
- **Scoring.** U-up2 is scored in the identity orientation (`precondition_basis: "A4 secondary"` in
  `scores\N2.json`). The first pass in orientation 6 gave a meaningless 1.40 and is superseded.

**Scores** on N2 (G 0.003777):

| | U-a (40 cycles) | U-up2 (107 cycles) |
| --- | --- | --- |
| relative L2, last cycle | 0.0279 (`r` 7.38) | 0.0191 (`r` 5.05) |
| within 5 × G's wall | 0.0299 (cycle 12, 7.90) | 0.0320 (cycle 8, 8.48) |
| within 5 × Gt's CPU | 0.0279 (cycle 40, 7.38) | 0.0253 (cycle 16, 6.69) |
| relative L2, extended / points | 0.0118 / 0.0522 | 0.0127 / 0.0314 |
| exact residual, inner rms / peak | 6.63σ / 434σ | 4.29σ / 229σ |
| total flux / truth | 0.991 | 0.982 |
| measure 3 (extended groups) / measure 4 (positions) | fail / fail | fail / fail |
| CPU, and over Gt's | 6,502 s (3.95 ×) | 70,394 s (42.8 ×) |

- **Upstream settings improve U.** The upstream weighting and reweighting lower U's error by 32 %
  against U-a, mostly in the point sources (0.052 to 0.031). U-up2 is still 5 × G's error at
  43 × G's CPU, and 6.7 × within 5 × G's CPU.
- **Stop and convergence.** pfb stopped the run itself at cycle 107 ("diverging": its peak
  residual stopped falling, at 3.994e-3 in cycles 106 and 107).
  - `eps` was 1.21e-3 against `tol` 5e-4, so the run did not converge. None of A4's stops was
    reached.
  - The primal-dual inner solve hit `pd-maxit` in 104 of 107 cycles.
  - Relative L2 changes by about 1 % after cycle 60 (0.0193 to 0.0191).
  - pfb's "xfit" message appears in every cycle, as in U-a and U-up.
- **Cost.** Wall 18,281 s (shared-host): init 127 s, grid 38 s, sara 18,115 s. CPU 70,394 s; peak
  memory 4.0 GB.

Files: `runs\U-up2\N2\` and `scores\N2.json`.

### 8.6 Not run

- **Pilot:** section 7 allows it only under 20 h of host time, and this study used more.
- **Arm A:** the owner's decision is open.
- **`pfb deconv`:** not run (A3).
- **Exclusive timing subset:** not triggered (A2.1).

### 8.7 Provenance

- **Out directory:** `D:\rang\outputs\rml-gap-20261113`.
  - `runs.tsv`: every run, failures included.
  - `runs\{G,Gd,Gt,W,U-a..U-d,U-up,U-up2}\<sky>\`: commands, logs, FITS, `/usr/bin/time` output
    and `wall.json`.
  - `scores\<sky>.json` and `scores\N2-a4-precondition.json`.
  - `df5o\{ws-G,ws-Gd,ws-W,pfb-sara-U-a}-r1\` and `df5o\measures\`.
- **Deleted 2026-11-15, after scoring (28 GB).** These are not read by any score:
  - pfb's per-cycle `pfb_I_main_residual_<k>.fits` and `pfb_I_main_update_<k>.fits`. pfb's own
    per-cycle residual peaks stay in its logs.
  - The DF5-O MS copies `df5o\field` and `df5o\field-niter0`. The original is in WSL
    `~/Github/rang/outputs/df5o-20261031-01/field`; re-running `df5o.py` or `df5o_l2.py` needs a
    copy of it at `df5o\field` again.
  
  Kept (33 GB): the per-cycle model images, final products, logs, `prep\`, `data\` and the scores,
  so that every score can be recomputed.
- **Seeds:** N1 and N2 as section 2.
- **Binary:** GeMClean as section 8.1.
- **Containers:** `rang-wsclean-native:3.7` and `rang-pfb-imaging:0.0.11`.
- **Scripts:** `research/results/rml-gap-scripts/`.
- **Compact archive:** [results/rml-gap.json](results/rml-gap.json). It holds every sky's scores
  (per arm, U's iterates as cycle, wall, CPU and relative L2) and DF5-O's `l2.json`.
- **Timings:** in [tool-timings.md](tool-timings.md).

## 9. For the coordinator

- **Outcome (section 5, with A3 and A4): "U worse at our settings on 4 of 4 gated skies, and at
  upstream's preset (without its averaging) on N2".**
  - On the gated skies, `r_s` is 9.6 (H4), 13.8 (M1), 9.9 (N1) and 7.4 (N2).
  - Neither gap clause holds on either cost basis.
  - U\* converged on 0 of 4 skies.
  - Parity holds on 4 of 4.
  - The reported skies agree: H1-H3 give `r` = 22-89, and DF5-O gives 13.8.
- **Upstream preset on N2:**
  - U-up, the shipped `gosara` recipe as is, is not scored: its `chan-average 4` smears these
    25 MHz-channel MSs (section 8.4).
  - U-up2, the same recipe without the averaging, gives relative L2 0.0191 against G's 0.0038
    (`r_up2` = 5.05, 6.7 within 5 × G's CPU), at 43 × G's CPU.
  - U-up2 did not converge. pfb's own stop at cycle 107 left `eps` at 1.2e-3 against `tol`
    5e-4 (section 8.5).
  - Upstream settings cut U's error by 32 % against U-a; it is still 5 × G's.
  - U-up2 passed A4's secondary precondition, not section 4's (robust -0.3 has no L∞ match to
    the natural-weighted core dirty image).
- **Not covered:** learned imagers (arm A), `pfb deconv`, SARA converged to `tol`, and upstream
  settings on H4, M1 and N1. A4's rule calls for none of these, since `r_up2` > 1.25.
- **What it means for step 2:** on these skies the sparsity-regularised baseline, at its own
  preset, does not show a gap for an RML or plug-and-play loop in GeMClean to close.
- **Open owner decision:** arm A (a learned imager), as before.
- **Branch.** `claude/rml-gap-up2` from main `70a90e2`: amendment A4 (committed before the run),
  `runs.py`'s U-up2 configuration, `analyse.py`'s A4 secondary branch, `a4_precondition.py`, the
  note, the timings and `results/rml-gap.json`.
  - No code change under `python/`, `core/` or `src/`, and no CHANGELOG entry.
  - Only `check_all.py --quick` was run.
- **Space.** 33 GB is left in `D:\rang\outputs\rml-gap-20261113`, after the 28 GB deleted in
  section 8.7. Nothing is running.
