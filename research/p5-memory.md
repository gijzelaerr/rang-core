# Big plan task P5: memory, one copy of the cube

Protocol frozen 2026-10-30 on branch `p5-memory` (from origin/main
`07dfb86`) before any campaign code was changed. Task P5 of
[big-plan.md](big-plan.md) and section 3 "P5 Memory" of
[simplification-review.md](simplification-review.md).

Status: **implemented and measured** (sections 4–5). Every gated identity
criterion passes: K's precondition masks and the four-station replay are
identical (images bit-identical), and the whole-array run reproduces the
same-host unmodified run on every non-timing field (3 of 12 dirty images
within 3.1e-11 of the peak, the rest bit-identical) and L1's archive on
every non-image field. Peak memory at array scale **12,997 → 10,406 MiB
(159 → 128 B per cell, −20 %)**; the pre-registered target of ≤ 115 B per
cell is **missed** (the gridder and the Tricolour port, both other tasks'
Rust, now set the peak). Per-cell slope on subsets 606 → 101 B per cell.

## Question

The whole-array LUNO campaign ([luno-array-campaign.md](luno-array-campaign.md), L1)
peaked at 12.46 GB. Where does each stage's memory go, and how far can it
drop with one copy of the visibility cube and no per-cell temporaries in
Python, while every result that the acceptance calls identical stays
identical?

## 0. Unit, floor and target

- **Cell.** As in S1 section 2.8: one (row, channel) sample with its four
  correlations. LUNO row chunk 0 on all stations is 41,786 rows × 2,048
  channels = **85,577,728 cells** (L1 counts 342 M cell-correlations; this
  note never uses that unit). K's four-station slice is 393,216 cells.
- **Floor.** The inputs held once: DATA and MODEL_DATA complex64 (32 + 32 B),
  WEIGHT_SPECTRUM float32 (16 B), FLAG bool (4 B) = **84 B per cell, 7.19 GB**
  at array scale. The frozen method needs all four for the whole chunk at
  once (one global solve, a global 0.99 stop fraction; L1 method 2), so a
  peak of "a few GB" for this chunk is not reachable without changing frozen
  inputs or the method. This is stated here so the target is not misread.
- **Where L1 stands.** 12.46 GB / 85.58 M cells = **146 B per cell**, already
  at the review's estimate (0.12–0.15 kB) because L1 had reimplemented the
  worst offenders in row blocks. S1's 0.87 kB per cell is K's driver, which
  L1 no longer runs at scale.
- **Target, pre-registered.** At array scale, peak RSS **≤ 115 B per cell
  (≤ 9.9 GB)**, with an expected **100–112 B per cell (8.6–9.6 GB)**, and no
  single stage more than 30 B per cell above the retained state. Accounting
  behind the expectation (array scale, after the changes of section 3):

  | Item | B per cell |
  | --- | ---: |
  | inputs held once | 84 |
  | split masks kept (eligible, train, validation, test, bool) | 4 |
  | process, libraries, gains, row columns | about 1 |
  | **retained** | **about 89** |
  | split (seed-7 draws for eligible cells, groups, sort order) | +12 to +16 |
  | solve (one reused uint8 flag buffer, solver internals) | +4 retained during solves, +8 transient |
  | features (fused-pass scores per baseline group, then sparse) | +8 to +12 |
  | Tricolour port (window, stage planes, output flags; no copies) | +20 to +26 |
  | imaging (sample, reader weight, imaging weights, one channel group) | +18 to +25 |

  The largest transient (Tricolour or imaging) sets the peak: 89 + 26 ≈ 115
  in the worst case, about 105–112 expected. The stage planes and the
  Tricolour window live in P3's Rust and are not changed here.

## 1. Baseline, measured before any change (code `07dfb86`)

### 1.1 Method

- `examples/bench_p5_memory.py` wraps the stage functions of
  `core_campaign_array` and the core calls they make (decode, split, solve,
  fused pass, Tricolour, TV loop, gain correction, imaging weights, gridder)
  and records per call the wall time, the RSS at entry and exit, and the
  call's **own high-water mark**: `VmHWM` is reset through
  `/proc/self/clear_refs` (value 5) at each entry and read at exit; a
  parent keeps the largest peak of its children. Rust allocations are
  included. Bytes per cell are `peak × 2²⁰ / cells` (peak) and
  `(peak − RSS at entry) × 2²⁰ / cells` (transient above entry).
- Caveat: resetting `VmHWM` also resets what `getrusage` and
  `/usr/bin/time -v` report, so inside the bench the campaign's own
  `max_rss_mb` fields and the `time -v` peak are *not* the process peak;
  the bench's composed `total` peak is. Headline before/after peaks are
  taken from **un-instrumented** runs under `/usr/bin/time -v` with the core
  prebuilt (so no `cargo build` child is counted).
- `RAYON_NUM_THREADS=8` throughout; host shared with sibling sessions
  (load 22–31), which affects walls, not memory.

### 1.2 Four-station and subset probes (instrumented)

