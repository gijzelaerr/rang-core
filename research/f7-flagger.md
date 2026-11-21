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

**D1 measured (2026-11-21, nash; `~/rang-data/outputs/f7-d1-20261121/`).** Seed 2, balanced
real batches, 30,000 steps in 6,544 s (12 threads); validation loss 0.110 (F6's seed 2: 0.082, on
SARAO-dominated validation shards). `f6_tau.py`: N5W4, τ −4.5, κ 3, as F6. Uninjected validation
DATA, added cells against T:

| Set | N5 | W4 | method (N5 ∪ W4) | T | A | R3 (method) | R5 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LUNO MAIN_7 | 1,580,028 (F6: 2,727,768) | 2,170,869 | 2,896,444 | 209,120 | 2,744,976 | **13.9** (F6 16.9) | 0.993 |
| 1573212012 scan 1 | 41,984,280 | 19,337,688 | 45,279,514 | 44,755,207 | 40,264,157 | 1.01 | 0.977 |
| scan 3 | 44,392,429 | 24,128,564 | 46,742,335 | 49,460,290 | 42,893,083 | 0.95 | 0.984 |
| scan 5 | 4,241,059 | 4,986,228 | 6,021,010 | 5,098,743 | 10,230,054 | 1.18 | 0.999 |

Reading: balanced sampling cuts the network's LUNO cells by 42 % and keeps SARAO in place, but N5
alone is still 7.6 × T on LUNO, and W4 (the anomaly arm; κ 3, independent of the network) adds
2.17M cells there by itself (10.4 × T). P1 alone does not fix the calibrators. Two things follow
for the proposal: W4's κ needs a per-observation rule or W4 must go for low-flag-rate data, and
the network needs P2 (or P3) on top of P1. The full verdict (every gate) lands in the same run root.

**D2 measured (2026-11-21, validation only, nash; `~/rang-data/outputs/f7-d2-20261121/`).**
`examples/f5_f6_probe.py --level 20` with F6's target weights (seed 2, τ −4.5), 128 baselines,
G-drop's first draw (seed 20265301). Share of eligible cells whose plane moves by > 0.1 (median
move, asinh units), and N5's change with that group frozen at its full-array value:

| Set, k dropped | N5 flags (128 baselines) | N5 change | F4 spectral moved (median) | 2c+2d blocks moved (median) | change, spectral frozen | change, blocks frozen |
| --- | --- | --- | --- | --- | --- | --- |
| ESO137 chunk 10, k = 1 | 57,125 | 0.084 | 7 % (0.05) | 85 % (0.18) | 0.074 | 0.051 |
| ESO137 chunk 10, k = 8 | 53,798 | **0.319** | **99.99 % (0.29)** | 99.98 % (0.58) | **0.205** | 0.267 |
| SARAO 111, k = 1 | 1,520,565 | 0.012 | 3 % (0.04) | 44 % (0.09) | 0.009 | 0.010 |
| SARAO 111, k = 8 | 1,568,012 | 0.037 | 66 % (0.12) | 98 % (0.29) | 0.030 | 0.027 |

Reading: on ESO137 the planes move two to three times as far under the same dropout as on SARAO
(spectral 0.29 against 0.12, blocks 0.58 against 0.29 at k = 8), and no single group explains the
change; the spectral planes are the largest single lever (0.32 → 0.21 when frozen). The relative
change is also inflated by ESO137's low flag count (54k cells on 128 baselines against SARAO's
1.57M): the same mechanism as LUNO's, a low-flag-rate observation. Both point to P2 (per-observation
normalisation of the planes) before P4; ESO137's 512 channels make the per-channel spectral
statistics noisier, which P4 (1k-channel SARAO blocks) would address in training.

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
