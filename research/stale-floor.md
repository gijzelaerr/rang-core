# Rang: a floor on GeMClean's measured stop rule

Status, 2026-11-03: **measured; one measure of the bar missed; the default is unchanged.** Branch `stale-floor`, flag
default off. The bar below was committed before any run with the floor (`9c95d19`). Archive:
[results/stale-floor.json](results/stale-floor.json). Raw products: `D:\rang\outputs\20261103-stale-floor`.
Owner's decision: test this on a branch, after the held-out test.

## Result

- **Bar 1 passed.** `f = 0.01` leaves dirty, PSF, model, residual and image identical in data on S1-S3 and H1-H4. Added
  after the bar: also on the pilot's three runs (set A at 3 and 1 mJy, set B at 3 mJy).
- **Bar 2 passed.** All four cases stop at the threshold, and every measure is inside its limit.
- **Bar 3 missed on one measure.** H3 plus 100 Jy has 6,263 model pixels, 1.12 × the 5,592 of H3 alone, against a limit
  of 1.1. By the bar's own wording the default therefore stays until the owner decides. Its other measures pass: off-source
  Σ|flux| 1.0006 ×, 8 cycles as on H3. The default on that case gives 344,761 pixels.
- **The failure is wider than an exact centre source.** S2 plus 30 Jy only 20 pixels off centre does not reach the budget
  under the default, but takes 9 cycles, 268,263 components and 45,249 model pixels, against 5, 90,905 and 4,249 for S2 alone.

| case | default: cycles, components, stop, model pixels, off-source Σ\|flux\| Jy | `f = 0.01`: same | pixels × own sky | Σ\|flux\| × own sky |
| --- | --- | --- | ---: | ---: |
| S1 + 10 Jy | 6, 99,900, threshold, 7,368, 14.36 | 6, 86,298, threshold, 2,830, 13.96 | 1.021 | 1.0005 |
| S1 + 30 Jy | 2, 1,000,000, budget, 202,092, 63.58 | 6, 86,805, threshold, 2,896, 13.97 | 1.045 | 1.0010 |
| S1 + 100 Jy | 2, 1,000,000, budget, 202,086, 63.58 | 6, 85,724, threshold, 2,820, 13.96 | 1.017 | 1.0002 |
| S1 + 1000 Jy | 2, 1,000,000, budget, 201,977, 63.57 | 7, 86,327, threshold, 2,819, 13.96 | 1.017 | 1.0008 |
| H1 + 30 Jy, not chosen on | 2, 1,000,000, budget, 230,317, 127.31 | 7, 88,682, threshold, 2,522, 16.45 | 0.982 | 1.0009 |
| H4 + 30 Jy, not chosen on | 2, 1,000,000, budget, 242,203, 28.73 | 6, 55,509, threshold, 30,688, 7.85 | 0.992 | 0.9997 |
| S2 + 30 Jy off 20 px, not chosen on | 9, 268,263, threshold, 45,249, 20.52 | 6, 94,678, threshold, 4,558, 16.02 | 1.073 | 1.0024 |
| H3 + 100 Jy, not chosen on | 2, 1,000,000, budget, 344,761, 225.71 | 8, 166,396, threshold, 6,263, 27.63 | **1.120** | 1.0006 |

The S1 + 10, 30 and 100 Jy default rows are the `7982b73` runs of [stop-rule-theorem.md](stop-rule-theorem.md) §5. In
every `f = 0.01` row the inner residual peak is within 0.18 % of 100 µJy and the source pixel within 0.0051 %. Cost: one
or two more cycles than the sky alone, none on H3. These are the model's own figures, not the truth-based false flux.

**Comparison values.** `f = 0.05` is not a no-op: on S1 it keeps 5 cycles but changes the images (85,784 components against
85,337, off-source Σ|flux| 13.958 against 13.953 Jy). `f = 0.02` and `0.05` also end the failure on S1 plus 30 and 100 Jy,
at 6-7 cycles.

**What this does not show.** `f = 0.01` was chosen after seeing every ordinary sky, so the no-op on them is by construction
and is not evidence on other skies. Only four failure cases were not used to choose it, all simulated. There is no proof,
and no real observation with such a source. A sky where a later cycle's stop falls below 1 % of its first peak would change.
The floor does not touch the 6, 6, 8, 5 cycles of [gemclean-heldout.md](gemclean-heldout.md). No wall time here is a result.

The problem: a first cycle that cleans only a phase-centre source measures an error near zero, because
the centre column of the beam error is exactly zero, and the next cycle then has no stop. On S1 plus
30 Jy the default reaches the component budget with about 200,000 model pixels
([stop-rule-theorem.md](stop-rule-theorem.md) §5).

The proposal: `-stale-floor f` ends a later cycle at the larger of the measured level and `f` times that
cycle's first peak. It needs no extra gridder call, and `f = 0` is the rule as it was.

**The value is not held out.** `f = 0.01` was chosen after seeing every ordinary sky. The smallest ratio of a
cycle's first peak to the previous cycle's is 0.018 on S1, 0.020 on S2, 0.033 on S3, 0.030, 0.087, 0.042 and 0.094
on H1-H4, and 0.029 on the pilot. So 0.01 should not bind on any of them, and a 5 % floor binds on most.

## The bar

For `f = 0.01`, from `-j 8` runs of `examples/stale_floor_runs.py`:

1. **No change on ordinary skies.** Model, residual and image identical in data to the archived default on S1-S3
   (`58e07e1`) and H1-H4 (`f0ca931`).
2. **The failure is gone where the value was chosen,** S1 plus 10, 30, 100 and 1000 Jy at the centre: stop at the
   threshold, model pixels at most 1.1 × S1's 2,772, off-source Σ|flux| at most 1.01 × S1's 13.95 Jy, inner residual
   peak within 1 % of 100 µJy, source pixel within 0.01 %.
3. **It is gone where the value was not chosen,** by the same measures against that sky's own default run: H1 plus
   30 Jy, H4 plus 30 Jy and H3 plus 100 Jy at the centre, S2 plus 30 Jy 20 pixels off centre. If the default does not
   fail on a case, that is reported and the case only has to stay no worse.

If 1 fails, the floor changes the benchmark and the held-out results, and needs them rerun. If 2 or 3 fails, the
default stays and the failure stays documented. Either way this says nothing about the 6, 6, 8, 5 cycles of
[gemclean-heldout.md](gemclean-heldout.md): a floor that does not bind cannot change them. `f = 0.02` and `0.05` are
run on S1 plus 30 and 100 Jy, and `0.05` on plain S1, for comparison only.
