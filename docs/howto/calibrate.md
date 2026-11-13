# Calibrate: CARACal's terms as a rang-core configuration

`rang-core calibrate` solves the terms of `calibrate.primary`,
`calibrate.secondary` and `calibrate.polcal` in order and writes one CASA
calibration table per term into `<run>/calibrate/<name>/`; `rang-core apply`
writes CORRECTED_DATA from them. The ports follow CASA's `gaincal`,
`bandpass`, `fluxscale`, `polcal` and `applycal` and are gated on CASA's
tables ({gh}`research/c2e-calibrate.md`, {gh}`research/c6w-polwire.md`).

## Terms

| Type | Solves | Where | Notes |
| --- | --- | --- | --- |
| `K` | antenna delay | primary | K offsets are not written to the table; G absorbs them ({doc}`../limits`) |
| `G` | complex gain (`calmode: ap` or `p`) | primary, secondary | |
| `B` | bandpass | primary | `fillgaps` (CARACal: 70), `combine: scan` |
| `A` | flags the corrected calibrator with a Tricolour `strategy` | secondary | CARACal's autoflag step |
| `F` | flux scale: the gain calibrator's G rescaled to the flux calibrator's scale, as `fluxscale` | secondary | `smodel: [1, 0, 0, 0]` |
| `Gpol` | gain on the polarised calibrator | polcal, `xcal` | |
| `KCROSS` | X–Y delay | polcal, `xcal` | `estimator: casa` (default) or `refined` |
| `Xf` | X–Y phase per channel | polcal, `xcal` | |
| `Df` | leakage per channel | polcal, `field: [fcal]` | `clip` (default CARACal's [−0.6, 0.6]) |
| `complex` | QuartiCal's full-Jones term into a QuartiCal store | primary | not mixed with the CASA terms; never transferred to a target |
| `Sp`, `Sa`, `Sd` | phase, amplitude, delay | `selfcal.terms` | one per round, the last repeating |

Every term takes `solint` (`inf`, `int`, N integrations or `Ns`), `combine`,
`preapply` (earlier terms by name) with one `interp` (`linear`, `nearest`) and
optionally one `gainfield` (a field, `nearest` or empty) per pre-applied term.
`refant`, `uvrange`, `minsnr` and `minblperant` override the section's.

## The 1GC chain in Stokes I

The quickstart's configuration ({gh}`examples/ms-to-image/config.yaml`):

```yaml
calibrate:
  model: {source: setjy, standard: Stevens-Reynolds 2016}   # MODEL_DATA on fcal
  refant: m000            # null or auto: CARACal's choice
  uvrange: ">150"
  primary:
    field: [fcal]
    terms:
      - {type: K, name: K, solint: inf}
      - {type: G, name: G, solint: inf, calmode: ap, preapply: [K], interp: [linear]}
      - {type: B, name: B, solint: inf, combine: scan, fillgaps: 70,
         preapply: [K, G], interp: [linear, linear]}
  secondary:
    field: [gcal]
    terms:
      - {type: G, name: Gsec, solint: inf, calmode: ap, preapply: [K, B],
         interp: [linear, linear]}
      - {type: F, name: F, solint: inf, calmode: ap, smodel: [1, 0, 0, 0],
         preapply: [K, B], interp: [linear, linear]}
apply:
  calwt: false
  targets:
    - field: [fcal]
      tables: [K, G, B]
      interp: [linear, linear, linear]
    - field: [gcal, target]
      tables: [K, F, B]
      gainfield: [J1939-6342, nearest, J1939-6342]
      interp: [linear, linear, linear]
```

`calibrate.model.source` also takes `manual` (Stokes I, Q, U, V, spectral
index, polarisation fraction, angle and rotation measure at a reference
frequency), `lsm` (a Tigger sky model) or `column` (an existing model column).

## Full polarisation

CARACal's polarisation strategy 1 (`xcal_model_fcal_leak`): Gpol, KCROSS and
Xf on the polarisation-angle calibrator against CARACal's NRAO model, Df on
the flux calibrator, P applied with `apply.parang: true`. The configuration
frozen for E2-B on LUNO, scans 17–20, is a complete example
({gh}`research/results/e2-acceptance-scripts/e2b.yaml`); its polcal section:

```yaml
  polcal:
    field: [xcal]
    model: {source: nrao, name: 3C286}
    feed_angle_rotation: -90
    extendflags: true
    terms:
      - {type: Gpol, name: Gpol, solint: 60s, calmode: p, parang: true,
         preapply: [K, G, B], interp: [linear, linear, linear]}
      - {type: KCROSS, name: Kcross, solint: inf, parang: true,
         preapply: [K, G, B, Gpol], interp: [linear, linear, linear, linear]}
      - {type: Xf, name: Xf, solint: inf, combine: scan, parang: true,
         preapply: [K, G, B, Gpol, Kcross], interp: [linear, linear, linear, linear, nearest]}
      - {type: Df, name: Df, field: [fcal], solint: inf, combine: scan, parang: true,
         clip: [-0.6, 0.6], preapply: [K, G, B, Kcross, Xf],
         interp: [linear, linear, linear, nearest, nearest]}
```

```{warning}
- **Reference antenna.** Strategy 1 is kept with its limit: on A1's truth every
  reference antenna but m000 makes the X–Y phase drift 13–22° rms
  ({gh}`research/e2-acceptance.md`).
- **Parallactic angle in memory only.** `feed_angle_rotation` sets the
  receptor angle used for P in memory; FEED is not rewritten, so CASA applying
  `parang=True` to a rang-calibrated MS whose FEED holds 0 applies a different P
  ({gh}`research/c6w-polwire.md`, section 7).
- **Absolute polarisation angle** is under investigation. Do not take χ from
  rang as settled.
```

Joined IQUV images: `image.pol: IQUV`, `image.join_polarizations: true`;
model writing, multiscale and self-calibration are refused for polarisations
other than I ({gh}`research/g9-stokes.md`).

## Memory and pre-averaging

Each solve reads its field in chunks of whole solution intervals within
`data.memory_limit_gb` (8 GiB by default); a term is refused only when one
solution interval, or one channel of one, does not fit
({gh}`research/w3b-chainchunks.md`). Without pre-averaging, CARACal's solution
intervals need 145–333 GiB at 4096 channels ({gh}`research/finish-plan.md`,
item 33): `calibrate.average_time: true` (CASA's time
pre-averaging, off by default) brings them within it, and
`calibrate.average_freq: true` adds CASA's frequency pre-averaging for G, F
and Gpol. Both differ from CubiCal's estimator
({gh}`research/e2-acceptance.md`, {gh}`research/e2-average-freq.md`). The
polarisation solves average within one scan and 5° of parallactic angle, so
an Xf with `combine: scan` over several 3C 286 scans keeps its signal
({gh}`research/xf-avg-fix.md`).

## Self-calibration

`rang-core selfcal` runs CARACal's rounds: image, predict MODEL_DATA, solve one
term, apply; a final image follows. Defaults: two rounds, `Sp` then `Sa`,
solving `CORRECTED_1GC` (a copy of apply's output) into CORRECTED_DATA, gains
clipped to [0.5, 2.0]. Per-image `clean_cutoff`, `cleanmask_method` and
`cleanmask_thr` follow CARACal ({gh}`research/c5b-selfcal-masks.md`).

```{note}
On simulated truth the loop does not meet its limits: the CLEAN model absorbs
part of the gain error, and CARACal's masks do not lift it
({gh}`research/c5-selfcal.md`, {gh}`research/c5b-selfcal-masks.md`). Each
round's solve itself equals QuartiCal's on the same MODEL_DATA.
```

## Refused for now

`solnorm: true`, `calmode: a`, `gainfield` on pre-applied tables, `complex`
mixed with K, G, B, A or F; `preavg` on Xf and Df is not ported. `rang-core config check
--all CONFIG` lists everything refused.