Runs `outputs/p5-memory-20261030-01/{k4,s8,s12}-before` (the L1 driver on
stations 0–3, 0–7, 0–11 with K's 512² image and one gridder group, so the
image's fixed cost is the same in all three):

| stage | 393,216 cells: +transient / peak B/cell | 1,835,008 cells | 4,325,376 cells |
| --- | ---: | ---: | ---: |
| `decode_inputs` | +109 / 242 | +88 / 115 | +87 / 98 |
| `build_state` (eligibility and split) | +27 / 269 | +32 / 147 | +31 / 129 |
| `solve_arm` (all) | +171 / 531 | +176 / 353 | +177 / 303 |
| `core.solve_complex` | +13 / 393 | +6 / 210 | +8 / 165 |
| `core.fused_pass` | +65 / 1071 | +65 / 322 | +62 / 273 |
| `residual_amplitude` (fused residuals in row blocks) | +168 / 531 | +176 / 353 | +163 / 303 |
| `baseline_scores` | +14 / 364 | +0 / 193 | +8 / 156 |
| `core_flag.flag_rows` | +75 / 391 | +22 / 207 | +22 / 173 |
| `tv_loop` | +12 / 393 | +13 / 210 | +25 / 176 |
| `corrected_stokes` (`apply_gains` + reader in 2048-row blocks) | +483 / 1539 | +518 / 840 | +507 / 705 |
| `core_weights.imaging_weights` | +8 / 1038 | +5 / 326 | +8 / 207 |
| `core_grid.invert` | +598 / 1071 | +150 / 349 | +60 / 219 |
| **whole run (peak)** | **577 MB, 1,539** | **1,470 MB, 840** | **2,909 MB, 705** |

- Peak per cell between the two larger probes: (2,909 − 1,470) MB /
  2.49 M cells = **606 B per cell**, set in every probe by
  `corrected_stokes`: below 2,048 rows the whole slice is one block, so
  `apply_gains`' complex128 temporaries (about 480–520 B per cell) are
  whole-slice. At array scale the blocks cap this at about 2 GB.
- The residual amplitude (+163–176 B per cell) is likewise one block below
  2,048 rows; the solve itself adds only 6–13 B per cell.
- `tracemalloc` was not used for these runs (the HWM reset covers Rust as
  well); it is available in the bench (`--tracemalloc`) for attribution.

### 1.3 Array scale, from L1's receipts and a same-host rerun

L1's frozen run `-01` (code before P1, P2, P3) recorded the cumulative
high-water mark after each stage (`result.json` `stages`):

| after stage | HWM | B per cell | step |
| --- | ---: | ---: | --- |
| decode | 7.25 GB | 85 | inputs |
| split | 9.87 GB | 115 | +31 B per cell (`split_holdout` on int64 groups, eligibility temporaries) |
| solve `original` + features | 10.08 GB | 118 | amplitude, outliers, guidance (float64, 8 B each) kept |
| Tricolour first-pass port | 11.42 GB | 133 | stage planes + their `astype(bool)` copy, output flags + copy |
| solve `tricolour-firstpass` + features | 11.47 GB | 134 | two feature sets alive |
| Tricolour mild port, then every later stage | **12.46 GB** | **146** | |

Because P1–P3 have since changed the solver, the Tricolour port and the
gridder (per-thread scratch and grids), the **before reference on this host
is a rerun of the unmodified driver** (`07dfb86`) on all stations:
`outputs/p5-memory-20261030-01/array-before`, un-instrumented, under
`/usr/bin/time -v`, `RAYON_NUM_THREADS=8`. Its numbers are entered in
section 4 when it finishes; it is also the identity reference for the
after-run (section 2, criterion 4).

*Added after the measurement (labelled):* that first rerun was killed by
the OOM killer; the reference is its repeat `array-before-b` (section
5.2). Also, the "GB" figures in the table above are the runs' `max_rss_mb`
values, which are MiB (`ru_maxrss` / 1024), so 12.46 "GB" is 152.7 B per
cell, not 146; section 5.2 uses MiB throughout. The target of section 0
(≤ 115 B per cell) was set in bytes and is judged in bytes.

### 1.4 The unmodified precondition on this host (pre-existing failure)

`outputs/p5-memory-20261030-01/precondition-before` (code `07dfb86`, 39 s,
614 MB): part 1 (K's precondition) **passes**, part 3 (groups, 7.5e-5 /
7.6e-5 against 1e-4) **passes**, part 2 (replay of K run `-01`) **fails
only on image keys**: every arm's `dirty_sha256` and `psf_sha256`, some
arms' `residual_rms` and `peak_jy_per_beam` (exact float equality), and the
first hypothesis' residual-RMS ratio. Additions, gains, losses, TV, flag
fractions, all 20 candidates and the Tricolour counts are identical. This
is P2's documented change of image bits (pixels within 2e-15, archived
hashes superseded) and predates P5. P5's replay check therefore compares
images by pixels and metrics, not hashes (criterion 2).

### 1.5 Pre-check of the fused-pass scores (before the freeze)

A scratch check (`outputs/p5-memory-20261030-01/scores-check-*.json`) compares
the fused pass's Rust scores (`scores=True`) against L1's NumPy path on the
`original` base. They are **not bit-identical**: the Rust amplitude sums
`(re√w)² + (im√w)²`, NumPy squares `hypot`; max |Δz| 1.0e-14 (four
stations, 36,172 of 393,216 cells differ) and 1.2e-14 (twelve stations,
418,073 of 4,325,376). No cell lies within 1e-12 of `outliers ≥ 2` or of
any of the nine `score > τ` edges, the non-zero support is identical, and
all nine policy masks are identical on both subsets. At array scale this
is checked through the candidates' mask hashes (criterion 4).

## 2. Acceptance (frozen)

Gated:

1. **K precondition masks identical.** `core_campaign.precondition`
   (unedited path through `prototype_section6`) passes all its checks;
   the nine section-6 policy-mask hashes and counts, χ², survey, converged
   and flagged-gain fractions equal `results/core-k-luno-campaign.json`.
