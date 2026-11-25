# DD8: the off-axis model gap in simulation, a held-out accuracy measure, and how much is iterations

Issue #15. Follows [dd7-cause.md](dd7-cause.md) (DD7), [dd6-d0.md](dd6-d0.md)
and [dd5-sim.md](dd5-sim.md). Branch `dd8-offaxis`. Coordinator brief
2026-11-25. A diagnostic, not a fix: no claim of better calibration or
imaging follows from it. Sections 1-8 are frozen 2026-11-25, before the code
that runs them and before any measurement. Later changes are dated
amendments, written before the reading they affect.

Status: **measured 2026-11-25.** Q1: the real-size off-axis model gap inserted into the exact simulation B (O) reproduces the real d0-free failure and its pattern (O-F 0.018, 0.009, 0.000 at cap 500; lifted at cap 2000, 0.486, 0.424, 0.308, and at 64 × 8 s), with gains 15-295 × the noise prediction off wherever it converges; by the frozen table the reading is **confounded**, because the exact-model control also slows (O-X 0.540, 0.464, 0.449, weakens) while staying accurate (e/ê 1.1-1.2). Q2: the held-out-baseline measure passes V1 and V2 and is indistinct on V3, so on real data it reads predictive quality only; it shows that with RM the weak facet d3's gains run away (|g| to 58 at cap 500, 156 at cap 2000), so held-out H rises (27, 1,525; in sample 1.77) as the converged fraction rises. Q3: the cap is partly the limit at 16 × 8 s (L2000-16 0.581, 0.460, 0.384) and mostly at 64 × 8 s (0.917, 0.877, 0.877). Flagging the 145 bad baselines adds to the deep off-axis model, specifically (R12 0.902, 0.876, 0.872; control 0.219, 0.171, 0.168) and repairs its 64 × 8 s loss (min 0.875).

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

Run root `D:/rang/outputs/dd8-20261125/` (`O/`, `R1/`, `R1c/`, `B-H/`,
`O-H/`, `real-H/`, `grid/`, `score/`, `times.log`); archive
[results/dd8-offaxis/](results/dd8-offaxis/). Host glacier, shared; the main
checkout's extension (DD8 changes no Rust). Every DD point ran to its cap.
Fractions are d1, d2, d3 (d0 in brackets); step is the d3 median
`|Δg|²/|g|²`. 15 DD points and 3 DI references were run, inside section 8's
cap; the spare was not used.

**Setup gates: all pass.** G1 (fluxes equal DD7's to 1e-6 Jy); GH (A1;
169 baselines, 9.65 % of the weight); GO (signed Δ +1.604, +0.323,
−0.155 Jy; `DATA_B − n − predict(B)` 2.7e-6 Jy, `DATA_O − n − predict(O)`
7.6e-6 Jy); GR (R1 65,250 rows; R1c's baselines equal DD7's); V1 (truth
gains on B-H: H = 1.0004 ± 0.0004). The inserted error is larger than its
net: Σ|DEEP − M₀ᶜ| is 21.2, 4.1 and 2.8 Jy per facet against nets of 1.6,
0.32 and −0.15 Jy.

### Q1: the insertion (bases BF 0.988, 0.974, 0.939; B pinned 0.997, 0.993, 0.956)

| Point | d1, d2, d3 (d0) | step | e/ê d1-d3 | Rule |
| --- | --- | --- | --- | --- |
| **O-F** (M₀ᶜ, d0 free) | **0.018, 0.009, 0.000** (0.094) | 1.4e-7 | 72, 15, 20 | **reproduces** |
| O-P (M₀ᶜ, d0 pinned) | 0.0001, 0, 0 | 5.1e-7 | 74, 21, 20 | reproduces |
| **O-X** (sky O exact, d0 free) | **0.540, 0.464, 0.449** (0.639) | 1.4e-11 | 1.2, 1.1, 1.1 | **weakens** (drops 0.45-0.51) |
| O-F-2000 (cap 2000) | 0.486, 0.424, 0.308 (0.705) | 1.8e-11 | 72, 15, 20 | lifted |
| O-F-64 (64 × 8 s) | 0.306, 0.271, 0.134 (0.579) | 1.4e-9 | 295, 52, 72 | lifted |
| *real MF-4 (DD7)* | *0.066, 0.042, 0.011 (0.152)* | *1.2e-7* | – | |
| *real L2000 (DD7)* | *0.530, 0.501, 0.465 (0.705)* | *2.6e-13* | – | |
| *real MF-64 (DD6)* | *0.794, 0.754, 0.752 (0.875)* | – | – | |

- **Frozen reading: confounded.** O-F reproduces and O-X weakens, which is
  section 3's second row: the inserted sky slows the solve even with an
  exact model, so candidate 4 is not identified as a model error alone.
- **Real pattern: reproduced** (frozen rule: reproduces at cap 500, lifted at
  cap 2000 and at 64 × 8 s). At cap 500 O-F sits at the real MF-4's level
  with the same d3 step (1.4e-7 against 1.2e-7); at cap 2000 it lands on
  the real L2000 (d0 0.705 in both; d1-d3 0.31-0.49 against 0.47-0.53).
  At 64 × 8 s it is lifted but well below real MF-64 (0.13-0.31 against
  0.75-0.79).
