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

## 2d. Gates and decision rule (committed 2026-11-20, before any F6 training step)

Committed and pushed before chain 3 trains (dl-plan: gates, bounds and the decision rule before
training). After training, the validation dry run of the complete scorer may change something
here only as a dated, labelled amendment; then the formal freeze; then the held-out reads.

| Gate | Test | Bar (source) |
| --- | --- | --- |
| **G-perm** | per held-out real set, live antennas relabelled by seeded permutations (seeds 20265201-03), antenna table alike | logits max abs difference ≤ 1e-4; flags differ on ≤ 1e-6 of eligible cells (F5 section 8) |
| **G-drop** | per held-out real set, 1, 4 or 8 live antennas removed at inference (seeds 20265301-03, `default_rng(seed + 100 k)`), remaining baselines' eligible cells | added-cell change ≤ **0.05 / 0.20 / 0.25** of the full-array added cells, k = 1 / 4 / 8, **each seed** (section 2a: T's change 0, F5's bars kept) |
| **G-sub** | core16 and outer32 synthetic sub-arrays of the held-out real sets; f4sim-t (odd antennas); **real sub-array blocks 1678312253 (29 antennas) and 1674958551 (32 outer antennas)**, R1's injections drawn on the sub-array | per sub-array, pooled over sets: R1 ≥ T_sub − 0.05; R3 ≤ 1.5 and ≥ R3's lower bound; R1 on the sub-array ≥ R1 at full array on the same sets − 0.05 (F5 section 8; real blocks per F5 Amendment 3) |
| **G-chan** | held-out real sets averaged by 4 channels (836 kHz; mean of four, flags OR), R1's injections after averaging | R1 ≥ T − 0.05, R3 ≤ 1.5: **reported**; sets the envelope's channel width (F5 section 8) |
| **G-obs** | **1579022459** (58 antennas, never seen in training) | R1 ≥ T − 0.05 and R3 within its bounds (F5 Amendment 3); **required for shipping**, not for the outcome |

