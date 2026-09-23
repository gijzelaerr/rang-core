# Representative public MeerKAT L-band candidate

Metadata-only inspection on 2026-09-23. No visibility arrays have been
downloaded, calibrated or imaged. Exact source URLs, numeric payload hashes,
array layouts and proposed chunk headers are preserved in
[meerkat-public-primary-metadata.json](results/meerkat-public-primary-metadata.json).

The [SARAO-managed AWS registry](https://registry.opendata.aws/meerkat-eso137-006/)
offers the ESO 137-006 observation and its primary calibrator without AWS
credentials. The registry specifies CC BY 4.0 and requests citation of
[Ramatsoku et al. 2020](https://doi.org/10.1051/0004-6361/202037800).
The [publisher documentation](https://github.com/ratt-ru/ratt-public-open-data-tutorial/blob/8c8c1c97c629b0a13d7c13b4b61b901f77cff88c/documentation.md)
identifies PKS 1934-638 as the primary calibrator and describes CARACAL processing
with CASA, WSClean and CubiCal. Documentation is pinned and hashed; processing
history and the physical accuracy of the supplied MODEL_DATA remain unverified.

## Actual archive facts, not telescope-wide assumptions

Anonymous access succeeded for consolidated Zarr metadata and nine small
numeric chunks. The primary archive contains eight scan groups, scans
1/3/5/7/9/11/13/15. Each group describes 98,332 rows × 4,096 channels × four
correlations, with DATA, MODEL_DATA, CORRECTED_DATA, FLAG, FLAG_ROW and native
WEIGHT_SPECTRUM present.

The first scan's decoded numeric metadata confirms 61 participating antennas,
52 integration times, 1,891 rows per integration including autos, and 407.82748
seconds between first and last centres. The ANTENNA table also has 61 rows;
the registry's statement about the 64-antenna telescope does not establish 64
participants in this archive. Actual channels span 856–1711.791015625 MHz,
spaced by 208,984.375 Hz; bandwidth is 856 MHz. Correlation codes 9/10/11/12
are XX/XY/YX/YY. This is a much more representative calibration candidate than
our four-antenna dedicated pointing fixture, but no transfer success is measured.

## Bounded pilot proposal, not acquisition

Stored visibility chunks are 50,000 rows × 128 channels × four correlations.
Selecting a handful of rows still fetches the whole compressed chunk. For
first-scan row chunk 0 and channel tile 8 (channels 1024:1152,
1070–1096.541015625 MHz), HTTP HEAD—not GET—confirmed:

| Column | Compressed object bytes |
| --- | ---: |
| DATA | 187,044,408 |
| MODEL_DATA | 104,219,968 |
| FLAG | 3,809,921 |
| WEIGHT_SPECTRUM | 75,573,142 |

Those four objects total 370,647,439 bytes, about 353.48 MiB compressed and
512.70 MiB decoded. They are not downloaded. A future pilot could retain 16
complete integrations and all 61 antennas after confirming row layout, then
use a separate scan for frozen-policy transfer. Budget downloads, decoded
arrays, fresh original/work copies, gain products and all backups independently;
available local disk is only about 21 GiB. Do not acquire the terabyte target
sets. The publisher's size table contains an inconsistent GB/TB entry; use
measured object sizes rather than silently correcting the table.

## Ingestion safeguards and remaining checks

Preserve every received FLAG/FLAG_ROW as authoritative lower bounds, regardless
of whether their origin was Observatory or subsequent processing. Never rewind
them to obtain a more attractive benchmark. Audit native weights and source
digests; preserve full subtable consistency and exact channel/row mapping in any
derived Measurement Set. Do not treat CORRECTED_DATA as raw DATA.

Object-string arrays use pickle filters. None were decoded; future ingestion
must refuse unrestricted remote pickle. Numeric chunks inspected here have no
filters and use the pinned container's Blosc decoder. Verify actual flag
occupancy, model finiteness/sky provenance, SNR, gain-bin support and telescope/
field metadata before training. A supplied MODEL_DATA column is not proof of
model adequacy. Separate acquisition, calibration, transfer and image/signal
results; none beyond metadata inspection are implemented or measured here.
