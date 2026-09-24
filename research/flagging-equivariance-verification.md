# Read-only verification of smooth receiver-phase controls

Measured2026-09-24 on `outputs/tv-equivariance-20260924-host-01/result.json`.
The independently recomputed predictions/losses are invariant to numerical
precision, while gain-TV rankings and five old-fixed-set decisions change.
This supports a **specificity limitation of raw first-order TV**, not a new
successful flagging policy or a receiver-phase-invariant calibration objective.

Compact numerical evidence, exact category counts, source hashes, all28
case/pattern summaries and limitations:
[gain-tv-equivariance-audit.json](results/gain-tv-equivariance-audit.json).
Source design: [flagging-equivariance.md](flagging-equivariance.md).

## Scope, source receipts and identity replay

Seven previously measured balanced development cases, four frozen phase
patterns,130 saved full-Jones gain products and **520 transformed-gain replays**.
These are gains from the same four-antenna MeerKAT L-band observation, not520
independent experiments. The28 individual checkpoints exactly equal their
corresponding result records.

The audit independently checks167 source-file digests before/after calculation,
all9 implementation-module digests before/after, and the native library digest.
All agree with the recorded configuration; no input was altered. Result SHA256:
`8bc444fc83c6b2f5b5cf531a1089f1531bace5acfbd1120b62df17bd348030a8`.
Native macOS Rust library SHA256:
`9d4b8105c06e946db797f5f0538c215b866af380f087b2b007f4b603f7cd9a02`.
Equivariance-module SHA256:
`7284f9f048ae5107e02f188245794868c08bbaba3e6f94d030e4b61bf4af0f61`.

Identity reproduces all seven original selections and all21 original ranking
lists. Across130 identity gain products, the maximum original/replayed total-TV
difference is5.551115123125783e-17; across123 identity action objectives the
maximum difference is4.440892098500626e-16. This is exact discrete
selection/ranking replay and floating-tolerance numerical replay, not bitwise
equality for every floating-point field.

## Independent numerical and support checks

The auditor separately reconstructs the frozen station-phase equation, native
time/channel maps and full-Jones visibility predictions using
`einsum('...ik,...kl,...jl->...ij', Gp, MODEL, conjugate(Gq))`, rather than the
production `gain_prediction` function. It calculates transformed DATA and
predictions, then weighted squared residuals in every originally eligible cell.

Across all520 replays:

- Maximum prediction-equivariance error:5.9580819677934555e-15Jy.
- Maximum row-channel weighted-MSE invariance error:3.410605131648481e-13.
- Maximum TRAIN/validation/TEST mean-loss difference from the old saved
  calibration:7.105427357601002e-15.
- Independently re-gauged native Rust total/raw/time/frequency TV matches every
  measured replay value exactly on this platform.
- All492 action fixed-support TV values, objectives and guards match exactly.

The explicit objective is `TV_fixed/TV0 + 2*added_fraction +
.25*validation_MSE/validation_MSE0`. Selection is an admissible strict improvement
over1.25 on the **old** ranking's action IDs, with the original objective,
flag-fraction and mask-ID tie break. TEST is absent from this expression.

Original incoming FLAG/FLAG_ROW, autocorrelation and outside-window exclusions
remain lower bounds on the saved eligible splits. All130 saved additional masks
are TRAIN-only, have the recorded counts/fractions and remain unchanged through
the replay. The same baseline scale is retained for every product/pattern.
Each case has984 temporal and1094 spectral baseline edges; their support remains
identical across patterns and candidates. Missing support is not rewarded.
The entire admissible whole-rectangle mask family also remains unchanged.

These are read-only checks of saved NPZ/JSON artifacts. They perform no new QC
solve, native-MS read, MS/DATA/weight/flag write or injection-truth-file decoding.
Actual original-MS preservation was checked in the earlier measured suite;
this audit does not replace that boundary with an inferred fresh MS check.

## Rankings, missing outcomes and old-set selection changes

Residual/random TRAIN rankings remain unchanged in all28 case/pattern pairs.
TV rankings change as follows; ratios use each case's identity baseline:

