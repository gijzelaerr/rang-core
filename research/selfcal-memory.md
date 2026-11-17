# Rang: the scan-long self-calibration solve within the default memory limit (issue #34)

Status, 2026-11-17: **measured (section 5): G1, G2a, G3 pass; G2b runs to the end, its 9.3 GiB peak is GeMClean.** Frozen in `bc8f515` before any code; sections 1-4 unchanged since. Branch `selfcal-memory`. Host for the
measurements: **nash** ([nash-host.md](nash-host.md)), heavy lock, `nice -n 19 ionice -c3`.

## 1. The problem, from the archive

[selfcal-defaults.md](selfcal-defaults.md) (section 8.2, clarification 1): on the E2 pilot (823,500
rows x 256 channels x 4 correlations = 843.3 M cell-correlations, one 1 h scan) the default
self-calibration (Sp then Sa, `solint: inf`) is refused at the default `data.memory_limit_gb: 8`:
`rang.cal_chunks.plan` holds one solution interval whole and plans it at `CELL_BYTES["chain"]` = 96
bytes per cell-correlation. The grid ran D at 96 GiB.

The archived peaks (`/usr/bin/time %M`, KiB, `research/results/selfcal-defaults/logs/grid-*.log`)
follow the limit, not the solution interval:

| limit (GiB) | runs | selfcal peak (KiB) |
| --- | --- | --- |
| 12 | L60, L120, L300, M*, N60-N300, and L600-attempt1, which was refused **before** its first solve | 9,747,132-9,749,172 |
| 16 | L600, M600, N600, X | 11,637,708-11,666,580 |
| 96 | D | 37,119,920 |

So the 9.3 GiB at 12 GiB comes from a stage before the solve (model prediction or apply, both
planned at 64 bytes per cell, or GeMClean, which does not read the limit). The issue's "13.6 GiB
planned against 11.7 GB measured" compares the solve's plan with another stage's peak. Nobody has
measured a selfcal solve on its own. At 96 GiB the model and apply chunks hold the whole MS (D's
summary: 1,560,613 rows a chunk), so D's 37 GB peak cannot be put on the solve either.

## 2. Design

**Streamed solve (`rang.cal_stream`, new; Rust `rang_core::cal::diag_stream`, new).** It is used
for an Sp or Sa solve (`calmode` p or ap, QuartiCal rules, no time or frequency pre-averaging)
whose smallest unit, one solution interval, does not fit the budget. Today those solves are
refused. Every solve that fits today keeps its present path, so no result that rang gives now
changes.

1. **One read pass.** The field's rows are read in blocks of whole rows within the budget and
   prepared as now (`_Field.prepare`). Each block then goes through the kernel's own cell rules
   (`cal_gain.finite_cells`, autocorrelations and FLAG_ROW, and `solve::data_flags`: any flagged
   correlation, a zero parallel-hand datum or weight). The unflagged cells go to a scratch
   directory next to the MS, in field-row then channel order, each with its interval index
   `(time bin, frequency bin)`, its two antennas and its 4-correlation data, model and weights
   (92 bytes a cell). The same pass gives the per-row weight sums (solution times) and the
   kernel's initial gain flags (a gain is live when an unflagged cell involves it).
2. **Iterations.** Each iteration accumulates `J^H J` and `J^H r` per gain over the scratch
   cells, read back in blocks, and then steps every gain. A serial global stop test follows
   (converged fraction over all gains), then QuartiCal's final flags and referencing. The kernel
   (`cal::diag`) sums each interval's cells serially in row-then-channel order. The stream keeps
   that order within each interval, and intervals do not share sums. `diag.rs` runs epochs of 8
   iterations and rewinds to the stopping iteration, which by its own documentation equals the
   serial loop. The accumulate, step, flag and reference functions are `diag.rs`'s own, made
   `pub(crate)` and split where needed, with no arithmetic changed. The new files hold only the
   driver (MIT).
