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
the network needs P2 (or P3) on top of P1. Full verdict (every gate, validation;
`val-verdict-calibrator.json` in the run root): F on R3 (LUNO MAIN_7 13.9), synthetic G-sub, and
now also G-drop on MAIN_7 (worst seed draw 0.056 / 0.179 / 0.262 against 0.05 / 0.20 / 0.25; F6:
0.047 / 0.141 / 0.209); SARAO's G-drop ≤ 0.036 / 0.101 / 0.202, R1 1.00 (T 0.77), R2 above T in
every morphology, S1 and S3 pass. Balanced sampling makes the network more sensitive to the
antenna set on LUNO, the set it now sees more of.

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

**D3 measured, targets (2026-11-21, validation only, nash; `~/rang-data/outputs/f7-d3-20261121/`).**
P2 (level 40, per-observation plane scale; kernel 4de582ea, F6's levels pinned unchanged) plus P1
(balanced real batches), seed 2, F6's scans and seeds re-sharded at level 40; validation loss
0.0335 (F6 seed 2: 0.0366); `f6_tau.py`: N5W4, τ −4.0, κ 4. Complete scorer and verdict on
ESO137 chunk 10 and 1573212012's target scans:

| Gate | D3 targets | F6 targets | Bar |
| --- | --- | --- | --- |
| R1 (T) | 1.000 (0.913) | 1.000 (0.913) | ≥ T − 0.05 |
| R2, worst morphology | 0.989 (H4n) | 0.996 | ≥ T − 0.05 |
| R3 ESO137 / SARAO | 0.31 / 1.17 | 0.42 / 1.16 | lower bound to 1.5 |
| R5 ESO137 / SARAO | 0.808 / 0.992 | 0.893 / 0.992 | ≥ 0.80 |
| G-drop ESO137, k = 1 / 4 / 8 | **0.096 / 0.200 / 0.287** | 0.110 / 0.217 / 0.350 | 0.05 / 0.20 / 0.25 |
| G-drop SARAO, worst | 0.015 / 0.040 / 0.082 | 0.014 / 0.037 / 0.081 | as above |
| G-sub core16 / outer32 | pass / **pass** (outer32 R3 on ESO 1.22) | pass / fail (1.94) | R3 ≤ 1.5 |
| S1 / S2 / S3 | pass | pass | |

Reading: P2 + P1 fixes the targets' outer32 over-flagging and leaves one failure, G-drop on
ESO137 chunk 10 (down 13-18 %, still above every bar; k = 4 is at 0.200 against 0.20). R5 on
ESO137 loses margin (0.81 against 0.80). For F7: the targets' remaining gap is the antenna-set
sensitivity on a 512-channel low-flag-rate observation; D2 names the spectral planes as the largest
single lever, so the next target candidate is P4 (1k-channel SARAO data in training) or a spectral
plane robust to the antenna set, not more normalisation.

**D3 measured, calibrators (2026-11-21, validation only; same run root).** Validation loss
0.116 (D1 0.110, F6 0.082); `f6_tau.py`: N5W4, τ −5.0, κ 3.

| Gate | D3 calibrators | D1 (P1 only) | F6 | Bar |
| --- | --- | --- | --- | --- |
| R3 LUNO MAIN_7 (N5 alone) | **17.8** (11.4) | 13.9 (7.6) | 16.9 (13.0) | ≤ 1.5 |
| R3 SARAO | 0.99 | 0.99 | 1.00 | |
| G-drop LUNO, k = 1 / 4 / 8 | **0.111 / 0.214 / 0.401** | 0.056 / 0.179 / 0.262 | 0.047 / 0.141 / 0.209 | 0.05 / 0.20 / 0.25 |
| G-drop SARAO, worst | 0.040 / 0.077 / 0.129 | 0.036 / 0.101 / 0.202 | 0.036 / 0.100 / 0.196 | as above |
| R1 (T) / R2 worst / R5 LUNO, SARAO | 1.00 (0.77) / 0.962 H2 / 0.987, 0.968 | pass | pass | |

Reading: for calibrators P2 makes LUNO worse on both failing gates; the per-observation scale
amplifies LUNO's quiet residuals (its bulk scale is small, so dividing by it pushes ordinary cells
up). SARAO stays inside every bar, with G-drop improved.

