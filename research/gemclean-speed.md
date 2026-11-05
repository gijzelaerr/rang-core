# Rang: GeMClean against WSClean 3.7, wall time on a quiet host

Status, 2026-11-04: **measured against WSClean built for this CPU; no claim of novelty.** At `-j 16` GeMClean is faster on all seven
skies, narrowly on H2 and H3. At `-j 1` WSClean is faster on H1-H3 at its best setting tried. GeMClean uses 3-5 times the memory.
Archives: [results/gemclean-speed-native.json](results/gemclean-speed-native.json) (this pass),
[results/gemclean-speed.json](results/gemclean-speed.json) (the SSE2 package). Outputs: `D:\rang\outputs\20261104-speed`
(`native/`, `opt/e1`, `opt/e2`; `out/` and `sse2/out/` for the package).

## Against WSClean built for this CPU (measured)

WSClean v3.7 (`4f395b2`) from source, `-DPORTABLE=OFF`, in `rang-wsclean-native:3.7` ([Dockerfile](../tools/oracles/wsclean-native/Dockerfile)):
about 79,800 ymm and zmm instructions, against none in the package. GeMClean as before, `3945394`. Threshold 100 µJy, Briggs 0.5, gain 0.1.
Wall time in seconds. "GeMClean" and "`nominres`" have the same gridding accuracy (1e-6); "GeMClean coarse" is `-single -wgridder-accuracy 1e-4`,
to set against WSClean's default accuracy, 1e-4 in `minres`. GeMClean, its coarse form and `-mgain 0.8` are medians of three repeats; `-mgain 0.9` and `0.95` are one run each.

`-j 16`:

| Sky | GeMClean | GeMClean coarse | WSClean `nominres` | `minres` | `minres -mgain 0.9` | `minres -mgain 0.95` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| S1 | 14.5 | 9.7 | 27.2 | 17.6 | 13.2 | 20.4 |
| S2 | 14.9 | 9.9 | 28.2 | 19.0 | 14.0 | 20.9 |
| S3 | 12.2 | 8.5 | 22.3 | 16.2 | 20.2 | 14.8 |
| H1 | 17.0 | 10.7 | 27.3 | 16.7 | 14.7 | 21.5 |
| H2 | 19.5 | 14.8 | 24.0 | 16.4 | 15.6 | 21.5 |
| H3 (4096²) | 54.9 | 35.5 | 66.1 | 41.0 | 41.0 | 107 |
| H4 | 14.7 | 9.6 | 34.5 | 27.9 | 39.8 | 76.0 |

`-j 1`:

| Sky | GeMClean | GeMClean coarse | WSClean `nominres` | `minres` | `minres -mgain 0.9` | `minres -mgain 0.95` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| S1 | 54.3 | 35.4 | 112 | 52.3 | 37.4 | 38.7 |
| S2 | 55.0 | 36.4 | 115 | 58.1 | 36.9 | 39.2 |
| S3 | 46.4 | 29.6 | 83.8 | 44.5 | 38.7 | 30.1 |
| H1 | 64.0 | 44.5 | 113 | 52.7 | 37.9 | 40.7 |
| H2 | 72.8 | 54.2 | 80.6 | 44.1 | 35.7 | 35.8 |
| H3 (4096²) | 206 | 129 | 192 | 97.1 | 77.3 | 134 |
| H4 | 56.0 | 35.1 | 91.4 | 54.3 | 59.3 | 93.4 |

The fastest WSClean `minres` setting over GeMClean coarse, S1, S2, S3, H1, H2, H3, H4: 1.36, 1.41, 1.74, 1.37, 1.05, 1.15, 2.91 at `-j 16`, and
1.06, 1.01, 1.02, 0.85, 0.66, 0.60, 1.55 at `-j 1`. WSClean's best time on each sky is picked after the fact among three `-mgain` values, so these ratios favour it.
At matched accuracy, `nominres` over GeMClean: 1.21-2.35 at `-j 16`, 0.93-2.09 at `-j 1`.

Accuracy at `-j 16`, scored through the exact gridder (`examples/gemclean_bench_compare.py score`), first repeat. Each cell is
GeMClean coarse / `minres` / `minres -mgain 0.9`; the last column is GeMClean's default and WSClean's `nominres`.

