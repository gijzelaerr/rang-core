# DD8: the off-axis model gap in simulation, a held-out accuracy measure, and how much is iterations

Issue #15. Follows [dd7-cause.md](dd7-cause.md) (DD7), [dd6-d0.md](dd6-d0.md)
and [dd5-sim.md](dd5-sim.md). Branch `dd8-offaxis`. Coordinator brief
2026-11-25. A diagnostic, not a fix: no claim of better calibration or
imaging follows from it. Sections 1-8 are frozen 2026-11-25, before the code
that runs them and before any measurement. Later changes are dated
amendments, written before the reading they affect.

Status: **proposed** (frozen, nothing run).

## 1. Questions

DD7 measured that the real d0-free solve at 4 × 8 s (MF-4) is slow, not stuck
(cap 500: 0.066, 0.042, 0.011 in d1-d3; cap 2000: 0.530, 0.501, 0.465), that
the deep clean as every facet's model is the one removal that lifts it at
cap 500 (R2: 0.304, 0.297, 0.297) but does worse at 64 × 8 s (R2-64: 0.254,
0.255, 0.256 against MF-64's 0.794, 0.754, 0.752), and that flagging the
145 bad baselines helps without being enough (R1). It left three items, which
DD8 runs:

1. **Insertion (Q1).** Does the off-axis model gap at its real size, inserted
   into the exact simulation B, reproduce the real failure? This is the
   insertion arm DD7's candidate 4 lacked.
2. **Accuracy (Q2).** Convergence does not certify accuracy (DD6, C-MF-64).
   Does a held-out-baseline prediction error measure gain quality on real
   data, and, if so, which real solutions are better?
3. **Iterations and the combination (Q3).** How much of the gap at 16 and
   64 × 8 s is iterations (cap 2000), and does flagging the 145 bad baselines
   add to the deep off-axis model (R1 + R2, a diagnostic, not a model
   proposal)?

Not done (brief): the unit-gain deep clean is not adopted as the off-axis
model. R1 + R2 uses it only as DD7's diagnostic did.

## 2. Data and inputs

DD7's run root `D:/rang/outputs/dd7-20261125/` is read only. DD8's run root
is `D:/rang/outputs/dd8-20261125/`; everything DD8 builds or writes goes
there.

- Real subset: DD7's `real/sub.ms` (823,500 rows = 1,830 baselines × 450
  integrations, 64 channels, 61 antennas, four facets d0-d3).
- Simulation B: DD7's `b/sim.ms`, sky M₀ᶜ = `b/sky.npy`, truth gains
  `b/truth.npz` (per 4 integrations, d0 exactly 1), k = 0.5291, noise
  `dd7.regen_noise` (seed 5501).
