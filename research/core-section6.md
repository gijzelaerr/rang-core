# Rang core: the section 6 prototype as frozen

Protocol written 2026-10-29, before any decoder or prototype code. Status:
**proposed**. Section 6 of
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
