# Known limits

What rang-core does not do, and where it is known to differ from the tools it
was checked against. Each item links the report that measured or decided it
(owner decisions: {gh}`research/finish-plan.md` section 7). No novelty is
claimed: rang-core is checked for parity with CASA, QuartiCal, Tricolour and
WSClean, not shown to beat them.

```{important}
**Acceptance on real data, as of 2026-11-18** ({gh}`research/v030-readiness.md`).
E2-B (LUNO, full polarisation) and E2-A (ESO 137-006, Stokes I) have reported:
the gates they miss are listed below and in `CHANGELOG.md`
({gh}`research/e2b-misses.md`, {gh}`research/e2-acceptance.md` 9.13). E2-A is
not passed as frozen; its gate 3b is a limitation with its cause
({gh}`research/e2a-3b-k.md`). E3 (CARACal's shipped MeerKAT strategy on the
same data) has measured E2-B (CARACal 6,926 s against rang 6,195 s; branch
`e3-caracal`) and was still running on E2-A at the release (a later release reports it). E2-N (native data, issue #7) is not met as frozen: 17 of 25 rows
({gh}`research/e2n-native.md`). Absolute polarisation angle is stated as a
limit, not solved (below).
```

## Scope

- **MeerKAT L band only.** UHF and S band are not validated: a stage given
  channels outside 856-1712 MHz runs with one warning that names this page and
  the band it detected. PKS 0408−65 has a flux model (setjy standard `caracal`,
  CARACal's 2016 cubic, valid from 843 MHz, so it refuses most of UHF; there
  `model.source: manual` with `rang.fluxstd.CARACAL_0408` is what CARACal
  gives CASA), but no UHF track has been calibrated yet
  ({gh}`research/uhf-11.md`). Data from other
  telescopes runs with a warning, untested ({gh}`research/meerkat-scope.md`).
