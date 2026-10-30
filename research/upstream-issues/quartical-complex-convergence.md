# QuartiCal: with default settings the iteration cap ends about half of the `complex` solves

Repository: ratt-ru/QuartiCal. Status: **filed 2026-10-30 (task U2),
https://github.com/ratt-ru/QuartiCal/issues/455** (improvement proposal; no PR). Builds on the
closed [quartical-iteration-cap.md](quartical-iteration-cap.md) (not a defect) with a
reproduction on the latest release. Duplicate search ("convergence"): only #432 (nullv term).

Checked on QuartiCal 0.2.7 (PyPI), Numba 0.68.1, dask 2024.10.0, dask-ms 0.2.32, Python 3.13,
on scan 9 of `outer_scans.zip` (140 rows, 4 antennas, 14 dumps, 4096 channels; MODEL_DATA = 1
on XX/YY; QuartiCal default unit weights, so #452 plays no part: a control with
WEIGHT/WEIGHT_SPECTRUM made XY = YX gives bit-identical gains). Runs `iter_recipe=[k]`,
`convergence_fraction=1.0`, k = 1-100; `conv_perc` from the gain dataset; chi-squared = mean
WEIGHT_SPECTRUM-weighted |DATA - G_p M G_q^H|^2 over unflagged cross rows (solver used unit
weights); Δmodel = median relative change of G_p M G_q^H against k = 100. Origin:
[../simplification-review.md](../simplification-review.md) section 2.7.

| setting | k | 10 | 15 | 20 | 25 (default) | 35 | 50 | 75 | 100 |
|---|---|---|---|---|---|---|---|---|---|
| 1 x 1, 1e-6 (defaults) | conv_perc | 0.010 | 0.052 | 0.207 | 0.540 | 0.630 | 0.766 | 0.964 | 0.981 |
| | chi-squared | 17.78 | 14.19 | 13.65 | 13.51 | 13.45 | 13.43 | 13.43 | 13.43 |
| | Δmodel | 5.3e-3 | 4.7e-4 | 2.7e-5 | 2.4e-6 | 1.3e-8 | 4.1e-12 | 3.4e-16 | 0 |
| 2 x 32, 1e-7 | conv_perc | 0 | 0.001 | 0.005 | 0.468 | 0.818 | 0.930 | 0.982 | 0.988 |
| | chi-squared | 31.365 | 31.330 | 31.323 | 31.320 | 31.317 | 31.314 | 31.313 | 31.312 |
| | Δmodel | 1.9e-3 | 1.4e-4 | 6.5e-6 | 5.0e-7 | 1.8e-9 | 3.1e-13 | 1.7e-16 | 0 |

- Default run (`iter_recipe=[25]`, stop fraction 0.99): stops at 25 with 54.0 % (1 x 1) and
  46.8 % (2 x 32) converged; 0.99 is not reached by 100 iterations in either setting.
- Gauge-invariant check (`onestep.py`, k vs k+1 runs): fraction of intervals whose one-step
  relative change is below the criterion, gains vs products G_p G_q^H: k = 25 51.0 / 50.7 %
  (1e-6), 38.1 / 36.8 % (1e-7); k = 50 80.9 / 79.9 %, 93.6 / 93.2 %. **Negative result**: a
  gauge-invariant criterion would not stop earlier; the tail is slow genuine convergence, so
  the proposal is (1) report capped intervals and document the cap, (2) an opt-in chi-squared
  decrease criterion. Matches the S1 port curve (7 % at 8, 49 % at 15, 0.99 at 91).
- Cost: 10-45 s per run on the loaded host (warm Numba cache), 0.43-0.55 GB RSS.
