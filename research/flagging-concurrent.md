# Concurrent MeerKAT L-band experiments

Protocol started 2026-09-24 06:53 UTC after checked/pushed checkpoint `5377902`.
The user requests all five next workstreams concurrently. This document records
proposed/frozen settings before new outcomes, not a scientific success claim.
Each module, recipe, source digest and exact run configuration is additionally
saved before its actual measurement. Changes require a new configuration/run.

## Common safeguards and resources

Preserve every received FLAG/FLAG_ROW, DATA and native weight column in source
observations. Copies, exclusive pre/post-write snapshots, read-only prepared
boundary checks and independent preservation audits remain mandatory. Simulation
or source injections affect backed-up working DATA only. No policy may decode
injection truth or use test loss to fit, rank, tune or choose an action.

Use QuartiCal `G.type=complex`, actual full 2x2 gains, identity initialization,
50 iterations, original weights, disabled MAD/output flags and fixed gain grid
unless a specifically labelled grid-control experiment says otherwise. Keep
existing Rust full-matrix TV computation and per-case baseline scale/edge support.
Objective remains `TV_fixed/TV0 + 2*added_fraction + .25*validation_MSE/MSE0`;
retain no-change, <=2% additions and <=1% validation degradation.

Disk availability at start: about17GiB. Keep an8GiB reserve, check before each
download/copy and preserve failed/null artifacts. No cleanup authorized. Limit
actual solver concurrency to three; independent outputs/logs/caches required.
Raw data remain ignored; compact evidence and executable Stimela2 recipes are
tracked. Full build/tests/lint/format before every regular commit/push.
Backup `outputs/flagging-backups/20260924-concurrent-start/code.tar.gz`, SHA256
`2d654f3e8454267892b34ce1964125d3a9d7052d63649ef86b5f1e0441e3de9e`.

## Geometry-balanced search

Existing whole-rectangle candidate family, no trimming or unions. Frozen new
search allocation: two global, two antenna-star and two single-baseline masks
per ranking; do not borrow empty-group slots. Compare TRAIN residual-only and
TRAIN TV-conditioned rankings plus an identically allocated random ranking
(seed137). Deduplicate masks and reuse their actual solves. Global allocation
is metadata-fixed, not selected from measured test/injection outcomes.

Prepare unmodified control plus fresh strong time-burst and antenna-local cases,
strength10, occupancy0.005. Injection seeds101/103/105 define model-training/
model-validation/model-test groups respectively, never shuffled action splits.
Same four-antenna observation: new-seed generalization is not observation transfer.
Exact labels are evaluation-only; hypotheses motivated by old measurements must
not treat the old fixture/results as a new independent test.

## Uncertainty-aware TV

Keep raw full-gain TV as the requested objective. Develop TRAIN-only trend/noise
or curvature guidance, with explicit gauge/support handling. Freeze clean smooth
delay/amplitude, noisy smooth gains and discontinuity controls before measurement;
record gains, coordinates, seeds, noise and every tested grid. High first-order TV
does not alone mean nonsmooth gains or RFI. Synthetic diagnostic separation is
not proof that a real-data flagging policy is improved.

## Representative real-data pilot

Bounded public PKS1934-638 primary archive, pinned metadata/source from
[candidate provenance](flagging-public-data.md). Start at MAIN_0 (scan1), first
row chunk and channel tile8 (native1024:1152), preserving all61 participants.
Retain up to16 complete integrations only after verifying row layout. MAIN_1
(scan3) is a proposed separate-scan transfer input, not an independent observation.
Four large objects per scan have an approximate353MiB first-scan compressed
budget; HEAD/ETag/length checks precede GET. No target-field bulk acquisition.

Reject unrestricted remote pickle/object decoding. Verify actual received flags,
weights, finite model, polarization, coordinates and gain-bin support. If safe
native-MS conversion or scalar-model assumptions cannot be established, record
the limitation instead of inventing metadata or silently modifying the model.
Acquisition, numeric inspection, conversion, calibration and transfer are separate
statuses and require their own evidence.

## Science-signal preservation

