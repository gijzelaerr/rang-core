# Rang: GeMClean within `data.memory_limit_gb` (issue #34, last item)

Status, 2026-11-28: **measured (section 6): Q, R and E pass; kept.** GeMClean estimates its own peak
within 1.03-1.08 x of the measured peak working set on all nine cases (never below), refuses the
unflagged pilot (10.6 GiB measured, 11.07 estimated) at 8 GiB, and the default selfcal on the held-out
pilot is byte-identical (15 FITS, both gain stores). Sections 1-5 frozen before any code (`db1d117e`;
clarification 1 `84e9ec24` and amendment A1 `928764b9` before any branch code ran). Host **glacier** (Windows,
16 threads, 63 GB; heavy lock, at most 8 slots / 24 GB for this task). Branch `gemclean-memlimit`.
Follows [selfcal-mem-34.md](selfcal-mem-34.md) (its stage B and gate Q are the design taken up
here) and [selfcal-memory.md](selfcal-memory.md).

## 1. What is left of #34

- **The solve planner is settled.** The issue's "13.6 GiB planned against 11.7 GB measured" compared
  the selfcal solve's plan with another stage's peak (selfcal-memory.md, sections 1 and 5). The solve
  is planned at `CELL_BYTES["selfcal"]` = 45 B per cell (600 s: 6.82 GiB planned, 5.99 GiB measured,
  1.138 x, the slope margin under 2 %, the safety in the fixed part). It is not retuned here: a lower
  figure risks under-predicting on a lightly flagged MS (that note's caveat).
- **What is open:** GeMClean, the child process of `image` and `selfcal`, reads no memory limit and
  has no estimate. On the grid's pilot copy (63 % of cells flagged) the default selfcal peaks at
  7.53 GiB (nash), under the default 8 GiB. The same MS without the hold-out flags would need about
  11.4 GB (estimate from the buffer report), and nothing would stop it. "The planner's prediction"
  of this task is therefore the new GeMClean estimate.

## 2. Design

1. **GeMClean option `-memory-limit <GiB>`** (rang's own; not WSClean's `-abs-mem`, which plans and
   does not refuse). Without it nothing changes. With it, on the validated path (point 3), GeMClean
   computes an estimate E of its own peak resident memory after the read, the weighting and the row
   compaction, and before the 2n PSF pass. If E is above the limit it stops with exit code 1 and a
   message that names E in GiB, the limit and what to raise; no image is written. The read itself
   (about 24 B per cell read, as on nash) comes before the check; its measured peak is part of E.
2. **E, a maximum over the phases**, from the sizes the run knows at that point: the process's own
   peak working set so far (the read and the weights, measured), its present working set, the image
   size, the gridder's grids (its own setup: nu, nv, plane group, precision), the kept rows' cells
   (dense arrays to the compaction) and the weighted cells (the clean holds 44 B per weighted cell:
   visibilities 8, weights 8, sorted index 8, stored sorted values 16, permutation 4). Phases: the 2n
   PSF pass, the plan and beam, the compaction, the major and minor cycles. Coefficients come from
   the exact buffer sizes of the memory report; a fixed part per phase is fitted on the fit cases of
   section 3 only.
3. **Validated path only:** one polarisation, `-channels-out 1`, no `-multiscale`, no
   `-gram-operator`, plan reuse on, no `-stop-rule certified`, `-floor-iterations 0`, no
   `-channel-range` or `-average-channels`, no masks. Elsewhere `-memory-limit` logs "no estimate for
   this path" and runs as without it. The selfcal images and rang's default `image` stage take the
   validated path.
4. **rang passes the limit.** `gemclean_arguments` appends `-memory-limit <data.memory_limit_gb /
   data.processes>` for `image` and `selfcal` (the only change in `core_pipeline.py`). The limit is
   per process, as `%M` and the stages' budgets are: the rang-core parent is not counted in
   GeMClean's figure. The argv in the stage summaries gains the two words; no image changes.

## 3. Cases and gates (frozen)

All on glacier, the E2 pilot rebuilt here from `cal2.ms` (`selfcal_grid.py base`; the held-out copy by
`prepare D`), run root `D:/rang/outputs/20261128-gemclean-memlimit`. Images are the selfcal round-1
argv (D's config: Briggs 0.5, 3″, threshold 3 mJy, `-j 8`, accuracy 1e-6, so double precision),
GeMClean through the extension (`python -m rang.gemclean`, as the pipeline runs it). M is GeMClean's
`peak_memory_bytes` (the peak working set on Windows).

| case | MS | size | role |
| --- | --- | --- | --- |
| F1 | held-out copy | 4096² | fit |
| F2 | held-out copy | 2048² | fit |
| V1 | base (no hold-out) | 4096² | validation, the binding case |
| V2 | base (no hold-out) | 2048² | validation |
| V3 | held-out copy | 3072² | validation |

- **Q, the estimate.** For every case, M <= E <= 1.15 M (selfcal-mem-34's frozen Q); and, when F1's
  M is below 8 GiB, F1's E too, so the default selfcal on the pilot is not refused. (If F1's M on
  glacier is above 8 GiB, B1 below runs with `memory_limit_gb` set above E instead, and that is
  reported.)
- **R, refusal.** V1 with `-memory-limit 8` stops before the PSF pass, exit 1, the message naming E;
  with `-memory-limit` above E it runs and its FITS equal V1 without the option (SHA-256).
- **E, identity.** B0: `rang-core selfcal` with D's config on main (`24572b76`), held-out copy, no
  `memory_limit_gb` set (the default 8), `-memory-report`. B1: the same on the branch, its own copy,
  so GeMClean gets `-memory-limit 8`, not binding. Every FITS of the three images and every file of
  both gain stores equal (`compare_runs.py` of selfcal-mem-34); solver records equal. No tolerance.
- **P, peaks reported** (before and after): B0's and B1's largest process and tree sum (psutil,
  `scripts/peak.py`), GeMClean's `peak_memory_bytes` per image.
- Tests: refusal message and the "no estimate" path on the public fixture; the argv change; the
  estimate's lower bound against the measured peak on the fixture.

**Clarification 1, 2026-11-28 15:50 SAST (before any F or V run; only B0, main's selfcal, had
started).** rang's default `image.wgridder_accuracy` is 1e-4, so the default `image` stage and the
default selfcal images grid in single precision; D's config (1e-6) grids in double. The estimate's
per-cell terms follow the precision's type sizes, and each precision gets its own fit and validation
cases, read under the same Q: F3 held-out 4096², F4 held-out 2048² (fit), V4 base 4096², V5 held-out
3072² (validation), all with `-wgridder-accuracy 1e-4` and otherwise F1's argv. How the fit is done
(stated before it): the fixed parts are fitted on the heap phases of the F cases run through the
`gemclean` binary (its counting allocator; the extension counts nothing on Windows), and Q is then
read on the extension's `peak_memory_bytes` for every case, F included.

**Amendment A1, 2026-11-28 15:30 SAST (design, before any branch code ran).** Section 2 point 4 said
`data.memory_limit_gb / data.processes`. gemclean runs alone: the chunk tasks that `data.processes`
divides the limit among do not run beside it. rang passes `data.memory_limit_gb` whole. No gate
changes (every case here has `processes` 1).

## 4. Decision rule

- Q, R and E pass: kept; #34 can close.
- E fails: nothing is merged.
- Q fails on the lower bound (E < M) for any case: the refusal is not kept (an estimate that
  under-predicts would let a run pass a limit it breaks); the estimate is reported, #34 stays open.
- Q fails only on the upper bound or on F1's 8 GiB: E's fixed parts may be refitted on F1 and F2
  once, dated as post hoc, and the validation cases re-read; a second failure keeps #34 open.
- The estimate is validated on glacier only (Windows working set, no huge pages); on nash it is
  unmeasured. No novelty or speed claim: a resource fix.

## 5. For the coordinator (open decisions)

- The default limit refuses as a set one does (rang's solve and chunk planners do the same). A lightly
  flagged MS of the pilot's size, which today images at about 11 GB under the default 8, will be
  refused with the figure to raise `data.memory_limit_gb` to. Planning within the limit (smaller
  plane groups, `-reorder`-style spills) is not built.

## 6. Results

Measured 2026-11-28 on **glacier** (Windows 11, heavy lock shared, 8 slots, 16 GB booked, `-j 8`,
`RAYON_NUM_THREADS=8`; another task's 4-slot check ran beside some cases). Run root
`D:/rang/outputs/20261128-gemclean-memlimit` (pilot base and three copies, about 40 GB; image outputs).
Pilot rebuilt from `D:/rang/outputs/20261103-gemclean-heldout/real/cal2.ms` (`selfcal_grid.py base`,
34 s; `prepare D` 8-11 s per copy): 823,500 rows x 256 channels; held-out copy 76,089,333 weighted
cells, base 152,158,164. Archive: [results/gemclean-memlimit/](results/gemclean-memlimit/) (`fit.json`
with every case's phases and inputs, the reports, `peak.json` per run, logs, scripts).

**Fit** (binary, heap phases; `scripts/fit.py`). The first fit gave a PSF part per 2n pixel of 26.9 at
4096² and 83.1 at 2048²: not a per-pixel cost. The missing term was the PSF pass's stored sorted values
(2t per weighted cell), added to `memlimit.rs` before any extension case was read (post hoc to the
binary fit, dated here). With it the fixed parts agree across sizes and precisions: per 2n pixel
8.7 / 10.6 (f64, F1 / F2) and 6.6 / 10.7 (f32, F3 / F4); beam 69.9-74.2; clean 164.5-186.6 B per pixel.
The constants are the larger of each pair, rounded up (`fixed.json`). E for each extension case is
recomputed from the inputs it recorded with these constants (the extension that ran the cases had zero
fixed parts; the final build, used for R1 and B1, prints the same figures: B1 round 1 E 7.875 GiB).

**Gate Q** (M = GeMClean's `peak_memory_bytes` through the extension; E with the 1.03 margin):

| case | MS | size | precision | M (GiB) | E (GiB) | E / M | binding phase | wall |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: |
| F1 | held out | 4096² | f64 | 7.517 | 7.860 | 1.046 | psf 2n | 152 s |
| F2 | held out | 2048² | f64 | 6.603 | 6.800 | 1.030 | psf 2n | 68 s |
| F3 | held out | 4096² | f32 | 6.279 | 6.793 | 1.082 | cycles | 85 s |
| F4 | held out | 2048² | f32 | 5.056 | 5.192 | 1.027 | psf 2n | 39 s |
| V1 | base | 4096² | f64 | 10.641 | 11.065 | 1.040 | cycles | 194 s |
| V2 | base | 2048² | f64 | 8.383 | 8.616 | 1.028 | cycles | 101 s |
| V3 | held out | 3072² | f64 | 6.643 | 6.892 | 1.038 | psf 2n | 83 s |
| V4 | base | 4096² | f32 | 8.592 | 9.128 | 1.062 | cycles | 137 s |
| V5 | held out | 3072² | f32 | 5.778 | 6.060 | 1.049 | psf 2n | 59 s |

Every case M <= E <= 1.15 M; F1's E is 7.86 GiB, below 8. **Q passes.** On glacier the F1 peak (7.52
GiB) matches nash's M1 (7.53).

**Gate R.** R1 = V1 with `-memory-limit 8`: stopped 17 s in, after the read, before the PSF pass, no
FITS written, exit code 2 (gemclean's error code; section 2 said 1): "the estimated peak memory,
11.06 GiB (in the major and minor cycles), is above -memory-limit 8 GiB; raise the limit to at least
11.1 (rang-core: data.memory_limit_gb), ...". V1 (`-memory-limit 1000`) and V1-plain (no option): all
five FITS SHA-256 equal. **R passes.**

**Gate E.** B0 = main `24572b76` (built in this worktree before any change), B1 = the branch, each on
its own held-out copy, D's config without `memory_limit_gb` (so the default 8; B1's gemclean argv carries
`-memory-limit 8`), `-memory-report`. `compare_runs.py`: 98 files identical, all 15 FITS and every file
of both gain stores included; the 8 that differ are the 3 `gemclean.log`, the 3 `image-report.json`
(argv, `memory_estimate`, paths, timings, peaks), `summary.json` (argv, timings) and `state.json`
(paths, times, flag-version name, binary hash) ([compare-B0-B1.json](results/gemclean-memlimit/compare-B0-B1.json)).
**E passes.**

**Peaks, before and after** (psutil, largest process / tree sum; the pipeline's wall):

| run | wall | largest process (GeMClean) | tree sum | GeMClean per image (bytes) | rang-core |
| --- | ---: | ---: | ---: | --- | ---: |
| B0 (main) | 889 s | 7,882,528 KiB (7.52 GiB) | 7,982,692 KiB | 8,070,451,200 / 8,071,708,672 / 8,071,139,328 | 6,830,080 KiB |
| B1 (branch) | 963 s | 7,882,896 KiB (7.52 GiB) | 7,983,408 KiB | 8,071,716,864 / 8,072,085,504 / 8,070,926,336 | (as B0) |

The check changes no peak (it runs on arrays already held; the footprint scans add about 1-2 s per
image). The wall difference is a shared host's, not a speed figure.

**Outcome.** Q, R and E pass: the refusal is kept. GeMClean now respects `data.memory_limit_gb` when
`rang-core run`/`image`/`selfcal` call it, on the single-image path of one polarisation; a lightly
flagged pilot-size MS at the default 8 GiB is refused with the figure (11.1) instead of running at
10.6 GiB. Not covered (logged, not checked): several polarisations, `-channels-out` above 1, channel
selection or averaging, multiscale, the Gram operator, `-no-plan-reuse`, the certified rule, the floor
and masks (selfcal's auto-masks included: a selfcal config with `cleanmask_*` or `auto_mask` runs
unchecked). The read itself (24 B per cell read) precedes the check. Validated on glacier only. The
solve planner is unchanged (section 1). No novelty or speed claim.
