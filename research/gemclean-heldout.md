# Rang: GeMClean's default on held-out data

Status: **proposed; pre-registered, no held-out result yet.** Branch `gemclean-heldout`.
The claim under test ([gemclean.md](gemclean.md)): the default stop rule
(`MeasuredStale { rho: 1, g: 0.95 }`, chosen on S1-S3) gives 4-5 major cycles at
WSClean-level false flux. Constants unchanged; code at `f0ca931`, `core/src/gemclean*`
untouched here.

## Pre-registered bar (written before any held-out imaging)

Skies H1-H4 (`examples/gemclean_bench_simulate.py --sky H*`), abs threshold 100 µJy,
Briggs 0.5, gain 0.1, `-j 16`, `examples/gemclean_bench_compare.py score`, WSClean
3.7 `nominres` plain and fast at mgain 0.8. New sky seeds 20261201-4, new noise seeds
20261211-4.

- H1 dec −75, 2 h, 60 points 5 mJy-1 Jy. H2 dec +10, 2 h, 300 points 0.2-200 mJy,
  blended. H3 dec −30, 4096 × 1.5″ (twice the benchmark's field at its sampling), 120
  points 5 mJy-1 Jy. H4 dec −45, 30 points, 6 Gaussians FWHM 20-200″, a 25-Gaussian
  curved tail of 3 Jy.
- **Survives on a sky** if GeMClean has at most 5 major cycles, at most as many as
  WSClean's fast loop, and false |flux| at most 1.6 × the lower of WSClean's two
  loops (1.53 was the worst ratio on S1-S3), with Q/Q_truth within 0.2 % of WSClean
  plain and recovery no worse by more than 0.5 %.
- **The claim survives on simulation** if it holds on every sky. Partial is reported
  sky by sky. Extended flux on H4 is compared, not barred.
- **Real data has no truth:** the same numbers in spirit (cycles, off-source flux in a
  shared mask, misfit, residual peak), and anything unlike the simulations is reported.