**What D1-D3 decide for F7 (validation only; nothing here is held out).**
- *Targets:* P2 + P1 leaves one failure, G-drop on ESO137 (0.29 at k = 8). F7's target candidate:
  P2 + P1 plus an antenna-set-robust spectral plane or P4 (1k-channel data), measured first on
  ESO137 chunk 10's G-drop.
- *Calibrators:* neither P1 nor P2 closes LUNO (best: P1, N5 at 7.6 × T). The network carries
  SARAO's flag level into LUNO whatever the input scale; W4 alone adds 10 × T there. What is left
  is P3 (more LUNO-like, low-flag-rate observations in training) and the owner's R3 question
  (section 3); W4 needs its own per-observation rule. Without new low-flag-rate training data, a
  calibrator F7 is not within reach on these diagnostics.
- *Cost:* level 40 adds one more split pass over all baselines (the scale), so C1 would need a new
  timing run if P2 enters F7.

**D4 (proposed 2026-11-22 03:15 SAST, before it runs; validation only).** Targets only: level 42,
the same per-observation scaling and balanced batches as D3 but without F4's spectral planes and
2d's variance planes (21 inputs; the kernel's existing level, no code change). D2 found the
spectral planes the largest single lever on ESO137's G-drop. Same scans and seeds, seed 2,
`f6_tau.py`, the complete validation scorer. Question: does G-drop on ESO137 chunk 10 fall below
0.05 / 0.20 / 0.25 while every other target gate (ESO137 and SARAO) keeps passing? Run root
`nash:~/rang-data/outputs/f7-d4-20261122/`; bookings from D3's measured peaks + 30 % or more.

**D4 measured, ESO137 chunk 10 (2026-11-22 06:25 SAST, validation only).** Level 42, seed 2,
validation loss 0.0349; `f6_tau.py`: N5W4, τ −3.5, κ 3. G-drop **0.10 / 0.34 / 0.55** (D3 0.096 /
0.200 / 0.287); R5 **0.686** (fails 0.80); outer32 R3 1.495; R3 0.31. Removing the spectral and
2d planes makes the targets worse: they carry signal the network needs, and the instability is
not theirs alone. W4 (κ 3) now adds more cells than N5 (429,441 against 342,699). The full verdict
lands in `nash:~/rang-data/outputs/f7-d4-20261122/`.

**D5 (proposed 2026-11-22 06:30 SAST, before it runs; validation only, no training).** G-drop on
ESO137 chunk 10 split by arm: N5 alone (logit > τ), W4 alone (anomaly > κ), and the method, for
F6's target method (L20, τ −4.5, κ 4) and D3's (L40, τ −4.0, κ 4), G-drop's draws (k = 1, 4, 8;
seeds 20265301-03). `examples/f7_gdrop_arms.py`. Question: how much of the ESO137 G-drop failure
is W4's, the anomaly arm without learned weights?

**D5 measured (2026-11-22 06:40 SAST, validation only; `nash:~/rang-data/outputs/f7-d5-20261122/`).**
G-drop on ESO137 chunk 10 by arm, worst of seeds 20265301-03 (bars 0.05 / 0.20 / 0.25):

| Method | N5 alone, k = 1 / 4 / 8 | W4 alone (κ 4) | method (N5 ∪ W4) |
| --- | --- | --- | --- |
| F6 targets (L20, τ −4.5) | 0.095 / 0.163 / 0.325 | 0.204 / 0.456 / 0.802 | 0.110 / 0.217 / 0.350 |
| D3 targets (L40, τ −4.0) | **0.066 / 0.118 / 0.220** | 0.204 / 0.456 / 0.802 | 0.096 / 0.200 / 0.287 |

