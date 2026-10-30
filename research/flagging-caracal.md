# CARACAL strategy verification

Source inspected 2026-09-23 at the user's request. Four native full-strategy
controls completed; this is not a full CARACAL pipeline or an imaging benchmark.
Pinned official revision: `8f7bb363876f5f0daecbf2167c36bb597c7e5160`.
Downloaded files remain in ignored `outputs/caracal-strategy-inputs-8f7bb363/`.
Hashes, active tasks and exact inspected settings are archived in
[caracal-strategies.json](results/caracal-strategies.json).

Paths (2026-10-30, task P8): the frozen `tv-flagging*` recipes,
`tools/flagging/` and the recipe-only modules named here now live under
[`history/`](../history/README.md); this text keeps the paths it was written
with.

## What the official worker actually runs

The [flag worker](https://github.com/caracal-pipeline/caracal/blob/8f7bb363876f5f0daecbf2167c36bb597c7e5160/caracal/workers/flag_worker.py)
selects AOFlagger, Tricolour or CASA tfcrop. Tricolour gets
`flagging-strategy=polarisation`, the configured column/field names, backend and
the full strategy YAML. Optional model-column subtraction changes that input.
Automatic Tricolour selection switches to its narrow strategy only when native
TOTAL_BANDWIDTH is≤20MHz. The fixture has856MHz native bandwidth; a selected
training window does not by itself make its metadata narrowband.

The [worker documentation](https://caracal.readthedocs.io/en/latest/manual/workers/flag/index.html)
describes field/strategy selection and correlation compatibility. CARACAL saves
before/after flag versions and can rewind/delete later versions. For Rang,
never enable unflagging or overwrite/rewind authoritative Observatory backups;
operate only on fresh copies and independently assert FLAG/FLAG_ROW protection.

## Shipped strategies and differences from our reduced comparator

- [Calibrator first pass](https://github.com/caracal-pipeline/caracal/blob/8f7bb363876f5f0daecbf2167c36bb597c7e5160/caracal/data/meerkat_files/mk_rfi_flagging_calibrator_fields_firstpass.yaml):
  dropout handling, static mask, SumThreshold, polynomial residual cycles,
  a0–550m UV-dependent mask, broad/narrow passes, auto flags and final union with
  input flags. Broad windows include32/48/64/128 channels; polynomial degrees20
  then25. Input-flag preservation must be checked despite internal mask cycles.
- [Calibrator second pass](https://github.com/caracal-pipeline/caracal/blob/8f7bb363876f5f0daecbf2167c36bb597c7e5160/caracal/data/meerkat_files/mk_rfi_flagging_calibrator_fields_secondpass.yaml):
  tighter7-sigma SumThreshold and8-sigma polynomial residual cuts; no first-pass
  static-mask/auto steps. It is a later-stage strategy, not a raw-data substitute.
- [Target first pass](https://github.com/caracal-pipeline/caracal/blob/8f7bb363876f5f0daecbf2167c36bb597c7e5160/caracal/data/meerkat_files/mk_rfi_flagging_target_fields_firstpass.yaml):
  matches the inspected calibrator first-pass active tasks/parameters. Its name
  does not establish distinct behavior at this revision.
- [Mild](https://github.com/caracal-pipeline/caracal/blob/8f7bb363876f5f0daecbf2167c36bb597c7e5160/caracal/data/meerkat_files/calibrator_mild_flagging.yaml)
  and [soft](https://github.com/caracal-pipeline/caracal/blob/8f7bb363876f5f0daecbf2167c36bb597c7e5160/caracal/data/meerkat_files/calibrator_soft_flagging.yaml):
  no static-mask tasks. Mild uses fewer background/polynomial cycles; these
  strategies are explicitly named controls, not automatically correct for L-band.
- [AOFlagger firstpass_Q](https://github.com/caracal-pipeline/caracal/blob/8f7bb363876f5f0daecbf2167c36bb597c7e5160/caracal/data/meerkat_files/firstpass_Q.rfis):
  StokesQ, iterative SumThreshold, high-pass/resolution stages and statistical
  morphology. The sparse-scans variant changes the inner time-selection
  threshold from2.1 to3.5; the files are not interchangeable. Runtime XML/engine
  compatibility is still to be tested.

Our earlier kernel comparison used Stokes-I-like amplitude, omitted static masks
and polynomial passes, and adapted dilation to sparse holdouts. It is correctly
labeled an ablation, not CARACAL's shipped strategy. A production strategy can
use polarization to avoid flagging sky structure that is bright in I.
Actual equivalence requires checking the installed Tricolour interpretation,
not merely matching a few SumThreshold parameters.

## Verification design

Run unmodified, hashed strategies with the genuine CLI on isolated copies;
record engine versions, exact command, static-mask provenance, selected field,
column, polarization handling and every task. Keep raw first-pass and residual
second-pass semantics distinct. Validate DATA/native weights, original flags,
and source digests before/after every native run. Include a constant-input
control with missing samples and an unmodified-real-data control.

Distinguish operational input flags from artificial holdout-masked input flags.
The installed Tricolour0.2.1 polynomial kernel confirms that initial masks can
be discarded before later cycles. Merely adding holdout flags does not guarantee
the hidden DATA stay excluded from native flagging features. Neither control is
claimed as unseen-holdout policy evaluation. Morphology can also expand those
synthetic holes. Never conceal differences by changing the shipped strategy.
All frozen-mask QuartiCal solves independently enforce original flag bounds.
Use paired injection/signal/image controls for scientific assessment.

Implemented verification entry point: [Stimela2 recipe](../recipes/tv-flagging-caracal.yaml).
With the suite image and downloaded pinned sources present:

```sh
bash tools/flagging/run-caracal.sh outputs/tv-caracal-new outputs/tv-flagging-actions-01
```

The recipe copies stable prepared inputs,
archives actual engine/mask/source hashes and native commands, runs unmodified
strategies and audits before/after masks, DATA, weights and source preservation.
It reports frozen training-mask full-Jones diagnostics, never selects a deployed
policy, and restores the main work copy to original flags after verification.

## Historical partial checkpoint: first two native controls

At the initial checkpoint, the clean fixture run `outputs/tv-caracal-clean-01/`
had completed both first-pass input modes. The two mild controls and final
whole-run source audit were then pending; completion is recorded below.
This partial checkpoint is preserved separately in
[gain-tv-caracal-progress.json](results/gain-tv-caracal-progress.json).

| First-pass input | Extra eligible training flags | Fixed baseline TV support | Validation predictions | Guard |
| --- | --- | --- | --- | --- |
| Operational original flags | 36.207% | Lost | 1,314 unsupported | Reject |
| Artificial holdout flags | 36.133% | Lost | Unavailable | Reject |

Both exceed the frozen 2% training budget. Their non-comparable supported-edge
TVs are 0.288703 and 0.293417; these must not be interpreted as fixed-support
objective measurements. Native CLI exit codes are zero and both persisted-mask
audits preserve original FLAG/FLAG_ROW, DATA and native weights. The engine
fully flags auto rows without updating FLAG_ROW; the copy audit records this,
and the later QuartiCal mask writer independently enforces row protection.
No deployed policy is chosen. Aggressive rejection on a four-antenna pointing
scan is not evidence that CARACAL is inferior on normal observations.

Each native call currently includes about 300 seconds of progress-logger delay:
Tricolour's non-TTY branch constructs Dask's ProgressBar with `dt=5*60`, and the
installed timer's finish method joins its sleeping thread. The completed log
reports 300.01 seconds. This is a verified instrumentation artifact, not a
measured flagging-kernel runtime. Retain unmodified launch semantics and logs;
make no performance claims from these emulated runs.

## Completed four-control verification

The full recipe completed 18:57:48–19:19:11 UTC on 2026-09-23. Exact config,
engine/source/static-mask hashes, four native controls, frozen-gain diagnostics
and final audit are in [gain-tv-caracal.json](results/gain-tv-caracal.json).
The partial archive above remains unchanged as an honest progress checkpoint.

Baseline objective is 1.25. Both first-pass controls are rejected as above.
The two mild controls retain fixed TV support and satisfy the budget/validation
guards, but neither improves the objective:

| Mild input | Extra training flags | Fixed-support TV | Validation MSE | Test MSE | Objective |
| --- | ---: | ---: | ---: | ---: | ---: |
| No-change baseline | 0% | 0.14743687 | 25.20612 | 24.91961 | 1.250000 |
| Operational original flags | 0.898% | 0.14767936 | 25.26985 | 25.01172 | 1.270237 |
| Artificial holdout flags | 0.997% | 0.14824565 | 25.28815 | 25.03502 | 1.276239 |

These are diagnostic controls, not held-out-feature policy selection. All four
native FLAG/FLAG_ROW lower-bound, DATA and weight audits pass. The final audit
also confirms unchanged prepared source, strategy inputs and original source,
and restores the main work copy to original flags. No policy is deployed and no
image/transfer/SOTA advantage is established. Full CARACAL calibration/imaging
on normal observations remains distinct future work.

Integration-only follow-up: removed the recipe's fixed outer log directory so
the wrapper's unique log path is honored. A fresh offline dry-run confirms this
for both native and structured recipes; no algorithm/strategy parameters changed.

Source inspection and raw-strategy runs do not establish state-of-the-art
superiority. A full CARACAL calibration/imaging replay on representative MeerKAT
L-band data remains a later verification target.
