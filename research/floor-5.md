# Rang: floor-5, what is left of the pilot's floor after one phase self-calibration round (issue #13)

Status, 2026-11-17: **measured; joint outcome J2** (Σ 0.41 of P_ref: H9 depth 0.22, spectral
modelling 0.19; Family I unresolved throughout; section 10). Frozen before any run: sections 1-8 are the frozen protocol;
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

**1, 2026-11-17 11:00 SAST, before any run or number.**

- **Copy.** The workstation's uplink to nash runs at about 0.75 MB/s, so `table.f4_TSM1` is not
  copied. It holds `MODEL_DATA` (TiledModel, 3.37 GB), a column no stage reads: `floor_tests.prep`,
  `floor3_score` copy and `floor5_tests` read DATA, FLAG, WEIGHT_SPECTRUM, WEIGHT, SIGMA and the
  row columns. On nash it is a sparse file of the same size. The manifest gate compares the other
  66 files; `table.f4_TSM1` is listed as excluded. DATA and WEIGHT_SPECTRUM go as 64 MiB blocks
  (gzip, eight streams) and are checked by the same manifest.
- **Order.** Family I's pilot stage and arms use G1's round-1 store and final model as copied
  from floor-4's nash folder (`inputs/floor-4-20261117/g1`), so they can run while G1 reruns.
  P_ref, and with it every a₂, comes from that copy. The G1 rerun must reproduce the copied store
  bit for bit (gains and flags) and the final model pixel for pixel; the summary checks both. If
  either differs, Family I is rescored from the rerun's products, and that is reported.
- **Smoke.** None ran. A 6,000-row smoke queued on the workstation's lock was stopped before it
  started, because the workstation was held by an exclusive timing run.
- **Store-equality check.** Added to the script's summary, before any output: `g1_rerun_equal`.

**2, 2026-11-17 11:30 SAST, written while the first arm ran and before any arm result, G1 rerun, GeMClean arm or score was read; after gates R0, G0
and HB (their numbers are in section 10).**

- **Pinned build, in place of section 2's "nash's main checkout build at the run".** The coordinator
  fast-forwards nash's main checkout during the run, so one stage could run different code from
  the next. Every stage runs from the `floor-5` worktree on nash: its Python (`python/rang` at
  `6de8ecb`), with the extension copied from main's build into the worktree
  (`python/rang/_core.abi3.so`, SHA-256 `ce12e7d2…c2bc884`, built 2026-11-16 22:39 SAST from main
  `9d1cf8fc`; main's Rust has changed since, so this is not main's source at `41bc3efb`). The
  interpreter is the worktree venv `.venv` (Python 3.14.10), with the same third-party versions as
  main's venv at 11:20 (a pip freeze, compared line for line). GeMClean is this extension's
  (`python -m rang.gemclean`), and `rang-core selfcal` is `python -m rang.core_cli selfcal`.
- **Gates run before the pin.** A first R0/G0 run (11:09-11:11) used main's unpinned code. It was
  set aside (`prep.unpinned-41bc3efb`, `logs/*.unpinned.log`), and R0, G0 and HB were rerun
  pinned. The 11:13 gates ran on main venv's interpreter with `PYTHONPATH` set to the worktree
  (same rang code and extension). Skies, pilot and everything after use the worktree venv.
- **Threads.** Family I stages are capped at 4 threads (Rayon, OpenMP, OpenBLAS), the slots they
  book. The skies stage started before the cap and briefly used about 5.6 cores.

## 10. Results

Measured 2026-11-17 on nash, every stage from the pinned build of clarification 2 (worktree Python
`6de8ecb`, extension `ce12e7d2`). Outputs: `~/rang-data/outputs/floor-5-20261117`. Archive:
[results/floor-5/](results/floor-5/) (`summary.json`, `pilot.json`, `gates.json`, `twobytwo.json`,
every arm's and Family II arm's JSON, GeMClean reports and logs, G1's `score.json`, the stage
scripts, the run logs, SHA-256 of every Family II model). Every run ended rc 0: the 11 Family I
arms (`logs/arms.log`, `logs/arm-*.log`), G1 (`logs/g1.log`), the seven GeMClean arms
(`logs/fam2-*.log`, "end rc 0"; see 10.2 item 8) and the scoring (`logs/post.log`). Section 10.1 is the reading exactly as frozen; section 10.2 holds
everything read after the numbers, labelled post hoc.

### 10.1 The frozen reading

**Gates: all pass.**

