# From voltages to an image, in one page

The chain rang implements, stage by stage, with the notebook that works each
one out in numbers. Terms in bold are in the {doc}`../glossary`.

## The instrument

MeerKAT has 64 dishes of 13.5 m on baselines up to about 8 km; rang
supports its L band, 856–1712 MHz (centre 1284 MHz), with dual **linear
feeds** (X, Y). The correlator multiplies the voltages of every pair of
antennas *p*, *q* and averages over an **integration**, giving four
correlations XX, XY, YX, YY per baseline, time and **channel**: the
**visibilities**. A **Measurement Set** (MS) holds them, one row per
baseline and integration ({doc}`../tutorials/notebooks/i2-visibilities`,
{doc}`../tutorials/notebooks/i3-meerkat-array`).

A visibility is a Fourier component of the sky brightness at the baseline's
projected length in wavelengths, $(u, v, w)$. Earth rotation sweeps each
baseline through the **uv plane**; the sampled points set the **PSF** (the
dirty beam).

## The measurement equation

For antennas *p* and *q*,

$$V_{pq} = J_p \, M_{pq} \, J_q^H + n_{pq},$$

with $M_{pq}$ the sky's model visibilities and $J_p$ a 2×2 **Jones matrix**,
a product of terms each with one physical cause: delay **K**, complex gain
**G**, **bandpass** B, leakage **D**, cross-hand phase **X** and the
**parallactic angle** rotation P. Gains are fixed only up to one common
phase, which a **reference antenna** sets
({doc}`../tutorials/notebooks/i4-measurement-equation`).

## Flagging

Radio-frequency interference (**RFI**) from satellites, aircraft and mobile
networks is bright and narrow in time or frequency. **Flagging** marks those
samples bad (the MS's FLAG column) before calibration. rang runs a port of
Tricolour's **SumThreshold** strategies with static masks of known RFI bands
({doc}`flagging`, {doc}`../tutorials/notebooks/i5-rfi-and-flagging`).

## Calibration

**Cross-calibration** solves the Jones terms on calibrator fields whose sky is
known: a **flux calibrator** (PKS 1934−638 at L band) for K, G and B, a
**gain calibrator** near the target for G over time, the **flux scale** F that
carries the flux calibrator's scale to it, and for polarisation a
**polarisation-angle calibrator** (3C 286 or 3C 138) for KCROSS and Xf, with
Df from the flux calibrator. Each term is solved per **solution interval**
and written as a CASA calibration table; **applying** them to the target
writes CORRECTED_DATA ({doc}`gains`, {doc}`../tutorials/notebooks/i6-calibration`,
{doc}`../tutorials/notebooks/i8-polarisation`).

**Self-calibration** then uses an image of the target itself as the model and
solves again, phase first, then amplitude. On simulated truth rang's loop
does not meet its limits: the model absorbs part of the gain error
({doc}`../limits`).

## Imaging and deconvolution

Weighting (natural, uniform, **Briggs**) and **gridding** turn the
visibilities into a **dirty image**: the sky convolved with the PSF.
**CLEAN** deconvolves it: it finds the brightest residual pixel, subtracts a
scaled PSF there, and repeats (**minor cycles**), returning to the
visibilities for an exact residual now and then (**major cycles**). The
components, convolved with a Gaussian **restoring beam** and added to the
residual, give the restored image. rang's imager is GeMClean
({doc}`imaging`, {doc}`../tutorials/notebooks/i7-imaging-and-deconvolution`).

## Checking the result

Each step is checked against truth (A1, simulated), against the upstream
tool it reimplements (the **oracle**: Tricolour, CASA, QuartiCal, WSClean),
or both. The research notes record how close, against a **tolerance** frozen
before the run, and which gates were not met ({doc}`../howto/check-results`).

## Beyond images

Pulsars and fast transients are averaged away in a long synthesis image.
{doc}`../tutorials/notebooks/i9-time-domain` covers dispersion, dedispersion
and folding; time-series products in rang are scoped, not built
({gh}`research/v1-timeseries-scope.md`).
