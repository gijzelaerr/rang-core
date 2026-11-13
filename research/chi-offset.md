# Chi-offset: why E2-B's absolute 3C 286 angle is wrong in rang and CASA alike

Status: **proposal, frozen 2026-11-13** before any run of this task. Results
and later changes go in dated sections below the freeze line.

## 1. The observation (E2's, read before this note)

E2-B's frozen arm (`research/e2-acceptance.md` 6, branch `fp-e2-acceptance`
section 7.1, `D:\rang\outputs\e2-20261111-20-e2b\rows-parity.json`): rang and
CASA give the same 3C 286 angle (parity |Δχ| ≤ 0.08°), and both are far from
the model's 33°. At 1.3-1.5 GHz, ψ at the array centre:

| Scan | ψ | Model χ (MODEL_DATA) | Corrected χ | Offset | Xf solved on |
| --- | --- | --- | --- | --- | --- |
| dev scan 1 (dry-run slice) | −169.2° | 32.7° | 88° | +55.0° | dev scan 1 |
| scan 17 (E2-B) | +146.4° | 30.0° | −3.2° | −33.2° | scan 17 |

Across the band on scan 17, χ runs from −0.5° (1.0 GHz) to −4.2° (1.65 GHz).
Corrected scan 17: q +0.099, u −0.011 (model q +0.052, u +0.090). The offset
changes by about 88° (mod 180) for Δψ = −44.4°, about 2Δψ. The configuration
is CARACal strategy 1: `feed_angle_rotation: -90` (LUNO's FEED stores 0, so
−90° is set in memory for rang and written into CASA's copy), `parang: true`
on Gpol, KCROSS, Xf, Df and the apply.

Seen before the freeze: the LUNO store's metadata (FEED RECEPTOR_ANGLE 0,
CORR_TYPE XX XY YX YY, observer B Hugo, project 20210818-0008; HISTORY lists
CASA 5.6 flagdata, setjy and applycal with parang false, all of which write
other columns than DATA). No data cell was read by this task before the freeze.

## 2. Conventions used for the predictions

P_p = [[cos a, sin a], [−sin a, cos a]], a = ψ + θ (θ the receptor angle);
data V = Xf P M Pᵀ Xfᴴ in the feed frame. Then (Q_f + iU_f) = (Q + iU)e^{−2ia},
so χ_f = χ − ψ − θ. Q_f, the parallel hands' (XX − YY)/2 after K, G, B, does
not depend on Xf; U_f does, through the cross-hand phase. With linear feeds Xf
cannot rotate (Q, U); it rotates U into V, and a solve against a model picks
the branch whose U sign matches the model's U in the configured frame.

## 3. Hypotheses and what each predicts

χ_c is the configured receptor angle (−90°), θ_t the true one, ψ the
parallactic angle rang and CASA compute.

- **H1. P has the wrong sense for these data** (ψ_true = −ψ + const: an
  hour-angle, longitude or time error in the metadata, or a sign error that
  rang and CASA share). Predicts: χ_sky = s χ0 ± 2ψ + c with one Xf for all
  scans; a receptor-angle change alone does not remove the ψ slope; in the
  simulation, data made with −ψ reproduce the slope; an independent ψ
  (astropy, MeerKAT's surveyed site, the scan times and 3C 286's J2000
  position) differs from the MS-derived ψ in sign or by more than 1°.
- **H2. `parang` off in one solve or the apply.** Predicts a ψ-dependent error
  of slope ±1 (not ±2) between scans, and a disagreement between rang and
  CASA unless both are configured alike. Checked in the configurations and,
  in the simulation, by turning parang off in Gpol, KCROSS, Xf in turn.
- **H3. The receptor angle is wrong** (θ_t ≈ 0 for LUNO's labelling, not the
  configured −90°). Q_f has the wrong sign against the configured model, so
  the Xf solve flips U to match; the result is χ_sky = −χ0 + 2ψ + 2θ_c + 90°
  (mod 180) = −χ0 + 2ψ − 90° for θ_c = −90°: −10° on scan 17 and +79° on dev
  scan 1 (E2: −3°, +88°; the remaining +7° to +9° would be θ_t − 0 or
  calibration error). Predicts: the Xf-free Q_f against ψ fits θ_t within
  15° of 0 (mod 180) and not −90°; rerunning the chain with the receptor
  angle 0 gives χ within 7° of 33° on both 3C 286 scans and no 2ψ slope;
  the simulation with θ_t = 0 and θ_c = −90° reproduces E2's numbers.
