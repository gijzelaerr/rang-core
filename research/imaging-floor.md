# Rang: the imaging floor on the pilot, a pre-registered attribution (issue #13)

Status, 2026-11-13: **protocol frozen; nothing measured under it yet.** This note was committed
before any statistic below was computed and before any run (`git log -- research/imaging-floor.md`:
the first commit is the freeze). Changes after the freeze are dated and labelled post hoc in
section 9. Raw products: `D:\rang\outputs\20261113-floor` (statistics only; scratch visibilities
are deleted at the end).

## 1. The floor and what is known before freezing

The pilot is ESO 137-006, 1 h, 64 dishes, 256 × 0.418 MHz at 1043 MHz, the publisher's QuartiCal
gains, no self-calibration, no DD solution ([gemclean-heldout.md](gemclean-heldout.md) §5-6).
Every number in this section was read before the freeze. None counts as an outcome of a test
below; each is a prior that a test must reproduce or overrule.

| prior | value | source |
| --- | --- | --- |
| thermal Stokes I image noise, 1 h, Briggs 0.5 | 15.5 µJy | heldout §5 (channel differences, 0.238 Jy per part per visibility) |
| off-source rms, set A (received flags), 3 mJy, GeMClean | 1.0568 mJy (68 ×) | heldout §6 |
| same, set B (145 of 1,830 baselines flagged), 3 mJy | 0.6972 mJy (45 ×) | heldout §6; the flags were chosen after seeing A (post hoc) |
| same, set A, 1 mJy | 0.5995 mJy | heldout §6; the 1 mJy model holds −35.5 Jy, cleaning into the noise |
| model flux | 82.7-83.8 Jy, about 80 Jy in the central source | heldout §6 |
| baselines < 400 m | 3.75 % of the weight, 63 % of the misfit Q | heldout §5 (`diag.py`) |
| worst baselines | 40-200 × the median short-baseline misfit, steady in time, antenna 1 most often | heldout §5 |
| per-channel global flux scale | removes 2.8 % of the short-baseline misfit; ratio follows α ≈ −1 | heldout §5 |
| off-source model flux | nearly all negative: a bowl around the source | heldout §6 |
| rings | elliptical, about 5′ apart, a few tenths of a mJy, in all three imagers | heldout §6 |
| imagers | GeMClean − WSClean plain rms 19 µJy, 3 % of the floor | heldout §6 |

Read as a prior (issue #13's comment): calibration residuals and a few bad short baselines first.
The fall from A to B (power 1.117 → 0.486 mJy², −56 %) is post hoc and is not a share.

## 2. The metric and the attribution rule (frozen)

**Floor F.** The rms of the exact residual image (`Exact.score` of
`examples/gemclean_heldout_real.py`: residual visibilities gridded with the Briggs 0.5 gridding
weights, divided by their sum; 4096 × 3″; `flip_v`, `flip_w`, w-gridding on) over pixels inside
the inner two-thirds and outside set A's source mask
(`D:\rang\outputs\20261103-gemclean-heldout\real\images\source-mask.fits`).

**Excess power.** P = F² − T², with T the floor of the noise-only arm on the same data subset.
Shares are fractions of excess power (variance), never of rms. They need not sum to one; the
unattributed remainder 1 − Σ shares is always reported.

**Data subset.** To bound memory and time, every run (simulated and pilot) uses set A's rows and
32 of its 256 channels, indices 4, 12, …, 252 (every 8th), full band. Briggs 0.5 weights are
recomputed on the subset. Gridder ε = 1e-5. Thermal on the subset is about √8 × 15.5 ≈ 44 µJy,
still 0.04 of F.

**Control C0 (subset fidelity).** F of the pilot subset against set A's GeMClean 3 mJy model
(`run/cal2-003-gem-model.fits`) must lie within ±15 % of 1.0568 mJy. If it does not, that is
reported and the subset's own F is the reference from then on (dated, post hoc).

**Reference excess.** P_pilot = F_C0² − T² on the subset.

## 3. The simulation (frozen)

Simulated data use the pilot's own geometry: set A's UVW, times, antennas, flags and weights on the
same 32 channels, so that the 83 Jy field and the short-spacing coverage are the pilot's.

- **Truth sky:** set B's GeMClean 3 mJy model (`run/cal3-003-gem-model.fits`, 82.7 Jy, −2.8 Jy
  negative), predicted with `core_wgridder.dirty2vis` (ε 1e-5).
