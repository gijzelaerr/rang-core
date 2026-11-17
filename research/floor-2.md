# Rang: floor-2, gains against short-spacing incompleteness on the pilot (issues #13, #6)

Status, 2026-11-16: **measured. Under the frozen rules the joint reading is row 4: H1 and H9 stay
unresolved**, because item 5's phase-only test is void (one truncation arm fails its
informativeness condition). Item 1 reads gain-like; item 3 finds the steady errors (P(G3) =
0.86 P_pilot, antenna 1 the worst of 60); item 5's long-baseline T1 survives (ρ_L = 0.97). Post hoc
(section 12), the lead is steady antenna phase errors of about 5°; the frozen reading does not
establish it. Protocol
frozen in `6d00242` before any run (sections 1-10 unchanged since, except the smoke declaration
in section 10). Follow-up to
[imaging-floor.md](imaging-floor.md) (issue #13), items 1, 3 and 5 of its section 8.6, on the
coordinator's decision of 2026-11-16 (owner delegated). Script: `examples/floor2_tests.py`
(committed after this note; it imports `examples/floor_tests.py` and does not change it).
Outputs: `D:\rang\outputs\floor-2-20261116`. Archive: `research/results/floor-2/`.

## 1. Question and what is known before freezing

imaging-floor left H1 (antenna-based calibration residuals) **unresolved, upper bound 0.85, shared
with model incompleteness (H9)**: T1 (5-min antenna gains against the model) removes 0.854 of the
pilot's excess power, but also 0.53 on arm M, whose model lacks the truth's pixels under 10 mJy.
Its section 8.4 (post hoc) noted that facet-scale fits (T4, T8) barely move on the pilot, unlike on
M, and that this excludes M's kind of incompleteness but not flux missing only on short spacings.
This protocol asks one question three ways: **is the floor that T1 removes antenna gain error, or
model flux missing on short spacings?** The answer decides whether #6's self-calibration is the fix.

Read before the freeze (archive `results/imaging-floor/summary.json`, `pilot.json`), so these are
priors, not outcomes:

| quantity | pilot | H1b at a₂ (5.616 × 1 %, 1°) | M (trunc. 10 mJy) |
| --- | ---: | ---: | ---: |
| P / P_pilot | 1 | 0.999 | 1.874 |
| D_T1 (5 min) | 0.854 | 1.000 | 0.532 |
| D_T4 (facet scale per 5 min) | 0.024 | 0.013 | 0.494 |
| D_T8 (facet scale per channel) | 0.042 | 0.019 | 0.491 |

So the pilot's facet-to-antenna ratio R (section 4) is already known: about 0.05 raw. The rules
below are formulas over the simulated arms, not numbers picked around that value. Other priors:
heldout §5's worst short baselines involve antenna index 1 (`ANT01`, 81 m from the array centre, a
core antenna) most often; `badbaselines.json`'s top three all contain it. The truth's pixels under
1, 3 and 10 mJy hold 1.64, 7.74 and 27.41 Jy net (3.67, 10.46, 30.22 Jy positive); measured
before the freeze on `cal3-003-gem-model.fits`.

## 2. Inputs and provenance

The 2026-11-13 scratch (`D:\rang\outputs\20261113-floor`) was deleted; the prep and the sky
predictions are rebuilt from the same inputs, which still exist:

| input | path (under `D:\rang\outputs\20261103-gemclean-heldout\real`) | SHA-256 / check |
| --- | --- | --- |
| set A data (received flags, publisher's QuartiCal net gain applied) | `cal2.ms` (8.1 GB) | rebuilt prep must reproduce `results/imaging-floor/prep-meta.json` (gate R0) |
| truth sky: set B GeMClean 3 mJy model | `run/cal3-003-gem-model.fits` | `b7eb113c356ebe588492626f5712b419f0b29454865dc850081bc6c9b090a028` |
| pilot model: set A GeMClean 3 mJy | `run/cal2-003-gem-model.fits` | `3c5f21290597f91207c8fd19ff0197b8f463eb48d6c4fc62489205aa809c0932` |
| source mask | `images/source-mask.fits` | `8110545cac61e3cdbddc8a0db4c5b2dd0ad47ee01d66bbaff49873fcfa553512` |
| publisher's QuartiCal GKB-net gain on the pilot grid (450 × 8 s, 512 native channels, 61 antennas, 2 hands) | `gains.npz` | `07c94440b65fe75da7bedb83a359a9e7782d521ad4850f0d2c52ea529016ff69`; objects in `results/gemclean-heldout-gains-manifest.json` |

Everything of imaging-floor sections 2-3 holds unchanged: floor F (exact residual, Briggs 0.5,
4096 × 3″, inner two-thirds outside set A's mask), excess power P = F² − T², the 32-channel subset
(indices 4, 12, …, 252), ε 1e-5, the noise model and seed 1301, residual against the truth.
Antenna 1 means index 1 of the MS (`ANT01`).

**Gate R0 (reproduction), checked before any new number is read:**

- prep: `nrow`, `active` equal; `noise_c` and `gridding_weight_sum` within 1e-6 relative of the archive;
- pilot: F(none), F(T1), F(T4), F(T8) within 0.5 % of `results/imaging-floor/pilot.json`;
- arms C@1, H1b@5.616 and K10@1 (= M@1): F(none) within 0.5 %, D_T1, D_T4, D_T8 within 0.02 of `summary.json`.

Truth facets are now predicted 4 × 4 directly (imaging-floor summed 8 × 8 into 4 × 4; the two agree
to 7e-6 relative, section 8.1 there). If R0 fails, nothing below is scored; the failure is reported.

## 3. Arms (simulated, frozen)

Each arm: V = data model + Gaussian noise (seed 1301), tests given the model stated. a₁ is the
amplitude written here; a₂ = a₁ √(P_pilot / P(a₁)), capped at 50 a₁ (it may be below a₁), with
P_pilot = 1.150e-6 Jy² and T = 44.09 µJy from the archive. Arms run at a₁ and a₂ unless stated.

| arm | data | tests given | a₁ (k = 1) |
| --- | --- | --- | --- |
| C | truth | truth | – (noise only; T) |
| H1b | truth × g_p g_q*, steady per antenna, amp σ 1 % k, phase σ 1° k (seed 1312, as imaging-floor) | truth | 1 %, 1°; also k = 5 (a_max) |
| H1bA | as H1b, the same draws, phase set to 0 | truth | 1 % |
| H1bP | as H1b, the same draws, amplitude set to 1 | truth | 1° |
| K1, K3, K10 | kept + k × missing, kept = truth pixels with \|S\| ≥ 1, 3, 10 mJy | kept | k = 1 is the truth (K10@1 = imaging-floor's M) |
| XS2, XS4 | truth + k × E, E = the truth's positive pixels convolved with a circular Gaussian of FWHM 2′ (XS2) or 4′ (XS4), normalised to 1 Jy | truth | 1 Jy |
| XG4 | truth + k × E, E = a circular Gaussian of FWHM 4′ at the pilot model's peak pixel, 1 Jy | truth | 1 Jy |
| MIX | (truth + k_X × E_XS2) × g_p g_q* with H1b's gains at k_H = 5.616/√2 and k_X = a₂(XS2)/√2 | truth | single arm, built after XS2@a₂ |

The X arms are flux missing only on short spacings, the case section 8.4 left open: a Gaussian of
FWHM θ has visibility amplitude exp(−π²θ²q²/(4 ln 2)), so at q = 1,390 λ (400 m) it keeps 0.097 of
its flux at 2′ and 1e-4 at 4′. E's positive, source-shaped form is the deconvolver's typical miss
(a bowl around the source). MIX is descriptive: where an even mixture lands.

## 4. Tests (frozen)

Run on every arm and the pilot, each against the arm's own model facets (4 × 4):

- **T1**: imaging-floor's T1 (StefCal, 5 min, frequency-independent, all baselines), now saving g.
- **T4**, **T8**: unchanged.
- **T1p**: T1 with each StefCal update projected onto unit amplitude (g ← g/|g|), phase only.
- **T1L**: T1 solved with weight zero on baselines under 400 m, then applied to all baselines and
  imaged on all. Per-antenna weight above 400 m is reported; an antenna with none keeps g = 1.

Drops D are fractions of the arm's own excess power, imaging-floor's definition. "Usable" arm: P ≥
0.1 P_pilot and D_T1 ≥ 0.1 (imaging-floor post hoc lesson 1, now frozen).

**Gain gauge** (for item 3, frozen): per 5-min bin b and antenna p, a_bp = |g_bp| divided by the
median of a over active antennas and bins (that median is reported as the flux scale); φ_bp = arg
g_bp minus a least-squares fit c_b + k_b · r_p over active antennas, r_p the antenna's local
east-north-up position (a common phase and a sky shift, not gain errors). ḡ_p = mean over bins of
a_bp e^{iφ_bp}; steady error e_p = \|ḡ_p − 1\|; σ_a = rms_p(\|ḡ_p\| − 1), σ_φ = rms_p(arg ḡ_p);
variable part v = rms over p, b of \|a_bp e^{iφ_bp} / ḡ_p − 1\|. Active: an antenna with gridding
weight in the subset.

## 5. Item 1: the facet-to-antenna ratio (frozen rule)

R = max(D_T4, D_T8) / D_T1, padded by the ±0.02 drop tolerance:
R⁺ = (max(D_T4, D_T8) + 0.02) / max(D_T1 − 0.02, 0.01), R⁻ = max(max(D_T4, D_T8) − 0.02, 0) / (D_T1 + 0.02).

- Gain reference G = {H1b, H1bA, H1bP at a₂}; R_G⁺ = max over G of R⁺.
- Incomplete set I = {K1, K3, K10, XS2, XS4, XG4 at a₂}, usable arms only.
- **Per kind j ∈ I:** j *separates* if R_j⁻ ≥ 2 R_G⁺. If it separates, the pilot is *unlike j* if
  R_pilot⁺ < τ_j = √(R_G⁺ R_j⁻), *like j* if R_pilot⁻ > τ_j, else undecided.
- **Overall:** the discriminator is *valid* if every usable j separates (and at least one X arm is
  usable). Valid and the pilot unlike every j: item 1 reads **gain-like**. Valid and like any j:
  **incompleteness-like** (that kind named). Otherwise **not discriminating**, and the kinds that
  do not separate are named: for them the pattern cannot tell incompleteness from gains, and items 3
  and 5 carry the question.

## 6. Item 3: the pilot's T1 gains against the publisher's (frozen rules)

T1's gains on the pilot are a residual on top of the publisher's net gain, already applied. Their
existence alone does not separate gains from absorbed incompleteness, so the same statistics are
computed on every arm's T1 gains as a control.

- **3a, size (direct).** Arm G3: truth × ḡ_p ḡ_q* (the pilot's steady T1 gains after the gauge),
  noise seed 1301, tests given the truth. Steady errors of the size H1b needs **exist** if
  P(G3) ≥ 0.5 P_pilot, are **absent** if P(G3) < 0.1 P_pilot, else **partial**. Controls G3K10 and
  G3XS2: the same with the steady T1 gains of K10@a₂ and XS2@a₂ (spurious gains from
  incompleteness). If a control's P ≥ 0.5 P(G3), 3a does not separate gains from incompleteness
  (stated with the reading). σ_a and σ_φ are quoted against H1b's 5.6 %, 5.6°.
- **3b, pattern.** s_p = the antenna's share of its gridding weight on baselines under 400 m.
  Spearman ρ(e_p, s_p) on the pilot and on each arm; *core-concentrated* if ρ ≥ 0.4 with a
  permutation p < 0.01 (10,000 permutations, seed 1333). Reading: the pilot's gains look like
  incompleteness's spurious gains if the pilot and every usable X and K arm are core-concentrated
  and H1b is not; like gain errors if neither the pilot nor H1b is; otherwise not discriminating.
- **3c, the publisher's gain.** Per antenna, on the 32 subset channels (each the mean of its two
  native channels), both hands, flagged cells left out: (i) amplitude variability, the median over
  channel and hand of rms over 8 s of \|g\|/⟨\|g\|⟩ₜ − 1; (ii) phase variability, likewise of the
  phase about its circular time mean; (iii) mean amplitude; (iv) gain-flag fraction; (v)
  \|log(⟨\|g_X\|⟩/⟨\|g_Y\|⟩)\|. Spearman of each with e_p, 10,000 permutations (seed 1333);
  *associated* if \|ρ\| ≥ 0.3 and p < 0.002 (0.01 over five). Descriptive: an association says
  which antennas the publisher's solution left worst, not a cause.
- **3d, antenna 1.** Its rank by e_p among active antennas; *among the worst* if rank ≤ 6 (top
  10 %; chance 6 / N_active). Its rank in K10's and XS2's spurious gains is reported beside it
  (it is a core antenna).

## 7. Item 5: phase-only and long-baseline T1 (frozen rules)

ρ_p = D_T1p / D_T1 and ρ_L = D_T1L / D_T1 on each usable arm and the pilot.

- **Validity.** T1L is valid if ρ_L(H1b@a₂) ≥ 0.7; T1p is valid if ρ_p(H1bP@a₂) ≥ 0.7. An invalid
  solver makes its reading void.
- **T1L.** It *separates* if max ρ_L over usable X arms ≤ ρ_L(H1b@a₂) − 0.3. With m_L the midpoint
  of ρ_L(H1b@a₂) and that maximum, the pilot's drop *survives* T1L if ρ_L,pilot ≥ max(0.5,
  m_L + 0.05), *does not survive* if ρ_L,pilot ≤ m_L − 0.05, else undecided.
- **T1p.** Informative if ρ_p ≤ 0.3 on every usable K and X arm (incompleteness of the tested kinds
  is not absorbed by phase-only gains). Then the pilot's drop *survives* T1p if ρ_p,pilot ≥ 0.5;
  otherwise it is amplitude-like and T1p does not decide (amplitude gain errors and incompleteness
  both remain). H1bA's ρ_p is reported to show how a pure-amplitude gain error reads.
- **Reading.** **Gains more likely**: valid, separating T1L survived and informative T1p survived.
  **Short-spacing cause more likely** (incompleteness on short spacings, or non-closing errors on
  short baselines, which T1L also leaves): separating T1L not survived. Otherwise **undecided**.

## 8. Joint reading and what it means for #13 and #6 (frozen)

| item 1 | item 5 | 3a | #13 (imaging floor) | #6 (self-calibration) |
| --- | --- | --- | --- | --- |
| gain-like | gains more likely | exist | **H1 attributed, share 0.854** (raw T1 drop; floor-2's rule: two independent discriminators agree and the size exists) | DI self-calibration on 5-min steady gains is the expected fix; the floor-2 pilot T1 floor (412 µJy before) is the target to reproduce with `rang-core selfcal` |
| gain-like or not discriminating | gains more likely | partial | H1 favoured, upper bound 0.854, not attributed | self-cal likely helps by about the share 3a carries |
| incompleteness-like or not discriminating | short-spacing cause | any | **H9 favoured** (flux missing on short spacings); H1's bound unchanged, not attributed | #6's self-cal against this model would absorb missing flux into gains; the next step is a deeper or multiscale model (8.6 item 2), not #6 |
| any disagreement other than the above | | | H1 and H9 stay unresolved, shared; the disagreement is reported | no change |

The issue's done-criterion (a measured share per cause) is met only by the first row.

## 9. Limits (stated before the run)

- The simulated tests are given the true model, less only the withheld part; the pilot's model was
  CLEANed from the same data and may have absorbed part of any error. That is the same limit as
  imaging-floor's.
- One noise seed; the gain draws are imaging-floor's (seed 1312). One realisation per incomplete
  kind; the X arms' shapes are two widths of one recipe and one halo, not a fit to the bowl.
- T1L leaves non-closing errors on short baselines unabsorbed, as it leaves incompleteness; it does
  not tell those two apart (imaging-floor's T2 bound, 0.055 after T1, stands for H2).

## 10. Runs

Order: R0's prep and skies, then the arms, then the pilot (its R0 check first, then the new
tests), then G3 and its controls. A smoke run, if any, uses a simulated arm on a row subset only and
is declared here; its numbers are not results.

**Smoke run, declared (2026-11-16 21:09-21:12, before the full run):** `floor2_tests.py smoke
--rows-limit 6000`, arms C, H1b@1, K10@1, XS2@1 only, under `--slots 2 --mem 6`, 230 s. It checked
the code paths (facet sign (1, −1) at 3.7e-6, facet sums 3.9e-6, the gauge, the publisher's gain
statistics); its numbers are not results and its directory is deleted. No rule or threshold
changed after it. (This paragraph was committed with the results in `f8077e6`; the pre-run record
of the smoke run is the message of `3d9bfcb`, pushed before the full run started.)

Every command under the main checkout's `tools/heavy_lock.py run --slots N --mem G`, wall-timed,
rows in [tool-timings.md](tool-timings.md).

**Clarification, 2026-11-16, after the run (no consequence):** the script ran all the pilot's
tests in one call and evaluated gate R0 only in the `summary` stage, not before the new tests as
this section says. R0 passed (11.1), so no number was read under a failed gate.

## 11. Results

One run, 2026-11-16 21:13-21:45 on the workstation (heavy lock `--slots 6 --mem 16`, normal
priority, `RAYON_NUM_THREADS=6`): 1,635 s compute, 1,925 s with the queue. Archive:
[results/floor-2/](results/floor-2/) (`summary.json`, `pilot.json`, every arm's floors and its T1,
T1p and T1L gains, `run.log`). Raw: `D:\rang\outputs\floor-2-20261116`; the prep and the sky
predictions (11.4 GB) were deleted after the run.

### 11.1 Gate R0: pass

- prep: `nrow` 823,500, `active` 19,133,875; `noise_c` and `gridding_weight_sum` bit-equal to the archive.
- pilot: F(none) 1,073.42, F(T1) 411.91, F(T4) 1,060.62, F(T8) 1,050.52 µJy, each 1.000000 × the archive.
- C@1 44.09 µJy. H1b@5.616: F ratio 1.0000, drops equal to 1e-6. K10@1 (= M): F ratio 1.000001,
  D_T1 / D_T4 / D_T8 = 0.532 / 0.494 / 0.491, as archived.
- Facet sums against full predictions: 6.9e-6 relative or less (sign (1, −1)).

### 11.2 The matrix

Drops are fractions of each arm's own excess power, at a₂ (P ≈ P_pilot), from `results/floor-2/summary.json`.

| arm | a₂ (× a₁) | D_T1 | D_T1p | D_T1L | D_T4 | D_T8 | R |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **pilot** | – | **0.854** | **0.828** | **0.827** | 0.024 | 0.042 | **0.049** |
| H1b | 5.616 | 1.000 | 0.663 | 1.000 | 0.013 | 0.019 | 0.019 |
| H1bA | 9.688 | 1.000 | 0.000 | 1.000 | 0.020 | 0.023 | 0.023 |
| H1bP | 6.862 | 1.000 | 1.000 | 1.000 | 0.008 | 0.014 | 0.014 |
| K1 (1.64 Jy missing at a₁) | 5.59 | 0.178 | 0.104 | −0.019 | 0.071 | 0.075 | 0.42 |
| K3 (7.74 Jy) | 2.376 | 0.315 | 0.043 | −0.039 | 0.251 | 0.250 | 0.80 |
| K10 (27.4 Jy) | 0.731 | 0.531 | 0.008 | 0.122 | 0.494 | 0.491 | 0.93 |
| XS2 (1 Jy at a₁) | 25.464 | 0.837 | 0.000 | 0.149 | 0.747 | 0.741 | 0.89 |
| XS4 | 36.909 | 0.634 | 0.000 | 0.000 | 0.450 | 0.455 | 0.72 |
| XG4 | 17.64 | 0.182 | 0.015 | 0.000 | 0.139 | 0.140 | 0.77 |
| MIX (P = 1.19 P_pilot) | k_H 3.97, k_X 18.0 | 0.932 | 0.325 | 0.630 | 0.339 | 0.339 | 0.36 |

Every arm is usable (P ≥ 0.1 P_pilot, D_T1 ≥ 0.1). On the pure gain arms each T1 variant removes
what it should: T1L 1.000 on all three; T1p 1.000 on H1bP, 0.000 on H1bA and 0.663 on H1b (its
phase share). Every antenna keeps at least 59 % of its natural weight above 400 m.

### 11.3 Item 1: gain-like (frozen)

R_G⁺ = 0.044. Every incomplete kind separates: R⁻ runs from 0.28 (K1) to 0.86 (K10), all at least
2 R_G⁺ = 0.087. The pilot's R⁺ = 0.075 lies below every τ_j (0.111 for K1, 0.161-0.194 for the
rest). The discriminator is **valid** and the pilot is **unlike every kind**, so item 1 reads
**gain-like**. The missing-extended arms, the case 8.4 left open, drive the facet-scale fits about
as hard as M does (R 0.72-0.89). MIX lands at R = 0.36; the pilot sits much closer to the pure gain
arms.

### 11.4 Item 3: the steady errors exist, and antenna 1 is the worst (frozen)

- **3a: exist.** P(G3) = 0.863 P_pilot (≥ 0.5). Controls: G3K10 0.396 and G3XS2 0.292, both below
  0.5 P(G3) = 0.431, so 3a separates. The pilot's steady T1 gains after the gauge: σ_a = 1.14 %,
  σ_φ = 4.84°, variable part 1.46 % per 5 min, flux scale 1.007. Against H1b's 5.6 %, 5.6°, the
  pilot's errors are **phase errors of the size needed, with amplitude errors five times smaller**.
  On G3, T1p removes 0.984: the steady error is nearly all phase.
- **3b: "like gain errors"** by the frozen branch: neither the pilot (ρ(e_p, s_p) = 0.22, p = 0.09)
  nor H1b (−0.10) is core-concentrated. But only XS4 (0.64) and XG4 (0.80) are core-concentrated;
  K1, K3, K10 and XS2 are not. So this statistic separates the pilot only from the two widest X arms.
- **3c: no association** with the publisher's gain. e_p against its amplitude variability gives
  ρ = −0.18 (p 0.18), phase variability 0.07 (0.61), mean amplitude 0.26 (0.044, above 0.002) and
  XX/YY ratio 0.08 (0.56). The gain-flag fraction is constant over the subset's antennas, so its ρ
  is undefined (the script's p for it is an artefact of the NaN); it is read as not associated.
- **3d: antenna 1 is among the worst: yes, rank 1 of 60** (chance of rank ≤ 6: 0.10). Next come
  25, 27, 22, 17 and 11. In the spurious gains of K10 and XS2 it ranks 21 and 22, in H1b's draws 48.

### 11.5 Item 5: undecided (frozen)

- Both solvers are valid (ρ_L(H1b) = 1.000, ρ_p(H1bP) = 1.000).
- **T1L separates** (max ρ_L over the X arms is 0.178, below 0.70), and the pilot **survives** it:
  ρ_L = 0.968 against m_L + 0.05 = 0.639. The pilot's T1 drop is found on baselines over 400 m and
  carries over to the short ones; the tested short-spacing kinds give ρ_L ≤ 0.23.
- **T1p is void.** It is informative only if ρ_p ≤ 0.3 on every K and X arm, and K1 gives 0.583
  (K3 0.136, K10 0.015, the X arms ≤ 0.085). Faint flux missing at the 1 mJy level shifts the
  phases that T1 fits. The pilot's ρ_p is 0.970.
- Reading: **undecided**. The "gains more likely" branch needs both tests to survive and T1p to be
  informative.

### 11.6 Joint reading (section 8): row 4

Item 1 is gain-like, item 5 undecided, 3a exist. No condition of rows 1-3 holds, so **H1 and H9
stay unresolved and shared, and H1's bound stays 0.854**. #13's done-criterion is still not met.
For #6 the frozen table says no change.

## 12. Post hoc reading (not a verdict)

- T1p is void because of one arm, K1, whose own T1 drop is only 0.178 (its T1p drop 0.104). On the
  pilot T1p removes 0.828 of the excess, against at most 0.104 on any incomplete arm at floor
  level. A rule on the T1p drop itself, rather than on ρ_p, would have passed. That rule was not
  frozen, so it is not used.
- Taken together: the pilot's T1 drop is found from long baselines alone (0.827) and by phase alone
  (0.828); the facet-scale fits leave it alone; the injected steady phases reproduce 0.86 of the
  floor, against 0.29-0.40 for incompleteness's spurious gains. Every kind of incompleteness tested
  fails at least two of these. The lead is **steady per-antenna phase errors of about 5° rms over
  the hour (1.1 % amplitude), worst on antenna 1**, left by the publisher's QuartiCal net gain and
  unrelated to that gain's own per-antenna variability. Where they come from (the publisher's
solution, or a model CLEANed from the same data) is not tested here.
- Remaining limits: one gain realisation and one noise seed; the pilot's model was CLEANed from the
  same data; T1L does not separate gain errors from non-closing errors on long baselines.

- **Per-antenna distribution (descriptive, post hoc,** from `summary.json` `antennas`): antenna 1's
  steady error is −14.3° and +1.2 % amplitude; the next are 25 (+12.8°), 27 (+9.7°), 22 (−9.2°),
  17 (−9.0°), 11 (+8.1°). σ_φ is 4.84° over all 60, 4.51° without antenna 1 and 3.63° without the
  worst six; 17 antennas exceed 5°, the median |φ| is 3.2°. So the error is array-wide with a tail,
  not one antenna.
- **Overlap with heldout's bad baselines (descriptive, post hoc):** in set B's 145 flagged
  baselines (`badbaselines.json`) the antennas appearing most are 1 (30 baselines), 25 (26),
  27 (17), 38 (16), 30 (12), 11 (11). Five of these six (1, 25, 27, 38, 11) are in T1's worst ten
  here. Set B's flags were chosen by misfit against a model, so this is an overlap, not a test.

## 13. What it means for #13 and #6

- **#13:** frozen, unresolved (row 4). Post hoc, it can be decided by a frozen follow-up with a T1p
  rule on absolute drops, or more directly by a 5-min phase-only self-calibration of the pilot
  (`rang-core selfcal`), imaged and scored with imaging-floor's metric. The floor after T1 is
  412 µJy (9 × thermal on the subset); nothing here explains that remainder.
- **#6:** the case for a phase self-calibration round on the pilot is now strong. A 5-min,
  frequency-independent phase solve against the 3 mJy model removes 0.83 of the excess (1,073 →
  447 µJy in the subset's exact residual). That is an expected effect, not a measured self-cal run.
  Antenna 1's worst-case misfit in heldout §5 is consistent with its steady phase error here
  (−14°); the link was not tested.

## 14. For the coordinator

- Branch `floor-2`: protocol `6d00242` (frozen and pushed before the run), script
  `examples/floor2_tests.py` (`3d9bfcb`), results in this note and `results/floor-2/`. No library
  code changed.
- Open decision: whether to run the direct test of section 13 (phase-only self-cal of the pilot,
  scored with imaging-floor's metric) as a frozen floor-3, which would settle H1 if it reproduces
  the 0.83 drop.
- Scratch on D: deleted (1.1 MB left in `D:\rang\outputs\floor-2-20261116`).