2. **K replay within task A's tolerances.** The array driver on K's four
   stations with K's image settings and one group, against K run `-01`
   **and** against the unmodified replay `precondition-before/replay`:
   - identical: shape, split counts, every arm's `additions_sha256`,
     `gains_sha256`, losses, TV, fixed-support TV, final flag fraction;
     every candidate's `mask_sha256`, `mask_count`, objective and
     acceptance; Tricolour newly flagged and additions counts; the three
     MSE calls;
   - images by pixels ([core-a-imaging-sensitivity.md](core-a-imaging-sensitivity.md)):
     dirty L∞ ≤ 8.8e-6 of the job's peak, PSF L∞ ≤ 2.8e-6, imaging-weight
     sums within 1e-9 relative, gridded counts and imaged cells equal;
     peak, residual RMS and off-source metrics within 1e-6 relative;
     residual-RMS calls equal;
   - the gridder-group check (part 3) still within 1e-4.
3. **Decode byte-identical.** `core_fetch.decode_slice` on
   `outputs/core-k-20261030-01/fetch` gives arrays byte-identical to the
   unmodified function, and `core_campaign_array.decode_inputs` gives
   arrays byte-identical to the unmodified function on stations 0–3 and on
   all stations (hashes recorded).
4. **Array scale.** If an after-run on all stations fits (it is planned;
   about 40–60 min at 8 threads), every non-timing field of its
   `result.json` and `candidates.json` equals the before reference
   (`array-before`) — split counts, every arm's additions, gains and
   losses, TV, flag fractions, Tricolour summaries and checks, all
   candidate masks and objectives, amendment-1 calls, hypotheses — except
   the image block, which must meet criterion 2's pixel and metric
   tolerances (dirty and PSF compared as FITS). Every non-timing,
   non-image field is also compared with L1's archive
   (`results/luno-array-campaign.json`) and differences are listed (P1–P3
   are expected to leave them identical; image fields differ through P2).
   If the after-run does not fit, the documented subset is stations 0–11
   (L1's smoke shape) against an unmodified rerun on the same subset, plus
   the four-station exact match.
5. **Units.** The correction kernel reproduces `core_campaign.apply_gains`
   + `core_grid.stokes_i_reader` (with the final-flag rule) to within
   complex64 rounding: reader weights bit-identical, samples within
   2 ulp of float32 relative to the cell's magnitude; the lean split, the
   sparse policy masks and the per-baseline-group scores are bit-identical
   to `flagging.split_holdout`, `flagging.policy_mask` and the fused pass
   on one call (pytest, synthetic and K data).
6. **Memory.** Peak RSS per cell before/after at four stations, 0–11 and
   array scale (if run), per stage from the bench. The target of section
   0 is reported as met or missed; a miss is a result, not a failure of
   the gates above.
7. Rust: clippy `-D warnings` and `rustfmt --check` on the new files (run
   on the standalone crate, see section 3, because `check-all` does not
   compile files outside `core/src/lib.rs`); `bash tools/check-all.sh`
   passes once before the final commit.

Fallback, pre-registered: if any candidate mask hash differs at array
scale because of the score difference of 1.5, the features fall back to
L1's NumPy amplitude path (kept as `scores="numpy"`), the run is repeated
and the difference is recorded.

## 3. Changes (planned)

1. **Decode into the caller's buffer.** Tile columns are decoded straight
   into the final `(row, channel, corr)` arrays: a strided Rust decode
   (`rang_core_blosc_decode_span_rows_strided`, `core/src/ffi_correct.rs`)
   writes each selected row of a tile at its channel offset; local tiles
   are `mmap`ed so the compressed span is not copied. `decode_slice` drops
   `tobytes` → `frombuffer` → `concatenate`.
2. **Split.** Eligibility in row blocks; a lean `split_holdout` that draws
   the same seed-7 stream in row blocks, keeps the draws of eligible cells
   only and reserves each group's two training cells with one lexsort
   instead of a Python loop over 1.4 M groups; bit-identical by
   construction and by test.
3. **Solve flags** written into one reused uint8 buffer (no bool cube, no
   bool → uint8 copy in `core.solve_complex`).
4. **Features.** Scores from the fused pass (`scores=True`) over groups of
   whole baselines (a baseline's scores depend only on its own cells, in
   order); kept sparse: only training cells with `outliers ≥ 2` can ever be
   proposed, so the base keeps their indices, outliers and guidance, plus
   the guidance median over all training cells. The policy mask is
   evaluated on that set (same elementwise arithmetic, same stable top-k
   cut as `flagging.policy_mask`). No float64 per-cell feature arrays are
   kept; additions are stored as sorted indices and expanded when needed.
5. **Tricolour wrapper.** `core_flag.flag_rows` returns the output flags
   and stage planes as `bool` views of the uint8 buffers after checking
   that every byte is 0 or 1 (no `astype(bool)` copies); the intensity
   window only when requested. The checks run without full-cube
   temporaries.
6. **Gain correction and Stokes I in Rust** (`core/src/correct.rs`,
   `rang_core_correct_stokes_i`): inverses of the small gain array from
   `np.linalg.inv` (identical to `apply_gains`), then per cell the two 2×2
   products, the cast to complex64, the reader's sample and weight in
   NumPy's float32 order, and the final-flag rule (original | FLAG_ROW |
   addition | invalid gain) folded in, written into sample and weight
   buffers reused across arms. No `final` cube.
