# QuartiCal: the `complex` term ignores `solver.reference_antenna`

Repository: ratt-ru/QuartiCal. Status: **not filed: documented in 0.2.7 and changed on
v0.2.8-dev.** Checked 2026-10-30.

- 0.2.7 (= `main` 942f77f): only `complex/diag_kernel.py` and the phase/delay/TEC kernels read
  `meta_inputs.reference_antenna`; the full `complex/kernel.py` does not. The option's `info`
  in `quartical/config/argument_schema.yaml` (lines 403–410) says QuartiCal "will also
  guarantee zero phase on the specified antenna for diagonal terms", so not referencing the
  full 2×2 term is the documented behaviour, not a bug.
- v0.2.8-dev (059c806): PR #440 (merged 2026-08-31) "Make referencing a per-term option and
  extend it to the complex term" references `complex` by default, with `{term}.referenced=false`
  to opt out; the schema text now reads "for every term which has a referencing stage".
- Related open issue: #376 "Inconsistent reference antenna handling" (flag propagation from
  the reference antenna).
- Rang consequence: rang fixes the gauge itself (polar factor of the reference antenna), which
  remains correct; on a future 0.2.8 the `complex` solutions will arrive already referenced,
  so receipts that hash raw gains will change.
