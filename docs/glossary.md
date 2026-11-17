# Glossary

Terms as rang and its notes use them. Where a term names a stage or a table,
the page in brackets is where it is defined in full.

```{glossary}
A1
  rang's simulated MeerKAT L-band observation, written from seeds with its
  true instrument and sky saved beside it; `small` has 16 antennas and 64
  channels, `full` 64 antennas and 256 channels ({gh}`research/a1-simtruth.md`).

applying
  Writing calibrated visibilities, CORRECTED_DATA, from DATA and the
  calibration tables, as CASA's `applycal` does (`rang-core apply`).

bandpass
  B: the per-channel complex response of each antenna's receiver chain,
  solved on the bandpass calibrator.

Briggs
  The robust weighting between natural (robust 2, best sensitivity) and
  uniform (robust −2, best resolution and sidelobes); rang's default is
  Briggs 0.

CARACal
  The MeerKAT pipeline whose shipped strategies rang's chain follows, and
  the state-of-the-art baseline of the v0.2.0 comparison (task E3).

channel
  One frequency bin of the correlator; the public fixture has 4096 across
  L band.

CLEAN
  Deconvolution by repeatedly subtracting a scaled PSF at the brightest
  residual pixel (Högbom 1974); multiscale CLEAN uses extended shapes.

cross-calibration
  Solving the instrument on calibrator fields with known skies and
  transferring the solutions to the target.

D
Df
  Leakage: the fraction of one linear feed's signal seen by the other,
  solved per channel (Df) on an unpolarised calibrator.

dirty image
  The inverse Fourier transform of the weighted, gridded visibilities: the
  sky convolved with the PSF.

flag version
  A saved copy of the FLAG column in `<ms>.flagversions/`, as CASA's
  `flagmanager` writes it; rang saves `rang_original` before its first write.

flagging
  Marking visibilities bad in the FLAG column, so that later stages ignore
  them.

flux calibrator
  A source with a known flux standard, PKS 1934−638 (J1939−6342) at MeerKAT
  L band, which sets the absolute flux scale (role `fcal`).

flux scale
  F: the gain calibrator's amplitudes rescaled to the flux calibrator's
  scale, as CASA's `fluxscale` does.

G
  The complex gain of each antenna and feed, per solution interval; solved
  first on the flux calibrator, then over time on the gain calibrator.

gain calibrator
  A compact source near the target, observed between target scans, that
  tracks the gains in time (role `gcal`).

GeMClean
  rang's reference imager (`gemclean`): WSClean-style options, Högbom minor
  cycles with the exact image-domain value at each step
  ({gh}`research/gemclean.md`).

gridding
  Resampling visibilities onto a regular uv grid so that an FFT gives the
  image; the w-stacking gridder and the wgridder correct for the w term.

integration
  One correlator dump in time (`solint: int` solves per integration).

Jones matrix
  The 2×2 complex matrix of one antenna's response to the two
  polarisations, a product of terms (K, G, B, D, X, P).

K
  The residual delay of each antenna, a phase slope across frequency.

KCROSS
  The delay between the X and Y feeds of the reference antenna, solved on
  the polarisation calibrator.

linear feeds
  Receivers with two orthogonal linear polarisations, X and Y, as on
  MeerKAT; rang refuses circular feeds.

major cycle
  A return to the visibilities: predict the model, subtract it, image the
  residual again.

Measurement Set
MS
  The casacore table format that holds visibilities, flags, weights and
  their metadata, one row per baseline and integration.

minor cycle
  The CLEAN iterations between two major cycles, on the image only.

oracle
  The upstream tool or reference path a port is checked against: Tricolour,
  CASA, QuartiCal, WSClean, ducc0, casacore, katdal.

parallactic angle
  The angle of the sky's north as seen from an alt-azimuth dish; it turns
  through a track, which separates the source's polarisation from the
  instrument's (P).

polarisation-angle calibrator
  A source with a known polarisation angle, 3C 286 or 3C 138 (role `xcal`),
  for KCROSS and Xf.

PSF
  The point-spread function or dirty beam: the image of a point source given
  the uv coverage and weights.

receipt
  The JSON record every `rang-core` call writes (schema `rang.receipt`,
  version 5): command, inputs, environment, commit, and the hashes of what
  it wrote.

reference antenna
  The antenna whose phase is held at zero, fixing the common phase that
  calibration cannot determine (`calibrate.refant`; `auto` is CARACal's
  choice).

restoring beam
  The Gaussian fitted to the PSF's main lobe; the CLEAN components are
  convolved with it in the restored image.

RFI
  Radio-frequency interference: man-made signals in the band.

run directory
  `<ms>.rang-run/`: the state, resolved configuration, tables, images and
  receipts of one chain on one MS.

self-calibration
  Calibration against a model made from the target's own image, in rounds
  (`rang-core selfcal`; terms Sp, Sa, Sd).

solution interval
  The time (and frequency) span over which one solution of a term is fitted
  (`solint`, `freqint`).

SumThreshold
  The flagging algorithm of Offringa et al. (2010): runs of samples whose
  summed amplitude exceeds a threshold that falls with the run's length.

tolerance
  The agreement a port or measurement must reach, written down and frozen
  before the run it judges.

uv plane
  The plane of projected baseline coordinates in wavelengths; each baseline
  samples one track through it as the Earth turns.

visibility
  The averaged correlation of two antennas' voltages, a Fourier component
  of the sky brightness.

Xf
  The per-channel phase between the X and Y feeds, solved on the
  polarisation calibrator.
```
