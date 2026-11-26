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

## Known RFI: MeerKAT L band

```yaml
flag:
  known_rfi: meerkat_l   # default none
```

- **Where it runs:** before the strategy, and again after it, OR-ed into FLAG on the stage's fields.
- **All baselines:** 850-900 MHz, 1658-1800 MHz and the Galactic HI line (1419.8-1421.3 MHz).
- **Baselines shorter than 600 m:** 15 satellite and transmitter bands (GSM, GPS, GLONASS, Galileo,
  Iridium, Inmarsat and others).
- **Source of the lists:** oxkat, from SARAO's MeerKAT Cookbook ({gh}`python/rang/meerkat.py`).
- **Channel selection:** as CASA `flagdata` selects `spw='*:<range>'`.
- **Refusals:** the stage refuses data that is not MeerKAT or not L band (issue #59,
  {gh}`research/solver-flags.md`).

:::{note}
The preset adds 6.1 % of E2-N's cells. Do not pair it with a cut of CARACal's first pass. On A1, that
cut's first three steps alone flagged 53 % of cells, against 29 % for the full strategy
({gh}`research/solver-flags.md`).
:::

## Flags at the gain solve

```yaml
calibrate:
  solver_flags:
    mode: quartical   # off (default) | quartical | rang
    terms: [G, B]
    rounds: 2
    guard: 0.8
```

**Experimental; measured null.** It reproduces QuartiCal 0.2.7's `mad_flags` cell for cell. On
E2-N, after the preset and a mild raw strategy, it lowered J1744-5144's flux by 1.0 % and raised the
calibrators' noise ({gh}`research/solver-flags.md`). A G solve with the bandpass not yet applied
(the primary G) flags on a residual that still holds the band's shape.

After each G (G, Gsec) or B solve, the residual of the unaveraged cells is flagged per solution
interval:

- **`quartical`:** QuartiCal 0.2.7's `mad_flags` rule;
- **`rang`:** the antenna-factorised rule of `flag.residual`.

The new flags are written to FLAG and the term is solved again. A baseline is never pushed past
`guard` flagged within an interval. The stage fails if a re-solve flags more of the term's solutions
than `tripwire` allows. It needs `data.processes: 1`.

What was measured, and against what, is in {gh}`research/solver-flags.md`.

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
