# W3b: chunking the chain terms (K, G, B, A, F and the polarisation terms)

Task W3b of [finish-plan.md](finish-plan.md). W3 ([w3-chunking.md](w3-chunking.md)) made `rang-core flag`, the
complex solve, `apply` and the models run within `data.memory_limit_gb`. C2e's chain terms (K, G, B, A, F;
[c2e-calibrate.md](c2e-calibrate.md)) and C6w's polarisation terms (Gpol, KCROSS, Xf, Df and P;
[c6w-polwire.md](c6w-polwire.md)) still read a whole field at once, and `preflight` refuses them above the limit
(`chain_memory_problems`). This task chunks them and replaces the refusal with chunked execution. Branch
`fp-w3b-chainchunks` from main `ba65792`. Interface and resource work: no novelty is claimed.

**Status: proposed (protocol).** Sections 0 to 4 are written before any comparison.

## 0. What the code does at `ba65792`

- `cal_gain.gaincal`, `cal_delay.gaincal` and `cal_bandpass.bandpass` read every row of their field (and
  `scan`) at once (`cal_gain._ms_columns`: DATA, FLAG, the weights or SIGMA, the model), pre-apply the earlier
  tables on the whole array (`_pre_apply`), and solve every solution interval in one kernel call. Per field and
  term about 60-100 bytes per visibility cell are held.
- `cal_fluxscale.bootstrap` (F) calls `cal_gain.gaincal` with `smodel_array(nrow, nchan)`, a whole-field copy of
  the point model; `cal_chain._solve_one` and `_solve_pol` build the same array for `model: unit`.
- `cal_pol.load` (KCROSS, Xf, Df) reads the field whole, rotates the model by P (`row_angles`: two float64 per
  row, plus a time index and the antenna columns) and pre-applies; `gpol` reads and rotates the whole model before
  `cal_gain.gaincal`.
