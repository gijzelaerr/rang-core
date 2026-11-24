# DD4c: phase-only off-axis DD on ESO 137-006, from DI0's clean model, against DI0

Issue #15, follow-up of [dd4-eso137.md](dd4-eso137.md) (DD4) and
[dd4b-eso137.md](dd4b-eso137.md) (DD4b). Branch `dd4-eso137`. Owner
decisions 2026-11-24, relayed by the coordinator. Sections 1-4 are frozen
2026-11-24, before the code that runs them; later changes are dated
amendments.

Status: **proposed.**

## 1. Hypothesis and what changes

DD4b's amplitude-and-phase off-axis solves did not converge at 500
iterations, and their gains wandered by orders of magnitude. The guess that
d1's facet absorbs ESO 137-006's extended emission was supported post hoc.

**Hypothesis:** with the extended emission in the start model and the
off-axis directions solved for phase only, the off-axis solves converge,
and DD still lowers the off-axis rms against DI0.

**Settings (frozen):**
- **DD solve:** d1-d3 are solved **phase only**, with amplitudes held at 1
  (rang `solve_dd(calmode="p")`; QuartiCal `G.type=phase`, direction
  dependent). d0 stays pinned at the publisher's DI calibration
  (`pinned_directions=[0]`). A pinned direction's gains are held at
  identity, so d0 is the same pinned diag_complex direction as in DD4.
- **Phase kernel:** in the science arm **R**, each direction's update
  uses its own gain (`phase_last_direction_gain=False`). QuartiCal 0.2.7
  instead uses the last direction's gain for every direction
  ([ratt-ru/QuartiCal#459](https://github.com/ratt-ru/QuartiCal/issues/459),
  [dd3b-flux-pin.md](dd3b-flux-pin.md) A1). The parity pair (section 2)
  therefore uses QuartiCal's behaviour in both codes.
- **Cap:** 500 iterations, stop criterion 1e-7, fraction 0.99 (DD4b).
  Intervals 4 × 8 s, all 64 channels per interval.
- **Start model M₀ᶜ:** DI0's model entering its final cycle,
  `D:/rang/outputs/dd4-20261123/run-02/DI0/cycle-4/model.npy`, SHA-256
  `619891d38b8d7508d6c3d95ee8fb2dfc6ec9ba9eb6d589379bd5ea1e30f4914a`. It is
  the catalogue model plus DI0's clean components, ESO 137-006's extended
  emission among them. This file is DD4b's M_x. Both the DD arms and DI0
  start from it.
- **Baseline:** DI0, frozen in DD4b: one direction, pinned, so only the
  deconvolution loop runs.
- **Unchanged from DD4:** data subset, catalogue, directions, facets, pins,
  grid, the minor cycle, five major cycles plus a final solve, the PSF and
  every measure of section 5.

## 2. Arms

| Arm | Solve | Imaging | Purpose |
| --- | --- | --- | --- |
| **Rc** | rang, phase off-axis, each direction's own gain | rang | science arm |
| **DI0c** | none (one pinned direction) | rang, one facet | baseline |
| **Rq** | rang, phase off-axis, last-direction gain (QuartiCal's) | rang | parity with Oc |
| **Oc** | QuartiCal 0.2.7 `G.type=phase`, `G.pinned_directions=[0]`, `iter_recipe=[500]` | WSClean 3.7 on DD4 A5's matched copy | oracle |

DI0c is built the same way as DD4b's DI0x, and is rerun here.

## 3. Measures and decision rules (frozen)

**Convergence per direction (Rc and Rq).** The solver reports one fraction
over all directions. So each cycle's solve is repeated with the cap set to
one more iteration than the first solve used, and the stop fraction set to
1. A solution cell has converged if its relative change between the two,
`|Δg|² / |g|²`, is below the stop criterion squared (1e-14), which is the
solver's own test. Flagged cells are left out.
- **Converges:** the direction's converged fraction is ≥ 0.99 in every
  cycle.
- **Partly:** it is above 0.10 in at least one cycle, but does not meet
  the first rule.
- **Does not converge:** it stays at or below 0.10 in every cycle.

**DD against DI0 (Rc against DI0c; decision measure).** `q₀` is the median
over d1-d3 of rms(Rc) / rms(DI0c). DD4b's rule:
- **DD helps (rang only):** `q₀ ≤ 0.90` and DR(Rc) ≥ DR(DI0c);
- **Null:** `0.90 < q₀ < 1.05`, or `q₀ ≤ 0.90` with DR(Rc) < DR(DI0c);
- **DD worse:** `q₀ ≥ 1.05`.

**Parity (Rq against Oc).** Gates L and S as DD4 section 5, including the
rule that relaxes S to 2 % only with parity up to the rule. That rule is
now implemented as frozen (`score()`, test `tests/test_dd4_score.py`).
Rq against DI0c is reported by the same `q₀` rule.

**Outcome:**
- **Pass:** L and S hold. The `q₀` reading of Rc is then backed by a
  ported, oracle-checked loop. Rc differs from Rq only in the
  phase-kernel choice above.
- **Parity failure:** L or S fails. The first differing cycle and quantity
  are recorded. If Oc's phase solve does not converge, the likely cause is
  QuartiCal#459, as in DD3b. Rc's reading then stays rang only.

## 4. Runs (planned)

- `dd4.py rang RUN --phase --own-gain --perdir --cap 500 --model0 M --name Rc`
- `dd4.py rang RUN --di0 --model0 M --name DI0c`
- `dd4.py rang RUN --phase --perdir --cap 500 --model0 M --name Rq`
- `dd4.py oracle RUN SCRATCH --phase --cap 500 --model0 M --name Oc`, on the
  matched copy (DD4 A5)
- `dd4.py score RUN --r Rq --o Oc --di DI0c --out scorec.json`, plus
  `dd4.py scorec RUN` for convergence and Rc against DI0c

All runs go through the host lock (at most 8 slots each). The results go
to `research/results/dd4c-eso137/`.

## 5. Measured result

Not yet run.