| Sky | Q/Q_truth | false flux, mJy | exact inner peak, µJy | major cycles | false flux, mJy, GeMClean / `nominres` |
| --- | --- | --- | --- | --- | --- |
| S1 | 1.01359 / 1.01372 / 1.01420 | 4.32 / 5.34 / 5.24 | 125 / 187 / 269 | 5 / 9 / 5 | 4.34 / 3.70 |
| S2 | 1.01517 / 1.01514 / 1.01634 | 4.91 / 6.02 / 6.23 | 122 / 176 / 286 | 5 / 9 / 5 | 4.88 / 3.93 |
| S3 | 1.00987 / 1.01002 / 1.00994 | 1.56 / 1.65 / 1.52 | 102 / 214 / 149 | 4 / 6 / 4 | 1.57 / 1.53 |
| H1 | 1.01417 / 1.01469 / 1.01431 | 1.43 / 4.71 / 4.67 | 108 / 265 / 212 | 6 / 8 / 5 | 1.43 / 1.12 |
| H2 | 1.00999 / 1.01059 / 1.01075 | 6.09 / 7.21 / 9.97 | 101 / 223 / 276 | 7 / 6 / 4 | 6.16 / 6.93 |
| H3 | 1.02541 / 1.02584 / 1.02610 | 11.77 / 9.93 / 10.99 | 107 / 317 / 258 | 7 / 9 / 5 | 11.84 / 7.97 |
| H4 | 1.00336 / 1.00304 / 1.00334 | 5.23 / 8.50 / 31.36 | 100 / 169 / 282 | 5 / 6 / 4 | 5.33 / 8.04 |

Coarse gridding hardly moves GeMClean's own scores: Q/Q_truth by at most 1e-4, false flux by at most 0.1 mJy. The exact inner peak rises to as much as
125 µJy for a 100 µJy threshold, and the cycle counts change on H2 and H3 (6 to 7, 8 to 7). Deeper `-mgain` costs WSClean false flux, most on the extended sky: 8.5, 31, 101 mJy on H4 at 0.8, 0.9, 0.95.
At 0.95 false flux is above GeMClean coarse's on all seven skies, at 0.9 on all but S3 and H3 (full rows in the archive).

Peak RSS, GB, 2048² / H3: GeMClean 3.4 / 6.0; coarse 2.2-2.45 / 5.3; WSClean `nominres` 0.80 / 1.84; `minres` 0.57 / 1.11.

Reading this:

- **The `-j 16` lead is in part thread scaling, not per-core speed.** WSClean `minres` gains 3.0 times from 16 threads on S1, GeMClean coarse 3.7 times, and deeper `-mgain` can make WSClean's `-j 16` run nearly as slow as `-j 1`
  (H3 at 0.95: 107 s against 134 s, for 4 cycles; the cause was not looked at). WSClean runs in Docker with its data on a bind mount; beyond the 0.3-0.9 s of the container start that has not been costed.
- **Against the novelty rule: still not met.** Coarse GeMClean at `-j 16` is the first form faster on every sky, at mostly equal or better scores. But false flux on H3 and misfit on S2 and H4 are worse than `minres`, the gain on H2 and H3 is 5-15 %, a single core reverses it
  on the hard skies, memory is 3-5 times worse, the data are simulated on one host, and S1-S3 are the skies the stop rule was tuned on.
- **WSClean `minres` at `-j 16` is not repeatable,** on all seven skies: 2,499 to 46,064 model pixels differ between repeats of one command, up to 2.6 mJy. Its scores are of one repeat and carry that scatter, not measured here. GeMClean's images are identical across all repeats, default and coarse, and between 1 and 16 threads at the default.
- **`-mgain` was the only WSClean setting tuned here.** Others might help it. GeMClean's coarse form has not been run on the real pilot.

Run details. 129 native runs 2026-11-04, interleaved, plus 42 GeMClean coarse and 14 at `1e-5` (not tabled; in the archive), and 30 at other `-mgain` with its control, not interleaved. The S1 `minres` control repeated at 17.3 s and 49.8 s against 17.6 s and 52.3 s. All exits 0. Spread of three repeats at most 14 %.
The runs used working copies of the Measurement Sets, and their checksum files were deleted with them, so that check is not on record for this pass; the source sets on `D:` were not opened for writing, and `-j 1` and GeMClean images repeat exactly. The held-out `prepare` arrays had been removed and were rebuilt in `D:\rang\outputs\20261104-speed\prep-h`.

## Tuning after the native pass (measured; provisional, not a result)

One run per setting and sky, not interleaved, all with `-single -wgridder-accuracy 1e-4`. Archive: [results/gemclean-speed-tuning.json](results/gemclean-speed-tuning.json); drivers: [results/gemclean-speed-scripts/](results/gemclean-speed-scripts/). No default changed.

**Where the time goes.** At `-j 1` resyncs take 19 % of the wall on S1 (6.98 of 36.9 s) and 43 % on H3 (57.4 of 132 s), more than H3's major cycles (46.2 s). At `-j 16` S1: resync 2.2 s, major 3.2 s. Nearly all are triggered by the tau certificate (164 of 170 on H3). This is why GeMClean loses on one core on the hard skies, and it was not known before this profile. The profile's binary has no symbols, so only the phase times count.

**`-tau-min`.** Default 0.5. Wall time, `-j 16` / `-j 1`, seconds; the coarse row's are medians of three repeats:

| Setting | S1 | S2 | S3 | H1 | H2 | H3 | H4 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| coarse, 0.5 | 9.7 / 35.4 | 9.9 / 36.4 | 8.5 / 29.6 | 10.7 / 44.5 | 14.8 / 54.2 | 35.5 / 129 | 9.6 / 35.1 |
| 0.3 | 9.7 / 36.4 | 8.8 / 33.1 | 7.5 / 27.5 | 10.6 / 47.0 | 11.1 / 47.1 | 27.6 / 102 | 9.1 / 33.4 |
| 0.2 | 9.4 / 36.2 | 8.7 / 32.9 | 7.4 / 27.6 | 9.6 / 37.8 | 10.0 / 40.7 | 27.5 / 103 | 8.9 / 34.0 |
| 0.1 | 9.5 / 36.3 | 8.8 / 32.8 | 7.5 / 27.4 | 9.3 / 37.8 | 9.3 / 38.2 | 29.1 / 106 | 8.5 / 33.6 |

At 0.2 Q/Q_truth moves by at most 2.4e-4 (S2, 1.01517 to 1.01541), false flux by at most 0.25 mJy (S2) and the exact inner peak by at most 2 µJy. Against the fastest WSClean `minres` setting on each sky, again favouring it: 1.40-3.13 at `-j 16`, 0.75-1.60 at `-j 1`, slower on H2 and H3 on one core, level on H1. The cycle count is unstable at the margin: S1 goes from 5 to 6 at 0.2, H1 from 6 to 5, and a run's time follows it. That is one reason not to read these rows closely. The picks change, so this is a numerical change for the owner to decide, with no bar written first.

**Band-limited resync, `-beam-band`.** The 2n PSF has little power beyond the longest baseline, and 1.5″ oversamples the beam, so the outer half-spectrum columns of the resync's convolver need not be transformed. Off by default; with it off, the images on S1 at `-j 16` were byte-identical to `3945394`. A first rule, by the rms of what is dropped, cut real signal, and is not in the tree. On S1 at `-j 1` it kept 2005 of 2049 columns at 1e-6, 831 at 1e-5 (resync 6.5 to 3.8 s) and 532 at 1e-4, where the major cycles went from 18.8 to 86.9 s. The rule in the tree computes the columns from the longest baseline, the highest frequency and the w-term at the image corner, plus 8: 1092-1100 of 2049, 2185 of 4097, with 2.4e-6 to 8.8e-6 of the peak (rms) left out, logged per run. That is more than rounding: the window's edge and coarse gridding put power out there.

| With `-beam-band` | S1 | S2 | S3 | H1 | H2 | H3 | H4 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `-tau-min` 0.5, `-j 16` / `-j 1` | 10.5 / 34.9 | 10.6 / 35.0 | 9.2 / 30.4 | 13.1 / 44.7 | 15.1 / 48.3 | 33.1 / 113 | 11.2 / 35.2 |
| `-tau-min` 0.2, `-j 16` / `-j 1` | 8.9 / 31.8 | 10.2 / 35.8 | 8.2 / 27.5 | 9.8 / 41.3 | 10.4 / 38.3 | 27.5 / 99.0 | 9.4 / 32.6 |

Scores at `-tau-min` 0.5 barely move: Q/Q_truth by at most 3e-5, false flux by at most 0.17 mJy. **Whether it saves time is not settled.** On H3 at `-j 1` the clean phase went from 105.6 to 90.2 s, but several `-j 16` rows are slower than without it, which less work should not cause. These ran on another day, one run each, so the host may be the cause. An interleaved on/off test of the same binary (`opt_e6.sh`) was stopped after its first pair, S1 `-j 16`: 10.14 s off, 9.98 s on, resync 2.29 and 2.15 s. It says nothing yet. Peak memory hardly moves, so the peak lies elsewhere. **Next: run that test to the end, then keep or remove the flag.** Band limiting saved under 0.3 GB on H3 and nothing at 2048².

## Against the SSE2 package (measured)

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

The third run, WSClean built for this CPU, is the section above.

## Where the time goes

Per cycle and cycle count are different effects. On S1 at `-j 16`, inversion and prediction take WSClean `nominres` 28.5 s
over 9 major cycles; GeMClean's major cycles take 6.0 s over 5, plus 2.3 s for the 2n PSF. The part of the gap
that comes from the method is the cycle count, and that part has its own limits:

- S1-S3 are the skies the stop rule was tuned on: 5, 5, 4 cycles against 9, 9, 6. On the held-out skies GeMClean used
  6, 6, 8, 5 against WSClean fast's 9, 6, 9, 6 ([gemclean-heldout.md](gemclean-heldout.md)), so the same ratio cannot be
  expected there. They were timed in the section above.
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

Not measured: real data, `-channels-out`, WSClean settings other than `-mgain`, and any other host.