7. **Build until merged.** `core/src/lib.rs` is a coordinator file, so on
   the branch the two new files are compiled as a standalone `cdylib`
   (`rang_p5_core`: a generated root with `#[path]` modules for
   `correct.rs`, `ffi_correct.rs` and `blosc.rs`, rayon from the offline
   cache) into `core/target/p5-standalone`, loaded through ctypes by
   `core_fetch`. After the coordinator adds `pub mod correct; pub mod
   ffi_correct;`, the same symbols come from `librang_core` (or the
   extension) and the standalone build is skipped.

## 4. What was built (code `ee1b02d`)

All seven items of section 3, as planned; nothing in the frozen method
changed. File by file:

- `core/src/correct.rs` (new, pure kernels, 5 unit tests):
  `correct_stokes_i` (rayon over rows; inverse gains passed in; NumPy's
  2×2 matmul accumulation order `(0 + a₀b₀) + a₁b₁`, complex64 rounding,
  the reader's float32 `(XX + YY) · 0.5`, `4 min(w_XX, w_YY)` with NumPy's
  NaN rule, the final-flag rule folded in) and `decode_rows_strided` (blocks
  decoded in parallel, each row written at `offset + i · stride`; every
  byte belongs to one block, so the writes are disjoint).
- `core/src/ffi_correct.rs` (new): `rang_core_correct_stokes_i` and
  `rang_core_blosc_decode_span_rows_strided`, `catch_unwind`, 0/1/2 status
  as in `ffi.rs`.
- `python/rangtoy/core_fetch.py`: `p5_library` (the core library when it
  exports the P5 symbols, else the standalone build `build_p5_standalone`
  into `core/target/p5-standalone`, offline, rayon from the core's lock;
  `RANG_P5_LIB` overrides), `p5_extension` (the extension when it carries
  the P5 bindings), `decode_rows_into`, `read_rows_into` (mmap, the same
  runs and statistics as `core_zarr.read_rows`), and `decode_slice`
  writing into one array per column.
- `python/rangtoy/core_campaign_array.py`: `eligible_cells`,
  `split_holdout_lean`, `solve_flags_lean`, `fused_candidates`
  (baseline groups of at most 2,048 rows), `solve_features`
  (`scores="fused"`, or `"numpy"` = L1's path, the pre-registered
  fallback), `guidance_scale`, `sparse_policy_mask`, additions stored as
  sorted indices (`additions_dense`), `correct_stokes_i` /
  `corrected_stokes` into two buffers reused across arms,
  `final_flags_summary` and `model_stokes_mean` in row blocks;
  `corrected_stokes_reference` keeps L1's NumPy path for the tests;
  `state["eligible"]` is dropped after the split counts.
- `python/rangtoy/core_flag.py`: `flags` and `stages` returned as bool
  views (`_bool_view` refuses a byte above 1).
- `python/rangtoy/core_campaign.py`: `tricolour_checks` in row blocks.
  K's driver (`run`, `solve_arm`, `tv_loop`, `apply_gains`) is unchanged.
- `tests/test_p5_memory.py` (16 tests) and the L1 tests in
  `tests/test_core_campaign_array.py` adapted to the sparse features and
  stored indices (three asserts; the bit-identity they check is kept).