- **H4. Cross-hand phase branch alone** (Xf off by 180°, frame right):
  χ → −χ0, sky q unchanged (+0.052 on scan 17). E2's q +0.099 already argues
  against it; predicted constant across scans.
- **H5. The 3C 286 model's reference frequency or angle convention.**
  Predicts MODEL_DATA's χ ≠ 33° (beyond the model's own spectrum) and an
  offset independent of ψ. Checked on MODEL_DATA per scan and in the
  simulation by the model the chain uses.
- **H6. Gpol or Xf absorbs the parallactic angle when one scan or a narrow
  ψ range is used.** Predicts in the simulation (frame right) a χ error that
  grows as the solve's ψ range shrinks; with the frame right and Xf from one
  scan, χ on other scans off by more than 2°.

## 4. Method

1. **Simulation** (`rang.simtruth` `poldx`, the noiseless twin: 16 MeerKAT
   antennas, 256 channels, 3C286-SIM with p 9.5 %, χ 33°, RM 0, four scans
   spanning about 115° of ψ, and J1939−6342 unpolarised with leakages).
   Truths: (a) θ_t = −90° (control; as C6/C6w), (b) θ_t = 0 with FEED 0 (H3,
   LUNO-like), (c) θ_t = −90° with the sense of ψ reversed in the corruption
   (H1). The chain is E2-B's polcal shape (`e2b.yaml`'s calibrate and apply:
   K, G, B on the fcal, Gpol p 60 s, KCROSS, Xf, Df, parang true,
   `feed_angle_rotation: -90`), in rang (`rang-core calibrate`, `apply`) and
   CASA 6.7.6.14 (WSL container, `examples/oracle_pol.py`), and toggled:
   receptor angle −90 / 0, parang off per term (rang), Xf from one scan.
   Measured: χ and p per 3C286-SIM scan against ψ (the estimator of
   `e2_rows_b.py`: unit-weight mean of the corrected correlations, all four
   unflagged), plus the Xf-free Q_f per integration.
2. **E2-B, read-only.** Per integration of scan 17 (frozen CASA copy,
   RANG_CORRECTED_DATA and CORRECTED_DATA) and dev scan 1 (dry-run copy):
   χ_sky, Q_f (P undone with the applied −90°), ψ; fit of θ_t from Q_f with
   the model χ0. Independent ψ from astropy against the MS-derived ψ.
3. **LUNO rerun, my own copy** (`e2_convert.py build` of MAIN_0, MAIN_1,
   MAIN_16, MAIN_17 with `--rows`, under `D:\rang\outputs\chi-offset-*`):
   the dev chain with the receptor angle −90° and 0, rang and CASA; χ on
   both 3C 286 scans, each with its own and with the other's Xf.

## 5. Decision rule (frozen)

