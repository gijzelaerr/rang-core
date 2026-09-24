# Frozen dirty-image calibration-response verification

Proposed/implemented2026-09-24; first real launch failed before producing FITS,
and the15-image02 retry exposed a semantic template error (retained below).
Root approved all settings,15 jobs and tolerances before results. This follows the measured
[visibility-response controls](flagging-response.md), not a flag-policy retune.

WSClean is absent from the recovered102767... solver image. The official
[Debian13 package](https://packages.debian.org/trixie/wsclean) is3.6-1. A small
child of NEW`rang-flagging-next:local` adds only that package and its exact signed
snapshot dependency closure; the old solver image remains untouched. Snapshot:
`https://snapshot.debian.org/archive/debian/20250901T000000Z/`, trixie/main/amd64.
Existing Debian keyring verifies metadata; only snapshot expiry checking is
disabled, never signature checking. No preexisting package upgrade, downgrade
or removal is allowed. The full plan's advertised new-deb bytes must be≤256MiB
BEFORE acquisition, actual sizes/SHA256 must match signed metadata, and package
list/WSClean binary/final image receipts freeze before measurement. Root owns
availability verification/build/launch; this module never acquires dependencies.

## Fixed measurement family

512×512 pixels,8arcsec,Briggs robustness0.5,StokesI,field0,channels1024:3072,
one CPU,0.5GiB WSClean memory hint,64w-layers, no small-inversion/reordering/model
updates, and niter0. Explicit`-gridder wstacking` matters: WSClean3.6 defaults to
[wgridder](https://wsclean.readthedocs.io/en/v3.6/wgridding.html), which ignores
w-layer settings. All jobs use exactly one command family. Analysis uses dirty
and PSF FITS only, with no CLEAN components/deconvolution or fitted spectral
indices. WSClean also emits a default `-image.fits` product at niter0; its filename
is not evidence of CLEAN recovery. Observed maximum imaged projectedUV73.857m
gives nominal finest scale558.99arcsec: broad sparsePSF, not precision morphology.

The first launch retained a version-compatibility failure: WSClean3.6 rejected
legacy`-datacolumn`, with0 completed inversions/FITS. Failed log SHA256 is
`7b7a887a3897eeea9807506156e94fd81ddec68f64be1e6c352de616e048d738`.
An independent23/23-check read-only boundary audit confirmed original DATA,
models, FLAG/FLAG_ROW, native weights/SIGMA and exclusive backups survived.
The old failed master output remains untouched. Before a separate fresh retry
at`outputs/tv-next-imaging-20260924-02`, fix exactly four CLI spellings:
`-data-column`, `-wstack-nwlayers`, `-abs-mem`, `-no-min-grid-resolution`.
The last disables Nyquist-resolution inversion/upscaling, preserving the frozen
full512² inversion. No physical setting/tolerance/geometry/job/budget changes.
The actual pinned binary's complete `-dry-run` parser preflight must succeed
BEFORE any MS copy/CORRECTED_DATA/FLAG writes; parser output/hash is retained.

The02 retry completed15 inversions, but independent audit found that saved
`spectral-templates.npz` already contains `spatial*(nu/reference)**alpha` from
`flagging_response._predict`. Imaging applied the factor again, yielding wrong
unit-template indices−1.0/−1.8 instead of−0.5/−0.9.409 numerical/preservation checks
passed and2 spectral-provenance predicates failed: overall matched-family
certification FAIL, not409PASS science. Unit visibility errors were0.10445/0.17329Jy,
far exceeding their approximately6e-8Jy complex64 cast errors. The full
[invalid-basis archive](results/gain-tv-next-imaging-invalid-basis.json) retains
all actual02 products/config/metrics; its paired coefficients are not advertised
as correctly matched template recovery.

Before the new fresh03 retry, remove only this duplicate factor. New pure tests
exercise the actual template producer with independently known zero-baseline
spectra, then verify exact-once unit embedding, both input indices, crosshand
zeros, protected support and nonfinite values outside support. This semantic
counterexample would not be caught by tests that merely reproduce the imager's
own wrong construction or check masking/casting. The15 jobs, settings, native
weights, support, closures and budgets remain unchanged; no QuartiCal rerun.

Fifteen actual inversions are frozen:

- Two unit-Jy compact/extended templates with their known fixed spectra.
- Fixed-fineG0 correction of the actual positive rounded injected DATA delta.
- Full clean, positive omitted-sky and positive complete-diagnostic correctedDATA.
- Total/direct/adaptation paired differences for each of those two sky controls.
- Separate full no-change/mild-operational/firstpass-operational CARACAL controls.

The12 response jobs use the same9,169 original TEST cells and unchanged native
WEIGHT_SPECTRUM. [WSClean's documented convention](https://wsclean.readthedocs.io/en/v3.6/polarizations_and_weights.html)
uses both XX/YY flags and the minimum native XX/YY weight forI; actual FITS
weight/count/PSF metadata are retained. These are matched native-weight proxies,
not an optimal post-Jones covariance or calibrated noise model. Mask-protected
cells/autos/outside-window samples are never restored to manufacture support.

CARACAL images use actual saved TRAIN-mask QC gains and the corresponding frozen
TRAIN-only proposal, not a newly rerun full pipeline. Firstpass is an overbudget
rejected diagnostic and loses gain-supported TEST cells; different support/PSF
are explicit, not a quality winner. The native engine saw holdout features, so
these controls are not unseen-feature flagger tests. No image selects a policy.

## Copy, precision and evaluation safeguards

Two fresh working MSs are reused, each with an exclusive initial whole-MS backup.
Before EVERY CORRECTED_DATA/FLAG write, archive schema/presence, previous corrected
column and FLAG/FLAG_ROW. Never write DATA, calibration-model or weight/SIGMA
columns. Every source/original tree is read-only and must preserve its digest.
Each WSClean job verifies exact diagnostic flags/correctedDATA and protected
native columns. Diagnostic copies keep their additional support masks and are
not advertised as restored/exportable/deployable observations.

Inverse-Jones correction and actual stored-DATA subtraction use complex128;
invalid/condition>1e8 gains abstain. Precast visibility decomposition must close
within1e-10Jy. The new standard CORRECTED_DATA column is complex64, matching the
imager's standard MS input; record actual cast errors. Dirty FITS are also finite
precision. Root froze1e-6Jy/beam maximum image closure and matched-PSF difference
before measurement; a failure is preserved, not repaired by widening tolerance.

Known two-component dirty templates get unrestricted real pixel-space fits,
with explicit rank/condition and no positivity bounds. Fractions are relative
to fixedG0 image coefficients. Pixels are correlated by thePSF: the fit is a
conditional known-family diagnostic, not independent pixels, blind astrophysical
flux/extent estimation, confidence intervals or deconvolved fidelity. Fixed
offsource regions report dirty RMS/std including sidelobes/real sky, not thermal
noise or a fair sensitivity win. A fixed-colour-scale diagnosticPNG accompanies
FITS. Original noise is shared and no new noise realization is drawn.

Checked allocated-block budget1.5GiB includes directories; preserve8GiB free
reserve and prospective write/copy reservations. Not an OS quota. Failures stop
and retain all logs/copies/checkpoints. Image/source/module/tool receipts guard
completion. Emulated walltimes are not a native/end-to-end cost benchmark.

## Interface

`rangtoy.flagging_imaging.run(run_dir,response_dir,caracal_dir)`; executable
[Stimela2 recipe](../recipes/tv-flagging-imaging.yaml). Root provides wrapper,
small image build, actual launch, compact result curation and checked pushes.
Pure correction/flag/fit/precision/resource tests do not establish image gains.
Status remains unmeasured until a fresh result plus independent audits exists.