- `examples/bench_p5_memory.py`: the bench (section 1.1) and `compare`
  (every non-timing field of two runs; images by task A's tolerances).

## 5. Measured result (2026-10-30)

### 5.1 Identity (criteria 1–5)

| Criterion | Run | Result |
| --- | --- | --- |
| 1 K precondition masks | `precondition-after` (`examples/precondition_luno_array.py`, code `ee1b02d`) | **pass**: K's eight checks pass; section-6 gains, gain flags, χ², converged and flagged-gain fractions, survey, the nine policy-mask hashes and counts equal the archive |
| 2 K replay | `precondition-after/replay` against `precondition-before/replay`: `compare` over 1,264 fields | **pass, identical**: every field equal, all 14 FITS images bit-identical, image hashes equal; the replay's `compare_replay` dict against K run `-01` is identical to the unmodified one (it still fails on image hashes only, the pre-existing P2 state of 1.4); part 3 (groups) 7.54e-5 / 7.63e-5, unchanged |
| 2 (bench runs) | `k4-after-b`, `s8-after`, `s12-after` against `k4-before`, `s8-before`, `s12-before` | **identical**: 1,259 / 1,136 / 1,168 fields, 14 / 12 / 12 FITS images bit-identical |
| 3 decode | `tests/test_p5_memory.py` on task G's archived fetch (`outputs/core-g-20261029-01`; K's fetch was deleted as a user item) and on stations 0–3; scratch check on stations 0–11 | **pass**: byte-identical arrays; statistics equal `read_rows`' |
| 4 array scale | `array-after` (all stations, code `ee1b02d`) against `array-before-b` (unmodified `07dfb86`, same host) and L1's archive | **pass**: against the before reference all 1,820 non-timing fields of `result.json` and `candidates.json` are equal (split counts, every arm's additions, gains and losses, TV, flag fractions, Tricolour summaries and checks, all 21 candidates' masks, counts and objectives, amendment-1 calls, hypotheses); image metrics within 9.5e-13 relative; 9 of 12 FITS images bit-identical, the `original`, `tv-policy` and `tv-unguided-best` dirty images differ by at most 3.1e-11 of the peak (tolerance 8.8e-6), every PSF bit-identical. Against L1's archive (pre-P1–P3 code): all 1,520 shared non-image fields equal, image metrics within 1.1e-12 relative (P2's pixel change); the unmodified rerun gives the same comparison (1,520 equal, 9.8e-14) |
| 5 units | `tests/test_p5_memory.py`; scratch `units-check-0-{3,11}.json` | **pass**: lean split, eligibility, solve flags, sparse masks (also with an active top-k cut), fused candidates over several baseline groups equal one call, final-flag summary and model mean equal the dense forms; the correction kernel is **bit-identical** to `apply_gains` + `stokes_i_reader` (samples and weights, synthetic with NaN data and weights, and on 0–3 and 0–11), better than the frozen 2-ulp allowance |

The fused-pass scores differ from NumPy's by at most 1.2e-14 (1.5), but
the candidate sets (`outliers ≥ 2`), the guidance median and all nine
masks are identical on 0–3 and 0–11, and the fallback was not needed
there.

### 5.2 Memory (criterion 6)

Bench peaks (composed HWM; section 1.1), the L1 driver with K's 512²
image and one group:

| Cells | Before: peak, B/cell | After: peak, B/cell | Change |
| ---: | ---: | ---: | ---: |
| 393,216 (stations 0–3) | 577 MB, 1,539 | 366 MB, 975 | −37 % |
| 1,835,008 (0–7) | 1,470 MB, 840 | 646 MB, 369 | −56 % |
| 4,325,376 (0–11) | 2,909 MB, 705 | 885 MB, 215 | −70 % |
| slope between 0–7 and 0–11 | **606 B/cell** | **101 B/cell** | |

Un-instrumented, `/usr/bin/time -v`: the precondition (K's precondition
plus the four-station replay with the group check) 614 MB → 440 MB.

Per stage, transient above entry / peak, B per cell (before → after):

| stage | 0–3 | 0–7 | 0–11 |
| --- | ---: | ---: | ---: |
| decode | +109/242 → +123/251 | +88/115 → +102/129 | +87/98 → +92/104 |
| split (`build_state`) | +27/269 → +39/258 | +32/147 → +33/155 | +31/129 → +32/132 |
| solves (`solve_arm`, all) | +171/531 → +48/352 | +176/353 → +34/190 | +177/303 → +99/214 |
| features (L1: `residual_amplitude`; P5: `solve_features`) | +168 → +17 | +176 → +22 | +163 → +91 |
| Tricolour (`flag_rows`) | +75/391 → +76/346 | +22/207 → +26/177 | +22/173 → +22/143 |
| gain correction (`corrected_stokes`) | +483/1539 → +1/353 | +518/840 → +0/346 | +507/705 → +8/205 |
| gridder (`core_grid.invert`) | +598/1071 → +646/975 | +150/349 → +133/369 | +60/219 → +56/215 |

Reading the table:

- Below 2,048 rows every row-block stage of L1 is one block, so its
  transients are whole-slice; at array scale L1's blocks capped them at
  about 2 GB. P5's features run on baseline groups of at most 2,048 rows,
  so at 0–11 (2,112 rows) one group copies almost the whole slice (+91);
  at array scale a group is 1/20 of the rows.
- At four stations the gridder's fixed working set (512², 64 w-layers,
  per-thread grids) is the peak; it is P2's and does not scale with cells.
- Decode and split are unchanged in transient terms at these sizes: the
  decode transient is the decoded arrays themselves, and the split's
  dominant temporaries are now the seed's draws per row block plus the
  eligible cells' draws, labels and sort order.

**Array scale** (85,577,728 cells; all memory figures in MiB as the
runs record them, bytes per cell in bytes):

| | Before (`array-before-b`, `07dfb86`) | After (`array-after`, `ee1b02d`) |
| --- | ---: | ---: |
| peak | **12,997 MiB, 159.3 B/cell** (`time -v` 13,308,612 kB, un-instrumented) | **10,406 MiB, 127.5 B/cell** (bench composed peak) |
| L1's frozen run (pre-P1–P3) | 12.46 "GB" (MiB as recorded), 152.7 B/cell | |
| wall (shared host, load 50–90 before, 36–70 after) | 1 h 21 min 38 s, `RAYON_NUM_THREADS=8` | 37 min 28 s, `RAYON_NUM_THREADS=4` |

Before, cumulative high-water mark after each stage (the run's own
`stages`), against after, the stage's own peak (bench):

| stage | before: HWM after stage | after: stage peak | after: transient above entry |
| --- | ---: | ---: | ---: |
| decode | 7,248 MiB (88.8 B/cell) | 6,984 MiB (85.6) | (the arrays themselves) |
| split | 9,865 (120.9) | 8,352 (102.3) | +1,431 MiB (+17.5 B/cell) |
| solve `original` + features | 10,495 (128.6) | 8,455 (103.6) | +1,182 (+14.5) |
| Tricolour first pass | 11,823 (144.9) | 9,813 (120.2) | +2,220 (+27.2) |
| Tricolour mild | 12,901 (158.1) | 9,869 (120.9) | +2,220 (+27.2) |
| TV loops (all solves) | 12,997 (159.3) | 9,090 (111.4) | +1,076 (+13.2) |
| images (correction, weights, 4 groups) | 12,997 (159.3) | **10,406 (127.5)** | +2,348 (+28.8), of which the gridder +1,009 |
| amendment-1 calls | 12,997 | 8,939 (109.5) | +897 (+11.0) |

