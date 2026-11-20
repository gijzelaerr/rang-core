# Rang: one-day screenings of stages 3, 4 and 5a for a learned replacement (#44, DL4s)

Status at freeze, 2026-11-20: **proposed; stages 4 and 5a decided from the record (section 5), stage 3's
probe not run.** Branch `dl4s-screen` from origin/main `92e67e2f`. Route:
[docs/agents/propose-and-measure.md](../docs/agents/propose-and-measure.md). Plan:
[dl-plan.md](dl-plan.md) stage table rows 3, 4, 5a ("one-day screenings, outcome recorded"); cost basis:
[dl0-profile.md](dl0-profile.md) (final form `6dd70c86`). nash's account was locked from about 10:00 SAST
on 2026-11-20, so this note was written on glacier from records only; stage 3's probe waits for nash.

**What a screening is here.** Not a pilot: for each stage, (1) the best any learned stage could save or
fix, bounded from records; (2) whether a failure class exists that the present rules miss; (3) an
outcome. A stage moves to a pilot only if both the bound and the failure class leave room.

**Provenance warning.** For stages 4 and 5a every number below was read before these rules were
written (the facts were gathered first, the same day). Their outcomes are therefore **readings of seen
results, labelled post hoc**, not blind tests. Stage 3's probe (section 2.3) is frozen here before it
runs.

## 1. Stage costs (bound on any saving)

From [dl0-profile.md](dl0-profile.md) 2.1 and 2.2 (E2-A, E2-N, time-averaged configuration) and
[dl-plan.md](dl-plan.md) lines 140-142:

| Stage | Share of `rang-core run` or of selfcal | Source |
| --- | --- | --- |
| 3, solution quality (rules after a solve) | < 1 % of the run | dl-plan row 3 |
| 4, polarisation terms (Gpol, KCROSS, Xf, Df) | inside calibrate (7-12 % of the run); on E2-N about 1,222 of 4,070 calibrate samples (30 % of calibrate, about 2 % of the run), almost all in table reads | dl0-profile 2.2 |
| 5a, predict and degrid | selfcal: major cycles 1.6-2.3 % plus MODEL_DATA predicts 3.9-5.3 %, so at most 5.5-7.6 % of selfcal | dl0-profile 2.1, 2.2 |

## 2. Stage 3: a classifier of bad solutions

### 2.1 Failure classes on record

- **One real instance, caught by no rule:** E2-A's K1 solution of ID 50 (m053), interval 7: 2,335 /
  2,291 ns (rang) and 2,365 / 2,381 ns (CASA) against 0.11 / 0.09 ns in every other interval; the only one
  of 1,680 solutions in either tool ([calchain-floor.md](calchain-floor.md) lines 535-595). Mechanism:
  94 cells with two baselines to the refant, the FFT start on a sidelobe. Found by a diagnostic outlier
  screen (K1 |Δτ| > 0.1 ns, G1 relative > 0.1; [e2a-3b-diag.md](e2a-3b-diag.md) line 104), not by a
  solver rule. **Fixed classically:** `calibrate.k_zero_start` (default off) moves it to 0.121 / 0.094 ns
  and no other solution by more than 1e-3 ns (calchain-floor 639-647).
- **Its downstream effect, caught by CASA, not by rang:** ID 50's G1 amplitudes 0.73 / 0.38 / 0.09 /
  0.29 / 0.72 in intervals 5-9; CASA flags interval 7 (X) by minsnr (SNR 2.22 < 3 on averaged,
  model-divided data), rang keeps it (SNR 30.1 on raw cells); that one flag carries the subset
  composite 1.1e-3 ([e2a-3b-k.md](e2a-3b-k.md) lines 305-326). An SNR rule on averaged cells is an open
  classical design question there (lines 475-478).
- **Disagreements, not failures:** Df flags on poldx (rang 8, CASA 666; 23 heavily flagged channels
  CASA cannot solve; [c6-polterms.md](c6-polterms.md) 222-249); E2-B's 5,242 B and 8,670 Df flag
  differences, reported not gated.
- **Truth with bad intervals: none.** A1 has smooth truth by design ([a1-simtruth.md](a1-simtruth.md)
  83-97); no injected bad gain intervals exist anywhere in `research/`.

So the record holds **one** instance of the target class, already fixed by a classical rule.

### 2.2 Rule (frozen)

A classifier pilot needs a failure class with at least **three independent instances** (different
capture blocks or terms) that no present rule catches, `k_zero_start` and CASA-style minsnr on averaged
cells included. Outcomes:

1. **Null:** fewer than three instances after the probe (section 2.3); the classical rules are the
   answer, and any open classical item is named for the coordinator.
