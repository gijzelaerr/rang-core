# Rang: floor-4, H1's specificity under imaging-floor's full criterion, and the XX−YY phase (issue #13)

Status, 2026-11-17: **measured (section 9): frozen reading row 1, H1 attributed under imaging-floor's
full criterion, share D_T1p 0.83 (fixed model; Sp D_Fix 0.81, D_Fin 0.88). XX − YY: a real steady
phase of 9.5° scatter, invisible to Stokes I.** Protocol frozen in `7bd4fb0` before any run.
Coordinator's decision (owner delegated), 2026-11-17, after [floor-3.md](floor-3.md). Companion protocol for #6:
[selfcal-defaults.md](selfcal-defaults.md); both share the reproduction run of section 5.
Host: **nash** ([nash-host.md](nash-host.md)), every job through the heavy lock with
`RANG_HEAVY_NICE=19`, at most 24 slots in all. Script: `examples/floor4_tests.py` (committed after
this note; it imports `examples/floor_tests.py`, `floor2_tests.py` and `floor3_score.py` unchanged).
Outputs: `~/rang-data/outputs/floor-4-20261117` on nash. Archive: `research/results/floor-4/`.

## 1. Question and priors

floor-3 attributed the pilot's floor to steady per-antenna phase errors **under its own standard**:
one 300 s phase-only `rang-core selfcal` round (Sp) takes the subset floor from 1,073 to 379 µJy
(D_Fix 0.806, D_Fin 0.877), and the solve above 400 m gives the same (0.799, 0.876). Its standard was
a direct correction plus specificity against six incomplete-model arms from floor-2. It was **not**
imaging-floor's full criterion (imaging-floor section 4): a test Tₓ is specific when it removes at
least 0.7 of its own arm's excess power and at most 0.3 of every other arm's. The phase-only and
long-baseline fits were never run on the H2 (bad short baselines), H8a (spectral index) and H4b
(beam) arms. This note runs them, and tests the 17.7° rms steady XX − YY phase floor-3 reported.

Priors, all read before this freeze:

