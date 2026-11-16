# Rang: floor-3, a direct test of H1 with phase-only self-calibration on the pilot (issues #13, #6)

Status, 2026-11-16: **measured (section 9): frozen joint reading row 1, H1 attributed under
floor-3's standard, share D_Fin 0.88.** The protocol (sections 1-7) was frozen in `59f9a20` before
any run; clarification 1 (`3f75001`) came before the stage. Follow-up to
[floor-2.md](floor-2.md) section 13, approved by the coordinator (owner delegated) on 2026-11-16.
Configurations: [results/floor-3/p1.yaml](results/floor-3/p1.yaml) (arm P),
[results/floor-3/pl.yaml](results/floor-3/pl.yaml) (arm PL). Scoring script:
`examples/floor3_score.py` (committed after this note; it imports `examples/floor_tests.py`
unchanged). Outputs: `D:\rang\outputs\floor-3-20261116`. Archive: `research/results/floor-3/`.

## 1. Question and priors

floor-2 left H1 (antenna calibration residuals) unresolved under its frozen joint rule, with a post
hoc lead: steady per-antenna phase errors of about 5° (σ_φ 4.84°, σ_a 1.1 %, antenna 1 at −14°).
A 5-min, frequency-independent, phase-only fit against the 3 mJy model (floor-2's T1p, a numpy
StefCal on Stokes I) removed **0.828** of the pilot's excess power, and the same fit on baselines
over 400 m only removed 0.827. This protocol asks: **does rang-core's own phase self-calibration
(`rang-core selfcal`, term Sp) reproduce that drop on the pilot, both against the fixed model and
after re-imaging?** Priors read before the freeze: 0.828 and 0.827 above; P_pilot = 1.150e-6 Jy²;
F = 1,073.42 µJy; subset thermal T = 44.09 µJy (imaging-floor, floor-2).

How Sp differs from T1p (read in `python/rang/cal_selfcal.py` before the freeze): Sp solves a
phase per antenna **and hand** (QuartiCal's `phase`, `GainDiagPhase`) on XX and YY against
MODEL_DATA, per CASA-style 300 s bins from the scan start, frequency-independent (`freqint: inf`),
referenced to antenna 0; T1p solved one phase per antenna on Stokes I. A per-hand solve can remove
more than T1p (heldout §5 left 0.17 rad of median XX−YY phase). `minuvw_m` cuts on projected
√(u² + v²) in metres, as floor-2's T1L did. The model is not the archived one: round 1 images
DATA with rang-core's GeMClean (`image` settings in the YAML: 4096 × 3″, Briggs 0.5, gain 0.1,
3 mJy absolute threshold, up to 1,000 major cycles, gridder accuracy 1e-6, as heldout's
`cal2-003-gem`), predicts it into MODEL_DATA, solves, applies into CORRECTED_DATA, and a final
image of CORRECTED_DATA follows (one round).

## 2. Inputs and provenance

