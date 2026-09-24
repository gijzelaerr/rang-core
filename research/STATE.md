# Rang research state

Updated 2026-09-24.

## Current continuation and routing

Continuation2026-09-24 after pushed`9f25601`: user requests persistent research
until reportable findings and regular checked intermediate commits. New freezes:
`research/flagging-reportable.md`, `research/flagging-equivariance.md`.
Parallel: Rust local actionresponse, ten-solve complete/omitted-sky/grid controls,
smoothreceiverphaseTV replay and supported-data/partial-Jones gauge review.
No new outcomes yet. Old measuredoutputs/modules protected; fresh runnames only.
Disk15GiB/reserve8GiB, response checkedbudget1.5GiB, derivedtracks256MiB each;
reservations/checkpoints are not OSquotas. No cleanup/bulk acquisition. Pre-start
backupSHA/path inprotocol; designs precede implementations/measurements.

Latest measured checkpoint, 2026-09-24 07:18:30UTC: the five-track Stimela2
suite completed all ten scatter branches and the dependent transfer fit, with
three workers. Implementation commit `1739d48` is pushed. Raw run:
`outputs/tv-concurrent-20260924-01`; entry recipe
`recipes/tv-flagging-concurrent.yaml`. All13 frozen module hashes and the prepared
source/acquisition boundaries are unchanged. Result/archive curation and
read-only verification are complete; no source retuning.

Compact evidence: `research/results/gain-tv-concurrent.json`,
`gain-tv-balanced.json`, `gain-tv-signal.json`, `gain-tv-transfer.json`,
`meerkat-public-pilot.json`; the acquisition and standalone gain controls keep
their historical archives. Seven balanced cases require130 actual full-Jones
diagnostic solves. Only time-burst seed105 selects flags: residual58/58 known
injected additions,10.1045% recall; TV113/136 known injected,19.6864% recall,
23 outside known injection. Objectives1.2496526895/1.2492314087 versus1.25;
random and every other case retain no change. Outside-injection additions are
not proven false positives on unlabeled DATA. This is not a robust TV advantage.

Paired signal track:16 diagnostic solves plus native MAD flag generation;
commonTEST9169/9169, no lost support. Residual/TV retain no extra flags. The
conditional omitted-source fits recover only15.34% compact/9.31% extended
reference flux, but BOTH fitted spectral indices hit the-5 lower bound.
Report boundary-constrained diagnostics, NOT astrophysical slopes or images.
NativeMAD adds960TRAIN cells, worsens objective1.2874921193. WSClean absent.

Grouped fitted model:35TRAIN/34VAL/36TEST actual guarded labels, seed groups
101/103/105, penalty0.1, optimism margin0.00108005734. All six recommendations
are no-change, missing the time-burst105 benefit0.0007685913. A post-hoc known
flag-cost-only predictor is much closer than a TRAIN-mean constant: do not imply
broad transferable improvement. Every case reuses one four-antenna observation.

Public numeric inspection is complete, not conversion/calibration: both scans
retain61antennas/16complete integrations/30256rows/128channels1070–1096.541MHz.
Received FLAG fractions80.4890%/80.2970%; DATA/model finite. Native XY/YX
WEIGHT_SPECTRUM is identically zero, leaving zero eligible full-four-correlation
cross cells in the current protocol. NEVER substitute row WEIGHT=1, clear flags
or cherry-pick a nicer epoch to force acceptance. This does not prove the data
uncalibratable under a separately justified partial-support/gauge protocol.
Safe string/native-MS conversion, representative full-support calibration,
independent observation transfer, images and mature-method cost/quality wins
remain outstanding. Source FLAGS/DATA/all four native weight/SIGMA columns are
protected; intentional simulation writes affect backed-up working copies only.

Latest full local checks:323Python tests(no skips),14Rust tests,releasebuild,
Clippy,Rust/Ruff lint/format,bytecompile,allwrapper syntax,41researchJSON parses,
exact archive/raw-result reconstruction andallthreecontainer pipchecks pass.
Actual recipe execution completes; Gitwhitespace passes before measured commit.
Suite allocated6.9GiB/free disk15GiB at07:22UTC, reserve8GiB retained/no cleanup.
The frozen6GiB allowance was a forecast, not a hard cap; check capacity afresh.
Read-only audit routing: `research/results/gain-tv-concurrent-audit.json`.
Separate counts:108prepared,2303balanced numerical/artifact,1297new compact
archive integrity,1255standalone/1257integrated gain-control,680transfer,
32+6+17signal artifact/replay checks all pass; counts are not scientific wins.
Final source/archive snapshot before adding its receipt to the handoff:
`outputs/flagging-backups/20260924-concurrent-measured-final/code.tar.gz`,
SHA2568fdaecdbf429a8d052d2ebe1bb4f7af676b7998e74a89520a3949ff4ca3fc419.
Next: source-preservation/identifiability guards on a new frozen validation
protocol, a genuinely supported representative dataset, then matched native
accuracy/cost experiments. Never tune new settings to the seed105 outcome.

## Historical checkpoints (superseded statuses)

Latest2026-09-24 07:10UTC: allfive modules/recipes implementedandstable;
fullchecks323Python/14Rust(no skips),releasebuild,Clippy,Rust/Rufflint/format,
bytecompile,allwrappersyntax,35JSONarchives,whitespace andallthreecontainer
pipchecks pass. Master/public/signal actualrecipe dryruns pass. Integratedactual
Stimela scatter3 started07:08:54UTC at`outputs/tv-concurrent-20260924-01`;
sixfresh backed-up cases staged, firstthree fullJones branches active, results
pending. Masterfreezes13sourcehashes andimage beforecases/solves; donotedit
runtime modules untilfinish orretainfailure andchoosea newrun.

Gain-only diagnostics measured180controls separately at
`outputs/tv-uncertainty-controls-01`; trackedcompactarchive
`research/results/gain-tv-uncertainty.json`. Legitimate smoothdelaygains mayhave
muchhigherrawTV thanflatnoisy gains. Detrending/noiseexcess isconditional
synthetic guidance only, notrealQC uncertainty orRFIclassificationvalidation.
Publicreceipts independentlyverified75boundedobjects/884609513bytes; first
entireFLAGchunk80.4068%flags, retainednegativefinding, no clearing/cherrypick.
Trackedacquisition `research/results/meerkat-public-ingestion.json`; fullnumeric
inspectionandMSconversion/calibration/transfer remainpending. Publicreader34
tests includereceipttotal/headers/statbounds beforepayloadread; reviewissueclosed.
Disk13GiB/allocatedsuite1.3GiB asof07:10UTC, reserve8GiB/no cleanup.
Checkedimplementation backup
`outputs/flagging-backups/20260924-concurrent-implementation/code.tar.gz`,
SHA2568d68fed79cc9171dec7322a2de40b98670ca4c03ef30dc031956ba2090a5a5bb.

User requests allfive next workstreams concurrently. Checked hardeningcheckpoint
`5377902` is pushed and worktree initiallyclean. Pre-outcome protocol/routing:
`research/flagging-concurrent.md`. Geometry-balanced search, uncertaintyTV,
bounded61antenna numeric ingestion, pairedscience signals and groupedtransfer
model implementedinparallel with separatefile ownership. Startdisk17GiB;
reserve8GiB, no cleanup, maxthree actualsolverworkers. Frozenfreshinjection
seeds101/103/105 are train/validation/test fortransfer, strongtimeburst/antlocal.
No newmeasurements yet. Backup/path/SHA inprotocol; originalflagsalwaysprotected.