| quantity | value | source |
| --- | --- | --- |
| P_pilot, T (subset) | 1.150e-6 Jy², 44.09 µJy | imaging-floor `summary.json` |
| pilot drops, numpy StefCal: T1, T1p, T1L | 0.854, 0.828, 0.827 | floor-2 `pilot.json` |
| pilot drops, Sp (rang-core): D_Fix, D_Fin; PL | 0.806, 0.877; 0.799, 0.876 | floor-3 section 9 |
| H2 @ a₂ = 25.144: F, P/P_pilot, D_T1 | 1,071.28 µJy, 0.996, 0.197 | imaging-floor `summary.json` |
| H8a @ a₂ = 6.38 (α = −4.5): F, P/P_pilot, D_T1 | 1,083.34 µJy, 1.019, 0.036 | same |
| H4b @ a₂ = 50 (cap): F, P/P_pilot, D_T1 | 390.56 µJy, 0.131, 0.028 | same |
| T1p on floor-2's K1, K3, K10, XS2, XS4, XG4 @ a₂ | 0.104, 0.043, 0.008, 0.000, 0.000, 0.015 | floor-2 11.2 |
| T1L on the same | −0.019, −0.039, 0.122, 0.149, 0.000, 0.000 | floor-2 11.2 |
| H1bP @ 1 (1°, phase only): P/P_pilot; @ 6.862: T1p | 0.0212; 1.000 | floor-2 `summary.json` |
| G3 (the pilot's steady complex T1 gains injected): P/P_pilot | 0.863 | floor-2 11.4 |
| pilot steady σ_φ (floor-2 gauge) | 4.84° (T1p), 4.80° (Sp) | floor-2, floor-3 |
| floor-3 P store, steady δ_p = arg⟨g_X g_Y*⟩ₜ over 60 active antennas | rms 17.7° = circular mean −15.0° and scatter 9.5° about it | computed 2026-11-17 on `D:\rang\outputs\floor-3-20261116\P\run\…\round-1\gains.qc`, before this freeze |

The last row matters for section 4. Each hand is referenced to antenna 0 separately, so a constant
added to every antenna's δ is a gauge: g_X,p g_X,q* and g_Y,p g_Y,q* do not change. Only the scatter
about the mean reaches the data. On a Stokes I score, a differential phase δ_p − δ_q enters as
cos((δ_p − δ_q)/2). That is second order and non-closing in Stokes I. With a scatter of 9.5°, the rms of
(δ_p − δ_q)/2 is 6.7°, an amplitude error of 1 − cos ≈ 0.7 %, against |e^{iφ} − 1| ≈ 12 % for the
4.8° phases. **Prior expectation: under 1 % of the excess** (about (0.0068/0.119)² ≈ 0.003).

## 2. Inputs and provenance

Every input of floor-2 section 2, copied from the workstation to
`~/rang-data/outputs/20261103-gemclean-heldout/real/` on nash (`cal2.ms`, both 3 mJy models, the
mask). The copy is checked by a sorted per-file SHA-256 manifest made on both sides; it must match
file for file. The three FITS must also match floor-2's SHA-256. `research/results/floor-2/pilot-gains.npz`
(in the repository) supplies floor-2's pilot T1p gains for G3P. rang-core, the extension and
GeMClean are nash's build at the run's commit. Commit and GeMClean SHA-256 are recorded.

## 3. Arms and tests (frozen)

**Arms** are built by `floor_tests.make_arm` and `floor2_tests.make`, unchanged: noise seed 1301,
effect seeds as there, 4 × 4 facets summed from 8 × 8 (imaging-floor's construction; H4b needs the
8 × 8 truth facets).

| arm | what | role |
| --- | --- | --- |
| C @ 1 | truth + noise | thermal T, gate |
| H1bP @ 6.862 | floor-2's steady phase-only gains at a₂ | own arm of T1p, gate |
| H1bP @ 5 | the same at a_max (5°) | plausibility (new) |
| G3P | truth × ḡ_p ḡ_q*, ḡ = exp(i arg) of floor-2's pilot T1p steady gains after floor-2's gauge (`gauge(...)["gbar"]`) | plausibility (new) |
| H2 @ 25.144 | 30 short baselines, 50 % steady non-closing errors | specificity (new tests) |
| H8a @ 6.38 | α = −4.5 under a flat model | specificity (new tests) |
| H4b @ 50 | katbeam rotation and chromaticity, 50 × | specificity (new tests) |

**Tests**, each against the arm's own model facets (the truth), 5-min bins, numpy StefCal
(`floor2_tests.stefcal`, 30 iterations):

- T1 (complex), T1p (phase only), T1L (complex, weight zero below 400 m, applied to all), all as
  floor-2;
- **T1pL**: phase only, solved above 400 m only, applied to all. It is the numpy counterpart of
  floor-3's arm PL.

The pilot gets the same four tests against its own 3 mJy model (`cal2-003-gem-model.fits`).

**The simulated tests are scalar fits on Stokes I.** Sp is a per-hand fit. The link between the two
is floor-3's replication: Sp's steady phases correlate with T1p's at r = 0.989, and D_Fix is 0.806
against T1p's 0.828. Specificity is measured on T1p, the fixed-model estimator. **So the share it
licenses is a fixed-model drop:** D_T1p on the pilot. Sp's D_Fix and D_Fin are quoted beside it;
D_Fin includes re-imaging, which no simulated arm tests.

## 4. The XX − YY phase (frozen)

On the reproduction of floor-3's arm P (section 5, G1): its Sp store (300 s, 12 bins), its round-1
model and the pilot's DATA (two hands, the 32 subset channels).

- **X0, decomposition (descriptive).** δ_p = arg mean over bins of g_X,p g_Y,p*. The constant is
  c = the circular mean over active antennas. Reported: rms of δ, c, the scatter
  s = rms wrap(δ_p − c), and s after floor-2's gauge (a fit c + k · r_p).
- **X1, repeatability.** δ_p from bins 1-6 against bins 7-12, each minus its own circular mean.
  Pearson r over active antennas.
- **X2, does it reach the Stokes I floor? (same solve).** Floor-3's Fix score with the per-hand Sp
  gains, against the same gains made scalar: both hands get the phase φ_X + wrap(φ_Y − φ_X)/2, and
  the hand difference is removed. Both corrections are applied to DATA in numpy, per hand, then
  converted to Stokes I by `core_weights.stokes_i`, against the round-1 model.
  ΔD_X2 = D_Fix(per hand) − D_Fix(scalar).
- **X3, matched solvers.** T1p (one phase per antenna on Stokes I) against **T1pH**, the same StefCal
  run on XX and on YY separately, each against the Stokes I model, with that hand's weights.
  The corrected hands are converted to Stokes I as in X2, 5-min bins, against the pilot's round-1
  model. ΔD_X3 = D_T1pH − D_T1p.

**Readings:**

- *Repeatable* if r ≥ 0.7, *noise-like* if r < 0.3, partial otherwise.
- *Reaches Stokes I* if ΔD_X2 ≥ 0.02 or ΔD_X3 ≥ 0.02, the per-hand fit being the better.
  *Costs* if either is ≤ −0.02, the scalar fit being the better: the per-hand freedom fits noise.
  *Invisible to Stokes I* otherwise.

| X1 | X2, X3 | reading |
| --- | --- | --- |
| repeatable | invisible | a real steady per-antenna XX − YY phase of scatter s (the 17.7° rms is c, a gauge, plus s). It does not reach the Stokes I floor. It is a polarisation calibration term, outside #13 |
| repeatable | reaches | a real differential phase that carries ΔD of the excess. The per-hand Sp already removes it; it is part of the floor-3 share, not of the 379 µJy left |
| noise-like | any | the scatter is solve noise: 17.7° is the gauge constant c plus noise |
| partial, or costs | any | undecided, reported |

Limit: the cross hands of `cal2.ms` are absent (zero in the four-correlation copy). So leakage and
an X−Y phase seen through XY and YX cannot be tested here.

## 5. Gates (frozen; tolerances stated for a Linux build)

nash's build may differ from the workstation's in the last bits (other compiler, libm, thread
order). Tolerances:

- **R0, prep** (`floor_tests.prep` on `cal2.ms`): `nrow` and `active` equal; `noise_c` and
  `gridding_weight_sum` within 1e-6 relative of `results/imaging-floor/prep-meta.json`.
- **G0, scoring:** DATA against the archived pilot model, F within 0.1 % of 1,073.42 µJy (floor-3's
  G0).
- **G1, rang-core on nash:** floor-3's arm P rerun on nash (`results/floor-3/p1.yaml`, fresh
  four-correlation copy, `floor3_score.py` stages). F_B, F_Fix and F_Fin each within 1 % of floor-3's
  1,073.42, 474.83 and 379.26 µJy, and D_Fix and D_Fin within ±0.02. Health as floor-3. If G1 fails,
  that is reported. Section 4 and selfcal-defaults then use nash's own numbers; no workstation
  number is mixed with nash's.
