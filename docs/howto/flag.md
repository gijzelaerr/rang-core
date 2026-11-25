# Flag: the Tricolour port

`rang-core flag` runs a port of Tricolour 0.2.1's strategies in Rust and
writes FLAG. On four archived controls it reproduced Tricolour flag for flag,
including every intermediate step ({gh}`research/core-d-tricolour.md`); on A1
it differs from Tricolour on 530 cells, accepted ({doc}`../limits`).

## Configure

```yaml
flag:
  strategy: mk_rfi_flagging_calibrator_fields_firstpass.yaml   # required, relative to config.yaml
  fields: [all]          # or roles (fcal, gcal, ...) or FIELD names or ids
  column: DATA
  static_masks: tricolour  # the two masks shipped with Tricolour 0.2.1; or none
  write: replace           # FLAG becomes the strategy's flags; or: OR with the flags present
```

The strategy is a Tricolour YAML: a list of tasks (`flag_nans_zeros`,
`apply_static_mask`, `sum_threshold`, `flag_autos`, `combine_with_input_flags`,
and the rest of Tricolour's set) with their `kwargs`. For MeerKAT calibrators
use CARACal's shipped first pass,
`mk_rfi_flagging_calibrator_fields_firstpass.yaml`.
{gh}`examples/ms-to-image/strategy.yaml` is written for A1 small's 64 wide
channels and is not a recommendation for real data.

A strategy is also what calibrate's `A` term runs on the corrected
calibrators (`strategy` on the term; {doc}`calibrate`).

## Flag versions and restore

Before the first write ever made to an MS, rang-core saves FLAG as the CASA
flag version `rang_original`, then `rang_<stage>_<UTC time>` before each
writing stage, in `<ms>.flagversions/`, as CASA's `flagmanager` writes them.
`rang-core run --force flag` restores the flags saved before the earlier
attempt first. To restore by hand:

```python
from rang.formats import flagversions

print(flagversions.versions("my.ms"))           # [(name, comment), ...]
flagversions.restore("my.ms", "rang_original")
```

or in CASA, `flagmanager(vis="my.ms", mode="restore", versionname="rang_original")`.
There is no `rang-core` command for it yet.

## An MSv4 store

`rang-core flag CONFIG STORE` (and `rang-core run` with `run.stages: [flag]`)
flags an MSv4 processing set (xradio schema 4, Zarr; the `[msv4]` extra) in
place, writing only the values of each partition's flag variable
({gh}`research/msv4-cli.md`, {gh}`research/msv4-flag-write.md`). The flags
equal those the MSv2 command writes, converted by xradio 1.3.1 or
xarray-ms 0.5.14. Its differences from an MS:

- `flag.column` is `DATA`, `CORRECTED_DATA` or `MODEL_DATA` (the data groups
  `base`, `corrected`, `model`); `flag.fields` takes MSv2 field names
  (`J1939-6342`), not ids or roles. xradio 1.3.1 stores a field as
  `<name>_<FIELD_ID>` (`J1939-6342_0`); that stored name also works, and
  `flag/summary.json` reports each group's MSv2 `field`, its `field_id` and
  the `store_field`. xarray-ms keeps the MSv2 name and no id (`field_id`
  null). `data.scans` matches the scan names;
- the run directory is `<store>.rang-run`, as for an MS;
- flag versions go to `<store>.flagversions/`, named as for an MS
  (`rang_original`, `rang_flag_<UTC time>`), each a byte copy of every
  partition's flag variable. CASA's `flagmanager` cannot read them:

```python
from rang import msv4_flags

print(msv4_flags.versions("my.ps.zarr"))         # [(name, comment), ...]
msv4_flags.restore_flags("my.ps.zarr", "rang_original")
```

- after a write that was killed, the next run from another run directory
  is refused until you restore (the message names the call); a rerun from
  the same run directory restores its own version first, as for an MS;
- only the flag stage: calibrate, apply, image and selfcal refuse a store
  until the weight each data group takes is settled
  ({gh}`research/msv4-interop.md`, M5). `FLAG_ROW` is lost in conversion: OR
  it into `FLAG` before converting.

## What is not there

- No learned flagger: F1 to F5 stopped or failed as frozen, and none ships
  ({gh}`research/f3-flagger.md`, {gh}`research/f5-flagger.md`,
  {doc}`../research/index`, section 7). `flag.learned` accepts a weights file
  of your own under the contract of {doc}`../learned`.
- No AOFlagger strategy runner. The SumThreshold kernel agrees with
  AOFlagger's at kernel level and differs at stage level
  ({gh}`research/a-flag-aoflagger.md`).
- Gain-TV-guided flagging is closed as null
  ({gh}`research/flagging-verdict.md`).