Paired source injections into copied working DATA, before calibration/flagging;
compact, extended and spectral controls. Freeze physical flux/reference frequency,
location/extent/spectrum and policy masks before outcomes in the track report.
Signal truth is evaluation-only, not supplied to policy features/selection.
Measure visibility-template flux/spectral recovery and calibration suppression.
Actual fixed-setting images require a verified imaging executable; template
metrics alone must not be labelled image or morphology validation. Include
no-added-flags and relevant native methods where executable/budget-compatible.

## Transferable action model

Predict actual guarded objective action benefit using TRAIN-only residual/TV/
geometry/support features; invalid/unsupported action labels are missing, notzero.
Fixed modest estimator/penalty family must be frozen before heldout cases. Fit
seed101 groups, tune seed103 groups, report seed105 predictions only after fit;
confirm nominated actions with actual QuartiCal results. Test labels never rank
or choose masks; include no-change and reject unsupported/out-of-domain inputs.
Old archives are development evidence only. Matched solve/search budgets and
native execution costs are needed before claims of runtime/quality superiority.

## Status and routing

All five tracks are underway; no new measured result at protocol creation.
Root owns public numeric acquisition, integrated orchestration, handoff/index and
checked pushes. Geometry, uncertainty/model and science-signal modules are
implemented in parallel in separate files. Track reports and compact archives
will replace pending statuses only after actual checks/measurements.

Implementation checkpoint: allsix new modules and executable recipes are stable;
323Python/14Rust and full local build/lint/format checks pass. Publicnumeric
acquisition completes75objects/843.63MiB with independent receipt-boundary checks.
Separate180gain-only controls are [archived](results/gain-tv-uncertainty.json).
Integrated actual run starts07:08:54UTC at`outputs/tv-concurrent-20260924-01`,
stages allsix backed-up cases and scatters threeworkers. New actual balanced/
paired-signal/public-inspection/model measurements are pending at this checkpoint.
Native-MS conversion, actual images and independent-observation transfer remain
unimplemented/unmeasured; gain-only controls do not establish real uncertainty.

## Completed measurements, 2026-09-24 07:18:30UTC

[Measured suite](results/gain-tv-concurrent.json) gathers all ten scatter
branches and the dependent actual fit successfully. Source implementation is
the pushed`1739d48` checkpoint; all13 frozen runtime hashes and prepared/source
boundaries remain unchanged. Three workers take approximately9min36s wall time
in Linux amd64 emulation, not native or matched mature-method performance.
Counts:130 balanced full-Jones diagnostic solves plus16 paired-signal diagnostic
solves and one nativeMAD flag-generating solve,147 QC invocations total. The
gain-only controls require no QC solves; fitting requires zero new solves.

Evidence is separated by track:

- [Balanced](results/gain-tv-balanced.json): TV improves one time-burst seed,
  recovering19.69% known injection versus residual10.10%, but all rankings
  keep no-change on clean and five other cases. No robust TV advantage.
- [Gain controls](results/gain-tv-uncertainty.json): legitimate smooth delay
  produces high rawTV; integrated180 controls replay the same frozen protocol.
  Detrended excess remains synthetic guidance, not deployed real uncertainty.
- [Public numeric pilots](results/meerkat-public-pilot.json): actual61-antenna
  DATA/model/flags/weights retained in two16-integration tiles; all native
  cross-hand spectral weights are zero. Current strict protocol has no eligible
  four-correlation cells. No weights/flags changed to force calibration.
- [Paired signals](results/gain-tv-signal.json): no-extra-flags selected,
  strong conditional omitted-source attenuation with bound-hit spectra; no
  physical spectral/image preservation validated.
- [Fitted model](results/gain-tv-transfer.json):105 actual guarded labels,
  grouped seed split, all six no-change recommendations; one beneficial action
  missed. Post-hoc flag-volume-cost decomposition limits constant-baseline claims.

[Read-only checks](results/gain-tv-concurrent-audit.json) retain separate
per-track counts, reconstruction categories and unchanged source digests. They
reproduce software/artifacts, not human peer review or independent science.
Final local release/build/test/lint/format checks are recorded in the handoff.

Suite allocation is6.9GiB, exceeding the6GiB preflight forecast; about15GiB
free disk remains after execution, above the8GiB reserve. The forecast is not
a hard cap; recheck actual source/copy budgets before another run. Nothing
was deleted. Backups, seeds, every rejected counterfactual and negative result
are retained. New eligibility/fit/guidance settings require a new frozen run,
not a retrospective retune of these test outcomes.
