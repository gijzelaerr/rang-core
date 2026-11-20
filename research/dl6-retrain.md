# DL6: retrain a passed stage for a held-out configuration

Task DL6 (issue #46, [dl-plan.md](dl-plan.md) section 8), branch `dl6-retrain` from origin/main
`7cd42b26`. **Status at freeze (2026-11-20): proposed. No procedure, script or run exists. No
stage has passed its gates yet;** F6 (session D, issue #40's successor) is expected to be the first.
Results go under "Measured result"; nothing above it changes except by dated, labelled amendment.

**Status (2026-11-20, 14:00 SAST): stages 0-2 done.** Note frozen (`f4ade32c`); procedure
`docs/agents/retrain-a-stage.md` and skill `retrain-a-stage`; dry run on F5 measured (below), its
gaps fixed in the page. Stage 3 (the agent test) waits for a passed stage (F6) and its manifest.

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

### Dry run on F5, 2026-11-20 (section 8; validation only, decides nothing)

F5's calibrator arm N5-ph (seed 3, τ −3.0, method N5; branch `dl3-f5` at `533d9b9f`) as the
stand-in passed stage; rule 1's 1k split of 1735892129. Reduced as frozen: train scans 1 and 3 (two
realisations each), validation scan 19, one seed, 1,000 steps. Code: `dl3-f5` unchanged in a nash
worktree (`~/Worktrees/rang/dl6-dryrun`, own venv); this branch's
[dryrun-scripts/](results/dl6-retrain/dryrun-scripts/) wrap it. Run root
`nash:~/rang-data/outputs/dl6-dryrun-20261120/`. **Held-out scans 23 and 25 were not read.**
Training moved to glacier's GPU on the coordinator's word (nash's queue was full). Compact receipts: [dryrun/](results/dl6-retrain/dryrun/).

**Reading.** Every step of R0-R6 ran from the page plus a loader; the reduced retrain stops twice
as frozen (Stop-T at R1, Stop-L at R2), and on its own validation scan it would also fail R2's H1.
Nothing here is a result about F5 or F6: one seed, 1,000 steps, two training scans, scored on the
scan τ was fit on.

| Step | Result | Host, wall |
| --- | --- | --- |
| R0 manifest | written by hand from F5's note: [f5-n5ph-retrain-manifest.json](results/dl6-retrain/f5-n5ph-retrain-manifest.json); null fields: tenant, ONNX file, exporter, cost readings, sha256 per data set | – |
| R0 entry | `envelope_violations`: `channel_width_hz 835937.5 outside [208984.375, 208984.375]` → held out; no 1735892129 scan in F5's data | glacier |
| R1 teachers | DL2's labels used (T: rang 0.3.0 at `4bb29720`, CARACal first-pass YAML; A: **AOFlagger 2.13.0**, CARACal `firstpass_QUV.rfis`). F5's A is AOFlagger 3.5.0, generic strategy: **Stop-T by the rule**; continued, labelled | – |
| R2 loader | `dl6_load_ms.py` (python-casacore, read-only): scans 1, 3, 19, 139,934 / 26,474 / 28,365 cross rows, no FLAG_ROW rows; MS hashes equal DL2's manifest; input flags 0.31 / 0.30 / 0.35. Against rang's own reader (`read_cells`), DATA, FLAG, ANTENNA1/2, TIME of 200 rows: **bit-equal** | nash, 168 s |
| R2 band | F5 sees 1070.0-1497.8 MHz only (LUNO tiles 8-23); the 1k scans cut to channels 256-767 (512) to match | – |
| R2 factory | `f5_shards.py` through `dl6_run.py` (set list, loader and flag cache patched; nothing else): validation 113 s, train 640 s, 1.7 GB of shards, peak RSS 13.4 GB | nash, 8 slots |
| R2 audit | **Stop-L as frozen**: ignored uninjected 0.525 (scan 1) and 0.410 (scan 19) against 0.40; T's / A's recall of injected positives 0.38 / 0.60 on scan 1, 0.86 / 0.93 on scan 19, 0.88 / 0.89 on scan 3 | – |
| R3 train | `f5_train.py` seed 1, 1,000 steps, CUDA under `gpu_run.py run --owner rang`: 45 s training, 56 s booked; validation loss 0.0752; flat sha256 `de7f95e2…` | glacier GPU, 12:43-12:44 SAST |
| R4 export | `dl6_export.py`: Conv ×7, Relu ×5 only; weights byte-equal (3,201); `rang.learned.load` accepts; **I2 6.7e-6**; ONNX sha256 `1836d236…` | glacier |
| R4 τ, method | `f5_tau.py` through `dl6_run.py` on validation scan 19 only (F5's MAIN_7 and f2sim-v not rerun): **τ −3.5** (F5 −3.0), pooled recall 0.977, N5 adds 2,286,381 cells against T's 2,316,121; **κ 5 qualifies, method N5W4** (F5: N5, no κ qualified) | nash, 47 s |
| R5 on validation | `f5_heldout.py real --validation` on scan 19, every case; F5's `f5_verdict.py`. The scan τ and κ were fit on, so optimistic; decides nothing. R1 1.000 (T 0.931); R1m all 1.000; **R2 H1 0.816 against T 1.000 (fails)**, H2 1.000, H3 1.000 (T 0.505), H4 1.000 (T 0.639), H4n 0.989 (T 0.366); R3 1.154; R4 J 0.446 (bar 0.250); R5 0.988; G-perm exact; G-drop k = 1 / 4 / 8: 0.036-0.044 / 0.072-0.085 / 0.111-0.155 (bars 0.05 / 0.20 / 0.25); G-sub core16 and outer32 pass; G-chan (reported) R1 1.000 (T 0.770), R3 0.683 | nash, 733 s |
| Non-regression | **not run**: F5's validation sets (MAIN_7, f2sim-v) need F5's data root and the mixed retrain, which the reduced dry run does not make | – |
| R6 cost | header `architecture`, op set and all 14 initializer shapes equal the manifest's (3,152 multiply-adds per cell), but the **method kind changed (N5 → N5W4)**: by section 7 the timing is **not** reused and a new exclusive run would be needed. (F5 has no C1/C2 reading yet in any case.) | – |

### Where the procedure was unclear or missing (fixed in the page unless noted)

1. **Export form.** F5's `export_onnx` gives Identity ×5, Transpose, Constant, Gather (NHWC input,
   `[:, 0]`); refused by name. Fixed in section 2a and the page (R4); passed to D, whose F6 export is
   now NCHW and Conv/Relu only (coordinator, 2026-11-20).
2. **torch shares equal initializers through Identity nodes** (zero biases at init, or any two equal
   tensors): the exporter must give each its own initializer (`dl6_export.py` does).
3. **Named-set factories.** F5's factory, τ and scorer read named LUNO/ESO137 sets and F4's flag
   cache layout; a new configuration needs a loader plus a flag cache. Allowed by R2 as written; the
   page now names the flag-cache layout.
4. **Band.** The procedure did not say that the configuration is cut to the stage's band; now R2.
5. **Teacher versions.** DL2's AOFlagger (2.13.0, CARACal strategy) is not F5's (3.5.0, generic):
   Stop-T as frozen. Either the stage's manifest pins DL2's teachers (F6 trains on DL2's labels), or
   R1 runs the stage's own teachers on the new scans. For the agent test, F6's manifest decides.
6. **Strategy inputs in ignored `outputs/`.** `rang.f2flag` reads CARACal's YAML from
   `outputs/caracal-strategy-inputs-8f7bb363/` (not in git); a fresh worktree fails at W3. The
   manifest must list staged inputs; the page now says so.
7. **Manifest.** F5 records no tenant, ONNX file, cost readings or one sha256 per data set; the
   stage's own note must provide them before an agent test (F6, before Monday).
8. **Branch age.** `dl3-f5` predates the interpreter (`2d9f4c5f`), so R4's contract checks ran on
   main's build on glacier; the stage's branch must contain main at or after `2d9f4c5f`.
9. **Label audit on another block.** 1735892129 fails F5's label audit (ignored uninjected above
   0.40 on two of three scans): at 1k, in this block, the teachers flag far more native RFI than in
   LUNO. Not a procedure defect: a real retrain would stop here (Stop-L). F6's audit bar, sized
   anew (F6 proposal item 4), decides for the agent test.
10. **Teacher flag fractions.** In F5's band, DL2's T flags 0.44-0.51 and A 0.51-0.62 of the kept
    cells of scans 1, 3 and 19 (input flags included), which is why the label audit stops (item 9).
11. **R6 depends on R4.** The method rule can change the method kind (here N5 → N5W4), so the
    cost check is read after R4's method, never from the architecture alone; the page says so.
12. **Read gates, not summaries.** F5's `f5_verdict.py` lists `failed: []` while its own R2 entry
    for H1 has `pass: false`; the page tells the agent to read every gate entry.
13. **Hosts.** nash's heavy-lock queue held the first booking 2 h 50 min; the chain runs as one
    booking and stops before training so the GPU step does not hold CPU slots.

## For the coordinator

- Procedure, skill and index entry are on `dl6-retrain`; merge needs no owner decision.
- Agent test (section 9) needs from F6 before it starts: a `retrain-manifest.json` per section 6
  (tenant, ONNX file in the 2a form, cost receipts, one sha256 per data set, staged inputs), teacher
  pins that match DL2's labels or a plan to rerun F6's teachers on 1735892129 (item 5), and F6's
  label-audit bar (item 9: F5's bar stops this block). Held-out scans 23 and 25 are unread.
- nash keeps the dry run's root `~/rang-data/outputs/dl6-dryrun-20261120/` (scans as npz, 1.7 GB
  shards) and worktree `~/Worktrees/rang/dl6-dryrun` (detached at `dl3-f5`) until the agent test or
  your word; glacier keeps only the weights and ONNX file in 
  `D:/rang/outputs/dl6-dryrun-20261120`.
