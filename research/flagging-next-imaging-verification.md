# Independent matched dirty-image verification

The corrected03 run passed419/419 independent checks. It is
`outputs/tv-next-imaging-20260924-03/result.json`, SHA256
`1dd4f4617483296635307c6f3fd32d05165e88788e7f10410969af61c7932838`.
Source checkpoint: `e3cab8c5e25899b17c3670cce77ff7517fcad635`.
The [full strict audit](results/gain-tv-next-imaging-audit.json) embeds the exact
audit program (SHA256
`a458021818301f95f59e64868bf36c57ae2a1c668ac36891d8b87db3955f6b4d`)
and all predicates, including separately retained prior failures. The pinned
Linux/amd64 image was
`sha256:5da4c1b754ddc3a43f57b5cb7f4d8b7bf9aa182c53eeac5c4ac0fb6208ac1d22`;
audit execution was offline with measured inputs read-only and only a new small
private audit namespace writable. No WSClean inversion, QuartiCal solve,
acquisition or measured-table/source write was performed by this audit.

## Preserved negative results

The first master attempt failed command parsing (`Unknown parameter: datacolumn`)
before any FITS/inversion. All23 independent boundary-preservation checks passed;
the failed log SHA256 is
`7b7a887a3897eeea9807506156e94fd81ddec68f64be1e6c352de616e048d738`.

The02 retry completed15 inversions and passed409 numerical/preservation checks,
but failed two independently checked spectral-provenance predicates. Its saved
unit templates already contained their spectrum, then received the spectral
factor again. Expected indices−0.5/−0.9 became−1.0/−1.8; native XX/YY unit errors
were0.104449/0.173293Jy, not approximately6e-8Jy casting roundoff. The archive
retains the complete original409-check program/results and a separate semantic
oracle reading the OLD native checkpoints directly, not replaying the new helper.
Thus02 is409/411 with two semantic failures, never a certified matched-family win.
Its raw result SHA256 is
`aa6d6f89eb47d9dc7f19af7dd8e27a4170deb27fa1d99eaae200d4c82d2adce4`.

The03 fix removed only the duplicate spectral factor. Physical settings,15 jobs,
weights/support, budgets and closure thresholds stayed frozen. There were30
successful inversions across02/03, one initial parse failure and zero imaging
QuartiCal re-solves. Total audit accounting is853 predicates:419 corrected03
passes,23 initial preservation passes,409 numerical02 passes and two retained
semantic failures. Reporting only409PASS would have hidden the scientific bug.

## Independent checks and scope

The audit independently reconstructs the intrinsic Fourier phase, Gaussian shape
and ONE spectral factor from actual UVW/frequencies and fixed source parameters,
then verifies the archived source arrays and native unit XX/YY checkpoints.
It checks actual correlation orderXX,XY,YX,YY, telescopeMeerKAT and L-band
spectral coordinates. Inverse-Jones algebra uses independently ordered linear
solves rather than production matrix inverses; casts are bounded against the
recorded errors, not repaired by changing tolerance.

All15 frozen commands/parser receipts, finite512² dirty/PSF FITS hashes,
8arcsec SIN WCS, support/counts and originalFLAG/FLAG_ROW protection were checked.
Exclusive previous CORRECTED_DATA/FLAG/schema backups follow the actual role-
specific write sequence. Original and copied DATA/model/WEIGHT/WEIGHT_SPECTRUM/
SIGMA/SIGMA_SPECTRUM match, source trees and original-copy digests survive,
whole-MS backups stay unchanged, and no MODEL_DATA was unexpectedly added.
Known-family fits and fixed offsource RMS/std were reconstructed from FITS.

The image configuration guards the five imported Python module files and the
pinned executable/package manifest; wrapper/recipe provenance is bound to the
checked source checkpoint and actual saved command vectors, not falsely claimed
as part of that five-module runtime receipt. Native weights are unchanged proxies,
not propagated optimal post-Jones noise covariance. Dirty analysis uses only
`-dirty.fits`/`-psf.fits`; WSClean also writes a default `-image.fits` at niter0,
with no CLEAN components/deconvolution. Its filename is not blind CLEAN recovery.

## Measured conditional response

FixedG0 reference coefficients are59.99999623/119.99999037mJy; rank2, condition
1.99561 and unweighted pixel-MSE proxy `3.45639e-17`. This restores semantic
closure to the nominal60/120mJy injection after actual native rounding; the
invalid02 basis had61.66336/118.96975mJy and MSE `2.04150e-6` instead.

| Saved gain control / paired term | Compact coefficient, mJy | Extended coefficient, mJy | Compact / extended relative to fixedG0 |
|---|---:|---:|---:|
| Omitted-sky total | 29.50019 | 93.08026 | 49.167% / 77.567% |
| Omitted-sky direct | 60.11873 | 119.98576 | 100.198% / 99.988% |
| Omitted-sky adaptation | −30.61855 | −26.90548 | −51.031% / −22.421% |
| Complete-sky diagnostic total | 59.81493 | 118.37968 | 99.692% / 98.650% |
| Complete-sky diagnostic direct | 60.00212 | 120.00211 | 100.004% / 100.002% |
| Complete-sky diagnostic adaptation | −0.18719 | −1.62242 | −0.312% / −1.352% |

Actual image total−direct−adaptation closure maxima are `3.53903e-8` and
`3.80969e-8`Jy/beam, within the premeasurement `1e-6` threshold. Complex128
visibility closure is approximately `1.02e-14`Jy, within `1e-10`. Matched controls
keep all9,169 TEST cells and identical PSFs. FITS fittedPSF BMAJ/BMIN are
0.249046110330294/0.0803389183755054degrees:14.94277′×4.82034′, PA97.28504°.

The separately evaluated CARACAL mild control keeps9,169 cells/identicalPSF and
dirty offsource RMS3.27997953Jy/beam versus3.27902514 for no-change; no sensitivity
win. Rejected firstpass loses1,357 TEST cells (7,812 remain), changes PSF by
0.07469787 maximum absolute, and has fittedPSF15.22875′×4.79572′. Its slightly
lower dirty RMS3.26404200 cannot be called a matched quality winner: mask is
overbudget, support/PSF changed and its native flagger saw holdout features.

## Scientific interpretation

The paired known-family image coefficients support the mechanism that gain
adaptation can absorb genuine model-omitted signal; direct transfer alone is near
one. The complete-sky control uses injection truth and is a calibration diagnostic,
not a deployable policy. Image-native/pixel-proxy and previous propagated-weight
visibility fits use different operators; their percentage differences are not
independent replications or contradictions.

This is one four-antenna112s sparse pointing scan, dirty images with a broad
ellipticalPSF, fixed source positions/width/spectra, shared original noisy DATA
and saved empiricalDI gains, no beam/DDE/independent noise. Coefficients are
source-specific conditional template responses, not blind astrophysical flux,
extent, confidence intervals, independent-observation transfer, a validated
flagging/imaging pipeline, or SOTA accuracy/runtime novelty. Dirty offsource RMS
includes sky/sidelobes rather than independent thermal noise. No image/TEST
values or source truth selected a flag policy or changed the TV objective.
