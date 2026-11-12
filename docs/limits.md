# Known limits

What rang-core does not do, and where it is known to differ from the tools it
was checked against. Each item links the report that measured or decided it
(owner decisions: {gh}`research/finish-plan.md` section 7). No novelty is
claimed: rang-core is checked for parity with CASA, QuartiCal, Tricolour and
WSClean, not shown to beat them.

```{important}
**Placeholder, to be filled from tasks E2 and E3** ({gh}`research/finish-plan.md`;
both are running). This page will add the acceptance gates as reported on
E2-A (ESO 137-006, Stokes I) and E2-B (LUNO, full polarisation), and the
comparison with CARACal's shipped MeerKAT strategy (image quality, flux,
wall time, memory), whatever the outcome.
```

## Scope

- **MeerKAT L band only.** UHF and S band are not supported. Data from other
  telescopes runs with a warning, untested ({gh}`research/meerkat-scope.md`).
- **Not yet tested on native MeerKAT data.** The acceptance rests on simulated
  truth (A1, E1), ESO 137-006 (a Measurement Set with raw phases, Stokes I)
  and LUNO (processed: pre-phased DATA, processed flags and weights; full
  polarisation), so the polarisation claim rests on processed data plus
  simulation. A native observation (E2-N) stays open
  ({gh}`research/a0-acceptance.md`).
- **No direction-dependent calibration** and no facets.
- **No learned flagger.** `rang-core flag` runs the Tricolour port only
  ({gh}`research/f3-flagger.md`).
- **GPU paths need a source build** with the core's `gpu` feature; the wheels
  are CPU only ({doc}`installation`).

## Flagging

- The Tricolour port differs from Tricolour on 530 cells of A1 (413 of them
  from the port's float64 transform against Tricolour's complex64 pocketfft,
  about 2 ulp at a threshold); accepted, not ported exactly
  ({gh}`research/e2-acceptance.md`).

## Calibration

- **Reference antenna.** CARACal's polarisation strategy 1 is kept with its
  limit: on A1's truth every reference antenna but m000 makes the X-Y phase
  drift 13-22° rms ({gh}`research/e2-acceptance.md`).
- **K offsets are not written to the K table**; G absorbs them, so a K table
  applied alone lacks them ({gh}`research/c2c-bandpass.md`). The delay error
  estimate is low by a factor 1.5-2 ({gh}`research/c2b-delay.md`).
- **Solution TIME** differs from CASA's by up to 0.054 s (0.41 s with
  `combine`); it is reported, not gated, until CASA's centroid weighting is
  ported ({gh}`research/c2a-gain.md`).
- **Parallactic angle in memory only.** `feed_angle_rotation` is applied in
  memory and FEED is not rewritten: CASA reading a rang-calibrated MS whose
  FEED holds 0 applies a different P with `parang=True`
  ({gh}`research/c6w-polwire.md` section 7).
- **Pre-averaging**, off by default. `calibrate.average_time` and
  `selfcal.average_time` average in time before a solve, as CASA does, which
  differs from CubiCal's estimator; `calibrate.average_freq` is CASA's
  frequency pre-averaging of the G, Gsec, F and Gpol solves (K, B, KCROSS,
  Xf, Df and selfcal unchanged; {gh}`research/e2-average-freq.md`)
  ({gh}`research/e2-acceptance.md`).
- Options refused for now: `solnorm: true`, `calmode: a`, `gainfield` on
  pre-applied tables, `complex` terms mixed with K, G, B, A, F; complex gains
  are never transferred to a target (`rang-core config check --all CONFIG`
  lists what is refused).

## Self-calibration

- **Model absorption.** On simulated truth the loop does not meet its truth
  limits: the model absorbs part of the gain error, and masks do not lift it.
  Accepted for 0.2.0 ({gh}`research/c5-selfcal.md`,
  {gh}`research/c5b-selfcal-masks.md`).
- Model writing, multiscale and self-calibration with Stokes Q, U or V are
  refused ({gh}`research/g9-stokes.md`).

## Imaging (GeMClean)

- **The unexplained floor.** On the real pilot the residual floor is 40-60 ×
  thermal in every imager tried, WSClean included, for a reason not found
  ({gh}`research/clean-overview.md`).
- **Memory** is 2.0-2.4 × WSClean's on the pilot at 512 channels
  ({gh}`research/g7-defaults.md`).
- **Images are not byte-identical across platforms**: native Windows and
  Linux builds differ in every file, and no tolerance across them has been
  measured ({gh}`research/g4-masks.md`).
- Refused options include `-fit-spectral-log-pol`, squared channel joining,
  XY, YX and circular polarisations and `-link-polarizations`
  ({gh}`research/g3-spectral.md`, {gh}`research/g9-stokes.md`).
- `gemclean` writes the model column by default, as WSClean does; pass
  `-no-update-model-required` when imaging a shared MS. `rang-core image`
  writes MODEL_DATA only with `image.write_model: true`
  ({gh}`research/g6-predict.md`).

## Data safety and platforms

- **Table lock on Linux only.** On Windows and macOS nothing stops a second
  writer to the same MS; `rang-core` refuses a second command on the same run
  directory ({doc}`concepts/ingest`).
- **Memory limit.** `data.memory_limit_gb` is 8 GiB by default; flag,
  calibrate and apply read in chunks within it. Channel-chunked solves on
  whole-array data are slow: 30-52 min per arm in W3b, before the channel
  sliced read, which is 2.1-2.2 × faster on the polarisation sets
  ({gh}`research/w3b-chainchunks.md`, {gh}`research/sliced-read.md`).
