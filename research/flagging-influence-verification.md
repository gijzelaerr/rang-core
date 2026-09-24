# Independent full-Jones deletion-response verification

Verified2026-09-24, read-only against
`outputs/tv-influence-20260924-host-01` and its seven measured balanced cases.
The final pass has4,620 successful predicates; it is a new audit, not a sum of the
previous prepared-case, balanced-solve or compact-archive audit counts.
[Machine-readable evidence and runnable reference](results/gain-tv-influence-audit.json)
retain exact receipts, chronology, tolerances, mask IDs and NumPy verification code.

## Numerical and boundary checks

Independently reconstructed all123 frozen TRAIN action masks and original
four-correlation weights. Analytic real Jacobians, including the negative
q-imaginary conjugate sign, produced126 unique full normal blocks and174
full-minus-removed projected responses. NumPy eigensolves used the frozen
right-U(2) horizontal gauge, baseline damping/rank threshold, anchored steps and
station trust bound. Raw predicted gains differ from the Rust-backed artifacts
by at most1.85e-14. Independent repolar-gauging, fixed-scale/fixed-edge-support TV,
validation weighted MSE/objectives and actual canonical gain-change diagnostics
also agree for all120 covered actions.

All174 response blocks have full/retained rank28, gauge rank4 and native status0.
Exactly three actions abstain because a station step exceeds0.1, not because of
rank loss or invalid curvature. Steps are0.106071,0.112552 and0.129333 for the
time-burst101/103/105 cases respectively; these remain missing predictions.

Artifact mtimes, unchanged source/native receipts and checked Python AST control
flow agree with the sequence: all seven TRAIN response caches → TRAIN JSON freeze
→ validation scoring → validation forecast freeze → actual outcome decoding.
The TRAIN fields remain unchanged in the validation/result records. All123
mean/residual-linear control predictions reconstruct from only35 seed101 labels;
no clean, seed103 or seed105 labels enter their fits. No validation tuning,
injection-truth archive access or TEST visibility/loss use occurs in the checked
forecast path. DATA bytes and unused JSON report fields can be loaded; that is
distinct from using their values in curvature, fitting or ranking. File chronology
and code inspection are consistency evidence, not an independent file-open trace.

The audit confirms all11 runtime/native hashes before and after, all11 derived
artifact receipts, complete source-tree immutability, original table-tree receipts,
positive native TRAIN weights and protection from originalFLAG/FLAG_ROW/autos/
out-of-window cells. No new calibration solve or MS/flag/cache write was made.
This host-only check did not freshly reopen casacore columns; whole-table byte
receipts preserve the previously column-validated originals.

## Measured forecast signal and limitations

On the retrospective seed105 case group,35 of36 actions are covered. Objective
benefit RMSE is8.56943e-5 versus6.22545e-4 for the exact `-2*f` flag-volume-only
control: a7.26472× error ratio on identical coverage. The ratio persists after
removing the known flag cost from both actual and predicted benefit. Median
canonical gain-change relative error is0.0831537 and cosine agreement0.996899.
These are one-observation, correlated, previously measured counterfactuals—not
independent transfer observations or a fair runtime comparison.

There are three positive-benefit forecasts; all three have positive actual
guarded benefits. This is benefit-sign precision for these labels, not RFI
false-positive performance. All six other case recommendations are no-change,
including the unmodified control. For time-burst105 the physics ranking chooses
58 TRAIN cells and predicts benefit0.000445050; the actual benefit is0.000347310,
giving objective1.24965269 from the1.25 no-change baseline. Residual-first's
actual benefit is0.00000291828; seeded-random-first is negative0.001020971.
These comparator choices are confined to the old solved union, not full-family
policy searches or state-of-the-art flaggers.

The strongest actual benefit,0.000768591, belongs to the trust-abstained seed105
action. The physics recommendation consequently has regret0.000421281. This
miss is retained; retrospectively raising the trust threshold would change the
frozen method. There are four positive actual labels overall, with three covered
and one abstained—not a robust beneficial policy across the seven cases.

This is a promising physical action-response diagnostic, not evidence of image
fidelity, reliable RFI recovery, deployment readiness, scientific novelty or
native-versus-emulated speedup. A selected action still requires the genuine
guarded full-Jones solve before flags are exported.

## Reproduce the independent check

From the repository root, using the preserved source/run trees and native/source
receipt files, the embedded reference prints its report without creating outputs:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python .venv/bin/python -c 'import json; from pathlib import Path; exec(json.loads(Path("research/results/gain-tv-influence-audit.json").read_text())["reference_python"])'
```

The reference uses independent NumPy algebra, not the response forecast function.
It hashes measured inputs byte-for-byte and does not open injection-truth archives
or perform any TEST numeric scoring. Runtime source changes intentionally fail
the archived receipts; preserve the checked checkpoint for a matched replay.