- **GS, simulations:** C @ 1 within 0.5 % of 44.09 µJy. The pilot's F(none), F(T1), F(T1p) and
  F(T1L) within 0.5 % of floor-2's `pilot.json`. H1bP @ 6.862: D_T1p within 0.02 of 1.000. H2, H8a
  and H4b at a₂: F(none) within 0.5 % and D_T1 within 0.02 of imaging-floor. If GS fails, no new
  drop is read and the failure is reported.

## 6. Decision rules (frozen)

Drops D are fractions of each arm's own excess power, P = F² − T². They are quoted to ±0.02. Arms
used for specificity are *usable*: P ≥ 0.1 P_pilot and, for the test in question, a defined excess.
All three new arms are usable by the priors.

**S, specificity of T1p (imaging-floor's full criterion).** T1p is specific if its own arm
H1bP @ 6.862 gives D ≥ 0.7 and every other usable hypothesis arm gives D_T1p ≤ 0.3. The other arms
are H2, H8a and H4b (new); K1, K3, K10 (= M), XS2, XS4 and XG4 (floor-2, priors, not rerun). The
same test is applied to T1pL, with own arm H1bP @ 6.862. It is reported and does not enter the
reading. MIX and the G3 controls are mixtures and controls, not hypotheses; they are excluded.

**Q, plausibility.** P_plaus = max(P(H1bP @ 5), P(G3P)). G3P counts because the pilot's own steady
σ_φ (4.84°) lies within a_max (5°). imaging-floor's attribution clause, P(a_max) ≥ 0.5 D P_pilot,
and its unresolved clause, "a pilot drop larger than any plausible amplitude can carry", are read as
one threshold, as imaging-floor 8.4 applied them to T1:

- *holds* if P_plaus ≥ 0.5 D P_pilot, with D = D_T1p on the pilot;
- the note "*the drop exceeds what a plausible amplitude carries by D − P_plaus/P_pilot*" is added
  if P_plaus < D P_pilot;
- *fails* (unresolved) if P_plaus < 0.5 D P_pilot.

**Reading for H1 and #13.**

| S | Q | H1 | #13's done-criterion (imaging-floor section 5) |
| --- | --- | --- | --- |
| specific | holds | **H1 attributed under imaging-floor's full criterion, share D_T1p (pilot, nash; fixed model)**, with Sp's D_Fix and D_Fin quoted | met for H1: a measured share for the one attributed cause. H2 (bound 0.055 after T1) and H8a (bound 0.042) stay unresolved; the remainder 1 − share is reported. Closing #13 is the coordinator's decision |
| not specific on an arm j | any | H1 stays attributed under floor-3's standard only; under the full criterion it is unresolved, upper bound D_T1p shared with j | not met |
| specific | fails | unresolved: the drop is larger than a plausible amplitude can carry, so T1p absorbs something else | not met |
| any gate fails | | void, reported | no change |

The XX − YY reading (section 4) is separate and does not change H1's row.

## 7. Runs

On nash, in this order: copy and manifest; R0 and G0; G1 (shared with selfcal-defaults, 8 slots,
`RAYON_NUM_THREADS=8`); then the simulation job (prep, skies, arms, pilot tests; 8 slots);
then X0-X3 on G1's products. Each heavy command runs as
`nice -n 19 ionice -c3 python3 tools/heavy_lock.py run --slots N --mem G -- …`, wall-timed, with
rows in [tool-timings.md](tool-timings.md) labelled **host nash**. No smoke run on the pilot. A
smoke run of the script on 6,000 rows of a simulated arm, if needed, is declared here and gives no
results.

## 8. Clarifications before any run

**1, 2026-11-17, written with the script, before any run or number.** X3 corrects the data side
for both fits, so the two are matched. T1p's one phase per antenna is applied to XX and to YY
alike; T1pH's two phases are applied each to its own hand. Each pair of corrected hands is then
converted to Stokes I by the same `stokes_from_hands` (floor_tests.prep's `[XX, XX, YY, YY]`
rule) and scored against the archived pilot model's 4 × 4 facet sum. That model is
pixel-identical to floor-3's round-1 model. floor-2's T1p, in section 3's matrix, is the
model-side form V − M g_p g_q*. That form is kept for the specificity reading S, where the arms
were built with it. X2 uses G1's own round-1 model, as section 4 states. The script checks that
the hands reproduce prep's Stokes I bit for bit (`x.json` `check`).

## 9. Results

Measured 2026-11-17 on **nash**. Every job ran through the heavy lock
(`run_nash.sh`, `RANG_HEAVY_NICE=19`, plus `nice -n 19 ionice -c3`): G1 at 8 slots and 20 GB, the
simulation at 8 slots and 24 GB, X0-X3 at 4 slots and 16 GB, all with `RAYON_NUM_THREADS=8`. The
scripts ran from the worktree at `b342702`, and the `rang` package and extension came from nash's
main checkout. The extension `python/rang/_core.abi3.so` was built 2026-11-16 22:39 SAST, SHA-256
`ce12e7d2…c2bc884`, and the stage records the same value as `gemclean_sha256`. The checkout was
at `56d5613` when G1's stage started. Another session fast-forwarded it to `d3746c9` while the stage
ran, so the receipt records `d3746c9`. That pull changed only Rust sources under
`core/src/gemclean`, and the extension was not rebuilt. No smoke run was made.
Archive: [results/floor-4/](results/floor-4/): `summary.json`, `x.json`, `pilot.json`,
`prep-meta.json`, `arms/*.json`, G1's `g1-P-score.json`, `g1-g0.json`, `g1-selfcal-summary.json`
and `g1-f3summary.json`, and the logs `g1.log`, `sim.log`, `x.log`, `sets.log`. The products stay
on nash in `~/rang-data/outputs/floor-4-20261117/`: G1's run directory (stores and models), the
arm gains, and the prep, skies and hands scratch. G1's MS copy was deleted after scoring.

### 9.1 Frozen readings

**Gates. All pass.**

- **Copy:** the sorted per-file SHA-256 manifest of `cal2.ms` matches the workstation's, 70 of 70
  files, and the three FITS match floor-2's hashes (by the previous session, before any run).
- **R0:** `nrow` and `active` are equal. `noise_c` and `gridding_weight_sum` are bit-equal to
  imaging-floor's `prep-meta.json` (relative difference 0.0). nash's build reproduces the
  workstation's prep exactly.
- **G0:** F = 1,073.416 µJy (ratio 0.999996).
- **G1: passes.** Floor-3's arm P on nash gives F_B 1,073.416, F_Fix 474.831 and F_Fin 379.262 µJy.
  These equal floor-3's numbers to the last printed digit: the relative differences are 0, 0 and
  −6e-14. D_Fix is 0.8057 and D_Fin 0.8766 (bit-equal to floor-3; the gate allows ±0.02).
  Health: converged 1.000, solutions flagged 1.6 %, r = 0.989 against floor-2's T1p. G1's round-1 model has 58,314
  components in 5 major cycles, the final 26,357 in 3, both as floor-3. The `f3 summary` in
  `g1.log` prints floor-3's own row 2 because no PL arm was run there; that line is not a reading
  of this protocol.
- **GS: passes**, all 12 checks: C @ 1 gives 44.090 µJy. The pilot's F(none), F(T1), F(T1p) and
  F(T1L) are 1,073.42, 411.91, 446.51 and 448.38 µJy (floor-2's to 0.5 %). H1bP @ 6.862 gives
  D_T1p 1.000. H2, H8a and H4b at a₂ give imaging-floor's F and D_T1.

**Arms** (subset floors in µJy, drops as fractions of the arm's own excess):

| arm | F(none) | P/P_pilot | D_T1 | D_T1p | D_T1L | D_T1pL |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| H1bP @ 6.862 (own) | 1,068.50 | 0.991 | 1.000 | **1.000** | 1.000 | 1.000 |
| H1bP @ 5 | 780.85 | 0.528 | 1.000 | 1.000 | 1.000 | 1.000 |
| G3P | 975.00 | 0.825 | 1.000 | 1.000 | 1.000 | 1.000 |
| H2 @ 25.144 | 1,071.28 | 0.996 | 0.197 | **0.092** | 0.001 | 0.004 |
| H8a @ 6.38 | 1,083.34 | 1.019 | 0.036 | **0.000** | 0.017 | 0.000 |
| H4b @ 50 | 390.56 | 0.131 | 0.028 | **0.004** | 0.006 | −0.003 |
| pilot (3 mJy model) | 1,073.42 | 1.000 | 0.854 | **0.828** | 0.827 | 0.812 |

**S: T1p is specific.** Its own arm gives 1.000 ≥ 0.7. Every other usable hypothesis arm is
≤ 0.3: the new arms H2 0.092, H8a 0.000 and H4b 0.004, and floor-2's priors K1 0.104 (the largest),
K3 0.043, K10 0.008, XS2 0.000, XS4 0.000 and XG4 0.015. All three new arms are usable
(P/P_pilot 0.996, 1.019, 0.131 ≥ 0.1). **T1pL is also specific** (reported only). Its own arm gives
1.000 and the new arms at most 0.004; floor-2 ran no T1pL on its arms.

**Q: holds.** P_plaus = max(P(H1bP @ 5), P(G3P)) = max(0.528, 0.825) P_pilot = 0.825 P_pilot,
at least 0.5 × D_T1p = 0.414. Because P_plaus < D P_pilot, the frozen note applies: *the drop
exceeds what a plausible amplitude carries by 0.828 − 0.825 = 0.004*, which is inside the ±0.02
quoting band.

**Reading (frozen table, row 1): H1 attributed under imaging-floor's full criterion, share
D_T1p = 0.83** (pilot, nash, fixed model; 0.8284). Sp on the same data gives D_Fix 0.81 and
D_Fin 0.88 (G1). **#13's done-criterion is met for H1**: a measured share for the one attributed
cause. H2 (bound 0.055 after T1) and H8a (bound 0.042) stay unresolved. The remainder, 1 − 0.83 =
0.17 of the excess against the fixed model, or 0.12 after Sp and re-imaging, is unattributed.
Closing #13 is the coordinator's decision.

**XX − YY (section 4).** `check`: the hands reproduce prep's Stokes I and weights bit for bit.

- **X0:** δ has rms 17.72° over 60 active antennas, which is a circular mean c = −14.97° plus a
  scatter s = 9.48° (9.44° after floor-2's gauge). Per-bin deviations from the steady δ are 0.54°
  rms, so the noise of the 12-bin mean is about 0.16°.
- **X1: repeatable**, r = 0.999 between bins 1-6 and 7-12.
- **X2:** the per-hand Sp gains give D_Fix 0.806, and the same gains made scalar give 0.819:
  ΔD_X2 = **−0.013**.
- **X3:** T1p (data-side) gives D 0.829 and T1pH gives 0.816: ΔD_X3 = **−0.013**. T1pH's own XX − YY
  scatter is 9.63° and correlates with Sp's at r = 0.9996.
- Both ΔD lie within ±0.02. **Reading: invisible to Stokes I.** Together with X1 (repeatable),
  the frozen row applies: a real steady per-antenna XX − YY phase of scatter 9.5°. The 17.7° rms
  is the gauge constant c (−15.0°) plus that scatter. It does not reach the Stokes I floor. It is
  a polarisation calibration term, outside #13.
- **HB1** (selfcal-defaults' gate, computed here): the numpy per-hand apply reproduces
  `floor3_score`'s F_Fix with relative difference 0.0. **Passes.**

### 9.2 Post hoc remarks (not part of the frozen reading)

- **The per-hand fit costs a little.** In X2 and X3 alike the per-hand correction scores
  0.013 worse than the scalar one, consistently in two independent solvers, but inside the
  ±0.02 "invisible" band. That fits the prior: the differential phase enters Stokes I at second
  order, while the per-hand freedom adds solve noise. It also explains why floor-3's Sp
  (per hand, D_Fix 0.806) came out 0.022 below floor-2's T1p (scalar, 0.828).
- **Plausibility is tight but not marginal for the rule.** G3P, the pilot's own steady phases
  injected into the truth, carries 0.825 P_pilot, almost exactly D_T1p. H1bP @ 5 alone (0.528)
  would also have passed the 0.414 threshold.
- **Remaining.** H2's T1p drop (0.092) is the largest new cross-term and is below K1's prior
  (0.104). The long-baseline phase fit (T1pL) is cleaner still (≤ 0.004 on every new arm), but
  it has no floor-2 rows.
- **Host.** Every gate reproduced the workstation exactly (R0, G0, G1 bit-equal), so nash's
  Broadwell build gives the same numbers as the Windows host for this chain.