- Models: `models/RM.npy` (RM, DD6's M: deep clean in d0, M₀ᶜ elsewhere),
  `models/DEEP.npy` (the deep clean in every facet). Per facet (DD7 G2):
  DEEP 60.518, 4.429, 0.774, 0.049 Jy; M₀ᶜ 44.317, 2.825, 0.451, 0.204 Jy.
- The 145 bad baselines: `badbaselines.json` of gemclean-heldout, as DD7.

**Setup gates (frozen; a miss is a setup outcome: stop that item and report):**
- **G1.** The DD7 inputs' SHA-256 recorded; `RM.npy`, `DEEP.npy` and
  `b/sky.npy` per-facet fluxes equal DD7's G2.json to 1e-6 Jy.
- **GO** (the insertion build, section 3): the inserted sky's signed flux per
  facet is DEEP − M₀ᶜ = +1.604, +0.323, −0.155 Jy in d1-d3 (0 in d0) to
  1e-3 Jy; Σ|DEEP − M₀ᶜ| per facet reported (the size of the error, not its
  net); the built `DATA` equals `predict(sky O, truth gains) + n` to 1e-3 Jy
  maximum absolute on unflagged cells, with `DATA_B − n` equal to
  `predict(sky B)` to 1e-3 Jy (DD7's G3, repeated).
- **GR** (the two rebuilt removal copies, section 5): R1 flags 65,250 rows
  (DD7 `builds/R1.json`); R1c's control baselines equal DD7's
  `builds/R1c.json` list.
- **GH** (the held-out draw, section 4): 10 % of the non-bad baselines in
  each of DD7's length bins (0-100, 100-200, 200-400, 400-1000, 1000-2000,
  2000-4000, > 4000 m), rounded, seed 8801; no bad baseline; every antenna
  on at least one held-out baseline (if not, seed 8802, 8803, ... up to 100
  tries, recorded). Count, weight share and per-bin counts reported.
- **V1** (the scorer, section 4): on B-H's held-out cells, the truth gains
  with sky B give H within 0.01 of 1.

All solves as DD7: `diag_complex`, stop criterion 1e-7, stop fraction 0.99,
`refant=None`, full band, DD5's grid solve with its one-longer second solve,
cap 500 unless stated. Converged fraction per direction and its levels as
DD5 A1 (≥ 0.99 converges, > 0.10 partly, ≤ 0.10 does not); **lifted** =
every one of d1-d3 above 0.10; step median as DD7 section 4; `e/ê` and
**accurate** (`e ≤ 2ê`) as DD5 on simulations.

## 3. Q1: the off-axis insertion into B

**Build O.** A copy of B's `sim.ms` with
`DATA_O = DATA_B + Σ_{f=1..3} G_f · predict((DEEP − M₀ᶜ) restricted to facet f) · G_f^H`,
G_f B's truth gains. So sky O = M₀ᶜ in d0 and DEEP in d1-d3; noise, flags,
weights, UVW and `truth.npz` are B's. Gate GO.

**Points (4 × 8 s, cap 500 unless stated):**

| Point | Data | Model | d0 | Base (DD7) |
| --- | --- | --- | --- | --- |
| **O-F** | O | M₀ᶜ (`b/sky.npy`) | free | BF 0.988, 0.974, 0.939 |
| **O-P** | O | M₀ᶜ | pinned | B pinned 0.997, 0.993, 0.956 |
| **O-X** (control) | O | sky O (exact) | free | BF |
| O-F-2000 (conditional) | O | M₀ᶜ | free, cap 2000 | – |
| O-F-64 (conditional) | O | M₀ᶜ | free, 64 × 8 s | – |

O-F-2000 and O-F-64 run only if O-F reproduces or weakens.

**Rule per point (DD7 section 7, word for word):** a point **reproduces**
if some d1-d3 falls to ≤ 0.10 where its base is above 0.10, and **weakens**
if it stays lifted but some d1-d3 drops by ≥ 0.20 or its step median rises
by ≥ 100×; otherwise **neither**.

**Decision table (frozen):**

| O-F | O-X | Reading for candidate 4 (off-axis model incompleteness) |
| --- | --- | --- |
| reproduces | neither | **sufficient in simulation**; with DD7's R2 (restores), candidate 4 becomes **identified** by DD7's table |
| reproduces | reproduces or weakens | **confounded**: the inserted sky is hard to solve even with an exact model; not identified as a model error |
| weakens | neither | **contributes, not sufficient alone** at the real size |
| neither | any | **not sufficient in simulation**: candidate 4 stays "necessary on real data" (DD7) |

- **The real pattern (frozen):** real MF fails at 4 × 8 s cap 500, is lifted
  at cap 2000 and at 64 × 8 s. O-F **reproduces the real pattern** if it
  reproduces at cap 500 and O-F-2000 and O-F-64 are both lifted; **partly**
  if it reproduces and one of the two is lifted; else not.
- O-P is read by the same rule against B pinned and reported as the real M
  analogue; it changes no row of the table.
- Accuracy in simulation: `e/ê` and **accurate** per direction for every O
  point, reported. A lifted O point that is not accurate is a second
  instance of "convergence does not certify accuracy" (DD6).

## 4. Q2: the held-out-baseline measure

**The draw** (gate GH): about 10 % of the 1,685 non-bad baselines (about
168), stratified by length. They are flagged in held-out copies of three
bases (B-H from B, O-H from O, real-H from the real subset), so no solve on
an H copy sees them. Their original flags are kept with the copy.

**The score.** For a solution (model `M`, gains `g`, interval `ti`) on a
base, on held-out cells (original flags unflagged, w > 0, both hands):
`r = DATA − Σ_f g_p,f V_f g_q,f^*` with `V_f` the facet-f predict of `M`,
and `H = Σ w|r|²/(2k) / N` (k = 0.5291; 1 for pure k/w noise). Flagged
gain cells: a cell is dropped if any direction's gain on either antenna is
flagged in any solution scored together, so all solutions in one call are
scored on the same cells; the dropped fraction is reported. Also per
solution:
- **ΔH_f** = H with direction f's gains set to 1 minus H: the held-out
  value of solving direction f (positive: the solved gains predict unseen
  baselines better than unit gains).
- H on rows whose off-axis cells (both antennas, d1-d3) converged and on the
  rest, and the in-sample H on the training cells (reported).
- **Uncertainty (frozen):** baselines are the clusters. For a difference
  Δ = ΣD_b / ΣN_b between two predictions on the same cells,
  `SE = sqrt(n/(n−1) Σ_b (D_b − Δ N_b)²) / Σ_b N_b`. A difference is
  **significant** if |Δ| > 3 SE.

**References** scored with every base: unit gains in every direction; a
one-direction DI solve (the whole model as one direction, `ti` = 4, cap 500,
`refant=None`, on the H copy); on simulations the truth gains, with the
solve's model and, on O-H, also with sky O.

**Points (4 × 8 s, all on H copies, d0 free):**

| Point | Base | Model | cap |
| --- | --- | --- | --- |
| BH-F | B-H | sky B (exact) | 500 |
| OH-F | O-H | M₀ᶜ | 500 |
| RH-MF (bridge) | real-H | RM | 500 |
| RH-L2000 | real-H | RM | 2000 |
| R2H | real-H | DEEP | 500 |
| BH-DI, OH-DI, RH-DI | each base | its model, one direction | 500 |

**Validation (frozen, read before any real H reading):**
- **V1** (section 2): scorer gate.
- **V2, sensitivity:** on BH-F, ΔH_f > 3 SE and ΔH_f(solved) ≥ 0.5 ΔH_f(truth)
  for each of d1-d3. Fail: the measure cannot see the off-axis gains at this
  signal to noise; the real readings below are reported only, not read.
- **V3, accuracy against absorption (on O-H, model M₀ᶜ, truth known):**
  H(truth gains, M₀ᶜ) against H(OH-F): **tracks accuracy** if the truth
  gains predict better (significant); **rewards absorption** if OH-F
  predicts better (significant), i.e. gains that absorb a wrong model also
  predict unseen baselines; **indistinct** otherwise. Per-direction ΔH_f of
  truth and solve and OH-F's `e/ê` reported.

**Real readings (frozen):** read only if V1 and V2 pass; called **accuracy**
if V3 tracks accuracy, **predictive quality only** otherwise.
- Per point and direction: ΔH_f significant and positive **informative**,
  significant and negative **harmful**, else **uninformative**.
- RH-L2000 against RH-MF: **more iterations predict better / worse / no
  difference** (paired, significant).
- R2H against RH-MF: **the deep off-axis model predicts better / worse /
  the same** (each with its own model and gains). This is DD7's "different,
  not better" question on a measure that is not convergence.
- Each DD point against RH-DI: **DD beats DI / loses / no difference**.
- Bridge: RH-MF within 0.05 of DD7's MF-4 in each of d1-d3: the H copy is
  **comparable**; otherwise recorded, and the H readings stand on their own.
- **Limitations, stated before measuring:** prediction error is not gain
  accuracy (V3 tests how far it is); with about 1e-3 solved parameters per
  datum, held-out and in-sample H will be close; RM and DEEP were cleaned
  from all baselines, held-out ones included, so the models have seen the
  held-out data (a leak in the model, not in the gains); the 145 bad
  baselines are excluded from the score because no antenna gain predicts a
  non-closing error.

## 5. Q3: iterations and the combination (on the unchanged data)

**Iterations.** Real MF (RM, d0 free) at cap 2000: **L2000-16** (16 × 8 s)
and **L2000-64** (64 × 8 s). Cap-500 references: DD6's real-MF-16 (0.116,
0.085, 0.038) and MF-64 (0.794, 0.754, 0.752), which DD7's G4 reproduced to
every digit. The last interval holds 2 integrations and never converges
(DD6 A2), so the ceiling is (n−1)/n: 112/113 = 0.991 at 4, 28/29 = 0.966
at 16, 7/8 = 0.875 at 64 × 8 s. Per direction the **share of the gap closed
by iterations** is `G = (f2000 − f500) / (ceiling − f500)`.

