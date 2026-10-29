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

## Provenance found, 2026-10-29

**How it was found.** ESO137 came from its AWS Open Data registry entry
(`ESO137/` prefix, CC BY 4.0, Ramatsoku et al. 2020, managed by SARAO). LUNO
came from listing the same bucket; the registry entry and its licence cover
only `ESO137/`.

**Measured from the stores' own metadata** (bounded text probe below; string
arrays use the `json2` filter, so they decode as plain JSON with no pickle):

- OBSERVATION `PROJECT` is `20210818-0008` (a MeerKAT schedule-block ID) and
  `OBSERVER` is `B Hugo`, in both the calibrator and target stores.
- FIELD names: `J1331+3030`, `J1939-6342`, `J1833-2103` (calibrators) and
  `Moon` (target). The Moon was 44′, 98′ and 149′ from the target `PHASE_DIR` at
  the start, middle and end of the 2021-08-18 13:31–17:28 UTC track (astropy
  ephemeris). So the single FIELD direction records the Moon's position about
  1.3 h before the first sample, not a tracked phase centre.
- HISTORY: 923 calibrator rows and 124 target rows, all CASA 5.6.0-60 task
  records written 2022-09-10 to 2022-11-02 on `l.ms` and `l_moon.ms`.
  Calibrators: 25 `applycal` runs with `calwt=True` and `applymode="calflag"`
  (gain tables from 1934−638, 3C 286 and the secondary: K, G, B, Df, KX, Xf),
  four `flagdata` runs in `manual` mode (scan 4 with a 1 s quack, and the
  850–900 MHz and 1650–1750 MHz band edges), `setjy` (Perley-Butler 2017,
  J1331+3030 at 18.954 Jy at 856 MHz, writing `MODEL_DATA`) and `clearcal`.
  No QuartiCal, statwt, initweights or split row.
- The S3 store roots were last modified 2024-11-29 14:07 UTC (calibrators) and
  17:04 UTC (target).

**Found in public repositories** (not in the stores):
[africalim/resources](https://github.com/africalim/resources), created
2024-11-29 13:56 UTC for the AfriCalim 2024 calibration and imaging workshop,
runs QuartiCal recipes (`recipes/luno_kgb.yaml`) on exactly these S3 stores. A
commented-out line there lists `output.columns: [CORRECTED_DATA_QCAL,
WEIGHT_SPECTRUM]`, and `luno_fullpol.yaml` points at local copies
`MOON/msdir/l_cal.zarr` and `l_moon.zarr`. The workshop's
[Polcal-Primer](https://github.com/africalim/Polcal-Primer) uses a Moon
polarisation-calibration dataset in UHF. It refers to a larger wide-band L-band
dataset for the Kubernetes exercises and carries a "Data fair use notice": the
data are wholly owned by SARAO, distributed for teaching, subject to the MeerKAT
data policy clause 4.2.2.2, with the full UHF data on request under
`EXT-20220902-BH-01`.

**What this means for rang.** LUNO is a MeerKAT L-band Moon observation
(schedule block 20210818-0008, observer B. Hugo) that was calibrated in CASA in
2022. It was then exported to Zarr and published in November 2024 as AfriCalim
workshop data. Its `FLAG`, `WEIGHT_SPECTRUM` and `MODEL_DATA` should be treated
as processing products, not native values:

- `calwt=True` rescales weights by gain amplitudes, which matches the varying
  0.095–1.0 weights.
- `calflag` and the manual flags add flags.
- `setjy` wrote the model.

`CORRECTED_DATA_QCAL` has no HISTORY row, since QuartiCal does not write
HISTORY. The workshop recipe makes a QuartiCal run likely; whether that run also
overwrote `WEIGHT_SPECTRUM` is unknown. The positive cross-hand weights that
made this candidate attractive are therefore not native evidence, and the
strict native-weight gate is not met. No data, flags or weights were changed.

## Still open

- **Licence and citation.** No licence was found for the LUNO stores. The
  closest statement, the Polcal-Primer notice, covers the workshop's UHF
  teaching data, not this L-band set. It implies SARAO ownership and
  teaching-only intent. Research use and publication need confirmation from
  SARAO or the observer. A question went to the "Hout boys" WhatsApp group on
  2026-10-29 at about 13:06 SAST; no answer has been recorded. Record any reply
  here with who said it and when; chat replies alone do not change data or
  flags.
- **Native data.** Whether `DATA` itself is the raw 4,096-channel, roughly 8 s
  correlator output is not established. Native weights and flags would come from
  the SARAO archive (schedule block 20210818-0008), not from these stores.
- **Gain-bin support.** Measure TRAIN identifiability on the 1934−638 and
  1830−211 scans before freezing any protocol, as in the
  [gain-support survey](flagging-next-gain-support.md). This is only worth doing
  once the licence and weight questions are settled.

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

The text-metadata probe (60 objects, 27,237 bytes; both stores) decodes the
same way, accepting only `json2` string arrays and unfiltered numeric arrays.
Its archive is [meerkat-luno-provenance.json](results/meerkat-luno-provenance.json).

```sh
bash tools/flagging/fetch-luno-text.sh outputs/fresh-luno-text
docker run --rm --platform linux/amd64 --network none --read-only --tmpfs /tmp \
  -v "$PWD/outputs/fresh-luno-text:/probe:ro" \
  -v "$PWD/examples/decode_luno_text.py:/decode_luno_text.py:ro" \
  --entrypoint python rang-flagging:local -I /decode_luno_text.py /probe
```