- **What the confound leaves (interpretation, not a frozen reading):** O-X
  and O-F differ only in the model. With the exact model the solve is slower
  than B but accurate (e/ê 1.1-1.2); with M₀ᶜ it is at the real failure
  level at cap 500 and, where it converges (cap 2000, 64 × 8 s), converges
  to gains 15-295 × the noise prediction off. So the deep off-axis sky (more
  structure: 21 Jy of absolute pixel flux in d1) slows the solve, and the
  model error both slows it further and makes it wrong. On the simulation
  that matches the real data best, convergence certifies nothing.
- O-P (the real M analogue) is at the floor like real M; no row changes.

### Q2: the held-out measure (169 baselines, 76,050 rows; cells touching a flagged gain dropped: 6.7 % B-H, 7.8 % O-H, 16.6 % real-H)

**Validation.** V1 passes (above). **V2 passes:** on BH-F, ΔH in d1-d3 is
3.286 ± 0.443, 0.0958 ± 0.0069, 0.0303 ± 0.0022 against the truth's 3.285,
0.0961, 0.0306 (all > 7 SE, ratio ≥ 0.99). **V3 is indistinct:**
H(truth gains, M₀ᶜ) − H(OH-F) = 1.60 ± 0.98 (OH-F e/ê 69, 15, 19; OH-F's
in-sample H 1.55, held-out 3.39). So by section 4 the real readings are
**predictive quality only**.

| Base | Solution | H held-out | H in sample | ΔH d0, d1, d2, d3 (reading) |
| --- | --- | --- | --- | --- |
| B-H | truth | 1.000 | 1.000 | –, 3.29, 0.096, 0.031 (all informative) |
| B-H | BH-F | 1.002 | 0.999 | −0.0003, 3.29, 0.096, 0.030 (inf.) |
| B-H | BH-DI / unit | 4.23 / 4.40 | 4.17 / 4.87 | |
| O-H | truth with sky O / with M₀ᶜ | 1.000 / 4.99 | 1.000 / 4.29 | |
| O-H | OH-F | 3.39 ± 0.91 | 1.55 | 0.007, 4.33 (inf.), 0.081 (inf.), −1.32 ± 0.84 |
| O-H | OH-DI / unit | 5.77 / 6.59 | 5.31 / 6.59 | |
| real-H | unit (RM) / unit (DEEP) | 6.08 / 2.42 | 5.53 / 2.42 | |
| real-H | RH-DI | 3.72 ± 0.31 | 3.21 | |
| real-H | RH-MF | 27.4 ± 25.3 | 1.77 | 0.89 (inf.), 2.77 (inf.), 0.017, −25.2 ± 25.2 |
| real-H | RH-L2000 | 1,525 ± 1,527 | 1.77 | −0.59, 2.36 (inf.), 0.11, −1,522 ± 1,527 |
| real-H | R2H (DEEP) | **1.55 ± 0.13** | 1.32 | 0.90, −0.015, −0.024, −0.010 (all uninf.) |

**Frozen real readings (predictive quality only):**
- RH-L2000 against RH-MF: **no difference** (−1,497 ± 1,502).
- R2H against RH-MF: **the same** (−25.9 ± 25.3, not significant).
- DD against DI: RH-MF **no difference**, RH-L2000 **no difference**, R2H
  **beats DI** (−2.17 ± 0.30).
- Bridge: RH-MF 0.029, 0.025, 0.012 against DD7's MF-4 0.066, 0.042, 0.011:
  **comparable**. RH-L2000 (0.496, 0.458, 0.370) is near DD7's L2000.

**Why the clustered SE is so large (post hoc, reported only).** The RM
solutions' held-out excess sits on one baseline: per-baseline H medians are
1.65 (RH-MF), 1.66 (RH-L2000), 1.23 (R2H), 2.61 (RH-DI), 1.36 (unit DEEP);
the worst baseline reads 6,315 (RH-MF) and 381,000 (RH-L2000) against 17.6
(R2H); without it the means are 2.28, 5.95 and 1.43. The cause is d3, the
facet with about 0.2 Jy in RM: its gains run away where nothing constrains
them (|g| p99 13.8 and maximum 58.6 at cap 500, 16.3 and 155.8 at cap 2000;
R2H: 1.94 and 8.1), so the product `g_p g_q*` on a held-out pair of two such
antennas predicts nonsense. 500 → 2000 iterations makes this worse, and the
convergence test raises its fraction at the same time. OH-F shows the same
sign in d3 (−1.32). So on real data a converged fraction can rise while the
solution's prediction of unseen baselines gets worse; the held-out score
sees what the convergence test does not, but as a mean over baselines it is
dominated by the runaway cells and needs a robust form (a per-baseline
median, or a cap on |g|) to read differences.
- Limitations as frozen: RM and DEEP were cleaned from all baselines, so the
  unit-gain DEEP prediction (median 1.36) is not an independent result;
  V3 could not separate absorption from accuracy here.
