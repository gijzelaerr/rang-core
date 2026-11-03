# Rang: a floor on GeMClean's measured stop rule

Status, 2026-11-03: **proposed; written before any run with the floor.** Branch `stale-floor`.
Owner's decision: test this on a branch, after the held-out test. The default is unchanged.

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
