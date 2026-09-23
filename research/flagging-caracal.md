# CARACAL strategy verification

Source inspected2026-09-23 at the user's request. This is verified source/config
inspection, not yet a measured full CARACAL pipeline or an imaging benchmark.
Pinned official revision: `8f7bb363876f5f0daecbf2167c36bb597c7e5160`.
Downloaded files remain in ignored `outputs/caracal-strategy-inputs-8f7bb363/`.
Hashes, active tasks and exact inspected settings are archived in
[caracal-strategies.json](results/caracal-strategies.json).

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

Distinguish two comparisons: an operational strategy seeing all originally
available data, and training-only data with artificial holdout holes. The first
is useful for checking pipeline behavior but cannot be called unseen-holdout
policy evaluation; the second can make dilation/propagation expand synthetic
holes. Never conceal that difference by silently changing shipped strategy
parameters. Use paired injection/signal/image controls for scientific assessment.

Source inspection and raw-strategy runs do not establish state-of-the-art
superiority. A full CARACAL calibration/imaging replay on representative MeerKAT
L-band data remains a later verification target.
