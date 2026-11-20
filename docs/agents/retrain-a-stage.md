# Retrain a stage for a held-out configuration

For: an agent asked to retrain a learned stage that has passed its gates (a
`rang.learned` tenant with a shipped weights file) for a configuration it was
not trained on, for example 1k channels or a core-only sub-array. Ends in a
weights file with a new envelope, receipts, a note with the outcome, and a
branch for the coordinator. The rules are frozen in `research/dl6-retrain.md`;
this page is how to follow them.

The recipe does not change. You add the configuration's training scans to the
stage's training mix and run the stage's own factory, trainer, threshold rule,
exporter and gates. If any of these cannot run unchanged, stop (Stop-R) and
write a proposal note instead (`propose-and-measure`).

## 0. What you are given

You need three things. Ask the coordinator for any that is missing, and do
not guess.

1. **The manifest**, `research/results/<stage>/retrain-manifest.json`. It names
   the stage's note, commit, weights and sha256, feature settings, label rule,
   factory, trainer, exporter, τ and method rules, gates with bars, cost
   receipts, and data (train, validation, held-out already spent). The schema
   is in `research/dl6-retrain.md` section 6.
2. **The configuration**: the capture block(s) and the train, validation and
   held-out scan split (`research/dl6-retrain.md` section 3). It also gives the
   paths and receipts of the teachers' labels.
3. **The gates**: the stage's own gates (manifest `gates`), plus
   non-regression and the contract checks (`research/dl6-retrain.md`
   section 4).

## 1. Freeze your note first

Copy `research/dl6-retrain.md` sections 4 and 5 into a new note,
`research/<stage>-retrain-<config>.md`, and fill in the following:

- the configuration;
- the scans with their sha256;
- each gate's bar on this configuration;
- the gates that are undefined here, each with a reason.

Commit and push the note before any run. Every later change is a dated
amendment.

## 2. Steps

Write a receipt per step to `outputs/<stage>-retrain-<config>/receipts/`. A
receipt records:

- the command and the commit;
- the host and the threads;
- the wall time and the peak RSS;
- the sha256 of every input and output.

Copy the compact ones to `research/results/` at the end. Book every job
through `tools/heavy_lock.py`, using the main checkout's copy, with honest
`--slots` and `--mem`. On nash, also run every job under `nice -n 19 ionice -c3`.
Run from your own worktree and venv, never from the main checkout. Add a row
to `research/tool-timings.md` for each timed run.

**R0 Entry.** Stop (Stop-0) if any of the following fails:

- `sha256sum` of the weights and of each manifest data file matches the
  manifest.
- `rang.learned.load(weights)` works, and the header's gate for its mode has
  `passed: true`.
- `rang.learned.envelope_violations(header, observation)` is non-empty for
  the configuration, which shows it is held out.
- None of the configuration's scans appears in the manifest's train or
  validation data.

**R1 Teachers.** Run the stage's teachers, at the manifest's pinned versions
and strategies, on the train and validation scans. A teacher label file that
already exists may be used if its receipt pins the same versions and matches
the input sha256. If a version differs, stop (Stop-T).

The held-out scans' teacher labels are made, or read, only in R5.

**R2 Data factory.** Use the stage's factory with its seeds. If the factory
only reads named sets, add a **loader** that turns the configuration's MS and
teacher labels into the factory's scan form, and change nothing else. A
loader is the one code change allowed. The loader must:

- give the same scan layout that the stage's own loaders give: cross rows,
  data, flags, antennas, times, channel frequencies and widths;
- be checked on one scan against a reader of the MS such as python-casacore,
  and the check must be bit-equal.

Then:

1. Append the new shards to the stage's shards, each with a sha256 and a
   done-marker.
2. Run the stage's label audit on the new scans. Its frozen stop gives
   Stop-L.

**R3 Train.** Use the stage's trainer, seeds and steps.

- Resume from checkpoints. Do not restart a seed that has a checkpoint.
- On glacier's GPU, book every job through
  `python ~/.gpu/gpu_run.py run --owner rang -- ...`, and yield on exit code 3
  of `gpu_run.py check`.
- Exclusive or timing work on glacier starts at 21:00 SAST at the earliest.
  Other GPU work must stop before any exclusive night the coordinator has
  announced.
- Take the median seed by validation loss.
- If the manifest's budget is exceeded, stop (Stop-B).

**R4 Threshold, method and export.**

- Compute τ and the method with the stage's rules. Run them on the stage's
  validation sets plus the configuration's validation scans.
- Export ONNX in the frozen form:
  - only `Conv` and `Relu` nodes;
  - input `planes` NCHW `(N, C, T, F)` and output `logits` `(N, 1, T, F)`;
  - opset 17.
- If the trainer's module uses another layout, export a conv-only copy of
  the same weights. One way is to load the flat weights into
  `rang.learned_torch` or an equivalent NCHW module. The weights read back
  through `rang.learned.dilated_cnn_weights`, or the stage's reader, must be
  byte-equal to the trainer's.
- Write the header. Keep the stage's header and change only these fields:
  - `envelope`: the union of the stage's and the configuration's;
  - `training`: add the new scans and their sha256;
  - `gates`: `passed: false` until R5.
- Check the file:
  - `rang.learned.load` accepts it;
  - `rang.learned.run_reference` against PyTorch is within 1e-4 on seeded
    planes (I2).
- If either check fails, stop (Stop-X).

**R5 Gates.**

- Read the held-out scans once. Score the stage's gates there, with
  T-relative bars recomputed on the same scans.
- Score non-regression on the stage's validation sets. Never use its spent
  held-out sets.
- Record every gate, including the undefined ones.
- Read the outcome from the frozen table:
  - F if any defined gate fails;
  - P if every defined gate passes.
- Set the header's `gates` from the outcome only.

**R6 Cost.** Compare the following with the manifest:

- the header's `architecture`;
- the ONNX op list and every initializer's shape;
- the feature id, level and degree;
- the method kind.

If all are equal, reuse the stage's cost receipts and write
`"cost": "reused"`. A change in τ alone still counts as equal. Any other
difference needs the stage's exclusive timing protocol, booked with the
coordinator.

**R7 Report.**

- Under "Measured result" in your note, record the following:
  - every step's numbers and receipts;
  - the outcome;
  - what is not claimed. A split inside one capture block is not G-obs.
- End the note with a section for the coordinator.
- Run `python tools/check_all.py --quick`.
- Push your branch, then read CI with `gh run list --branch <branch> -L 3`
  (see `check-and-ci`).
- Ship nothing. Moving the weights into the wheel is the owner's decision.

## 3. Stops

| Stop | Step | What to write |
| --- | --- | --- |
| Stop-0 | R0 | which entry check failed |
| Stop-T | R1 | teacher, pinned and found versions |
| Stop-L | R2 | the audit record |
| Stop-B | R3 | steps reached, GPU hours |
| Stop-X | R4 | the refusal or I2's largest difference |
| Stop-R | any | the recipe change that would be needed; propose it in a new note |

Every stop is a result. Record it the same way as a pass.
