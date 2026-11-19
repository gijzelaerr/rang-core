# DL1: the swap contract, the weights file, `rang.learned`, the inference runtime

Task DL1, issue #38, branch `dl1-contract` from main `dd6adc5d`. Session B of v0.4.0 wave 1.
Implements section 4 of [dl-plan.md](dl-plan.md) under decisions 3-5 of its section 10.

**Status at freeze (2026-11-19): proposed; nothing implemented, exported or measured.** Results go
under "Measured result"; nothing above it changes except by dated, labelled amendment.

What is claimed: an engineering contract and a measured runtime choice. Nothing here claims better
flags, calibration or images; F3's network is used only because it exists, is small and has a Rust
kernel to check against. F3 failed its own gates (antenna-local recall 0.024 against 0.907,
[f3-flagger.md](f3-flagger.md)), so its weights file records failed gates, and that is the test of
refusal.

## 1. The `learned:` key

Every stage section of the configuration (`flag`, `calibrate`, `apply`, `image`, `selfcal`) gets

```yaml
learned:
  mode: off        # off | propose | settings | replace
  weights: null    # a path to an ONNX weights file, or a registered name
  force: false     # run a mode the weights file has not passed, or outside its envelope
```

- `off` is the default and is **bit-identical to dd6adc5d**: the same products, the same stage hashes,
  the same receipts. Evidence: the stage hashes of every `rang-config` file in the repository (60
  files, 5 stages each, `outputs/dl1/hashes-dd6adc5d.json`, made before any code change) are equal
  after the change, and the quick check passes.
- `propose` (P) is the documented default when learning is on; `settings` (S) and `replace` (R) as in
  dl-plan section 2. Decision 3 makes every mode an option per stage; the brief names off, propose and
  replace, section 4 also `settings`: all four are accepted as values. `replace` is allowed only where
  the stage's product is labelled approximate in its receipt.
- `apply` gets the key as a hook and no tenant (decision 3).
- A mode other than `off` on a stage with no registered tenant is a configuration refusal
  (`rang-core config check` and `run` refuse before reading data), not a silent `off`.
- The stage hash includes `learned` only when the mode is not `off`, and then as `{mode, force,
  weights_sha256}`, the file's SHA-256 and not its name or path.

## 2. The weights file

One ONNX file per stage, telescope, band and data class (Landman, 2026-11-06). ONNX
(`ModelProto`) because decision 5 makes it the format of every weights file; exported from PyTorch
(decision 4). The provenance header is one JSON document in `ModelProto.metadata_props` under the key
`rang.learned`; the network is the graph with its initializers. Header fields (format version 1):

| Field | Content |
| --- | --- |
| `format` | `rang.learned/1` |
| `stage`, `data_class`, `telescope`, `band` | e.g. `flag`, `calibrator`, `MeerKAT`, `L` |
| `architecture` | `{id, hyperparameters}`, e.g. `{id: dilated-cnn/1, hyperparameters: {inputs: 15, hidden: 8, dilations: [1,2,4,8,16]}}` |
| `inputs`, `outputs` | tensor names, layouts and shapes (symbolic dims named) |
| `normalisation` | constants the features use |
| `training` | manifest SHA-256, teacher names and versions, seeds, framework and version, exporter and opset |
| `gates` | per mode: `{passed: bool, rule: <note#section>, scores: {...}}` |
| `envelope` | antenna count, baseline length (m), channel width (Hz), dump time (s), band (Hz): each `[lo, hi]` |
| `licence`, `source` | SPDX id of the weights; the note and run paths that made them |

The pipeline reads the file without PyTorch or the `onnx` package: a small protobuf reader in the
Rust core (`ModelProto` fields 7 graph and 14 metadata_props; `GraphProto` 1 node, 5 initializer,
11 input, 12 output; `NodeProto` 1 input, 2 output, 3 name, 4 op_type, 5 attribute; `TensorProto`
1 dims, 2 data_type, 4 float_data, 8 name, 9 raw_data), the field numbers checked against
`onnx.proto` of the installed `onnx` package before the reader is written. FLOAT tensors only;
anything else is refused with a message.

## 3. Refusal

In order, at configuration time where the inputs allow it, else at the stage's start:

1. **Gates.** Mode m is refused unless `gates[m].passed` is true. `force: true` runs it anyway, writes
   `forced: gates` in the receipt and marks the product as an experiment.
2. **Header match.** `stage` must be the stage it is configured on; `architecture.id` must be one the
   tenant registers. No force overrides these.
3. **Envelope** (W4 style), checked against the observation: mode P falls back to the classical path
   and logs it; modes S and R refuse unless `force`, which is recorded.

## 4. Receipts

Every stage with mode not `off` records `learned: {mode, weights, weights_sha256, architecture,
gates_passed, envelope: {ok, violations}, forced, fallback, runtime}` in its receipt. With `off`
nothing is added, so receipts are unchanged.

## 5. `rang.learned`