- **Target missed**: 127.5 B per cell against the pre-registered ≤ 115
  (expected 100–112). The peak is now the imaging stage: the reused sample
  and weight buffers (12 B per cell), the imaging weights (4 B), the
  channel group's contiguous copies and the gridder's samples (+1,009 MiB
  in `core_grid.invert`, about twice P2's 52 B per kept sample estimate)
  on a retained state of about 93 B per cell. The Tricolour stage (+27 B
  per cell: P3's window, the twelve stage planes, the output flags) is
  second. Both are in other tasks' Rust (section 6).
- **Achieved**: −2,591 MiB (−20 %) at array scale against the same-host
  unmodified driver, −1.88 GiB below L1's recorded peak; per-cell slope
  between subsets 606 → 101 B per cell; every stage's transient ≤ 29 B per
  cell (criterion of section 0: met).
- Side effect on time (not a P5 criterion; shared host, different thread
  counts): an image takes 13–15 s instead of 288–633 s (the gain correction
  was most of it), decode 24 s instead of 48 s, the split 122 s instead of
  53 s (the lexsort; cores busy 0.19 under load). The amendment-1 loop
  429 s against 933 s and the TV loop 756 s against 610 s are solver time
  under different loads and threads.
- The 3 dirty images that are not bit-identical: the correction kernel is
  bit-identical to `apply_gains` on every cell of the 0–3 and 0–11 subsets
  (5.1), so some cell of the whole array is rounded differently (NumPy's
  2×2 matmul may take its BLAS path on some blocks); not traced further,
  as the pixels are 5 orders inside task A's tolerance and every PSF,
  weight sum and count is identical.

An earlier unmodified attempt (`array-before`, 09:31) was **killed by the
kernel's OOM killer** after 15 min at 13.2 GB, while a sibling's DDFacet
processes held most of the host's memory; recorded as a failed run and
repeated from a pristine export (`~/Build/tmp/20261030-rang-p5-before`).

### 5.3 Rust checks (criterion 7)

- Standalone crate (`core/target/p5-standalone`, the generated root with
  `blosc.rs`, `correct.rs`, `ffi_correct.rs`): `cargo build --release`,
  `cargo test` (11 tests: 5 new, 6 of `blosc.rs`), `cargo clippy
  --all-targets -- -D warnings` and `rustfmt --check` all pass.
- **With the coordinator's lines applied** (scratch copy
  `~/Build/tmp/20261030-rang-p5-ext`, patch below): `rang-core` builds, its
  60 tests pass, clippy `-D warnings` and fmt pass; the extension builds
  with `maturin develop`, its clippy and fmt pass. `tests/test_p5_memory.py`
  and `tests/test_core_campaign_array.py` pass on the extension backend
  (P5 calls go through the new bindings) and on the ctypes backend (the
  symbols come from `librang_core`, and no standalone build is made). The
  four-station bench through the extension is identical to the unmodified
  replay (1,264 fields, 14 images bit-identical). Log
  `outputs/p5-memory-20261030-01/exttest.log`.

## 6. For the coordinator

- **STATE paragraph.** "Big plan task P5, 2026-10-30 (implemented;
  measured): one copy of the cube. Tiles decode straight into the final
  arrays (strided Rust decode, mmap), the split runs in row blocks with one
  lexsort, the base solves' outlier scores come from the fused pass over
  baseline groups and are kept sparse, additions are stored as indices, and
  gain correction plus the Stokes I reader run in Rust (`core/src/correct.rs`)
  into reused buffers. Every identity gate passes: K's precondition masks
  and the four-station replay identical (images bit-identical); the
  whole-array run equals the unmodified driver on all 1,820 non-timing
  fields (three dirty images within 3.1e-11 of the peak) and L1's archive
  on every non-image field. Whole-array peak 12,997 → 10,406 MiB (159 →
  128 B per cell, −20 %); the pre-registered ≤ 115 B per cell is missed,
  the gridder and the Tricolour port now set the peak. An image takes
  13–15 s instead of 5–10 min. Report `research/p5-memory.md`."
- **Timing rows** for `tool-timings.md`: the table "Timings" below.
- **Upstream observations.** RATT (`ratt-ru`): none new (Tricolour's stage
  outputs are a rang port detail; QuartiCal is not involved). RATT
  `caracal-pipeline` (CARACal, Stimela): nothing new. Non-RATT, not
  reported by decision: NumPy's stacked 2×2 complex matmul appears to round
  a few cells differently from its plain loop at array scale (not traced);
  the LUNO store's 50,000-row × 128-channel chunks force whole-tile decode
  (already listed by L1).
- **Evidence to keep:** `outputs/p5-memory-20261030-01` (bench runs
  `k4-*`, `s8-*`, `s12-*`, `array-before-b`, `array-after`,
  `precondition-before`, `precondition-after`, the `compare-*.json`
  reports, `units-check-*.json`, `scores-check-*.json`,
  `coordinator-lines.patch`, `exttest.log` and the `.log` files). May be
  deleted: `array-before` (the OOM-killed attempt) and the scratch trees
  `~/Build/tmp/20261030-rang-p5-before` and `~/Build/tmp/20261030-rang-p5-ext`
  (removed at the end of this task).
- **`core/src/lib.rs`**: add `pub mod correct;` (after `pub mod blosc;`)
  and `pub mod ffi_correct;` (after `pub mod ffi;`).
