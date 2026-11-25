# DD6: d0 left free, or a better d0 model, before the off-axis DD solve on ESO 137-006

Issue #15. Follows [dd5-sim.md](dd5-sim.md) (DD5, section 8 and A3),
[dd4d-eso137.md](dd4d-eso137.md) (DD4d) and
[dd1-facet-gains.md](dd1-facet-gains.md) (DD1). Branch `dd6-d0`.
Coordinator brief 2026-11-25. Sections 1-7 are frozen 2026-11-25, before the
code that runs them and before any run. Later changes are dated amendments.

Status: **proposed 2026-11-25.** Nothing built or run.

## 1. Question and hypotheses

DD5 reproduced the real non-convergence of the off-axis DD solves (DD4d:
0, 0, 0 in d1-d3 at 4 × 8 s, pinned d0, model M₀ᶜ) in simulation only when the
model was wrong: arm C (sky M₀ᶜ, model the catalogue M₀) at every interval, and
arm E (sky DI0c's model, model M₀ᶜ) at 4 × 8 s. Its diagnostic E0 put nearly
all of E's failure in the d0 facet. The untested post hoc mechanism: d0 is
pinned at 1, so it cannot absorb its model error, and the free off-axis gains,
whose own signals are 10-1000 × weaker, take it up.

Two remedies follow from that mechanism. DD6 tests both, alone and together:

- **H-F (d0 free):** with d0 solved as a free direction (`pinned_directions=[]`,
  as DD1 P1-P3), part of d0's model error goes into d0's own gains, and the
  off-axis solves converge.
- **H-M (better d0 model):** with a deeper d0 model, made by one frozen
  multiscale clean (section 3), the d0 model error is smaller, and the off-axis
  solves converge with d0 still pinned.

Not claimed: that DD helps the image (that needs the loop, section 5, stage 5),
a speed result, or anything for kinds other than `diag_complex`. `phase` is not
run: QuartiCal 0.2.7's DD `phase` is broken (ratt-ru/QuartiCal#459), and DD5
read `diag_complex` as primary.

A free d0 can converge by absorbing model error into gains that should be 1.
So convergence alone is not success. In simulation, accuracy against the truth
(section 4) is read beside it for every solved direction, d0 included.

## 2. Data

**Simulations: DD5's, reused unchanged** (`D:/rang/outputs/dd5-20261124/`,
not regenerated, not deleted). Each `sim.ms` is the real subset with `DATA`
replaced (DD5 section 2), with its `truth.npz` (d0 truth gain exactly 1) and
k = 0.5291 (`noise.json`).

