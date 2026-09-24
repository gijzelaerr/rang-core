# Discriminating follow-up toward reportable flagging results

Frozen2026-09-24 after pushed measured checkpoint`9f25601`. The user requests
continued research and checked intermediate pushes until interesting findings.
A reproducible mechanism/limitation is reportable, but not a novel successful
RFI method or mature-method quality/cost win without matched evidence.

## Common safeguards

MeerKAT L band, genuine QuartiCal`G.type=complex` full2x2 gains, nativeRust TV.
Original/receivedFLAG/FLAG_ROW, sourceDATA/models and all native WEIGHT/SIGMA
columns remain unchanged. Exclusive backups precede working-copy writes; retain
failures/nulls/rejections. No TEST loss or injection truth in policy decisions.
Old measured modules/outputtrees stay immutable; freeze new source/image receipts.
About15GiB free disk;8GiB reserve, no cleanup/bulk download, ≤3solverworkers.
New response checkedallocation budget1.5GiB, derivedtracks≤256MiB each.
Reservations/checkpoints are NOT OS-enforced quotas; stop safely before further
work on breaches and preserve artifacts. Pre-start snapshot:
`outputs/flagging-backups/20260924-reportable-start/code.tar.gz`, SHA256
`eaf682913b18062523c7ecc8fb44001231a3d82e2118ec3cecc5516568a51867`.

## Physical local-response surrogate (frozen before implementation)

Retrospective seven balanced cases/123 measured counterfactuals, one observation;
seed101/103/105 remain development TRAIN/validation/TEST, not independent tests.
Rust per-native-bin real weighted TRAIN Jacobian of`V=Gp M Gq^H`: active antenna
major, row-majorXX/XY/YX/YY, adjacentRe/Im; q imaginary derivative sign negative.
Four stations give32real parameters. Full/removed normals use original weights,
DATA/model/actual gains only. Project out four common rightU(2) gauge tangents.
Require rank8*Nactive-4/no retained rank loss; two-station extraGL(2) ambiguity
must refuse, not invent support. Baseline spectral rank cutoff1e-10 and damping
1e-6 times full projected largest eigenvalue; relative stationstep≤0.1.
Anchor masked one-step response by subtracting the same full-data step to avoid
baseline nonstationarity drift. Re-polar-gauge before native full2x2 TV at the
original scale/edge support. Freeze TRAIN response before validation objective
scoring. Rank/support/trust failures abstain/missing. No TEST curvature/truth.
Compare all fixed labels at matched coverage, full benefit and benefit with
known2*f cost removed. Controls: `-2*f`, TRAIN101 mean, TRAIN101 residual-score
linear fit and seed137 rankings; no validation tuning. Predictions/source
receipts freeze before label evaluation. No newQC/MS writes. Native predictor
and emulated QC timing cannot establish a fair speedup. Derived namespace:
`outputs/tv-influence-20260924-01`.

## Complete versus omitted sky response (ten-solve pilot)

Pristine`outputs/tv-flagging-actions-01`, splitseed7, grids(2times,32channels)
and(14times,128channels). Actual14integrations spaced7.9966s; coarse grid covers
whole~112s integration span. TRAIN supports288/11 time-frequency bins.
New intrinsic unpolarized templates, reference1283.791015625MHz: compact60mJy
at(l,m)=(+9,-6)arcmin,alpha-0.5; Gaussian120mJy at(-12,-14)arcmin,FWHM8arcmin,
alpha-0.9. Signs±1, amplitude1, no new stochastic noise. Negative sign is a
finiteperturbation diagnostic, not physical negative source flux. No beam/DDE.
Fix clean fine-gridG0 before copied eligibleDATA injection`G0p B G0qH`.
Two clean baselines + two signs×two grids×omitted/complete intrinsic sky=10QC
solves. Complete truth-sky is a DIAGNOSTIC control, not a deployable selector;
use a new backed-up modelcolumn, preserve originalRANG_MODEL_DATA. No flag search.
After solve/settings freeze evaluate unrestricted-real joint linear amplitudes
at known fixed spectra, rank/condition, same commonTEST and fixedG0 weight proxy.
No spectral fitting/bound widening/CI/images. Decompose totalpairedresponse
exactly into injected delta corrected by injected gains PLUS the gain-induced
correction of the SAME original noisyDATA; use identical support/weights and
report closure. BaselineJonesproduct drift is gauge-invariant; elementwise gain
error is not. Checked1.5GiB budget with80MiB futurewrite reservation perQC.
Fresh`outputs/tv-response-20260924-01`; failures preserved, no old retuning.

## Smooth phase specificity and supported real data

[Equivariance freeze](flagging-equivariance.md) replays legitimate unit-modulus
receiver phases in memory: weighted residual magnitude/RFI occupancy invariant,
physical gainTV may change. OLD counterfactual action sets remain fixed; newly
reranked unmeasured actions are missing outcomes, not accepted policies.
Derived`outputs/tv-equivariance-20260924-01`; no newMS/QC in first diagnostic.

Inspect publisher nativeweights/flags/model provenance and complete pinned
QuartiCal/CARACAL functions; distinguish software support, mathematicalJones
identifiability and Rang's current strict all-four-positive-weight protocol.
No rowweight substitution, unsafe pickle decoding or eligibility changes.
Any partial-correlation experiment requires a separately justified frozen gauge.
No visibility acquisition until exact bounded plan/capacity is verified.

Prior art: [Yatawatta2019](https://arxiv.org/abs/1902.10448),
[Yatawatta & Avruch2021](https://arxiv.org/abs/2102.03200),
[Sob et al.2021](https://arxiv.org/abs/2103.12508). Influence-aware calibration and
gain-grid selection are established; implementations alone do not establish novelty.

Status at creation: designs frozen as above, new implementations/results pending.
Parallel fileownership; root integrates recipes, checks, evidence and pushes.
