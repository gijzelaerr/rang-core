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
numeric pilot inspection, native-MS conversion and scientific transfer are
pending at this acquisition checkpoint. No imaging/flux/SOTA result is claimed.