3. **Memory.** The resident part is the field's row metadata, one read block and one scratch
   block, whatever the interval's length. Disk use is 92 bytes per unflagged cell (pilot: about
   76 M cells, 7 GB), deleted after the solve.
4. **Not covered.** CASA's statistics `snr` and `err` are NaN on the streamed path (the selfcal
   solve does not read them; `casa_rules` solves stay on the present path). Sd (delay) and the
   CASA-rule G/K/B solves keep refusing an interval that does not fit.

**Planner.** The selfcal solve gets its own figure per cell-correlation (`CELL_BYTES["selfcal"]`).
It is fitted to a solve-only peak measured on the pilot: one 600 s interval, 142.4 M
cell-correlations, on the present path. The shared `CELL_BYTES["chain"]` (K, G, B, polarisation
chunks) does not change. The figure decides only which path a selfcal solve takes, never its
result.

## 3. Gates (frozen)

- **G1, identical solutions.** The streamed path against the present path at a budget that holds
  the interval: gains, flags, iterations and converged fraction `np.array_equal` (row weights
  too). Checked on:
  - (a) synthetic tests: Sp and Sa; several intervals and frequency bins; flags, zero weights,
    zero data, a non-zero cross-hand model, an antenna without data; several block sizes;
  - (b) the public fixture (`RANG_FIXTURE`, `outer_scans.zip`): Sp and Sa at `solint: inf`;
  - (c) the pilot on nash: Sp and Sa at `solint: inf` against `MODEL_DATA`, the present path at
    a budget of 96 GiB.
  - Any difference is a defect. No tolerance applies. A tolerance could only enter as a dated
    clarification written before the comparison that needs it.
- **G2, the default fits.** On the pilot, at the default limit (no `memory_limit_gb` key):
  - (a) the streamed Sp and Sa `inf` solves, each in its own process, peak at or below 8 GiB =
    8,388,608 KiB (`%M`);
  - (b) `rang-core selfcal` with the default self-calibration (D's config without
    `memory_limit_gb`) runs to the end without a refusal. Its whole-process peak (GeMClean
    included) is reported against 8,388,608 KiB.
- **G3, planner.** For a 600 s interval on the pilot, the selfcal plan is at least the measured
  solve-only peak and at most 1.15 times it. On a 300 s interval, the plan is at least the
  measured peak.
- Reported, not gated: wall times of the streamed and present solves; D's stored round-1 gains
  against the new run's, if the round-1 models' hashes are equal.

## 4. Decision rule

- G1 and G2a pass: the streamed path is kept, and #34 item 1 is done.
- G2b's peak above 8 GiB: the excess stage is named with its measured peak, and the issue stays
  open for that stage.
- G3 passes: the new figure is kept. If it fails, the figure stays at 96 and the measured peaks
  are recorded.
- G1 fails: nothing is merged.
- No novelty or speed claim. This is a resource fix.

## 5. Results

Measured 2026-11-17 on **nash** (heavy lock, shared, `nice -n 19 ionice -c3`; solve-only runs 2 slots,
`RAYON_NUM_THREADS=2`; the pipeline 8 slots). Worktree code at `346de18` with `CELL_BYTES["selfcal"]` still 96
for the runs (the figure only picks a path). Pilot rebuilt from floor-5's read-only copy of `cal2.ms`
(`selfcal_grid.py base` 93 s, `prepare D` 38 s, the same 128 held-out channels flagged) into
`~/rang-data/outputs/selfcal-memory-20261117/D/pilot.ms`. Logs and the driver in
`~/Build/tmp/20261117-selfcal-memory/`; solutions and records (`*.npz`, `*.json`) in `.../solves/`; the
archive copy in [results/selfcal-memory/](results/selfcal-memory/).