- **`core/py/src/lib.rs`**: `use rang_core::ffi_correct::CorrectInputsC;`,
  the two functions below, and
  `m.add_function(wrap_pyfunction!(blosc_decode_span_rows_strided, m)?)?;`
  `m.add_function(wrap_pyfunction!(correct_stokes_i, m)?)?;` after the
  `blosc_decode_span_rows` registration. The full tested patch is
  `outputs/p5-memory-20261030-01/coordinator-lines.patch`.
- **`python/rangtoy/core.py`**: nothing is required. The P5 wrappers live
  in `core_fetch.py`, which uses the extension's bindings when present and
  otherwise registers its own ctypes symbols (from `librang_core` once the
  modules are listed; the standalone build is then never made).
  After P7 drops the ctypes path, `build_p5_standalone` and `p5_library`
  can be deleted with it.
- **For P7 (owner of `core.py`):** `core.solve_complex` converts the flag
  cube with `np.asarray(flag, bool)` then `np.require(..., np.uint8)`, so a
  uint8 cube is copied twice and a bool cube once (4 B per cell at the
  whole array, 342 MB per solve). Accepting a uint8 or bool cube without a
  copy would let `solve_flags_lean` write the solver's buffer directly.
- **For P3/P7 (owners of `sumthreshold.rs`, `ffi_flag.rs`):** the stage
  planes are 1 B per window cell per step (12 steps: about 12 B per cell
  at the whole array) and only their fractions are used by the campaign; a
  "fractions only" output would remove them.

Extension block for `core/py/src/lib.rs` (as tested):

```rust
/// `rang_core_correct_stokes_i` on borrowed arrays (big plan P5,
/// `research/p5-memory.md`); `added` may be None. Returns the C status.
#[pyfunction]
#[pyo3(signature = (nrow, nchan, ntime_bins, nfreq_bins, nant, data, weights, flags, flag_row, added, antenna1, antenna2, time_bin, freq_bin, inverse, valid, sample, weight))]
#[allow(clippy::too_many_arguments)]
fn correct_stokes_i(
    nrow: usize,
    nchan: usize,
    ntime_bins: usize,
    nfreq_bins: usize,
    nant: usize,
    data: Ro<'_, f32>,
    weights: Ro<'_, f32>,
    flags: Ro<'_, u8>,
    flag_row: Ro<'_, u8>,
    added: Option<Ro<'_, u8>>,
    antenna1: Ro<'_, u32>,
    antenna2: Ro<'_, u32>,
    time_bin: Ro<'_, u32>,
    freq_bin: Ro<'_, u32>,
    inverse: Ro<'_, f64>,
    valid: Ro<'_, u8>,
    mut sample: Rw<'_, f32>,
    mut weight: Rw<'_, f32>,
) -> PyResult<i32> {
    let Some(cells) = nrow.checked_mul(nchan) else {
        return Ok(1);
    };
    let gains = ntime_bins * nfreq_bins * nant;
    let (data, weights, flags, flag_row) = (
        data.as_slice()?,
        weights.as_slice()?,
        flags.as_slice()?,
        flag_row.as_slice()?,
    );
    let added = match &added {
        Some(a) => Some(a.as_slice()?),
        None => None,
    };
    let (antenna1, antenna2, time_bin, freq_bin) = (
        antenna1.as_slice()?,
        antenna2.as_slice()?,
        time_bin.as_slice()?,
        freq_bin.as_slice()?,
    );
    let (inverse, valid) = (inverse.as_slice()?, valid.as_slice()?);
    let (sample, weight) = (sample.as_slice_mut()?, weight.as_slice_mut()?);
    if data.len() != 8 * cells
        || weights.len() != 4 * cells
        || flags.len() != 4 * cells
        || flag_row.len() != nrow
        || added.is_some_and(|a| a.len() != cells)
        || antenna1.len() != nrow
        || antenna2.len() != nrow
        || time_bin.len() != nrow
        || freq_bin.len() != nchan
        || inverse.len() != 8 * gains
        || valid.len() != gains
        || sample.len() != 2 * cells
        || weight.len() != cells
    {
        return Ok(1);
    }
    let inputs = CorrectInputsC {
        nrow,
        nchan,
        ntime_bins,
        nfreq_bins,
        nant,
        data: data.as_ptr(),
        weights: weights.as_ptr(),
        flags: flags.as_ptr(),
        flag_row: flag_row.as_ptr(),
        added: added.map_or(std::ptr::null(), |a| a.as_ptr()),
        antenna1: antenna1.as_ptr(),
        antenna2: antenna2.as_ptr(),
        time_bin: time_bin.as_ptr(),
        freq_bin: freq_bin.as_ptr(),
        inverse: inverse.as_ptr(),
        valid: valid.as_ptr(),
    };
    // SAFETY: every slice is live for the call and has the length checked above.
    Ok(unsafe {
        rang_core::ffi_correct::rang_core_correct_stokes_i(
            &inputs,
            sample.as_mut_ptr(),
            weight.as_mut_ptr(),
        )
    })
}

/// `rang_core_blosc_decode_span_rows_strided`: rows land at byte
/// `offset + i * stride` of the caller-owned uint8 array `out` (P5).
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn blosc_decode_span_rows_strided(
    head: &[u8],
    first: usize,
    count: usize,
    span: Ro<'_, u8>,
    row_bytes: usize,
    rows: Ro<'_, usize>,
    mut out: Rw<'_, u8>,
    offset: usize,
    stride: usize,
) -> PyResult<i32> {
    let (span, rows) = (span.as_slice()?, rows.as_slice()?);
    let out = out.as_slice_mut()?;
    if offset > out.len() {
        return Ok(1);
    }
    let out = &mut out[offset..];
    // SAFETY: every slice is live for the call; `out` bounds the writes.
    Ok(unsafe {
        rang_core::ffi_correct::rang_core_blosc_decode_span_rows_strided(
            head.as_ptr(),
            head.len(),
            first,
            count,
            span.as_ptr(),
            span.len(),
            row_bytes,
            rows.as_ptr(),
            rows.len(),
            out.as_mut_ptr(),
            out.len(),
            stride,
        )
    })
}
```

