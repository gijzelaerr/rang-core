# Five-track results campaign: frozen plan

Created 2026-09-24 after checked pushed checkpoint `166350c`, before these new
implementations/measurements. The user requests execution of all five tracks in
parallel, regular checked pushes and results rather than another roadmap.

## Measured progress,2026-09-24

Four original branches complete under source `ec2f17d`; the fifth hits a
preserved WSClean3.6 CLI compatibility failure before any FITS. There is no
successful original master gather. A checked four-option spelling fix and
real-binary parser gate enable a separately fresh imaging-only retry, without
repeating the63 actual calibrations already completed.

| Track | Measured outcome | Independent verification |
| --- | --- | --- |
| Estimated scalar-trend guidance | All21 smooth-phase comparisons preserve detrended top-six order; raw-TV order changes17times | [562 checks](flagging-next-trend-verification.md) |
| Absolute signal-preservation guard | Abstains: one TRAIN bin has rank8 versus required12; no available safety matrix | [558 checks](flagging-next-signal-verification.md) |
| Prospective candidate confirmation | Matches measured shortlist-union reference in all3cases; one56-cell mask recovers9.40% of known injected patch | [2355 checks](flagging-next-prospective-verification.md) |
| Public metadata provenance |85chunks,505strings,21HISTORYrows recovered; one CASA split does not certify DATA/noise convention | [657 checks](flagging-next-provenance-verification.md) |
| Actual images/CARACAL controls | Original parser failure retained;02completes15inversions but fails two spectral-family checks | Corrected fresh03retry/audit pending |

The first four tracks now have reportable results. Physics forecast error is
4.5–8.6times lower than a negative-flag-cost-only descriptive control, but raw-TV,
residual and detrended rankings share the single winner here. This does not
establish a trend-ranking win, native runtime speedup, independent-observation
transfer, certified signal-safe policy or superiority to a mature flagger.
All original DATA/FLAG/FLAG_ROW/model/native noise columns remain protected.

Remaining in this cycle: fresh03corrected-unit-basis dirty inversions, their
independent numeric/provenance/preservation audit, and the combined checked public handoff. The1–3hour
initial estimate concerns this prototype cycle only. The scientifically larger
next gate is a representative observation with known noise/model provenance and
adequately identified TRAIN bins, followed by matched image-quality/cost tests.

## How much remains

We already have reportable mechanisms: sky-dependent signal absorption, physical
phase sensitivity of gain TV, and useful local objective forecasts. A credible
flagging demonstrator still needs three gates: prospective candidate outcomes,
signal-preservation/specificity evidence, and independent observation plus
matched imaging/compute comparisons. This first implementation/verification
cycle is estimated at1–3hours, not a promise; its at-most93 prospective/paired QC
invocations should take minutes on the present small fixture. Independent-data
provenance and representative imaging may dominate later work. No number of
additional seeds on this same scan establishes independent transfer or novelty.

## Shared immutable boundaries and resources

MeerKAT L band only. All gain solves remain QuartiCal `G.type=complex` full2×2,
fine2integration×32channel grid, identity initialization,50iterations, native
weights and unchanged convergence settings. TV of the solved full Jones gains
remains in the objective; expected instrumental trends are extra guidance, not
a hidden replacement of the scientific objective.

Received FLAG/FLAG_ROW, original/source DATA, calibration model and all native
WEIGHT/WEIGHT_SPECTRUM/SIGMA/SIGMA_SPECTRUM columns are authoritative. Only fresh
backed-up copied MSs are writable. Exclusive flag/state/DATA/schema backups
precede mutations; retain all failures/nulls and source hashes excluding only
casacore transient table.lock bookkeeping. No truth/TEST values in selection.

Maintain8GiB free-disk reserve. Checked per-track allocated-block allowances:
inputs768MiB, prospective3GiB, signal guard1.5GiB, imaging1.5GiB, trend256MiB;
provenance8MiB logical outputs, remote compressed/decoded sum each≤1MiB. These
are pre/post operation reservations, not OS quotas. Reserve80MiB per shared QC
write batch and stop on observed breaches without deleting outputs. At most two
simultaneous QC workers, plus one single-threaded imager; no fulltools rebuild,
bulk visibility download or automatic cleanup. The old solver image102767... and
raw measured trees stay retained. Build a separately tagged shared Rust-kernel
overlay and a small pinned WSClean child; freeze IDs/package receipts before runs.

## 1. TRAIN-estimated trend-aware TV guidance