| Pattern | Baseline TV ratio range | Cases with changed TV rank | Unmeasured TV-ranked slots |
| --- | ---: | ---: | ---: |
| Identity | 1 | 0/7 | 0 |
| Smooth frequency | 1.750525–1.771179 | 7/7 | 14 |
| Smooth time | 1.105822–1.110963 | 3/7 | 3 |
| Both | 1.859371–1.882141 | 7/7 | 17 |

There are34 unknown slot occurrences across patterns, representing23 distinct
`(case_id,mask_id)` pairs. Their QC counterfactual outcomes remain **unknown**.
None enters selection; no reranked-policy quality, recall or benefit is inferred
from these unavailable measurements.

All five changed ranking-mode decisions occur in time-burst seed105. The other
six cases retain no-change under all patterns. On old fixed sets:

- Smooth frequency: residual and TV both change to no-change.
- Smooth time: TV changes to no-change; residual retains its old action.
- Both: residual changes to a different already measured old-set action;
  TV changes to no-change. Random always remains no-change.

All guards still pass: these are objective-driven changes, not lost-support or
validation-guard failures. For the old selected residual/TV actions:

| Pattern | Old residual-action objective | Old TV-action objective |
| --- | ---: | ---: |
| Identity | 1.2496526895157485 | 1.249231408712533 |
| Smooth frequency | 1.250534353568959 | 1.2514155737312365 |
| Smooth time | 1.249983188601246 | 1.2501470795087475 |
| Both | 1.2506806605238319 | 1.251835634767887 |

The different residual action selected under both has objective
1.2499998915562092, only approximately1.08e-7 below no-change. Preserve this
negative/marginal finding; it is not scientifically compelling improvement.

## Held-out isolation and implementation review

Source inspection confirms candidate scores/TV normalization read TRAIN only;
the objective/guards read validation only in addition to gain-TV and flag volume.
The old action/result/config paths contain no decoded injection mask. Imports of
modules that define injection constructors do not call those constructors.
Every actual NPZ load uses `allow_pickle=False`.

Additional direct input perturbations cover all28 case/pattern pairs:
arbitrarily large non-TRAIN residuals leave TRAIN features unchanged; NaN TV and
infinite residual scores outside TRAIN leave residual/TV/random rankings
unchanged; replacing all TEST losses by `None` leaves every objective, guard and
old-set selection unchanged. These688 asserted perturbation predicates pass.
Fourteen existing targeted equivariance tests independently pass, including
full-matrix prediction symmetry and TEST-value objective independence.

There are11318 replay/artifact predicates plus688 perturbation predicates,
**12006 total**; the14 pytest test cases are separate. These counts describe
software/numerical checks, not independent scientific replications.

No measurement-blocking issue was found. Two provenance/wording limitations:

- The actual replay is a host run, with `suite_image=null`; its configuration
  does not record execution-time Python/NumPy versions. The audit records its
  own observed Python3.14.7/NumPy2.5.3/macOS-arm64 environment, without claiming
  that this retrospectively fills the original runtime receipt.
- Configuration wording `no_MS_flags_DATA_weights_or_truth_written_or_decoded`
  means no MS/DATA/weight writes and no truth decoding here. Numeric DATA and
  weights **are** decoded from the saved state, as required for the diagnostic.

Reproduction uses the existing read-only numerical APIs with an explicit
`RANG_TOY_LIB` path; no automatic rebuild or new calibration is needed. The
entry point `rangtoy.flagging_equivariance.run(fresh_output, completed_suite)`
replays all four patterns and writes only fresh derived JSON checkpoints.
The independent audit additionally uses the explicit equations above instead
of production prediction/objective implementations. Targeted verification:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python RANG_TOY_LIB=target/release/librang_toy.dylib \
  .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_flagging_equivariance.py
```

These grid-matched phases are not continuous hardware/noise simulations or new
QC-converged solutions. Physical gain-TV need not be invariant to legitimate
receiver phase. The useful finding is that high first-order TV and changed TV
guidance can occur without changed native-weighted residual evidence. Safe
physical-trend/noise-aware guidance still needs a new frozen experiment;
independent-observation transfer, imaging and matched SOTA advantage remain
unmeasured.
