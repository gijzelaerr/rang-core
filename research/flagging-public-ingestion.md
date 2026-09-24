# Bounded public visibility ingestion

Acquisition measured2026-09-24; [exact object hashes/ETags](results/meerkat-public-ingestion.json).
The [metadata-only candidate](flagging-public-data.md) now has actual downloaded
numeric DATA, MODEL_DATA, FLAG/FLAG_ROW, coordinates and every present native
WEIGHT/WEIGHT_SPECTRUM/SIGMA/SIGMA_SPECTRUM for two bounded tiles. No received
flag or weight is modified. Offline complete-integration inspection and native-MS
conversion/calibration/transfer remain separate statuses, not inherited success.

## Frozen acquisition

Pinned numeric-reader [module](../python/rangtoy/flagging_public.py). First-row
chunk, channel tile8/native1024:1152 for MAIN_0(scan1) and MAIN_1(scan3), plus
numeric antenna/polarization/field/SPW/descriptor/observation subtables. Remote
metadata is GET-revalidated against the frozen SHA before object HEAD requests;
each GET requires exact recorded ETag/length and receives an exclusive file,
SHA256 and per-object checkpoint. Failures preserve partial files. 75 objects,
884609513bytes/843.63MiB compressed. The initial353MiB estimate was four
large columns from one scan; this two-scan acquisition also keeps native SIGMA
spectra and numeric metadata. No target or CORRECTED_DATA acquired.

```sh
PYTHONPATH=python .venv/bin/python -m rangtoy.flagging_public acquire \
  outputs/fresh-public-acquisition \
  outputs/flagging-next-data-20260923/primary-zmetadata.json
bash tools/flagging/run-public.sh outputs/fresh-public-inspection \
  outputs/fresh-public-acquisition
```

Offline [Stimela2 recipe](../recipes/tv-flagging-public.yaml) uses the pinned
network-disabled container. Numeric-only schemas, decoded-size bounds and Blosc
header/schema equality are checked before decompression. Every object/pickle
filter is refused; fourteen requested string arrays are excluded and reported.
No untrusted pickle opcode is executed. Native-MS conversion cannot invent
telescope/antenna/field strings or silently coerce a non-scalar supplied model.

The inspection selects16 complete integrations using exact61-antenna physical
pair sets; partial/duplicate epochs never enter silently. It keeps native row
and channel indices, received flags and all weight/SIGMA columns in numeric
NPZ products and rechecks acquired-source hashes before/after processing.
Model finiteness/scalar-unpolarized compatibility and eligible cross-correlation
counts are diagnostics, not proof of sky/noise adequacy or full-Jones conditioning.

## First read-only finding and limits

The entire acquired first-scan FLAG chunk(50000×128×4) has80.406796875% flags.
This is not yet the16-integration pilot's occupancy. Retain this negative/high-
occupancy outcome; do not clear flags or silently select a nicer benchmark.
The tile may have limited gain support, which must be audited before solving.
Two scans remain one observation. Publisher/model accuracy, telescope string,
noise-weight conventions and Observatory-versus-processing flag origin remain
unverified. Preserve every received flag regardless of origin.

34 reader/schema/row-layout/disk/path/receipt tests pass. Offline recipe actual dry-run
passes; one read-only FLAG chunk decode passes in the pinned container. Full
numeric pilot inspection was pending at that acquisition checkpoint. Its actual
completed result is below; native-MS conversion/scientific transfer remain
pending. No imaging/flux/SOTA result is claimed.

## Completed numeric pilots and native-weight limitation

[Pilot evidence](results/meerkat-public-pilot.json), completed07:15:55UTC:
both scans retain61antennas and16 complete triangular pair integrations,
30256rows×128channels×4correlations,119.9493s time span. No epoch is selected
by flag fraction. Scan1/3 received FLAG fractions are80.48904556%/80.29701237%,
with1941/1938 FLAG_ROW rows. DATA is finite and supplied MODEL_DATA is finite
scalar/unpolarized; that does not validate its sky accuracy or noise convention.
All raw receipt/object hashes remain unchanged, and no object/pickle is decoded.

The native correlation order is XX/XY/YX/YY. Per scan, positive native
WEIGHT_SPECTRUM counts are `[3872768,0,0,3872768]`: every XY/YX spectral weight
is exactly zero, not nonfinite. There are755614/763051 fully unflagged cross
row/channel cells before the weight criterion, but **zero** eligible cells
under the current strict all-four-correlation-positive-weight protocol.
Native row WEIGHT values are1; substituting them would change the received
noise-weight semantics and is forbidden. No flag is cleared and no nicer
integration is chosen to force acceptance.

This rejects the tiles for the current full-support protocol, not all possible
calibration of the observation. A physically justified partial-correlation
Jones/gauge protocol would require new frozen assumptions and validation.
Safe original string/native-MS conversion also remains unresolved; metadata
must not be invented or unrestricted pickle decoding enabled. No61-antenna
QuartiCal solve or independent-observation transfer has been run. Both scans
belong to the same observation; original Observatory/processing flag origin
remains unverified, so every received flag stays authoritative.
