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

## Measured result (provisional)

Run on 2026-10-29 after protocol commit `807eb52`:

- **Slice:** `outputs/luno-support-20261029-01/slice`, 122 objects,
  3,222,257,341 bytes, receipt SHA256 `9a2b7d5a…3643c`.
- **Extraction and survey:** as frozen, with no code or threshold changes.
- **Archive:** [meerkat-luno-support.json](results/meerkat-luno-support.json).
  It holds all summaries, every failure row, the whole-array per-antenna
  counts, the input and code hashes, the result SHA256 `08f0d25e…aef` and the
  post-hoc status audit.
- **Stations:** m000–m003.

| | PKS 1934−638, scan 2 | PKS 1830−211, scan 3 |
| --- | ---: | ---: |
| Integrations in row chunk 0 | 32 | 10 (whole scan) |
| Gain bins | 1,024 | 320 |
| Bins with TRAIN data | 432 | 160 |
| Fully identified bins | 389 | 0 |
| Underidentified bins | 43 | 15 |
| Over-rank bins | 0 | 145 |
| No-TRAIN bins | 592 | 160 |
| TRAIN cells, fully / under | 116,805 / 751 | 0 / 128 (rest over-rank) |
| Native status, `(H,0,0,0)` call | 389 × 0, 43 × 3 | 160 × 6 |

Identity and the seed-20261029 random gain point give the same counts. The
only difference is that a few 1830−211 over-rank bins have rank 30 rather than
31.

**Crosscheck correction (post hoc, reporting only).** The frozen crosscheck
called `anchored_response(H, 0, H, 0, …)`. The kernel's retained curvature is
`full_h − drop_h`, so that call makes it zero and returns status 4 ("retained
rank loss") on every fully identified bin. The frozen survey only compared
status 3 with the underidentified label, so this went unnoticed, and the first
pushed version of this report overstated agreement as "432/432".
`examples/audit_luno_support_status.py` re-evaluates the same extraction under
both calls:

- **Frozen call:** 389 × status 4 and 43 × status 3 for 1934−638; all 160 bins
  status 6 for 1830−211.
- **The original survey's `(H, 0, 0, 0)` call:** 389 × status 0 and 43 ×
  status 3, matching the rank labels exactly. All 160 1830−211 bins still return
  status 6, the U(2) gauge-null mismatch, which confirms the model reading below.

Rank labels and counts are unchanged.

**PKS 1934−638.** MODEL_DATA is scalar: XX equals YY, and XY and YX are exactly
zero. 90.0% of supported bins and 99.36% of TRAIN cells meet `8*nactive-4`. All
43 failures have a tree-shaped support graph, with no odd cycle:

- 17 bins have only baseline 0–3 (rank 8 against the required 12);
- 15 bins have the path 0–3–2 (rank 16 against 20);
- 11 bins have the four-station star around station 2 (rank 24 against 28).

This is the same mechanism as the earlier bin 811: connected support without
an odd cycle does not identify full-Jones gains.

**PKS 1830−211.** The frozen common-U(2) condition does not apply.
MODEL_DATA carries small cross-hand terms, with median |XY/XX| of 1.1e-3 and
median |YX/XX| of 1.2e-3. These break the gauge, so four-station bins reach
rank 30–31 against the scalar-model 28. The native kernel returns status 6
(U(2) gauge-null mismatch) on all 160 supported bins. The 15 bins that rank
classifies as underidentified are trees as well: baseline 0–2, or a path
through 0–2. Per the protocol,
the model is not edited after the fact. Zeroing or replacing the cross-hand
model would need its own frozen follow-up.

**Where support is missing.** No-TRAIN bins come from channels flagged on every
baseline, not from time. In both scans, roughly 1150–1311 MHz and 1471–1498 MHz
have no TRAIN cells, which is the L-band RFI region masked by the earlier
processing. Every integration keeps about 30% (1934−638) or 39% (1830−211) of
its cells.

**Whole array.** Antennas 25 (m031), 33 (m040) and 37 (m044) have no TRAIN cell
in either scan, so they are entirely flagged or zero-weight in this slice. The
median antenna has about 1.19 M TRAIN cells in the 1934−638 chunk.

**Weights.** TRAIN weights differ between scans:

- 1934−638: XX and YY 0.50–8.45 (median 4.38), XY and YX 0.95–15.7 (median
  about 8.1);
- 1830−211: all four correlations nearly constant, about 0.37–0.40.

Values do not affect rank. The spread is consistent with processing-scaled
weights. On 1934−638 the cross-hand weights are uniformly about twice XX and YY;
`calwt` rescaling of equal starting weights would not naturally produce that,
which hints that another step wrote the weights. This is an observation, not a
conclusion, and it bears on the weight question put to Ben.

**Model origin.** Neither surveyed MODEL_DATA has a logged origin:

- The only `setjy` row names field J1331+3030 (3C 286).
- A `clearcal` with `addmodel=True` on field 2 (1830−211) would have reset that
  model to unity, yet it now holds about 12.8 Jy with cross-hand terms.
- The 1934−638 model (about 14.9 Jy, scalar, with a small imaginary part)
  matches no HISTORY row either.

Both were presumably written later, for example by an unlogged prediction step.
The survey depends on these models, so their source is listed as open in
[the candidate report](flagging-luno-candidate.md#still-open).

**What this does and does not show.** On processed support, a second, real
MeerKAT observation gives mostly identified four-station TRAIN support on its
flux calibrator, with failures confined to tree-shaped bins. The gain calibrator
is not covered by the frozen scalar-model condition. Nothing about
calibration, flagging, signal transfer or image quality is measured. Everything
here stays provisional until the licence is confirmed and the native weights
and flags are established.