One module, `python/rang/learned.py` (inside `source_receipts`' glob), with:

- `Mode`, `Header`, `load_header(path)`, `check(stage, mode, header, observation, force)`;
- a registry: `register(Stage(...))`, where a `Stage` names the config stage, the data classes, the
  architecture ids it can run, its features, its forward (by architecture id and hyperparameters, so
  F4 and F5 register a tenant rather than fork one), and for training only its loss, teacher runner
  and gates;
- PyTorch only inside `rang.learned_torch` (the training extra `learned-train`: torch, onnx), never
  imported by the pipeline, the check or the wheel's tests.

F3 becomes the first registered architecture (`dilated-cnn/1`), run by the existing Rust kernel
(`f3flag::network`) with weights read from the ONNX initializers. F5's move under the contract is
then a registration and a weights file, with its kernel unchanged.

## 6. F3 through the contract

- Recreate F3's network in PyTorch (5 dilated 3×3 convolutions with zero padding and ReLU, 1×1 head;
  NCHW), load seed 3 of `f3-20261110-17-train-calibrator` (sha256
  `2cdeee1795995b9d2f8c7c1d6deff6ec354c4a305712766afaccfb3091e2e91e`, 3,433 float32), export to ONNX
  with dynamic time and channel axes, and write the header (gates: all modes `passed: false`, from
  f3-flagger.md's calibrator outcome F).
- Commit the file as a test fixture (`tests/data/learned/f3-calibrator-seed3.onnx`, about 16 kB) so
  that CI runs the tests below without PyTorch. It is not shipped in the wheel.
- **Bit-identity, frozen:** (a) the flat weights the reader extracts from the ONNX file are equal byte
  for byte to `flat_weights(npz)`; (b) on the F3 test scans, logits through the contract (ONNX file,
  forced, kernel) equal `rang._core.f3flag_logits` with the npz weights bit for bit. The contract
  does not change the arithmetic, so anything but exact equality is a defect.
- PyTorch against the kernel on the same inputs: max |Δ logit| ≤ 1e-4 (F3's JAX parity was 2.7e-5).

## 7. Runtime comparison

Candidates: **tract** (tract-onnx), **burn** (its ONNX import), **candle** (candle-onnx), and the
**hand-written kernel** (`f3flag::network`). They are built in a separate crate,
`tools/dl1_runtimes/`, with its own `Cargo.lock`, outside `core/` and the wheel; nothing is added to
the core's dependencies by this task.

Inputs: F3's ONNX file; per measurement, float32 planes drawn from N(0, 1) with seed 20261119, shape
(1, 15, nt, nc). Shapes: **A** nt 64, nc 512 (one baseline of a LUNO tile scan); **B** 128 such
planes, run in parallel over planes with rayon (the per-baseline pattern of `f3flag`).

Hard gates (a candidate failing one is out, with the reason recorded):

| Gate | Pass |
| --- | --- |
| G1 run-time loading | runs a weights file given at run time, with the network defined by the file (a code generator that fixes the network at build time fails) |
| G2 build | builds with stable Rust 1.93 on Windows x86_64 here, without protoc, a C/C++ toolchain beyond what the core already needs, or network access at build time; Linux and macOS by the crate's own CI, not rebuilt here |
| G3 dynamic shape | the same loaded model runs shapes A and a second nt, nc (32, 256) without reloading |
| G4 licence | the crate and every transitive dependency MIT, Apache-2.0, BSD, ISC, Zlib, Unicode or MPL-2.0 (GPL-3.0-only compatible), from `cargo metadata` |
| G5 agreement | against PyTorch 2.x CPU float32 on shape A: max \|Δ logit\| ≤ 1e-4 |
| G6 size | the stripped release cdylib of a minimal crate that loads the file and runs it, minus the same crate with the hand kernel only (x86_64-pc-windows-msvc, opt-level 3, thin LTO, codegen-units 1): ≤ 8 MB, against the current 10.6 MB `_core.pyd` |

Measured and reported, not gating:

- **Speed:** wall per forward, shape A at 1 thread, and shape B at 1, 4 and 16 threads (median of 7
  after 2 warm-ups), each candidate beside the hand kernel. Daytime numbers on glacier are labelled
  provisional; final numbers in an exclusive `heavy_lock` hold on glacier from 21:00 SAST (CPU only,
  no `gpu_run` booking).
- **Thread identity:** shape B's outputs at 1, 2, 4, 8 and 16 threads (both rayon's pool and the
  runtime's own threading setting where it has one) compared bit for bit with 1 thread. A runtime
  that is not identical is stated as a limit for mode `replace` (decision 5), not a failure.

**Decision rule.** Among candidates that pass G1-G6, choose the one with the lowest shape-B wall at
16 threads; if two are within 10 %, the smaller G6 size. The hand-written kernel stays the fast path
for shipped architectures with the chosen runtime's output as its reference (decision 5). Outcomes:

- **C (chosen):** one crate passes; it is named, and adding it to the core is a later task.
- **N (none):** no crate passes; recorded with each failed gate; the fallback is an interpreter of
  our own over the ONNX reader of section 2 (convolution, matmul, add, relu first).

## 8. Stages and stop rules

1. This note, frozen in its own commit.
2. `learned:` key, `rang.learned`, the ONNX reader; `off` evidence (section 1). Stop if any pinned
   stage hash changes.
3. F3 export and the bit-identity tests (section 6). Stop if (a) or (b) fails and the cause is not a
   defect in the new code.
4. Runtime bench (section 7), provisional in the daytime; final timings after 21:00.

## Measured result

Nothing yet.
