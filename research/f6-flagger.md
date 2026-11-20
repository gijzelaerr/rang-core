# F6: a fast supervised RFI flagger for MeerKAT L-band, fifth protocol (draft)

Task F6 (issue #40, after F5; v0.4.0's critical path to DL6, #46), branch `dl3-f6` from origin/main
`92e67e2f` with `dl3-f5` merged. **Status: draft, not frozen. Nothing of F6 trained, and no F6 data
read.** It freezes only after the complete scorer has run on validation, every gate and stop bar
included, with bounds sized by F6's own network (coordinator, 2026-11-20). The owner's fork
(2026-11-20, `research/v040-plan.md`): if F6 has not passed by Monday 2026-11-23 21:00 SAST,
0.4.0 ships on Tuesday with DL6 as a known limitation.

F6 starts from F5 ([f5-flagger.md](f5-flagger.md)): F5's cost gate passed in both classes (C1
0.365-0.409, C2 1.00), its R1 and R2 far above T on validation, and its validation dry run predicted
failures of R5 (0.338 against 0.80) and G-drop (0.14 against 0.05 for one dropped antenna). F5's
"F6 proposal" section and its plane-sensitivity probe are F6's starting point.

## 1. Data (rules fixed before any F6 data are read)

**Training-set cut-off (coordinator, 2026-11-20, written before any F6 data were read).** F6's
SARAO training set is every scan of session C's training blocks whose stage-1 teacher labels are
complete (done-marker and sha256 in C's run root, `research/dl2-data.md` section 20) by
**2026-11-21 06:00 SAST**. The set is fixed by that time, never by results. A training block with no
complete calibrator scan by then is left out of F6's calibrator class, and the note says so. The
scans the rule selects are listed here at the cut-off, before any of them is read.

**Applied, 2026-11-20 (labels complete 15:57 UTC, before the cut-off; session C's
`manifests/stage1.json`, sha256 `94f512db1d07c2c5…`, read for its scan list only, no visibility
read):**

| Block | Role | Scans (calibrator + target) | Labels |
| --- | --- | --- | --- |
| 1571938260 | train | 46 (43 + 3) | rang, Tricolour 0.2.1, AOFlagger 2.13.0, all complete |
| 1611426666 | train | 17 (14 + 3) | complete |
| 1629213076 | train | 20 (17 + 3) | complete |
| 1749428161 | train | 14 (11 + 3) | complete |
| 1735892129 | excluded (DL6) | 11 (8 + 3) | complete, not used |
| 1573212012 | validation | 32 (29 + 3) | complete |
| 1678312253, 1674958551, 1579022459 | held out | 26, 22, 31 | none, as the rule requires |

So F6's SARAO training set is **97 scans (85 calibrator, 12 target) from four blocks**, and every
training block has calibrator scans. C reports rang's Tricolour port and Tricolour 0.2.1
bit-identical on 34 of 140 scans and differing on 106, by about 5e-8 of cells where sampled.

| Role | Data |
| --- | --- |
| Train | the cut-off rule's scans of C's training blocks 1749428161, 1629213076, 1571938260, 1611426666 (1735892129 excluded, below); LUNO MAIN_1, 2, 4, 5, 6; ESO137 chunks 0, 2, 4, 6, 8, 14, 16; F2's simulations |
| Validation | SARAO block 1573212012; LUNO MAIN_7; ESO137 chunk 10; f2sim-v |
| **Held out, read once** | SARAO blocks **1678312253** (29 antennas), **1674958551** (32 outer antennas), **1579022459** (58 antennas, unseen observation; G-obs); LUNO **MAIN_0, 12, 14** (F4's, unread); ESO137: whatever of chunks 1, 3, 5, 7, 9, 15, 17 F5 leaves unread (F5 reads 11, 12, 13); **f4sim-t** calibrator scans (F5 did not read them) |
| Excluded | block **1735892129** (1,024 channels): kept out of F6's training and validation for DL6's other-channelisation test (coordinator, 2026-11-20; B's split inside it is DL6's) |

The held-out SARAO blocks need teacher labels made at the read: C's runner (`TEACHERS=rang,aoflagger
HELDOUT=1 teach_block.sh <cbid> 6 k/2`, k = 0, 1; about 5 h for the three side by side on nash),
started beside F6's scoring after the freeze.

## 2. Fixes from F5, each measured on validation before the freeze

1. **Hybrid positives** (R5): native cells flagged by both T and A with strength s ≥ 3 on the
   uninjected DATA are positive; Landman's scheme otherwise (injections, simulation truth; T- or
   A-only native cells ignored).
2. **Block planes robust to the antenna set** (G-drop): z, Q and 𝒯 normalised over a fixed
   reference or per baseline, not over the antennas present; the polish's rank-dependent bias
   removed or made irrelevant. Measured with `examples/f5_f6_probe.py` and G-drop on validation.
   *Measured, 2026-11-20 14:10-14:17 SAST, glacier, validation LUNO MAIN_7, one antenna dropped
   (seed 20265301), 128 baselines, N5-ph seed 3 at τ −3.0 (`examples/f5_f6_probe.py`,
   `outputs/f6/probe-L*.json` in this worktree):*
   - **Per-antenna scale alone does not help** (kernel levels 10-12: z and Q scaled by each
     antenna's own spread over its channel blocks): the block planes still move on 86 % (2c) and
     82 % (2d) of cells (level 0: 84 %, 78 %), and the planes' scale is not where the dependence
     lies. Kept in the kernel as a measured negative; F6 does not use it.
   - **Holding both block groups at their full-array values** cuts N5-ph's flag change from 0.152
     to **0.054** (bar 0.05; F4's N4 0.027). So about two thirds of G-drop comes from the block
     planes, and the rest from cells near τ. The fix has to make the polish solution itself
     insensitive to the antenna set (its per-cell centring and its rank-dependent fixed point),
     for example an M-estimator solved to convergence, or γ measured against a fixed reference
     set of antennas, then measured the same way before any training.
   *Second candidate, measured 2026-11-20 on nash (same probe, `outputs/f6/probe-L{0,20,30}.json`
   in nash's dl3-f6 worktree):* the **one-step factorisation** (kernel levels 20-22: s the median
   over all baselines, each antenna's term the median over its own baselines of y − s, no
   iteration; F4's antenna-median form per block) moves the block planes less when one antenna is
   dropped: 2c on 66 % of cells (median move 0.136 asinh units) against the polish's 84 % (0.182),
   2d on 49 % (0.098) against 78 % (0.153). One-step with the per-antenna scale (levels 30-32) is
   in between (70 %, 59 %). The remaining move, about 0.13, is what removing one of about 55 terms
   from a median does to a statistic normalised by its own spread (about 1/√n of it): no
   factorisation removes it. **Decision (proposed for the freeze): level 20, plus antenna dropout
   on every real training realisation** (dl-plan section 6 item 7), so the network learns not to
   rely on that last bit. G-drop's bound is fixed below, independently of F6.
3. **Label-audit bar sized on validation**, pooled over a scan's realisations or with a minimum
   number of strong (A ≥ 3) events per draw, so one weak draw cannot stop a class.
4. **G-sub outer32 over-flagging** (F5 targets, held out: R3 1.85 on ESO137 chunk 12 against
   1.5). Likely the same antenna-set normalisation as G-drop, but measured, not assumed: R3 on the
   simulated outer32 layout of F6's validation scans, before and after fix 2.
5. **R2 H2 near miss** (F5 targets, held out: 0.945 against 0.95). Reported per seed on F6's
   validation; no special fix unless it is systematic across seeds.

## 2a. Bounds are never sized from F6 (rule fixed 2026-11-20, before any F6 validation number)

Coordinator, 2026-11-20: a bound sized from the candidate's own validation result passes by
construction. So every bound F6 freezes is derived from T, A, a predecessor's frozen bar or the
requirement, never from F6.

- **G-drop:** the reference is the classical flaggers' own change under the same antenna dropout
  (same seeds, k = 1, 4, 8; symmetric difference of added cells on the remaining baselines). T's
  change is **0 cells** at every k (measured 2026-11-19 on LUNO MAIN_7, F5's pre-freeze sizing:
  T and W3 flag per baseline), and A, also per baseline, is 0 by construction. The rule (bound =
  T's change plus a margin, or F5's bars if T's change is below them) therefore keeps **F5's
  bars: G-drop ≤ 0.05 / 0.20 / 0.25 of the method's full-array added cells for k = 1 / 4 / 8**.
  F4's network met them (0.03 / 0.07-0.13 / 0.13-0.17); F5's did not.
- **G-perm, G-sub, R1-R5, S1-S3, C1, C2:** F5's frozen bars and rules, unchanged (each defined
  against T, A or a fixed requirement).

## 2c. Label audit for F6 (fixed 2026-11-20 from the validation labels, before training; no network involved)

Validation shards, L20, d = 1 (nash, `~/rang-data/outputs/dl3-f6-20261120/shards/`): calibrators
(LUNO MAIN_7 and 29 calibrator scans of 1573212012, 2 realisations each, plus f2sim-v) pooled:
injected positives 2.6 %, **hybrid positives 15.4 %**, ignored uninjected 36.6 % of eligible
cells; per scan the ignored share reaches 41.3 % (1573212012/scan001). Targets (ESO137 chunk 10,
three target scans of 1573212012): 2.8 %, 10.3 %, 31.8 %. SARAO scans carry far more native RFI
than LUNO (AOFlagger 2.13 `firstpass_QUV` flags about 60 % of the full band), so per-scan ignored
shares near 40 % are the data, not a fault of the labels. F5's per-realisation bars would stop the
calibrator class on validation already (Amendment 3's lesson). **F6's audit (frozen with the note):**
stop a class if, pooled over the class's realisations, ignored uninjected cells exceed **45 %** of
eligible cells, or injected positives fall below **0.1 %**; per-scan shares are reported, never a
stop. Rationale: the bar guards against label sets too sparse to train on; a class pooled at 37 %
and 32 % on validation is far from that.

## 2b. Teachers and loaders (proposed)

- **T** = rang's Tricolour port with CARACal's first-pass YAML (as F3-F5). For SARAO scans, C's
  stage-1 `rang` labels (rang 0.3.0, the calibrator or target first-pass YAML by scan class); on
  the training window (channels 1024-3071) a fresh T agrees with C's on 0.995 of cells (validation
  scan 1573212012/scan051), the rest at the window's edges.
- **A** = **AOFlagger 2.13.0 with CARACal's `firstpass_QUV.rfis`** (C's stage-1 `aoflagger`
  labels, image `stimela_aoflagger_1.2.0.sif`), coordinator's choice of 2026-11-20: CARACal's
  shipped MeerKAT strategy is the better MeerKAT teacher than F3-F5's AOFlagger 3.5
  `generic-default.lua` (which ships for no telescope in particular). This differs from F5's A;
  R4 and R5 use it. LUNO and ESO137 keep F4's cached A (3.5 generic) unless C's runner is run on
  them, which the note will say before the freeze.
- **Loader** `rang.f5flag.load_sarao` (rang's own MS reader): C's frozen MSs, cross-correlations,
  FLAG_ROW rows dropped, channels 1024-3071 (LUNO's 1070-1498 MHz window of the 4,096-channel L
  band), with C's bit-packed labels as per-row T and A. On a typical validation scan T flags 46 %
  and A 60 % of the full band, the MS's own FLAG 17 %.

## 3. Shipping form (frozen commitments)

- Weights in the swap contract's form: ONNX, NCHW `planes` (N, C, T, F) → `logits` (N, 1, T, F),
  Conv and Relu only (`rang.f5net.export_onnx_nchw`, `tests/test_f6_export.py`). Loading through
  `rang.learned.load` is part of F6's shipping gate.
- Cost: if F6 changes the work per cell, a timing night (Sunday 2026-11-22); if not, F5's timing
  stands (cost does not depend on the weights). The note says which.
- Training host: nash's CPU if its wall is within about 2 × glacier's GPU (F5's trainer measured
  on both), else glacier's GPU through `gpu_run`.
- **Licence (owner, 2026-11-20, verbatim: "yeah lets do that license, i think it is fine"):** F6's
  weights, trained on SARAO archive data, ship under **CC BY 4.0**. The ONNX header carries
  `licence: "CC-BY-4.0"` and, in `source`, SARAO's acknowledgement (from `research/dl2-data.md`,
  the archive's terms as session C recorded them): "The MeerKAT telescope is operated by the South
  African Radio Astronomy Observatory, which is a facility of the National Research Foundation, an
  agency of the Department of Science, Technology and Innovation." The same text goes in the
  documentation, with the training blocks' capture block IDs, LUNO (Ben Hugo's permission of
  2026-10-29) and ESO137 (CC BY 4.0, Ramatsoku et al. 2020). SARAO is informed at
  publications@ska.ac.za when a paper uses the weights, as its terms ask of papers.
- **glacier (owner, 2026-11-20: "the computer is all yours until monday"):** exclusive and timing
  runs at any hour, no 4-thread reserve; except 2026-11-20 21:00 to about 06:30 (#47) and the AI
  app's 06:05-06:45 slot. F6's cost night, if needed, runs whenever glacier is idle.
