# Rang: floor-6, held-out checks of floor-5's two supported causes (issue #13)

Status, 2026-11-17: **measured. H9 (depth) confirmed, D_h 0.201; H8 (spectral) confirmed, larger,
D_h 0.474; every gate passes (GP by clarification 2's reading).** Sections 1-8 are frozen before any held-out
visibility, gain or image is read; clarifications go in section 9 (dated, before the numbers they
affect, or labelled post hoc); results in section 10. Coordinator's brief (owner delegated),
2026-11-17, after [floor-5.md](floor-5.md)'s coordinator decision (a). Host: **nash**
([nash-host.md](nash-host.md)), every job through the main checkout's heavy lock with honest
`--slots`/`--mem`, under `nice -n 19 ionice -c3`. Script: `examples/floor6_tests.py` (committed
after this note; imports `floor_tests`, `floor3_score`, `floor5_tests` and
`gemclean_heldout_real` unchanged). Outputs: `~/rang-data/outputs/floor-6-20261117` on nash.
Archive: `research/results/floor-6/`.

## 1. Question

floor-5 (section 10.1) attributed, on the pilot after one Sp round, **H9 (deconvolution depth)**
share **0.224** of P_ref (arm Dm03: masked Högbom to 0.3 mJy) and found **H8 (spectral
modelling)** supported, share **0.186** (arm S: `-channels-out 8 -join-channels
-fit-spectral-pol 2`). Both were measured on the same visibilities that made the model, the mask
and the self-calibration. **Do the same interventions remove a comparable share of the post-Sp
excess on visibilities floor-5 never used?**

## 2. The held-out set: rule (frozen) and choice

**Rule.** Take the brief's candidates in its order. The held-out set is the first that meets all
of:

1. **Disjoint.** No visibility of it entered floor-5 (floor-5 used `cal2.ms`, the pilot: scan 2,
   `ms1_target.zarr` MAIN_0, channels 640:1152 averaged 2×).
2. **Same recipe, no choice from its data.** It can be built by the pilot's own recipe
   ([gemclean-heldout.md](gemclean-heldout.md) sections 4-5: same channel tiles, the publisher's
   QuartiCal GKB-net gains, set A's received flags, 2× averaging) and scored by floor-5's metric
   with set A's source mask unchanged, so nothing is tuned on it.
3. **Real data before simulation.** A real held-out set tests whether the pilot's causes recur in
   the instrument; a simulation only tests whether the interventions work on a sky built to need
   them. Candidate 3 is used only if 1 and 2 fail.

**Applied, from documents and file layout only (no held-out visibility read):**

- **Candidate 1, `RANG_FLOOR_HELD`, fails rule 1.** In `~/Build/tmp/20261117-floor5/env.sh` it is
  `$OUT/inputs/20261103-gemclean-heldout/real`, the folder holding the pilot's `cal2.ms`: the
  "held-out" in its name is gemclean-heldout's (held out from GeMClean's tuning skies), and it is
  exactly the data floor-5 used.
- **Candidate 2, another time range of the same track.** The pilot is scan 2 of a 7-hour track
  (gemclean-heldout section 8). `ms1_target.zarr` MAIN_4 (scan 10, ESO137-001, the same target
  store; [e2-acceptance.md](e2-acceptance.md) leg a) is already on nash
  (`~/rang-data/e2-a/ESO137/ms1_target.zarr`, fetched for E2-A on 2026-11-17, SHA-256 manifest
  beside it). It is the only other target scan on nash, so it is chosen by availability, not by
  any property of its data. The publisher's GKB-net gains for it are fetched from the same public
  store (`ratt-public-data`, CC BY 4.0, Ramatsoku et al. 2020).
- **Candidate 2 is the held-out set if these conditions hold** (each checked from metadata, and
  each failure is reported; on failure the choice moves to candidate 3, which then needs its own
  frozen protocol before it runs):
  - MAIN_4's rows use one field whose PHASE_DIR equals the pilot's to 0.01″ (so set A's mask
    and F's pixels apply unchanged);
  - one GKB-net group's `gain_time` gives every MAIN_4 row a gain within 1 s, and its
    `gain_freq` matches channels 640:1152 to 1 Hz;
  - at least 15 min of target time.

**Why this is independent of floor-5's pilot.** Different visibilities (another hour angle, so
other uv tracks and sidelobe pattern), independent thermal noise and RFI, its own round-0 model,
its own Sp solutions and final model. Shared with the pilot, by design: the sky, the array, the
publisher's calibration route and set A's source mask (made on the pilot). E2-A has calibrated
and imaged scan 10 with rang's own chain; none of those numbers enters here, and nothing from
floor-5 was chosen after seeing scan 10.

**What it is not.** One more scan of the same field with the same publisher's gains: it can show
that the two causes recur, not that they hold on another field or calibration.

## 3. Pinned code

Every stage runs from the `floor-6` worktree on nash (`~/Worktrees/rang/floor-6`), Python at the
branch's commit (origin/main `9af4f580` plus this branch's script), its own venv `.venv` (Python
3.14.10, `uv pip freeze` equal line for line to floor-5's `freeze.txt`), and **floor-5's
extension, copied**: `python/rang/_core.abi3.so`, SHA-256 `ce12e7d2…c2bc884` (floor-5
clarification 2). So GeMClean, the gridder and the Sp solver are floor-5's exactly. Python under
`python/rang` differs from floor-5's `6de8ecb` only in SPDX lines and paths not used here
(`core_cli` lightcurve and flagdata, `core_config` executor keys, `core_spool`, calibration
error classes). Gate GP (section 5) checks the pin against floor-5's numbers.

## 4. Build, state and metric (frozen)

**Build (held-out, "ho").** `gemclean_heldout_real.py`'s steps on MAIN_4 in place of MAIN_0:
`convert` (channels 640:1152), `verify` (every cell against the Zarr), `gainload` (the chosen
GKB-net group), `gaincheck`, `calibrate` (V / (g_p g_q*), XX and YY), `average --factor 2`, giving
the held-out `cal2.ms` with the received flags (set A's rule). No extra flags.

**Sp round (G1's).** `floor3_score.py copy` (four correlations), then `rang-core selfcal` with
`research/results/floor-3/p1.yaml` unchanged (round-1 image at 3 mJy on DATA → m0; Sp, 300 s,
`freqint: inf`; final 3 mJy image on CORRECTED_DATA → m1).

**State and metric: floor-5 section 3, on the held-out data.** Subset channels 4, 12, …, 252;
Briggs 0.5 recomputed on the subset; 4096 × 3″; F over the inner two-thirds outside set A's mask;
ε 1e-5. S1 = DATA corrected per hand in numpy by the Sp store (floor-5's `apply_store`); S0 = DATA.
**T_ho** is the held-out noise-only floor: F of `Data.noise(1301)` (floor-5's arm C rule on this
geometry). **P = F² − T_ho²**; **P_ref = F(S1, m1)² − T_ho²**; **P_B = F(S0, m0)² − T_ho²**. For a
GeMClean arm X: **D_X = (P_ref − P_X) / P_ref** on S1, and C0's D against P_B on S0, exactly as
floor-5 (`floor5_tests.cmd_score`); a `-channels-out 8` model is predicted per output channel.

## 5. Arms (frozen)

GeMClean = floor-5's family II command (`-size 4096 4096 -scale 3asec -weight briggs 0.5 -gain 0.1
-nmiter 1000 -j 8 -wgridder-accuracy 1e-06 -field 0 -no-update-model-required`), mask = set A's
`images/source-mask.fits`, `-niter 10000000` except R3 (1,000,000, as G1). **No arm uses
`-multiscale`** (floor-5 10.2 item 1: the masked multiscale arm broke its mask; open GeMClean
issue). Masked arms are Högbom.

| arm | data | change | role |
| --- | --- | --- | --- |
| R3 | ho CORRECTED_DATA | `-niter 1000000 -threshold 0.003` | gate GM: reproduces m1 |
| **Dm03** | ho CORRECTED_DATA | mask, `-threshold 0.0003` | **H9's held-out test** |
| C0 | ho DATA | mask, `-threshold 0.0003` | Dm03's gain control (κ) |
| **S** | ho CORRECTED_DATA | `-threshold 0.003 -channels-out 8 -join-channels -fit-spectral-pol 2`, no mask | **H8's held-out test** |
| Dm1 | ho CORRECTED_DATA | mask, `-threshold 0.001` | depth trend (secondary) |
| Rm3 | ho CORRECTED_DATA | mask, `-threshold 0.003` | control: mask alone at R3's depth |
| Sm3 | ho CORRECTED_DATA | S's spectral options, mask, `-threshold 0.003` | S at matched mask and depth |
| SDm03 | ho CORRECTED_DATA | S's spectral options, mask, `-threshold 0.0003` | both together (descriptive) |
| pRm3, pSm3, pSDm03 | pilot CORRECTED_DATA (floor-5's `g1/P/pilot.ms`, read only) | as Rm3, Sm3, SDm03 | the same controls on the pilot (not held out) |

Recorded per arm as floor-5: components, major cycles, stop reason, model flux, negative flux,
flux and pixels outside the mask, residual MAD, wall time.

## 6. Gates (frozen; a failing gate voids what depends on it and is never read as a refutation)

- **GH (build):** `verify` 0 cells differ; every row has a gain within 1 s; gain frequencies within
  1 Hz; `gaincheck` shows the corrected convention more coherent than raw and than the other
  conjugate (as the pilot, gemclean-heldout section 5).
- **GS1 (Sp health, floor-3's):** converged fraction ≥ 0.9, ≤ 5 % solutions flagged. (floor-3's
  r ≥ 0.7 against floor-2's pilot T1p does not apply to another scan and is not required.)
- **HB:** the numpy apply's F(S1, m0) within 1e-4 relative of the same from the MS's
  CORRECTED_DATA (`floor3_score.prep_arm`).
- **GT:** T_ho / F_ref,ho ≤ 0.3, so there is an excess to share.
- **GM:** R3's model pixel-identical to m1. If not, the difference is reported and the held-out
  drops are taken against R3's own score in place of F_ref.
- **GP (pin):** on the pilot, this script's S1 against floor-5's m1 gives F_ref within 1e-6
  relative of floor-5's 379.2616 µJy, and floor-5's kept Dm03 and S models
  (`family2/Dm03`, `family2/S`) score F within 1e-6 relative of floor-5's (`Dm03.json`,
  `S.json` in `results/floor-5/family2/`: 334.8258 and 342.6366 µJy). This also supplies the pilot's P_ref for pRm3, pSm3,
  pSDm03.

## 7. Decision rules (frozen)

For each cause X with floor-5's pilot share D_p and held-out drop D_h, tolerance
**δ = max(0.05, 0.25 D_p)**: H9 (Dm03) D_p 0.224, δ 0.056; H8 (S) D_p 0.186, δ 0.050.

| outcome | rule | H9: D_h | H8: D_h |
| --- | --- | --- | --- |
| **void** | a gate it depends on fails | – | – |
| **confirmed** | D_h ≥ 0.10 and D_h ≥ D_p − δ (H9 also κ_h ≤ 0.3) | ≥ 0.168 | ≥ 0.136 |
| confirmed, **larger** (a qualifier of confirmed) | D_h > D_p + δ | > 0.280 | > 0.236 |
| **smaller** | 0.05 ≤ D_h < D_p − δ (H9 also κ_h ≤ 0.3) | 0.05-0.168 | 0.05-0.136 |
| **not reproduced** | D_h < 0.05 | < 0.05 | < 0.05 |
| **not separated** (H9 only) | D_h ≥ 0.05 and κ_h > 0.3: deep CLEAN absorbs gain artefacts; D_h is an upper bound | – | – |

κ_h = (ΔP(C0) − ΔP(Dm03)) / (P_B − P_ref) on the held-out data, floor-5's definition. floor-5
10.2 item 2 found its premise weak (κ −0.175 there, the control moving the other way); it is kept
unchanged so the two notes read alike, and its value is reported either way.

**Secondary readings (reported; they never change an outcome above):**

- **Spectral at matched mask and depth:** ΔS = D(Sm3) − D(Rm3), on the held-out data and on the
  pilot. If D_S ≥ 0.10 and ΔS_ho < 0.05, the note "**S's drop is mostly unmasked flux, not
  spectral**" is added; if ΔS_ho ≥ 0.10, "**spectral gain survives masking**".
- **Depth trend:** D(Dm1) beside D(Dm03).
- **Together:** D(SDm03) and the ratio D(SDm03) / (D(Dm03) + D(S)), held-out and pilot.
- **Joint:** Σ_ho = the sum of D_h over the causes confirmed, beside floor-5's Σ 0.410. The two
  are not orthogonal, so Σ_ho is not a decomposition.

## 8. Runs, cost and what this does not test

On nash, one unattended driver (`drive.sh`, section 9 names its path and logs): fetch the gains
(metadata first, then the chosen group's chunks for channel chunks 2-4); `build` (single thread,
about 25 min on the pilot's size); `copy`; `rang-core selfcal` (8 slots, `RAYON_NUM_THREADS=8`,
about 46 min on the pilot); `state` (4 slots); the eight held-out and three pilot GeMClean arms
(`-j 8`, 8 slots and 20 GB each, two at a time before 21:30 SAST and one at a time from 21:30 to
06:00); `pilotgate`; `score`; `summary`, which writes `summary.json` and the log's final line
`FLOOR6 DONE rc …`. Every stage writes its own JSON, so a fresh agent can score from the logs.
Each heavy command is wall-timed into [tool-timings.md](tool-timings.md), host nash. No smoke run
touches held-out scores.

Not tested: another field, another calibration route (the publisher's gains are shared), more than
one held-out scan, the cross hands, and multiscale with a mask.

## 9. Clarifications

**1, 2026-11-17 16:10 SAST, before any held-out visibility, gain or image was read.**

- **Night cap.** Nothing that could overlap 21:30-06:00 runs above 8 booked slots in total. The
  driver admits a job if all of its jobs then book at most 8 slots, or at most 16 when it is
  after 06:00 and every running job and the new one end by 21:00 on 1.5 × their estimate.
- **κ needs a gain-caused excess.** κ divides by P_B − P_ref. If Sp barely helps on scan 10 the
  ratio means nothing, so κ is **read only if P_B − P_ref ≥ 0.5 P_ref**; below that it is
  reported, not read, and H9's outcome follows D_h alone ("not separated" cannot occur).
- **Order.** The pilot side runs first and alongside the held-out build: the pilot state, gate GP
  (which is also the smoke test of the whole scoring path, the 8-plane S model included), then
  pRm3, pSm3, pSDm03. On the held-out side R3, Dm03, C0 and S run and are scored before Dm1, Rm3,
  Sm3 and SDm03, so an interim hand-back can read the primaries.
- **Conditions fail → stop.** If section 2's conditions fail, the driver stops and logs it;
  candidate 3 is not improvised unattended.
- **The gain download.** The publisher's GKB-net gains for MAIN_4 are fetched from the public
  store (`https://ratt-public-data.s3.af-south-1.amazonaws.com`, keys under
  `ESO137/ms1_gains.qc/GKB-net/`), as the pilot's were (gemclean-heldout section 5); every object's
  key, size and SHA-256 go to `inputs/gains/manifest.json`. Group metadata and `gain_time` are
  fetched for every group that exists, and the first whose times cover every MAIN_4 row within
  1 s is chosen; only its gains for frequency chunks covering 640:1152 are fetched.
- **Recipe details.** `gemclean_heldout_real.py` is imported unchanged with `main_group` pointed
  at MAIN_4. Its `gainload` (fixed to `GKB-net_0`, three time chunks) and `gaincheck` (row chunks
  0 and 8) are re-implemented in `floor6_tests.py` for the chosen group's chunks and row chunks 0
  and the middle one; the checks and the correction are the same functions. The MS keeps the
  recipe's cosmetic constants (`SCAN_NUMBER` 2, OBSERVER text naming MAIN_0).
- **T and directories.** Every score takes T from its own state (`pilot.json` → `T`): T_ho for
  the held-out side, floor-5's 44.09 µJy for the pilot side (T_noise recomputed beside it, gate
  GP within 0.5 %). The held-out state (`ho/`), the pilot state (`pilot/`) and the arms
  (`family2/`) are separate from floor-5's folders, which are only read. No new environment
  variable; paths go on the command line.

**2, 2026-11-17 16:40 SAST, after the pilot state and before any held-out number (the held-out
build was still running; no held-out score, gain solution or image existed).** The pilot state
reproduces floor-5's F_B (1,073.415606729 µJy) and F_Fix (474.831000629 µJy) to every digit, HB
(rel 0.0) and T_noise (44.0902391 µJy, rel −5e-10). Its F_ref is 379.2621316 µJy. floor-5 holds
two values of this F: 379.2615719 in `pilot.json` (its numpy S1 against the copied m1) and
379.2621316 for R3's model and G1's F_Fin; floor-5 accepted the 1.5e-6 gap under its 1e-4 HB gate.
The pin reproduces the second to every digit and misses the first by 1.48e-6, above GP's 1e-6.
GP's 1e-6 was set below floor-5's own internal gap, so **GP's F_ref test is read against the
nearer of the two floor-5 values**; the miss against `pilot.json` is reported beside it. The
model-score parts of GP (R3, Dm03, S) are unchanged.

## 10. Results

Measured 2026-11-17 on nash, one driver run (16:17:00 to 19:31:39 SAST, `FLOOR6 DONE rc 0`,
held-out and pilot tracks rc 0). Code: the driver started at `e7ac2d26`; `e5f6e74d` (clarification
2) was committed at 16:34:01, so every stage started after it (copy, selfcal, held-out state, the
arms, the scores, `summary`) ran at `e5f6e74d` (Sp receipt: head `e5f6e74d`, dirty false). The two
commits differ in `floor6_tests.py` only in `cmd_summary`'s GP reading. Extension `ce12e7d2…c2bc884`
throughout (Sp summary and receipt). T from seed 1301. Outputs:
`~/rang-data/outputs/floor-6-20261117`. Archive: [results/floor-6/](results/floor-6/)
(`summary.json`, `provenance.json`, the held-out and pilot states, build checks, Sp summary and
receipt, gain manifest, every arm's score, GeMClean report and log, every stage log). Section 10.1
was recomputed by hand from the per-arm JSONs and the two states (every D and ΔP, κ, the
thresholds, the arm commands in each `image-report.json` against section 5's table); it agrees
with `summary.json` to every printed digit. Section 10.2 is post hoc.

### 10.1 The frozen reading

**Held-out set: candidate 2, MAIN_4** (scan 10, field 0, PHASE_DIR separation 0.0″, 450
integrations, 3,590 s; GKB-net group 4 covers every row with gap 0.0 s, gain frequencies equal
to 0 Hz). Section 2's conditions hold.

**Gates: all pass.**

| gate | measured | rule | result |
| --- | --- | --- | --- |
| GH | `verify` identical in UVW, TIME, ANTENNA1/2, DATA, FLAG, WEIGHT_SPECTRUM (850,950 rows); gain gap 0.0 s, freq 0 Hz; `gaincheck` rows chunks 0 and 9: Stokes I coherence 0.986 / 0.988 corrected against 0.949 / 0.955 raw and 0.969 / 0.972 other conjugate; XX-YY phase 0.167 rad against 1.51 and 1.16 | section 6 | pass |
| GS1 | converged 1.0, 1.64 % solutions flagged (= the publisher's gain flags, antenna 21) | ≥ 0.9, ≤ 5 % | pass |
| HB | numpy apply against CORRECTED_DATA: rel 0.0; vis and weights equal; 0 newly flagged | 1e-4 | pass |
| GT | T_ho 41.480 µJy / F_ref,ho 393.294 µJy = 0.105 | ≤ 0.3 | pass |
| GM | R3's model pixel-identical to m1 (same SHA-256 `5651ed63…`); 27,374 components, 3 major cycles, Threshold | pixel-identical | pass, drops against F_ref |
| GP | pilot F_ref 379.2621316 µJy: rel 0.0 against floor-5's R3 / F_Fin, **1.48e-6 against `pilot.json`'s 379.2615719**; F_B, F_Fix, fR3, fDm03 (334.8258), fS (342.6366) rel 0.0; T_noise rel −5e-10 | 1e-6 (F_ref: nearer value, clarification 2); 0.5 % | pass **by clarification 2**; by section 6's letter (against `pilot.json`) it fails and both outcomes would be void |

Held-out state: F_B 835.80, F_Fix 421.38, F_ref 393.29 µJy (9.48 × T_ho; pilot 8.60 ×).
P_ref = 1.530e-7 Jy², P_B = 6.968e-7 Jy², (P_B − P_ref) / P_ref = 3.56 (pilot 7.11), so κ is read
(≥ 0.5, clarification 1).

**Arms.** F on the subset; D against P_ref (C0 against P_B). Every arm stopped on Threshold.
Flux, negative and outside-mask figures for the 8-plane arms are per plane (mean of 8).

| arm | F (µJy) | D | ΔP (Jy²) | components | major cycles | model flux (Jy) | negative (Jy) | outside mask (Jy, pixels) | residual MAD (µJy) | wall (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| R3 | 393.29 | 0.000 | 0 | 27,374 | 3 | 81.88 | −0.05 | 0.069, 209 | 246.7 | 347 |
| **Dm03** | **352.08** | **0.201** | 3.07e-8 | 101,814 | 6 | 86.56 | −0.89 | 0, 0 | 216.2 | 523 |
| C0 (S0) | 847.23 | −0.028 (of P_B) | −1.92e-8 | 152,666 | 4 | 86.42 | −3.80 | 0, 0 | 489.6 | 445 |
| **S** | **286.68** | **0.474** | 7.25e-8 | 28,186 | 3 | 80.14 /plane | −0.09 /plane | 0.048 /plane, 1,232 (8 planes) | 180.3 | 1,033 |
| Dm1 | 361.05 | 0.159 | 2.43e-8 | 49,292 | 3 | 84.98 | −0.31 | 0, 0 | 221.8 | 342 |
| Rm3 | 395.78 | −0.013 | −1.96e-9 | 27,121 | 3 | 81.82 | −0.03 | 0, 0 | 246.9 | 336 |
| Sm3 | 288.98 | 0.465 | 7.12e-8 | 27,986 | 3 | 80.10 /plane | −0.07 /plane | 0, 0 | 180.3 | 1,008 |
| SDm03 | 212.25 | 0.717 | 1.10e-7 | 99,752 | 5 | 84.99 /plane | −0.86 /plane | 0, 0 | 117.8 | 1,714 |
| pRm3 (pilot) | 382.55 | −0.018 | −2.51e-9 | 26,060 | 4 | 85.87 | −0.09 | 0, 0 | 240.1 | 581 |
| pSm3 (pilot) | 347.38 | 0.163 | 2.32e-8 | 26,646 | 3 | 84.69 /plane | −0.10 /plane | 0, 0 | 209.8 | 1,095 |
| pSDm03 (pilot) | 272.13 | 0.492 | 6.98e-8 | 107,386 | 5 | 90.12 /plane | −0.93 /plane | 0, 0 | 156.7 | 2,040 |

Arm walls are GeMClean's own; the pilot arms ran beside the held-out build and Sp, the held-out
arms one at a time (beside the pilot track until 17:47).

- κ_h = (ΔP(C0) − ΔP(Dm03)) / (P_B − P_ref) = (−1.923e-8 − 3.072e-8) / 5.439e-7 = **−0.092**
  (≤ 0.3; floor-5 −0.175).
- **H9 (Dm03): D_h 0.201 ≥ 0.10 and ≥ 0.168 (D_p − δ), ≤ 0.280 (D_p + δ), κ_h ≤ 0.3: confirmed.**
  0.023 below the pilot's 0.224, inside δ 0.056.
- **H8 (S): D_h 0.474 ≥ 0.10 and > 0.236 (D_p + δ): confirmed, larger.** 2.5 × the pilot's 0.186,
  0.24 above the upper edge of the band.
- **Secondary.** ΔS_ho = D(Sm3) − D(Rm3) = 0.465 − (−0.013) = **0.478 ≥ 0.10: note "spectral gain
  survives masking"**; on the pilot ΔS = 0.163 − (−0.018) = 0.181. Depth trend: Dm1 0.159, Dm03
  0.201 (pilot 0.172, 0.224). Together: D(SDm03) 0.717, ratio to D(Dm03) + D(S) 1.06 (pilot 0.492,
  1.20). Σ_ho = 0.201 + 0.474 = 0.675 (floor-5 Σ 0.410); not a decomposition, and SDm03's measured
  0.717 is the joint figure.

### 10.2 Post hoc reading (written after the numbers; does not change 10.1)

1. **The verdicts rest on clarification 2.** Section 6 as first frozen tested GP's F_ref against
   floor-5's `pilot.json` value at 1e-6; the pin misses it by 1.48e-6 and hits floor-5's other
   value (R3 / F_Fin) exactly. Clarification 2 was committed at 16:34:01, after the pilot state
   (16:33:22) and while the held-out build was running: `verify` (to 16:33:19) and `gaincheck`
   (16:33:36 to 16:35:07) had read held-out visibilities and gains, but no held-out Sp solution,
   image or score existed until Sp ended at 17:39 and the held-out state at 17:43. The change
   reads a gate on the pilot, set tighter than floor-5's own internal gap; it cannot move a
   held-out D.
2. **"Larger" means the magnitude does not transfer.** The spectral cause recurs, and with the mask
   on (Sm3 0.465, outside-mask flux 0) nearly all of S's held-out drop is spectral, not unmasked
   flux. But the share is 2.5 × the pilot's, outside the frozen tolerance. With one scan per side
   there is no error bar: 0.186 and 0.474 are two draws, and neither is a stable share of the
   post-Sp excess. Why scan 10 gains more (sky position in the beam with hour angle, bandpass, the
   weaker Sp correction there) was not tested.
3. **Depth transfers in magnitude.** Dm03 0.201 against 0.224, Dm1 0.159 against 0.172: the same
   trend with threshold, about 0.04-0.05 lower on scan 10.
4. **The gain control again moves the other way.** Deep masked CLEAN on uncorrected DATA raises
   F_B from 835.80 to 847.23 µJy (D −0.028 of P_B), with 152,666 components and −3.80 Jy negative.
   κ passes by the letter, as in floor-5, but C0 does not bound how much of Dm03's drop is gain
   artefacts (floor-5 10.2 item 2). Sp also removes less of the excess here: (P_B − P_ref) / P_ref
   3.56 against 7.11.
5. **The mask alone does nothing.** Rm3 −0.013 held out, pRm3 −0.018 on the pilot: masking at 3 mJy
   raises F slightly on both. R3 puts 0.069 Jy (209 pixels) outside the mask; S 0.048 Jy per plane.
6. **Both together.** SDm03 brings F to 212.25 µJy, 5.1 × T_ho, residual MAD 117.8 µJy; the drops
   add almost linearly on scan 10 (1.06) and super-linearly on the pilot (1.20).
7. **Cosmetics.** The held-out MS is named `ho/P/pilot.ms` (the copy stage's name) and keeps
   `SCAN_NUMBER` 2 (clarification 1); the data are MAIN_4's.

## 11. For the coordinator

- **Branch** `floor-6`, not merged. Write-up only in this session; `tools/check_all.py --quick`
  on Windows. The full check is left to the coordinator's merge check.
- **Outcomes as frozen:** H9 confirmed (0.201, κ −0.092); H8 confirmed, larger (0.474); secondary
  note "spectral gain survives masking" (ΔS 0.478). GP passes only under clarification 2 (item 1).
- **For #13 / v0.3.0:** both of floor-5's causes recur on held-out scan 10. Depth at about 0.2 of
  the post-Sp excess; spectral modelling at 0.19-0.47, scan-dependent. Spectral and depth together
  (SDm03) remove 0.72 held out and 0.49 on the pilot.
- **Owner decisions.** (a) Whether to make 8-channel spectral deconvolution with the mask at
  0.3 mJy (SDm03's settings) the selfcal final-image default, which needs its own proposal and a
  cost note (1,714 s against 347 s for R3, 22 GiB against 11 GiB). (b) Whether the antenna-gain
  protocol (floor-5's largest unresolved bound) is now run on top of SDm03's model.
- **nash, can be deleted** (not deleted): `~/rang-data/outputs/floor-6-20261117` holds 79 GB: `ho/build` 35 GB
  (cal.ms, cal2.ms), `ho/P` 24 GB (the Sp MS and run), `family2` 16 GB (the 11 arms' images),
  `pilot` 1.9 GB, `ho/{hands,hb,prep}` 1.7 GB, `inputs` 0.5 GB (gains); the compact readings are
  archived. Keep `ho/P/pilot.ms` and the SDm03 / Dm03 / S models if (b) follows; also
  `~/Build/tmp/20261117-floor6` (scripts, archived in `results/floor-6/scripts/`).

## Coordinator decisions, 2026-11-17

- **Readings accepted as reported, with the GP caveat kept.** H9 (depth) is confirmed at
  D_h = 0.201. H8 (spectral) is confirmed with a larger effect, D_h = 0.474, which is 2.5× the
  pilot's share. GP passes only under clarification 2. That clarification was committed after the
  held-out visibilities and gains were read, but before any held-out Sp solution, image or score
  existed. It stays labelled post hoc in 10.2. A reader who rejects it should read both outcomes as
  void, not as failed.
- **No default changes before v0.3.0.** SDm03 as the selfcal final-image default is a candidate for
  v0.4. It needs E2-A's and E2-N's gate rows re-read with SDm03 before a default changes, under
  calchain-floor's simulation-control rule. Until then it is documented as the floor's largest
  attributed lever (0.717 of the excess on the held-out scan). The antenna-gain protocol on top of
  SDm03's model is queued after that re-read.
- nash's 79 GB output stays until the v0.3.0 release, then is deleted apart from the archive.
