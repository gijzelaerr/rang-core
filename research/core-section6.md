# Rang core: the section 6 prototype as frozen

Protocol written 2026-10-29 in `fead4ef`, before any decoder or prototype
code. Status: **implemented; measured: run `-01` failed criterion 8; after
implementation fixes with unchanged criteria, run `-02` passes all eleven**. Section 6 of
[stack-consolidation-feasibility.md](stack-consolidation-feasibility.md)
froze ten acceptance criteria in `fe9f049` for one fused pass from the LUNO
zarr tiles to the rank survey. Phases 1–3 met most of them piecewise, but
phase 2 solved from an MS export, so criteria 8 (runtime from zarr) and 9
(no Measurement Set) are still open. This protocol runs section 6 as frozen.
It adds only what section 6 left unspecified, listed below, and changes none
of its numbers. A reimplementation; under AGENTS.md not a scientific
contribution.

## Additions, fixed before any code

- **Zarr ingest at the edge, in Rust.** `core/src/blosc.rs` decodes the
  blosc-1 chunks of the public store (format 2, LZ4, byte shuffle, split
  streams; the only codec the needed arrays use). Python reads chunk files
  and selects rows; Rust decodes. Only the blosc blocks that contain the
  selected rows are decoded, so a 205 MB tile is never fully expanded.
- **Ingest oracle.** `examples/oracle_luno_chunks.py` runs once in
  `rang-flagging:local` and records, for every chunk the prototype reads, the
  SHA256 of the bytes numcodecs decodes, and the time it takes. It is run,
  timed and hashed before the decoder is first used.
- **χ² for criterion 3.** Section 6 asks for the post-solve χ² against
  QuartiCal's logged 0.27 (two decimals), recomputed with "the same residual
  definition". The definition is fixed now as the mean over the survey's
  TRAIN cells of the per-cell mean over four correlations of $w|r|^2$; at
  QuartiCal's archived gains this gives 0.26824, consistent with the log
  (phase 2 archive). Criterion 3 compares the core value with that.
- **Criterion 6, TV.** The core path and the reference path both compute TV
  with the existing Rust kernel through `rangtoy.flagging.gain_tv`, so the TV
  part of criterion 6 holds by construction and is reported as such. The MAD
  scores and policy masks are a real comparison: fused-pass scores against
  `residual_features`.
- **Criterion 8 reading.** Wall time excludes only the blosc decode, as
  written; the peak RSS limit applies to the whole process, decode included.
- **Comparator precondition** (section 9). This run compares arrays with
  archived arrays and counts, not a result tree with a comparator, so the
  archive-versus-reproduction precondition does not apply; the ingest oracle
  plays that role for the new decoder.

## Inputs (frozen)

- LUNO row chunk 0, tiles 8–23: DATA from `outputs/luno-solve-20261029-02/inputs`,
  and FLAG, WEIGHT_SPECTRUM, MODEL_DATA, ANTENNA1, ANTENNA2, TIME, FLAG_ROW
  from `outputs/luno-support-20261029-01/slice`, as `build_luno_ms.py` reads
  them (stations 0–3, cross rows with FLAG_ROW false, channels 1024–3071).
- Oracles: `outputs/luno-solve-20261029-02/solve/gains.npy` and
  `gain_flags.npy`, the archived convergence and rank survey in
  `research/results/meerkat-luno-solved.json`, the phase 2 arrays
  `outputs/core-phase2-inputs-20261029-01/arrays.npz` (the MS-built arrays)
  and, for criterion 7, the fixture clean case as in phase 2.

## Acceptance criteria

Section 6 criteria 1–10 as frozen in `fe9f049`, with the additions above, and:

11. **Ingest.** Every decoded chunk's SHA256 equals the ingest oracle, and the
    selected 192 × 2048 × 4 arrays equal the MS-built arrays of phase 2
    exactly (DATA, MODEL_DATA, FLAG, WEIGHT_SPECTRUM, ANTENNA1, ANTENNA2,
    TIME, FLAG_ROW).

Reported, not gated: decode time and bytes decoded with block selection,
against the full-tile decode (2.3 s, 3.28 GB) and the measured chain.

## Measured result (2026-10-29)

**Ingest oracle.** `outputs/core-section6-oracle-20261029-01`: numcodecs
(c-blosc 1.21.6) decoded the 68 chunks in 1.48 s; the Rust decoder reproduces
every decoded chunk's SHA256.

**Run `-01`** (`outputs/core-section6-20261029-01`, checked in
`core-section6-check-20261029-01`): criteria 1–7 and 9–11 pass; **criterion 8
fails**: 2.86 s excluding decode
(limit 2.0 s) and 299 MB peak RSS (limit 200 MB). The memory peak came from
the receipt, which read whole 170 MB chunk files to hash them; the time from
per-row copies in Python during ingest and per-bin eigenvalue calls.

**Implementation fixes, criteria unchanged:** streamed SHA256 in the receipt;
the Rust decoder copies the requested rows while decoding each run of blocks;
one batched eigenvalue call in the survey.

**Run `-02`** (`outputs/core-section6-20261029-02`, checked in
`core-section6-check-20261029-02`): **all eleven criteria pass.** Archive:
[core-section6.json](results/core-section6.json).

| Criterion | Measured (run `-02`) | Limit |
| --- | --- | --- |
| 1 gain flags | identical to QuartiCal | exact |
| 2 baseline products | max 5.6e-16 (gain entries 3.3e-16) | 1e-6 |
| 3 χ² | 0.26824, equal to the value at QuartiCal's gains | ≤ 0.275 |
| 4 rank survey | 389 status 0, 43 status 3, 592 without TRAIN data | exact |
| 5 diagonal normal blocks | 0 relative difference | 1e-13 |
| 6 MAD scores; policy masks | 1.3e-14; all nine identical (TV by construction) | 1e-12; exact |
| 7 fixture clean case | gains within 1.4e-15, validity identical, TV 1.9e-16 from the archive | 1e-6 |
| 8 cost | 1.67 s excluding decode; 140 MB peak RSS | 2.0 s; 200 MB |
| 9 outputs | `result.json`, `gains.npz`, `receipt.json` only; no MS | – |
| 10 receipt | 68 input chunk hashes, code, settings, oracle gain hashes | – |
| 11 ingest | every chunk hash equals numcodecs; arrays equal the MS-built arrays | exact |

**Time per step (run `-02`).** Ingest 1.50 s, of which
1.29 s is decode; solve 0.62 s (50
iterations); fused pass 0.07 s; TV and nine policy masks
0.04 s; rank survey 0.73 s. Whole
process 5.2 s including Python start-up, imports and the receipt.

**Ingest with block selection (reported).** The pass read
752 MB and decoded 2048 of 12544 blosc
blocks, against reading and decoding 2.72 GB of DATA tiles plus the support
tiles in full before. The block-start table that makes this possible would
also allow HTTP range requests against the public bucket, so a four-station
slice could be fetched without downloading whole tiles; this is noted in
[upstream-notes.md](upstream-notes.md) and not yet measured.

**Against the measured chain** (section 2.1): MS build 4.1 s, QuartiCal
28.3 s cold or 3.6 s warm (633 or 382 MB), survey 1.5 s; this pass replaces
all of it with 1.67 s excluding decode, in 140 MB, with no MS and no
container. The S3 fetch is unchanged.
