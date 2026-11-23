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

Code: branch `chunk-api-3`, `5375c029` (the code), harness at `6d2e94e3`. Oracle U: main `e071bdab` from the
detached worktree `C:\Users\gijsm\Worktrees\rang\cta1b-oracle-e071bdab` with this branch's `_core.pyd` (SHA-256
`6023d006…`; `git diff e071bdab -- core/ src/` empty). Host glacier, shared under the heavy lock at normal priority.
Run root `D:\rang\outputs\cta1b-20261123-02` (hashes, logs and summaries kept; MS copies deleted); verdict copied to
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
- **Criterion 7.** `tests/test_chunk_tasks_1b.py`, 6 tests, pass on Windows; with the related suites (W3, W3b,
  c4b, c2e, c6w, spool, calwt, Xf calwt, fluxscale, reweight, c5 selfcal) 110 passed, 4 skipped. CI's `tests` on
  Linux and Windows: see the pull request or the hand-back.
- **Walls** (s, calibrate / apply; shared host, **not timing results**): W U 421.4 / 28.2, P1 526.7 / 28.5,
  P4 586.2 / 22.7. P4 ran one rayon thread per worker against U's four. Every `chain-chunk` task re-runs its
  recipe up to the replayed solve (the field's metadata, model and solution bins, the earlier tables read from
  disk) before its chunk, which costs per task what the parent pays once per solve; whether that or host load
  explains P4 > U is for section 5 to measure.

**Void and refused runs, kept.**
- `D:\rang\outputs\cta1b-20261123-01-void`: C, P and M arms failed while writing their configuration (the harness's
  config hook called itself), before any stage ran; W-U was stopped mid-calibrate when the oracle worktree was
  removed by another session's cleanup pass. No verdict drawn; `VOID.txt` in it.
- `W-*.void-amendment2` in the run root: W's first arms, refused at apply in U and P1 (no `apply.targets`) and at
  calibrate in P4 (2 GiB per process), which led to amendment 2.

### 6.1 Timing (section 5): not obtained

nash's lock had 32-40 of 44 shared slots booked through the task, so no idle window came. Stage 1's matrix stays
closed at 2 of 15 points. Prepared on nash for the coordinator: the branch worktree `~/Worktrees/rang/chunk-api-3`
(venv and extension built by its quick check), the oracle `~/Worktrees/rang/cta1b-oracle-e071bdab`, and
`tools/oracles/chunk_tasks/timing_1b.py matrix RUN`, which queues each point only when the lock is idle.
The driver was started on nash on 2026-11-23 at 08:55 SAST without a session (pid 307375, nice 19, branch commit
`5c72f877`, whose `python/`, `core/` and `src/` equal `5375c029`'s), run root
`~/rang-data/outputs/cta1b-nash-20261123/` with its own copy of `w3.ms` (all 65 files equal to D:'s by SHA-256,
`inputs/hashcheck.txt`), log `driver.log`, one line per point in `status.txt`. When it ends:
`timing_1b.py report RUN`, then the table of section 5 here.

**Found in passing (not this task's code):** `tests/test_v030_fix.py::test_fully_flagged_gaincal_ends_run_with_a_stage_failure`
fails on nash (Linux, with `RANG_FIXTURE` set) on this branch **and on main `e071bdab`** with the same extension:
calibrate exits 0 where the test expects a stage failure. CI does not see it (no fixture there).

## For the coordinator

- **What #3 still lacked is built:** CASA-table apply by row chunk and the chain solves (K, G, B, Gpol; by chunk of
  the stop replay and by field) go through `data.processes` / `data.executor` (local pool and spool alike). F, the
  A step, Df's gauge, the KCROSS/Xf/Df chunk loops, averaged and streamed solves stay serial (1.2). No new key, no
  Rust change.
- **Identity:** bit-identical to main `e071bdab` on A1, poldx, a two-field chain and `w3.ms` in every arm.
  Criterion 6 failed as worded on two small-set P4 arms that had nothing to split (6, post hoc reading); your call
  whether that blocks the merge.
- **Image:** not built; DL0's ceiling (1.3) makes a per-channel split worth about 2 % of self-calibration.
- **Timing:** not obtained (6.1); stage 1's matrix closed at 2/15. Overhead to watch: each `chain-chunk` task
  rebuilds its field before its chunk.
- **Not run:** the full `python tools/check_all.py` (oracle and archive gates) on this branch.
- **Kept:** `D:\rang\outputs\cta1b-20261123-02` (hashes, logs), the `-01-void` root, the oracle worktrees on glacier
  and nash (each with a KEEP note) until merge.