Every bar is F5's frozen bar (section 2a's rule: none sized from F6). The SARAO held-out blocks
are read once, after the freeze, with C's runner (`TEACHERS=rang,aoflagger HELDOUT=1
teach_block.sh <cbid> 6 k/2`) for T and A; the network reads the full 4,096 channels in 2,048
channel windows (F5 Amendment 3). Fix 4's outer32 R3 and fix 5's R2 H2 per seed are measured on
validation before the freeze and reported; their bars are F5's.

**Seed.** Three seeds per class (1, 2, 3); the shipped seed is the median seed by validation loss
(F5 section 9; corrected in Amendment 2d-1, 2d first said "by validation R1"); R2 H2, G-drop and R1
are reported per seed on validation, and the held-out sets score the median seed.

**Decision rule (per class, first that applies; F5 section 11 otherwise unchanged).** Stop-C,
Stop-E and Stop-Z are F5's pre-training stages and are not re-run (F5's measurements stand; level
20 changes only the block planes' normalisation). **Stop-L**: section 2c's class-pooled audit
stops. **F**: any of R1, R1m, R2, R3, R4 (calibrators), R5, S1, S3, G-perm, G-drop, G-sub fails, or
C1 worse at either thread count. **H**: all quality gates pass, C1 not "beats" at 4 or at 1 thread.
**S**: all quality gates pass, C1 beats at 4 and 1 thread, C2 not worse, P holds. **S−**: S except
S2 or P. **Shipping** (weights in the wheel, `off` by default, section 3's ONNX form and licence):
S or S−, and G-obs passed; a class ships without the other. Cost: section 3 says whether F5's
timing stands or a timing run is needed (level 20 changes the work per cell); C1 and C2 are
scored on whichever applies.

**Amendment 2d-1 (2026-11-20 23:50 SAST, before any F6 training step and before any F6
network output; no held-out data read).** Fixes what 2d left to the scorer, for cost and for
consistency with training. (i) A SARAO set is one scan of C's stage-1 manifest, cut as in
training: channels 1024-3071 (1070-1498 MHz, LUNO's window) and the central 32 dumps; this replaces
2d's "full 4,096 channels in 2,048-channel windows", so the shipped envelope is the window trained
on. (ii) Which SARAO scans are scored, by rule, per block and class: every target scan, and for
calibrators the first scan of each distinct calibrator source in the manifest. Validation
1573212012: calibrator scans 1 (J1331+3030), 3 (J1939-6342), 5 (J2011-0644); targets 111, 113,
115. The held-out blocks get the same rule at the read; their source lists are in the manifest's
metadata, already listed for C's runner, not data. (iii) T is F5's T on the cut scan (as for LUNO
and ESO137; the injected cases need it); A is C's AOFlagger 2.13 `firstpass_QUV` label on the same
cells OR W3. (iv) Pooling: R1-R5, G-perm, G-drop, G-chan and synthetic G-sub (core16, outer32)
pool over all of the class's held-out real sets (F4/F5 sets and the three SARAO blocks). Real G-sub:
the scans of 1678312253 (29 antennas) and 1674958551 (32 outer antennas), each block pooled, R1 ≥
T − 0.05 and R3 within its bounds (the full-array comparison does not exist for these blocks and is
not applied). G-obs: 1579022459's scans pooled, the same bars. Code: `examples/f6_heldout.py`
(F5's scorer, SARAO loader, manifest split enforced) and `examples/f6_verdict.py`. (v) τ and κ
(`examples/f6_tau.py`): F5's rule, with the positives of every F6 validation shard (logits on the
shard's per-baseline planes) and the added-cells condition summed over the real validation scans
(LUNO MAIN_7 or ESO137 chunk 10, plus 1573212012's scored scans). (vi) The seed rule above is
F5's: median by validation loss.

**Amendment 2d-2 (2026-11-21 00:35 SAST, before any F6 training step).** The timing run moves
from "after the freeze" (section 3) to now: like F5's, it times the untrained network U5 (the
weights do not change the work, only level 20's one-step factorisation does), on F5's timing sets
(LUNO MAIN_1, ESO137 chunk 0: neither validation nor held out), so it reads no F6 result and
nothing it measures depends on training. Protocol unchanged: `examples/f6_timing.sh` is F5's
`f5_timing.sh` at `--level 20` (glacier, exclusive, 21:00-06:00, 5 alternating pairs against T, at 4
and 1 threads, N5 and N5W4 at κ 5); C1 and C2 are read from it with F5's bars.

**Amendment 2d-3 (2026-11-21 07:45 SAST; post hoc: written after the calibrator validation dry
run, before any held-out read; coordinator's instruction; cut-off 14:00 SAST).** The dry run
(median seed 2, τ −4.5, κ 3, N5W4) passes every gate on validation except R3 on LUNO MAIN_7
(16.9 × T; bar 1.5) and, through it, synthetic G-sub; SARAO 1573212012's R3 is 1.00. T flags 1.2 %
of LUNO's eligible cells and about 55 % of SARAO's, and the τ rule sums added cells over the real
validation sets, so LUNO's level is invisible to it. On LUNO N5 alone needs τ ≥ 0.3 and W4 adds
234k cells (> T's 209k) even at κ 16, so no single raw τ meets both sets with margin (measured,
seed 2). The fix tried is threshold-side only, written here before any variant is computed:

- *Constraints.* No T or A at inference (C1 stays valid); invariant to the antenna set (G-drop);
  no retraining (that would be F7); W4 off (it alone breaks LUNO at every κ, above). The bars are
  unchanged. The whole scorer is rerun on validation (every gate), not R3 alone.
- *Candidates* (the network's logits ℓ unchanged; per baseline b, over that baseline's eligible
  (time, channel) cells of the scan):
  - **K1, per-baseline location:** flag ℓ − median_b(ℓ) > τ′.
  - **K2, per-baseline robust z:** flag (ℓ − median_b(ℓ)) / (1.4826 MAD_b(ℓ)) > τ′.
  - **K3, per-scan location:** flag ℓ − median(ℓ) > τ′, the median over all eligible cells of the
    scan (on the shards: over the shard's baselines, recorded as an approximation).
  K1 and K2 depend only on the baseline's own logits, so they add no antenna-set dependence.
- *τ′ per candidate:* on F6's grid shifted to the candidate's scale (K1, K3: −2 to 12 in 0.5;
  K2: 0 to 12 in 0.25), the largest pooled recall on the validation shards' positives such that the
  added cells on **each** real validation set (not their sum) do not exceed T's.
- *Selection.* A candidate qualifies if, with its τ′, every gate passes on validation and R3 lies
  inside both bars with margin on every real validation set of both classes: R3 ≥ 1.1 × its lower
  bound and R3 ≤ 1.35. Among the qualifying candidates, the largest pooled R1, then K1 before K3
  before K2 (fewest statistics). None qualifies by 14:00: freeze as written (calibrators F on
  validation; LUNO MAIN_0, 12, 14 and the three SARAO blocks not read, kept for F7), targets as
  they stand.
- *Every variant tried* is recorded below with its τ′, per-set R3, R1, R5 and G-drop, pass or not.
- *Diagnostic, not acted on:* the share of the method's LUNO added cells that A also flags; R3's
  anchor T may be what is unstable across observations (a gate question for F7 and the owner).

**Amendment 2d-3, variants tried (2026-11-21 09:05 SAST; measured on validation, median seed 2;
`examples/f6_calib.py` on nash, `~/rang-data/outputs/dl3-f6-20261120/calib-<class>/`).** R3 per
real validation set at each candidate's τ′. The lower bar is 0.5 min(T, A) / T: 0.5 on MAIN_7,
0.45, 0.43 and 0.5 on 1573212012's calibrator scans 1, 3 and 5, 0.053 on ESO137 chunk 10, 0.5 on
the SARAO target scans. Margin: 1.1 × lower to 1.35.

| Class | Candidate | τ′ | shard recall | R3 per set | R3 margin |
| --- | --- | --- | --- | --- | --- |
| calibrator | K1 per-baseline location | 8.0 | 0.777 | MAIN_7 0.785; scans 1, 3, 5: 0.318, 0.438, 0.519 | fails (SARAO low) |
| calibrator | K2 per-baseline robust z | 4.5 | 0.302 | 0.786; 0.072, 0.121, 0.295 | fails |
| calibrator | K3 per-scan location | 8.0 | 0.824 | 0.838; 0.324, 0.431, 0.525 | fails |
| target | K1 | 6.5 | 0.953 | ESO137 chunk 10 0.050; scans 111, 113, 115: 0.927, 0.898, 0.969 | fails (ESO low) |
| target | K2 | 1.25 | 0.926 | 0.624; 0.877, 0.941, 0.967 | passes |
| target | K3 | 6.5 | 0.982 | 0.196; 0.917, 0.911, 0.988 | passes |

No candidate qualifies: the rule asks for the margin in both classes, and no calibrator candidate
has it (LUNO's "added ≤ T" pins τ′ and leaves SARAO under its lower bar). By the rule F6 freezes
as written. K2 and K3 for targets are scored in full on validation as recorded, non-selectable
variants for F7.

*Diagnostic (not acted on).* LUNO MAIN_7, frozen τ −4.5: N5 adds 2,727,768 cells; A also flags
792,710 of them (29 %), T 164,754 (6 %). On the SARAO calibrator scans the overlap is 69-92 % with
each teacher. So about 1.8M of N5's LUNO cells are flagged by neither teacher: the network carries
SARAO's flag level (T flags about 55 % there, 1.2 % on LUNO) into LUNO. R3's anchor T is not the
main problem on LUNO; a per-observation flag-rate gap is, and threshold-side calibration does not
remove it.

**Amendment 2d-4 (2026-11-21 09:30 SAST; coordinator; written and committed before the
frozen-method target dry run's verdict is read).** The calibrator class freezes as written:
**F on validation** (R3 on LUNO MAIN_7, synthetic G-sub; 2d-3 found no qualifying calibration).
LUNO MAIN_0, 12, 14 and the calibrator scans of the three SARAO held-out blocks are not read; they
stay whole for F7. The target class's held-out read depends on its validation dry run (frozen
method: median seed, τ and κ from `f6_tau.py`), by this rule fixed before the result:

- *The dry run passes every validation gate* (R1, R1m, R2, R3 on ESO137 chunk 10 and on the SARAO
  validation block, R5, G-perm, G-drop, synthetic G-sub, S1, S3; `examples/f6_verdict.py`'s failed
  list empty apart from S2 and cost; S2 is exempt because in F5's frozen decision rule, section 11, which F6 keeps, S2 never decides F or shipping: a failed S2 only turns S into S−, and S2 is measured again on f4sim-t at the held-out read; cost is measured on Sunday): read the **target scans** of 1678312253 (36, 40, 44),
  1674958551 (31, 35, 39) and 1579022459 (115, 117, 121) once, for real G-sub and G-obs, with C's
  teachers (`dl2_teach.py --heldout-read`, T = rang, A = AOFlagger 2.13 `firstpass_QUV`), their
  calibrator scans unread; then ESO137 chunks 1, 3, 5, 7, 9, 15, 17 and f4sim-t.
- *It fails any gate:* the three blocks stay whole for F7; only ESO137 chunks 1, 3, 5, 7, 9, 15,
  17 and f4sim-t are read, to record the outcome.

Reason: the owner's "keep the SARAO blocks" saved them for an F6 candidate that could pass, and a
target pass is the only route to shipped weights (DL6) by Monday. Spending them on an outcome
validation has already decided would waste them. Both branches are fixed before the result.

## 2c. Label audit for F6 (post hoc: fixed 2026-11-20 after the validation label shares were seen; before training; no network involved)

*Labelled post hoc (coordinator, 2026-11-20).* The bars below were set after the validation
shares in this section were seen. They are a data gate, not a performance bound, and are derived
from F5's frozen audit (40 % ignored per realisation, 0.1 % injected positives, F4's target bars),
loosened to a class-pooled 45 % so that one RFI-heavy scan cannot stop a class; the 0.1 % injected
floor is F5's, unchanged. They are not tuned to the shares: the class-pooled shares seen (36.6 %,
31.8 %) pass F5's own 40 % as well; only one scan's 41.3 % would have stopped it.


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
- Cost: F6 changes the work per cell (level 20's one-step factorisation replaces F5's polish of
  the block planes), so **F5's timing does not stand: one exclusive timing run on glacier** (F5's
  `f5_timing.sh` protocol, after the freeze, before the decision; Sunday 2026-11-22 at the latest).
- Training host: nash's CPU if its wall is within about 2 × glacier's GPU (F5's trainer measured
  on both), else glacier's GPU through `gpu_run`. *Measured 2026-11-20:* F5's trainer, 3,000 steps on
  F5's calibrator shards, nash CPU at 8 threads: 300 s (10 steps/s), 25.6 GB; glacier's RTX 4070
  Ti: 44 s (68 steps/s). Per step the CPU is 6.8 × slower, but the GPU route first needs F6's
  training shards (about 150 GB) copied to glacier at about 5 MB/s, 5-8 h, while three CPU seeds run
  side by side in about 1 h on nash. **F6 trains on nash's CPU** (three processes of 8 threads,
  each seed bit-reproducible on its own; CPU and GPU weights are different draws of the same
  procedure, as F4 recorded).
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
