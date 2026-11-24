# Chunk task API, stage 1b: CASA-table apply and the chain terms through the executor

Issue gijzelaerr/rang-core#3, what is left of it after [chunk-task-api.md](chunk-task-api.md) (stage 1, merged): that
stage put flag, the `complex` solve and `complex` apply through `plan`/`run`/`reduce` and a local process pool
(identity gate passed on 17 comparisons, 2026-11-14), and [multinode-executor.md](multinode-executor.md) added the
spool executor (#4). Still serial in the parent: CASA-table apply (`applycal.applycal`), the chain terms (K, G, B,
F, Gpol, KCROSS, Xf, Df; `cal_chain.run`) and image. Branch `chunk-api-3`, from main `e071bdab`. Infrastructure
work: no novelty is claimed; the gate is identity, timing is reported for #4's decisions.

**Status, 2026-11-23: implemented and measured (section 6).** Sections 0 to 5 were frozen in `fce3f82c` before any code; amendments 1 and 2 are dated. Identity criteria 1-5 pass everywhere; criterion 6 fails as worded on two small-set P4 arms; timing not obtained.

## 0. Probes before the design (not comparisons)

- **Thread count.** Stage 1's probe covered the `complex` solve, `apply_jones` and `flag_rows`. This stage adds
  kernels: `cal_delay` (K, both kinds), `cal_gain` (G), `cal_bandpass` (B), `cal_pol` (Gpol, KCROSS, Xf, Df) and
  `cal_apply.apply` with P (`applycal.applycal(parang=True)`, calwt on). `tools/oracles/chunk_tasks/thread_probe.py`
  runs each at `RAYON_NUM_THREADS` 1, 2, 4 and 1 again, in fresh processes, on W3b's unit-test MS
  (`calibrator_ms` with a feed, the `pol_ms` of `tests/test_w3b_chainchunks.py`), and compares the SHA-256 of every
  table and of CORRECTED_DATA, FLAG and WEIGHT. Result: see 0.1 (filled in before the design was frozen).
- **The state stage 1 left.** Before this note, at `e071bdab`:
  - the nash timing matrix of chunk-task-api 5.1 has 2 of 15 points (W-B-r0, W-N1-r0); its driver and the pinned
    worktrees `cta-run-abdfb5a` and `cta-oracle-30d9412` are gone from nash; `timing.json` is in
    `~/rang-data/outputs/cta-nash-20261116/` with the other 13 points "not run yet";
  - #4's spool executor measured S(N) on nash on a shared host only (provisional), and no exclusive point.

### 0.1 Thread-probe result

Run 2026-11-23 on glacier under the heavy lock (4 slots), this branch's extension (`core/` and `src/` equal to
`e071bdab`'s), work directory `outputs/probe/t1` in the worktree. Every output was equal at 1, 2, 4 and 1
threads: K `54f471fe…`, G `f6384568…`, B `5b76d15e…`, Gpol `44f7bf5a…`, KCROSS `c136f41d…`, Xf `f0103c97…`,
Df `1409240e…`; after applycal with P and calwt, CORRECTED_DATA `b3d8b5b7…`, FLAG `3bcfac8f…`, WEIGHT
`df17181b…`. **PASS.** Limit: the test MS is small (4 antennas), so rayon may not have split some loops; the
identity arms of section 3 at `threads: 4` against U at 4 threads (P4 runs one thread per worker) test the
large sets.

## 1. Design (proposed)

### 1.1 CASA-table apply (`applycal.applycal`), by row chunk

- The loop body over one row chunk (read row metadata and cells, apply the tables per (field, ddid) group, P,
  the weight reset and calwt scales, the counts and the uncovered set) moves into one function,
  `applycal._apply_rows(source, start, nrow, ctx)`, which never writes. The serial path calls it for every
  chunk and writes its partial, so the default runs the same code as the pool.
- `applycal.applycal` gains `executor=None` (inline). With an executor that is not inline, and every table given
  as a **path**, the chunks become `apply-casa` specs: `start`, `n`, the table paths, interp, the field maps
  (per table, field → table field or `pooled`), the fields, scans, `applymode`, the calwt flags, the output
  column and the P settings; P's angle tables (computed once in the parent over the whole field, as now) travel
  as arrays. A worker reads the tables from their paths once per process (cached by path, size and mtime).