2. **Pilot:** three or more; a pilot note is written (training on injected bad intervals in A1, scored
   on the instances held out).
3. **Incomplete:** the probe cannot run (no blocks fetched); recorded as such.

### 2.3 Probe (frozen, not run): count instances on #39's capture blocks

On every calibrator scan of the nine SARAO blocks of [dl-plan.md](dl-plan.md) decision 6 that #39 has
fetched and converted (each read once for this purpose; no training use): `rang-core calibrate` with
E2-N's calibrate section, `k_zero_start` on and off; then the e2a-3b-diag outlier screen per term
(K |Δτ − median over intervals| > 0.1 ns; G, B relative deviation from the antenna's median over
intervals > 0.1) and, for every outlier, whether rang's flags (minsnr 3, minblperant 4) or an SNR rule on
time- and frequency-averaged model-divided cells (the CASA estimator, already in rang as
`average_freq` and `casa_phase_weights`) catch it. Count the outliers caught by none, per block and term.
Host nash, one shard per block, `--slots 2 --mem 16`. One day.

## 3. Stage 4: polarisation terms (reading of seen results)

- **Cost:** about 2 % of the run (section 1), mostly reads; a warm start cannot save wall time
  (dl0-profile 2.2: iterations are a fraction of a percent of the time-averaged solves).
- **Failure classes:** none in rang on record. CASA drops Gpol intervals at its 50-iteration limit
  (dev 3/4, held 46/48, dev90 45/48, held4 4/4, gpol8 339/360 rows against rang's full set;
  [xf-gap.md](xf-gap.md) 182-192, 340-344, 392-395); rang writes every interval. The c6 misses are
  ill-conditioning (|M_XY|/I = 0.00055 on scan 4), not solver failures (c6-polterms 237-245). Rang's
  Gpol iteration counts were not recorded.
- **Rule (written after reading these):** a pilot needs a cost share ≥ 5 % or one rang failure class.
  **Outcome: null (reading of seen results).** Nothing to learn that rang does not already solve,
  and nothing to save. Not checked: rang's own Gpol iteration counts on the cases where CASA hits its
  limit (a classical observation, not a reason for a network).

## 4. Stage 5a: approximate predict (reading of seen results)

- **Bound:** an infinitely fast predict saves at most 5.5-7.6 % of selfcal (section 1); mode replace
  only, so it could never feed a gated product (dl-plan row 5a).
- **The classical lever is already taken:** GeMClean ships the coarse gridder (f32, ε 1e-4); against f64
  1e-6 it gave 1.6-2.4 × faster major cycles and 1.25-1.46 × faster total wall on S1, H2, H3
  ([gpu-grid.md](gpu-grid.md) 440-445, 492-495); one degrid at f32 1e-4 costs 184 G against 307 G
  instructions at f64 1e-6 ([gridder-theory.md](gridder-theory.md) 112-114). ε of 1e-2 or 1e-3 was never
  timed. The GPU was not faster (gpu-grid 448).
- **Literature:** no neural degridder found ([dl0-profile.md](dl0-profile.md) 1.3).
- **Rule (written after reading these):** a pilot needs a bound ≥ 10 % of selfcal, or a consumer that
  needs approximate predicts faster than the coarse gridder gives them.
  **Outcome: null (reading of seen results).** Named consumer that could change this: the training-data
  factory (#39, the regenerated ASTRODECONV2019), where a point-source DFT predict was 268 of 350 s of a
  simulation in #43 (`dl4c-mask` run root, T1); that is a classical choice (degrid an image at ε 1e-4
  instead of a DFT of components), not a network.

## 5. Outcomes

| Stage | Outcome | Basis |
| --- | --- | --- |
| 3 | **probe pending** (rule 2.2) | one instance on record, fixed classically; probe on #39's blocks when nash returns |
| 4 | **null** (post hoc reading) | about 2 % of the run, mostly reads; no rang failure class |
| 5a | **null** (post hoc reading) | ≤ 7.6 % of selfcal; coarse gridder already shipped; no neural degridder exists |

## For the coordinator

- Stages 4 and 5a: null from the record, labelled post hoc; no host time spent. If you want a blind
  form, stage 5a's would be an ε 1e-2 / 1e-3 timing of the core degridder (classical, an evening on
  glacier after 21:00); I did not plan it, because the bound is below the rule either way.
- Stage 3: one day on nash once #39's blocks are converted; needs nash back.
- Classical items seen, not opened: an SNR rule on averaged cells for G (e2a-3b-k 475-478); rang's
  Gpol iteration counts where CASA stops at 50.