- `cal_chain.flag_corrected` (the A step's Tricolour pass on CORRECTED_DATA) reads DATA and FLAG of every row
  of the A step's fields at once.
- `applycal.applycal(parang=True)` computes P's angles for every MS row before its chunk loop
  (`_field_angles`: two float64 per MS row plus FIELD_ID, TIME, ANTENNA1 and ANTENNA2 read whole); C6w
  noted they sit outside W3's budget.
- **Whole-field state** that a chunked solve must reproduce:
  1. **The global stop test.** The G and B kernel (`core/src/cal/diag.rs`, also Gpol and F's G) and the K
     kernels (`delay.rs`, `delay_offset.rs`) evolve each solution interval on its own but stop at the first
     iteration where the converged fraction summed over **every interval of the call** (the field) reaches
     `stop_fraction`, as W3 found for the complex solve.
  2. **CASA's reference antenna** (`cal_gain_apply_refant`, flex) runs over all intervals of a G, B or Gpol
     solve; `fill_gaps` (B) runs over all channels. Both work on the solutions, not on visibilities.
  3. **Df's gauge test** (`cal_pol.unpolarised_gauge`): the median of `M_YY / M_XX` over every unflagged cell
     of the field, and the largest deviation from it, decide `degenerate`, which the kernel takes as input
     (and an error when the gauge is not 1).
  4. **Solution times** (`cal_gain.solution_times`): per interval the TIME of its rows weighted by each row's
     unflagged parallel-hand weight summed over **all** channels after the pre-apply.
  5. Per interval and all channels: K's delay (the mid frequency of the window, the FFT estimate), G's and
     Gpol's single frequency bin, KCROSS's FFT. B, Xf and Df solve per interval **and channel**
     (`leakage.rs` per (interval, channel); Xf's `sumwt > 0` test is equivalent per channel subset because a
     channel with a solution has a positive weight in it).

## 1. Design (proposed)

### 1.1 Rule: chunk the cell arrays, keep rows and solutions whole

- A solve keeps per **row** of its field the row metadata (TIME, SCAN_NUMBER, FIELD_ID, ANTENNA1, ANTENNA2,
  UVW, FLAG_ROW, the interval index and the row's weight sum of 0.4) and per **solution** the solver's outputs.
  Only the cell arrays (data, model, weights or SIGMA, flags and their pre-applied copies) are chunked.
- A chunk is a set of **whole solution intervals**: consecutive intervals with all channels, or, for B, Xf and Df
  when one interval does not fit, consecutive channels of one interval (W3's `core_chunks.solve_chunks`). Rows
  keep the field's order inside a chunk, so every interval sees its rows in the order of the one-call solve.
- The cell columns are read with `core_chunks.read_rows`. Pre-applies always run on **whole rows (all
  channels)**, as the one-call solve does; a channel chunk is read in blocks of whole rows, each pre-applied and
  then cut to the chunk's channels, so the full band is held for one block only. Each row's weight sum for the
  solution times is taken from those whole rows.
- The post-solve steps run unchanged on the assembled per-solution arrays: `minsnr`, the reference antenna,
  `fill_gaps`, K's CASA referencing, Df's subtractive reference and SNR, the solution times, the table writers
  and the "no solution written" errors.
- Library functions (`cal_gain.gaincal`, `cal_delay.gaincal`, `cal_bandpass.bandpass`, `cal_pol.gpol`,
  `kcross`, `xf`, `df`, `cal_fluxscale.bootstrap`, `cal_chain.run`, `cal_chain.flag_corrected`) gain a keyword
  `budget` (default None: the field in one chunk, as now). A field that fits one chunk is solved by the code
  path of `ba65792` (one kernel call).
- `model: unit` and F's `smodel` become broadcast views (no copy); a chunk copies only its rows.

### 1.2 The global stop test, replayed

- As W3 did for the complex solve: **pass 1** solves each chunk with the stop test disabled and records, per
  iteration, the counts of converged and flagged gains; their sums over the chunks give the stop iteration `j`
  and the converged fraction of the one-call loop (`core_chunks.replay_stop`). **Pass 2** solves each chunk again
  with `max_iterations = j + 1` and the stop test disabled; intervals evolve independently, so its solutions are
  the one-call solutions of its intervals.
- The G/B and K kernels expose no per-iteration counts. New **counted** entry points (`diag::solve_counted`,
  `delay::solve_counted`, `delay_offset::solve_counted`; Python `cal_gain_trace`, `cal_delay_trace`,
  `cal_delay_offset_trace`) run the same loop and return the summed counts per iteration. They are observers:
  the existing `solve` functions call the same loop with the recording off, and no arithmetic changes. These
  are not the files the task protects (`core/src/solve.rs`, `jones.rs`, `correct.rs`, `core.solve_complex`).
- The counted call also returns the counts up to a solver error and the iteration of the error, so a chunked
  solve fails exactly where the one-call solve fails: when no stop is found before the earliest error
  iteration over all chunks, the error is raised; otherwise pass 2 stops before it. This removes W3's stated
  limit for these terms.
- `minblperant` (per interval, frequency bin and antenna) and CASA's SNR statistics (per gain) are per interval
  and are computed per chunk.

### 1.3 Df's gauge test, streamed

- When Df's field does not fit one chunk, the median of the real and imaginary parts of `M_YY / M_XX` over the
  unflagged cells is found exactly by two histogram passes over the chunks on order-preserving 32-bit keys of
  the float32 values (high 16 bits, then low 16 bits within the chosen bin), with NumPy's averaging of the two
  middle values for an even count; a third pass takes the largest deviation. Then the chunks are solved
  (Df is a closed form: no stop test). Cost: up to four reads of the field, for Df only, only when chunked.

### 1.4 The A step

- `flag_corrected` works per (field, data description, scan) group as now. A group that fits is one call (the
  `ba65792` call); otherwise blocks of consecutive baselines flagged on the group's full time grid, W3's flag
  stage (`core_chunks.baseline_blocks`, `flag_rows(time_grid=...)`). Its summary keeps its keys: the fractions
  from integer counts, `flag_sha256` by re-reading FLAG of the selected rows in row order after the write.
- The A step's `applycal` already writes in row chunks (W3 5.3).

### 1.5 P's angles

- `cal_pol.row_angles` splits into an **angle table** (the parallactic angle plus receptor angle per unique time
  and antenna, computed by astropy once, over the same rows as now) and a per-row lookup. `cal_pol.load`,
  `gpol` and `applycal` look the angles up per chunk; no per-row angle array of the field or MS is kept.
  `applycal`'s table per field is built from the field's unique times collected chunk by chunk.
- Measured before and after (tracemalloc) on `poldx` and on the whole-array set (section 5).

### 1.6 Memory budget and preflight

- `core_chunks.Budget.chain()` gives a chain solve the bytes `chunk_bytes − CHAIN_ROW_BYTES · n` for its cell
  arrays (`n` the rows of the field), at `CELL_BYTES["chain"]` bytes per cell; per-channel terms (B, Xf, Df)
  split it in halves, one for the chunk and one for a block of whole rows. `data.chunk_rows` caps every chunk,
  never below one solution interval (one channel of one interval for B, Xf, Df).
- **Amendment 1** (during implementation, before any comparison): `data.chunk_rows` caps every chunk but not
  the read blocks of whole rows (a read buffer, as W3 read a frequency chunk's rows whole); a block is bounded
  by the memory only. With blocks of 7 rows, arm T's B, Xf and Df (one channel per chunk) would read each field
  in hundreds of thousands of blocks.
- `CELL_BYTES["chain"]` (now an unfitted 96) and `CHAIN_ROW_BYTES` are fitted from a probe (peak RSS against
  chunk size) on the whole-array set before any comparison, with a margin, as W3's section 5.1.
- `preflight`'s `chain_memory_problems` is replaced: a term is refused, before anything is written, only when its
  smallest unit does not fit: one interval with all channels (K, G, Gpol, F, KCROSS), one interval and one
  channel plus one whole row (B, Xf, Df), one baseline of a flag group on its time grid (A). The message names
  the GiB needed.
- No new configuration key. Results do not depend on the limit or `chunk_rows` (the claim tested here), so
  neither enters the stage hash (W3's rule).

## 2. Data and cases (frozen)

Each arm runs on a fresh copy of the MS. Stages: `calibrate` then `apply` (O, C, P, H); `calibrate` only (W).

| Case | MS (read-only source) | Configuration |
| --- | --- | --- |
| O | O-CASA's slice `~/Github/rang/outputs/o-casa-20261030-01/work.ms` (192 rows x 2048 ch, 4 antennas) | C2e's I-slice: `model.source: column`, `refant: m000`, `minblperant: 3`, K0, G0, B0 (`fillgaps: 70`), A0, K1, G1, B1 (KGBAKGB); apply K1, G1, B1 |
| C | A1 small `/mnt/d/rang/outputs/fp-a1-20261106-simtruth/small/a1-small.ms` (12,480 rows x 64 ch, 16 antennas) | C2e's I-a1: `setjy`, `refant: m000`, `uvrange: ">150"`, `data.weights: uniform`, `data.scans` all but the last; primary K, G, B, A; secondary Gsec (`60s`), Asec, F; apply as I-a1 |
| P | C6w's prepared `poldx` `/mnt/d/rang/outputs/c6w-20261106-01/prepared.ms` | C6w's CONFIG (`examples/check_c6w.py`) without `data.chunk_rows: 700`: K, G, B; F; polcal Gpol (`60s`), KCROSS, Xf, Df (clip); apply with `parang: true` to all four fields |
| W | W3's whole-array set `/mnt/d/rang/outputs/w3/data/w3.ms` (40,320 rows x 4096 ch, 64 antennas, 8.0 GB) | `setjy`, `refant: m000`; primary on the fcal: K (`solint: int`), G (`int`, K), B (`inf`, `combine: scan`, K G) |
| H (held out) | C6w's prepared `polholdout` `/mnt/d/rang/outputs/c6w-20261106-02/prepared.ms` | as P |

W's K and G are `solint: int` because one `inf` interval (6 dumps x 2016 baselines x 4096 channels, 198 M cells)
does not fit 8 GiB; that refusal is criterion 4. Each source MS is hashed (casacure, every column) before its
first copy.

Arms:

- **U, unchunked (the oracle):** main `ba65792` in a detached checkout
  (`~/Worktrees/rang/w3b-oracle-ba65792`) with an extension built from that checkout, run with
  `data.memory_limit_gb: 28` and `data.chunk_rows` at least the MS's rows (so its apply and models are one chunk
  too). Not on W: the fcal's 24,192 rows x 4096 channels do not fit the host's 30 GiB unchunked, and main
  refuses them at any limit the host has.
- **D, default:** this branch, `data.memory_limit_gb` at its default (8).
- **T, tiny chunks:** this branch, `data.chunk_rows: 7` (O, C, P, H). Every solve chunk one interval (or
  one channel for B, Xf and Df where an interval has more than 7 rows), A blocks of single baselines.
- **M, a low limit:** this branch with `data.memory_limit_gb` set by a rule frozen here: `1.25 x` the largest
  GiB any one chain term of the case needs for its smallest unit (section 1.6, the number preflight reports),
  rounded up to 0.05 GiB. On O, K0 and G0 are one interval of every row of the field (`solint: inf`, one
  scan), so M cannot split them; B0, B1, K1 and G1 may split. On W this splits K and G into chunks of one dump
  and B into channel chunks.
  **Amendment 2** (before any comparison, after computing the limits): the GiB preflight reports include the
  process's fixed 0.63 GiB, so 1.25 times them left room for whole fields on O, C and P (0.85-1.00 GiB) and M
  would have split nothing there. The rule is now: the fixed bytes plus 1.25 times the largest smallest unit's
  part above them, rounded up to 0.001 GiB (`tools/oracles/w3b/compare.py m_limit`). At the code of this
  amendment that gives O 0.801, C 0.648, P and H 0.710, W 4.327 GiB (recomputed by the harness for each arm,
  so a refitted `CELL_BYTES` moves them).

## 3. Criteria (frozen before the first comparison)

Results must be bit-identical: chunking changes no arithmetic (section 1). A difference is a failure, reported as
measured.

1. **Identity** on O, C, P, against U for each of D, T and M:
   - every file of the calibrate run directory's tables (`<run>/calibrate/*`, the CASA tables K, G, B, F,
     `F.append`, Gpol, Kcross, Xf, Df) byte-identical;
   - every MS column (casacure SHA-256 per column, W3's `compare.py hashes`) equal after calibrate and after
     apply, and the flag versions equal cell by cell (keyed by stage);
   - `summary.json` of calibrate and apply equal after removing times, paths, flag-version names and the new
     chunking records (W3's cleaner).
2. **Memory** on W: peak RSS (`/usr/bin/time -v`) of calibrate in D and M at or below their
   `data.memory_limit_gb`.
3. **W consistency** (no U there): D and M table files byte-identical, every MS column and flag version equal
   after calibrate, summaries equal as in 1.
4. **Refusal** on W: `calibrate` with K `solint: inf` at the default limit exits 2 before anything is written,
   naming the GiB one interval needs; every MS column and the flag-version list unchanged, no run directory.
5. **Held-out** H (frozen here, run once after O, C, P, W have run): criterion 1 on H.
6. **Unit tests** (pytest, run by check-all): counted and uncounted kernels give identical solutions; chunked
   and one-call library results are equal for K (both kinds), G (ap, p), B (with fillgaps), F, Gpol, KCROSS,
   Xf and Df, with a stop before the maximum, a run to the maximum, a flagged interval, channel chunks, and Df
   both degenerate and not; the streamed median equals `np.median`; `flag_corrected` in blocks equals one block;
   the angle table lookup equals `row_angles`; the preflight refusal of an interval above the limit.

Reported, not gated: U's and D's peaks on O, C, P; the chunk counts per term; the P angle memory before and
after; stage wall times (one run each, shared host; no speed claim).

## 4. What is not checked (stated before the run)

- A whole-array MS of hours at 4096 channels (disk), and `apply` on W (W3 measured apply).
- An A step, F, or polarisation terms on W (only K, G, B there); they are checked for identity on O, C, P, H.
- Non-default solver options for these terms (they have none in the commands).
- Windows and macOS. Speed.

## 5. Runs

### 5.1 Probe (not a comparison)

`/mnt/d/rang/outputs/w3b-20261106-02-probe`: `tools/oracles/w3b/run.sh` case W, arm M (4.327 GiB), calibrate
only, code `295e65c`, heavy lock; no U arm exists on W, so nothing was compared. Exit 0, 55 min 24 s.

| Term | Chunks | Largest chunk | Iterations, converged fraction |
| --- | --- | --- | --- |
| K (`int`) | 12 (one dump each) | 2016 rows x 4096 x 4 = 33.0 M cells | 21, 0.9972 |
| G (`int`) | 12 | 33.0 M cells | 16, 1.0 |
| B (`combine: scan`) | 20 channel chunks of about 213 channels, blocks of about 1,260 whole rows | about 20.6 M cells plus a block of about as many | 14, 0.9909 |

Peak RSS 1.66 GiB against the limit of 4.33 GiB. Over the largest chunk that is about 51 bytes per cell (K and G)
or 43 per cell of chunk plus block (B), against `CELL_BYTES["chain"]` = 96: the factor keeps its margin of about
two and is **not changed**, so `CHAIN_ROW_BYTES` (128) stays too. The probe also shows the replayed stop test
stopping early on whole-array data (K at 21, G at 16, B at 14 of 50 iterations).

### 5.2 P's angles (measured, `tools/oracles/w3b/angles_memory.py`)

`/mnt/d/rang/outputs/w3b-20261106-01-angles`: tracemalloc peak of `applycal`'s angle step, read only, with the
angles of every row checked equal between the two.

| MS | Rows | `ba65792` (`_field_angles`, per-row arrays) | W3b (angle tables) | Table bytes | Angles equal |
| --- | ---: | ---: | ---: | ---: | --- |
| poldx | 12,480 | 1.16 MB | 0.55 MB | 14 kB | yes |
| A1 full | 2,842,560 | 255 MB (90 bytes a row) | 3.8 MB | 0.73 MB | yes |

The per-row arrays (two float64 per MS row, plus FIELD_ID, TIME and the antennas read whole) are gone; what is
held is a table per field of unique times x antennas (8 bytes each) and the chunk being read, both inside the
budget (row metadata and chunk). `cal_pol.load` and `gpol` use the same tables for their field.

The library check on poldx (read only, `tools/oracles/w3b/library_check.py`, log
`library-dev-check-poldx.log` in the same directory) found K, G (ap, p), B, Gpol, KCROSS, Xf and Df chunked (a
small budget, and a 7-row cap) equal to one call, table cell for table cell.

### 5.3 Frozen run -04

`W3B_ORACLE=~/Worktrees/rang/w3b-oracle-ba65792 bash tools/oracles/w3b/all.sh
/mnt/d/rang/outputs/w3b-20261106-04`, at `b07bf24` (code `295e65c` plus note and harness lint). The U arm ran main
`ba65792`'s Python with an extension built from that checkout. After the first arm (O-U) the run was restarted
at `1715dea`, a harness-only change (`all.sh` keeps finished arms and runs the O, C and P arms without the heavy
lock, which other tasks held for hours); no comparison had been made, and `run.sh`, `compare.py` and the code are
unchanged (recorded in `w3b-20261106-04.code/head.txt`). A run started as -03 was stopped before its first arm
and removed. Verdict `run-04/verdict.json`, archive [results/w3b-chainchunks.json](results/w3b-chainchunks.json).

| # | Criterion | Measured | Verdict |
| --- | --- | --- | --- |
| 1 | Identity on O, C, P: D, T, M against U | every calibrate run-directory file (K, G, B, F, `F.append`, Gsec, Gpol, Kcross, Xf, Df tables) byte-identical; every MS column equal after calibrate and after apply; flag versions equal; calibrate and apply summaries equal (cleaned) | **pass** (12 of 12 comparisons) |
| 2 | Memory on W | calibrate peak 3.35 GiB at the 8 GiB default (D), 1.66 GiB at 4.327 GiB (M) | **pass** |
| 3 | W consistency, M against D | tables byte-identical, columns, flag versions and summaries equal | **pass** |
| 4 | Refusal on W (K `solint: inf`, 8 GiB) | exit 2: "one solution interval holds 198180864 visibility cells of 24192 rows and needs 18.353 GiB, above data.memory_limit_gb 8"; every column hash unchanged, no flag version, no run directory | **pass** |
| 6 | Unit tests | `tests/test_w3b_chainchunks.py` (17) and the changed W3 test pass in check-all | **pass** |

Chunks (from each summary's `chunking.solves`; one chunk everywhere at D except W):

- O: T: B0 and B1 28 channel chunks, K1 and G1 32 (one integration each); M: B0, B1 2 channel chunks; K0 and G0
  are one interval and one chunk in every arm, as section 2 said.
- C: T: B 64 channel chunks, Gsec and F 10; M: B 2, Gsec and F 4 (K and G: one scan, one chunk). The A steps under
  T flagged in blocks of single baselines.
- P: T: K, G 2; B, Xf, Df 256 channel chunks (Df's gauge test streamed); F 10; Gpol, KCROSS 4; M: B, Df 4, Xf 5,
  F, Gpol, KCROSS 4, K, G 2.
- W: D: K and G 6 chunks (two dumps), B 10 channel chunks; M: K and G 12, B 20. Both stop where the probe stopped
  (K 21, G 16, B 14 iterations), so the replay reproduced early stops on whole-array data, identically at two
  chunkings.

Peaks (GiB, `/usr/bin/time -v`), reported: O calibrate U / D / T / M 0.21 / 0.20 / 0.15 / 0.19; C 0.14 / 0.14 /
0.06 / 0.08; P 0.31 / 0.30 / 0.25 / 0.21, apply 0.54 / 0.54 / 0.16 / 0.24. On the small sets M's limit (0.65-0.80
GiB) is below what a Python process with the reader needs at all; the arm forces chunks, it does not test memory
(W does). Walls: W calibrate D 31 min 32 s, M 51 min 44 s; P-T calibrate 28 min 42 s, C-T 16 min 16 s (one
channel per chunk re-reads the field; 7-row WriteBack flushes); every other arm under 1.1 min per stage.

### 5.4 Held-out run -05 (criterion 5)

`/mnt/d/rang/outputs/w3b-20261106-05`, case H (C6w's prepared `polholdout`, frozen in section 2, untouched before
this run), arms U, D, T, M (M 0.710 GiB), same code as -04, started after W's D and M arms had finished.
Verdict `run-05/verdict.json` (in the archive as `held_out`): D, T and M against U **pass**: every table file
byte-identical, every column and flag version equal after calibrate and after apply, summaries equal. Peaks:
calibrate 0.31 / 0.30 / 0.25 / 0.21 GiB, apply 0.54 / 0.54 / 0.16 / 0.24 GiB. Walls: H-T calibrate 28 min 18 s,
apply 9 min 50 s; the others 0.8-1.3 min per stage; 45 min in all.

**Every frozen criterion (1 to 6) passes.**

## 6. Limits and what was not checked

- As section 4: no whole-array MS of hours, no apply, A, F or polarisation term on W, no Windows or macOS, no
  speed.
- One solution interval with all its channels is the smallest chunk of K, G, F, Gpol and KCROSS (one channel of
  one interval for B, Xf, Df). K or G with `solint: inf` on a whole-array scan (198 M cells) needs about 18 GiB
  and is refused below that; splitting an interval over channels would change the solvers.
- A chunk in channels re-reads the whole interval's rows for every chunk and both passes (Df: four passes, the
  gauge test first), because the pre-apply runs on whole rows and the reader has no channel-sliced read. On W
  calibrate at 4.3 GiB took 55 min against W3's complex solve's 22 min at 2 GiB (shared host, not a timing
  measurement); arm T on poldx takes most of its time in B, Xf and Df at one channel per chunk.
- The counted kernels record counts up to a solver error, so a chunked solve fails exactly where the one-call
  solve fails (unit-tested on a synthetic replay; no solver error occurred in a run).
- `CELL_BYTES["chain"]` was fitted on W only (section 5.1); its margin is about two there.
- E0 (branch `fp-e0-refant`) adds `refant: auto` and `extendflags` with hooks in `core_pipeline` and
  `cal_chain`; the merge is expected to be small (`stage_calibrate_chain`'s call of `cal_chain.run` gains
  `budget=`; `cal_chain.run` gains a `budget` keyword).

## 7. Owner decisions

- **Blocks are not capped by `data.chunk_rows`** (amendment 1): `chunk_rows` caps solve chunks only; a read block
  of whole rows for a channel chunk is bounded by the memory. Provisional.
- **The counted kernels** (`diag::solve_counted`, `delay::solve_counted`, `delay_offset::solve_counted` and their
  `rang._core.*_trace` entry points) are new public Rust and extension functions that only observe; owner may
  prefer them private. Provisional: public, as `core.solve_complex(trace=...)` is.
- **The A step's summary** gains a `chunking` record when it runs under a budget (`rang-core calibrate` always),
  and its `flag_sha256` is now taken from FLAG re-read after the write (the same bytes). Provisional.
- **The heavy lock** was taken per arm for W only; O, C and P arms (under 0.6 GiB) ran without it after the first
  arm waited about two hours behind other tasks (no timing is claimed).

## For the coordinator

- **research/README.md**, after the W3 line (this also makes `test_every_note_is_in_the_research_index` pass):
  `- [W3b, chunking the chain terms](w3b-chainchunks.md): K, G, B, A, F and the polarisation terms run within data.memory_limit_gb in chunks of whole solution intervals (B, Xf, Df also in channels), bit-identical to the unchunked commands on O-CASA's slice, A1 small, poldx and held-out polholdout; the G, B and K stop test replayed from counted kernels; P's angles from per-time tables.`
- **research/STATE.md**, log, newest first:
  `W3b, 2026-11-07 (implemented and measured; [w3b-chainchunks.md](w3b-chainchunks.md)). rang-core calibrate runs C2e's K, G, B, A, F and C6w's Gpol, KCROSS, Xf, Df within data.memory_limit_gb: each solve reads its field in chunks of whole solution intervals (B, Xf and Df also in channels of one interval, pre-applied on whole rows), the stop test of the G/B and K kernels replayed over the chunks from new counted kernels (observers; no arithmetic changed), Df's gauge test found exactly over the chunks, the A step flagging in blocks of baselines, E0's extend step in blocks of baselines of a 60 s chunk. preflight now refuses only one solution interval (B, Xf, Df: one channel of one) that does not fit. Every frozen criterion passes: D, T and M bit-identical to main ba65792 unchunked on O-CASA's slice (KGBAKGB), A1 small (C2e chain) and poldx (polcal) and on the held-out polholdout (tables, every column, flag versions, summaries); on the whole-array set (K, G, B) calibrate peaks at 3.35 GiB under 8 GiB and 1.66 GiB under 4.33 GiB, the two byte-identical, and K solint inf (18.4 GiB) is refused before anything is written. P's angle arrays are gone: applycal's angle step on A1 full went from 255 MB to 3.8 MB. No novelty claim, no speed claim.`
  In "Current status", add W3b to the Done list.
- **research/finish-plan.md**, row W3b: `**Done 2026-11-07** ([w3b-chainchunks.md](w3b-chainchunks.md)): bit-identical chunked and unchunked on the slice, A1, poldx, held-out polholdout; whole-array K, G, B at 3.35 / 1.66 GiB.` before the task text. Section 7: add W3b's decisions (section 7 here).
- **Shared files changed:** Rust `core/src/cal/diag.rs`, `delay.rs`, `delay_offset.rs` (a `Trace` and `solve_counted`;
  `solve` unchanged in arithmetic), `core/py/src/cal_gain.rs`, `cal_delay.rs`, `cal_delay_offset.rs` (`*_trace`),
  `core/py/src/lib.rs` (registration lines at the end); Python `cal_gain` (`solve` split into `_kernel` and
  `_finish`, `_Field`, `row_weights`, `times_from_row_weights`), `cal_delay`, `cal_bandpass`, `cal_pol`
  (`angle_table`, `table_angles`, `_PolField`, `df_solve` split), `cal_fluxscale` (`smodel_view`), `cal_chain`
  (`budget`, `flag_corrected(max_rows=)`), `applycal` (`_field_angles` returns tables), `core_chunks`
  (`ChainBudget`, `CHAIN_ROW_BYTES`), `core_pipeline` (`chain_chunk_plans`, new `chain_memory_problems`, the
  calibrate summary's `chunking`), `flag_extend` (`_batches`, after the merge); new `rang.cal_chunks`;
  `tests/test_w3_chunking.py` (the chain-refusal test now tests the new rule). **Merged with main `0f5ef06`**
  (E0, G3; section 5.5).
- **On disk:** `/mnt/d/rang/outputs/w3b-20261106-02-probe` (9 MB), `-04` (30 MB) and `-05` (5 MB) with `.code`
  snapshots and logs, `-01-angles` (angle measurements and the library-check log); the MS copies were removed after
  the verdicts. `~/Worktrees/rang/w3b-oracle-ba65792` and `w3b-oracle-0f5ef06` are detached oracle checkouts
  with their own extensions: remove with `git -C ~/Github/rang worktree remove --force <path>` once this is merged.
  W3's `w3.ms` (8.0 GB) is unchanged.