| gate | measured | rule | result |
| --- | --- | --- | --- |
| Copy | `cal2.ms` 66 of 66 files equal by SHA-256 (`table.f4_TSM1` excluded, clarification 1); three FITS equal floor-2's | file for file | pass |
| R0 | `nrow`, `active` equal; `noise_c` and `gridding_weight_sum` rel 0.0 | 1e-6 | pass |
| G0 | F 1,073.4156 µJy, ratio 0.999996 | 0.1 % | pass |
| G1 | F_B 1,073.4156, F_Fix 474.8310, F_Fin 379.2621 µJy (rel ≤ 1e-6); converged 1.0, 1.6 % solutions flagged, 0 newly flagged visibilities, phase r 0.989 against floor-2's T1p | 1e-4; ≥ 0.9, ≤ 5 %, ≥ 0.7 | pass |
| G1 rerun equality (clarification 1) | round-1 Sp store gains and flags equal, final model pixel-equal to floor-4's copy | bit for bit | pass, so Family I stands on the copy as run |
| HB | numpy apply: F_Fix rel 0.0; S1 against m1: F_ref 379.2616 µJy, rel −1.5e-6 against F_Fin | 1e-4 | pass |
| GS | C @ 1: 44.0902 µJy (rel −2e-10); H2 @ 25.144 and H8a @ 6.38: rel 5e-8 and 3e-7 against imaging-floor | 0.5 % | pass |
| GM | R3's model pixel-identical to G1's final model (`np.array_equal`; same SHA-256 `330ee81a…`), 26,357 components, 3 major cycles, Threshold, 85.893 Jy; R3 scores F 379.2621 µJy, D −3e-6 | pixel-identical | pass, so Family II's drops are against F_ref |

P_ref = 1.419e-7 Jy² (F_ref 379.26 µJy), 0.1234 P_pilot; P_B = 1.150e-6 Jy².

**Family I (section 6.1).** Pilot drops (fraction of P_ref) and every arm at a₂ (rows: arm, its
P(a₂)/P_ref; columns: tests). Every arm at a₂ is usable (P ≥ 0.1 P_ref). Bold: own arm.

| arm (a₂) | P/P_ref | T_A | T_Af | T_B \| A | T_B | T8 | T_D \| A |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **pilot** | 1 | **0.375** | **0.387** | **0.109** | 0.459 | **0.282** | **0.035** |
| H1bA (3.403) | 1.001 | **1.000** | 1.000 | 0.000 | 1.000 | 0.023 | 0.000 |
| H1a (12.479) | 1.387 | 0.790 | **1.000** | 0.002 | 0.384 | 0.316 | 0.000 |
| H2 (8.831) | 0.996 | 0.194 | 0.195 | **0.803** | 1.000 | 0.016 | 0.139 |
| H8a (2.241) | 1.006 | 0.034 | 0.034 | 0.044 | 0.078 | **1.000** | 0.021 |
| H3c (0.971) | 0.999 | 0.509 | 0.509 | 0.356 | 0.864 | 0.044 | **0.481** |
| K1 (1.963) | 1.000 | 0.179 | 0.179 | 0.498 | 0.671 | 0.075 | 0.098 |
| K3 (0.835) | 1.001 | 0.316 | 0.316 | 0.428 | 0.742 | 0.250 | 0.091 |
| XS2 (8.944) | 0.999 | 0.836 | 0.836 | 0.162 | 0.999 | 0.741 | 0.032 |
| XS4 (12.963) | 0.997 | 0.629 | 0.629 | 0.368 | 0.998 | 0.455 | 0.064 |
| XG4 (6.196) | 0.999 | 0.181 | 0.181 | 0.715 | 0.895 | 0.140 | 0.208 |

(T_Ap, the descriptive phase-only split of T_A: pilot 0.263.) P(a_max)/P_ref: H1bA 2.16, H1a 0.170,
H2 1.28, H8a 0.407, H3c 27.3.

| hypothesis (test) | specific? | fires on (D > 0.3, usable) | frozen verdict |
| --- | --- | --- | --- |
| H1r (T_A) | no | H1a, H3c, K3, XS2, XS4 | **unresolved**, upper bound 0.375 shared with those arms |
| H1a (T_Af) | no | H1bA, H3c, K3, XS2, XS4 | **unresolved**, upper bound 0.387 shared with those arms; also the pilot drop exceeds what H1a's a_max carries (0.170 < 0.5 × 0.387) |
| H2 (T_B \| A) | no | H3c, K1, K3, XG4, XS4 | **unresolved**, upper bound 0.109 shared with those arms; the 2 × 2 reads below |
| H8 (T8) | no | H1a, XS2, XS4 | **unresolved**, upper bound 0.282 shared with those arms |
| H3c (T_D \| A) | no (own arm 0.481 < 0.7) | – | **unresolved**, upper bound 0.035 (not specific, so not rejected although D < 0.05) |
| H5, H10 (T5, T10) | – | – | **rejected**: no alternative lowers P (best ΔP −1.9e-5 P_ref; `flip_w` toggled −0.209, without w-correction −0.110); ε 1e-7 changes F by 4e-6 |