Every input of floor-2 section 2, unchanged (`cal2.ms`, the pilot model, the mask, SHA-256 there).
Each arm runs on its **own fresh copy** of `cal2.ms` (`selfcal` writes the MS and its FLAG in place;
`cal2.ms` itself is never written). rang-core and GeMClean are the main checkout's build at the run
(commit and GeMClean SHA-256 recorded from the stage's `summary.json`).

## 3. Arms (frozen)

| arm | what | configuration |
| --- | --- | --- |
| P | one round of Sp, 300 s, all baselines | `p1.yaml` |
| PL | the same, solved on baselines with √(u² + v²) > 400 m only, applied to all | `pl.yaml` (`minuvw_m: 400`) |

**The worst-six arm is not run.** Flagging antennas 1, 25, 27, 22, 17 and 11 does not discriminate
by itself. Without them σ_φ falls only from 4.84° to 3.63° (floor-2 section 12), so H1 predicts a
drop of order 1 − (3.63/4.84)² = 0.44, not 0.83. Flagging them also removes about a fifth of the
baselines, many of them short (antenna 1 sits 81 m from the centre), which changes the PSF and the
thermal noise and would also lower a floor caused by short-spacing incompleteness. A fair version
needs a seeded control set of six antennas with a matched short-baseline share, its own baseline
and thermal, and a prediction by formula. PL is the stronger discriminator: floor-2 showed it valid
on gains (1.000) and separating from every short-spacing kind (≤ 0.23).

## 4. Metric (frozen)

imaging-floor's floor F (exact residual, Briggs 0.5 weights recomputed on the subset, 4096 × 3″,
32 channels 4, 12, …, 252, inner two-thirds outside set A's mask, ε 1e-5), computed by floor-2's
code path (`floor_tests.prep` and `grid`) on the arm's MS after the stage, with that MS's FLAG and
WEIGHT_SPECTRUM, so before and after share one flag set. Excess P = F² − T² with T = 44.09 µJy.
Scores per arm:

- **B**, the baseline: DATA against the round-1 model (rang-core's own image of uncorrected data).
- **Fix**: CORRECTED_DATA against the round-1 model (the gains alone, the model fixed). This is the
  replication of floor-2's T1p with an independent solver; the expected value 0.828 was known.
- **Fin**: CORRECTED_DATA against the final model (gains and re-imaging), the new measurement and
  the one #6 cares about.

D_Fix = (P_B − P_Fix) / P_B and D_Fin = (P_B − P_Fin) / P_B. Drops are quoted to ±0.02.

## 5. Gates (frozen, before any new number is read)

- **G0, scoring code.** On arm P's fresh copy, before the stage: DATA against the archived pilot
  model `cal2-003-gem-model.fits` must give F within 0.1 % of 1,073.42 µJy.
- **G1, baseline.** F_B within ±10 % of 1,073.42 µJy (GeMClean, the host and the threads changed since
  2026-11-03). If outside, that is reported, and the drops stay relative to the arm's own P_B.
- **G2, flags.** The fraction of subset cells that the stage newly flags is reported. If it exceeds
  1 %, every drop is also quoted with T rescaled by √(active before / active after).
- **Health of each solve** (else the arm is **void**, never a refutation): converged fraction ≥ 0.9;
  at most 5 % of solutions flagged; the steady phases (per antenna, the mean of the two hands,
  after floor-2's gauge, mean over bins) correlate with floor-2's T1p steady phases at Pearson
  r ≥ 0.7 over active antennas.

## 6. Decision rules (frozen)

On arm P, if healthy:

- **R1, replication (Fix).** Replicates if D_Fix ≥ 0.75. Refutes floor-2's T1p drop as an estimator
  artefact if D_Fix < 0.40. Partial otherwise.
- **R2, practice (Fin).** Self-calibration lowers the floor if D_Fin ≥ 0.75. Fails if D_Fin < 0.40.
  Partial otherwise.
- **Disagreement.** If R1 replicates and D_Fin < 0.40, the gains are right but re-imaging brings the
  floor back. That points at deconvolution of the corrected data (H9), and is reported as such. If
  D_Fin ≥ D_Fix + 0.10, re-imaging adds to the drop, and that is reported.

On arm PL, if healthy:

- **R3, where the correction is found.** Long-baseline solve: D_Fix^PL ≥ 0.7 D_Fix^P means the phase
  correction is found on long baselines (floor-2's short-spacing kinds gave ρ_L ≤ 0.23). Below
  0.3 D_Fix^P means it is absorbed from short spacings. Partial otherwise.

**Joint reading for #13 and #6.**

| R1 | R2 | R3 | #13 | #6 |
| --- | --- | --- | --- | --- |
| replicates | lowers | long | **H1 attributed under floor-3's standard, share D_Fin (raw)** | one Sp round of `rang-core selfcal` at 300 s fixes most of the floor on the pilot; the default selfcal settings are the next question |
| replicates | lowers | partial or short | H1 supported, not attributed: the correction may partly absorb missing short-spacing flux | selfcal lowers the floor in practice; the mechanism is not settled |
| replicates | partial or fails | any | H1 supported for the data, but the image floor needs more than gains (H9 or deconvolution) | selfcal alone is not the fix |
| partial | any | any | H1's bound stays 0.854, unresolved | no change |
| refutes | any | any | floor-2's lead withdrawn; H1's bound stays as imaging-floor's, unresolved | selfcal is not the fix |

**Floor-3's attribution standard, stated:** a direct correction by an independent solver, with
specificity against incompleteness taken from floor-2's simulations (six incomplete-model arms
giving R ≥ 0.42 and ρ_L ≤ 0.23). It is **not** imaging-floor's full specificity criterion:
floor-2 did not run the phase-only or long-baseline fits on the H2 (bad short baselines), H8a
(spectral index) or H4b (beam) arms, and this protocol adds none. The amplitude condition holds as
a prior: the pilot's σ_φ 4.84° is within imaging-floor's a_max of 5°.

## 7. Runs

Order: copy for P, G0, the stage, scores, then copy for PL, the stage, scores. The copies are
deleted after scoring. Every heavy command runs under the main checkout's
`tools/heavy_lock.py run --slots 8 --mem 20` (GeMClean at 8 threads, then the solve), wall-timed,
with rows in [tool-timings.md](tool-timings.md) labelled with the host. **Host: this workstation,
not nash.** The 8.1 GB MS is already here, a copy is cheap, and the run takes minutes. A smoke run,
if any, stays off the pilot's new scores and is declared here.

## 8. Clarifications before the stage ran

**1, 2026-11-16 22:35 (after G0, before any selfcal number existed).** The first attempt stopped
at the stage's refusal: `selfcal: correlations XX, YY: the solves and the apply kernel take four
correlations` (research/w4-unsupported.md). G0 on that plain copy had passed (F 1,073.416 µJy,
0.999996 ×; kept as `g0-2corr.json`). Each arm's copy is therefore **rewritten with four
correlations**: XX and YY as in `cal2.ms`, XY = YX = 0, with XY's flag and weight taken from XX
and YX's from YY. That is the same expansion `floor_tests.prep` already makes in memory, except
that the cross hands hold 0 instead of a copy (the Stokes I rule reads XX and YY only). The model
is Stokes I, so its cross hands are 0 and the zero data adds no residual to the diagonal phase
solve. One consequence: the apply's general-Jones rule flags all four correlations of a cell when
any input flag is set, so cells flagged in one hand only become flagged in both. Stokes I already
drops those cells, and G2 reports any change. G0 runs again on the four-correlation copy and must
pass as frozen; that also checks the rewrite. No rule, threshold or arm changed.

## 9. Results

Measured 2026-11-16 on this workstation (native Windows), each arm under the main checkout's heavy
lock (`--slots 8 --mem 20`, `RAYON_NUM_THREADS=8`). rang-core and GeMClean were the main checkout's
build at `9d1cf8f` (receipt `commit.head`, not dirty); GeMClean SHA-256 `acbae192…46bda46d29fda5c8`.
PL's selfcal summary records `uvrange: '>400'` (P: empty), so the cut reached the solve. No smoke run
was made. Archive: [results/floor-3/](results/floor-3/): `P-score.json`, `PL-score.json`,
`summary.json`, `g0.json`, `g0-2corr.json`, and the logs `P-attempt1.log` (the refused first
attempt of clarification 1), `P.log`, `PL.log`. The run directories (receipts, gain stores, both
models; 0.84 GB per arm) stay in `D:\rang\outputs\floor-3-20261116\{P,PL}\run`. The MS copies and
the prep scratch are deleted (`floor3_score.py clean`).

### 9.1 Frozen readings

**Gates.**

- **G0 passed**: F = 1,073.416 µJy (ratio 0.999996) on P's two-correlation copy (`g0-2corr.json`).
  It passed again, bit-equal, on the four-correlation copy (`g0.json`), so the rewrite of
  clarification 1 leaves the Stokes I residual unchanged.
- **G1 passed**: F_B = 1,073.416 µJy in both arms (ratio 0.999996). rang-core's round-1 model is
  pixel-identical to the archived `cal2-003-gem-model.fits`: maximum absolute difference 0,
  43,376 non-zero pixels in each, the same sum. The files differ only in header bytes. That is why
  B equals G0 to every digit.
- **G2**: the stage newly flagged 0.0 % of subset cells in both arms (19,133,875 active before and
  after). T is not rescaled.

**Health.** Both arms are healthy.

| arm | converged | solutions flagged | iterations | Pearson r vs floor-2 T1p | σ_φ, Sp / T1p | healthy |
| --- | --- | --- | --- | --- | --- | --- |
| P | 1.000 | 1.6 % | 13 | 0.989 | 4.80° / 4.84° | yes |
| PL | 1.000 | 1.6 % | 13 | 0.983 | 4.82° / 4.84° | yes |

**Scores.** F is in µJy on the subset, T = 44.09 µJy, and drops are quoted to ±0.02.

| arm | F_B | F_Fix | F_Fin | D_Fix | D_Fin |
| --- | --- | --- | --- | --- | --- |
| P | 1,073.4 | 474.8 | 379.3 | **0.81** (0.806) | **0.88** (0.877) |
| PL | 1,073.4 | 483.3 | 380.1 | 0.80 (0.799) | 0.88 (0.876) |

**Rules.**

- **R1 (Fix): replicates.** D_Fix^P = 0.806 ≥ 0.75.
- **R2 (Fin): lowers.** D_Fin^P = 0.877 ≥ 0.75.
- **Disagreement checks: neither fires.** D_Fin ≥ 0.40, so there is no H9 flag. D_Fin − D_Fix = 0.071,
  below 0.10, so "re-imaging adds to the drop" is not reported.
- **R3: long.** D_Fix^PL / D_Fix^P = 0.799 / 0.806 = **0.991**, at least 0.7.

**Joint reading (frozen table, row 1): H1 attributed under floor-3's standard, share D_Fin (raw)
= 0.88.** #6: one Sp round of `rang-core selfcal` at 300 s fixes most of the floor on the pilot.
The default selfcal settings are the next question.

The row-1 reading uses section 6's standard and no more. The standard is a direct correction by an
independent solver, plus specificity against incompleteness taken from floor-2's six
incomplete-model simulations (R ≥ 0.42, ρ_L ≤ 0.23). It is **not** imaging-floor's full
specificity criterion. Neither floor-2 nor floor-3 ran the phase-only or long-baseline fits on
the H2 (bad short baselines), H8a (spectral index) or H4b (beam) arms. "Attributed" here means
attributed under that stated standard.

### 9.2 Post hoc remarks (not part of the frozen reading)

- **Replication size.** D_Fix 0.806 lies 0.022 below floor-2's T1p (0.828), just outside the
  ±0.02 quoting band. The per-hand solve removed slightly less than T1p, not more. The per-hand
  freedom that section 1 allowed for did not add to the drop.
- **What is left.** After the final image the floor is 379 µJy, 8.6 × thermal. The excess falls
  from 1.150e-6 to 1.42e-7 Jy², so 0.12 of it remains. Nothing here explains that remainder.
  It is close to floor-2's post-T1 remainder (412 µJy against the fixed model).
- **Long against all baselines.** PL matches P in every score to within 9 µJy (Fix) and 1 µJy
  (Fin). Its phases correlate with T1p at 0.983, against 0.989 for P. The correction needs nothing
  from baselines under 400 m.
- **Between hands.** The steady XX − YY phase difference is 17.7° rms over active antennas
  (17.4° in PL), much larger than the 4.8° spread of the mean of the hands. The Stokes I score is
  insensitive to a difference between the hands. This is descriptive, untested, and may be a
  feed or X−Y phase term, or the Stokes I model fitted per hand.
- **Same-data model.** Both models are CLEANed from the pilot itself, and Fin is scored against
  the model imaged from the corrected data. Self-calibration against a same-data model can absorb
  unmodelled flux. The D_Fix ≈ D_Fin agreement and PL's long-baseline result argue against a
  large effect, but neither tests it. The run has one round, one data set and one noise
  realisation.
- **Deconvolution.** The final CLEAN reached the 3 mJy threshold in 3 major cycles with 26,357
  components (round 1: 5 cycles, 58,314).

### 9.3 What it means for #13 and #6

- **#13 (the pilot's floor).** Frozen: **H1 attributed under floor-3's standard**, with share 0.88
  of the subset's excess power (raw). That means steady per-antenna phase errors of about 5° rms,
  left in the publisher's calibrated data, removed by one phase solve. The share is a direct
  measurement on the pilot. It is not attribution under imaging-floor's full criterion, which
  would need the H2, H8a and H4b specificity arms. The 379 µJy remainder (0.12 of the excess) is
  unattributed.
- **#6 (self-calibration).** Frozen: one phase-only round of `rang-core selfcal` (Sp, 300 s,
  `freqint: inf`) fixes most of the floor on the pilot (1,073 to 379 µJy on the subset), and the
  default selfcal settings are the next question. Post hoc: the same holds when the solve uses
  baselines above 400 m only. A field other than the pilot is untested.
