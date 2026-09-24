# Read-only verification of signed calibration response

2026-09-24. Fresh run `outputs/tv-response-20260924-precision-01`
completed all ten actual full-complex2×2 QuartiCal controls after checked
fix-forward commit `1f53a17`. The preserved
`outputs/tv-response-20260924-recovered-01` remains unchanged.
This audit launches no solves, changes no runtime/raw artifacts and writes only
this new report and the [compact audit](results/gain-tv-response-audit.json).
The main [response archive](results/gain-tv-response.json) is curated separately.

The signed omitted/complete-sky controls reveal calibration adaptation, not a
working flagging policy: no additional flags or selector is used. Known sky
truth appears only in explicitly labelled complete-sky calibration diagnostics
and fixed-template evaluation. No images, fitted spectral slopes, confidence
intervals, independent-observation transfer or novelty/SOTA claim is made.

## Numerical reconstruction

Independently coded read-only replay uses persisted native DATA, actual Jones
matrices and the frozen templates, rather than invoking QuartiCal again. For
each TEST visibility, reconstruct half the trace of
G_p^-1 V G_q^-H. Its correlation coefficients are
c_ab = 0.5 sum_i (G_p^-1)_ia conjugate((G_q^-1)_ib);
the fixed-G0 weight is the reciprocal of sum_ab |c_ab|²/W_ab.
Independent native-correlation variance1/WEIGHT is a diagnostic assumption,
not a validated noise covariance for shared paired observations.

Use one common9169/9169 original TEST support, zero lost/unsupported samples,
and identical fine-G0 weights across all ten arms. Observed weight range
7.290711857351118–25.938700843777664; maximum sampled Jones condition1.2625941.
Joint real-coefficient fixed-spectrum fits have rank2, condition1.9239049794.
Both source spectra remain frozen at−0.5/−0.9; no bounds, positivity or slope
fit is introduced. All26 reference/total/direct/adaptation fit replays agree
with stored coefficients to at most3.4000580129e-16Jy.

The rounded injected DATA difference is complex128, computed by casting EACH
stored native-complex64 operand before subtracting. It exactly equals saved
injected DATA minus original DATA; actual native DATA storage remains complex64.
Every frozen injection and complete-column addition is independently rebuilt:
DATA uses signed fine-G0 corruption on the eligible mask; the separate
RANG_RESPONSE_MODEL uses base RANG_MODEL_DATA plus signed intrinsic prediction,
rounded to native complex64. Outside-mask DATA and the base model stay exact.

Decomposition on the same support/weights:

    total paired response = injected-gain correction of the actual DATA delta
                          + change in correction of SAME original noisy DATA

Saved visibility closures span6.8845e-15–8.2530e-15Jy; independent matrix-trace
closures span8.1127e-15–1.0109e-14Jy. Replayed coefficient closure is at most
6.2450e-17Jy. Both unchanged numerical closure thresholds remain1e-10Jy.
This replay reuses the same saved gains/DATA and known template family:
it verifies artifact arithmetic, not independent scientific replication.

## Conditional measured response

Reference fits recover signed60.000004/119.999994mJy under fixed fine-G0.
Response fractions divide each unrestricted coefficient by its same-sign
fixed-G0 reference coefficient, not by an independently measured sky flux.

| Sky control | Gain grid | Positive compact / extended | Negative compact / extended |
| --- | --- | ---: | ---: |
| Omitted | 2,32 | 0.510023 / 0.741920 | 0.512994 / 0.741466 |
| Omitted | 14,128 | 0.524040 / 0.762121 | 0.527077 / 0.761725 |
| Complete diagnostic | 2,32 | 0.999599 / 0.989177 | 0.999518 / 0.989200 |
| Complete diagnostic | 14,128 | 1.011047 / 0.999164 | 1.010965 / 0.999129 |

For positive fine-grid omitted sky, direct terms are60.148773/120.050624mJy,
while gain adaptation contributes−29.547391/−31.020242mJy. The total is therefore
30.601382/89.030382mJy. Complete-sky fine-grid adaptation is much smaller:
−0.026375/−1.305486mJy, with total59.975953/118.701193mJy. This separates inverse
correction of the injected signal from absorption through changed calibration.

Signed fractions cohere without enforcing symmetry: their compact differences
are0.002971/0.003037 for omitted fine/coarse and0.000081/0.000082 for complete
fine/coarse. Maximum even-part total coefficient is0.091108mJy. These repeated
finite perturbations share noise and do not supply independent error bars.
A negative sign is a diagnostic perturbation, not a physical negative source.

Gauge-invariant Jones-product drift against same-grid clean gains is
0.00404–0.00424 omitted versus0.000195–0.000425 complete. The coarse clean
baseline already differs by0.0916143 relative to empirical fine-G0 and has
TEST residual loss31.20994 versus24.91961, a25.24% increase. Validation loss
also worsens by25.68%. Slightly larger coarse response is not a matched-quality
win: constant-in-time gains may underfit legitimate instrumental variation.