Bounded publicacquisition nowcomplete: `outputs/tv-public-acquired-20260924-01`,
75numericBloscobjects/884609513bytes(843.63MiB), MAIN_0/MAIN_1tile8firstrowchunk,
metadatarepin+HEAD/GET exactETag/length+SHA256 eachobject. ReceivedFLAG/FLAG_ROW
andWEIGHT/WEIGHT_SPECTRUM/SIGMA/SIGMA_SPECTRUM allacquired unchanged; no
CORRECTED_DATA orobject/picklestringdecoded. Offlineinspection/calibrationnotyet.
Newpublicreader34tests/masterorchestrator8tests pass, bothrecipes actualoffline
dryruns pass. Balancedsearch17tests anduncertainty/transfer21tests pass; source
filesstable. Masterrecipe scatter3, transferwaitsforactualbalancedlabels;
`recipes/tv-flagging-concurrent.yaml`. Signalmodule nowstable/16tests pass.

Complete measured checkpoint `94369a0` pushed to origin/main after196Python/
14Rust and full local checks, public user identity/no co-authors. Separate
read-only artifact verification is now complete:318predicates pass across all
seven structured states/14exports/101solves and four native controls. Includes
all present weight/SIGMA columns, exact source reconstruction, frozen ranks,
actual Rust TV/support/scale, source boundaries and selections. Record
`research/results/gain-tv-artifact-audit.json`; no measurement-blocking issue.

Fix-forward hardening after review: new stdlib host preflight resolves run/log/
prepared/strategy paths before any cache,log orDocker writes, rejects nested/
escaped sources and reused/dangling logs, and reserves logs with exclusivemkdir.
Both actual wrappers have invalid-call regression tests and fresh offline
recipe dry-runs pass. Diagnostic objective rejects nonfinite/negative inputs;
all98published action/native scores remain exactly unchanged under new guards.
These fixes do not relabel old runs as new-code measurements. Full new checks
pass before commit/push:222Python/14Rust(no skips),releasebuild,Clippy,Rust/Ruff
lint/format,bytecompile,allwrapper shell syntax,33research JSON parses and
whitespace. Both hardened wrappers pass fresh offline recipe dry-runs; only
valid/invalid-call hardening, no retuned science. Pre-commit code/archive backup
`outputs/flagging-backups/20260923-preflight-hardening/code.tar.gz`,
SHA2561ab43731d4d195dbb7631f737eebb3b1e9812668ff5c20acca56296444f438c8.

Completed native/structured measured checkpoint, superseding pending entries
below. Four unmodified CARACAL native controls finish19:19:11UTC with all source/
original-mask/DATA/weight audits passing. First-pass controls~36% exceedbudget
and lose support; mild controls~0.90–1.00% retain support but worsen objective,
TV and val/test prediction. Report/archive `research/flagging-caracal.md` and
`research/results/gain-tv-caracal.json`; no native policy selected.

All seven unchanged frozen structured controls complete19:26:27UTC,101actual
QuartiCal solves. Both rank23,329identicalmasks/top8 each; all112ranked slots
are single-baseline actions, neverglobal/star. Both nochange on unmodified,
both narrowband, weaktimeburst/antenna-local. Strongtimeburst residual rank
selects11known-injected samples(2.89%recall),objective1.249904895/test−0.01985%;
TV rank choosesnone. Strongantenna-local TVrank selects8outside known injection,
objective1.249931062/test−0.00949%,zero injectionrecall; notprovenfalsepositives.
All source/export/originalflags/rows/DATA/weights/TRAIN-only audits pass.
Report/archive `research/flagging-structured.md`/`research/results/gain-tv-structured.json`.
No independent transfer, signal/image/SOTA or robustTV-guidance advantage.

After all measurements, rename only audit key no_truth_read→
no_truth_decoded_or_used_for_selection: provenance hashes label-file bytes but
does not decode/use them in decisions. Raw measured audits remain annotated;
archive verifies exact measured source reconstruction by one literal replacement
against every recorded SHA. Numerical protocol unchanged. Recipe logger fix
validated in fresh native/structured dry-runs and five actual isolated-log runs.
Firsttwo structured outer logs retained in
`outputs/flagging-backups/20260923-structured-shared-logs/`; neveruse forcostclaims.

Fresh full checks after the audit-wording change pass:196Python/14Rust(no skips),
releasebuild,Clippy,Rust/Ruff lint/format,bytecompile,allwrapper shell syntax,
32research JSON parses and whitespace. Both new recipes prevalidate locally;
four native and seven structured controls executed, no CI used as test runner.
Final code/archive backup
`outputs/flagging-backups/20260923-caracal-structured-final/code.tar.gz`,
SHA2560d0b03fbe0dce04372a2976dca9c13ca6d22db16a5f756beb810ca7959c7e82a.
Independent agent read-only review
already passed51actual checks for native+firsttwo structured states, recomputed
rankings/TVsupport/exports; extension toremainingfive ongoing. Next: calibrated
coherence/aggregate or group-balanced proposals, uncertainty-awareTV and signal
preservation; representative61antenna primary acquisition remains proposedonly.

Native implementation/partial-results/data provenance checkpoint `9a454fc` was
pushed to origin/main using the public user identity, no co-author trailers.
All local tests passed before commit, including187Python tests once the parallel
pure generator was present; the committed native implementation itself has179.

Structured matched-search implementation and recipe now have17pure tests;
clean and strong time-burst frozen experiments started19:17UTC in
`outputs/tv-structured-clean-01/` and `outputs/tv-structured-timeburst-01/`.
Both rankings have identical23,329mask families and top8budgets; shared masks
reuse one actual solve. Only single whole-rectangle proposals, no trimming or
unions; original flags/rows/DATA/weights remain protected. Source/truth/test
selection rules and module hashes are recorded before baseline solves.
Pre-run backup `outputs/flagging-backups/20260923-structured-native/code.tar.gz`,
SHA2565c76acfb44355ebd43d139c6a15f3ae45357d5a7af3aff70811d883728e5a75e.
Measured results pending; do not claim a new model or quality improvement.

Integration finding: top-level recipe static log paths override the wrapper's
global `-s opts.log.dir`, so these first two structured controls share Stimela's
outer logs/profiling. Actual copiedMS/config/frozen masks/QC logs/checkpoints are
isolated per run; no scientific-state collision. Preserve shared outer logs and
do not use their profiling as timings. Removed only the recipe's fixed log-dir
default (no algorithm/module change); validate wrapper-selected unique paths in
a fresh dry-run before commit. Native CARACAL's single outer run is unaffected
by this parallel collision but receives the same logging fix for future runs.

Handoff/rules/CARACAL source checkpoint3d561d1 pushed toorigin/main; no agent
attribution or Spotify identity. New native verification module/recipe/wrapper
implemented, measurements pending. It compares operational and artificial
holdout-masked input flags under unmodified first-pass/mild CARACAL YAMLs.
Installed Tricolour0.2.1 polynomial cycles can discard starting masks, so neither
control is advertised as unseen-holdout policy evaluation. Actual gain solves
always preserve every originalflag/row. The new implementation passed all local
checks and179Python/14Rust tests; native measurements are separately recorded.

Native default CARACAL verification started in `outputs/tv-caracal-clean-01/`:
first-pass and mild strategies × operational/holdout-masked inputs, full native
CLI withoneworker, no network, protected copies and recorded engine/mask hashes.
Baseline reproducesTV0.1474368701/validation25.20612260. Source code frozen for
this run, pre-runbackup `outputs/flagging-backups/20260923-caracal-native/code.tar.gz`.
Full new suite already passed14Rust/179Python tests(no skips), releasebuild,
Clippy,Rust/Ruff lint/format,bytecompile andshellsyntax. Both first-pass controls
completed successfully and preserved persisted original flags/rows/DATA/weights,
but propose36.207%/36.133% extra training flags, lose fixed TV support and have
unavailable validation losses. Both are rejected; no policy is chosen. Partial
archive `research/results/gain-tv-caracal-progress.json` explicitly records2of4
controls and final source audit pending. Full-strategy mild controls ongoing.
Verified non-TTY Dask progress logger adds~300seconds per native CLI call;
do not misidentify the sleeping timer as deadlock or use it as kernel timing.

