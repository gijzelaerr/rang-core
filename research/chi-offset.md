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