- Reduce in plan order through the stage's `WriteBack` session: the output column, FLAG, and WEIGHT and
  WEIGHT_SPECTRUM when calwt writes them; the counts add up (integers) and the uncovered sets join.
- Tables given as `CalTable` objects (the A step inside `calibrate`) stay inline: nothing is on disk for a
  worker to read. The apply stage passes paths, so it goes through the pool.

### 1.2 The chain terms, by solution-interval chunk and by field

A chain solve keeps W3b's structure: the field's row metadata whole, cell arrays read in chunks of whole
intervals (`cal_chunks.plan`), the stop test replayed over the chunks in two passes (`cal_chunks.replayed`),
the post-solve steps (reference antenna, `fill_gaps`, minsnr, solution times, table writer) on the assembled
solutions in the parent. The tasks:

- **`chain-chunk`**: one chunk of one replayed solve, pass 1 (stop test off, counted: returns the per-iteration
  counts, the error and the gain count) or pass 2 (`max_iterations = j + 1`, stop off: returns the chunk's
  kernel result and its row weights). The spec carries a **recipe** of the solve, not its live state: the
  function (`cal_chain._solve_one` or `_solve_pol`), the term (configuration dicts), the field, the earlier
  tables by path (`cal_chain` writes every term's table before the next term starts), the common settings and
  the `ChainBudget` as numbers. The worker runs the recipe with a marker that makes `cal_chunks.replayed` run
  only the spec's chunk and return its result, so it builds the field, its chunks, its model and its
  pre-applies with the parent's own code. The plan is the same in parent and worker: same code, same
  budget, same tables.
- **`chain-field`**: one field of a term with several fields (K, G, B, Gpol, KCROSS, Xf, Df): the worker runs
  the recipe whole and returns `(table, solution, info)`; the parent appends in field order
  (`cal_fluxscale.append`, as now). Used when a term has two or more fields; its fields' solves then chunk
  inline inside each worker under the per-process budget.
- Only the **first** replayed solve of a recipe is dispatched. A recipe that calls `replayed` again (none of
  `_solve_one` or `_solve_pol` does at `e071bdab`, as far as the code reads) runs later calls inline in the
  parent, so a worker never needs the result of an earlier solve it did not run.
- Barriers: between terms (term k pre-applies the tables of terms before k), and between pass 1 and pass 2 of
  a solve (the stop replay needs every chunk's counts).
- Serial still: F (`cal_fluxscale.bootstrap` solves several fields in sequence with a reduction across them), the
  A step (its applycal is given `CalTable` objects, its `flag_corrected` writes), Df's streamed gauge (three passes
  over the field before the closed-form solve), the KCROSS, Xf and Df chunk loops (closed forms, not
  `replayed`), the averaged paths (`average_time`, `average_freq`), streamed solves (`cal_stream`) and the
  self-calibration terms. These run as today; the cases below check they are unchanged, nothing more.

Departures from the issue's wording: calibrate splits by solution-interval chunk and by field, not by channel
block (B, Xf and Df chunks are channel blocks within an interval where W3b already cuts them); the reductions the
issue names for fluxscale, Df, Xf and KCROSS stay in the parent, serial (above).

### 1.3 Image

Not built here. DL0 ([dl0-profile.md](dl0-profile.md)) measured major cycles (the gridding a per-channel split
would distribute) at 1.6-2.3 % of E2-A's and E2-N's self-calibration, and the minor cycle at 63-65 %: by Amdahl
the ceiling of distributing gridding over channels is about a 2 % saving in self-calibration and somewhat more
for `image` alone with many output channels. A per-output-channel split (as `wsclean-mp`) is left as a note for
#4, with that ceiling stated, unless the owner asks for it.

### 1.4 Keys, memory, errors

- No new configuration key and no new `RANG_*` variable: `data.executor`, `data.processes`, `data.threads`
  (stage 1) now also reach `applycal.applycal` and `cal_chain.run` from the apply and calibrate stages.
- Memory: as stage 1, `data.memory_limit_gb / processes` per process; the parent holds the stage's metadata and
  up to 2N partials (apply: the output column, FLAG and weights of a chunk; chain: one chunk's kernel result).
  Peak memory is reported, not gated.
- Errors: a failing task raises at its turn in plan order (stage 1's rule); for a pass-1 solver error the
  replay raises it where the one-call solve raises (W3b 1.2), unchanged.
- `RANG_SOLVE_TRACE` with N > 1 stays refused (stage 1).

## 2. Data and cases (frozen)

Host glacier (Windows, the host in `STATE.md`), shared under the heavy lock at normal priority, at most 8 slots.
Every arm on a fresh copy in `D:\rang\outputs\cta1b-<yyyymmdd>-<nn>\<case>-<arm>\`, sources read only, hashes
with rang's reader in 128 MiB row chunks (stage 1's `tools/oracles/chunk_tasks/run.py` `hashes`).

| Case | MS | Stages | Configuration |
| --- | --- | --- | --- |
| C | A1 small (`D:\rang\outputs\fp-a1-20261106-simtruth\small\a1-small.ms`) | calibrate, apply | stage 1's case C (W3b's C: K, G, B, A; Gsec, Asec, F; CASA apply) |
| P | poldx (`D:\rang\outputs\c6w-20261106-01\prepared.ms`) | calibrate, apply | stage 1's case P (W3b's P: K, G, B; F; Gpol, KCROSS, Xf, Df; apply with parang) |
| M | A1 small | calibrate, apply | case C with a G term `G2` of two fields (`field: [J1939-6342, SIM-GCAL]`, `solint: int`, pre-applying K and B) before F in the secondary section (`chain-field` tasks), and `apply.calwt: true` |
| W | W3's whole-array set (`D:\rang\outputs\w3\data\w3.ms`) | calibrate, apply | W3b's case W (K `int`, G `int`, B `inf` `combine: scan` on the fcal), apply K, G, B to every field |

**Amendment 1** (2026-11-23, while writing the harness `tools/oracles/chunk_tasks/run_1b.py`, before any
comparison): W's apply uses the default targets (each term on the fields it was solved on, the fcal), as W3b's
`WHOLE` configuration has no apply section; "apply K, G, B to every field" above is withdrawn.

**Amendment 2** (2026-11-23, after run `cta1b-20261123-02`'s W arms were refused and before any W comparison; C, P
and M had been compared, their protocol is unchanged): (a) amendment 1 was wrong: a chain run needs explicit
`apply.targets`, and W's apply was refused in U and P1 alike (exit 2), so W applies `{field: [fcal], tables: [K, G,
B]}`; (b) at the default 8 GiB, P4 gives each process 2 GiB, and one K or G interval of W's fcal needs 3.587 GiB:
preflight refused P4's calibrate before writing (the designed refusal, 1.4). Every W arm (U, P1, P4) therefore runs
at `memory_limit_gb: 20` (5 GiB per P4 process) with a 24 GB booking. The refused W arms are kept as
`W-*.void-amendment2` in the run root.

Arms:

- **U, today's single process (the oracle):** main `e071bdab`'s Python from a detached worktree
  (`~/Worktrees/rang/cta1b-oracle-e071bdab`) with this branch's extension build; `git diff e071bdab -- core/ src/`
  stays empty (no Rust change). Default configuration.
- **P1:** this branch at the defaults (`processes: 1`).
- **P4:** this branch, `processes: 4, threads: 4`.
- **P2T:** this branch, `processes: 2, threads: 2, chunk_rows: 7` (C, P, M): many chunks per solve and per apply
  through the pool. Not on W.

Slots: 4 (U, P1, P4), 2 (P2T). Memory: 4 GB on C, P, M; 20 GB on W (U and P1), 12 GB (P4).

## 3. Criteria (frozen before the first comparison)

No tolerance: the executor changes no arithmetic. Each of P1, P4, P2T against U; a difference is a failure,
reported as measured.

1. **Columns:** after each stage every MS column's SHA-256 equals U's.
2. **Flag versions:** after the last stage, the list and every version's FLAG and FLAG_ROW hashes equal U's.
3. **Tables:** every file under `<run>/calibrate/` except `summary.json` byte-identical to U's.
4. **Summaries:** each stage's `summary.json` equal to U's after stage 1's cleaner (`run.py` `VOLATILE`).
5. **Exit:** every stage command exits 0.
6. **Work went through the pool:** in P4 and P2T, the calibrate summary's `chunking` record counts `chain-chunk`
   tasks above zero on C, P and W, `chain-field` tasks above zero on M, and the apply summary counts `apply-casa`
   tasks above zero on every case. (A pass by identity alone would not show that anything ran in a worker.)
7. **Unit tests** (pytest, CI on Linux and Windows): an `apply-casa` and a `chain-chunk` spec round-trip through
   JSON; on the W3b test MS, `applycal` (with P and calwt), K, G, B, Gpol and a two-field G at `processes: 2` with
   7-row chunks equal `processes: 1` (tables, columns); `CalTable` objects stay inline; a failing chunk task raises
   in plan order.

**Decision:** stage 1b's identity gate passes when 1-7 pass on every case and arm.

## 4. What is not checked (stated before the run)

- F, the A step, Df's gauge, the KCROSS/Xf/Df chunk loops, averaged and streamed solves and the
  self-calibration terms in a worker: they do not go through it (1.2).
- Image (1.3).
- Linux identity arms: CI's unit tests only. macOS: not checked.
- Peak memory: reported, not gated.
- A held-out case: none; identity fits nothing.

## 5. Timing (frozen here; run when the lock allows)

**Stage 1's matrix is closed as not completed:** 2 of 15 points (chunk-task-api 6.1), on code `abdfb5a`, which
main has since passed. It is not resumed: its pinned worktrees are gone and 8 h exclusive on superseded code buys
little. This section replaces it, on this branch's final code.

- **Host nash**, exclusive among this account's jobs (`heavy_lock.py run -- ...` with no slots), queued only when
  `heavy_lock.py status` shows no hold and an empty queue (the coordinator's rule of 2026-11-17), under
  `nice -n 19 ionice -c3`, with chunk-task-api 5.1's load record and void rule (foreign load above 2.0 cores voids
  a point; three attempts).
- **Case W** of section 2 plus stage 1's flag: flag, calibrate (the chain of section 2's W) and apply, each on a
  fresh copy in the run root's own copy of `w3.ms` (file SHA-256 checked against D:'s).
- **Thread budget T = 16**, N ∈ {1, 2, 4, 8} at `threads: 16`, `memory_limit_gb: 32`; baseline B main `e071bdab`
  at `RAYON_NUM_THREADS=16`, `memory_limit_gb: 32`. One repeat per point (5 points, about 3 h); a second and third
  repeat only if the lock stays idle.
- **Reported:** wall per stage, S(N) = t(N1)/t(N), efficiency S(N)/N, time to the first task, peak RSS of the
  largest process, foreign load, identity of each point against B (criteria 1-4).
- If no idle window comes before the hand-back, the points are reported as not obtained and the driver's
  command is left for the coordinator.

## 6. Results (measured 2026-11-23)

Code: branch `chunk-api-3`, `c37a8699` (`5375c029` plus the row-weight fix below), harness at `6d2e94e3`. Oracle U: main `e071bdab` from the
detached worktree `C:\Users\gijsm\Worktrees\rang\cta1b-oracle-e071bdab` with this branch's `_core.pyd` (SHA-256
`6023d006…`; `git diff e071bdab -- core/ src/` empty). Host glacier, shared under the heavy lock at normal priority.
Run root `D:\rang\outputs\cta1b-20261123-03` (P1, P4 and P2T on `c37a8699`; U's arms copied from `-02`, whose code is
main's and unchanged; hashes, logs and summaries kept, MS copies deleted); verdict copied to
[results/chunk-task-api-1b-identity.json](results/chunk-task-api-1b-identity.json).

**Verdict: criteria 1-5 pass on every case and arm; criterion 6 fails as frozen on C-P4 and P-P4; criterion 7
passes.** So by section 3's decision rule the gate **does not pass as frozen**. The failure is in what criterion 6
asked of P4 on the small sets, not in any result (below).

| Case | Files compared | P1 | P4 | P2T | Tasks in P4 (calibrate; apply) | Tasks in P2T |
| --- | ---: | --- | --- | --- | --- | --- |
| C (A1 small, chain + CASA apply) | 162 | identical | identical | identical | none; 2 `apply-casa` | 148 `chain-chunk`; 3,566 `apply-casa` |
| P (poldx, pol chain, parang apply) | 243 | identical | identical | identical | none; 3 `apply-casa` | 528 `chain-chunk`; 5,349 `apply-casa` |
| M (C with a two-field G, calwt apply) | 189 | identical | identical | identical | 2 `chain-field`; 2 `apply-casa` | 148 `chain-chunk`, 2 `chain-field`; 3,566 `apply-casa` |
| W (`w3.ms`, K/G/B chain) | 81 | identical | identical | (not run) | 82 `chain-chunk`; 10 `apply-casa` | – |

"Identical": every MS column after calibrate and after apply, the flag versions, every file under
`<run>/calibrate/` byte for byte, and the cleaned summaries; every stage command exited 0.

- **Criterion 6 (post hoc reading, not a change of the criterion).** On C and P at P4 the default 8 GiB gives
  2 GiB per process, in which every solve of these small sets fits one chunk, so `replayed` has nothing to
  dispatch (a single chunk is solved in the parent, 1.2). Stage 1's note said the same of P4 on the small sets
  ("one chunk per group or partition"); the criterion should have asked `chain-chunk` of P2T and W-P4 only. Where
  there was more than one chunk, the chunks went through the pool and the results were identical: C-P2T, P-P2T,
  M-P2T and W-P4.
- **Criterion 7.** `tests/test_chunk_tasks_1b.py`, 9 tests, pass on Windows: spec round trips; CASA apply with
  calwt and with P at 2 processes; CalTables staying inline; G and Gpol by `chain-chunk`; a failing task raising
  after the partials before it; the chain command with and without a two-field term. With the related suites (W3,
  W3b, c4b, c2e, c6w, spool, calwt, Xf calwt, fluxscale, reweight, c5 selfcal) 110 passed, 4 skipped at
  `5375c029`; `check_all.py --quick` on `c37a8699` PASS on glacier (338 passed, gain-hash gate PASS); CI `tests`
  green on Linux and Windows.
- **A cost found and fixed between runs -02 and -03.** At 5 GiB per process W-P4 cut B into 17 channel chunks
  (34 tasks over the two passes), and every one re-read all rows of the fcal at all channels for the row weights
  (the solution times), which the serial path reads once per field and memoises. In `c37a8699` the counted pass
  skips them (it never uses them) and pass 2 memoises them per recipe in each worker. Run -02 (on `5375c029`)
  gave the same identity verdict; its W walls were calibrate U 421.4, P1 526.7, P4 586.2 s.
- **Walls** (s, calibrate / apply; shared host, **not timing results**): W U 421.4 / 28.2, P1 566.5 / 40.4,
  P4 524.9 / 34.2. P4 ran one rayon thread per worker against U's four. Each `chain-chunk` task still re-runs its
  recipe up to the replayed solve (the field's metadata, model, solution bins and earlier tables) before its chunk;
  section 5 measures what that costs.

**Void and refused runs, kept.**
- `D:\rang\outputs\cta1b-20261123-01-void`: C, P and M arms failed while writing their configuration (the harness's
  config hook called itself), before any stage ran; W-U was stopped mid-calibrate when the oracle worktree was
  removed by another session's cleanup pass. No verdict drawn; `VOID.txt` in it.
- `W-*.void-amendment2` in the run root: W's first arms, refused at apply in U and P1 (no `apply.targets`) and at
  calibrate in P4 (2 GiB per process), which led to amendment 2.

### 6.1 Timing (section 5), measured 2026-11-24 on nash

The driver (6.1 as first written: started 2026-11-23 09:20 SAST, pid 311413, on `c37a8699`; B on main `e071bdab`)
found its idle window on 2026-11-24 and ran the five points 05:26-07:12 SAST, one repeat each (r0; no second repeat
was queued). Run root `~/rang-data/outputs/cta1b-nash-20261123/` (`w3.ms` copy checked against D:'s by SHA-256),
`timing_1b.py report RUN` copied to [results/chunk-task-api-1b-timing.json](results/chunk-task-api-1b-timing.json).
Every stage exited 0; foreign load 0.17-0.31 cores on every stage (void rule 2.0: no point void). **Identity
against B (criteria 1-4): no difference at any point** (every MS column after each stage, flag versions, the files
under `calibrate/`, the cleaned summaries).

| Point | flag (s) | calibrate (s) | apply (s) | S(N) calibrate / apply | efficiency calibrate / apply | first task, calibrate / apply (s) | peak RSS calibrate / apply (GB) |
| --- | ---: | ---: | ---: | --- | --- | --- | --- |
| B (main, rayon 16) | 178.7 | 681.0 | 93.8 | – | – | – | 17.0 / 14.5 |
| N1 | 179.1 | 686.2 | 94.8 | 1.00 / 1.00 | 1.00 / 1.00 | none (serial) | 17.0 / 14.5 |
| N2 | 189.2 | 559.3 | 81.2 | 1.23 / 1.17 | 0.61 / 0.58 | 56.3 / 41.3 | 8.5 / 8.7 |
| N4 | 204.7 | 464.0 | 74.1 | 1.48 / 1.28 | 0.37 / 0.32 | 51.3 / 41.0 | 3.5 / 7.0 |
| N8 | 195.6 | 417.0 | 68.5 | 1.65 / 1.38 | 0.21 / 0.17 | 48.5 / 43.0 | 1.8 / 4.5 |

- N1 equals B within 0.8 % on every stage: the executor at one process costs nothing measurable.
- Calibrate gains 1.65 × at 8 processes (681 to 417 s), apply 1.38 ×. The first task starts 48-56 s into
  calibrate and 41-43 s into apply, so about 50 s of each calibrate and 40 s of each apply is serial set-up before
  any work reaches the pool; with that subtracted, calibrate's pooled part goes from about 630 s to about 370 s.
  Cores used in calibrate rise only from 3.7 (N1) to 6.8 (N8) of 16.
- Flag does not go through the pool (chunk-task-api 1.x); its wall rises 6-14 % at N2-N8 (179 to 189-205 s), with
  the same CPU seconds, from the per-process thread split.
- Peak resident set of the largest process falls with N (calibrate 17.0 to 1.8 GB), which is what the memory
  limit per process is for.
- One repeat per point, so no spread is reported; S(N) is read from single walls.

**Found in passing (not this task's code):** `tests/test_v030_fix.py::test_fully_flagged_gaincal_ends_run_with_a_stage_failure`
fails on nash (Linux, with `RANG_FIXTURE` set) on this branch **and on main `e071bdab`** with the same extension:
calibrate exits 0 where the test expects a stage failure. CI does not see it (no fixture there).

Diagnosed 2026-11-24: the test's premise went stale with #53 (`47684e36`, K `refantmode: flex` by default). With
refant m000, whose baselines to m001 and m003 the example strategy flags, K now solves every antenna through the
connected baselines (flagged fraction 0.0), and G then solves with an alternate reference (flagged 0.25,
`used_alternate_refant`), so calibrate writes solutions and exits 0. With `refantmode: strict` on the test's K term
the run fails as R-02 expects ("gaincal wrote no solutions for field 0"). Fixed on this branch by pinning K to
strict in the test's config; `tests/test_v030_fix.py` 7 passed on nash with the fixture. No code change.

## For the coordinator

- **What #3 still lacked is built:** CASA-table apply by row chunk and the chain solves (K, G, B, Gpol; by chunk of
  the stop replay and by field) go through `data.processes` (the local pool; the spool executor takes the same
  specs, but no spool run of the three new task kinds was made). F, the
  A step, Df's gauge, the KCROSS/Xf/Df chunk loops, averaged and streamed solves stay serial (1.2). No new key, no
  Rust change.
- **Identity:** bit-identical to main `e071bdab` on A1, poldx, a two-field chain and `w3.ms` in every arm.
  Criterion 6 failed as worded on two small-set P4 arms that had nothing to split (6, post hoc reading); your call
  whether that blocks the merge.
- **Image:** not built; DL0's ceiling (1.3) makes a per-channel split worth about 2 % of self-calibration.
- **Timing (6.1, nash, exclusive, one repeat):** N1 equals main within 0.8 %; calibrate S(8) 1.65 (681 to 417 s),
  apply S(8) 1.38 (94 to 68 s), efficiency 0.21 / 0.17; about 50 s / 40 s serial before the first task; flag
  unchanged to 14 % slower. Identity against main at every point.
- **Not run:** the full `python tools/check_all.py` (oracle and archive gates) on this branch.
- **Found in passing:** `test_v030_fix.py::test_fully_flagged_gaincal_ends_run_with_a_stage_failure` fails on main
  too, with the fixture: its premise went stale with #53's K flex default; the test now pins K to strict (6.1).
- **Kept:** `D:\rang\outputs\cta1b-20261123-03` and `-02` (hashes, logs), the `-01-void` root, the oracle worktrees
  on glacier and nash (each with a KEEP note), and on nash `~/rang-data/outputs/cta1b-nash-20261123` (8 GB
  `w3.ms` copy, the driver) and `~/Build/tmp/20261123-chunk-api-3` (build log, smoke configs), until the matrix
  ends and the branch merges.