Positive fine-grid omitted TV0.1468465544 is lower than complete TV0.1472823832,
despite much smaller source response. Both use full Jones matrices and fixed
support/normalization. This is a concrete conditional warning against rewarding
low TV alone. Fine/coarse TV edge counts differ2078 versus36; lower cross-grid
raw TV cannot establish higher quality.

## Exact inputs, qualified gain reproduction

The first614 artifact/numerical predicates retain602 passes and12 FAILED
exact-identity expectations. They are not removed or silently converted to
passes. All calibration DATA/base and complete model values, native weights,
frozen physical settings, per-trial training flags and command options are
exactly unchanged from the failed run; commands differ only in output paths.
All ten prediction-loss dictionaries are exact. Runtime image/module receipts
change as expected for the evaluation precision fix.

Nine of ten native QC gain trees and saved gain arrays are byte/value-identical.
The clean fine solve genuinely differs in raw QC gains and jhj chunks, not just
postprocessing: maximum native Jones change3.1401849174e-16 and jhj change
3.4926033322e-10 against peak756183.1640 (relative4.61873e-16). Coordinates,
finite support, gain flags and convergence iterations/percentages are exact.
The shared fine-G0 norm changes by one ulp:
old1.0520039063056517, fresh1.0520039063056514.
All ten TV edge arrays consequently fail strict value identity, but their
finite supports are exact; maximum edge change1.1934897515e-15.

Separately recorded roundoff qualification passes24/24 checks, using
16×float64epsilon×max(1,reference magnitude) only for reproduction diagnostics.
This is not a changed gain objective or widened scientific/closure threshold.
Additional exclusive-backup, exact training-holdout and flag-restoration
boundary checks pass30/30. The archive retains every predicate, exact failure,
numerical comparison and the actual read-only replay programs.

## Preservation, resources and receipts

All three fresh working MSs have received FLAG and FLAG_ROW restored exactly;
all immutable original.ms copies match the received source digest. Original
source DATA, Observatory flags and all four native WEIGHT/WEIGHT_SPECTRUM/
SIGMA/SIGMA_SPECTRUM columns remain protected. Injection backs up full working
MS and state before DATA writes; DATA flag snapshots are identical. Schema,
base-model/flags and state backups precede the separate complete-model column;
that column matches its immutable snapshot and frozen intrinsic addition.

Failed working copies remain failed, including their temporary TRAIN/holdout
flags; they are not exported as restored/deployable data. Neither failed nor
successful raw output trees changes during read-only checks, excluding only
casacore transient table.lock bookkeeping:
failed `f16c341384e9d8baf397640a2c0fa245235cbc1b34aedc621d5bff123534af8f`,
fresh `bce25d2ef8db8b840c0eaac20df8f259f2ef2014a608f087d30db4028e1999ce`.

Measured allocation including directories889081856bytes (0.828022GiB) remains
below the checked1.5GiB cap. Audit container-view free space105640300544bytes
exceeds the frozen8GiB reserve. Reservations/checks are NOT an OS-enforced hard
quota, and this final observation cannot independently establish every
historical transient disk minimum. All failure artifacts are retained.

Ten failed-run actual QC invocations plus ten fresh invocations mean20actual
solver runs, but only ten distinct frozen physical controls, not20independent
trials. This audit adds zero QC/native-flagger invocations and26 numerical fit
replays. Emulated timings do not establish native resource/SOTA advantage.

Result SHA256:
`e7ee791ba0f8ca1f1775c49348dd2e4a51c9fe9e29b77a7e4cda2cfd29215083`.
Configuration SHA256:
`f037a506c357a20aedf1731d50dd544853ca175d04104eb22ad987220f1d43fa`.
Runtime source SHA256:
`b62a9877af099d9c72875b8439818b033e8fdff22d5b931386f327dbfed5fac8`.
Linux Rust library SHA256:
`f764ed8f215a6b22db5b511fcefae6398f9ff52c0a1b851d914f66452d235a8f`.
Exact pinned image:
`sha256:102767125ea2fe1f7fc000738cb16e28d1e967188c227a583d27293596fb2d95`.
Prepared digest:
`8d21dd5ab4ff0d689ee06379fdc5bc00890fcb7c6221beec5d30007e34afba4c`;
received raw digest:
`84e244f9e8256731b0d20a0e853a107dd80e3c2be36a532efe707b3d8766c519`.
Python3.12.14; QuartiCal0.2.7, Stimela2.1.4, NumPy2.5.3,
codex-africanus0.4.4 (the prediction library), python-casacore3.8.1;
the four frozen helper hashes and package receipts verify exactly.