- **H3 accepted** when all of: (i) Q_f fits θ_t within 15° of 0 (mod 180)
  on E2-B's two scans; (ii) simulation (b) with θ_c = −90° reproduces the sign
  pattern (offset slope ±2 per degree of ψ, |χ − (−χ0 + 2ψ − 90°)| ≤ 3° per
  scan) in rang and CASA, and (b) with θ_c = 0 recovers 33° within 1.11°
  (C6w's tolerance); (iii) the LUNO rerun with θ_c = 0 gives |χ − 33.1°| ≤ 7°
  (A0's transfer limit) on both 3C 286 scans, with Xf from either scan.
- **H1 accepted** instead when (iii) fails with a ψ slope that survives
  θ_c = 0, and the independent ψ differs in sign from the MS-derived ψ.
- **H2, H4, H5, H6** are accepted only if their own prediction holds and H3's
  (iii) fails; otherwise reported as excluded with the number that excludes
  them.
- Neither: report "cause not found" with every measurement.

**If H3 is accepted, the fix** is configuration: `feed_angle_rotation`
omitted (FEED's stored 0 used) or 0 for this data product. Rang's default is
not changed unless the cause is shown to hold for MeerKAT data generally
(it depends on the producer's X/Y labelling; ESO137's store holds −90°), so
the choice is stated for the owner. E2's frozen protocol and code are not
touched.

---

(Results below this line, dated.)

## 6. Post-freeze addition (2026-11-13, before any chain run; labelled post hoc)

Read after the freeze, from E2's committed outputs only (no new run):

- **ψ from the metadata is right.** Astropy (MeerKAT site −30.713°, 21.443°;
  3C 286 J2000; scan 17's first and last TIME) gives 147.11° and 145.27° at
  HA +2.43 h and +2.60 h; rang's CASA-frame angles give 147.18° and 145.33°.
  The MS's array centre is at −30.712°, 21.442°. The metadata part of H1 is
  excluded.
- **Scan 17 in the feed frame** (E2's q +0.099, u −0.011 rotated back by
  a = ψ − 90°): q_f −0.049, u_f −0.087. The model in the same frame: q_f
  +0.063, u_f −0.083. The Xf-free parallel hands disagree with the model in
  sign; the cross hands agree. That is H3's signature: a frame error in Q_f,
  with Xf having matched U_f to the model.
- **χ against λ² on scan 17** (`rows-parity.json`, seven bins, weighted by the
  unflagged fraction): slope +77.6°/m² (rang) and +79.9°/m² (CASA), i.e.
  RM_app +1.35 and +1.39 rad m⁻²; intercept −6.9° and −7.0°; residuals
  ≤ 0.15° except the 7 %-unflagged bin (0.5°). Under H3 the measured angle
  is −χ_true(λ) + 2ψ + θ_t − 90°, so a real RM enters with the opposite
  sign: RM_true ≈ −1.35 rad m⁻² (ionospheric size), and the intercept gives
  θ_t ≈ +3.5° (mod 180) for χ0 = 33°.
- **Added prediction (H3), for the reruns with the receptor angle 0:** on
  each 3C 286 scan, χ = χ0 + RM λ² − θ_t with the RM slope **negative**
  (sign flipped against the −90° arm), χ ≈ 26-30° at 1.4 GHz on scan 17
  (33° − 3.6° (RM) − up to 3.5° (θ_t)). Under H1 the slope sign would not
  flip with the receptor angle.

## 7. Paused 2026-11-13 (owner's stop order; no chain run made)

**Status.** H3 (receptor angle wrong for this product: θ_t ≈ 0, configured
−90°) is the leading hypothesis on E2's committed outputs alone (section 6:
ψ correct to 0.07°, Q_f wrong in sign against the model while U_f agrees,
χ against λ² linear with intercept giving θ_t ≈ +3.5°). The decision rule
(section 5) is **not yet evaluated**: (i) the per-integration Q_f fit, (ii)
the simulation and (iii) the LUNO rerun have not run. H1 (metadata part)
is excluded; H2, H4, H5, H6 are open. H5 note: MODEL_DATA through the
estimator reads χ 30.0°, p 0.104 on scan 17 (expected 33°, 0.098); check it
on the rerun's own MS.

**Nothing measured since section 6.** All jobs were queued behind E2 on a
full host (16/16 slots) when stopped; the queued tickets and the empty
output folders (`D:\rang\outputs\chi-offset-20261113-0{1,2-sim,3-luno}`)
were removed. E2's run directories were never opened for writing.

**Scripts** (`research/results/chi-offset/`, untested end to end):
`chi_vs_psi.py` (χ, ψ, q_f, u_f per integration, read-only), `sim_chi.py`
(gen control/feed0/revpsi truths; rang arms m90/null/gpol_noparang; CASA
arms m90/feedms; score), `luno_rerun.py` (own 6-integration copy of LUNO
scans 1, 2, 17, 18; build+flag; rang m90/null; CASA m90/feed0; score per
band), `chain.sh` (the queued order and lock sizes).

**Resume, in order** (main checkout's heavy_lock, shared slots):
1. `maturin develop --release` in the worktree venv (8 slots, 8 GB).
2. `sim_chi.py gen {control,feed0,revpsi} D:/rang/outputs/chi-offset-<date>-sim`
   (4 slots, 4 GB each), then `chain.sh` (fix its SIM/LUNO paths to the new
   date). Rule (ii): feed0+m90 per scan within 3° of −χ0 + 2ψ − 90°;
   feed0+null within 1.11° of 33°; control 33°.
3. LUNO rerun: rule (iii), null arm |χ − 33.1°| ≤ 7° on scans 1 and 17,
   RM slope negative (section 6's prediction).
4. Optional H6 arm: Xf from one scan in the sim.
5. Rule (i) on E2-B scan 17 with `chi_vs_psi.py` only after E2 reports done
   (read-only on `R\casa\e2b.ms`).
6. Results section, compact JSON archive, full check, hand back. The fix if
   H3 holds: `feed_angle_rotation: null` (or 0) for the LUNO product; rang's
   default unchanged; the choice is the owner's.

## 8. Resumed 2026-11-13: the control gate and `average_time` (post hoc, before the rule)

Run root `D:\rang\outputs\chi-offset-20261113-*`; worktree venv built from
54bd119 (`maturin develop --release`, 3 min 09 s compile). The three truths
were generated as section 4.1 (`gen` 4.6-5.3 s each; feed0's FEED reads 0,
control's and revpsi's −90).

**The control gate failed with the chain as frozen.** `rang control m90`
(`calibrate.average_time: true`, as e2b.yaml) gave χ 49.51°, 38.16°, 33.57°,
33.35° on 3C286-SIM scans 2, 8, 14, 22 (ψ −121.2°, −140.4°, +167.8°,
+122.9°), p 0.062, 0.093, 0.028, 0.095 against the truth's 33°, 0.095, and
|V| up to 0.093 (truth 0): U_f rotated into V by about 90°. The same arm with
`average_time: false` (`m90_noavg`): 33.38°, 33.86°, 33.00°, 33.95°, p
0.0935-0.0952. CASA's chain on the same truth (`casa control feedms`):
the same four values to 0.01°. The tables of the two rang arms are equal
for K, G, B, Gpol (≤ 1.8e-6), KCROSS (≤ 8e-4 ns); **Xf differs by 78° median,
107° max**.

Measured: toggling `average_time` alone moves Xf by 78° (median); the
no-average arm equals CASA. Cause, **inferred, not measured** (read from
`rang.cal_pol.xf` and `core/src/cal/crosshand.rs`): with
`average_time` the Xf solve (solint inf, `combine: scan`) runs on rows
averaged across the whole interval, here all four 3C286-SIM scans (115° of
ψ). The model is rotated by P per row before averaging, so the averaged
polarised cross-hand model decoheres while the leakage terms (d·I, not
rotating) do not, and Xf's closed form `arg Σ w V M*` is then set by the
leakage. CASA's spec here sets no `preavg`, so polcal ran on its default
(300 s by CASA's documentation; not checked in this run). E2-B's Xf was
solved on one scan (Δψ ≈ 2°); measured support that this is a separate defect
and not E2's offset: on the LUNO reruns (single-scan Xf, `average_time` on)
rang equals CASA to 0.03° (section 9). **Owner
item: `calibrate.average_time` must not average Xf (or any polarised-model
solve) across a ψ range; proposed fix: cap the averaging at CASA's preavg or
at a ψ step.** Not fixed in this task.

Consequence for this protocol (post hoc): every sim and LUNO arm is run both
as frozen (`average_time: true`) and with `average_time: false` (`*_noavg`);
the rule is evaluated on both and the `_noavg` arms are the ones that test the
frame question.

## 9. Results and the frozen rule (2026-11-13)

Archive: `research/results/chi-offset/results.json` (the sim, LUNO and E2-B
θ fits; the Xf table comparison, the own-rerun θ fits and the RM-corrected
θ_t are quoted here only, from `-04-qf` and the arm directories);
run roots `D:\rang\outputs\chi-offset-20261113-02-sim`, `-03-luno-s17`,
`-03-luno-s1`, `-04-qf`, `-05-eval`. Scripts: `sim_chi.py`, `luno_rerun.py`,
`chi_vs_psi.py`, `evaluate.py`, `chain.sh` (this directory). Deviations
from section 4, all post hoc: `_noavg` arms (section 8); the LUNO rerun is
two sub-runs because the local store holds MAIN_16-19 only (scans 1-2 exist
only in the dry run's slice, copied before E2 deleted the dry-run directory;
its config is kept verbatim as `dryrun-b-config.yaml`), so each 3C 286 scan
has its own Xf and the combined and other-scan Xf arms were not possible;
LUNO `null_noavg` was refused by rang's memory limit (14.7 GiB per interval)
and is unnecessary there (one scan per Xf, Δψ < 2°). The s1 copy carries the
FLAG column as the dry run left it (flag stage plus whatever its calibrate
and apply stages flagged); its flag backup went with the deleted directory.
**Planned in section 4 and not run:** the KCROSS and Xf parang-off toggles
(only Gpol's was run), the sim arm with Xf from one scan (H6), the LUNO
`null_own`/`m90_own` arms and every LUNO arm with another scan's Xf.

**(i) Q_f, Xf-free** (`chi_vs_psi.py`, 1.3-1.5 GHz, q_f = p_m cos 2(χ_m − ψ − θ),
model p_m 0.098, χ_m 32.93-32.96° from MODEL_DATA, no RM):

| Data | n int | ψ | q_f | θ_t minima (rms q) | rms at 0 / −90° |
| --- | --- | --- | --- | --- | --- |
| E2-B frozen `casa/e2b.ms` scan 17 (read-only, after E2 reported done) | 74 | 145.3-147.2° | −0.0445 | **+8.2° (0.0004)**, −54.9° (0.0035) | 0.023 / 0.112 |
| dry-run slice scan 1 | 13 | −169.4° | +0.0873 | **+8.6° (0.0008)**, +35.7° (0.0012) | 0.017 / 0.158 |
| joint | 87 | | | **+8.2° (0.0005)**; next −41.2° (0.065) | |

Own reruns (CASA m90): scan 17 +7.4°, scan 1 +8.3°. **Pass** (within 15° of 0;
−90° excluded by 0.11-0.16 rms against 0.0005). With the RM measured in (iii)
(χ at 1.4 GHz 3.6° and 5.6° below the model) θ_t ≈ +4.4° and +2.7°.

**(ii) Simulation** (four 3C286-SIM scans, ψ −121.2°, −140.4°, +167.8°, +122.9°):

| Arm | χ per scan | max \|χ − H3 pred\| | slope dχ/dψ | max \|χ − 33°\| |
| --- | --- | --- | --- | --- |
| control, rang `m90_noavg` = CASA | 33.38, 33.86, 33.00, 33.95 | – | 0.0 | 0.95° |
| feed0 + −90, rang `m90_noavg` = CASA `m90` | −5.72, −44.43, 32.54, −58.01 | **0.9°** | **2.0** | – |
| feed0 + 0, rang `null_noavg` / CASA `feedms` | 33.29, 33.59, 33.00, 33.80 | – | 0.0 | **0.80°** |
| revpsi (H1) + −90, rang = CASA | −28.35, −67.25, 9.23, −80.58 | 23.0-23.5° (constant) | 2.0 | – |
| control, rang `m90` as frozen (`average_time`) | 49.51, 38.16, 33.57, 33.35 | – | – | 16.5° |
| feed0 + −90 / + 0, rang as frozen | −41.8, −52.5, −56.5, −56.7 / 60.1, 39.6, −62.6, 32.8 | 89.0° | 0.0 / 2.0 | – |

rang `_noavg` and CASA agree to ≤ 0.01°. **Pass in rang (`_noavg`, post hoc)
and CASA; fail in rang as frozen**, for the `average_time` defect of section 8,
not for the frame. H1's truth gives the 2ψ slope too but sits a constant
−23° off H3's line; it is distinguishable and the LUNO data do not show it.
`gpol_noparang` equals `m90` to 0.01° (phase-only Gpol: Q changes the
parallel hands' amplitude, not their phase), so H2 via Gpol is excluded.

**(iii) LUNO rerun, own copies** (1.3-1.5 GHz; rang = CASA within 0.03°):

| Sub-run | ψ | χ, receptor −90 (rang / CASA) | χ, receptor 0 (rang / CASA) | \|χ − 33.1\| at 0 | RM at −90 / 0 (rad m⁻²) | χ(λ²=0) at 0 |
| --- | --- | --- | --- | --- | --- | --- |
| s17 (scan 17, Xf scan 17) | +147° | −1.36 / −1.39 | 25.61 / 25.63 | **7.49 / 7.47** | +1.35 / −1.35 (CASA ±1.39) | 29.24 / 29.37 |
| s1 (scan 1, Xf scan 1) | −169° | 87.79 / 87.80 | 23.80 / 23.79 | **9.30 / 9.31** | +2.09 / −2.09 (CASA ±2.14) | 29.42 / 29.43 |

p 0.0967-0.0971 in every arm (model 0.098). **Fail**: 7.47° and 9.31° against
the frozen 7°. What the receptor angle 0 does: the scan-to-scan difference
falls from 89.2° (H3 predicts 87.0°: −χ0 + 2ψ − 90° gives −8.8° and +78.2°, observed −1.4° and +87.8°) to 1.8° at 1.3-1.5 GHz and to 0.06° at
λ² = 0; the RM changes sign as section 6 predicted; what is left is a constant
−3.6° (χ(λ²=0) 29.4° on both scans against 33°) plus Faraday rotation of
−1.4 and −2.1 rad m⁻² (ionospheric size, different 2.4 h apart). The 7° limit
(A0's transfer limit) did not budget an RM of this size: at 1.4 GHz it
is 3.6° and 5.6°.

**Verdict against the frozen rule.** (i) pass, (ii) pass in CASA and in
rang without `average_time` (fail as frozen, separate defect), (iii) fail by
0.47° and 2.31°. **H3 is not accepted as frozen.** H1 is excluded: ψ is right
(section 6, 0.07°) and no ψ slope survives the receptor angle 0. H2 excluded
(Gpol: no effect; a slope ±1 is absent: the slope is 2 at −90° and 0 at 0).
H4 excluded (the offset is not constant: 89° change for Δψ 44°). H5 excluded
as the cause (MODEL_DATA χ 32.93-32.96°, p 0.098 on the rerun MSs; the offset
is ψ-dependent); E2's 30.0° MODEL_DATA reading is not reproduced here. H6 not
supported but not tested as planned (own-scan Xf on both scans gives the same
χ(λ²=0) to 0.06°; no scan was given another scan's Xf, and the sim one-scan
arm was not run). By the
frozen rule's letter: "cause not found" for H3's absolute tolerance.

**Post hoc reading (labelled).** The measurements say the configured receptor
angle −90° is wrong for this LUNO product by 90° (θ_t ≈ 0, more precisely
+3 to +8° depending on whether the RM is modelled), Xf then forces U into the
model's sign, and E2-B's χ is −χ0 + 2ψ − 90° plus Faraday rotation. The part
of the frozen rule that fails is the absolute 7°, which is consumed by the
ionospheric RM (not in the 3C 286 model, RM 0) and a residual 3.6°. A dated
follow-up rule would compare χ(λ²=0) or RM-corrected χ with 33°.

## 10. Owner decisions

1. **LUNO receptor angle.** Proposed: `calibrate.polcal.feed_angle_rotation:
   null` (FEED's stored 0) for the LUNO calibrator product
   (`LBAND_LUNO_CALIBRATORS`), i.e. drop CARACal strategy 1's −90 in E2-B's
   config for this product only. Evidence: (i) θ_t +8.2° (−90° excluded);
   (iii) with 0, the 2ψ slope and the RM sign flip vanish, χ(λ²=0) 29.4° on
   both scans; rang = CASA. Not applied: rang's default is already null; the
   −90 is in E2-B's frozen config and CARACal's strategy, which is right for
   stores that hold −90 (ESO137) and for producers whose X/Y labelling
   matches. Whether other MeerKAT products need 0 is open (one product seen).
2. **Accept or not under a post hoc rule.** H3 failed the frozen absolute
   limit by 0.47° and 2.31°; the owner decides whether the RM-corrected
   reading (χ(λ²=0) 29.4°, 3.6° from 33°) closes the question, or whether a
   dated follow-up with an RM term in the 3C 286 model is wanted.
3. **`calibrate.average_time` and Xf** (section 8): with `combine: scan`
   over scans at different ψ, Xf is wrong by 78° (sim); any E2/E3 run that
   solves Xf across several 3C 286 scans with `average_time` on is affected.
   Proposed fix: cap the pre-averaging of polarised-model solves at CASA's
   `preavg` (300 s) or a ψ step. Not fixed here.

## For the coordinator

Branch `claude/chi-offset-80cb6a`; research files only (`research/chi-offset.md`,
`research/results/chi-offset/`, `research/tool-timings.md`); no package code
changed. Checks: only `ruff check`/`ruff format --check` on the scripts ran;
the full check (step 6) was not run here and is left to the coordinator's
merge check (no code under `python/`, `core/`, `src/` touched; this branch
predates `tools/check_all.py`). Run outputs on D: (sim 7 GB, LUNO
bases s17 4 GB and s1 18 GB kept for a follow-up; arm MSs deleted after
scoring). **`-03-luno-s1/base/luno4.ms` is now the only local copy of raw
LUNO scans 1-2: do not wipe it.**
