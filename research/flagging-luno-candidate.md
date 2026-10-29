# Second public MeerKAT L-band candidate: LUNO calibrators

Probe on 2026-10-29. Metadata plus one bounded numeric tile; no visibilities
were calibrated, flagged or imaged, and no object/pickle array was decoded.
Exact object keys, sizes and SHA256 values are in
[meerkat-luno-candidate.json](results/meerkat-luno-candidate.json).

## Why look again

The [ESO 137-006 primary calibrator](flagging-public-data.md) has 61 antennas
but zero native XY/YX `WEIGHT_SPECTRUM`, so the strict four-correlation protocol
accepts no cells ([supported-data review](flagging-supported-data.md)). The
earlier candidate survey also rejected larger datasets for disk reasons (about
21 GiB free then; about 930 GB on the current host).

The same anonymous RATT bucket (`ratt-public-data`, af-south-1) also holds
`LBAND_LUNO_CALIBRATORS.zarr`, `LBAND_LUNO_TARGET.zarr` and `LUNO/`. `LUNO/` has
the same group count, array shapes and stored DATA bytes as the calibrator store;
it is treated as a duplicate. The bucket's `G330/` store has only two
correlations and 2,048 channels, so it cannot test full-Jones support.

## Measured facts

| Property | ESO137 primary | LUNO calibrators |
| --- | --- | --- |
| Antennas (ANTENNA rows / cross-participating in tile) | 61 / 61 | 56 / 56 |
| Longest baseline | — | 7.70 km |
| Fields | PKS 1934−638 | 3C 286, PKS 1934−638, PKS 1830−211 (by direction) |
| Scan groups | 8 | 20 (field 2 has 16, fields 0/1 two each) |
| Track length | — | 14,218 s, same observation as the target store |
| Channels | 4,096, 856–1711.79 MHz | 4,096, 856–1711.79 MHz |
| Correlations | XX/XY/YX/YY | XX/XY/YX/YY |
| Positive `WEIGHT_SPECTRUM` per correlation (tile) | XX/YY only; XY/YX zero | all four, 6,170,624 each |
| Cells with all four weights positive and unflagged | 0 | 1,735,448 of 6,170,624 cross cells |
| Columns | DATA, MODEL, CORRECTED, weights, sigma | also `CORRECTED_DATA_QCAL`, `IMAGING_WEIGHT` |
| HISTORY rows | 21 | 923 (object strings, not decoded) |

Field identities are inferred only from the numeric `PHASE_DIR` values
(202.785°, +30.509°), (294.854°, −63.712°) and (278.416°, −21.061°); FIELD
names are object arrays and were not decoded. The tile is `MAIN_0` (3C 286, scan 1),
row chunk 0 (50,000 rows, 32 integrations, about 248 s), channels 1024:1152
(1070–1096.54 MHz). In that tile 17.7% of rows are row-flagged and 71.9% of
cross cells are flagged; antennas 25, 33 and 37 have no all-four-supported cell.
Row `SIGMA` is 1 throughout. `WEIGHT_SPECTRUM` varies (median about 0.149, range
0.095–1.0), which suggests processing-derived rather than raw correlator weights.

## Status and open questions

This is the first public MeerKAT L-band observation found with positive
cross-hand weights, a polarisation-angle calibrator, a flux/bandpass calibrator
and a long gain-calibrator track from one observation. It is also a second,
independent observation alongside ESO137. That makes it the best current
candidate for the summary's first gate. Nothing about calibration, flagging,
transfer or image quality is measured.

Not established, and required before use:

- **Licence and citation.** No registry entry or documentation was found for the
  LUNO stores; usage and redistribution terms must come from the publisher.
- **Provenance.** Whether the weights, flags and `MODEL_DATA` are native or the
  output of processing (the `_QCAL` column implies QuartiCal was run). The 923
  HISTORY rows should answer this through a bounded inert-text extraction like
  the [ESO137 provenance recovery](flagging-next-provenance-verification.md),
  without unpickling.
- **Gain-bin support.** Measure TRAIN identifiability on the 1934−638 and
  1830−211 scans before freezing any protocol, as in the
  [gain-support survey](flagging-next-gain-support.md).

## Reproduce

Anonymous HTTPS GETs into a fresh directory (50 objects, 58,843,034 bytes),
then an offline decode in the pinned image that refuses filters and object
dtypes:

```sh
bash tools/flagging/fetch-luno-probe.sh outputs/fresh-luno-probe
docker run --rm --platform linux/amd64 --network none --read-only --tmpfs /tmp \
  -v "$PWD/outputs/fresh-luno-probe:/probe:ro" \
  -v "$PWD/examples/decode_luno_probe.py:/decode_luno_probe.py:ro" \
  --entrypoint python rang-flagging:local -I /decode_luno_probe.py /probe
```

Compare the receipt with the archived object hashes; the bucket is not
versioned, so a changed hash means the publisher changed the data.
