# F7: a fast supervised RFI flagger for MeerKAT L-band, sixth protocol (proposal, not frozen)

Proposal for v0.5.0, drafted 2026-11-21 after F6 ([f6-flagger.md](f6-flagger.md)). **Status:
proposal. The owner decides scope; nothing here is frozen.** Validation-only diagnostics may run
on nash before the owner's decision; no held-out set is read.

## 0. Starting point (F6, frozen 2026-11-21)

- Every SARAO validation scan (1573212012: calibrator scans 1, 3, 5; target scans 111, 113, 115)
  passes every gate in both classes: R3 0.82-1.16 × T, R5 0.98-0.99, G-drop ≤ 0.04 / 0.10 / 0.20.
- Calibrators fail on **LUNO MAIN_7**: the network adds 2.73M cells, T 0.21M, A 2.74M, and 1.8M
  of the network's cells are flagged by neither teacher. T flags 1.2 % of LUNO's eligible cells
  and about 55 % of SARAO's (45×). Threshold-side calibration (K1-K3) does not close the gap.
- Targets fail on **ESO137 chunk 10** (512 channels): G-drop 0.11 / 0.22 / 0.35 at k = 1 / 4 / 8,
  outer32 R3 1.94. The targets' real training batches are already half ESO137 (28 of 52 real
  shards), so more ESO137 data alone is unlikely to be the fix; the calibrators' are 10 % LUNO
  (20 of 190).
- Held out, unread, for F7: LUNO MAIN_0, 12, 14; ESO137 chunks 1, 3, 5, 7, 9, 15, 17; f4sim-t;
  SARAO 1678312253 (29 antennas), 1674958551 (32 outer antennas), 1579022459 (58 antennas, unseen
  observation; G-obs), all scans.

## 1. Candidate fixes (proposed)

| # | Fix | Targets | Cost to try |
| --- | --- | --- | --- |
| P1 | **Source-balanced sampling**: real batches drawn equally from F4-era sets and SARAO | LUNO R3 (calibrators) | one retrain, no new shards |
| P2 | **Per-observation input normalisation**: the per-cell planes divided by a robust per-observation scale (e.g. the scan's median of the per-baseline σ planes), so the input does not carry the observation's flag level | LUNO R3, ESO137 | Rust kernel change, new shards, retrain |
| P3 | **More LUNO-like and ESO-like data**: further F4-era groups, or SARAO observations with low flag rates, in training | LUNO R3 | data selection, new shards, retrain |
| P4 | **SARAO 1k-channel and sub-array blocks** for diversity (1735892129 excluded so far for DL6) | ESO137 (channel count), G-sub | new shards, retrain; channelisation enters G-chan |
| P5 | **K2/K3 for targets** (F6 2d-3: R3 with margin on ESO137 and SARAO; scored in full on validation in F6's run root, `val-target-K2/`, `val-target-K3/`) | target R3 | none; does not address G-drop |

## 2. Cheap diagnostics first (validation only, nash)

- **D1 (P1, calibrators).** Retrain seed 2 only on F6's calibrator shards with source-balanced
  real batches (`f5_train.py --balance-real`: half the real batches from `luno-*` shards, half
  from `sarao-*`), 30,000 steps, 12 threads; then `f6_tau.py` and the complete validation scorer.
  Question: does R3 on LUNO MAIN_7 fall to ≤ 1.5 while every SARAO validation scan keeps passing
  every gate? Read on validation only; no bar changes. About 3 h on nash.
- **D2 (targets, diagnosis).** The plane-movement probe (`examples/f5_f6_probe.py --level 20`) on
  ESO137 chunk 10 under the G-drop draws: which planes move when antennas drop on a 512-channel
  set, against the same on a SARAO target scan. Minutes; it chooses between P2 and P4 for targets.
- **D3 (P5, recorded).** K2/K3 target variants' complete validation verdicts, when F6's chain 5
  finishes: does any calibration also fix G-drop on ESO137? (Expected no: G-drop compares flags
  under dropout, and calibration is per baseline.)

A diagnostic decides nothing alone: a fix enters F7's frozen protocol only through the owner's
scope decision and a proposal section committed before its measurement.

## 3. Gate question for the owner (no decision taken here)

R3 bounds the method's added cells by T's: 0.5 min(T, A) / T ≤ R3 ≤ 1.5. T flags 1.2 % of LUNO
MAIN_7 and about 55 % of SARAO; A flags 16 % of LUNO. On LUNO the network sits near A's level
(but 1.8M of its cells are neither teacher's). Options:

1. **Keep R3 against T** (F3-F6's rule): a flagger must match T's level per observation.
2. **R3 against a teacher band**: min(T, A) / 2 ≤ added ≤ 1.5 max(T, A), so an observation where
   the teachers disagree by 13× does not decide the gate by itself.
3. **R3 against the consensus**: added within bounds of T ∪ A, plus a cap on cells neither teacher
   flags (the 1.8M on LUNO would then fail directly, and stay visible).
4. **R3 per observation class**: separate bars for low-flag-rate observations, sized from T and A
   only (never from the candidate), before any F7 number.

Any change is the owner's, dated, and made before F7 trains.

## 4. Data and splits (proposed, unchanged from F6 unless the owner widens scope)

Training: F6's (four SARAO blocks, LUNO and ESO137 training sets, simulations). Validation: F6's
(1573212012; LUNO MAIN_7; ESO137 chunk 10). Held out: section 0's list, read once after an F7
freeze. 1735892129 (1,024 channels) stays excluded unless P4 is in scope.

## 5. Coordinator

- Ready to run now (validation only, honest booking: 12 slots, 160 GB for D1's trainer by F6's
  measured peak of 153 GB with mapped shards): D1, D2.
- Needs the owner: scope among P1-P5, and the R3 question (section 3).