Representative public data identified: `research/flagging-public-data.md` and
`research/results/meerkat-public-primary-metadata.json`. Metadata/nine numeric
chunks only, no visibility downloads or pickle decoding. Actual primary archive
has61antennas/eightscans/fullLband/XX,XY,YX,YY and supplied MODEL_DATA/nativeweights.
A proposed one-tile DATA/model/FLAG/weight acquisition would fetch353.48MiB
compressed; current~21GiB disk requires strict capacity/backups accounting.
Flag/model provenance, occupancy and support remain unverified. Closure-based
cross-check is now documented as a proposed hypothesis, not an implementation.

Structured TRAIN-only multiscale candidate generation is proceeding in parallel
with the native verification under the earlier user authorization. Root owns
integration/recipes/results; injection-controls agent owns only the new pure
candidate module/tests. Frozen residual and TV-conditioned scoring/top8 budgets
must be archived before any actual gain re-solves. No structured result yet.

Native implementation/partial-results/public-data checkpoint pre-commit checks:
release build,14Rust/179Python tests(no skips),Clippy,Rust/Ruff lint/format,
bytecompile,all wrapper shell syntax,30research JSON archives and all three
container pip checks pass. Actual native recipe prevalidation/execution is
underway on protected copies. Backup
`outputs/flagging-backups/20260923-caracal-progress-commit/code.tar.gz`,
SHA25688047647948a3b53cdf3b7d9dda2230637291cea43d1c3b0454b885c4b5c8472.

The verified baseline/follow-up commits35e763b/f782921 were pushed to origin/main
at the user's request on2026-09-23. Both author and committer are
Gijs Molenaar <gijsmolenaar@gmail.com>; no co-author/agent attribution or Spotify
email occurs in those commit messages. Attribution prohibitions and durable
handoff routing are explicit in rootAGENTS.md. Start with `research/README.md`.

The user additionally requested CARACAL strategy verification and regular pushes
of checked progress so astronomers can follow along. Official CARACAL revision
8f7bb363876f5f0daecbf2167c36bb597c7e5160 strategy/flag-worker inspection completed:
polarisation-mode fullTricolour passes/staticmasks/polynomial residual handling
are not the reduced StokesI kernel comparator. AO firstpass_Q usesStokesQ.
Report `research/flagging-caracal.md`; full native strategy measurements pending.
Current documentation/routing/rules checkpoint passed14Rust/171Python tests,
releasebuild,Clippy,Rust/Ruff lint/format,bytecompile and28archive JSON parsing.

Continuation: investigate structured multiscale baseline/antenna-shared flagging
actions without injection-truth inputs, keeping the original TV/validation/flag
budget and all original flags. Frozen proposed scope, hypotheses and primary
prior-art links: `research/flagging-next.md`. Implementation/results pending.
Pre-edit backup `outputs/flagging-backups/20260923-structured-start/code.tar.gz`,
SHA256a421d417394d256ac8024752a796f45cf46cb97ab1d091bc0f9f66fd7a9f92cb.
Current handoff/rules/planning/source-inspection changes have fresh local checks;
their checkpoint will be pushed before further implementation. Larger structured
and CARACAL verification experiments require their own measured archives/checks.

## Active flagging experiment (2026-09-23)

The user requested a model for MeerKAT flagging trained on the TV norm of
QuartiCal full complex 2x2 gains, guided by TV maps, delivered as a Stimela2
recipe. Preserve every original observatory flag and back up as work proceeds.
The clean initial revision is `39eeb53`; code and raw archive backups are in
`outputs/flagging-backups/20260923-initial/`. The existing real public SKA scan-9
fixture is the first intuition dataset. Plan and provenance are recorded in
`research/flagging.md`. An isolated public-PyPI QuartiCal 0.2.7/Stimela 2.1.4
Linux environment has been built and tested. Earlier pointing results remain valid
under their documented assumptions.

Checkpoint: complete Stimela2 pilot in `outputs/tv-flagging-pilot-03/` selected
no additional flags. Baseline gauge-fixed TV 0.1476474, raw TV 0.2701043,
validation weighted MSE 25.20588. Six nonempty proposals increased TV and none
beat no-change. This version used unwhitened policy features; test MSE was
unavailable due to unsupported baseline predictions. Original flags/data
digests survived. Archive the null result. Final strategy now whitens features,
reserves sparse-bin training data before solving, reports invalid prediction
counts and masks unsupported plot bins. Final pinned-environment replay pending.
Full local checks passed 14 Rust and 112 Python tests before the latest
sparse-bin regression addition; rerun appropriate verification after changes.

Second complete pinned-environment pilot `outputs/tv-flagging-pilot-04/` passed:
73,720 train / 9,115 validation / 9,169 test samples; zero invalid predictions.
Gauge-fixed TV 0.14743687, raw TV 0.26732583; validation MSE 25.20612, test MSE
24.91961. Five nonempty proposals raised TV; no additions selected. Original
flags and final DATA array verified unchanged. Latest suite passed 113 Python
tests before the final telescope/band guard regression. User explicitly
reaffirmed MeerKAT L-band only; OBSERVATION identifies MeerKAT, project
20230103-0005. Preparation now enforces MeerKAT and nominal 856–1712 MHz channels.
Final scope-guarded recipe replay: `outputs/tv-flagging-pilot-06/`, passed.
The scope-guard startup caught a casacore string-list `.tolist()` assumption;
explicit NumPy conversion fixed it. No original observation was modified.

Final flagging checkpoint (2026-09-23): recipe implements prepare/train/report,
QuartiCal full complex 2x2 inner solves, Rust masked Frobenius TV with fixed
support/scale, unpolarized polar-gauge handling, noise-weighted TV-conditioned
outlier policy, original-flag lower bounds, per-write backups, flag budget,
fixed validation and test checks, and explicit MeerKAT L-band metadata guards.
Final run reproduced the prior no-change result, with zero invalid predictions,
test MSE ratio 1.0, all 1,074,094 original flag cells/rows and final DATA preserved.
Results/provenance archived in `research/results/gain-tv-flagging.json`;
method and limitations in `research/flagging.md`; recipe `recipes/tv-flagging.yaml`.
Verification passed release build, 14 Rust/114 Python tests (no skips), Clippy,
Rust/Ruff lint/format, byte compilation, dependency and whitespace checks, and
the full pinned container recipe. Final backup is
`outputs/flagging-backups/20260923-final/`. This checkpoint is the baseline for
the user-requested commit before parallel follow-up work.
No flagging/imaging improvement or native-performance advantage established.
Next scientifically relevant checks: accurate L-band calibrator sky,
RFI/signal injection controls and matched established flagger comparisons.

User authorized parallel follow-ups and a commit of all current flagging work.
Four workstreams: injection/oracle controls, SARAO multi-component sky,
QuartiCal MAD/Tricolour comparators, and measured patch-action TV benefit.
Each must use fresh isolated outputs and writable MS copies. The learned-policy
scientific assessment depends on the controls, even if implementation proceeds
in parallel. Detailed proposed scope and references are in `research/flagging.md`.
Fresh pre-commit verification passed: release build, 14 Rust and 114 Python
tests, Clippy, formatting/lint, container build/dependency consistency, research
JSON parsing and the complete Stimela2 replay in
`outputs/tv-flagging-precommit-01/`. Replay reproduced no additions, TV
0.14743687, test MSE ratio 1.0 and preservation audits. Pre-commit code backup:
`outputs/flagging-backups/20260923-precommit/code.tar.gz`, SHA256
`ab9a0c849041a418a6abce788a25f4dcac1d336883b2ffe2e1516ff4004b4c01`.
No follow-up quality improvement is yet measured.

