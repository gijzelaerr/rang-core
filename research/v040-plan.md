# v0.4.0: plan to the milestone (coordinator, 2026-11-20)

Owner, 2026-11-20: "make a better plan on how to reach our 0.4.0 milestones as quick as possible.
you have priority over all GPU activities." Releases ship with known limitations rather than wait
(standing practice since 0.2.0). This plan replaces the wave tables of
[next-session.md](next-session.md) for scheduling; [dl-plan.md](dl-plan.md) still holds the method.

## The critical path in one line

v0.4.0's done-when needs DL6 (#46) to retrain **one stage that passed its gates**. Nothing has
passed: F5 (#40) is predicted F on validation (R5 0.338 against 0.80; G-drop above its bounds), and
#42 step 0 cannot decide cost by design. So the path is **F6 (a flagger that passes) → DL6 retrains
it for a held-out configuration**. Everything else runs beside it.

**Fork, default dated.** If F6 has not passed its frozen gates by **Monday 2026-11-23, 21:00 SAST**,
v0.4.0 is released on **Tuesday 2026-11-24** with DL6 recorded as a known limitation ("no stage
passed; the procedure is written and dry-run on F5's pipeline"), and F6/DL6 move to 0.4.1.

## Issue dispositions

| Issue | Disposition | Owner of the work | Done |
| --- | --- | --- | --- |
| #37 DL0 | close: merged `7cd42b26`, order #42, #43, #44, #41 | – | now |
| #38 DL1 | close after tonight's final timings land | B | 2026-11-20 night |
| #39 DL2 | close with outcome: stage-1 manifests and labels; stage-2 and stage-7 runners deferred to the pilot that needs them (route recorded) | C | 2026-11-20 |
| #40 DL3 F5 | score as frozen today, record F honestly; SARAO blocks unread (owner) | D | 2026-11-20 |
| #1 Landman | F5 result, text shown to the owner first | D drafts | 2026-11-20/21 |
| **F6** (new, under #40) | fixes from F5's validation: strong-consensus or hybrid positives; block planes robust to the antenna set; C's six SARAO training blocks; held-out: the three SARAO blocks, LUNO MAIN_0/12/14 | D | freeze 11-21, score 11-22 |
| #46 DL6 | procedure drafted and dry-run on F5's pipeline now; run on F6 once it passes; held-out configuration: a sub-array class not in training (or 1k channels) | B | draft 11-21, run 11-23 |
| #41 DL4a | one-day screening (classical warm starts first, dl0-profile section 3), outcome recorded | C after teachers | 11-21 |
| #42 DL4b | step 0 capped at 6 GPU h (anchor, expected null); step 1 a bounded #24 comparison on existing MeerKAT truth skies at E2 scale, proposed to the owner with its GPU hours | E | step 0 11-21; step 1 decision 11-21 |
| #24 | joins #42 step 1 | E | with #42 |
| #43 DL4c | finish the mask pilot already running (spare slots) | A | 11-22 |
| #44 DL4s | **propose v0.5.0** (spare-slot work, not in done-when) | – | – |
| #45 DL5 | **propose v0.5.0**: triggered only if #41 or #42 passes; neither is expected to | – | – |
| #47 WSClean 3.8 | arm T, one exclusive night (about 9.5 h, no GPU training), then merge | coordinator | night of 11-21 |
| #4 multi-node | **propose v0.5.0**: the spool executor serves DL2; Slurm/PBS has no test cluster here | – | – |
| #7 E2-N | **propose v0.5.0**: the follow-up's kept outputs are gone; a rerun from the start | – | – |
| #34 | **propose v0.5.0** with #32: the solve fix is merged (`281a1a79`); GeMClean's 9.3 GiB peak remains | – | – |

## Nights (exclusive, glacier, from 21:00)

| Night | Run | Then |
| --- | --- | --- |
| Fri 11-20 (day, owner: "feel free to run it as soon as you want") | F5 timing (D, done 12:39: C1 0.365-0.409, gate passes), DL1 final runtime timing (B, done) | – |
| Fri 11-20 night | #47 arm T (about 9.5 h, armed, waits for 21:00) | – |
| Sat 11-21 | F6 cost gate (only if F6 changes the work per cell; F5's cost does not depend on the weights, so a retrain alone reuses it) | – |
| Sun 11-22, Mon 11-23 | spare: DL6 if its cost differs, or a rerun | release prep |

Daytime: GPU training at rang's priority; CPU work on nash, and on glacier's CPU when nash is fully
booked (small-data compute only, 4 threads left for the owner). glacier is clear of every job from
20:50 until the night's exclusive run ends.

## Rules learned this week

- **Freeze only after the complete scorer has run on validation**, every gate and stop bar included
  (F5 hit a stop bar borrowed from F4's other class, and G-drop bounds sized with F4's network).
- **Chains on nash drive themselves** (`setsid`, done-markers, the next stage started by the
  previous one), never by a watcher on glacier: a glacier freeze then costs nothing on nash.
- **Sessions end their turns while jobs run**, or the coordinator's messages queue behind them.
- glacier lost power twice on 2026-11-19 (owner, 2026-11-20; not the GPU, although its driver
  also logs timeouts every few hours); every job resumes from a checkpoint after a reboot.

## Owner answers, 2026-11-20

- Fork and dispositions: "sounds good for now"; #4, #7, #34, #44, #45 moved to v0.5.0 the same day.
- Weights trained on SARAO archive data ship under CC BY 4.0, with SARAO's acknowledgement in the
  weights header and the docs: "yeah lets do that license, i think it is fine".
- glacier: "the computer is all yours until monday" (exclusive and timing runs at any hour until
  2026-11-23; the other GPU user's 06:05-06:45 slot stays).
- No 0.3.1: "people should just use master for the latest and greatest"; the watch ships in 0.4.0.

## Owner questions as first asked (defaults, kept for the record)

1. The fork above: default as written.
2. #4, #7, #34, #44, #45 to v0.5.0: default yes.
3. Licence requests upstream (R2D2-RI, AIRI shelf, rcGAN, astroNNomy): texts to the owner first.
4. Text for Landman on #1: to the owner first.
