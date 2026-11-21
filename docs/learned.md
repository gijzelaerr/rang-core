# Learned stages

A learned stage replaces or helps part of a pipeline stage with a trained
network. Its weights come in one ONNX file. **0.4.0 ships no weights file**:
the contract, the reader and the interpreter are in place, but no stage has
passed its gates yet ({doc}`limits`). Everything on this page is `off` unless
you turn it on. The contract is in {gh}`research/dl1-contract.md`.

## The `learned:` key

Every stage section of the configuration (`flag`, `calibrate`, `apply`,
`image`, `selfcal`) takes:

```yaml
flag:
  learned:
    mode: off        # off | propose | settings | replace
    weights: null    # path to an ONNX weights file
    force: false     # run a mode the file has not passed, or outside its envelope
```

| Mode | What the network does |
| --- | --- |
| `off` (default) | nothing: products, stage hashes and receipts are the same as without the key (checked on 60 configurations × 5 stages) |
| `propose` | proposes; the classical stage decides. The documented mode when learning is on |
| `settings` | sets the classical stage's settings |
| `replace` | replaces the stage's arithmetic; allowed only where the stage labels its product approximate |

A mode other than `off` on a stage with no registered network is refused by
`rang-core config check` and `run` before any data is read. `apply` takes
the key but has no network. With a mode on, the stage hash includes
`{mode, force, weights_sha256}`: the file's SHA-256, not its path.

## Refusal and `force`

The checks run in this order, at configuration time where possible:

1. **Gates.** A mode is refused unless the weights file's header says it
   passed that mode's frozen gates. `force: true` runs it anyway. The receipt
   then records `forced: gates` and marks the product as an experiment.
2. **Header match.** The file's `stage` must be the stage it is configured on,
   and its architecture must be one the registered network runs. `force` does
   not override this.
3. **Envelope.** This compares the observation (antenna count, baseline
   length, channel width, dump time, band) with the ranges the network was
   trained on. Outside them, `propose` falls back to the classical stage and
   logs it. `settings` and `replace` refuse unless `force`, which is recorded.

Every stage with a mode on records `learned: {mode, weights, weights_sha256,
architecture, gates_passed, envelope, forced, fallback, runtime, reference}`
in its receipt.

## The weights file

One ONNX file per stage, telescope, band and data class (calibrator or
target). The network is the ONNX graph. The provenance is one JSON document
in the file's `metadata_props` under the key `rang.learned`:

| Field | Content |
| --- | --- |
| `format` | `rang.learned/1` |
| `stage`, `data_class`, `telescope`, `band` | e.g. `flag`, `calibrator`, `MeerKAT`, `L` |
| `architecture` | `{id, hyperparameters}` |
| `inputs`, `outputs` | tensor names, layouts and shapes |
| `normalisation` | the constants the features use |
| `training` | data manifest SHA-256, teachers and their versions, seeds, framework, exporter, opset |
| `gates` | per mode: `{passed, rule, scores}`, the rule being the note and section that froze it |
| `envelope` | each of antennas, baseline (m), channel width (Hz), dump (s), band (Hz) as `[lo, hi]` |
| `licence`, `source` | the weights' licence; the note and runs that made them |

The pipeline reads the file without PyTorch or the `onnx` package, through a
small protobuf reader in the Rust core.

## The interpreter

rang runs the graph with its own ONNX interpreter (`core/src/learned_interp.rs`,
pure Rust). It knows two operators, `Conv` and `Relu`. A file with any other
operator is refused at load, by name. Measured
({gh}`research/dl1-contract.md`, amendment 2):

- against PyTorch, within 8.6e-6 (F3) and 2.4e-5 (F4);
- bit-identical at 1, 2, 4, 8 and 16 threads;
- 49,664 B added to the extension;
- 0.852 s at 1 thread and 0.166 s at 8 for 128 planes of 64 × 512 (glacier,
  exclusive).

It is the reference: a stage's hand-written kernel is a fast path, checked in
CI to stay within 1e-4 of the interpreter.

To inspect a weights file:

```python
import numpy as np
from rang import learned

w = learned.load("f3-calibrator-seed3.onnx")   # refuses a bad header or an unknown operator
print(w.sha256, w.ops, w.inputs, w.outputs)
h = w.header
print(h.stage, h.data_class, h.telescope, h.band, h.architecture["id"], h.licence)
print({m: h.passed(m) for m in ("propose", "settings", "replace")})
print(h.envelope)                  # {"band_hz": [...], "channel_width_hz": [...], ...}

x = np.zeros((1, 15, 16, 64), np.float32)      # planes, NCHW
y = learned.run_reference(w, x)                # the interpreter's logits, (1, 1, 16, 64)
print([t.name for t in learned.tenants()])     # registered networks
```

The repository's test fixture `tests/data/learned/f3-calibrator-seed3.onnx` is
F3's calibrator network: every gate `passed: false`, `licence: MIT`.

## Licence of weights

Weights trained on SARAO data (the data factory of {gh}`research/dl2-data.md`)
are CC BY 4.0. Their header's `licence` says so, and its `source` carries
SARAO's acknowledgement (owner decision, 2026-11-20). Other weights state
their own SPDX licence in the header.

## Training and retraining

Training needs the `learned-train` extra (`torch`, `onnx`); the pipeline never
imports it. Exports must use the Conv/Relu, NCHW form above. Retraining a
stage that passed its gates for another configuration (another channel width
or a sub-array class) follows the agent procedure
`docs/agents/retrain-a-stage.md` (branch `dl6-retrain`) and its frozen rules in
`research/dl6-retrain.md`.