Parallel execution checkpoint: baseline committed as `35e763b` under
`Gijs Molenaar <gijsmolenaar@gmail.com>`; no push requested/performed. Three
delegated workstreams own injection, calibrator-sky and comparator modules,
recipes, tests and reports; root owns action-benefit and suite integration.
Individual branches use fresh copied MS and isolated compatible tool venvs.
Crystalball's psutil requirement conflicts with Stimela; Tricolour's legacy
Numba requirement conflicts with QuartiCal. Separate `/opt/sky` and
`/opt/tricolour` environments resolve these without altering the base solver.

Action branch completed `outputs/tv-flagging-actions-01/`: 16 disjoint
counterfactual patch re-solves, 10/3/3 train/validation/test actions, seed29.
Fifteen removals increased fixed-support TV. One validation-action removal
lowered TV0.172% but worsened validation/test MSE0.117%/0.177%; this illustrates
that smoother fitted gains do not necessarily predict held-out data better.
Ridge model test-action MSE2.971197e-6 exceeds constant-control1.670672e-6;
selected no additions. Original flags/data/source/copy audits passed. Compact
archive `research/results/gain-tv-actions.json`, report `research/flagging-actions.md`.
Parallel Stimela2 recipe `recipes/tv-flagging-parallel.yaml` prevalidates under
installed2.1.4 with native `for_loop.scatter=4`; full concurrent execution is
not yet verified. Suite image successfully combines the two separate venvs
and passes all three pip checks. Injection, sky and comparator pilots remain
in progress; retain their checkpoints and do not claim scientific improvement.

Further parallel checkpoint: all six injection cases passed, 49 actual solves.
Strong time-burst injection-only oracle improves currentobjective1.25→1.24873479
while proposalpolicy choosesnochange. Oracle is evaluation-only. Three-sky
control passed: fullcatalog improves val/test MSE~1.20%/~0.98% vs officialprimary
but slightly raises TV. Clean and strongnarrowband comparatorpilots passed with
nochange; packaged Tricolour dilation expandsrandomholdoutholes and is retained
as negativecontrol, explicit holdout-safe settings tested separately.
Root actionpilot on copiedtimeburst completed16 re-solves, source/flags/DATA
audits passed, nochange; predictor testMSE9.546514e-7 vsconstant9.397650e-7.
Full suite is running native scatter4 in `outputs/tv-flagging-parallel-01/`;
sky and action branches complete, comparator/injection branches ongoing.
Review found generic preparedDir trust/nesting safety gaps; new original-state
and split validation helper is being added before commit. Trusted measured
inputs are consistent and no original flags/data were lost. All follow-up
findings remain local/uncommitted pending integration checks.

Final parallel checkpoint (supersedes the in-progress entries above): all four
native Stimela2 scatter workers completed in
`outputs/tv-flagging-parallel-01/`, 18:21:29–18:28:32 UTC, no failures. Individual
and concurrent pilots reproduce the negative findings summarized in
`research/flagging-parallel.md` and `research/results/gain-tv-parallel.json`.
No flagging/imaging superiority or native-performance advantage established.
The strong time-burst evaluation-only oracle improves the guarded objective;
current proposals and ridge action learning still select no-change. Fullsky
predicts held-out data somewhat better while slightly increasing gain TV.

Prepared-input safety integration completed: actual original flags/rows and
native weights are authoritative, saved/work data and metadata must agree,
eligible splits must be disjoint and manifest channels/count/grid coherent.
Nested source/output paths are rejected before creating outputs. Fresh gated
action and comparator Stimela smokes passed. Final helper
SHA2568c1878cdaa3259ca2e5416b78df2a89544a87cea86aa1b47099eaf4b3d96e8ab
independently audited 24 completed prepared inputs read-only, including every
concurrent branch/case; source/original digests, final DATA/native weights and
original flags passed. An in-memory original-flag tampering probe was rejected.
The original scientific runs predate these new guards and remain versioned,
not silently relabeled as reruns of the strengthened implementation.

Fresh full local verification: release build,14Rust/171Python tests(no skips),
Clippy,Rust/Ruff lint/format,byte compilation,shell syntax,27result JSON archives
and whitespace checks passed. All dependency environments and containers were
built/checked locally; no CI used as a test runner. All six final Stimela recipe
schemas passed dry-runs without touching real data. Final backup directory:
`outputs/flagging-backups/20260923-parallel-final/`. The follow-up checkpoint
contains code and compact measured findings; raw MS/catalog/gain outputs stay
ignored, never added to Git.
Baseline commit35e763b is local; no push requested or performed.
Next discriminating scientific work is broader coherent action proposals and
independent MeerKAT L-band observation/image/signal-recovery checks, not an
assumed neural-network or TV-only solution.

## Earlier pointing checkpoint

Handoff documentation supersedes the historical in-progress entries below:
`research/status.md` is the current scientific assessment and
`research/development-roadmap.md` specifies the next go/no-go experiment.
The antenna-beam work was committed and pushed as `2b5211a`.
README smoke testing found complex gains could not be serialized by
`examples/pointing.py`; real/imaginary arrays now preserve these outputs and
an end-to-end CLI regression covers the failure. Both README examples run;
the seed-7 joint antenna-width campaign converged in all eight cases.
Final verification passed: release build, 12 Rust and 107 Python tests with no
skips, Clippy, Rust/Ruff formatting, Ruff lint, byte-compilation and whitespace
checks. All 20 result JSON archives parse and handoff local file links resolve.
Verified environment and smoke results are recorded in `research/status.md`.
This checkpoint includes the documentation, export fix and regression test;
next research work is the roadmap's focused algorithm comparison, not a novelty
claim. Generated outputs and local environments remain ignored and uncommitted.

## Historical checkpoint log

Entries below describe their state at the time, not outstanding current work.

- Antenna-beam checkpoint full verification passed: release build,12Rust tests,106Python tests, Clippy, Rust formatting, Ruff lint/format and whitespace checks. This includes the relative/common uncertainty split and existing solver paths. Ready to commit; continue after checkpoint.

- Component-wise coverage replay completed: omitted antenna widths relative17.0%, common41.3%, total26.3%; jointwidth relative95.7%, common85.4%, total89.4%. Mean median relative std0.868 vs0.899arcsec: bias removal, not interval inflation. Same12noise/fixedtruth71, correlated coordinates; no precise coverage guarantee. Replay archived separately (`antenna-beam-coverage-components.json`), not counted as new independent trials. Report `antenna-beam-widths.md` and README linked; latest full checks running after uncertainty split. Next independent adequacy/signal-recovery validation; no novelty or measured-data calibration claim.

- Heterogeneous-beam result archived in `results/antenna-beam-widths.json`: 168fit configurations (144three-seed stress/prior +24fixed-truth noise). Ignored widths relative6.30–9.26arcsec/test2.60–3.98; sharedwidthalone6.33–9.19/test2.60–3.99; inferredrelativewidthσ.03 gives0.79–1.10/test1.049–1.051, widthRMSE2.33e-4–3.55e-4. σ.003 comparable; overconfidentσ.0003 leaves3.17–4.36arcsec/test1.43–1.72. All converge. Twelve-noise truth71 total-pointing95%coverage26.28% omittedwidth vs89.43% fittedwidth; relative-widthcoverage94/96, fluxratio34/36 fitted vs28/36 omitted. Correlated coordinates/one truth, no precise confidence claims. Full checks passed12Rust+106Python before newest uncertainty-output split.
- New follow-up: return marginalized relative and common pointing standard deviations separately from total physical-pointing std. Replaying both12noise pilots with split coverage diagnostics; full tests need rerun after this change. This avoids conflating robust relative pointing with weak shared-mode inference. No commit yet for antenna-beam work.