Reading: W4, the anomaly arm with no learned weights, is the unstable part (0.80 at k = 8); D3's
network alone passes G-drop at k = 4 and 8 and misses k = 1 (0.066 against 0.05). P2 + P1 cut the
network's own sensitivity by 30-32 %.

**D6 (proposed 2026-11-22 06:45 SAST, before it runs; validation only, no training).** D3's target
weights and τ (−4.0) with W4 off (method N5), through the complete validation scorer and verdict on
ESO137 chunk 10 and 1573212012's target scans (A cached from F6's run). Question: does N5 alone
pass every target gate but G-drop at k = 1, and what does dropping W4 cost R1, R5 and S3? This
is a method choice made after D5's numbers, so if F7 adopts it, F7 must re-select κ by a rule
written before its own validation read.

**D4 full verdict (2026-11-22 07:31 SAST):** F on R5 (ESO137 0.686) and G-drop (ESO137); every
SARAO target gate passes.

**D6 measured (2026-11-22 08:51 SAST, validation only; `nash:~/rang-data/outputs/f7-d6-20261122/`).**
D3's target weights, τ −4.0, W4 off (N5 only). Complete scorer and verdict:

| Gate | D6 | D3 (N5W4) | F6 | Bar |
| --- | --- | --- | --- | --- |
| R1 (T) | 1.000 (0.913) | 1.000 | 1.000 | ≥ T − 0.05 |
| R2 worst (T) | 0.901 H3 (0.568) | 0.989 | 0.996 | ≥ T − 0.05 |
| R3 ESO137 / SARAO | 0.25 / 1.02 | 0.31 / 1.17 | 0.42 / 1.16 | lower bound to 1.5 |
| R5 ESO137 / SARAO | **0.801** / 0.992 | 0.808 / 0.992 | 0.893 / 0.992 | ≥ 0.80 |
| G-drop ESO137, k = 1 / 4 / 8 | **0.066** / 0.118 / 0.220 | 0.096 / 0.200 / 0.287 | 0.110 / 0.217 / 0.350 | 0.05 / 0.20 / 0.25 |
| G-drop SARAO, worst | 0.013 / 0.032 / 0.064 | 0.015 / 0.040 / 0.082 | 0.014 / 0.037 / 0.081 | |
| G-sub core16 / outer32, S1-S3 | pass | pass | outer32 fail | |

Reading: with W4 off the targets fail one gate, G-drop on ESO137 at k = 1 (0.066 against 0.05);
R5 on ESO137 sits on its bar (0.801). **Targets are within reach for F7**: P1 + P2, N5 only, and one
more step on single-antenna robustness on the 512-channel set (P4's 1k-channel data, or dropout of
1 antenna weighted up in training). Every choice in D1-D6 was made after seeing validation
numbers, so an F7 target protocol must re-select τ, κ (or W4's removal) and the level by rules
written before its own validation read, and the held-out sets of section 0 decide it.

**D7 (proposed 2026-11-22 09:10 SAST, before it runs; validation only).** Targets: D3's recipe
(level 40, balanced batches, seed 2) with **eight dropout realisations per ESO137 training chunk**
instead of four (realisations 4-7 new, seeds continuing F6's series; dropout 0-8 antennas as
before); every other training shard is D3's, unchanged. No 1k-channel data (1735892129 is DL6's
held-out configuration). τ by `f6_tau.py`, W4 off (as D6), the complete validation scorer.
Question: does G-drop on ESO137 at k = 1 fall to ≤ 0.05 with k = 4, 8 and every other target gate
still passing, R5 on ESO137 included? Run root `nash:~/rang-data/outputs/f7-d7-20261122/`.