| min of G over d1-d3 | Reading at that interval |
| --- | --- |
| ≥ 0.5 | **mostly iterations** |
| 0.1 to 0.5 | **partly iterations** |
| < 0.1 | **not iterations** |

`stopped_before_cap` and the step medians are reported; "still moving" if
at the cap with a d3 step median above 1e-14. At 4 × 8 s DD7 measured both
caps already (G = 0.50, 0.48, 0.46: partly); applying the rule there is post
hoc and labelled so; the 16 and 64 readings are new.

**R1 + R2.** Two copies rebuilt in DD8's root (gate GR): R1 (the 145 bad
baselines flagged) and R1c (DD7's weight-matched control baselines
flagged). Points, d0 free, model DEEP in every facet:
- **R12** (R1 copy, 4 × 8 s) and **R1cR2** (R1c copy, 4 × 8 s), against
  DD7's R2 (0.304, 0.297, 0.297; min 0.297):
  - **R1 adds to R2** if min(R12) ≥ 0.347 (R2 + 0.05) and min(R1cR2) < 0.347;
  - **adds, not specific** if both reach 0.347;
  - **no gain** if min(R12) < 0.347.
- **R12-64** (R1 copy, 64 × 8 s), against MF-64 (min 0.752) and R2-64
  (min 0.254): **repairs R2's loss at 64** if min ≥ 0.702 (MF-64 − 0.05);
  **partly** if min ≥ 0.354 (R2-64 + 0.10); else **no**.
