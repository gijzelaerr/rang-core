# LUNO 1934−638 support at solved gains

Protocol frozen 2026-10-29, after the dry run and before any LUNO DATA tile was
fetched. This follows the [processed-support survey](flagging-luno-support.md)
and is provisional for the same reasons: the licence and the native weights are
unconfirmed (Ben Hugo has been asked), and no visibilities are redistributed.

## Question

The processed-support survey evaluated four-station rank at identity and at
random gains. Does rank on PKS 1934−638 change at gains that QuartiCal actually
solves from the data? The expected outcome is no change: on a scalar model,
identity and random gains already agreed. Agreement is therefore a consistency
check, not a new finding.

## Frozen design

- **Data.** The same cells as the support survey: `LBAND_LUNO_CALIBRATORS.zarr`
  group 1 (scan 2), row chunk 0, channels 1024–3071 (1070.0–1497.8 MHz),
  stations 0–3 (m000–m003), and cross rows whose FLAG_ROW is false (192 rows).
  DATA tiles 8–23 are added, 2,717,394,612 bytes by HEAD.
- **MS.** `examples/build_luno_ms.py` writes a casacore `default_ms` in the
  pinned container:
  - MAIN gets the four-station rows with DATA, MODEL_DATA, FLAG,
    WEIGHT_SPECTRUM, SIGMA_SPECTRUM = 1/√w (0 where w = 0), and the row columns
    from chunk 0.
  - ANTENNA is trimmed to rows 0–3 and FEED to those antennas, concatenating
    dask-ms's per-antenna FEED groups.
  - SPECTRAL_WINDOW is rewritten for the 2048 channels.
  - POLARIZATION, DATA_DESCRIPTION, FIELD, OBSERVATION and STATE are copied.
  - Only unfiltered numeric and json2 arrays are decoded.
- **Solve.** `examples/solve_luno.py` runs the frozen pipeline command from
  `rangtoy.flagging_workflow.solve`: `G.type=complex`, `G.time_interval=2`,
  `G.freq_interval=32`, 50 iterations (the `train()` default, as used by the
  campaign recipes), convergence 1e-7, reference antenna 0, robust and MAD off,
  `output.flags=false`, single-threaded. FLAG and FLAG_ROW must be
  byte-identical afterwards.
- **Survey.** `examples/survey_luno_solved.py` uses the frozen survey's TRAIN
  cells, grid, native normals, 1e-10 cutoff and `8*nactive-4`, with each bin's
  gains taken from the solve.
  - A supported bin whose active-station gains QuartiCal flagged, or left
    non-finite, is reported as `no_solved_gain`. It is not dropped and not
    classified.
  - Native status is tabulated per label with the original
    `anchored_response(H, 0, 0, 0)` call.
- **Recorded diagnostics.** QuartiCal convergence (`conv_iter`, `conv_perc`),
  the flagged-gain fraction and the log. These depend on the processed
  WEIGHT_SPECTRUM and on a 1934−638 MODEL_DATA with no logged origin, so they
  are labelled conditional on both. This is the first real solve on LUNO, not a
  calibration-quality result.

## Dry run (before freezing, before DATA)

The dry run used `outputs/luno-solve-20261029-01`, with DATA set to MODEL_DATA:

- **MS build:** 2.4 s; 192 rows × 2048 channels.
- **QuartiCal:** exit 0 in 27 s; FLAG unchanged; gains shaped (16, 64, 4, 2×2);
  converged.
- **Bin mapping:** 432 bins carry TRAIN data, matching the survey. QuartiCal's
  gain flags match station support exactly (0 supported station-bins flagged,
  0 unsupported unflagged).
- **Gains:** the baseline closure |G_p G_qᴴ − I| is exactly 0 on unflagged
  gains, so the solve stays at its identity start.
- **Survey at the solved gains:** reproduces the identity result exactly, with
  389 fully identified bins (status 0) and 43 underidentified (status 3).

The dry run found two builder issues, both fixed before freezing:

- FEED is partitioned per antenna;
- string-array columns need explicit shapes.

It also found that S3 listings stop at 1000 keys, so
`tools/flagging/fetch-luno-solve.sh` now paginates. The real run uses the fresh
namespace `outputs/luno-solve-20261029-02`. Its subtable fetch (2,608 objects,
2.3 MB) is already in place.

## Note after freezing (2026-10-29, 15:37 SAST)

Mid-run, the observer said in chat that WEIGHT_SPECTRUM was modified by
QuartiCal and that SIGMA_SPECTRUM holds the original inverse variances. The
frozen design is unchanged. Rank depends only on weight positivity, but the
solve itself is weighted by a QuartiCal-derived WEIGHT_SPECTRUM, so its
diagnostics stay conditional on that.

## Measured result (provisional)

Run on 2026-10-29 in `outputs/luno-solve-20261029-02`, after protocol commit
`487208b`, with no change to code or settings. Archive:
[meerkat-luno-solved.json](results/meerkat-luno-solved.json).

- **Inputs.**
  - DATA tiles: 17 objects, 2,717,394,982 bytes, about 461 s.
  - Subtables and row columns: 2,608 objects, 2,306,677 bytes, 432 s.
  - MS build: 4.4 s, 192 rows × 2048 channels.
- **QuartiCal.** Exit 0 in 27.5 s (24.6 s graph execution), with FLAG and
  FLAG_ROW byte-identical afterwards.
  - Chi-squared fell from 73.75 to 0.27.
  - 98.3% of solution intervals converged within the frozen 50 iterations; the
    chunk's `conv_iter` reached the 50 cap.
  - 59.0% of station-bin gains are flagged, exactly the unsupported
    station-bins. No supported station-bin was flagged.
  - Unflagged gains have a median diagonal amplitude of 0.79 and a median
    off-diagonal amplitude of 0.006.
  - The maximum baseline closure |G_p G_qᴴ − I| is 0.42, so the solved gains
    clearly differ from identity.
- **Rank at the solved gains.** Exactly as at identity and random gains:
  - 389 of 432 supported bins are fully identified, covering 116,805 TRAIN
    cells; all return native status 0.
  - 43 bins are underidentified, covering 751 cells; all return status 3.
  - No bin lacks a solved gain, none is over-rank, and 592 have no TRAIN data.

As declared, this agreement is the expected consistency result. On the scalar
1934−638 model, four-station rank does not depend on the gain point: identity,
seeded random and actually solved gains give the same classification bin for
bin. The solve diagnostics hold only for the processed inputs: the
QuartiCal-modified WEIGHT_SPECTRUM, as the observer confirmed, and a
1934−638 model with no logged origin. They say nothing about calibration
quality, flagging or imaging.
