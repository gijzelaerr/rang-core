# DL6: retrain a passed stage for a held-out configuration

Task DL6 (issue #46, [dl-plan.md](dl-plan.md) section 8), branch `dl6-retrain` from origin/main
`7cd42b26`. **Status at freeze (2026-11-20): proposed. No procedure, script or run exists. No
stage has passed its gates yet;** F6 (session D, issue #40's successor) is expected to be the first.
Results go under "Measured result"; nothing above it changes except by dated, labelled amendment.

**Done when** (issue #46): an agent retrains one passed stage for a held-out configuration from the
procedure alone and meets the gates. **Not claimed:** novelty, better calibration or imaging, or that
a stage generalises to a configuration it was not retrained for. A split inside one capture block is
scans of one observation, so this is **not G-obs**.

## 1. Terms

- **Passed stage:** a `rang.learned` tenant whose weights file passed its own note's frozen decision
  rule with outcome S or S− (or the stage's equivalent "ships" outcome), and whose header has
  `gates.<mode>.passed = true` for the mode it ships in.
- **Configuration:** what the header's `envelope` describes (channel width, band, antenna count or
  layout class, dump time). A configuration is **held out** for a stage when no scan of it is in the
  stage's training data and `rang.learned.envelope_violations` is non-empty for it.
- **Retrain:** the passed stage's frozen recipe (architecture, features, labels, optimiser, steps,
  seeds, τ rule, method rule) run again with the new configuration's training scans added to the
  stage's training mix. Nothing in the recipe changes. If the recipe cannot run unchanged, the
  procedure stops (section 5, Stop-R).

## 2. The procedure (what `docs/agents/retrain-a-stage.md` says)

**Inputs, all handed to the agent:**

1. the passed stage's **manifest** `research/results/<stage>/retrain-manifest.json` (schema in
   section 6): note, tenant, weights file and sha256, commit, feature level and settings, label
   rule, data factory, trainer, exporter, τ and method rules, gate list with bars, cost receipts,
   training and validation scans with sha256, held-out sets already spent;
2. the **held-out configuration**: its name, the capture block(s), the scan split (train /
   validation / held-out) fixed by section 3, and the teachers' label paths with sha256;
3. the **gates**: the passed stage's own frozen gates, re-scored on the new configuration (section 4).

**Steps** (each writes a receipt; a receipt is a JSON file with the command, commit, host, threads,
wall time, peak memory and the sha256 of every input and output):

| Step | Work | Stop if |
| --- | --- | --- |
| R0 | Entry: the configuration is held out (section 1); the stage is passed; the manifest's sha256s match the files | any fails: **Stop-0** |
| R1 | Teachers: the stage's teachers (T and A for flagging) on the new train, validation and held-out scans, at the pinned versions, from the configuration's label receipts or run anew; held-out labels are read only at R5 | a teacher fails or its version differs from the manifest: **Stop-T** |
| R2 | Data factory: the stage's own factory (injections, labels, sub-array draws, shards with sha256 and done-markers) on the new train and validation scans, appended to the stage's shards; the stage's label audit on the new scans | the audit's frozen stop: **Stop-L** |
| R3 | Train: the stage's trainer, its seeds and steps, resumable, GPU through `gpu_run.py` or CPU under the heavy lock; the median seed by validation loss | the stage's budget is exceeded: **Stop-B** |
| R4 | τ and method by the stage's rules, on the stage's validation sets plus the new validation scans; export ONNX (section 2a); header with the new envelope; `rang.learned.load` accepts it; interpreter against PyTorch within 1e-4 | export refused or I2 fails: **Stop-X** |
| R5 | Gates: the held-out scans of the configuration, read once (section 4); the non-regression check (section 4) | — (the outcome is read from section 5) |
| R6 | Cost: section 7's rule; a new exclusive timing only if it requires one | — |
| R7 | Report: a "Measured result" section in a new note `research/<stage>-retrain-<config>.md`, frozen before R1 by copying this note's sections 4-5 with the configuration filled in; receipts under `research/results/`; a branch for the coordinator | — |

### 2a. Export form (frozen)

The ONNX graph has only `Conv` and `Relu` nodes (the interpreter's op list, dl1-contract.md
amendment 2), input `planes` NCHW `(N, C, T, F)`, output `logits` `(N, 1, T, F)`, opset 17, the
header in `metadata_props["rang.learned"]`. A trainer whose module takes another layout (F5's
`f5net` takes NHWC and exports Identity, Transpose, Constant and Gather, refused by the interpreter,
checked 2026-11-20) exports a conv-only copy of the same weights; the exported file's weights must be
byte-equal to the trainer's (as `examples/dl1_export_f3.py` checks).

## 3. The held-out configuration (rule, frozen)

1. **1k channels** (836 kHz channels, 1,024 across L-band) if capture block **1735892129** (the only
   1k block on hand; [dl2-data.md](dl2-data.md); 62 antennas, 8.002 s) is absent from the passed
   stage's training and validation data. Split (from DL2's manifest, calibrator class, time order):
   train scans 1 (J1939-6342 bpcal, 74 dumps), 3, 7, 11, 15 (J1744-5144 gaincal, 14-15 dumps);
   validation scan 19; **held-out scans 23 (gaincal) and 25 (bpcal, 74 dumps)**. Target class: train
   scan 9, validation 13, held-out 17.