New Rust kernel estimates per-station scalar frequency/time phase gradients from
adjacent determinant-phase differences of TRAIN-supported, polar-gauged actual
Jones matrices. Use robust medians, native coordinates, valid edge/gap support;
no known injected phase, truth, TEST or invalid-bin interpolation. Half determinant
phase requires an explicit unaliased scalar-step assumption; retain insufficient
support/conditioning as unavailable rather than inventing a fit.

Dephase all four Jones entries with the baseline-estimated linear trend, then
use existing native full-matrix TV for guidance. Baseline coefficients freeze
and are shared across its counterfactuals. First replay the four previously
frozen grid-matched phase patterns on seven baselines, estimating coefficients
from each TRAIN gain product. Measure trend shifts, raw/residual TV, support and
residual/detrended/raw TRAIN candidate rankings. This does not establish
finite-iteration QuartiCal equivariance or universal physical trend separation.

## 2. TRAIN-only absolute signal-response guard

New time-burst seeds107/109, strength10 original inverse-weight units,
occupancy0.005; same original splitseed7. Freeze at most three masks per seed:
nochange, best predicted-objective candidate without guard, best with guard,
deduplicated. Use retained TRAIN full-Jones curvature and fixed two-source
template probes to forecast their inverse-corrected2×2 transfer. Require native
rank/gauge/support/trust≤0.1 and absolute spectral norm ||T−I||2≤0.1. No relative
fallback if the incomplete-sky baseline is already unsafe; nochange is then
explicitly uncertified, not a fabricated signal-safety success.

Freeze all TRAIN forecasts before validation scoring. Existing full objective:
fixed-supportTV/TV0 +2*addedfraction +0.25*VALMSE/MSE0. Require positive predicted
benefit>1e-6, addedfraction≤2%, actual validation degradation≤1% and actual
objective improvement>1e-6 for final acceptance. Serialize acceptance before
any injected-signal TEST evaluation. Selected-candidate diagnostics run regardless
of acceptance. Paired clean/positive-source omitted/complete diagnostic sky,
fine grid only, at most18QC total; two fresh copied trees per seed. Reuse frozen
60/120mJy compact/extended family, fixed spectra/positions, empirical fineG0
DI corruption, common TEST and linear response decomposition. Complete sky uses
truth only as an explicitly labelled diagnostic. No images/CI/blind-flux claim.

## 3. Prospective physical-surrogate candidate confirmation

Prepare clean plus TRAIN-only time-burst seeds107/109 from pristine
`outputs/tv-flagging-actions-01`. Freeze newly generated admissible rectangles
before reading outcomes. Shortlist two per canonical global/star/baseline group
for residual, rawTV, seeded137 random and estimated-trend TV guidance; empty
groups do not borrow slots. Union≤24 distinct masks per case. Forecast with the
already validated Rust anchored projected GN deletion response; retain the
frozen0.1 station-step limit,1e-10 rank cutoff,1e-6 damping and missing reasons.

All TRAIN responses freeze before VAL scoring; all forecasts/rankings freeze
before any new candidate solve or label decoding. Physics gets at most two
positive predicted-benefit masks for confirmation. For matched retrospective
evaluation of this now-prospective freeze, actually solve the full shortlist
union (≤75QC including three baselines). Score confirmed physics and the original
six-slot rankings at identical actual quality guards. Report missed benefit,
coverage, gain-change accuracy, known flag-cost controls, actual solve counts,
forecast overhead and emulated timings separately. No native-speedup claim;
this experiment spends extra reference solves to test a cheaper future policy.

## 4. Bounded independent-data provenance recovery

Implement the already frozen [85-object textual plan](flagging-supported-provenance-plan.md)
with inert `pickletools` symbolic recognition and adversarial tests before remote
payload inspection. Fixed source and allowlist only; HEAD each object, enforce
≤64KiB/object and≤1MiB total, freeze complete HEAD receipt before conditional
GET, reconcile length/ETag/SHA. Bound Blosc output before decompression. NEVER
unpickle, instantiate arbitrary reducers or invoke payload-selected callables.

Extract native antenna/field labels and21 HISTORY rows to investigate DATA versus
sigma/weight/export provenance. This alone does not supply missing measure frames,
certify noise, create an MS, justify sigma selection or provide independent
calibration results. Missing/unsupported provenance remains a gate, not grounds
to substitute unit weights, clear flags or invent metadata. No MAIN requests.

## 5. Actual matched image-domain diagnostics