- Not on the H copies, so no held-out score: R12. Note that R2 on the H copy
  (R2H 0.118, 0.101, 0.104) is much lower than DD7's R2 (0.304, 0.297,
  0.297): removing 169 random baselines costs it most of its lift, while
  removing the 145 bad ones (R12) nearly triples it.

### Q3: iterations and R1 + R2 (on the unchanged data)

| Point | d1, d2, d3 (d0) | step | Reading |
| --- | --- | --- | --- |
| L2000-16 | 0.581, 0.460, 0.384 (0.810) | 4.2e-12 | G 0.55, 0.43, 0.37: **partly iterations**; still moving |
| L2000-64 | 0.917, 0.877, 0.877 (0.998) | 2.4e-33 | G 1.51, 1.02, 1.01: **mostly iterations** |
| (L2000-4, DD7, post hoc) | 0.530, 0.501, 0.465 | 2.6e-13 | G 0.50, 0.48, 0.46: partly |
| **R12** (R1 copy, DEEP) | **0.902, 0.876, 0.872** (0.957) | 3.6e-34 | **R1 adds to R2** (control below 0.347) |
| R1cR2 (control) | 0.219, 0.171, 0.168 (0.298) | 1.2e-9 | below R2 |
| **R12-64** | 0.877, 0.877, 0.875 (0.958) | 7.8e-34 | **repairs** R2's loss at 64 × 8 s (min 0.875 ≥ 0.702) |

- The section-5 ceiling was wrong at 64 × 8 s: at cap 2000 d1 reaches 0.917,
  above 7/8, so the 2-integration last interval converges in part, and G
  above 1 means "at or past the assumed ceiling". The reading is the same.
- R12 at 4 × 8 s (min 0.872) reaches what the real solve otherwise reaches
  only at 64 × 8 s, at cap 500. The control flags weight-matched baselines and
  does worse than R2 alone, so the gain is specific to the 145. This is a
  diagnostic: the deep model is still the unit-gain clean, not adopted.

**Cost (glacier, shared; walls include lock waits).** A cap-500 point:
predict 46-53 s, each solve 371-464 s, walls 846-4,219 s; a cap-2000 point:
each solve 1,545-1,937 s, walls 3,581-5,782 s; DI references 24-38 s of
solve (84-131 iterations, 0.99); insertion build 151 s; copies 15-193 s of
work (walls to 1,504 s); scores 115-189 s. Rows in
[tool-timings.md](tool-timings.md).

## 10. For the coordinator

- **The real failure is reproduced in simulation for the first time:** B with
  the real-size off-axis model gap (O) fails, lifts at cap 2000 and at
  64 × 8 s, like the real data, and its gains are wrong by 15-300 × the
  noise wherever it converges. By the frozen table it is "confounded" (the
  deep off-axis sky also slows an exact-model solve, which stays accurate).
  O is the testbed to use: it has a truth and behaves like the real data.
- **Convergence is not a usable target on this field:** more iterations raise
  the fraction (L2000 at 4, 16, 64 × 8 s; 64 × 8 s is mostly iterations)
  while, with RM, d3's gains run away and held-out prediction gets worse. The
  held-out score sees the off-axis gains exactly in B (V2) but did not
  separate accuracy from absorption (V3 indistinct), and its mean is
  dominated by one baseline; freeze a robust form (per-baseline median, or
  trimmed) before using it as a criterion.
- **Flag the 145 bad baselines in any DD recipe for this field:** with the
  deep model they lift 4 × 8 s to 0.87-0.90 at cap 500 (control 0.17-0.22)
  and keep 64 × 8 s at the ceiling.
- **Recommended DD9 (frozen before code):** on O, where the truth is known,
  test the fixes for the off-axis model and the runaway weak-facet gains
  against truth error, not convergence: (a) an off-axis model rebuilt from
  DD-corrected facet images (DD3's loop) against M₀ᶜ and the unit-gain DEEP;
  (b) a constraint on the weak facets (d3: merge it, regularise its
  amplitude, or solve it at a longer interval); both with the 145 baselines'
  residual added to O so it carries the bad-baseline effect too. Then carry
  the winner to real data with the robust held-out score.
- Do not adopt the unit-gain deep clean: R12's lift uses it as a diagnostic
  only, and R2 alone collapses when 9 % of the baselines are held out
  (R2H 0.10-0.12).
- Run root `D:/rang/outputs/dd8-20261125/`: built MS copies deleted at the
  end; records, gains and scores kept (see the hand-back).

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

**A2, 2026-11-25, post hoc (after O-F, L2000-64 and the real-H score were read).**
- The per-baseline medians, the mean without the worst baseline and the gain
  amplitude tails in section 9's Q2 are reported only; they change no frozen
  reading.
- Section 5's ceiling 7/8 at 64 × 8 s is exceeded at cap 2000 (d1 0.917);
  G above 1 is read as "at or past the ceiling"; the reading stands.
