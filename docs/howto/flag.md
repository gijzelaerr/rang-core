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

## What is not there

- No learned flagger: F1, F2 and F3 stopped or failed as frozen and none was
  proposed for `rang-core flag` ({gh}`research/f3-flagger.md`,
  {doc}`../research/index`, section 7).
- No AOFlagger strategy runner. The SumThreshold kernel agrees with
  AOFlagger's at kernel level and differs at stage level
  ({gh}`research/a-flag-aoflagger.md`).
- Gain-TV-guided flagging is closed as null
  ({gh}`research/flagging-verdict.md`).
