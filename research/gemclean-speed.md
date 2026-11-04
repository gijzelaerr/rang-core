# Rang: GeMClean against WSClean 3.7, wall time on a quiet host

Status, 2026-11-04: **measured, and not a matched comparison.** GeMClean is faster than the packaged WSClean, but that
WSClean's gridder has no instruction wider than SSE2 and GeMClean's uses AVX-512. With GeMClean capped to its baseline
code the lead is gone. No claim of novelty follows. Archive: [results/gemclean-speed.json](results/gemclean-speed.json).
Outputs: `D:\rang\outputs\20261104-speed` (`out/` the main pass, `sse2/out/` the baseline pass, with both binaries).

## Result

Median wall time of three repeats, seconds, S1 / S2 / S3 at 100 µJy (`abs`). `nominres` is
`-no-min-grid-resolution -wgridder-accuracy 1e-6`, GeMClean's own gridding accuracy; `minres` is WSClean's default
grid and accuracy, coarser than GeMClean's.

| Imager and build | `-j 16` | `-j 1` | peak RSS, GB |
| --- | ---: | ---: | ---: |
| GeMClean, x86-64-v3, kernels AVX-512 | 14.6 / 14.9 / 12.5 | 56.9 / 55.6 / 46.4 | 3.4 |
| GeMClean, x86-64, kernels at baseline | 36.7 / 37.0 / 31.3 | 329 / 330 / 276 | 3.4 |
| WSClean fast, `nominres`, SSE2 package | 33.6 / 34.6 / 27.2 | 165 / 166 / 121 | 0.80 |
| WSClean fast, `minres`, SSE2 package | 20.8 / 21.4 / 18.4 | 79.6 / 80.5 / 60.1 | 0.57 |
| WSClean plain loop, `nominres`, SSE2 package | 322 on S1 | not run | 0.80 |

WSClean time over GeMClean time:

| Against | `nominres`, `-j 16` | `nominres`, `-j 1` | `minres`, `-j 16` | `minres`, `-j 1` |
| --- | ---: | ---: | ---: | ---: |
| GeMClean AVX-512 | 2.2-2.3 | 2.6-3.0 | 1.4-1.5 | 1.3-1.5 |
| GeMClean baseline | 0.87-0.94 | 0.44-0.51 | 0.57-0.59 | 0.22-0.24 |

The two rows bracket the question and neither answers it. The first gives GeMClean AVX-512 against SSE2. The second is
pessimistic for GeMClean: its major-cycle time at `-j 1` rises 7.5 times (33.8 to 254 s on S1), and GeMClean has no
hand-written SSE2 path, while WSClean's gridder is built for that width. The cause of the 7.5 was not analysed. FFTW in the WSClean
image holds AVX code in both rows, as GeMClean's FFT does.

The number that needs a third run is WSClean built for this CPU. It has not been built, because that takes a source download.

## Where the time goes

Per cycle and cycle count are different effects. On S1 at `-j 16`, inversion and prediction take WSClean `nominres` 28.5 s
over 9 major cycles; GeMClean's major cycles take 6.0 s over 5, plus 2.3 s for the 2n PSF. The part of the gap
that comes from the method is the cycle count, and that part has its own limits:

- S1-S3 are the skies the stop rule was tuned on: 5, 5, 4 cycles against 9, 9, 6. On the held-out skies GeMClean used
  6, 6, 8, 5 against WSClean fast's 9, 6, 9, 6 ([gemclean-heldout.md](gemclean-heldout.md)), so the same ratio cannot be
  expected there. Those skies have not been timed.
- The two loops do not end at the same place. WSClean fast stops at inner peaks of 178-245 µJy, GeMClean at 100 µJy, and
  WSClean's plain loop at 102-117 µJy, for 22 times GeMClean's time on S1 at `-j 16`. The plain loop is almost all
  deconvolution, 298 of 322 s, and is not how WSClean is normally run.
- WSClean fast `nominres` has less false flux on all three: 3.5, 3.2, 1.5 mJy against GeMClean's 4.3, 4.9, 1.6
  ([gemclean-benchmark.md](gemclean-benchmark.md)).

Memory goes the other way: GeMClean peaks at 4.2 to 5.9 times WSClean's RSS.

## Against the novelty rule

Not met. A lower runtime at comparable quality would count, but the runtime gain is not shown to survive a matched build,
it is largest on tuned skies, memory is several times worse and false flux is slightly worse. What is measured
is narrower: on these three skies and this host, GeMClean as built here runs 1.3-1.5 times faster than the KERN WSClean package at its
default settings, and 2.2-3.0 times faster at matched gridding accuracy. A user of that package would see this;
it says little about the method.

## Reproducibility seen in passing (measured)

- GeMClean: model and residual pixel-identical over the three repeats and between `-j 1` and `-j 16`. All five images at
  `-j 16` are pixel-identical to those of `58e07e1` on S1-S3, so the accuracy table of the benchmark's rerun applies here.
  AVX-512 against baseline: models identical, residuals differ in 2 to 10 of 4,194,304 pixels, at most 3.6e-12 Jy.
- WSClean `minres`, `-j 16`, same command, same data, three repeats: 2,801 to 4,811 model pixels differ, up to 1.1 mJy, and
  nearly every residual pixel, up to 0.21 mJy. At `nominres` the models are identical, and one residual pixel differs
  at rounding level. All `-j 1` jobs are identical. This is stronger than item 3 of the
  [WSClean report draft](../outputs/clean-theory-20261030/wsclean-report-draft.md), which compares thread counts only. The draft has not been changed.

## Run details

Commit `3945394`. Host: 16 threads, WSL 2; data and outputs on the WSL disk. Heavy lock held per job.

- Main pass: `examples/gemclean_bench_timing.sh`, 57 jobs, interleaved, WSClean first on odd repeats, 03:25 to 04:47 on
  2026-11-04, far below the 3.3 h estimated from contended runs. All exits 0, Measurement Sets unchanged. Spread of three repeats at most 7.7 %, except
  WSClean S2 `nominres` `-j 1`, where one repeat took 188 s against 165 s.
- Baseline pass: `RUSTFLAGS="-C target-cpu=x86-64"` with `RANG_WGRIDDER_SIMD=baseline RANG_GEMCLEAN_SIMD=baseline`, 18 GeMClean
  jobs and 6 WSClean controls, run after the main pass and not interleaved. All exits 0. Spread at most 1.4 %. The controls
  repeat the main pass: 33.0 s and 164 s against 33.6 s and 165 s, so the host had not changed.
- Builds: `cargo +1.93 --profile gemclean` (fat LTO). WSClean `3.7-1kern1` in `rang-o-casa:6.7.6.14`; `/usr/bin/wsclean`
  holds the gridder and has 0 ymm or zmm instructions in 1.4 M. The baseline GeMClean binary still contains wide code,
  which the two variables keep from the gridder and kernels but not from its FFT.
- Docker: a WSClean wall above is measured inside the container. Outside it adds 0.3-0.9 s.
- Host load: the other processes above half a core at job boundaries were Spotify's launcher (about 55 %) and, in two
  rep 1 `-j 1` jobs, `llama-server` (about 100 %), an effect the spread does not show. `WmiPrvSE` is the load probe itself.
  Load before a job is mostly the decay of the job before it, and the 60 s load samples add little, since most jobs last about one sample.

Not measured: WSClean built from source, held-out skies, real data, `-channels-out`, GeMClean at a coarser gridding accuracy,
and any other host.
