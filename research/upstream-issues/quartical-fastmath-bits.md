# QuartiCal: cached and freshly compiled kernels give different bits

Repository: ratt-ru/QuartiCal. Status: **not filed: rounding-level, cause not isolated, not a
defect.** Checked 2026-10-30.

- Observation ([stack-consolidation-feasibility.md](../stack-consolidation-feasibility.md)):
  the LUNO four-station gains from a cold-cache run (hash `57809b86…`) and a warm-cache run
  (`769a69b1…`) differ by at most 1.1e-16 absolute and 2.0e-14 relative, with identical gain
  flags. `JIT_OPTIONS` has `"fastmath": True` (0.2.7 = `main`).
- Why not filed: differences of this size are expected from floating-point evaluation order;
  `fastmath` is one possible source, but the cause was not isolated (thread scheduling and
  dask chunk order are equally possible), so there is nothing technically certain to report.
  Bit-reproducibility across cache states is not a stated QuartiCal guarantee.
- Rang-side consequence, already adopted: compare QuartiCal gains with a tolerance, never a
  hash. A port without `fastmath` agrees with QuartiCal to 1.4e-15.
- What an issue would have said: a documentation note that `fastmath` makes results
  bit-unstable across builds, or an opt-in strict mode. Not worth a maintainer's time without
  a demonstrated accuracy effect.
