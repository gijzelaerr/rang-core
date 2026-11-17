# Known limits

What rang-core does not do, and where it is known to differ from the tools it
was checked against. Each item links the report that measured or decided it
(owner decisions: {gh}`research/finish-plan.md` section 7). No novelty is
claimed: rang-core is checked for parity with CASA, QuartiCal, Tricolour and
WSClean, not shown to beat them.

```{important}
**Acceptance on real data, as of 2026-11-17** ({gh}`research/v030-readiness.md`).
E2-B (LUNO, full polarisation) and E2-A (ESO 137-006, Stokes I) have reported:
the gates they miss are listed below and in `CHANGELOG.md`
({gh}`research/e2b-misses.md`, {gh}`research/e2-acceptance.md` 9.13). E2-A is
not passed as frozen. E3 (CARACal's shipped MeerKAT strategy on the same data)
has measured E2-B on its branch (`e3-caracal`, not yet merged) and is running
on E2-A; E2-N (native data) is running. Absolute polarisation angle is stated as a
limit, not solved (below).
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
- **Absolute polarisation angle χ is a stated limit, not gated.** On LUNO's
  3C 286 the RM-corrected χ(λ²=0) is 29.4°, 3.6° from 33°, rang equal to CASA
  ({gh}`research/chi-offset.md` section 11). On LUNO's calibrator product use
  FEED's stored receptor angle 0 (leave `feed_angle_rotation` unset): the
  fitted angle is +8.2°, which excludes CARACal strategy 1's −90; −90 suits
  stores holding −90 such as ESO137. On held-out 3C 286
  simulations rang's Xf differs from CASA's by 0.054° (median; issue #33,
  {gh}`research/xf-preavg.md`). E2-B's 1830−211 χ, transfer χ and 0.30 %
  leakage misses are in {gh}`research/e2b-misses.md` sections 5-7.
- **Parallactic angle in memory only.** `feed_angle_rotation` is applied in
  memory and FEED is not rewritten: CASA reading a rang-calibrated MS whose
  FEED holds 0 applies a different P with `parang=True`
  ({gh}`research/c6w-polwire.md` section 7).
- **Pre-averaging**, off by default. `calibrate.average_time` and
  `selfcal.average_time` average in time before a solve, as CASA does, which
  differs from CubiCal's estimator. Gpol, KCROSS, Xf and Df with the
  parallactic angle applied never average across scans or more than 5° of
  it ({gh}`research/xf-avg-fix.md`); `calibrate.average_freq` is CASA's
  frequency pre-averaging of the G, Gsec, F and Gpol solves (K, B, KCROSS,
  Xf, Df and selfcal unchanged; {gh}`research/e2-average-freq.md`)
  ({gh}`research/e2-acceptance.md`). `calibrate.casa_phase_weights` (needs
  `average_freq`) gives the calmode `p` solves (Gpol) CASA's phase-only
  weighting instead of QuartiCal's ({gh}`research/e2b-misses.md` 9.26).
- Options refused for now: `solnorm: true`, `calmode: a`, `gainfield` on
  pre-applied tables, `complex` terms mixed with K, G, B, A, F; complex gains
  are never transferred to a target (`rang-core config check --all CONFIG`
  lists what is refused).

## Self-calibration

- **Model absorption.** On simulated truth the loop does not meet its truth
  limits: the model absorbs part of the gain error, and masks do not lift it.
  Accepted for 0.2.0 ({gh}`research/c5-selfcal.md`,
  {gh}`research/c5b-selfcal-masks.md`).
  More rounds, longer first intervals and a phase-only first round do not
  meet the truth gate either ({gh}`research/selfcal-arms.md`).
- Model writing, multiscale and self-calibration with Stokes Q, U or V are
  refused ({gh}`research/g9-stokes.md`).

## Imaging (GeMClean)

- **The imaging floor, in part unexplained.** On the real pilot the residual
  floor is 40-60 × thermal in every imager tried, WSClean included. Steady
  antenna gains are its main cause: on floor-3's subset one phase-only
  self-calibration round takes the floor from 1,073 to 379 µJy (share 0.88
  under floor-3's standard; floor-4 gives 0.83 under imaging-floor's full
  criterion), and the remaining 379 µJy, 8.6 × thermal, is not explained
  ({gh}`research/floor-3.md`, floor-4 on its branch,
  {gh}`research/imaging-floor.md`).
- **Memory** is 2.0-2.4 × WSClean's on the pilot at 512 channels in Stokes I
  ({gh}`research/g7-defaults.md`). Joined IQUV at 2048², 8 channels on E2-B's
  fields peaks by default at 15.9-16.5 GiB on the large fields (8.2-8.4 ×
  WSClean's) and 8.4 GiB on J1833−2103 (6.3 ×); with `-reorder`, 9.1 GiB
  (4.7 ×) and 7.2 GiB (5.4 ×), with about 28 GB of temporary files
  ({gh}`research/gemclean-memory.md`, {gh}`research/gemclean-memory2.md`).
- **Multiscale over-estimates compact sources**: a median +9 to +18 µJy on
  sources ≥ 20σ_ap on DF5-O's field, in WSClean 3.7 and GeMClean alike; no
  tested setting fixes it on both fields. Automatic scales come nearest;
  Högbom is unbiased at 7-11 % higher residual RMS
  ({gh}`research/multiscale-flux-fix.md` 8.1).
- **Joined polarisations peak on the linear sum**, as WSClean 3.7 and radler
  do: with `-pol QU -join-polarizations`, components whose Q and U cancel are
  not cleaned ({gh}`research/g9-stokes.md`, {gh}`research/v030-readiness.md`
  section 4).
- **Cleaned images against WSClean (gate 3c)**: compact-source scatter 1.18 %
  on E2-B with the mask (bound 1 %), and 3.6 % on E2-A, where 512- against
  4,096-channel smearing lowers the ratios with radius
  ({gh}`research/e2b-misses.md` 9.29, {gh}`research/e2-acceptance.md` 9.14).
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

- **Table lock on Linux and Windows only.** Linux takes casacore's `fcntl`
  lock, Windows a `LockFileEx` lock; on macOS nothing stops a second writer to
  the same MS, and on Windows a casacore process inside WSL does not see rang's
  lock ({gh}`research/ms-lock-windows.md`). `rang-core` refuses a second command
  on the same run directory on every platform ({doc}`concepts/ingest`).
- **Memory limit.** `data.memory_limit_gb` is 8 GiB by default; flag,
  calibrate and apply read in chunks within it. Channel-chunked solves on
  whole-array data are slow: 30-52 min per arm in W3b, before the channel
  sliced read, which is 2.1-2.2 × faster on the polarisation sets
  ({gh}`research/w3b-chainchunks.md`, {gh}`research/sliced-read.md`).