- **Facets:** the 4096² image cut into 8 × 8 facets of 512 px (25.6′), each predicted separately;
  sums of 2 × 2 of them give the 4 × 4 facets of 1024 px used by the tests. The phase centre sits
  on a facet corner, so the central source is split across four facets.
- **Noise:** Gaussian, per part σᵢ² = c / wᵢ, wᵢ the Stokes I natural weight, c fitted on the pilot
  from adjacent-channel differences (channel k against k+1 for each subset channel). One noise
  seed, 1301, common to every arm, so differences between arms are the effect alone. Arm C2 repeats
  the control with seed 1302.
- **Residual against the truth.** Each arm's residual is data minus the truth sky, i.e. perfect
  deconvolution: the floor an effect leaves when the sky is known exactly.
- **Arms.** C (noise only), C2 (seed 1302), one or more per hypothesis (section 4), and M, a
  control for model incompleteness: truth as above, but the tests are given the truth with every
  pixel under 10 mJy removed. M is not a hypothesis; it measures how much a test absorbs of an
  incomplete model (issue #6's concern).
- **Amplitudes.** a₁ is the plausible amplitude written in section 4. The floor-level amplitude is
  a₂ = a₁ √(P_pilot / P(a₁)), capped at 50 a₁; arm X₂ is rerun at a₂. Linearity is reported: P(a₂)
  against (a₂/a₁)² P(a₁). a_max is the largest amplitude this note calls plausible.
- **Effect seeds:** 1311 + hypothesis number.

## 4. Hypotheses, injections and tests (frozen)

Each hypothesis has an injection (sim stage) and a correction test Tₓ, run on every arm and then on
the pilot. Tₓ's drop D = (P_before − P_after) / P_before. Tests marked "after T1" run on data
already corrected by T1 (5 min).

| # | hypothesis | injection, a₁ (a_max) | test Tₓ |
| --- | --- | --- | --- |
| H1 | **calibration residuals, antenna-based (closing)** | H1a: per antenna, per 8 s, frequency-independent complex gain, σ 1 % amplitude and 1° phase (5 %, 5°). H1b: the same, steady over the hour | T1: per-antenna complex gains, frequency-independent, StefCal against the model, solution interval 5 min (64 × 12 × 2 real parameters); T1f the same at 8 s |
| H2 | **a few bad short baselines, baseline-based (non-closing), steady in time** (the comment's cause) | 30 baselines under 400 m (seeded), each V × (1 + ε), \|ε\| = 2 %, random phase, steady over the hour and band (20 %) | T2, after T1: per-baseline complex scale, steady over hour and band (1,830 × 2) |
| H3 | **direction-dependent errors** | per 8 × 8 facet outside the central four, per antenna, per 5 min, complex gain σ 2 %, 2° (10 %, 10°); the central four take no error (the DI solve's reference) | T3, after T1: per 4 × 4 facet outside the central four, per antenna, steady complex gains, alternating over facets, 2 sweeps × 8 StefCal iterations |
| H4 | **the primary beam** | katbeam `MKAT-AA-L-JIM-2020` at each 8 × 8 facet's model-flux centroid, rotated with the parallactic angle per time: H4a gain B(t, ν)/⟨B⟩ₜ(ν) (rotation only); H4b B(t, ν)/⟨B⟩ₜ,ᵥ (rotation and chromaticity) (2 × the deviation from 1) | T4: per 4 × 4 facet, per 5 min, a complex scale common to all antennas (16 × 12 × 2) |
| H5 | **the w-term** | H5a: truth predicted with the w sign flipped; H5b: truth predicted without w-correction (convention errors; no plausibility scale) | T5: rescore the pilot with `flip_w` toggled, without w-gridding, and at ε 1e-7 |
| H6 | **RFI below the flag threshold** | additive, fringe-stopped terrestrial signal a σᵢ e^{−2πi w ν / c} on baselines under 400 m, in 3 of the 32 channels (seeded), all times; a = 1 (a 5σ flagger misses it) (3) | T6, after T1: flag the worst 10 % of (channel, 2-min) cells by residual power on baselines under 400 m; the drop is taken against flagging a random 10 % (seed 1316) |
| H7 | **confusion** | a source population, S^{2.5} dN/dS = 10 Jy^{1.5} sr⁻¹ for true 10 µJy-10 Jy at 1.4 GHz, scaled by (1.043/1.4)^{−0.7}, uniform to 4° radius, apparent flux from katbeam's azimuthal mean at band centre (floored at 1e-3 beyond its range); sources inside the image above 3 mJy apparent are taken as modelled and left out; predicted at 6″ on a 5120² grid (no plausibility scale beyond the counts: a_max = 3 × the counts) | none possible by correction. Analytic check: σ_c ≈ 1.2 µJy (ν/3 GHz)^{−0.7} (θ/8″)^{10/3} (Condon et al. 2012) at θ = 12.7″ |
| H8 | **spectral structure under one flat-spectrum term** | truth S(ν) = S₀ (ν/ν₀)^α, ν₀ the band centre, each facet's flux renormalised so its best flat fit is the model. H8a: α = −0.7 everywhere. H8b: α per 8 × 8 facet ~ N(−0.7, 0.3). H8c: α per pixel ~ N(−0.7, 0.3), predicted in 8 α bins (scatter 0.5) | T8: per 4 × 4 facet, per channel, complex scale (16 × 32 × 2) |
| H10 | **bandwidth smearing** (added here: data averaged 2× in frequency, β ≈ 0.26 at 1.78°) | truth = mean of predictions at ν ± Δν/4, model at ν (no scale) | T10: rescore the pilot with the model smeared the same way |
| H9 | **model incompleteness and deconvolution depth** (added here: the bowl, the 3 → 1 mJy fall) | **listed, not tested by injection.** Arm M measures how the tests confuse it; the 3 → 1 mJy fall stays a prior | – |

The time smearing of 8 s dumps is not tested (the data were not averaged in time). Polarisation
leakage into Stokes I is not tested (XX and YY only, no D-terms solved).

**Specificity.** On the sim matrix (every test on every arm at a₂), Tₓ is *specific* when it
removes at least 0.7 of the excess power of its own arm and at most 0.3 of every other arm's
(C, C2 and M included). A test that is not specific gives on the pilot only an upper bound shared by
the arms it fires on.

**Pilot order.** Each test alone (T2, T3, T6 after T1), then cumulatively in the frozen order
T1 → T2 → T8 → T3 → T4 → T6, reporting each incremental drop. T5 and T10 are rescoring. The
baselines T2 weights most are compared with the 145 of set B (overlap reported, descriptive).

## 5. Decision rules (frozen)

For each tested hypothesis X, with D_X the pilot drop of Tₓ alone (as a fraction of P_pilot) and
P_X(a) the excess power of its arm at amplitude a:

- **Attributed, share D_X**, if Tₓ is specific, D_X ≥ 0.10, and P_X(a_max) ≥ 0.5 D_X P_pilot (a
  plausible amplitude can carry that share).
- **Rejected**, if Tₓ is specific and D_X < 0.05, or if P_X(a_max) < 0.05 P_pilot (no plausible
  amplitude can carry 5 % of the floor), whatever the pilot test gives.
- **Unresolved** otherwise: 0.05 ≤ D_X < 0.10, or a test that is not specific (its D_X stated as an
  upper bound shared with the arms it fires on), or a pilot drop larger than any plausible amplitude
  can carry (then the test is absorbing something else, and that is reported).
- **H5:** rejected if no rescoring alternative lowers the pilot's P by 5 % or more and ε 1e-7
  changes F by less than 2 %; otherwise attributed with the drop of the best alternative.
- **H7:** rejected if P_H7(a₁) < 0.05 P_pilot and the analytic σ_c² < 0.05 P_pilot; otherwise an
  upper bound, P_H7(a₁) / P_pilot (no correction test exists).
- **H10:** as H5, with T10.
- **Tolerances.** F reproduces to 2 % between seeds 1301 and 1302 (C against C2), else every share
  is quoted with that spread. Drops are quoted to ±0.02. The shares stated are the raw pilot drops;
  D_X divided by Tₓ's recovery on its own arm is also given, labelled as a correction.

The issue's done-criterion: the floor attributed with a measured share per cause, or every listed
hypothesis recorded as rejected. The remainder is reported either way.

## 6. Cheap analysis on existing products (frozen statistics, provisional verdicts)

On the existing exact residuals of `D:\rang\outputs\20261103-gemclean-heldout\real\run`
(`cal2-003-gem`, `cal3-003-gem`, `cal2-001-gem`, and WSClean plain and fast for A and B), no new
imaging:

- **E1, radial profile.** Off-source rms in annuli about the image peak, 0-10′, 10-20′, 20-40′,
  40-68′.
- **E2, uv distribution of the floor.** FFT of the off-source residual (masked pixels and the outer
  third set to zero); the fraction of power at |uv| < 1,390 λ (400 m at 1043 MHz) against that
  range's share of the gridding weight.
- **E3, A against B** per annulus and in E2's split.
- **E4, shape.** Off-source skewness, and the fraction of pixels below −3 rms against above +3 rms.

The same four statistics are computed on every sim arm's residual. A pilot verdict from E1-E4 is
**provisional**: the pilot's profile is assigned to the arm whose log-profile (E1) and short-power
fraction (E2) lie nearest, and that assignment counts only if the arms themselves are separated by
it (an arm's nearest arm must be itself). E1-E4 never override section 5.

## 7. Runs

Under the main checkout's `tools/heavy_lock.py run --slots 8 --mem 24` at normal priority. Scripts
in `examples/floor_tests.py` (committed after this note). Every run is wall-timed and logged in
[tool-timings.md](tool-timings.md).

## 8. Results

None yet.

## 9. Clarifications and post-hoc changes

**Clarifications, 2026-11-13, written into `examples/floor_tests.py` before the full run produced
any output** (a 6,000-row smoke run checked the code; its numbers are not results):

1. Tests "after T1" (T2, T3, T6) are scored by their increment: D = (P_T1 − P_T1+X) / P_none.
2. T6 sets the chosen (channel, 2-min) cells to zero weight on baselines under 400 m only.
3. a_max for H8a is α = −1.0 (k = 1/0.7); for H8b and H8c a scatter of 0.5. Every hypothesis with
   a scale also gets an arm at a_max, so P_X(a_max) is measured, not extrapolated.
4. T5 and T10 run on every arm as well, against that arm's model set's alternative predictions.
5. Facets are predicted from their own sub-image with a centre shift; the sign was chosen by
   matching the 4 × 4 sum to the full prediction on 3,000 rows (3.6e-6 relative), and each sky
   set's facet sum is checked against its full prediction on all rows.
6. The noise constant is measured, not set: σ per part 0.172 Jy at the median weight on 0.418 MHz
   channels, consistent with heldout §5's 0.238 Jy on the native 0.209 MHz (0.238/√2 = 0.168).
7. The smoke run's `cheap` stage read the real full-data residuals, so E1-E4 on them (section 8)
   were seen before the full run; they are frozen statistics computed after the freeze, not priors.
