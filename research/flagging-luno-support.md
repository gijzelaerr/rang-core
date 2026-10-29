# LUNO processed-support survey

Protocol frozen 2026-10-29 before any LUNO visibility-tile download or rank
computation.

## Decision and status

On 2026-10-29 the user chose to continue with the LUNO calibrators while the
licence and the native weights remain unconfirmed. Ben Hugo, the observer, was
asked the same day and has not answered yet. Results are therefore
**provisional**. Raw slices stay in ignored `outputs/`, and only compact
summaries are archived; no visibilities are redistributed. This is a
descriptive support survey, not calibration, flagging or a transfer
measurement.

## Why "processed" support

[Provenance](flagging-luno-candidate.md#provenance-found-2026-10-29) shows
CASA `applycal` (`calwt=True`, `calflag`), manual `flagdata`, `setjy` and
`clearcal` before export:

- **Weights.** Rank depends only on which cells carry positive weight, not on
  weight values, so `calwt` rescaling cannot change rank. A gain multiplied by
  zero stays zero, so the positive cross-hand weights cannot come from `calwt`
  alone. That makes native positivity likely, unless an unlogged QuartiCal or
  export step rewrote WEIGHT_SPECTRUM. This is an inference, not a finding.
- **Flags.** `calflag` and manual `flagdata` only add flags, and `clearcal`
  leaves FLAG alone. Given the decoded HISTORY, the processed support is a
  lower bound on native support.

The survey is therefore labelled "processed support", never native support.

## Frozen design, and how it differs from the ESO137-era survey

The [original survey](flagging-next-gain-support.md) is unchanged where
possible:

- the four-station, 32-real-parameter native Rust normals
  (`rangtoy.flagging_influence.training_normals`);
- the 2-integration × 32-channel gain grid;
- raw-eigenvalue rank with a relative cutoff of 1e-10;
- requirement `8*nactive-4` under the common-U(2) gauge;
- no-data bins counted separately, every failure row kept.

Fixed choices for LUNO:

- **Data.** `LBAND_LUNO_CALIBRATORS.zarr` row chunk 0 of group 1 (PKS 1934−638,
  scan 2) and group 2 (PKS 1830−211, scan 3). Scan 4 is skipped because a manual
  `flagdata` flagged it. Channel tiles 8–23 (channels 1024–3071,
  1070.0–1497.8 MHz) match the earlier TRAIN band. Columns: ANTENNA1, ANTENNA2,
  TIME, FLAG_ROW, FLAG, WEIGHT_SPECTRUM, MODEL_DATA. DATA is not downloaded, and
  no solve is run.
- **Stations.** The first four ANTENNA rows (indices 0–3), named from the
  json2 ANTENNA NAME array, regardless of their support. Whole-array per-antenna
  TRAIN cell counts are reported separately, including antennas 25, 33 and 37.
- **TRAIN cells.** Cross rows among the four stations where FLAG_ROW is false,
  no correlation is flagged, all four WEIGHT_SPECTRUM values are positive and
  MODEL_DATA is finite. The residual is set to zero, because rank uses the
  normal matrix only.
- **Gain point (deviation).** LUNO has no rang solve, so rank is evaluated at
  two declared points: identity gains, and a fixed-seed random point
  `I + 0.1(N + iN)` per bin and station (NumPy `default_rng(20261029)`). Rank at
  identity can be special, so a disagreement between the two points is reported,
  not resolved.
- **Model check.** Per field, report the fraction of TRAIN cells with a
  non-zero MODEL_DATA in each correlation. If a field's model is all zero, its
  bins are reported as "no model" and not classified. The model is not
  replaced.
- **Crosscheck.** `anchored_response(H, 0, H, 0, g, active)` per supported
  bin. Native status 3 ("underidentified full curvature") must agree with the
  rank classification. Disagreements are reported.

Execution, also fixed before any tile is fetched:

1. `bash tools/flagging/fetch-luno-support.sh outputs/luno-support-20261029-01/slice`.
   HEAD before freezing gives 3,222,232,014 bytes for the 96 visibility-tile
   objects.
2. `examples/extract_luno_support.py` runs in `rang-flagging:local` with the
   network off and the slice mounted read-only. It accepts only unfiltered
   numeric arrays and json2 strings, and writes the four-station rows and the
   whole-array counts.
3. `examples/survey_luno_support.py` runs in the host venv, using the frozen
   native library through `rangtoy.flagging_influence`.

A synthetic dry run, before freezing and before any download, checked the
code paths. Scalar models gave fully identified four-station bins and
two-station bins of rank 8 against the required 12, and the native crosscheck
agreed. Random full 2×2 models came out over-rank, because a non-scalar model
breaks the U(2) gauge. Over-rank LUNO bins are therefore read alongside the
reported XY/YX model fractions, not as kernel errors.

Outputs: per field and gain point, report all bins, bins with TRAIN data,
fully and under-identified bins, no-data bins, over-rank anomalies, TRAIN
cells by category and per-failure rows. The run directory is
`outputs/luno-support-20261029-01`, and the archive is
`results/meerkat-luno-support.json`.

## Measured result

Not yet run.
