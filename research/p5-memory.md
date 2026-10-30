# Big plan task P5: memory, one copy of the cube

Protocol frozen 2026-10-30 on branch `p5-memory` (from origin/main
`07dfb86`) before any campaign code was changed. Task P5 of
[big-plan.md](big-plan.md) and section 3 "P5 Memory" of
[simplification-review.md](simplification-review.md).

Status: **proposed; baseline measured** (sections 1–2). Implementation and
the measured result follow in later sections.

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
| 09:31 | unmodified whole-array run (`array-before`) | running | | section 4 |