**D7 measured (2026-11-22 13:12 SAST, validation only; `nash:~/rang-data/outputs/f7-d7-20261122/`).**
86 target training shards (56 ESO137); training 5,107 s, validation loss 0.0344 (D3 0.0335);
`f6_tau.py` τ −4.0; W4 off. Complete verdict: F on one gate, **G-drop on ESO137 at k = 1: 0.060 /
0.063 / 0.065 per seed** (bar 0.05; D6 0.066), k = 4 0.115, k = 8 **0.197** (D6 0.220). Every other
target gate passes: R1 1.00 (T 0.913), R2 worst 0.914 (H3), R3 ESO137 0.25 and SARAO 1.00, R5
ESO137 **0.809** and SARAO 0.993, SARAO G-drop ≤ 0.014 / 0.032 / 0.064, core16, outer32, S1-S3.

Reading: doubling ESO137's dropout realisations moves k = 8 by 10 % and k = 1 hardly at all
(0.066 → 0.065). The k = 1 change is a floor of about 6 % that more of the same augmentation does
not lower: it sits in which cells cross τ when one antenna's baselines leave the per-observation
and block statistics, not in how often training saw a dropout. Next candidates for that gate: a
training loss that pairs each realisation with its k = 1 dropout (consistency), or block and scale
statistics that exclude the baseline's own antennas; both need code, both validation-only first.

**D8 (proposed 2026-11-23 07:40 SAST, before it runs; validation only, no training).** D2's k = 1
row on ESO137 (not its k = 8 row, which D4 followed) names the 2c and 2d blocks as the k = 1 lever:
0.084 → 0.051 with both frozen, 0.074 with the spectral planes frozen. A mechanism from the code:
at level 40 (`own` false) each block's z is an antenna's one-step median over its ~60 baselines,
less a smooth fit over channel blocks, divided by the row's pooled MAD. On a quiet observation that
MAD is mostly the medians' own jitter, so removing one of ~60 baselines from a median moves z by
about 1/√60 of its spread (≈ 0.13), whatever the training saw; this would explain D2's 85 % of
cells moved (median 0.18) and why D7's extra dropout realisations did not lower k = 1. D8 runs
`examples/f5_f6_probe.py` (extended: the 2c z and Q planes apart, every pooled plane at once,
every plane at once, the flipped cells' logit margin, the logit move, and change at τ from −5 to
−2 on the same logits) with D7's weights, level 40, τ −4.0, on ESO137 chunk 10 at k = 1 for G-drop's
three draws (20265301-03), 256 baselines, and on SARAO 1573212012 scan 111 at k = 1 (first draw)
for contrast. Question: does freezing the pooled planes take k = 1 below 0.04, and which group
carries it? If the blocks carry it, the next arm is a feature-side fix (a dead zone on the block
planes, or a noise-referenced floor on their scale) at a new level, levels 0-42 unchanged.
Run root `nash:~/rang-data/outputs/f7-d8-20261123/`.

**Seed spread (proposed 2026-11-23 07:40 SAST, before it runs; validation only).** Every arm so far
is training seed 2 alone. D7's recipe (its shards, unchanged) trained with seeds 1 and 3, τ by
`f6_tau.py` per seed, W4 off, screened by `examples/f7_gdrop_arms.py` on ESO137 chunk 10. Question:
how far do seeds spread on ESO137's k = 1 (D7 seed 2: 0.060 / 0.063 / 0.065)? Run root
`nash:~/rang-data/outputs/f7-seeds-20261123/`.

**D8 measured, ESO137 (2026-11-23 09:25 SAST, validation only; `nash:~/rang-data/outputs/f7-d8-20261123/`).**
D7's weights, level 40, τ −4.0, k = 1, 256 baselines. N5's change on those baselines, and with a
group frozen at its full-array values:

| Draw | flags | change | 2c z | 2d | 2c + 2d | F3 medians | spectral | 2c Q | all pooled |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 20265301 | 96,542 | 0.054 | 0.042 | 0.049 | 0.030 | 0.047 | 0.052 | 0.052 | 0.002 |
| 20265302 | 90,660 | 0.061 | 0.046 | 0.057 | 0.033 | 0.054 | 0.059 | 0.059 | 0.003 |
| 20265303 | 98,742 | 0.056 | 0.043 | 0.050 | 0.030 | 0.050 | 0.053 | 0.053 | 0.002 |