- **Native MeerKAT data: tested once, not met as frozen.** E2-N (SARAO
  1735268787, L band, observatory-phased) runs end to end but meets 17 of 25
  rows: 3a (73 flag cells), Xf p95 (2.085° against 2.0°), the K/G/B composites,
  3c, the J1744−5144 χ and the target's compact scatter (13.3 % against 1.5 %)
  miss. The data are observatory-phased, so K, KCROSS and Xf are near-null and
  their real-size solve is untested. The CASA reference flagged 19 of 62
  antennas in its delay solve because the oracle gave CASA the post-`extendflags`
  flags, not those rang solved on, so the K-downstream misses are partly an
  oracle defect; a corrected rerun is in progress. The polarisation claim still rests on LUNO (processed
  data) plus simulation ({gh}`research/e2n-native.md`, issue #7).
- **No direction-dependent calibration** and no facets.
- **No learned flagger.** `rang-core flag` runs the Tricolour port only
  ({gh}`research/f3-flagger.md`). The learned-stage contract is in place
  ({doc}`learned`), but no weights file ships (below).
- **GPU paths need a source build** with the core's `gpu` feature; the wheels
  are CPU only ({doc}`installation`).

## Learned stages (0.4.0)

0.4.0 adds the contract for learned stages ({doc}`learned`): the `learned:`
key, ONNX weights files, refusal and the interpreter. It does not add a
learned stage that you can turn on:

- **No shipped weights.** F5's flagger did not pass its gates: targets
  outcome F, calibrators stopped at the label audit ({gh}`research/f5-flagger.md`,
  issue #40). F6 is still running; unless it passes before the release, every
  `learned:` mode other than `off` needs your own weights file and, without
  passed gates, `force: true`.
- **The learned pilots were null or failed:**
  - warm starts for the gain solver saved only 8-15 % of iterations, so no
    network was tried (DL4a, issue #41, null);
  - an iterated learned deconvolution step put +0.07 to +0.12 of false flux
    against +0.01, on 270 held-out fields (DL4b step 0, issue #42, outcome F).
- **The interpreter runs `Conv` and `Relu` only.** A weights file with any
  other operator is refused at load. Exports must be NCHW, without the
  Transpose, Gather or Identity nodes that torch's exporter can add.
- **Retraining for another configuration** (1k channels, a core-only
  sub-array) has a procedure ({doc}`agents/retrain-a-stage`), dry-run
  on F5 only. Its agent test waits for a stage that passed.
- **`learned:` on `apply`** is a hook with no network.

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
- **K reference antenna (issue #53, {gh}`research/k-refant-53.md`).** CASA's
  K uses the first refant only and never re-references, so it flags an antenna
  without an unflagged baseline to it, and a whole interval where the refant
  has no data. With `refantmode: flex` (the default) rang falls back along the
  refant list (then to the best-connected antenna) per interval, and solves an
  antenna connected to the reference through other baselines. So rang can
  solve K where CASA leaves it flagged; `refantmode: strict` is CASA's rule.
  The table's reference per interval is in the solve's `refant_used`; the K
  table's `ANTENNA2` stays -1, as CASA's.
- **Solution TIME** differs from CASA's by up to 0.054 s (0.41 s with
  `combine`); it is reported, not gated, until CASA's centroid weighting is
  ported ({gh}`research/c2a-gain.md`).
- **Absolute polarisation angle χ is a stated limit, not gated.** On LUNO's
  3C 286 the RM-corrected χ(λ²=0) is 29.4°, 3.6° from 33°, rang equal to CASA
  ({gh}`research/chi-offset.md` section 11). On LUNO's calibrator product use
  FEED's stored receptor angle 0 (leave `feed_angle_rotation` unset): the
  fitted angle is +8.2°, which excludes CARACal strategy 1's −90; −90 suits
  stores holding −90 such as ESO137. On held-out 3C 286
  simulations rang's Xf differs from CASA's by 0.054° (median; issue #33).
  The cause is CASA's `calwt` weighting of the Xf solve; the opt-in
  `calibrate.xf_calwt: true` takes the gap to 0.012° ({gh}`research/xf-gap.md`;
  the other solve types: {gh}`research/calwt-terms.md`). E2-B's 1830−211 χ, transfer χ and 0.30 %
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
  criterion). Of the remaining 379 µJy, 8.6 × thermal, deconvolution depth
  and spectral modelling are confirmed on a held-out scan (D_h 0.201 and
  0.474), and masked Högbom to 0.3 mJy after the round explains 0.717 of the
  held-out excess; the rest is not explained, and no default changes yet
  ({gh}`research/floor-3.md`, {gh}`research/floor-4.md`,
  {gh}`research/floor-5.md`, {gh}`research/floor-6.md`,
  {gh}`research/imaging-floor.md`).
- **Memory** is 2.0-2.4 × WSClean's on the pilot at 512 channels in Stokes I
  ({gh}`research/g7-defaults.md`). Joined IQUV at 2048², 8 channels on E2-B's
  fields peaks at 7.7 GiB on the large fields and 5.7 GiB on J1833−2103:
  `-reorder` is the default with `-join-polarizations`, and writes temporary
  files beside `-name` (or in `-temp-dir`), about 28 GB on the large fields,
  which a killed run leaves behind. `-no-reorder` keeps everything in memory
  (16.5-16.9 GiB on the large fields, about 5-8 % faster)
  ({gh}`research/gemclean-memory.md`, {gh}`research/gemclean-memory2.md`,
  {gh}`research/gemclean-memory3.md`).
- **Multiscale over-estimates compact sources**: a median +9 to +18 µJy on
  sources ≥ 20σ_ap on DF5-O's field, in WSClean 3.7 and GeMClean alike; no
  tested setting fixes it on both fields. Automatic scales come nearest;
  Högbom is unbiased at 7-11 % higher residual RMS
  ({gh}`research/multiscale-flux-fix.md` 8.1).
- **A FITS mask with multiscale confines the component centres, not the
  flux**, as in WSClean 3.7 and radler. The scale shapes of centres inside the
  mask reach outside it. With extended emission outside a mask of small
  islands, the large scales take that emission up: after one major iteration
  on a simulated sky, 2.7 Jy lies outside a 3,394-pixel mask in GeMClean and
  2.9 Jy in WSClean. Cleaned deep (about 1.6σ), both imagers can diverge. When
  nothing may be cleaned outside the mask, use Högbom, cap the scales, or erode
  the mask ({gh}`research/gemclean-ms-mask.md`, issue #35).
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
  calibrate and apply read in chunks within it. A self-calibration Sp or Sa
  solve whose solution interval does not fit (the default `solint: inf` on
  a long scan) is streamed through a scratch file beside the MS, 92 bytes
  per unflagged visibility, with the same solution
  ({gh}`research/selfcal-memory.md`); Sd and the CASA-rule solves still
  refuse such an interval. Channel-chunked solves on
  whole-array data are slow: 30-52 min per arm in W3b, before the channel
  sliced read, which is 2.1-2.2 × faster on the polarisation sets
  ({gh}`research/w3b-chainchunks.md`, {gh}`research/sliced-read.md`).
