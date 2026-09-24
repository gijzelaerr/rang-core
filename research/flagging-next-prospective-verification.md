# Independent prospective flagging artifact verification

Verified2026-09-24 against scientific source checkpoint
`ec2f17d1dad5f4de65311db19db6daaf1aa4fc2a`, after all prospective outcomes
completed. This is a retrospective read-only artifact audit, not a new QC
measurement, revised policy or independent-observation experiment. Exact code,
command, hashes,2331 scripted passed predicates and unrounded values are retained in
[the verification archive](results/gain-tv-next-prospective-audit.json).
An additional24 baseline-command checks pass (eight controls across three
baselines), giving2355 recorded predicates in total.

## Immutable and numerical boundaries

All93 captured runtime paths, including Linux native library
SHA`cf61db3728a1bb1e1a8bc66ec738d80a102f636185dd527e11a1f6290c530a84`,
and all five frozen source trees match. Read-only historical source overlays
retain the original implementation while unrelated imaging CLI corrections
are developed. Verification used immutable campaign image
`sha256:5da4c1b754ddc3a43f57b5cb7f4d8b7bf9aa182c53eeac5c4ac0fb6208ac1d22`,
network disabled, one CPU and2GiB memory. An initial nested read-only mount
failed before Python; the successful launch overlays the seven captured code
directories/files onto a read-only repository. Neither launch calibrated data
or changed a dataset.

All three copied MSs were inspected directly with native casacore read-only
`autonoread` locks. Received original FLAG/FLAG_ROW and DATA match their state
and original source hashes. Working DATA/model remain exactly their frozen
case values; every present native WEIGHT/WEIGHT_SPECTRUM/SIGMA/SIGMA_SPECTRUM
column matches the immutable original. Final FLAG/FLAG_ROW equal received
protection plus the selected TRAIN mask only. Constructor DATA changes are
absent outside TRAIN, including heldouts/protected support, and all other state
arrays/splits/model/native weights match the pristine constructor source.

Every frozen candidate is sorted/unique, has the correct SHA/count/exact
fraction, and contains only8-or-more TRAIN cells within the2% budget.
Rebuilding the TRAIN-only baseline geometry and estimated trend reproduces
the exact family, metadata, shortlist and residual/raw-TV/random/trend-TV
rankings. Each ranking has at most six slots, at most two per canonical group,
without borrowing empty slots. The union is18/17/16 distinct whole masks.
All54 recorded QC commands use full complex2×2 gains,2integration×32channel
intervals,50iterations, native WEIGHT_SPECTRUM, single solver thread, disabled
MAD, and disabled solver flag output.

Native Rust replay reproduces all51 TRAIN response gain payloads and forecast
TV values. Poisoning every VAL/TEST DATA/model/weight value leaves the full
TRAIN curvature, score vector and predicted gains bitwise identical. Native
TV edges, fixed baseline scale/support, actual weighted split losses, objective
and guards independently replay for all51 counterfactuals. Actual-objective
selections remain identical after poisoning all TEST-loss labels. Injection
truth is opened by the audit only after these selection checks, then its
reported recall/outside-mask counts reproduce exactly.

All-case TRAIN response freezes precede validation-ranked forecast freezes;
all-case forecast freezes precede the first actual candidate command. Exclusive
backups precede each solve mask/command. Source control flow and the34 earlier
synthetic prospective tests support those boundaries; filesystem timestamps
are corroborating artifact evidence, not a substitute for those checks.
Scientific no-truth-use means no labels decoded/used for selection: provenance
tree hashes do read label-file bytes. No TEST value affects ranking, acceptance
or confirmation. Actual outcome labels belong solely to the subsequent
reference-union measurement and confirmation guards.

## Reportable measured result

The frozen physics policy matches the full measured shortlist-union reference
in all three cases, with zero missed objective benefit within that union:

| Case | Union actions | Frozen confirmations | Selected extra flags | Selected objective |
| --- | ---: | ---: | ---: | ---: |
| Clean |18|0|0|1.25|
| Time-burst seed107 |17|0|0|1.25|
| Time-burst seed109 |16|1|56|1.2495729266458455|

All51 actual actions pass the support/validation/budget guards, but only one
improves the guarded objective by more than the frozen1e-6 margin. The
seed109 winner is a global16-channel rectangle at time-index7,
channels2400:2416, mask SHA
`c17bf4f649f9d573ef81d63672564078d9810c7ec79a1e6b470e79ce069527b1`.
Its56 additions are0.000759631036353771 of TRAIN. Predicted benefit is
0.00041994287835755983; actual benefit is0.00042707335415448355. Residual,
raw-TV and trend-TV six-slot rankings select the same winner; seeded random
selects nochange. Thus this experiment does not show a trend-ranking advantage.

Known synthetic injection recall is0.09395973154362416, with zero additions
outside its known injection. That is low absolute recovery of this artificial
patch, not general RFI precision/specificity. The selected TEST MSE is
25.03525053092711 versus25.036838898721214 for nochange; TEST is diagnostic
only, and this tiny difference is not independent scientific significance.

## Flag-cost confound and compute accounting

Objective-benefit RMSE over all51 matched guard-passing actions, split by case,
compares the actual physical forecast against the posthoc known-cost-only
forecast `-2*added_fraction`. Neither labels nor TEST fit/select either policy;
these are descriptive diagnostics, not a trained comparator or blind transfer:

| Case | Native response forecast RMSE | Negative flag-cost-only RMSE |
| --- | ---: | ---: |
| Clean |0.00009249954486931304|0.00041953040309246695|
| Seed107 |0.00009810568768062288|0.0006424211789225031|
| Seed109 |0.00008627902202793562|0.0007413710386063944|

The forecast contains useful information beyond the fixed flag penalty on these
same-scan cases, but there is only one positive action. Clean and seed107
remain explicit null/nochange findings. Three baselines plus51 union actions
were actually solved:54QC, below the frozen75 ceiling. A future execution
restricted to the frozen confirmations would require three baselines plus one
action:4QC. This campaign spent all54 solves to measure that reference; it does
not demonstrate a runtime speedup or matched state-of-the-art scientific win.
Recorded response and QC timings are retained as Linux-amd64 emulated
diagnostics and omit some orchestration overhead; no native performance claim
is justified.

No hypothesis, penalty, margin, ranking budget or action was retuned after
these outcomes. The result establishes a narrowly useful prospective objective
forecast and confirmation mechanism on one real MeerKAT L-band fixture with
two synthetic TRAIN patches. Independent observation, representative RFI,
signal-safe imaging and matched scientific quality/cost gates remain open.