Flipped cells sit a median 0.09 logits from τ (90 % within 0.29); logits move a median 0.10. The
change does not depend on τ (0.053-0.057 for τ from −5 to −2 on the same logits), so this is not a
threshold-density effect. Reading: the per-baseline planes carry none of it; the pooled planes carry
all of it, 2c z and 2d most (2c + 2d frozen 0.030-0.033), F3's antenna and array medians the next
part (with them, 0.002-0.003). The mechanism of the D8 proposal fits: noise-level pooled statistics
moving by 1/√N.

**D9 (proposed 2026-11-23 09:30 SAST, before its code or run; validation only).** Feature-side fix
at new kernel levels, levels 0-42 unchanged (pinned hashes for 0, 20 and, on Linux, 40):
- **D9a, level 60:** level 40 with a dead zone on the pooled block planes (2c z, the four 2d
  planes) after the per-observation scale: v → sign(v) max(|v| − 2, 0), half-width 2 in
  per-observation units (≈ 2σ of a noise-level z), so a noise-level block statistic reaches the
  network as 0 and a real antenna anomaly passes, shifted by 2. Q, the spectral planes and the
  per-baseline planes unchanged.
- **D9b, level 70:** D9a plus the same dead zone on F3's antenna and array medians (planes 8-13).
- Half-width 2 is fixed here, before any number; it is not tuned on validation.
- Each arm: D7's recipe (F6's scans and seeds, balanced real batches, eight dropout realisations
  per ESO137 training chunk, seed 2, 30,000 steps) re-sharded at its level, τ by `f6_tau.py`, W4 off,
  then the screening rule below. An arm that passes the screen goes to the complete validation
  scorer. Run roots `nash:~/rang-data/outputs/f7-d9a-20261123/` and `f7-d9b-20261123/`.
- Questions: does k = 1 on ESO137 fall to ≤ 0.040 (screen), and what does the dead zone cost R1,
  R2 and R5 (a real antenna anomaly now enters 2 units lower)?

**Coordinator, 2026-11-23 09:45 SAST (relayed):** a targets-only stage may freeze and ship
(separate calibrator and target weights; calibrators recorded F, `learned:` refuses the calibrator
class). R3 stays as frozen until the owner rules (asked). Run P3 beside the target arms if
suitable data exists.