- R12 is a diagnostic of what limits the solve; it proposes no model.

## 6. What the outcomes mean for the DD plan

| Outcome | Next DD step |
| --- | --- |
| Q1 sufficient (and real pattern) | The simulations must carry the off-axis model gap; the fix is a better off-axis model, made with DD gains (a DD-corrected deconvolution of the off-axis facets, DD3's loop on real data), not a unit-gain deep clean; test it in O first, where the truth is known |
| Q1 contributes or not sufficient | The real failure needs more than one property: a combined insertion into B (O plus the 145 baselines' residual plus d0's error), before any fix |
| Q1 confounded | The deep off-axis sky itself slows the solve; look at the solver (iterations, step) on O-X, not the model |
| Q2 V1, V2 pass and V3 tracks | Held-out H replaces the convergence test as the DD loop's criterion and as the gate for "DD helps" claims |
| Q2 V3 rewards absorption | Held-out H measures predictive quality only; accuracy on real data needs another route (an injected source, or a simulation matched to the real data) |
| Q2 V2 fails | No held-out accuracy at this signal to noise; accuracy only in simulation |
| Q3 mostly iterations at 16 and 64 | Solver speed is the limit: a faster solver or a higher cap before any model work, and every "does not converge" at cap 500 reread |
| Q3 not iterations | The cap is not the limit at longer intervals; the model and data are |
| R1 adds to R2 | The 145 bad baselines and the off-axis model act separately; flagging them belongs in any DD recipe for this field |

## 7. Not claimed

Image quality; accuracy of real gains beyond what V1-V3 support; speed. No
oracle parity is run: DD8 measures rang's own solve, which DD6 matched to
QuartiCal 0.2.7 in flags, fraction and iterations.

## 8. Implementation, host and cost

- `tools/oracles/dd8/dd8.py` (reads DD7's root, writes DD8's): `gates`
  (G1), `insert` (O, GO), `rebuild` (R1, R1c, GR), `draw` (GH), `holdout`
  (an H copy of a base), `grid` (through `dd5.grid_point`), `di` (the
  one-direction reference), `score` (section 4, all solutions of one base in
  one call). Unit tests in `tests/test_dd8.py` for the draw, the clustered
  SE and the scorer on synthetic data.
- glacier, shared, under the main checkout's `tools/heavy_lock.py`: a
  4 × 8 s or 64 × 8 s point 4 slots and 15 GB, a build 2 slots and 10 GB,
  the insertion build and a score 4 slots and 15 GB. No exclusive or timing
  runs. Cap-2000 points are queued first.
- **Point cap:** 15 DD solve points (Q1 3 + 2 conditional, Q2 5, Q3 5) and
  3 DI references, plus one spare for a rerun; past it the remaining points
  are not run and are reported as such.
- Expected 800-1,600 s per cap-500 point, about 2,900 s per cap-2000 point
  (DD7). Wall times go into [tool-timings.md](tool-timings.md). Built MS
  copies (about 2.5 GB each, six) are deleted at the end; the archive
  `results/dd8-offaxis/` keeps the records.

## 9. Measured result

Not yet measured.

## 10. For the coordinator

Not yet written.

## Amendments

**A1, 2026-11-25, setup (lanes started, no solve point finished or read).**
- GH needed seed 8803 (8801 and 8802 left an antenna off every held-out
  baseline): 169 held-out baselines, 9.65 % of the unflagged weight, all 61
  antennas; per bin 3, 8, 24, 44, 29, 46, 15. G1 passes.
- The bases' step medians are exactly 0 (B pinned and BF: more than half the
  cells repeat to the last bit), so section 3's "step median rises by
  ≥ 100×" is read as "step median above 1e-14" (the converged threshold).
  A median above 1e-14 means more than half the cells have not converged, so
  some direction has dropped by more than 0.20 and the drop clause already
  applies: the change alters no reading.
