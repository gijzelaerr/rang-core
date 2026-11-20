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
3. **Label-audit bar sized on validation**, pooled over a scan's realisations or with a minimum
   number of strong (A ≥ 3) events per draw, so one weak draw cannot stop a class.
4. **G-sub outer32 over-flagging** (F5 targets, held out: R3 1.85 on ESO137 chunk 12 against
   1.5). Likely the same antenna-set normalisation as G-drop, but measured, not assumed: R3 on the
   simulated outer32 layout of F6's validation scans, before and after fix 2.
5. **R2 H2 near miss** (F5 targets, held out: 0.945 against 0.95). Reported per seed on F6's
   validation; no special fix unless it is systematic across seeds.

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