| Dataset | MS (truth sky) | Base model (DD5's arm) | DD5 pinned reading, `diag_complex` 4 × 8 s |
| --- | --- | --- | --- |
| **C** | `b/sim.ms` (M₀ᶜ, 47.8 Jy) | `a/sky.npy` (catalogue M₀, 92.6 Jy) | 0.020, 0.022, 0.025 |
| **E** | `e/sim.ms` (DI0c's cycle-4 model, 50.2 Jy) | `b/sky.npy` (M₀ᶜ) | 0.036, 0.004, 0.000 |
| **B** (control) | `b/sim.ms` | `b/sky.npy` (exact) | 0.997, 0.993, 0.956 |

`b/sky.npy` is M₀ᶜ (file SHA-256 `619891d3…4914a`, checked 2026-11-25);
`e/sky.npy` is checked against DI0c's `2da55706…0a6a03` before use.

**Real data: DD4d's, regenerated.** DD4's run root `D:/rang/outputs/dd4-20261123`
was deleted. The subset is rebuilt without CASA:
- copy DD5's `a/sim.ms` (the subset's layout, flags, weights and UVW, only
  `DATA` replaced) to `D:/rang/outputs/dd6-<date>/real/sub.ms`;
- write `DATA` from `D:/rang/outputs/20261103-gemclean-heldout/real/cal2.ms`,
  channels 96-159, rows in order (DD4 A1's CASA `split` keeps rows and
  `datacolumn='data'` copies `DATA` unchanged);
- **setup check (S1):** `TIME`, `ANTENNA1`, `ANTENNA2`, `UVW`, `FLAG_ROW`,
  and channels 96-159 of `FLAG` and `WEIGHT_SPECTRUM`, equal between `cal2.ms`
  and the copy, exactly. A miss is a setup outcome; stop.
- Run directory: DD5 `a/`'s `psf.npy`, `header.json`, `facets.reg` and
  `model0.npy` (DD4's), with `setup.json` pointing at the new `sub.ms`.
- Directions, facets, pins, grid (2880², 3″): DD4's, unchanged.

**Reproduction gate (S2), read before any remedy arm on real data:** DD4d's
point rerun: `diag_complex`, 4 × 8 s, d0 pinned, model M₀ᶜ, cap 500. It must
read ≤ 0.10 in every off-axis direction (DD4d: 0, 0, 0; 1,876 flagged off-axis
gains). Also reported: k on the regenerated data by DD5 section 2's estimator
(DD5: 0.5291). A miss of S2 is a setup outcome; stop.

## 3. Arms

Each dataset gets a 2 × 2: d0 pinned or free, crossed with the base or the
deeper d0 model. The pinned, base cell is DD5's point (C, E) or S2 (real).

| Arm | d0 | Model | Datasets |
| --- | --- | --- | --- |
| base (P) | pinned | the dataset's base model | DD5's C, E points; S2 for real |
| **F** | free | base model | C, E, real |
| **M** | pinned | deeper d0 model: the deep clean in facet d0, the base model in d1-d3 | C, E, real |
| **MF** | free | M's model | C, E, real |
| **X** (diagnostic) | pinned | the truth in facet d0, the base model in d1-d3 | C, E (simulation only) |
| **BF** (control) | free | exact (`b/sky.npy`) | B |

X is the ceiling of H-M: a perfect d0 model. BF checks that freeing d0 does no
harm when the model is exact.

**The deeper d0 model (one frozen procedure for every dataset).** GeMClean on
the dataset's MS `DATA`, with unit gains (no DD correction), from an empty
model:

```
gemclean -size 2880 2880 -scale 3asec -weight natural -pol I -data-column DATA
  -wgridder-accuracy 1e-6 -niter 2000000 -mgain 0.8 -nmiter 30
  -multiscale -auto-mask 4 -auto-threshold 1.5 -local-rms -j 8 -name OUT/deep MS
```

- Its `deep-model.fits` (Jy per pixel, DD4's grid and pixel order) inside facet
  d0 (DD4's Voronoi index) replaces the base model there. d1-d3 keep the base
  model, so the pins and the off-axis facets are unchanged.
- Against DI0's procedure (DD3's Högbom, 5,000 components at gain 0.1 per
  cycle, a 1 mJy floor, four cycles from the catalogue), this is deeper
  (2,000,000 components, 1.5 σ local) and models extended emission
  (multiscale).
- If GeMClean cannot run on this MS or with these options, the fix is a dated
  amendment before any M arm is read.
- A run longer than 6 h is stopped and recorded; then M is "not built".

**Precondition M0 (read before any M or MF arm):** the deeper model must be
better in d0.
- Real data: the rms of the unit-gain residual image (`dd4.facet_image` of
  `DATA` minus the unit-gain predict of the model) over facet d0's interior
  pixels is lower with M's model than with M₀ᶜ.
- Simulation: Σ|model − sky| over facet d0 is lower with M's model than with
  the base model. The same residual rms is reported.
- If M0 fails for a dataset, its M and MF arms are reported but read as
  **no better model built**, not as a test of H-M.

**Solve (each arm, each interval): DD5's grid solve** (`dd5.py grid`'s
procedure): `cal_gain.solve_dd`, `diag_complex`, cap 500, stop criterion 1e-7,
stop fraction 0.99, `refant=None`, full 64-channel band; a second solve one
iteration longer with stop fraction 1 for the per-direction measure. The only
change for F, MF and BF is `pinned_directions=[]`.

**Intervals.** 4 × 8 s for every arm. On real data, an arm that is not lifted
(section 4) at 4 × 8 s runs 16, 64 and 450 integrations, in that order, and
stops at the first that lifts it. Simulation arms run 4 × 8 s only, as DD5 A1
allowed, unless the host is free after the real grid (reported, not read).

## 4. Measures

- **Per-direction converged fraction:** DD4c section 3's measure (DD4d A1),
  unflagged cells, d0-d3 (d0 is 1.0 by construction when pinned).
- **Levels (DD5 A1):** ≥ 0.99 converges, > 0.10 partly, ≤ 0.10 does not.
- **Lifted:** every one of d1-d3 is above 0.10 (partly or better).
- **At A's level:** every one of d1-d3 is ≥ 0.90 (DD5's arm A, exact
  catalogue model, reached 0.913-0.990).
- **Accuracy (simulation):** DD5 section 4's `e_d` and `ê_d` for d0-d3.
  **Accurate** if `e_d ≤ 2 ê_d` in every solved direction (d1-d3, and d0 when
  free). For a free d0, `ê_d` is DD5's prediction with d0's own model.
- Reported, not gated: flagged gains per direction, d0's median |g| and phase
  spread when free, iterations, step statistics, `e_d / ê_d`.

## 5. Decision rule (frozen)

**Stage order:** S1, S2 (section 2); the deep cleans and M0; the
4 × 8 s points; real-data longer intervals; the parity solve; conditionally
the loop.

**Simulation readings (per dataset C, E, at 4 × 8 s):** each of F, M, MF, X is
one of: **not lifted**; **lifted, biased** (lifted, not accurate); **lifted,
accurate**. BF: **no harm** if lifted and accurate (B pinned is noise-limited),
else **harm**.

**Real-data outcome (primary).** Read on F, M and MF over the interval grid
(lifted at some interval), with S2 passed:

| Lifted on real data | Outcome |
| --- | --- |
| M (with or without F) | **a better d0 model restores the off-axis solves** |
| F, not M | **freeing d0 restores the off-axis solves** |
| MF only | **both are needed** |
| none, but some arm lifted on C or E | **works in simulation only:** the real failure has a further cause than d0's model error and pinning |
| none anywhere | **null: neither remedy** |

- If M0 fails on real data, rows with M or MF are read as "no better model
  built", and only F can give a positive reading.
- An arm lifted only at 450 × 8 s (the whole scan) is reported as such: it
  restores a solve that no longer tracks the gains in time.
- Each lifted real arm is also read for "at A's level" and "converges".
- The sufficiency diagnostic: if X is lifted on C or E and M is not, the
  deeper clean, not d0's model error, is the limit there.

**Parity (one configuration, always run):** QuartiCal 0.2.7 against rang on
one cycle-0 solve.
- Configuration: the real-data arm among F, M, MF with the highest minimum
  d1-d3 fraction, at the interval where that arm was read (ties: M, F, MF).
- Oracle: DD4's arm O steps 0-1 (`step4_o0.sh`, `step4_o1.sh`: WSClean 3.7
  per-facet predicts into `MODEL_D0..3`, then `goquartical` with
  `G.type=diag_complex`, `G.time_interval` as the arm, `G.freq_interval=0`,
  `iter_recipe=[500]`, `G.pinned_directions` `[0]` or `[]` as the arm),
  venv `~/Build/tmp/20261123-dd15/venv-qc027` on WSL, scratch on WSL ext4.
  No imaging step.
