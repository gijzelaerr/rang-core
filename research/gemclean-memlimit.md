# Rang: GeMClean within `data.memory_limit_gb` (issue #34, last item)

Status, 2026-11-28: **proposed.** Sections 1-5 frozen before any code. Host **glacier** (Windows,
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

Not yet measured.
