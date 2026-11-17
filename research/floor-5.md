# Rang: floor-5, what is left of the pilot's floor after one phase self-calibration round (issue #13)

Status, 2026-11-17: **proposed, frozen before any run.** Sections 1-8 are the frozen protocol;
results go in section 10, clarifications in section 9 (dated, before the numbers they affect, or
labelled post hoc). Coordinator's brief (owner delegated), 2026-11-17, after floor-4.
Host: **nash** ([nash-host.md](nash-host.md)): every job through the main checkout's heavy lock,
`nice -n 19 ionice -c3`, honest `--slots` and `--mem`. Script: `examples/floor5_tests.py`
(committed after this note; it imports `examples/floor_tests.py`, `floor2_tests.py` and
`floor3_score.py` unchanged). Outputs: `~/rang-data/outputs/floor-5-20261117` on nash.
Archive: `research/results/floor-5/`.

## 1. Question and priors

After one phase-only round of `rang-core selfcal` (Sp, 300 s, `freqint: inf`) the pilot's subset
floor is **379.26 µJy, 8.6 × thermal** ([floor-3.md](floor-3.md) section 9, reproduced bit for bit
on nash by floor-4's G1). floor-4 (branch `floor-4` at `6ab0446`, measured, not merged) attributed
the floor before self-calibration to steady antenna phases under imaging-floor's full criterion
(share D_T1p 0.83), and found the steady XX − YY phase real (r 0.999) but invisible to Stokes I
(ΔD −0.013). Neither explains the 379 µJy. **Which cause, if any, carries the excess left after
the phase round?**

**The reference is rebased.** Every share in this note is a fraction of the excess left after Sp:
P_ref = F_ref² − T², F_ref = F(Sp-corrected data, final model) = 379.26 µJy, T = 44.09 µJy, so
P_ref = 1.419e-7 Jy² = **0.1234 P_pilot**. A verdict of imaging-floor made against P_pilot does
not carry over. The rejection clause "P_X(a_max) < 0.05 P_pilot" becomes 0.05 P_ref, 8 × lower:

| arm (imaging-floor 8.2) | P(a_max)/P_pilot | / P_ref | status here |
| --- | ---: | ---: | --- |
| H1a, gains random per 8 s | 0.021 | 0.17 | **reopened** (T_Af, arm H1a) |
| H2, 30 bad short baselines | 0.16 | 1.30 | **reopened** (T_B, arm H2) |
| H8a, α = −0.7 → −1.0 under one flat term | 0.050 | 0.41 | **reopened** (T8, arm H8a; GeMClean arm S) |
| H8b, H8c, α scatter | 0.028, 0.025 | 0.23, 0.20 | reopened in principle; tested through T8 and arm S only (no own arm) |
| H3, DD gains outside the central ±25.6′ | 0.0005 | 0.004 | stays rejected as injected; the untested form (differential across the central source) is new arm H3c |
| H4a, H4b, beam rotation and chromaticity | 0.0000, 0.0002 | 0.000, 0.002 | stays rejected as injected |
| H6, sub-threshold RFI | 0.0000 | 0.000 | stays rejected as injected |
| H7, confusion (a₁; σ_c² 1.2e-4) | 0.0010 | 0.008 (σ_c² 0.001) | stays rejected under its own rule (a₁ and σ_c² both < 0.05 P_ref) |
| H5, H10, w-term and smearing | rescoring | – | rescored on the new state (T5, T10) |

Priors, all read before this freeze (none is an outcome of a test below):

| quantity | value | source |
| --- | --- | --- |
| F_B, F_Fix, F_Fin of Sp on the pilot (subset) | 1,073.42, 474.83, 379.26 µJy | floor-3 9.1; floor-4 G1 on nash, bit-equal |
| full-data residual of the final 3 mJy image | peak 2.999 mJy, MAD σ 0.240 mJy, 26,357 components, 85.89 Jy, 3 major cycles, 316 s at `-j 8` | G1 `final/image-report.json` on nash |
| imaging-floor's cumulative chain before self-cal (fraction of P_pilot) | T1 0.854; + T2 0.055; + T8 0.020; + T3 0.004; + T4 0.001; + T6 0.015 | imaging-floor 8.3 |
| T2's absorption of incompleteness | 0.32 on M (truth less pixels < 10 mJy) | imaging-floor 8.3 |
| T8 on the pilot alone, on M, on H8a | 0.042, 0.49, 1.00 (P_pilot units) | imaging-floor 8.3 |
| T1 against T1p on the pilot (fixed 3 mJy model) | 0.854 against 0.828: amplitude freedom adds 0.026 P_pilot ≈ 0.21 P_ref | floor-2, floor-4 |
| amplitude self-cal, held out (selfcal-defaults, `origin/floor-4`, `summary.json` on nash) | D_ho of P_0: P1@300 0.876, P1A@300 0.913, P2@300 0.908, P2A@300 0.914, P3A@300 0.915; Sa adds 0.005-0.007 at a fixed number of phase rounds; a second Sp round adds 0.03; solint 60-600 s moves D_ho by ≤ 0.004; gap D_in − D_ho ≈ −0.002 everywhere | selfcal-defaults, before this freeze |
| heldout: the 1 mJy model (no mask, before self-cal) | F 0.5995 against 1.0568 mJy; it holds −35.5 Jy | heldout §6 |
| E2 before self-cal | 88 % of the floor's power at \|uv\| < 1,390 λ (3.9 % of the gridding weight) | imaging-floor 8.5 |

Read as priors: amplitude gains are a small part of what is left (the held-out Sa gain is
0.005-0.007 P_0, about 0.05 P_ref). A better model is worth more (the second Sp round, 0.03 P_0,
about 0.25 P_ref). CLEAN stopped at 12.5 σ of its own residual, so the model is shallow. Before
self-cal the per-baseline fit was the largest increment after T1, but it absorbs incompleteness.
**The central question is per-baseline errors (H2) against model incompleteness and depth (H9).**
Amplitude (H1r), random gains (H1a), spectral structure (H8) and DD errors across the central
source (H3c) are tested beside them.

## 2. Inputs and provenance

- `cal2.ms`, copied again from the workstation (`D:\rang\outputs\20261103-gemclean-heldout\real`)
  to `~/rang-data/outputs/floor-5-20261117/inputs/20261103-gemclean-heldout/real/` (floor-4 had
  deleted its nash copy). The copy is checked by a sorted per-file SHA-256 manifest made on both
  sides, which must match file for file. The three FITS (both 3 mJy models, the source mask) are
  copied from floor-4's nash folder and must match floor-2's SHA-256 (floor-2 section 2).
- G1's run directory (round-1 Sp store, round-1 and final models, reports), copied from
  `~/rang-data/outputs/floor-4-20261117/g1` to `inputs/floor-4-20261117/g1`. The stage is rerun
  here (gate G1), and this note's numbers use the rerun's products.
- rang-core, the extension and GeMClean: nash's main checkout build at the run (commit and
  GeMClean SHA-256 recorded). The script runs from the `floor-5` worktree.