- Relative antenna-width inference passed noiseless combined recovery; all6 three-seed heterogeneous-beam/prior campaigns finished (144fits). Inferred contrasts recover width deviations to about2–3e-4 log width and restore~1arcsec pointing in initial0.03prior results. Stronger-prior controls0.003/0.0003 retained. Twelve-noise fixedtruth71 coverage campaign with joint antenna widths finished; paired omitted-antenna-width coverage run and full checks running. Do not equate this matched-family inference with novelty: BIRO already precedes joint pointing/beam inference. New docs/archive pending; no commit until full checks pass.

- Heterogeneous-beam continuation: 1% pre-demean antenna log-width scatter yields roughly8–9arcsec relative pointing errors despite correct quadratic spectral gains; a shared-width fit does not fix it. Known-per-antenna oracle control completed. Added inferred zero-mean log-width deviations (N−1 orthonormal contrasts) plus optional shared width, avoiding a redundant common width parameter. Full prior Jacobian uncertainty now includes marginal relative antenna-width std. Combined common-pointing/shared-width/relative-width noiseless test and finite differences passed (15 beam tests). First inferred-width campaign running/completing; prior sensitivity0.003 and0.0003 (default0.03) running. New code/results uncommitted; no full checks yet.

- `811bed9` chromatic/polynomial checkpoint pushed. Continuing gate1: optional known per-antenna scalar log-width corrections in tabulated beam predictor, with common-width and shape callbacks retaining them. Example injects independent demeaned antenna width errors using a separate reproducible seed stream; optional explicitly labelled known-beam oracle control. Targeted uniform-width equivalence, autodiff/finite-difference locality and input-validation tests plus first0.01scatter campaign running. No heterogeneous-beam recovery result claimed yet; new changes uncommitted.

- Chromatic/polynomial checkpoint verified: release build,12Rust tests,100Python tests, Clippy, Rust formatting, Ruff lint/format and whitespace checks all passed. Degree0/achromatic equivalence, polynomial joint noiseless recovery with time-varying spectral phase+amplitude, and invalid option combinations covered. Prior-art boundary explicitly linked to Yatawatta2015 frequency-smooth distributed calibration; no polynomial novelty claim.

- Gate2 follow-up now168 archived fits across7 campaigns, all converged. Degree1 gain model + fitted spectra uses192 total parameters vs312 independent-channel, with linear-truth relative0.726–1.038arcsec/test1.016–1.039. Added quadratic truthscale0.5 breaks degree1 (relative4.75–6.28arcsec/test17.2–32.4); degree2 restoresrelative0.724–1.065/test1.043–1.047 with252params, channelbaseline0.754–1.090/test1.059–1.065. This is expected matched-family compression, not novelty; priors differ across parameterizations. Archive `research/results/chromatic-gains.json`, report `research/chromatic-gains.md`. Expanded noiseless time-varying chromatic phase+amplitude tests and invalid-option controls passed46 targeted tests; new degree0 equivalence test/full checks pending. Continue with independently validated model adequacy and out-of-family beams/bandpasses, not claims from inadequate baselines.