| gate | measured | verdict |
| --- | --- | --- |
| G1a synthetic | Rust `diag_stream` tests: `diag_complex` and `phase`, 1-3 intervals x 1-5 frequency bins, blocks of 1, 7, 64 and all cells, bits equal; Python `tests/test_selfcal_memory.py`: Sp and Sa at `solint` 3 and `inf`, `freqint` inf, 2 and 4, read blocks of 1, 7, 40 rows and the auto switch, `np.array_equal` (row weights too) | **pass** |
| G1b fixture | `outer_scans.zip` (scan 9), Sp and Sa `inf` against a 1 Jy point model, streamed = one-call | **pass** |
| G1c pilot | Sp `inf`: 13 iterations, Sa `inf`: 37, gains, flags, times, fraction equal streamed (limit 8) and one-call (limit 96) | **pass** |
| G2a solve peak | streamed Sp 3,798,392 KiB, Sa 3,799,516 KiB (3.62 GiB) against 8,388,608 | **pass** |
| G2b default run | `rang-core selfcal`, D's config without `memory_limit_gb`: ran to the end, 2,207 s; whole-process `%M` 9,748,364 KiB (9.30 GiB), above 8,388,608 | **runs; peak above, from GeMClean** |
| G3 planner | 600 s interval (142,417,920 cells) peak 6,282,172 KiB (5.991 GiB), plan at 45 B 6.815 GiB (1.138 x); 300 s (71,208,960 cells) peak 3,210,836 KiB (3.062 GiB), plan 3.830 GiB | **pass** at 45 |

**G2b, the excess stage.** The rang-core process itself peaked at 6,722 MiB (receipt `peak_rss_mb`,
`RUSAGE_SELF`), under 8 GiB. The 9.30 GiB `%M` covers the GeMClean child (4096², `-j 8`), which does not
read `data.memory_limit_gb`. The grid's limit-12 runs peaked at the same 9,747,132-9,749,172 KiB
whatever their solint, L600-attempt1 too, which never solved. So that figure was GeMClean all along.
Under the decision rule, #34 stays open for GeMClean's memory (its own limit, or a documented figure).

**Planner (G3).** The fit uses the solve-only peaks of the present path (`examples/selfcal_memory.py solve
--stream false`, the process holding `inspect_ms`'s rows as rang-core does). The figures per cell above the
fixed part (0.846 GiB: process, MS rows and field rows) are 38.8 B (600 s), 33.4 B (300 s) and 43.9 B for the
one-call scan-long interval (843,264,000 cells, 37,066,116 KiB, the archived D's 37.1 GB). The frozen band
for 600 s allows 38.8-45.6 B. 45 is chosen, not the minimum, because it also covers the scan-long point
(plan 36.19 GiB against 35.35 measured). That choice is reported here as post hoc reasoning inside the
frozen band. At the default 8 GiB a chunk now holds 170 M cells, so a 600 s interval of the pilot solves
on the present path. The archived "13.6 GiB planned against 11.7 GB measured" was the solve's plan
against a different stage's peak (section 1). The present path at 600 s peaks at 6.0 GiB.

**Reported.** The new run's round-1 and round-2 gain stores equal the archived D's (old path at 96 GiB)
bit for bit: same round-1 and round-2 model hashes, 13 and 37 iterations. Every final FITS file is
identical; only `image-report.json` (timings) differs.
- Wall times, solve-only: Sp streamed 358 s against one-call 329 s; Sa 575 s against 409 s.
- The read pass is 134 s of each streamed solve.
- The cell file holds 76,089,333 unflagged cells (7.00 GB), deleted after each solve.
- In the pipeline the solves took 343 s (Sp) and 575 s (Sa), against D's 299 s and 429 s. The whole run
  took 2,207 s, against D's 2,041 s.

**Outcome.** G1 and G2a pass, so the streamed path is kept and #34 item 1 is done: the default
self-calibration runs on the pilot at the default limit, with the archived D's solutions. G3 passes, so
`CELL_BYTES["selfcal"]` = 45. G2b: GeMClean's 9.3 GiB is the remaining item of #34. No novelty or speed
claim.