## 3. The state and the metric (frozen)

**State S1.** The pilot's DATA on imaging-floor's 32 subset channels (4, 12, …, 252), corrected
per hand in numpy by G1's round-1 Sp store (V / (g_p g_q*) for XX and YY, cells with an invalid
gain flagged), then made Stokes I by floor_tests.prep's rule. This is floor-4's numpy apply,
re-implemented in `floor5_tests.py`. **Model m1**: G1's final 3 mJy model. **State S0**: DATA
uncorrected, with the round-1 model m0.

**Floor F** as imaging-floor section 2 (exact residual, Briggs 0.5 recomputed on the subset,
4096 × 3″, inner two-thirds outside set A's mask, ε 1e-5). Excess P = F² − T², T = 44.09 µJy.
Shares are fractions of P_ref (pilot) or of the arm's own excess (simulations). Tests marked
"| A" run on data already corrected by T_A, and are scored by their increment
D = (P_A − P_A+X) / P_ref (imaging-floor clarification 1). Drops are quoted to ±0.02.

## 4. Hypotheses, arms and tests (frozen)

Two families. **Family I** is imaging-floor's method, fixed-model fits in numpy with specificity
from simulated arms. **Family II** re-images the corrected data with GeMClean. It needs no
simulation, but has its own control (section 6.2).

### 4.1 Family I: tests on S1 against m1

| test | what | own arm |
| --- | --- | --- |
| T_A | per-antenna complex gains, frequency-independent, 5-min bins, StefCal against the model (floor-2's `stefcal`, 30 iterations) | H1bA |
| T_Af | the same per 8 s dump | H1a |
| T_B \| A | per-baseline steady complex scale (floor_tests `t2`) after T_A | H2 |
| T_B | the same alone (descriptive) | – |
| T8 | per 4 × 4 facet, per channel, complex scale (floor_tests `t8`) | H8a |
| T_D \| A | per-antenna steady complex gains per **cluster**, after T_A. The clusters are the four central 4 × 4 facets, each holding one quadrant of the central source (the phase centre sits on their common corner), and the other twelve as one. Alternating StefCal, 2 sweeps × 8 iterations, as floor_tests `t3` but over every cluster | H3c |
| T5, T10 | rescore S1 against m1 predicted with `flip_w` toggled, without w-correction, at ε 1e-7, and smeared over ±Δν/4 | (rescoring) |

T_Ap (phase only, 5 min) is computed beside T_A as a descriptive split of T_A into phase and
amplitude.

### 4.2 Simulated arms (imaging-floor sections 3 and 4, rebased)

Data = truth sky (set B's 3 mJy model) with the effect, + noise seed 1301. Tests are given the
truth's 4 × 4 facets, or the arm's stated model. a₁ is the amplitude stated below.
**a₂ = a₁ √(P_ref / P(a₁))**, capped at 50 a₁, so an arm at a₂ makes a floor the size of what is
left on the pilot. a_max is the largest plausible amplitude. Every arm runs at a₁, a₂ and a_max
(where it has one).

| arm | effect (built by) | a₁ | a_max |
| --- | --- | --- | --- |
| C | none (noise only; T) | – | – |
| H1a | per antenna, per 8 s, complex gain σ 1 %, 1° (`floor_tests.make_arm`) | 1 %, 1° | 5 %, 5° |
| H1bA | steady per-antenna amplitude σ 1 %, phase 0 (`floor2_tests.make`) | 1 % | 5 % |
| H2 | 30 baselines < 400 m, ×(1 + ε), \|ε\| 2 %, steady (`make_arm`) | 2 % | 20 % |
| H8a | truth × (ν/ν₀)^α renormalised, model flat (`make_arm`) | α = −0.7 | α = −1.0 |
| H3c | steady per-antenna complex gains on each of the four central 4 × 4 facets, σ 2 %, 2°, seed 1503; the other twelve take none (new) | 2 %, 2° | 10 %, 10° |
| K1, K3 | the truth's pixels under 1, 3 mJy missing from the model, × k (`floor2_tests.make`) | k = 1 | – |
| XS2, XS4, XG4 | 1 Jy × k of extended emission missing from the model (`floor2_tests.make`) | k = 1 | – |

K1, K3, XS2, XS4 and XG4 are H9's arms (model incompleteness of five kinds). Family II tests H9
directly; in Family I they only measure how much each fit absorbs incompleteness. Their a₂ also
scales to P_ref.

Plausibility of H3c's a_max: a pointing error δ moves the gain at offset r by about
8 ln 2 · r δ / θ_FWHM². With θ_FWHM ≈ 96′ at 1043 MHz, r = 10′ and δ = 1′, that is 0.6 %. So 10 %
is generous.

### 4.3 Family II: re-imaging with GeMClean

GeMClean runs on G1's rerun MS (CORRECTED_DATA = S1 on all 256 channels). The command is G1's
final-image command (`-size 4096 4096 -scale 3asec -weight briggs 0.5 -gain 0.1 -nmiter 1000
-j 8 -wgridder-accuracy 1e-06 -data-column CORRECTED_DATA -field 0 -no-update-model-required`).
Each arm changes only what the table says, and `-niter` is 10,000,000 in every arm (the cap must
not bind; the stop reason is recorded). The **clean mask** is set A's source mask
(`images/source-mask.fits`, exactly the pixels F excludes), so a masked arm puts no component
where F is measured.

| arm | change | role |
| --- | --- | --- |
| R3 | none (`-niter 1000000` as G1) | gate GM: reproduces m1 |
| Dm1 | `-fits-mask` mask, `-threshold 0.001` | depth, masked |
| **Dm03** | `-fits-mask` mask, `-threshold 0.0003` | **H9's test** |
| Dms03 | `-fits-mask` mask, `-multiscale`, `-threshold 0.0003` | depth, multiscale (secondary) |
| Du1 | `-threshold 0.001`, no mask | comparator: unmasked depth |
| S | `-channels-out 8 -join-channels -fit-spectral-pol 2`, 3 mJy, no mask | spectral structure (H8), direct |
| C0 | Dm03 on **DATA** (state S0) | control of Dm03 (section 6.2) |

Each model is scored on the subset: F of S1 (C0: of S0) against the model predicted on the
32 channels. For S each subset channel takes the model of its output channel (`-0000` … `-0007`;
256 / 8 = 32 MS channels each). D_X = (P_ref − P_X) / P_ref (C0: (P_B − P_C0) / P_B).
Recorded per arm: components, major cycles, stop reason, model flux, model flux outside the
mask, negative flux, residual MAD and wall time.

**The depth × baseline 2 × 2.** T_A then T_B | A are run on S1 against m1 and against Dm03's
model. ΔP_B(m) is the absolute power T_B | A removes. **ρ_B = ΔP_B(Dm03) / ΔP_B(m1)** says
whether the per-baseline increment survives a deeper model.

### 4.4 Facet-split and shape statistics (descriptive, provisional)

On the residual images of S1 − m1 and of every simulated arm at a₂ (no correction):
E1 (imaging-floor's radial profile), E2 (short-uv power fraction), and **E5**, the rms in each of
the sixteen 4 × 4 facets over F's pixels, against the facet's model flux. A provisional
assignment counts only if the arms are separated by it, as in imaging-floor section 6: the pilot
goes to the arm nearest in (log E1, E2, log E5 profile), and that counts only if every arm's
nearest arm is itself. E1, E2 and E5 never override section 6.

## 5. Gates (frozen, before any new number is read)

- **Copy**: the SHA-256 manifest of `cal2.ms` matches the workstation's, file for file; the three
  FITS match floor-2's hashes.
- **R0**: `floor_tests.prep` gives `nrow` and `active` equal, and `noise_c` and
  `gridding_weight_sum` within 1e-6 relative of `results/imaging-floor/prep-meta.json`.
- **G0**: DATA against the archived pilot model, F within 0.1 % of 1,073.42 µJy.
- **G1**: floor-3's arm P (`results/floor-3/p1.yaml`, fresh four-correlation copy, `floor3_score`
  stages) rerun: F_B, F_Fix and F_Fin within 1e-4 relative of 1,073.416, 474.831 and
  379.262 µJy, with health as floor-3 (converged ≥ 0.9, ≤ 5 % flagged, r ≥ 0.7).
- **HB**: the numpy apply of G1's store gives F_Fix within 1e-4 relative of `floor3_score`'s
  (from CORRECTED_DATA), and S1 against m1 gives F_ref within 1e-4 of F_Fin.
- **GS**: C @ 1 within 0.5 % of 44.09 µJy; H2 @ 25.144 and H8a @ 6.38 give imaging-floor's
  F(none) within 0.5 % (the arms are rebuilt identically).
- **GM**: R3's model is pixel-identical to G1's final model. If it is not, the difference is
  reported, and Family II's drops are taken against R3's own score in place of F_ref.

A failing gate voids what depends on it. It is reported and never read as a refutation.

## 6. Decision rules (frozen)

### 6.1 Family I: imaging-floor's attribution standard, rebased

This is imaging-floor section 5 with P_ref in place of P_pilot. Tests are run on every arm at
a₂. An arm is **usable** for a test if P(a₂) ≥ 0.1 P_ref (and, for "| A" tests, the excess is
defined after T_A). For hypothesis X with test T_X and pilot drop D_X:

- **Specific**: own arm D ≥ 0.7 and every other usable arm (the five H9 arms included) D ≤ 0.3.
- **Attributed, share D_X**, if T_X is specific, D_X ≥ 0.10 and P_X(a_max) ≥ 0.5 D_X P_ref.
- **Rejected** if T_X is specific and D_X < 0.05, or if P_X(a_max) < 0.05 P_ref.
- **Unresolved** otherwise: 0.05 ≤ D_X < 0.10; a test that is not specific (D_X is then an upper
  bound shared with the arms it fires on, named); or a pilot drop larger than any plausible
  amplitude carries (reported).
- **H5, H10**: rejected if no rescoring alternative lowers P by 0.05 P_ref and ε 1e-7 changes F by
  less than 2 %; otherwise attributed with the best alternative's drop.

Hypotheses: **H1r** (residual antenna amplitude, steady) ↔ T_A / H1bA; **H1a** ↔ T_Af / H1a;
**H2** ↔ T_B | A / H2; **H8** ↔ T8 / H8a; **H3c** ↔ T_D | A / H3c.

**H2 and the 2 × 2.** If T_B | A is not specific on an H9 arm, ρ_B decides how H2 reads:

- ρ_B ≥ 0.7: **H2 supported**: the per-baseline increment survives a deeper model, upper bound
  ΔP_B(Dm03)/P_ref;
- ρ_B ≤ 0.3: **H2 absorbed**: the increment was missing model flux, which goes to H9;
- partial otherwise.

ρ_B is read only if Dm03 passes GM and C0's control (section 6.2). Otherwise it is reported, not
read.

### 6.2 Family II: H9 (depth and model incompleteness) and H8 directly

**The control.** In S0 most of the excess is attributed to antenna phases (floor-4), so S0 is
S1 plus a known gain error. A depth test that is blind to gain artefacts removes about the same
absolute power from both. Define **κ = (ΔP(C0) − ΔP(Dm03)) / (P_B − P_ref)**, with
ΔP(C0) = P_B − P_C0 and ΔP(Dm03) = P_ref − P_Dm03. κ is the fraction of the gain-caused excess
that the deep masked CLEAN removes. **Gain-blind** if κ ≤ 0.3 (imaging-floor's cross-arm
bound).

**H9 (depth)**, under **floor-5's depth standard** (a direct intervention with a gain control;
not imaging-floor's full criterion, which needs a simulated own arm that GeMClean cannot run here):

- **attributed, share D_Dm03**, if D_Dm03 ≥ 0.10 and κ ≤ 0.3;
- **rejected** if D_Dm03 < 0.05: cleaning deeper, inside the source, does not lower the floor;
- **unresolved** otherwise: 0.05 ≤ D_Dm03 < 0.10, or κ > 0.3 (deep CLEAN absorbs gain
  artefacts; D_Dm03 is then an upper bound).

Reported beside it, without changing the verdict:

- Dm1, which gives the trend with threshold;
- Dms03, the multiscale arm. If D_Dms03 ≥ D_Dm03 + 0.10, the note **"extended emission CLEAN
  misses"** is added;
- Du1 against Dm1. If D_Du1 ≥ D_Dm1 + 0.10, the note **"unmasked depth cleans artefacts"** is
  added. That drop is never a share.

**H8 (spectral) directly.** Arm S: D_S ≥ 0.10 means **spectral modelling supported**, share
D_S, under the same direct standard (no control). D_S < 0.05 means **not supported as tested**.
Unresolved otherwise. The H8 verdict is section 6.1's T8 reading. Arm S adds a line: a specific
T8 with D_S < 0.05, or the reverse, is reported as a conflict.

### 6.3 Joint reading for #13

Σ is the sum of the attributed shares (Family I under 6.1, H9 under 6.2, S if supported). The
tests are not orthogonal, so Σ is not a decomposition, and the remainder 1 − Σ is reported
either way.

| outcome | reading for #13 | next |
| --- | --- | --- |
| **J1**: Σ ≥ 0.5 | the 379 µJy is mainly explained by the attributed causes, named with shares | the fix in practice for the largest (a selfcal or imaging default), on a held-out channel split first |
| **J2**: 0 < Σ < 0.5 | partly explained; the remainder is unattributed | a protocol for the largest unresolved bound |
| **J3**: nothing attributed, something unresolved | bounds only, each named with the arms it is shared with | the 2 × 2's reading picks between H2 and H9 for the next protocol |
| **J4**: every tested hypothesis rejected | the remainder is none of the tested causes. Named as untested: DD errors varying in time, leakage through the absent cross hands, pointing per antenna, non-closing errors varying in time | an observer's question (correlator, cross hands) |
| **J5**: a gate fails | void, reported | rerun after the fix |

## 7. Runs and cost

On nash: copy and manifest; R0 and G0 (`floor5_tests.py gates`, 4 slots); G1
(`floor3_score.py` copy, `rang-core selfcal`, score; 8 slots, `RAYON_NUM_THREADS=8`). In
parallel with G1: Family I's prep and skies, then the arms, each chain a₁ → a₂ → a_max in its
own process (4 slots, `RAYON_NUM_THREADS=4`, about 10 GB each), up to six at once. After G1:
Family II's seven GeMClean runs (`-j 8`, 8 slots, 16-20 GB each), up to three at once, then
their scores and the 2 × 2. From 21:30 SAST no more than 16 slots are booked in all. Every heavy
command is wall-timed with a row in [tool-timings.md](tool-timings.md), **host nash**. A smoke
run of the script, if needed, uses 6,000 rows of simulated arms only. It is declared in section 9
and gives no results. No smoke run touches the pilot's S1 scores.

## 8. What this does not test

The cross hands (XY, YX) are absent from `cal2.ms`, so leakage, an X−Y phase seen through them,
and Stokes I contamination by polarisation remain untested. Errors varying in time other than
H1a are not tested: DD per 5 min, and non-closing errors with a time pattern. Neither is pointing
per antenna as such. One data set, one noise seed, one field.

## 9. Clarifications

None yet.

## 10. Results

Not run yet.