- Rang: the same solve with `refant=0` (DD4's science solve; QuartiCal
  references to antenna 0).
- **Gates:** flags equal; aggregate converged fraction equal to 1e-6; gain
  products `g_p ḡ_q` within 1e-5 absolute **over the cells rang's measure
  counts as converged** (DD5's gate L failed at 1.07e-5 on cells that had
  not met the step test at cap 500; on those cells two codes that differ by
  their predicts' ε cannot be expected to agree). The maximum over all
  unflagged cells, the median and the fraction within 1e-5 are reported.
- **Outcome:** **parity** (all three gates), or **parity failure** (the
  quantity that fails).
- QuartiCal's aggregate converged fraction is also read as a cross-check of
  rang's reading: if it differs by more than 0.01, that is reported beside
  the outcome.

**Stage 5, the loop (conditional):** only if some real-data arm reaches A's
level (all of d1-d3 ≥ 0.90) at an interval T*.
- Rang: DD4's loop (`dd4.py rang`) with that arm's d0 setting, start model and
  T*, five major cycles plus the final solve, the per-direction measure each
  cycle.
- DI0x: `dd4.py rang --di0` from the same start model.
- Rule: DD4b's `q₀` (DD helps: `q₀ ≤ 0.90` and DR(R) ≥ DR(DI0x); null:
  `0.90 < q₀ < 1.05`, or `q₀ ≤ 0.90` with lower DR; DD worse: `q₀ ≥ 1.05`).
- Loop parity against `dd4.py oracle` is then a separate proposal, because
  it costs about 6 h of host time (DD5 Od).
- If no arm reaches A's level, the loop is not run, and the outcome says so.

## 6. Implementation

- `tools/oracles/dd6/dd6.py` (Python orchestration):
  - `realms`: section 2's copy and the S1 check;
  - `deep`: the frozen GeMClean run and the d0 composition;
  - `modelcheck`: M0;
  - `grid`: DD5's grid point with a `--free` option (d0 unpinned);
  - `parity`: the cycle-0 oracle solve and its gates.
- `dd5.py`'s `grid_point` gains `pinned` and works without a truth file (real
  data). Its existing behaviour is unchanged.
- No Rust change is expected: `solve_dd` already takes
  `pinned_directions=[]` (DD1 P1-P3).
- Unit tests on synthetic data, in the style of `tests/test_cal_gain_dd.py`
  (CI has no D: data): facet composition, the d0-free solve recovering every
  direction's products, and the parity comparator on converged cells.

## 7. Host use and cost

- glacier, shared, through `tools/heavy_lock.py`.
- A 4 × 8 s grid point holds about 11-12 GB. It books 4 slots and 15 GB, so at
  most three run at once on 48 GB.
- A whole-scan point is single-threaded and books 2 slots.
- GeMClean books 8 slots and 16 GB. QuartiCal books 2 slots and 10 GB.
- Expected: 13 points at 4 × 8 s, at 550-1,700 s each (DD5, DD4d); up to nine
  real longer-interval points; three deep cleans of unknown length (6 h cap);
  one parity solve, about 1 h.
- Wall times go into [tool-timings.md](tool-timings.md).
- Outputs go in `D:/rang/outputs/dd6-<date>/`, with WSL scratch on ext4,
  deleted at the end.

## 8. Measured result

Not yet measured.

## Amendments

**A1, 2026-11-25, setup (before any deep model existed; no result read).**
GeMClean refused section 3's command at start-up: `-local-rms is not
implemented` (research/g4-masks.md). The frozen command is run without
`-local-rms`; the auto-mask (4 σ) and auto-threshold (1.5 σ) then use
GeMClean's global noise estimate. Nothing else changes. The two refused runs
lasted under a second and wrote no model.
