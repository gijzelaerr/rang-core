# Signal-guard verification: measured abstention, not safety certification

Read-only verification of the frozen MeerKAT L-band signal branch under
`outputs/tv-next-20260924-01/experiments/signal`. The source checkpoint is
`ec2f17d1dad5f4de65311db19db6daaf1aa4fc2a`, campaign image
`sha256:5da4c1b754ddc3a43f57b5cb7f4d8b7bf9aa182c53eeac5c4ac0fb6208ac1d22`,
and native library SHA256
`cf61db3728a1bb1e1a8bc66ec738d80a102f636185dd527e11a1f6290c530a84`.
The complete predicates, replay sources, original truncated capture and numeric
results are in [the audit archive](results/gain-tv-next-signal-audit.json).
These are two new RFI seeds on the same four-antenna pointing scan, not two
independent observations.

## What the guard actually did

The shortlist union has17 masks for seed107 and16 for seed109, plus each
nochange control. No signal-guarded mask was selected or accepted. Crucially,
their TRAIN responses were **unavailable**, not measured matrices exceeding
the0.1 absolute operator-error threshold. The first unit-template probe stops
at gain bin811: just two native TRAIN cells on baseline0–2. An independent
eigendecomposition of the original weighted full-Jones curvature gives rank8
at the frozen1e-10 relative cutoff. Two active stations have16 real gain
parameters; removing the assumed common U2 gauge leaves12, not8. Inactive
stations must not be counted toward a28-rank claim at this bin.

The implementation correctly retained the frozen native underidentification
abstention. It did not loosen rank/trust limits, discard the troublesome
original TRAIN cells, normalize by an unsafe reference or certify fallback
nochange. This pilot therefore does not demonstrate an actionable certified
signal-safe flagging policy, nor rejection by a measured transfer norm.

Without the signal guard, seed107 selected no change. Seed109 selected and
accepted mask `c17bf4f649f9d573ef81d63672564078d9810c7ec79a1e6b470e79ce069527b1`:
56 whole-correlation TRAIN cells,0.0759631% additions. Its actual fixed-support
objective is1.2495729266458455 versus1.25; TV changes from0.14938593817355783
to0.14911276431630954 and validation MSE from25.32211021562811
to25.3101895414395. This satisfies the frozen1% validation and positive-benefit
quality conditions, but does not make that mask signal-safe.

RFI labels were decoded only after acceptance and paired evaluation. The56
additions all coincide with the596 injected TRAIN cells:9.39597% injection
recall and zero outside-injection additions. This is a late diagnostic, not a
selection feature, completeness claim or proof of general false-positive rate.

## Paired measurement

There were9 actual QuartiCal full-complex2×2 solves: two baselines, one clean
candidate and six positive-source omitted/complete-sky diagnostic controls.
No native flagger or audit QC invocation was added. All measurements share the
original9,169 TEST cells, with none lost and each seed's fixed nochangeG0/native
weight variance. Joint real linear fits use the frozen compact/extended
templates, spectra and no positivity bounds; all have rank2 and condition
about1.92. These are conditional known-template responses, not blind source
fluxes, spectral-index fits, uncertainty intervals or images.

| Seed/control | Compact response/reference | Extended response/reference |
| --- | ---: | ---: |
|107 omitted/nochange|0.5093446442|0.7420029122|
|107 complete/nochange|0.9999603377|0.9890589166|
|109 omitted/nochange|0.5108319321|0.7417645364|
|109 omitted/accepted56|0.5109498209|0.7419216507|
|109 complete/nochange|0.9998242557|0.9887041199|
|109 complete/accepted56|0.9998494874|0.9886312295|

The accepted mask changes omitted-sky recovery by only0.01179 and0.01571
percentage points. No significance is claimed. Sky completeness has a much
larger conditional effect: direct corrected injection is approximately60/120mJy,
while omitted-sky gain adaptation subtracts approximately29.5/31.0mJy. The
truth-complete model is explicitly a diagnostic calibration control, not a
deployable selector or a verified telescope/beam model.

All6 total/direct/adaptation visibility and coefficient decompositions close
below the frozen1e-10Jy limit; the saved worst visibility residual is
6.988730482830058e-15Jy. The independent audit also computes the inverse-Jones
trace directly as matrix products and propagates the original four native
correlation weights, rather than deriving coefficients from signal truth.

## Evidence and integrity

The first read-only replay executed558 predicates, all passed. It reproduced
TRAIN guard availability/abstention and heldout DATA/model/weight poisoning
invariance, VAL scoring/TEST poisoning invariance, slots, actual acceptance,
paired coefficients/decompositions, actual raw QC gain matrices and original
FLAG/FLAG_ROW/native DATA/model/weight copies and backups. TRAIN freezes precede
VAL scoring; acceptance is hashed and precedes signal DATA mutation and paired
TEST evaluation. Timestamp ordering is an artifact consistency check, not a
cryptographic proof of execution history; source structure and adversarial
tests provide the complementary evidence.

The first stdout transport exceeded its30,000-token capture request by2,048
tokens, truncating predicate detail, not numerical summaries or scientific
checks. That captured artifact is retained with473 detailed predicates and the
exact558/558 execution summary. Of473 parsed detail entries,472 are intact;
one key splices text across the transport truncation and is explicitly marked
corrupted in the archive, not treated as an executed predicate. A separate
read-only recovery completed558/558 predicates and retained their full list
and source in an exclusive checked8MiB audit namespace, with all measurement
inputs and trusted frozen-code overlays mounted readonly. All472 intact first
entries and all measured numeric fields agree between replays. The audit
namespace uses253,952 allocated bytes, maintains an8GiB reserve, and adds no
calibration solves or scientific setting changes. One recovery mount attempt
failed before program execution because the frozen root lacked an outputs
mountpoint; it is recorded, and the snapshot was never mutated.

The measured tree allocates1,014,280,192 bytes including directories, below
the checked1.5GiB allowance; this is not an OS-enforced quota. Raw result SHA256:
`c6eab4439dbb0f3f47345cd18a41a8fd2a859e92361883b396e87d4af6ffa0e6`.
The raw tree before/after replay is
`e5d4a630c29b4497d74964c5ecba809d8143c1022a444a5417dd0712a34fbba2`,
excluding only casacore transient `table.lock` bookkeeping. Input/raw source
digests, all pinned helper/library/version receipts and received Observatory
flags remain unchanged. Final work flags are restored exactly; trial holdout
flags remain documented only in backed-up working controls. Original
`RANG_MODEL_DATA` is preserved, with new complete-model schema/data/state
backups and an exact native-complex64 snapshot in a separate column.

Numerical reuse of the frozen guard/native helpers is artifact replay, not
independent scientific validation. The independent matrix-inverse/fit and
curvature-rank references support numerical consistency; they do not resolve
noise, primary-beam, direction-dependent gain or sparse-fixture applicability.
