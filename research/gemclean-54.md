# Issue #54: a multiscale scale whose convolved PSF has no positive peak

Bug fix, branch `gemclean-54` from origin/main `c215821e`, 2026-11-21. No scientific or
performance claim.

**Bug.** `gemclean -multiscale` with the automatic scale list stopped before any cleaning with
`the PSF convolved with scale ~1,600 has no positive peak` on four #43 images (E2-N scan R3,
simulations T1-T3; 4096², 3″). The tenth automatic scale, about n / 2.5 pixels, sums the PSF over
most of the image. Coverage without short spacings (one scan, or 2 h) makes that sum zero or
negative.

**What WSClean does** (radler `bb56daeb`, 2026-11-19, `cpp/algorithms/multiscale_algorithm.cc`):
`InitializeScales` limits the automatic list to scales below half the image side and to
`max_scales`. `SetScaleInfo` then sets `gain = minor_loop_gain / psf_peak` and `is_active = true`
whatever the peak's sign, with no check. So WSClean runs on, with a negative or infinite gain for
such a scale; in #43's finished runs that scale took no components.

**Fix** (`core/src/gemclean/multiscale.rs`, `run_multiscale_masked`):

- Each scale's peak (radler's circular sum, unchanged) is computed before the run.
- A scale other than 0 whose peak is not positive and finite is **dropped**. The log prints
  `warning: multiscale scale <s> px dropped: the PSF convolved with it has no positive peak (<peak>)`,
  and the report's multiscale section gets `dropped_scales` (scale, peak). The section is unchanged
  when nothing is dropped.
- Scale 0 without a positive peak, or no scale left, is still an error.
- Departure from radler, by design: radler keeps such a scale with a non-positive or infinite gain.
- Bias factors of the kept scales are unchanged. They depend on the scale count only through
  "fewer than two".

**Checks.**

| Check | Result |
| --- | --- |
| Reproduction | T1-like simulation on glacier: `examples/gemclean_bench_simulate.py --sky H4 --nchan 8 --fmin 0.856e9 --fmax 1.712e9 --size 4096 --scale 3` (8 channels instead of 64; 1,814,400 rows), the issue's command with `-niter 1000 -channels-out 8 -j 8`. Main's build (the dl1-interp venv): rc 2, `the PSF convolved with scale 1653.3159385933832 has no positive peak`. This branch: rc 0, the warning with peak −4.66e-7, nine scales, 1,000 components, 384 s. |
| Bit-identity (nothing dropped) | Same MS and command with `-multiscale-max-scales 9` (no scale dropped), main's build against this branch: **all 45 FITS byte-identical** (dirty, PSF, model, residual, image; 8 channels and MFS). The report differs in timings, the output path, and `dq_predicted`/`gap` in the 16th digit (−0.18007650358447017 against −0.1800765035844702). That diagnostic is a rayon parallel sum: a second run of this branch gives main's value exactly (two runs of each build: old, old, new −…702, new −…7017). Not a result of the change. |
| Unit test | `a_scale_without_a_positive_psf_peak_is_dropped`: a PSF lowered by 0.02 makes the 24-px scale's peak ≤ 0. The run keeps 0 and 4, drops 24, cleans, and reports `dropped_scales`. A PSF of −1 still fails at scale 0. |
| Existing tests | the 11 other multiscale tests and the core suite (315) pass; quick check. Full-check oracle gates (G5's WSClean comparisons) left to the coordinator's merge check. |

Not checked: a WSClean run on this MS (the behaviour above is from radler's source); E2-N R3 itself
(nash, the #43 data).