## 7. Open items

- The ≤ 115 B per cell target: the remaining peaks are the gridder's
  per-group copies and samples (P2's `grid.rs`, about 12 B per cell) and the
  Tricolour stage planes and window (P3's `sumthreshold.rs`/`ffi_flag.rs`,
  about 27 B per cell). A "fractions only" stage output and gridding
  straight from strided `(row, chan)` buffers would take the peak to about
  105 B per cell.
- `core.solve_complex` copies the flag cube (section 6, for P7).
- The three not bit-identical dirty images at array scale: cause not traced
  (inside tolerance by five orders).
- The bench resets `VmHWM`, which invalidates the instrumented runs' own
  `max_rss_mb` and `/usr/bin/time` peaks; the after-run's headline is the
  bench's composed peak, the before-run's the un-instrumented one.

## Timings (every tool run of this task)

| When (UTC) | Tool run | Wall | Peak RSS | Note |
| --- | --- | ---: | ---: | --- |
| 2026-10-30 | `uv venv` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin psutil` | 1 min 20 s | – | public PyPI |
| 2026-10-30 | `maturin develop --release --offline` | 1 min 21 s | – | |
| 2026-10-30 | `cargo build --release` (core) | 55 s | – | |
| 09:23 | bench `campaign` stations 0–3 (`k4-before`) | 45 s (run), 1 min 14 s (process) | 577 MB (bench); 621 MB `time -v` (includes `cargo`) | baseline |
| 09:26 | bench `campaign` stations 0–7 (`s8-before`) | 44 s | 1,470 MB (bench) | baseline |
| 09:27 | bench `campaign` stations 0–11 (`s12-before`) | 1 min 44 s | 2,909 MB (bench) | baseline |
| 09:31 | `examples/precondition_luno_array.py` unmodified (`precondition-before`) | 39 s | 614 MB | part 2 fails on image keys only (1.4) |
| 09:33 | scratch score pre-check, stations 0–3 and 0–11 | 14 s, 43 s | 155 MB, 1.19 GB | 1.5 |
| 09:31 | unmodified whole-array run (`array-before`) | 14 min 57 s | 13.2 GB at kill | **killed by the OOM killer** (sibling DDFacet held the host's memory); failure recorded |
| 2026-10-30 | standalone P5 crate: build, test (11), clippy `-D warnings`, rustfmt (twice; one clippy fix `collapsible_if`, one rustfmt rewrite) | about 1 min each | – | section 5.3 |
| 09:50 | scratch unit checks, stations 0–3 (includes the first standalone build) | 48 s | 332 MB | all identical |
| 09:52 | scratch unit checks, stations 0–11 | 40 s | 2.97 GB | all identical |
| 09:54 | unmodified whole-array run from a pristine export (`array-before-b`), `time -v`, 8 threads, load 50–90 | **1 h 21 min 38 s** | **13,308,612 kB** | reference; MemAvailable 22.5 GiB at start |
| 09:56 | bench `campaign` 0–3 with the group check (`k4-after`) | 45 s | 380 MB (bench) | identical to the unmodified replay |
| 09:58 | `precondition_luno_array.py` with P5 (`precondition-after`) | 51 s | 440 MB | same pass/fail dict as before; replay identical |
| 10:00 | targeted pytest (`test_p5_memory`, `test_core_campaign_array`, `test_core_fetch`, `test_core_zarr`, `test_core_campaign`) | 41 s | 161 MB | 37 passed, 1 skipped (K fetch deleted; then pointed at task G's fetch: 2 passed, 40 s) |
| 10:02 | bench `campaign` 0–7 and 0–11 (`s8-after`, `s12-after`) | 1 min 30 s, 1 min 58 s | 646 MB, 885 MB (bench) | identical to before |
| 10:08 | coordinator lines in a scratch copy (`exttest.log`): uv venv, core build/test/clippy/fmt, `maturin develop`, extension clippy/fmt, pytest on both backends, bench through the extension | about 20 min (load 60–90) | – | all pass |
| 10:40 | bench `campaign` 0–3 without the group check (`k4-after-b`) | 58 s | 366 MB (bench) | identical to `k4-before` |
| 11:20 | bench `campaign` all stations (`array-after`), 4 threads, `OPENBLAS_NUM_THREADS=1`, load 36–70 | **37 min 28 s** | **10,406 MiB (bench composed)**; `time -v` 9,070,168 kB is invalid under the HWM reset | identical (section 5.1) |
| 11:58 | `compare` after vs before; scratch archive comparisons (before and after vs L1) | seconds | – | pass |
| 12:02 | `flock /home/gijsm/.rang-checkall.lock bash tools/check-all.sh` (4 threads, `OPENBLAS_NUM_THREADS=1`; lock wait 0 s) | 3 min 24 s (pytest 586 passed, 1 skipped in 2 min 17 s) | 1.50 GB | **overall PASS** (`outputs/p5-memory-20261030-01/check-all.log`) |