Family I attributes nothing.

**Family II (section 6.2).** F on the subset; D against P_ref (C0: against P_B). Every run stopped
on Threshold; none reached `-niter`.

| arm | F (µJy) | D | ΔP (Jy²) | components | major cycles | model flux (Jy) | negative (Jy) | outside mask (Jy, pixels) | residual MAD (µJy) | wall (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| R3 | 379.26 | −0.000 | −4e-13 | 26,357 | 3 | 85.89 | −0.14 | 0.036, 282 | 240.0 | 327 |
| Dm1 | 345.54 | 0.172 | 2.44e-8 | 48,849 | 4 | 89.09 | −0.35 | 0, 0 | 214.9 | 388 |
| **Dm03** | **334.83** | **0.224** | 3.17e-8 | 110,140 | 5 | 91.46 | −0.71 | 0, 0 | 209.1 | 469 |
| Dms03 | 303.89 | 0.363 | 5.15e-8 | 105,646 | 3 | 96.17 | −7.62 | 3.53, 16,647,036 | 191.1 | 2,236 |
| Du1 | 322.31 | 0.282 | 3.99e-8 | 58,496 | 4 | 88.93 | −1.12 | 0.057, 9,042 | 212.1 | 386 |
| S | 342.64 | 0.186 | 2.64e-8 | 26,982 | 3 | 84.94 (joined) | −1.25 (8 planes) | 0.37, 2,640 (8 planes) | 209.5 | 1,030 |
| C0 (S0) | 1,138.70 | −0.126 (of P_B) | −1.44e-7 | 203,096 | 5 | 104.54 | −1.93 | 0, 0 | 716.2 | 501 |

- κ = (ΔP(C0) − ΔP(Dm03)) / (P_B − P_ref) = (−1.444e-7 − 3.173e-8) / 1.008e-6 = **−0.175 ≤ 0.3: gain-blind.**
- **H9 (depth): attributed under floor-5's depth standard, share 0.224** (D_Dm03 ≥ 0.10, κ ≤ 0.3).
  This is floor-5's direct-intervention standard, not imaging-floor's full criterion.
- Beside it: Dm1 0.172 (the trend with threshold: 1 mJy → 0.3 mJy adds 0.05). Dms03 0.363 ≥ 0.224 +
  0.10, so the note **"extended emission CLEAN misses"** is added. Du1 0.282 ≥ Dm1 0.172 + 0.10,
  so the note **"unmasked depth cleans artefacts"** is added (never a share). Both notes are
  qualified post hoc in 10.2.
- **H8 directly (arm S): D_S 0.186 ≥ 0.10, spectral modelling supported, share 0.186.** The H8
  verdict is T8's: unresolved (not specific). T8 is neither specific with D_S < 0.05 nor rejected
  with D_S ≥ 0.10, so no conflict line.

**The 2 × 2 (section 4.3).** ρ_B is read: Dm03 passes GM (through R3) and C0's control.

| model | F none | F after T_A | F after T_A, T_B \| A | ΔP_A / P_ref | ΔP_B / P_ref |
| --- | ---: | ---: | ---: | ---: | ---: |
| m1 | 379.26 | 300.95 | 273.95 | 0.375 | 0.109 |
| Dm03 | 334.83 | 282.78 | 266.23 | 0.227 | 0.064 |

**ρ_B = 0.586: partial** (between 0.3 and 0.7). H2 stays unresolved (section 6.1).

**Joint outcome (section 6.3): J2.** Σ = 0.224 (H9) + 0.186 (S) = **0.410**, so 0 < Σ < 0.5. The
379 µJy is partly explained. Attributed: model depth inside the source mask (0.224) and spectral
modelling (0.186). The two are not orthogonal, so Σ is not a decomposition. The remainder
1 − Σ = **0.590** is unattributed. Unresolved bounds, each shared with the named arms: T_Af 0.387
(H1bA, H3c, K3, XS2, XS4), T_A 0.375 (H1a, H3c, K3, XS2, XS4), T8 0.282 (H1a, XS2, XS4), T_B | A
0.109 (H3c, K1, K3, XG4, XS4; ρ_B partial), T_D | A 0.035 (own arm 0.481). Rejected: H5, H10.
Frozen next step for J2: **a protocol for the largest unresolved bound**, here per-antenna gains
on 8 s (T_Af 0.387) and 5 min (T_A 0.375). They are not separated from each other or from
incompleteness (XS2, XS4, K3) or central-source DD gains (H3c).

### 10.2 Post hoc reading (written after the numbers; does not change 10.1)

1. **Dms03 does not respect the mask.** Its model is non-zero on 16,647,036 of 16,777,216 pixels,
   3.53 Jy of it outside set A's mask, and −7.62 Jy is negative. GeMClean logged 0 resyncs and
   τ NaN. Section 4.3 required that a masked arm put no component where F is measured. Dms03
   fails that, so its D 0.363 includes flux in F's own pixels, and the note "extended emission
   CLEAN misses" has no basis as run. It may come from the multiscale scale kernels spreading
   components whose centres lie inside the mask, or from `-fits-mask` being ignored under
   `-multiscale`. This was not checked, and it is a GeMClean question worth an issue. The other
   masked arms (Dm1, Dm03, C0) have no flux outside the mask.
2. **κ is negative.** Deep masked CLEAN on the uncorrected data raises that floor by 0.126 P_B:
   1,073 to 1,139 µJy, with 203,096 components and 104.5 Jy against 91.5 Jy on S1. ΔP(C0) is
   about −1.0 P_ref against +0.22 P_ref for Dm03. The control's premise was that a gain-blind
   depth test removes about the same absolute power from both states. It did not: C0 moved the
   other way, by four times as much. The rule passes by the letter (κ ≤ 0.3), but the control
   does not measure how much of Dm03's drop could be gain artefacts. It does show that deep
   CLEAN on gain-corrupted data builds artefacts into the model, which the subtraction then
   spreads.
3. **The two attributed shares overlap with Family I's bounds.** Family I's non-specific tests
   fire mostly on the incompleteness arms (XS2, XS4, K3), which is what H9's direct test then
   finds. One descriptive joint figure: T_A then T_B | A on top of Dm03 leaves 266.2 µJy,
   0.486 P_ref, so model depth and the two fits remove about 0.51 of P_ref together. Arm S is an
   unmasked 3 mJy run with 0.37 Jy outside the mask. Its drop may include a little extra depth
   (26,982 against 26,357 components), and was not separated from it.
4. **Margins.** The Du1 note passes by 0.010 (0.282 against 0.272), inside the ±0.02 the note
   quotes drops to. The H9 share (0.224) and S share (0.186) are clear of their 0.10 thresholds.
5. **Section 4.4 (E1, E2, E5).** The stats were recorded for the pilot and every arm at a₂, but
   `summary` does not compute the assignment. Computed afterwards: Euclidean distance over log E1
   per annulus and log E5 per facet (each over the arm's own rms), and E2. The pilot is nearest
   XS2 (0.256), H8a (0.262) and XS4 (0.269), then XG4 (0.362) and H1bA (0.364). Each arm has
   one realisation (stats at a₂ only), so "every arm's nearest arm is itself" holds trivially.
   By the letter of 4.4 the provisional assignment is **XS2** (extended emission missing from the
   model). It carries little weight. Three arms of different kinds (XS2, H8a, XS4) lie within
   0.013 of each other in distance from the pilot. The pilot's nearest distance (0.256) is larger
   than the separation of the closest arm pair (XS2 and XS4, 0.182; next XG4 and XS2 0.254, K3 and
   XG4 0.267, H1bA and H3c 0.272). The statistic does not separate the arms at the pilot's
   distance. As frozen, E1, E2 and E5 never override section 6. Pilot E2 0.806; E1/rms 2.93,
   1.62, 1.24, 0.87 (0-10′ … 40-68′).
7. **ρ_B read.** About 59 % of the per-baseline increment survives the deeper model, and about
   41 % was missing model flux. After Dm03 its upper bound is 0.064 P_ref.
8. **The rc of the GeMClean arms.** `fam2.sh` ends without `exit $rc`, so the "rc 0" lines in
   `logs/drive-fam2.log` would read 0 whatever happened. The evidence is each
   `logs/fam2-<arm>.log`, which ends "end rc 0" from GeMClean's own exit status, together with
   the reports (Threshold stop) in the archive.

### 10.3 What #13 can say now (post hoc)

After one Sp round, a deeper model inside the source mask (CLEAN
to 0.3 mJy) removes 0.22 of what is left: F 379 → 335 µJy, 7.6 × thermal. Spectral modelling
with 8 output channels removes 0.19. Neither is a held-out result. The remainder (0.59) is
not tied to any single cause. Antenna gains, per-baseline scales and facet spectral fits each
remove 0.1-0.4, but none is specific against model incompleteness. The per-baseline
increment keeps about 59 % of itself under a deeper model (ρ_B 0.59). w-terms and smearing are excluded.
Cheap next steps: a held-out channel split of Dm03 and of S, and S with Dm03's mask and depth
combined.

## 11. For the coordinator

- **Branch** `floor-5`, not merged. Only `tools/check_all.py --quick` ran (Windows). The full
  check is left to the coordinator's merge check.
- **Owner decisions.** (a) Which J2 next step comes first: a protocol for the antenna-gain
  bound (T_Af / T_A), or the cheap held-out checks of Dm03 and S (and S at Dm03's depth and
  mask). (b) Whether to open a GeMClean issue for `-multiscale` with `-fits-mask` (10.2 item 1).
- **nash, can be deleted** (not deleted; sizes from `du -sh`; all under
  `~/rang-data/outputs/floor-5-20261117` unless named):

  | item | size | regenerate | advice |
  | --- | ---: | --- | --- |
  | `floor-5/skies` | 15 GB | `floor5_tests.py skies`, 248 s | delete |
  | `floor-5/prep.unpinned-41bc3efb` | 431 MB | set aside, never used | delete |
  | `floor-5/prep`, `floor-5/hands`, `floor-5/s1.npy` | 431 MB, 667 MB, 202 MB | `gates` + `pilot`, about 8 min (`floor5_tests.py clean` removes them) | delete after the next step is decided |
  | `family2/{R3,Dm1,Du1,Dms03,C0}` images | 321 MB each | one GeMClean run each, 6-37 min | keep the `-model.fits`; the rest can go |
  | `family2/Dm03`, `family2/S` | 321 MB, 2.9 GB | 8 min, 17 min | keep until the held-out step is decided |
  | `g1/P/g0`, `g1/P/score` | 431 MB, 632 MB | `floor3_score` g0 / score, 1-2 min | delete |
  | `g1/P/pilot.ms` (+ flagversions 202 MB) | 23 GB | copy + 46 min selfcal | keep until the next step is decided (every follow-up reimages it) |
  | `inputs/20261103-gemclean-heldout` (`cal2.ms`, FITS) | 5.1 GB | about 2 h over the workstation uplink | keep until the next step is decided |
  | `inputs/floor-4-20261117` (G1 copy) | 843 MB | equal to the rerun (bit for bit) | delete; also `~/rang-data/outputs/floor-4-20261117` (843 MB), if floor-4 needs it no longer |
  | `inputs/selfcal-defaults-20261117` | 1.6 GB | from selfcal-defaults' run | delete if not used by that branch |
  | `~/Build/tmp/20261117-floor5` (scripts, `arch/`) | 0.6 MB | archived in `results/floor-5/` | delete when the branch is merged |
  | worktree `~/Worktrees/rang/floor-5` on nash (with `.venv`, pinned extension) | 1.1 GB | worktree + venv + copied `.so` | keep while follow-ups need the pinned build |

## Coordinator decisions, 2026-11-17

- (a) Next for #13: held-out checks of the two causes this note supports come first, since they are cheap and confirm or refute 0.224 (depth, Dm03) and 0.186 (spectral, S) on a set not used here. The antenna-gain protocol (T_Af / T_A, the largest unresolved bound) follows. Each gets its own note, frozen before data.
- (b) The multiscale arm Dms03 broke its mask (3.53 Jy on 99 % of pixels). This is a GeMClean defect report, filed as its own issue, and fixed or explained before any multiscale-with-mask result is relied on.
- nash: delete now `floor-5/skies`, `prep.unpinned`, `g1/P/g0`, `g1/P/score` and the floor-4 G1 copies. Keep `g1/P/pilot.ms`, `cal2.ms`, `family2/Dm03` and `S` for the held-out checks.
- For v0.3.0, #13 records its outcome: H1 is attributed (0.83 of the pilot's excess). After one Sp round, depth 0.22 and spectral 0.19 of the remainder are supported but not held out, and 0.59 of the remainder is unattributed. This is a documented limitation.
