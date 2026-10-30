# QuartiCal: 50-iteration cap reached with 98.3 % of intervals converged

Repository: ratt-ru/QuartiCal. Status: **not filed: not a defect.** Checked 2026-10-30.

- Observation ([core-k-luno-campaign.md](../core-k-luno-campaign.md)): the four-station LUNO
  `complex` solve (`solver.iter_recipe=[50]`, `solver.convergence_criteria=1e-7`) ends with a
  converged fraction of 0.98332; rang's faithful port gives the same fraction, on real data as
  on the fixture.
- Why not filed: the cap and the criterion are user options; reaching a 1e-7 relative-change
  criterion on 1.7 % of intervals of a sparse four-antenna array within 50 iterations is
  plausible behaviour of the block-diagonal update on weakly constrained bins, and the port
  shows it is not an implementation fault. A convergence-criterion study on more data is a
  research item for rang (big-plan P1), not a report.
- One mechanism that does slow convergence is filed separately:
  [quartical-qp-jhj-weights.md](quartical-qp-jhj-weights.md) (wrong JHJ weights when
  w_XY != w_YX). Rang's LUNO solve used `solver.robust=false` with the observer's
  WEIGHT_SPECTRUM; whether its XY and YX weights differ was not checked, so no link between the
  two is claimed.
- Related open issue: #432 "Investigate convergence behaviour of nullv solver" (different term).