Small pinned Debian WSClean3.6-1 child image, signed snapshot package/dependency
receipts, bounded new-package download≤256MiB, no upgrades/removals/downgrades
of pre-existing packages and no solver/fulltools rebuild. Actual dirty
images/PSFs first:512²,8arcsec,Briggs0.5,StokesI,channels1024:3072,
explicitwstacking gridder,nwlayers64,no-small-inversion,oneCPU,niter0. Use copied
MS CORRECTED_DATA, same original common
TEST9169 and native spectral weights, with received flags OR excluded support;
no MODEL update. Record WSClean XX/YY weight handling explicitly.

Image paired fine-grid positive omitted/complete response, fixedG0 reference
and direct/adaptation closure from already retained QC gains. Same support must
give matched PSFs. Fixed known-template coefficients, morphology and off-source
RMS are conditional sparse-four-antenna diagnostics, not blind deconvolved
fidelity or independent science. Separately image saved full-CARACAL nochange,
mild and rejected-firstpass controls: differing support/PSFs and overbudget
outcomes stay explicit; no matched-quality winner is manufactured.

Premeasurement imaging refinements:15 fixed inversions (12 response/template/
decomposition diagnostics plus3 CARACAL controls), two fresh copied MSs.
Complex128 pre-write visibility closure≤1e-10Jy; native complex64/FITS image
closure≤1e-6Jy/beam, with explicit casting-roundoff receipts. No posthoc tolerance
widening. WSClean3.6 defaults to wgridder, which ignores nwlayers; explicit
wstacking ensures the intended64 layers. Signed Debian snapshot
`https://snapshot.debian.org/archive/debian/20250901T000000Z/`, trixie/main,
amd64, existing Debian archive keyring; no unsigned/trusted fallback.

## Execution and handoff

Root owns trend/prospective kernels/interfaces, shared input preparation,
wrappers, top-level Stimela2 graph, freezes, resource checks, actual launches,
compact archives, independent cross-checks and checked public-identity pushes.
Parallel owners implement signal guards, provenance and imaging in disjoint new
files; frozen old helpers/raw artifacts are not edited. Each track documents
design before measurements. All builds/tests/lint/format/schema and staged
whitespace must pass before every commit, with nonzero status gating commits.

First deliverable: an executed five-track campaign and compact report distinguishing
measured outcomes, implemented methods and remaining gates, including negative
results. A validated science flagger and quality/cost novelty remain later gates.

Implementation routing: [top-level Stimela2 graph](../recipes/tv-flagging-next.yaml),
[offline Docker launcher](../tools/flagging/run-next.sh), fresh shared inputs
`outputs/tv-next-20260924-01/inputs/cases/{clean,time-burst-seed107,time-burst-seed109}`.
Metadata HEAD/acquisition are separately gated preparatory stages, never implied
by the offline graph. Each of five sibling experiment namespaces is exclusive.
Existing stable inputs receive explicit read-only Docker bind mounts; a real
casacore prepared-boundary check on a read-only mount passed before launch.
Three scatter processes can run two QC workers plus a single imager; neither
trend nor provenance invokes QC. All-case TRAIN freezes precede VAL forecast
scoring, and all-case forecast freezes precede prospective action outcomes.

Premeasurement hardening found and fixed unsigned-mask monotonicity and missing
explicit input-identity/cardinality checks. Require exact distinct clean/107/109
case paths, source digests/preservation receipts and<=24 distinct shortlisted
masks; enforce<=75 actual prospective solves before candidate work. Full-precision
native GN, heldout-poison and mocked sequencing tests precede launch. These
checks are implementation verification, not a positive scientific result.

Compatibility retry: [dedicated offline imaging launcher](../tools/flagging/run-imaging.sh)
uses the existing [imaging recipe](../recipes/tv-flagging-imaging.yaml), fresh
`outputs/tv-next-imaging-20260924-02`, and read-only signed-response/CARACAL
sources. Four changed option names preserve the original physical settings;
the pinned binary parses the full command before any copied-MS mutation.
All initial failures and backups stay retained; no posthoc tolerance widening.

Second retained imaging failure:02passes409numeric/preservation checks but
fails2semantic checks. The saved unit templates already contain the approved
spectral laws; applying them again produces the wrong unit basis. Preserve02
as [invalid-basis evidence](results/gain-tv-next-imaging-invalid-basis.json),
remove only the duplicate factor and add provenance regression tests before
fresh03. This is restoration of the frozen source family, not spectral/quality
retuning or changed QC input. Independent verification must compare actual
unit checkpoint visibilities to the saved spectral payload, not merely
reimplement the runner's formula.
