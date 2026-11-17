# Rang: the self-calibration defaults, a frozen grid on the pilot (issue #6)

Status, 2026-11-17: **measured (section 8): default unchanged under the frozen rule.** The chosen
cell, two phase rounds at 600 s (P2@600), gives D_ho 0.905 against the current default's 0.892,
which is less than the 0.05 margin. Protocol frozen in `7bd4fb0` before any run; clarification 1
(`4483ec6`) came before any 600 s or `inf` run solved. Coordinator's decision (owner delegated),
2026-11-17, after [floor-3.md](floor-3.md). floor-3's frozen table said that the default selfcal
settings are the next question for #6. Companion: [floor-4.md](floor-4.md) (#13). Both share the
nash reproduction G1 of floor-3's arm P. Host: **nash** ([nash-host.md](nash-host.md)), heavy lock
with `RANG_HEAVY_NICE=19`, at most 24 slots in all. Script: `examples/selfcal_grid.py` (committed
after this note). Outputs: `~/rang-data/outputs/selfcal-defaults-20261117`. Archive:
`research/results/selfcal-defaults/`.

## 1. Question and priors

Which `selfcal` settings should `rang-core` use by default? The current default
(`python/rang/core_config.py`) is `rounds: 2` and `terms: [{type: Sp}, {type: Sa}]`, so phase,
then amplitude. Each term takes the term default `solint: inf`, one solution per scan, and
`freqint: inf`. It uses `gain_clip: [0.5, 2.0]` and `minuvw_m: 0`. The pilot is one 1 h scan
(scan 2; floor-3's store has 12 bins of 300 s in it), so `inf` means one solution per hour.

Read before this freeze (priors, not outcomes):

- floor-3: one Sp round at 300 s takes the subset floor from 1,073 to 379 µJy (D_Fin 0.877).
- floor-2: the pilot's errors are steady over the hour. The steady part is σ_φ 4.84°, σ_a 1.1 %;
  the variable part is 1.46 % per 5 min.
- How rounds work (read in `core_pipeline.stage_selfcal`): **rounds are not cumulative.**
  Round k images the output column (round 1: the input column), predicts that image into
  MODEL_DATA, solves round k's term on the *input* column against it, and writes
  input / gains to the output column. So the data are corrected by the last round's term alone;
  earlier rounds only improve the model it is solved against. "With an amplitude round" therefore
  means the final correction is a complex diagonal gain (Sa), solved against the model of the
  phase rounds.
- Consequence used for cost: the image made after round r's apply is what a run with r rounds
  would have used as its final image. A run with R rounds therefore also yields the cells for
  1, …, R − 1 rounds of its own terms, each scored with round r's store and image r + 1's model.

## 2. The overfitting concern and the held-out check (frozen)

The model is CLEANed from the same data the gains are solved on, and the score uses that data
again. Two kinds of overfitting are possible:

1. **Noise fitting:** the gains fit the noise in the data they are solved on. It grows with
   shorter intervals and with amplitude freedom.
2. **Absorption:** the gains absorb sky the model lacks. floor-2's incomplete-model arms measured
   that for the fixed-model numpy fits.

**The check for 1 is a channel split.** Gains are frequency independent (`freqint: inf`), so gains
solved on one set of channels apply unchanged to another set at the same times. Every grid run
uses a copy in which the held-out channels B = {c − 1, c, c + 1, c + 2 : c ∈ 4, 12, …, 252}
(128 of 256) are flagged in all four correlations. Imaging and solving then see only the other
128 channels (A). Scores:

- **held out**, on S_B = imaging-floor's 32 metric channels 4, 12, …, 252. Their DATA, flags and
  weights come from `cal2.ms`, never seen by the solve or the CLEAN. The guard channels c − 1 and
  c + 2 keep any correlation between neighbours out of A.
- **in sample**, on S_A = 0, 8, …, 248, 32 channels inside A with the same spacing.

The noise in S_B is independent of everything the gains and the model saw. The sky is the same in
both sets, so **this split does not test absorption (kind 2).** For that, the chosen cell is rerun
once with the solve restricted to baselines above 400 m (`minuvw_m: 400`, floor-3's arm PL), as
section 5 states.

## 3. The grid (frozen)

All runs use floor-3's `p1.yaml` (image section unchanged: 4096 × 3″, Briggs 0.5, 3 mJy, gain 0.1,
8 threads; `memory_limit_gb` 12; `refant: 0`; `input_column: DATA`). Only `selfcal.rounds` and
`selfcal.terms` change. Each Sp and Sa term has `solint: s` and `freqint: inf`. Sa uses the same s
as the phase rounds.

| run | rounds | terms | cells it yields |
| --- | --- | --- | --- |
| L_s | 4 | Sp, Sp, Sp, Sa | P1, P2, P3 (after rounds 1-3), P3A (final) |
| N_s | 3 | Sp, Sp, Sa | P2A |
| M_s | 2 | Sp, Sa | P1A |
| D | 2 | Sp, Sa, both `solint: inf` (the current default) | **the baseline** |

s ∈ {60 s, 120 s, 300 s, 600 s}, so there are 24 grid cells: n ∈ {1, 2, 3} phase rounds, without or
with a final Sa round. Rounds 1 to n of N_s and M_s repeat those of L_s. Their gain stores are
compared bit for bit with L_s's, as a determinism check. Each cell is still scored from the run
named in the table.

## 4. Scores (frozen)

Per cell X (store g of its correction round, model m of the image after it):

- Correction in numpy, per hand, on the chosen channel set, of `cal2.ms`'s DATA:
  V / (g_p g_q*) for XX and YY. Then `core_weights.stokes_i` with the MS's weights and flags. Cells
  where the gain of either antenna is invalid are dropped (cal_apply's rule). The fraction is
  reported; if it exceeds 1 %, T is rescaled as in floor-3's G2.
- Floor F with imaging-floor's code path (`floor_tests.prep`, `grid`, `floor`: Briggs 0.5
  recomputed on the subset, 4096 × 3″, inner two-thirds outside set A's mask, ε 1e-5) against m.
- **Flux scale.** σ = the median of |g| over valid bins, antennas and hands (1 for Sp). An Sa
  round can lower F just by scaling the data and the model down together. Every score is therefore
  normalised, F' = σ² F, and P = F'² − T² uses the set's own thermal T. That T comes from the
  noise-only arm (`Data.noise(1301)` gridded) on that set's prep.
- P_0 per set = DATA (uncorrected) against the round-1 model of run D. Every run's round-1 image
  is the same computation, and the models are compared pixel for pixel. If they differ, each run's
  drops use its own round-1 model, and that is reported.
- **D_ho(X)** = (P_0 − P_X) / P_0 on S_B; **D_in(X)** the same on S_A. Δ(X) = D_in − D_ho is the
  noise-fitting gap.
- **Health of X:** every round of its run up to its correction round has converged fraction ≥ 0.9
  and at most 5 % of solutions flagged (gain clip included).

## 5. Decision rule (frozen)

1. **Eligible:** healthy cells with Δ ≤ 0.05.
2. **Best:** D* = max D_ho over eligible cells. Candidates: eligible cells with D_ho ≥ D* − 0.02.
   Of these, **the chosen cell** is the cheapest: fewest rounds (n plus one if amplitude), then
   without amplitude, then the longest s.
3. **Absorption check:** the chosen cell is rerun in hold-out mode with `minuvw_m: 400`. It passes
   if that run's D_ho is at least D_ho(chosen) − 0.05.
4. **Change the default** to the chosen cell (its rounds and terms; `solint: s` written into the
   default terms) if the check passes and either:
   - D_ho(chosen) ≥ D_ho(D) + 0.05; or
   - D is not eligible and D_ho(chosen) ≥ D_ho(D) − 0.02.
5. Otherwise **the default is unchanged**, with the numbers reported. If the check fails, that is
   reported as suspected absorption, and the default is unchanged.

Drops are quoted to ±0.02. **One field.** The rule is applied to the pilot alone (one 1 h scan, one
band, one bright source). The CHANGELOG entry says so. A default change is code: `core_config.py`,
its tests, `python docs/gen_cli.py` and the CHANGELOG, made only after the outcome and on this
branch.

**What it means for #6.** The chosen setting is the measured default for a field like the pilot.
It also says whether amplitude self-calibration, as the current default does, helps after the
phase errors are gone, and how short an interval the pilot's steady errors need.

## 6. Gates (frozen)

- G0 and G1 of [floor-4.md](floor-4.md) section 5 (G1 is floor-3's arm P on nash, full data).
- **HB1, the numpy apply.** On G1's copy, the numpy correction with the round-1 store reproduces
  `floor3_score`'s F_Fix (from the MS's CORRECTED_DATA) within 1e-4 relative.
- **HB2, thermal:** T on S_B within 0.5 % of 44.09 µJy.

If HB1 fails, nothing in the grid is scored.

## 7. Runs and cost

Each run gets a fresh copy of the four-correlation pilot (made once on nash by
`floor3_score.cmd_copy`'s rewrite). B is then flagged, and the copy is deleted after scoring. Order:
G1; then L_s for s = 300, 60, 120, 600; D; M_s; N_s; then the absorption check. Up to three runs at
a time, each `--slots 8 --mem 20` with `RAYON_NUM_THREADS=8`; the simulation job of floor-4 takes
one of the three places while it runs. On the workstation a round took about 870 s (solve 609 s,
image about 200 s) at 8 threads. There are 43 rounds and 15 final images, about 11 h of 8-thread
work, so about 4 h or more on nash with three in parallel. Wall times go into
[tool-timings.md](tool-timings.md), **host nash**.

## 8. Results

Measured 2026-11-17 on **nash**. Every job ran through the heavy lock (`RANG_HEAVY_NICE=19`, plus
`nice -n 19 ionice -c3`, `RAYON_NUM_THREADS=8`). The grid runs booked 8 slots and 20 GB (24 GB for
600 s, 96 GB for D) and the absorption run X 2 slots and 24 GB (scheduling change, section 9). At
most three grid runs were in flight. The scripts ran from the worktree at `b342702`, and at
`4483ec6` from L600's second attempt on. The package came from nash's main checkout, and every run
records the same extension, `gemclean_sha256` `ce12e7d2…`. The scores of L60, L120 and L300 ran
after HB1 had been read (`NOSCORE=1`, then `run_nash.sh score`). The other runs scored at their
end. Archive: [results/selfcal-defaults/](results/selfcal-defaults/): `summary.json`
(`summary-before-X.json` before run X), `scores/<run>.json` (every cell on S_B and S_A, solve
health, round CLEAN, model hashes), the thermal of both sets, `logs/` (every job, the failed
`*-attempt1` and the rebooked `grid-D-ticket100`), and `scripts/` (the nash drivers). Run
directories (stores, images) stay on nash in `~/rang-data/outputs/selfcal-defaults-20261117/`.
The MS copies, the base copy and nash's copy of `cal2.ms` are deleted.

### 8.1 Frozen readings

**Gates. All pass.** G0 and G1 are those of floor-4 (G1 bit-equal to floor-3). **HB1:** the
numpy apply reproduces `floor3_score`'s F_Fix with relative difference 0.0. **HB2:** T on S_B is
44.090 µJy (relative −5e-10). S_A's T is 44.063 µJy. **Round-1 models:** identical across all 13
runs (one SHA-256), so P_0 is one number per set: F_0 = 1,068.10 µJy on S_B and 1,098.09 µJy on
S_A. **Determinism:** rounds 1 to n of every M and N run equal L's gain stores bit for bit.

**Health.** Every cell is healthy: converged fraction ≥ 0.9989 in every round, solutions flagged
1.64 % (antenna 21, flagged throughout), 0 clipped, no cells newly flagged. **Every gap
Δ = D_in − D_ho lies between −0.0027 and −0.0022**, so no cell shows noise fitting, and all 24
cells and the default are eligible.

**Grid** (D_ho on the held-out channels; in brackets F on S_B in µJy):

| cell | 60 s | 120 s | 300 s | 600 s |
| --- | --- | --- | --- | --- |
| P1 (one Sp round) | 0.877 (376.8) | 0.877 (377.0) | 0.876 (379.0) | 0.873 (382.9) |
| P2 | 0.909 (325.1) | 0.909 (325.3) | 0.908 (327.5) | **0.905 (331.9)** |
| P3 | 0.910 (322.8) | 0.910 (323.0) | 0.909 (325.2) | 0.906 (329.8) |
| P1A (Sp, then Sa) | 0.914 (313.1) | 0.914 (313.3) | 0.913 (315.7) | 0.910 (320.5) |
| P2A | 0.916 (310.8) | 0.915 (311.1) | 0.914 (313.5) | 0.911 (318.4) |
| P3A | **0.916 (310.1)** | 0.916 (310.3) | 0.915 (312.6) | 0.912 (317.5) |
| D, current default (Sp, Sa, `solint: inf`) | | | | 0.892 (350.4) |

Amplitude cells are normalised by σ² with σ = 1.0039-1.0043. D_in runs 0.0022-0.0027 below
D_ho in every cell.

**Rule.**

1. Eligible: all 24 cells (and D).
2. D* = 0.9159 (P3A@60). Candidates with D_ho ≥ 0.8959: all P2, P3, P1A, P2A and P3A cells (20). The
   cheapest is **P2@600**: two rounds and no amplitude. P1A has two rounds as well but amplitude,
   and 600 s is the longest interval. D_ho(P2@600) = 0.9050.
3. Absorption check: X, P2@600 with `minuvw_m: 400` (the selfcal summary records
   `uvrange '>400'`, and the round-1 model is the grid's). It is healthy and gives D_ho = **0.9037**,
   at least 0.9050 − 0.05 = 0.855: **passes** (gap −0.0025).
4. Change: D is eligible (healthy, Δ −0.0025), and D_ho(P2@600) − D_ho(D) = 0.9050 − 0.8922 =
   **0.013 < 0.05**. Neither branch of step 4 holds.
5. **The default is unchanged** (`rounds: 2`, Sp then Sa, `solint: inf`). This holds whatever
   step 3 gives.

**What it means for #6 (frozen).** On the pilot (one 1 h scan, one band, one bright source), the
current default lowers the held-out excess by 0.89. No cell of the grid beats it by the frozen
margin of 0.05, the best by 0.024 (P3A@60). Amplitude self-calibration after the phase rounds
helps: each nA cell beats its n-round phase-only cell by 0.005-0.037. Shorter intervals help by
0.004 at most, between 600 s and 60 s. The pilot's errors are steady, so `inf` is nearly
enough.

### 8.2 Post hoc remarks (not part of the frozen reading)

- **One phase round is worse than the default.** P1 (0.873-0.877) is the floor-3 setting, and D
  (0.892) beats it by 0.015-0.019. A second phase round adds 0.03 by improving the model the last
  round solves against. That is the largest single step in the grid.
- **No overfitting by noise** at any interval or freedom: Δ is the same −0.0025 ± 0.0003 for
  phase-only and amplitude cells, from 60 s to `inf`. A gap that is the same for every
  setting, the default included, belongs to the two channel sets (S_A's P_0 is higher, 1,098
  against 1,068 µJy), not to any setting.
- **Remaining floor.** The best cell leaves 310 µJy on S_B (7.0 × T). That is close to floor-3's
  379 µJy after one round on the full data, and the gain from more freedom levels off.
- **Memory.** D's scan-long solve peaked at 37 GB of resident memory against the 80 GiB the
  chunk plan predicted, and the 600 s runs at 11.7 GB against 13.6 GiB. The current default
  cannot run on this pilot at the default `memory_limit_gb` of 8 (clarification 1). That is a
  usability problem for #6, independent of the score.
- **Cost.** The selfcal stage wall times, at 8 threads on a shared host, are L60 3,291 s, L300
  5,753 s, M60 1,807 s, M600 3,119 s and D 2,041 s. Solves at 300-600 s take 3-4 × those at
  60-120 s (925 against 287 s for one Sp round). D's `inf` solve is the fastest (299 s).
- **Absorption.** The long-baseline solve keeps 0.9037 / 0.9050 = 0.999 of the chosen cell's drop,
  as floor-3's PL kept 0.99 of P's. The two-round correction is found on baselines above 400 m.

## 9. Clarifications before the scored runs

**1, 2026-11-17 04:20 SAST (after L60, L120 and L300 were scored, before any run with a 600 s or
`inf` interval had solved).** Run L600 stopped in its first solve with rang-core's refusal:
`one solution interval holds 142417920 visibility cells of 823500 rows and needs 13.579 GiB, above
data.memory_limit_gb 12` (log kept as `grid-L600-attempt1.log`). D's scan-long interval
(`solint: inf`, about 843 million cells) would need about 80 GiB, so D was stopped before its solve
(`D-attempt1`). `data.memory_limit_gb` is a resource budget only. The solver solves one interval
whole. rang-core's chunking "changes no arithmetic" (`core_chunks`, research/w3-chunking.md
section 3), and GeMClean does not read the limit. Runs whose terms include a 600 s interval (L600, M600,
N600, and X if the chosen cell has one) therefore use `memory_limit_gb: 16`. Runs with `inf` (D)
use 96. Every other key of `p1.yaml` is unchanged. Lock bookings follow honestly: 24 GB for
the 600 s runs, 100 GB for D. The failed attempts' MS copies were deleted and the runs start again
from a fresh copy of the base. No rule, threshold, cell or score changed. Post hoc remark, not a
reading: the current default (`solint: inf`) cannot solve this 1 h, 256-channel pilot within the
default `memory_limit_gb` of 8.

**Scheduling change, 2026-11-17 08:25 SAST (coordinator, on the owner's order; no protocol effect).**
The grid runs booked 8 slots but used about one core each (the solve and the numpy stages are not
8-way parallel). Every run not yet launched books `--slots 2` with its `--mem` figure unchanged,
up to 8 runs at once, with the sum of `--mem` at most 160 GB. Only X was still to launch;
N300 and N600 kept their 8-slot bookings. `RAYON_NUM_THREADS=8` and every setting are unchanged.
The booking changes neither the arithmetic nor the order of any computation.