2. Otherwise, **core-only sub-array**: the 16 live antennas nearest the median antenna position
   (G-sub's `core16`), never drawn in training (F5 draws 24 or more), on the passed stage's training
   blocks for train and validation, and on its held-out blocks' scans that its own gates did not read
   for R5, named by a dated amendment before R1.

Which applies is decided from the passed stage's manifest. **Agreed with session D through the
coordinator, 2026-11-20, before this freeze:** F6 excludes 1735892129 from training and validation,
so **rule 1 (1k channels) applies** to F6; rule 2 stays as the fallback for any other stage. The
dry run (section 8) uses rule 1 on F5.

## 4. Gates (frozen)

- **The stage's own gates**, each re-scored on the configuration's held-out scans with T-relative
  bars recomputed there (T run on the same scans): for a flagger as F5's, R1, R1m, R2, R3, R4
  (calibrators), R5, G-perm, G-drop and G-sub where defined. A gate whose test cannot be built on the
  configuration is listed as **undefined** with the reason (for 1k: G-chan's 4× averaging would give
  3.3 MHz channels, outside any envelope; G-sub on 16 antennas is undefined when rule 2 applies).
  Undefined gates are not passes.
- **Non-regression** on the stage's own **validation** sets (never its spent held-out sets): the
  retrained method's R1 pooled ≥ the passed method's − 0.02 and R3 within ±0.10 of it.
- **Contract:** `rang.learned.load` accepts the file; I2 (interpreter against PyTorch, ≤ 1e-4).

## 5. Outcome (first that applies)

| Outcome | Condition |
| --- | --- |
| Stop-0, Stop-T, Stop-L, Stop-B, Stop-X | section 2's stop at that step |
| **Stop-R** | the recipe cannot run unchanged on the configuration (a code change beyond a loader is needed); the change goes to a new proposal note |
| **F** | a defined gate of section 4 fails, or non-regression fails |
| **P** | every defined gate and non-regression pass: the retrained weights may ship for the union envelope, on the owner's word |

One retrain per configuration; a second needs a dated amendment and held-out scans not yet read.

## 6. Manifest schema (`retrain-manifest.json`, frozen)

`{"stage", "tenant", "note", "commit", "weights": {"path", "sha256"}, "architecture" (the header's),
"ops", "initializer_shapes", "features": {"id", "level", "degree", ...}, "labels" (rule and section),
"factory": {"command", "seeds"}, "trainer": {"command", "steps", "seeds", "budget_gpu_h"},
"exporter", "tau_rule", "method_rule", "method": {"tau", "kappa"}, "gates": [{"name", "bar",
"section"}], "cost": {"c1": {...}, "c2", "receipts"}, "data": {"train": [{"name", "sha256"}],
"validation": [...], "heldout_spent": [...]}, "teachers": [{"name", "version", "strategy",
"sha256"}]}`.

## 7. Cost rule (frozen)

The retrained network's **work per cell equals** the passed stage's when all of: the header's
`architecture` is equal; the ONNX op list and every initializer's shape are equal; the feature id,
level, degree and method kind (N5 or N5W4) are equal. Then the passed stage's C1 and C2 readings
and receipts are **reused** and no exclusive night is needed; a τ change keeps the work equal. A
change of κ or of the method kind (W4 on or off), or any other change, needs a new exclusive timing
by the stage's own cost protocol.

## 8. Dry run on F5 (validation only; decides nothing)

F5 has not passed (its validation dry run predicts R5 and G-drop failures), so the dry run tests the
procedure, not a stage: F5's calibrator arm N5-ph (seed 3, τ −3.0, method N5;
[f5-flagger.md](f5-flagger.md) on branch `dl3-f5`) stands in for the passed stage, on rule 1's 1k
split. Reduced, labelled as such: train scans 1 and 3, validation scan 19, one seed, 1,000 steps on
CPU (nash, heavy lock, nice 19); every step R0-R4 and R6, and R5's measures **on validation scan 19
only**. **Held-out scans 23 and 25 are not read**, so the agent test keeps them. Each place where the
procedure was unclear, missing or needed code is recorded under "Measured result" with the fix made
to the procedure page.

## 9. The agent test (after a stage passes)

A fresh session (no context from this one) is started by the coordinator with only: this repository
at a named commit, `docs/agents/retrain-a-stage.md`, the passed stage's manifest and section 3's
configuration. It runs R0-R7. **Pass:** it reaches outcome P or F by section 5's rule, with every
receipt, and a reviewer confirms the gates were scored as frozen; outcome P is needed for issue
#46's "meets the gates". Every clarifying question the session asks is counted as a procedure defect
and fixed in the page; two attempts at most (a second after fixes, on the same held-out scans only
if the first did not reach R5).

## 10. Stages

| Stage | Work | Host |
| --- | --- | --- |
| 0 | this note, committed and pushed before any procedure or script | |
| 1 | `docs/agents/retrain-a-stage.md`, `.claude/skills/retrain-a-stage/SKILL.md`, index entry | |
| 2 | dry run on F5 (section 8); fixes to the page | nash CPU |
| 3 | the agent test (section 9), when a stage has passed and its manifest exists | nash / glacier GPU |

## Amendments

(none)

## Measured result

(none yet)