- Gate2 chromatic-truth campaign completed72 fits, all converged. Achromatic joint fit: relative18.9–26.4arcsec, held-out whitened mean square543–619. Independent channel gains restore relative0.759–1.094arcsec and test1.054–1.065. Adding spectral-index priors0.1 changes relative little but common error grows from0.20–0.29arcsec to0.70–1.46arcsec (matched beam, commonprior0.5arcmin). These are assumed linear spectral log-gain slopes, not measured bandpasses. Results in ignored outputs/*commonprior0.5*chromatic1*.
- Implemented optional gain_frequency_degree Chebyshev log-gain coefficients (degree+1 rather than one coefficient per channel, tensor time-spline basis). Independent coefficient priors explicitly differ from independent-channel priors. Returns frequency-labelled gains and basis metadata. No state-of-the-art or novelty claim. Noiseless joint recovery tests expanded; targeted checks and24fit linear-degree+spectral-prior campaign running. Changes uncommitted.

- `f270342` committed and pushed with structured projection benchmarks and public-MS reader. Continuing gate2: `examples/relative_pointing.py` now injects optional smooth frequency-dependent log-gain slopes (linear frequency coordinate around1.3GHz per0.4GHz), independent of fitted gain flexibility. Optional spectral-index priors added to joint-flux/gain-only cases and prediction uses fitted spectra. Three-seed campaigns running: achromatic fit, per-channel fit, per-channel+spectral priors, all with commonprior0.5arcmin and true slope scale1. New script changes uncommitted; no conclusions yet.

- Checkpoint verification passed: release build,12Rust tests,91Python tests, Clippy, Rust formatting, Ruff lint/format and whitespace checks. Digest-pinned public-PyPI Docker reader build and actual read-only archive inspection also passed. No raw observation files or upstream source downloads are committed.

- Ready-to-checkpoint: public-MS inspector/container verified; structured projector and internal Rust layout optimized. Final isolated scaling run (after tests completed) archived:64-size full NumPy0.1525s/312.2MiB, grouped NumPy0.0621s/133.5MiB, grouped Rust0.1713s/134.0MiB; rank634, Gram relativeerror<5e-16. No full-array geometry, sky/beam simulation or end-to-end calibration in this matrix benchmark. Full checks passed12Rust+89Python before two additional empty-shared projector tests; final rerun pending. Continue afterward with realistic gain/beam mismatch, not another claim based only on kernel speed.

- Scaling continuation: synthetic gain-incidence matrices at8/16/32/64 antennas and4 channels, isolated workers and whole-process peakRSS. Found poor row-major access in Rust QR. Internal column-major storage plus four-lane dot accumulation cuts64-size grouped Rust median1.359s→0.173s; NumPy/Accelerate still~0.062s. Shared/target derivatives random: not a MeerKAT observation or calibration benchmark. Exact Gram/rank checks pass~5e-16. Five-repeat final campaign underway; native full checks running after added scale/remainder tests. Important correction: NumPy uses Apple Accelerate, so OPENBLAS_NUM_THREADS=1 does not establish single-thread execution. Record environment and backend, not an unmeasured thread count.

- Active continuation: `fdf5883` pushed after full checks (11 Rust, 73 Python). Frequency-blocked gain elimination now implemented and tested against dense information, including exact gauge/flux-anchor controls. An additional regression caught and fixed promotion of already-eliminated shared nuisance round-off to rank. Five warmed repetitions: dense median1.520s, time-blocked Rust0.178s, frequency-blocked Rust0.153s, frequency-blocked NumPy0.151s. Same information to~2.6e-11 absolute. Ordinary structured elimination, not a novel algorithm or competitive-calibrator benchmark. New full checks pending.
- Public SKA MeerKAT `outer_scans.zip` inspected via network-disabled, read-only amd64 casacore container using public PyPI wheels; host ARM/macOS reader unavailable. Archive SHA256 d4dae56f7ad1bb4a49ab8c4a3846871d5b8ebb4b731ee958cb9f1baf3306144f, 45,452,147 bytes, five MS (not six), four antennas m000–m003, J1939-6342, 4096 channels856–1711.791MHz, 42–47% flags. All POINTING.ANTENNA_ID values0; antenna-major timestamps match upstream reshape, but physical label assignment not independently established. TARGET/SOURCE_OFFSET tagged J2000 while upstream interprets AzEl/xel-el. Do not fit silently or claim real-data pointing recovery. Inspector and Docker recipe uncommitted; rawdata and downloaded upstream source kept ignored under outputs. Next: document reader barrier, checkpoint verified implementation, advance larger structural scaling and real-data convention validation.

- Beam-selection and common-prior campaigns archived and documented. Rich beam selection (192 fits) brings four truth families to mean held-out residual~1.042 and mean maxflux-ratio errors0.014–0.033%; one-width chromatic fit instead has~1.10% bias despite lower residual than fixed beam. Enumerating candidates is not cheaper and no superiority over always-rich joint fit established. Two-candidate96fit baseline retained. Common-prior72fit sweep: trueconstant(+30,-30)arcsec, jointflux + matchedkatbeam gives relative0.74–1.03arcsec, common0.17–0.37arcsec, test~1.01–1.02 for priors0.1/0.5/3arcmin. Restricted gain/sky/spline model and constant truth are not unrestricted Gaussian gauge. Full checks running. Continue after checkpoint; do not treat commit as terminal.

- Active continuation: user explicitly asks not to stop at commits. Separate train/validation/test beam-model selection campaign implemented (12 seeds, four truth families). Two-candidate baseline exposes lower residual yet worse flux ratios for chromatic width error. Expanded beam callback/solver to three physical parameters (log width, chromatic log-width slope at1.3GHz per0.4GHz, log-axis ratio), with independent optional priors/zero-fixed coordinates. Rich four-candidate campaign completed192 fits; derivative/noiseless tests passed. This is ordinary model-selection baseline, not novel. Results/docs pending archive.
- Gate6 continuation in progress: optional common pointing spline with zero-centred knot prior, explicitly separated from zero-mean relative offsets; physical total returned in offsets_arcmin. Requires zero_mean_pointing and fit_pointing. Prior sweep0.1/0.5/3arcmin running on matched katbeam, gains and fluxes jointly fitted. New common-mode tests/full verification pending. Do not claim prior-independent recovery from this restricted model.

- Checkpoint verified: release build, 11 Rust tests and 68 Python tests, Clippy, Rust formatting, Ruff lint/format and whitespace checks passed. New tests cover SVD propagation against analytic linear covariance, rejection of singular precision, frozen-parameter uncertainty, joint width autodiff and noiseless recovery.

- Gate5 pilot: optional local Gauss–Newton uncertainty from SVD of full residual+prior Jacobian; marginalized pointing/flux/flux-ratio/beam-width std. Rank-deficient precision rejected, noise not rescaled. Twelve independent noise seeds at fixed truth71 give correct-beam pointing coverage96.0%, flux-ratio35/36; fixed1% wrong width pointing85.6%, ratio0/36. Coordinates/ratios correlated, one truth only: no precise coverage guarantee.
- Added shared beam log-width inference through tabulated callback, optional prior0.03. Same wrong-width noise pilot restores pointing coverage96.0%, flux-ratio34/36 and mean held-out residual1.030, recovered multipliers1.009765–1.010264. Known-family control, not novel or arbitrary-beam robustness. Gate7 contiguous time-gap control implemented, three zero-common joint test residuals1.0108/1.0136/0.9897. Archive/doc `uncertainty-coverage.md`. Gates5/7 only pilot; gate6 common-prior sweep still pending; gates8–10 unchanged. Full checks running including new derivative/recovery/uncertainty tests.

- User clarified novelty must mean better calibration/imaging quality or comparable quality with less runtime/resources than state of the art. Persisted in AGENTS.md and `development-roadmap.md`. Toy wins alone are insufficient.
- First passes of gates 1–4: 96 stress fits across width mismatch, independent fitted channel gains, out-of-family ripple and missing source. Report/archive `robustness-stress.md` and `results/robustness-stress.json`. Width +1% leaves 1.09–1.46 arcsec pointing but biases flux ratios 0.53–0.76%, held-out residual 2.38–2.57. Ripple 6 arcsec/90 min yields ~4.32 arcsec errors. Missing 20mJy source yields 12.57–12.88 arcsec errors, residual160–165. All convergence flags true; convergence is not correctness.
- Added optional `gain_per_channel=True` in JAX solver; independent spline coefficients at each observed frequency, gain cube shape(time,frequency,antenna) and frequency labels returned. Default achromatic shape unchanged. Channel-dependent noiseless recovery controls added. Full checks running. Remaining within gates1–4: heterogeneous beams/squint, smooth spectral gain truth, jumps and extended/spectral sky errors. Gates5–10 not completed; no measured-data drift fit or state-of-the-art advantage claimed.

- Verification for this checkpoint: release build, 11 Rust tests, 63 Python tests, Clippy, Rust formatting, Ruff lint/format and whitespace checks passed. Held-out campaign completed all 24 fits successfully and results archived with fixture/beam provenance.

- Public 892 KB SARAO pointing-history downloaded into ignored outputs; CC BY-NC 4.0 provenance in `pointing-history.md`. Safe NPZ inspection finds 2x64x881 array, 2019–2022 timestamps, missing values, five duplicate timestamps and 53.8% exact adjacent antenna repeats. Coordinate/assembly/freshness conventions unresolved, so no empirical temporal covariance or six-hour interpolation claimed. Inspector script saves local summary/hash. Raw data not committed.
- Held-out benchmark implemented with six whole withheld times (2016 train / 672 test complex rows) and exact frozen-pointing gain/sky-only baseline. Three seeds, 24 fits: zero physical mean joint test clean RMS 0.220–0.247 mJy versus baseline 2.566–2.724; whitened test residual 1.011–1.023 versus 4.329–4.773. Nonzero shared physical pointing still fails adequacy (31.4–32.4). Matched beam and spline assumptions; synthetic trajectories, not historical data. Added gain-only recovery test; full checks running. No claim of real-data validation or resolved common-mode ambiguity.

- Joint nonlinear smooth achromatic gains implemented in `solve_pointing` via optional `gain_prior_sigma=(logamp_sigma, phase_sigma)`, same spline knots, antenna-zero phase reference, proper knot priors. Existing spectral/mode paths retain standardized nuisance priors. Noiseless anchored-flux test recovers pointing, gains and sky; four invalid-prior tests added. Three-seed/18-fit katbeam campaign archived in `results/joint-gain-pointing.json`: zero physical mean + joint flux gives 0.575–0.888 arcsec relative RMSE, wrong fixed sky 6.51–6.90. Nonzero common offset still mismatched (residual mean square 31.7–32.8); gain model is restricted achromatic, not the free-channel Gaussian gauge. Absolute flux scale remains prior-dependent in campaign. Held-out/gain-only/beam-error tests still pending.

- Zero-mean recovery campaign: `examples/relative_pointing.py`, three seeds, six cases each, full toy rows and scalar katbeam H. Known unit gains/exact beam. Zero physical mean: joint flux recovery 0.63–0.88 arcsec versus 5.67–6.22 arcsec with fixed ±2% wrong sky. Physical (+30,-30) arcsec common offset: joint flux relative error 3.48–3.98 arcsec but whitened residual mean square ~35.6, exposing restricted-model mismatch. All fits converge, numerical zero mean maintained. Archived results and `research/relative-pointing.md`; next joint nonlinear gains, not a claim against the gauge convention. Full checks: 11 Rust and 57 Python tests passed before campaign addition; rerun underway for checkpoint.

- Oleg recommends imposing zero mean per-antenna pointing rather than trying to recover the nearly degenerate shared offset. Implemented opt-in `zero_mean_pointing=True` in the smooth solver using an orthonormal antenna contrast basis at every knot. Linear spline interpolation preserves the constraint at all times; two coordinates per knot are removed, not softly penalized. Existing default retained for reproducibility. Added known-sky noiseless relative-recovery tests, including mode selection. This is a conventional identifiability constraint, not a novelty claim; unknown physical common pointing can still cause mismatch under restricted sky/gain models. Joint gain/sky nonlinear validation remains pending.
- Structured audit implemented in the working tree: Rust column-pivoted Householder QR with checked Python C-ABI wrapper eliminates time-local gains and differential offsets; a reusable compressed design preserves information for sky/common-mode audits and external flux priors. Native katbeam H benchmark: dense median 2.005 s, blocked Rust 0.177 s, blocked NumPy 0.160 s (three warmed runs each). Maximum information-matrix difference from dense approximately 2.6e-11. Speedup comes from blocking; Rust is not faster than NumPy here. Dense nuisance matrix 5376x1934 becomes local 224x78 blocks and a 432x64 retained design. These sizes are not peak-memory measurements. Benchmark artifact: ignored `outputs/blocked-benchmark/results.json`; reproduction: `examples/blocked_benchmark.py`. Local nuisance smoothness cannot be imposed after independent elimination.

- Extended session started2026-09-11 09:32:54UTC, targeting approximately two hours of development (to11:32:54UTC). First checkpoint: public PyPI katbeam0.1 installed (7.9KB wheel). Runtime L-band table900–1650MHz differs from current GitHub; pinned/hash provenance. Implemented stable differentiable cosine taper, table validation/no extrapolation, H/V scalar adapters and custom predictor callbacks in smooth solver/audit. 14 ablations show native measurement-informed bounds~8arcsec; freezing axis ratio gives~100–120arcsec; native-width Gaussian~8–9arcsec; fixed-shape Gaussian, circular profile and no rotation remain degenerate. Report `research/katbeam-pointing.md`, script/archive. Beam known exactly; not measured visibility calibration. Next: structured audit computation, beam-parameter uncertainty, joint nonlinear recovery.

- Implemented local external-flux information budget: optional positive-definite correlated log-flux covariance in `sky_locked_information`, with standalone data, externally conditioned data, external-prior and total information matrices. Generalized fractions compare standalone data to total, not posterior-variance fractions. `examples/information_budget.py` runs eight controlled cases. Gaussian with independent1% flux errors yields local σ[6.269,6.731]arcsec but zero standalone data fraction; 5% gives[31.341,33.642]. Quartic.1 with1% gives[5.907,6.297] and0.75–1.34% data-only fraction. A common5% flux-scale error changes neither; channel-correlated priors tighten constraints via spectral knowledge. Report `research/information-budget.md`, archived matrices/covariance definitions. No measured-beam validation or nonlinear recovery claimed.

- Removed the separate review brief and its links at the user's request; the main scientific note remains.
- Review package prepared: expanded formal derivation/prior-art boundaries in `research/gaussian-gauge.md`, and `research/sharing-draft.md` (not sent). Added 21-point gauge sweep with fixed noisy data: maximum prediction difference1.35e-15 Jy; chi-squared5424.231020291 varies7.01e-11. Reproducible SVG in `research/figures/gauge-orbit.svg`, visually inspected via local raster rendering. Results now record source/fixture/binary SHA-256 plus runtime versions. Additional regression checks composition, noisy likelihood and failure of collinear anchors. Analytic heterogeneous-metric corollary included but explicitly not simulated. Literature comparison includes Pointing SelfCal, RIME ambiguities, BIRO, identifiability work, blind ptychography and measured MeerKAT beams; novelty remains unconfirmed. No message sent to professor.

- Important correction to earlier lead: freeing the 46 remaining common temporal modes restores both Gaussian null directions. Derived exact finite gauge h(t)=Q^-1 R(t)a, accompanied by source/channel flux and antenna/time/channel gain transformations. Seed61 finite test with nonzero smooth differential offsets and complex gains: 34.95 arcsec pointing difference, max visibility difference9.31e-16 Jy for ratio1.1. Implemented `rangtoy.gauge`; report `research/gaussian-gauge.md` supersedes unrestricted interpretation of beam-rotation results.
- Generalized local audit now supports common temporal complement, synthetic quartic log-beam shape and exactly fixed source/channel flux anchors. Full eight-antenna coverage with all gain/differential/common nuisances: Gaussian ellipse rank0; quartic .01 rank2 with local bounds561/586 arcsec, quartic .1 bounds57.7/60.0 arcsec. Circular beam remains rank0 at zero pointing. Central flux anchor alone rank0; central+one off-axis rank1; central+two non-collinear off-axis rank2 (perfect-flux assumption). Reproducible `examples/gaussian_gauge.py`; archive `research/results/gaussian-gauge.json`. Measured beams and nonlinear joint recovery remain pending; no confirmed novelty claim.

- Frequency-dependent gain/differential-pointing audit implemented and run: `examples/gain_observability.py`, archived `research/results/gain-observability.json`. New Rust `--pointing-full-reference` exports all 2688 rows for the same eight antennas (not full MeerKAT). With 1536 unconstrained real antenna/time/channel gain columns plus 336 zero-mean per-time pointing columns and 16 channel-flux columns, the rotating ratio-1.1 model retains both shared modes: local bounds [1.107, 1.066] arcsec. Thinned 538-row fixture loses both modes under the same nuisance assumptions. Complete circular control still degenerate. Other common temporal modes and beam shape remain fixed; nonlinear joint nuisance recovery still pending. Tests verify full/thinned consistency, all baseline coverage, and both rank controls.

- Gain-nuisance extension of the local symmetry audit: optional constant or per-time complex antenna gains, shared across frequency, projected jointly with free source/channel amplitudes. Both shared pointing modes survive ratio-1.1 rotating-beam audit; local coordinate bounds change from [2.068, 1.916] to [2.549, 2.405] arcsec with 384 gain columns. Not a nonlinear gain/pointing recovery result. Regression covers nested information loss and preservation of circular-beam ambiguity. Reproduction: `examples/observability.py` (seven cases). Public SARAO L-band metrics download returned HTTP 502; measured-beam validation remains pending.

- New concrete physical lead: exact sky-locked common-pointing/sky degeneracy for identical circular beams and unconstrained source/channel amplitudes. Measured pilot error energy is 99.9% in this two-dimensional shared trajectory. Implemented `rangtoy.observability`, local sky-prior-free audit, and nonlinear variable-projection solver; see `research/beam-rotation.md`. Generic mode truncation remains a negative accuracy result.
- Controlled 20-noise-realization shared-mode test: circular-beam fits refused; correct rotating ratio-1.1 beam recovers 1.787 arcsec RMS; wrong fixed ratio1.08 gives 51.929 arcsec; jointly fitting ratio from circular initialization restores 1.859 arcsec. Sixteen source/channel fluxes free, no spectral prior. Other pointing and DI gains fixed. Not a confirmed first-in-literature contribution or general telescope result.
- Exact finite gauge, local rank controls, nonlinear recovery, and shape recovery tests pass. Reports `research/beam-rotation.md`, `research/spectral-pointing.md`; combined summaries under `research/results/symmetry-and-spectral-campaigns.json`. JAX-only new paths preserve Rust baseline.

- Work toward a defensible contribution: optional spectral-index priors and prior-whitened, sky-marginalized pointing-mode truncation are implemented. Expanded `examples/sky_uncertainty.py`; new `examples/mode_selection.py` gives both full/selected solvers identical five-value smoothing grids with separate train/validation/test times.
- Spectral mismatch (alpha ±.1, flux ±2%, 20 seeds, 1 mJy noise): flux-only joint fit gives 68.51 arcsec pointing error despite improved residuals; jointly fitting spectra gives 4.132 arcsec. At 10 mJy, fixed-smoothing selection keeps 56/96 modes and improves 19.27→18.13 arcsec. Equal-budget validation tuning removes pointing advantage: full 18.5009 vs selected 18.4975 arcsec, selected mean 44.8/96 modes. Do not claim a new accuracy improvement.
- Current runs: `outputs/spectral-20`, `outputs/spectral-noisy-20`, `outputs/mode-cv-20`; three-seed physical decomposition in `outputs/common-mode-pilot` shows flux-only spectral-error failure is mostly array-common (68.79 arcsec common versus 4.79 differential). Investigating sky-locked/parallactic-frame ambiguity, not yet a validated novelty claim.
- Additional close precedents reviewed: Sob et al. 2021 solution interval selection, Tasse 2014 nonlinear Kalman calibration, Fisher/score compression and low-rank methods. Absence of exact search matches does not establish novelty.

- Added optional per-component Gaussian flux priors to smooth-pointing inference; zero sigma fixes a component, None preserves fixed-sky behavior. Returns fitted fluxes; prior-normalized additive corrections are differentiated jointly with spline coefficients.
- Three 20-seed campaigns (180 converged fits, including duplicate paired controls): 2% source-flux errors cause 30.237 arcsec fixed-sky pointing RMSE; 5% joint flux priors recover 2.475 arcsec vs 2.402 correct-sky control. Held-out RMS 3.682 → 1.067 mJy/component. Overconfident 0.01% priors leave 28.187 arcsec error. Matched-sky joint fit costs a small increase to 2.475 arcsec.
- Results and reproduction: `research/sky-uncertainty.md`, `research/results/sky-uncertainty.json`, `examples/sky_uncertainty.py`. Fixed source layout/sign pattern, exact central flux anchor and correct spectra/beam remain limitations. No new-algorithm claim.

- Converted all 18 display equations across four research documents to GitHub-supported fenced math blocks; equations unchanged. Documented the formatting convention in CONTRIBUTING.md.

- User/professor focus: pointing-error solutions; explicitly requested component-list conversion, DFT prediction, JAX automatic differentiation and smoothly time-varying per-antenna offsets. Implemented optional `rangtoy.pointing` with natural cubic spline trajectories, integrated-curvature regularization and SciPy least squares using JAX Jacobians.
- Public PyPI explicitly required by user; isolated `.venv` installed JAX/JAXlib 0.11.1, NumPy 2.5.3, SciPy 1.18.1, pytest 9.1.1 and Ruff 0.16.7. Do not use the Spotify registry. Rules saved in AGENTS.md.
- Rust `--pointing-reference` exports deterministic prediction/analytic-derivative fixtures; JAX comparisons, finite differences, spline controls and noiseless recovery passed (7 new tests).
- Initial smooth-pointing example (seed 7, noise 1 mJy/component, six knots, smoothness .01): 2.005 arcsec trajectory RMSE, held-out residual RMS 2.635 → .950 mJy/component. Sinusoidal truth differs from spline fit; sky/beam remain exactly known. Full details in `research/pointing-solutions.md`.
- Saved smooth-pointing numerical summary and dependency-free SVG trajectory figure under `research/results` and `research/figures`. Full local check passed with 9 Rust and 15 Python tests, including JAX, plus Clippy and both format/lint checks.

- Public repository created and verified at `https://github.com/gijzelaerr/rang`; initial public commit `2587480`. Both author and committer use `gijsmolenaar@gmail.com`; this identity is configured locally and required by AGENTS.md.
- Presentation revised: result-led README, contributor guide, clear implementation status and linked reproducibility material. Current contribution assessment is `research/novelty.md`.
- Targeted prior-art review adds robust ellipsoidal beamforming and partially constrained CMB component separation as strong objections to broad novelty. The sharper candidate uses separate response-distortion and model-error sensitivity budgets for physical calibration selection; specified, not implemented or demonstrated.
- Next discriminating work: complete-estimator derivatives and uncertain bright-source/beam perturbations with matched joint-inference baselines. No novelty claim is warranted by current results.

- Added shared log-beam-width fitting (17 physical parameters), analytic derivative test, and end-to-end width-mismatch recovery test. JSON keeps pointing arrays at 16 elements and reports fitted width separately.
- Twenty paired seeds 1–20: 2% width mismatch gives fixed-width joint flux 34.269 mJy versus width-fitting 20.124 mJy (truth 20). Corresponding injection response is 99.748% versus 99.990%; held-out RMS 11.706 versus 9.976 mJy. Matched-width flux 20.030 versus 20.081 mJy. Adaptive protection still gives no added benefit.
- Professor-facing discussion note: `research/first-results.md`; machine-readable campaign summary in `research/results/beam-width-campaign.json`. Raw runs and inspected plots in ignored `outputs/campaign-{matched,width}`.
- BIRO (Lochner et al. 2015, including Smirnov) directly precedes joint flux/pointing/beamwidth inference. Explicitly cited; no novelty claimed.
- Full release build, 9 Rust tests, 8 Python tests, Clippy, Ruff and both format checks passed after implementation.
- User authorized pushing and supplied `https://github.com/gijzelaerr/rang`. Both Git HTTPS and authenticated GitHub CLI report repository not found. Asked asynchronously for creation/visibility permission or access correction; do not create without that choice. Earlier approval classification issue was resolved enough to run the explicit supplied-URL checks; current problem is repository availability.

## Earlier checkpoints

- Request: review recent radio calibration/imaging and related fields, then identify a plausible new mathematical method, including non-coplanar geometry and 3D propagation.
- Repository initially contained no implementation or research documents; existing `.gitignore` was preserved.
- Completed a targeted primary-source literature investigation. Findings and a detailed candidate method are in `calibration-research-2026-09-11.md`.
- Current user scope: MeerKAT only. Active specification is `meerkat-scope.md`. The original report remains background and is marked superseded for experiment scope.
- User implementation conventions: Rust for computational kernels; Python for astronomer-facing interfaces and pipeline scripting. Commit solely under the user's identity without agent signatures or co-author trailers. Persisted in the root `AGENTS.md`.
- Initial working choice: MeerKAT L-band Stokes-I continuum, physical pointing and small beam corrections selected using sky-uncertainty-adjusted information and a local bound on science-signal distortion. L-band is an agent-selected starting point, not a user-imposed band restriction.
- Closest precedents: Albert tomography; BayesCal; resolve; Mouri Sardarabadi/Koopmans identifiability and suppression; Yatawatta/Leahy influence-based tuning; IDG-CAL 2026.
- Relevant latest result: Russeeawon et al. June 2026 clock/TEC initialization, including Smirnov, incorporated into QuartiCal.
- Status: runnable Rust/Python toy implemented. Rust has no external crate dependencies; Python invokes a JSON executable and plots with Matplotlib. No telescope downloads, commits or external publication.
- Additional close precedents: pointing selfcal, MeerKAT L-band beam measurements/holography, EIDOS and the December 2025 MeerKAT visibility-plane mosaicing framework.
- Toy: eight rounded published MeerKAT core positions, flat heights, Gaussian 13.5 m beam, 24 time samples, four L-band frequencies, full w phase, 16 constant antenna-frame pointing parameters, four known bright sources and one uncertain extended component. Geometry provenance/verification limitation is explicit in `data/README.md`.
- Initial matched-width result (seeds 7, 11, 19; true source 20 mJy): pointing-only recovers 12.05 mJy; joint/protected 19.79 mJy; known-pointing 19.89 mJy. All 16 modes survive the default budget; no evidence of added benefit from adaptive protection.
- Stress result: 2% beam-width mismatch biases joint/protected flux to 34.03 mJy while the finite injection response stays near one. Distinguish signal-response preservation from absolute accuracy.
- Strict budget (1e-6, seed 7) underfits and recovers 27.78 mJy instead of 20 mJy. A shifted source outside the fitted template shows 7.62% finite norm distortion despite a near-unit response projection. Both failure cases are documented.
- Controls: zero-error base fit exact; analytic derivatives, geometry, linear algebra and noiseless recovery tested. Coarse source quadrature initially biased even known-pointing recovery; resolved by adequate sampling and covered by a finer-grid convergence test.
- Main entry point: `python3 examples/toy.py --seeds 7 11 19 --output outputs/demo`. Artifacts in ignored `outputs/`; reproducible commands/results documented in `examples/README.md`.
- Verification: 8 Rust tests and 7 Python tests passed; release build, Clippy with warnings denied, Rust formatting and Python Ruff lint/format passed. PNG visually inspected. Final state is uncommitted per current workflow.
- Next research step: replace the idealized beam with measured beam information, include bright-source uncertainty and evaluate whether any adaptive selection benefit survives a matched joint-inference comparison. Acquire verified full-array coordinates before instrument-specific claims. Keep the w-term; introduce ionospheric complexity only as supported.