**P3 survey (2026-11-23 09:50 SAST; training data only, no held-out label read).** T's (rang port)
flag rate on every SARAO calibrator training scan of DL2's four training blocks (85 scans; 1735892129
left out as DL6's), over all cells of the label: 0.47-0.69, median about 0.58. *Correction
(10:00 SAST):* this all-cell rate does not separate LUNO-like scans: on LUNO, T over all cells is
0.45-0.61 too (F4's cache; MAIN_7 0.469), because W3's and the input flags dominate it; the 1.2 %
is T's added cells over eligible ones. What does hold: F6 already trains on all 85 SARAO scans, so
SARAO offers no new training data for P3. The low-flag-rate data that exists
is F4-era LUNO: the groups **MAIN_8, 9, 10, 11, 13, 15**, reserved since F4 for F5's post hoc arm
N5-ph and fetched on nash (`dl3-f5-20261119/d/outputs/f5-20261120-reserved-fetch/`, 5.3 GB,
receipt), never trained on, and not among F7's held-out sets (section 0: MAIN_0, 12, 14).
Using them as F7 calibrator training data takes them out of any later held-out use; recorded here.

**D10 (proposed 2026-11-23 09:55 SAST, before its code or run; validation only; calibrators).** P3 on
top of D1 (the best calibrator arm so far): F6's calibrator shards at level 20 (unchanged, linked)
plus four realisations of each of LUNO MAIN_8, 9, 10, 11, 13, 15 (T and A computed as F4 did:
`f3.t_flags`, AOFlagger 3.5.0 through `f5.a_flags`), so LUNO's real training shards go from 20 to
44. Balanced real batches (half LUNO, half SARAO), seed 2, 30,000 steps; τ by `f6_tau.py`; **W4 off**
(D1: W4 alone adds 10 × T on LUNO), fixed before the run. The complete calibrator validation scorer
on LUNO MAIN_7, 1573212012 scans 1, 3, 5 and the simulations. Question: does R3 on LUNO MAIN_7 fall
to ≤ 1.5 while SARAO keeps every gate (D1, N5 alone: 7.6 × T)? Run root
`nash:~/rang-data/outputs/f7-d10-20261123/`. A pass here does not freeze calibrators: G-drop on
LUNO (D1 0.056 at k = 1) and synthetic G-sub also failed in D1.

*D10 shards (2026-11-23 07:53 SAST, nash, 1,275 s, 7.6 GB peak):* 24 new LUNO shards, no audit stop;
223 calibrator training shards, 44 LUNO. T and A on the reserved groups over all cells, 0.446-0.467
and 0.549-0.570 (MAIN_7: 0.469, 0.550): the same kind of observation as MAIN_7.

**Training host (2026-11-23 10:15 SAST).** F7's arms train on nash's CPU, not glacier's GPU: a
shard copied nash → glacier ran at 0.7 MB/s (211 MB in 300 s, scp), so D10's calibrator shards
(154 GB) would take about 2.5 days and a D9 target arm's (46 GB) about 18 h, against 1.4-1.8 h per
CPU trainer on nash; the SARAO MSs live on nash only, so the shards cannot be built on glacier.
Agreed with the coordinator.

**Screening and freeze rules for F7's target arms (written 2026-11-23 07:40 SAST, before D8 and
every later arm).** (1) An arm is screened on ESO137 chunk 10 with `f7_gdrop_arms.py` (G-drop's
three draws at k = 1, 4, 8, N5 arm); it goes to the complete validation scorer only if its worst
draw is ≤ 0.040 at k = 1, ≤ 0.16 at k = 4 and ≤ 0.20 at k = 8 (margin for the held-out set's
seven ESO137 chunks, every draw of which must pass the 0.05 / 0.20 / 0.25 bars). (2) A candidate
freezes only after the complete scorer on validation passes every target gate, with τ (and κ or
W4's removal) chosen by `f6_tau.py`'s rule and the level fixed in this note before that read;
then three seeds are trained and selected as in F6, the cost gate is timed, and the held-out sets
are read once.

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

**Owner's ruling (2026-11-23, relayed by the coordinator):** R3 stays as frozen (option 1),
judged against Tricolour; the calibrator model passes only if the new LUNO training data (D10)
brings LUNO MAIN_7 to R3 ≤ 1.5, otherwise calibrators are F. Read here as: T is unchanged, F3-F7's
teacher (rang's run of the Tricolour-derived CARACal strategy, `f3flag.t_flags`; on SARAO the DL2
`rang` labels), and the bar 0.5 min(T, A) / T ≤ R3 ≤ 1.5 is unchanged. D10 is the calibrators'
last arm.
Confirmed by the coordinator the same day: "Tricolour" was shorthand for the frozen T; D10 is
scored against the frozen T, no gate change.

## 4. Data and splits (proposed, unchanged from F6 unless the owner widens scope)

Training: F6's (four SARAO blocks, LUNO and ESO137 training sets, simulations). Validation: F6's
(1573212012; LUNO MAIN_7; ESO137 chunk 10). Held out: section 0's list, read once after an F7
freeze. 1735892129 (1,024 channels) stays excluded unless P4 is in scope.

## 5. Coordinator

- Ready to run now (validation only, honest booking: 12 slots, 160 GB for D1's trainer by F6's
  measured peak of 153 GB with mapped shards): D1, D2.
- Needs the owner: scope among P1-P5, and the R3 question (section 3).
