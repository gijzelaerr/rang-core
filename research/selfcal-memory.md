# Rang: the scan-long self-calibration solve within the default memory limit (issue #34)

Status, 2026-11-17: **proposed, frozen before any code.** Branch `selfcal-memory`. Host for the
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
