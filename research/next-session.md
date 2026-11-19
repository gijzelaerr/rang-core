# Brief for the next coordinator session: start v0.4.0 (written 2026-11-19)

v0.3.0 is released (2026-11-19). v0.4.0 is deep learning, with Landman Bester's flagger first. The
plan, the stage table, the swap contract, the gates and all eight owner decisions are in
[dl-plan.md](dl-plan.md); read it first, then `AGENTS.md`, then this brief. The brief of 2026-11-13
that stood here is in the git history (`git show 5a5edb50:research/next-session.md`).

## State on disk, 2026-11-19

- `main` is pushed with the plan and decisions (`7f037581` and the commit that adds this brief); full
  check PASS, CI green on the earlier pushes of the day.
- Nothing of v0.4.0 is built, fetched, trained or measured.
- GitHub: milestone v0.4.0 holds #37-#46 (the plan's tasks), #1 (Landman), #4 (multi-node executor),
  #24 (CLEAN against regularised and learned imagers), #7 and #34. There is no v0.3.1; its roadmap
  table is kept only as the resume state of stopped runs, none scheduled.
- Issue #1: a status update was posted on 2026-11-19 (comment 7002083361), with no questions. F5
  freezes without waiting for a reply.
- nash: `~/rang-data/sarao-links-dl.txt` (mode 600) holds nine per-block archive links with read-only
  tokens issued 2026-11-19, valid about 60 days (to about 2027-01-18). Never print the file.
  **Check before starting anything there:** the 0.3.0 session reported a CARACal E3-A timed pass
  still running and holding nash exclusive (started 07:37 SAST, 2026-11-19), and kept 1.8 TB
  (`e2a-kzero-20261117`) and 201 GB (`e2n-followup-20261118`) of outputs. Stopping that pass or
  deleting those outputs is an owner decision; ask once, then work around it.
- glacier: no PyTorch environment yet; the GPU is booked through `~/.gpu/gpu_run.py` (owner `rang`).
- No unmerged branch is needed: F4's code (`core/src/f4flag.rs`, `python/rang/f4flag.py`) and note
  ([f4-flagger.md](f4-flagger.md)), F5's draft ([f5-flagger.md](f5-flagger.md)) and the spool executor
  (`python/rang/core_spool.py`, `data.executor: spool`) are on main. F4's trained calibrator weights and
  its unread held-out sets are located from f4-flagger.md (trained on nash, 2026-11-17).

## Standing rules for v0.4.0 (owner, 2026-11-19)

- **Hosts.** Everything CPU-heavy or data-heavy runs on nash: fetches, conversions, the teacher
  tools, feature extraction, label generation, simulation, CPU evaluation. Only GPU work runs on
  glacier: training and GPU inference. glacier's data disk filled once; copy to it only the training
  shards a GPU run needs, and remove them after.
- **GPU hours.** Training may run at any hour, booked through `gpu-run`. Timing and exclusive runs
  on glacier start at 21:00 or later. Budget before a go/no-go: 24 GPU hours per pilot, 48 for F5,
  three seeds included; one extension, on the owner's word.
- **Resumable in small batches** (owner: the PC may crash, reboot or be taken over by his own
  work). Training checkpoints at least every 15 minutes and at every epoch end, and resumes from the
  last checkpoint with the same result as an uninterrupted run where the framework allows (seeded
  data order, optimiser state saved); otherwise the difference is stated. Evaluation, label
  generation and teacher runs are split into shards (per scan, per block, per sky), each with a
  done-marker and a checksum; a rerun skips finished shards. No job loses more than about 15 minutes.
- **Framework.** PyTorch for every new learned stage, as a training-only extra; weights as ONNX; a
  pure-Rust runtime chosen by measurement in #38. Existing JAX code is frozen and not ported.
- **Modes.** Everything `off` by default; propose is the documented default when learning is on;
  replace only for products labelled approximate.
- **Claims.** Each task follows `docs/agents/propose-and-measure.md`: note frozen before code,
  oracle, tolerance, held-out sets read once, nulls recorded. No antenna-indexed inputs; gates
  G-sub, G-drop, G-perm, G-chan, G-obs frozen before training.
- **Landman.** Text for him is terse and numbers first, and the owner sees it before it is posted.
  No questions to him on architecture or on the pilots beyond flagging.

## Work packages

Wave 1 starts at once, four sessions in parallel, each in its own worktree
(`~/Worktrees/rang/<branch>`), each with `outputs/status/<task>.md` and a 15-line hand-back.

| Session | Issue | Branch | Host | First steps | Blocks |
| --- | --- | --- | --- | --- | --- |
| A | #37 DL0 | `dl0-profile` | agent work; one profiled run on nash | verify sections 3 and 6's candidates (weights, licences, MeerKAT evidence; R2D2's inputs); the selfcal split on E2-A and E2-N from receipts or one profiled run; the solver's present start | the order of #41-#44 |
| B | #38 DL1 | `dl1-contract` | Windows checkout and CI; no heavy slots | `learned:` key on every stage, weights header, envelope refusal, receipts; export F3's network from PyTorch to ONNX; compare tract, burn, candle and the hand-written kernel | #40's shipping form (not its training) |
| C | #39 DL2 | `dl2-data` | nash | publication terms of the nine proposals; dump time and scan list of each block from its metadata, before any visibility; then fetch subsets (all calibrator scans, middle three target scans) with every job at `nice -n 19 ionice -c3`; manifests with SHA-256; teacher runners; the spool executor (#4, `data.executor: spool`) for teacher runs | G-sub and G-obs data for #40-#42 |
| D | #40 DL3, **priority** | `dl3-f5` | nash for features, labels, injections and CPU scoring; glacier for training | rewrite [f5-flagger.md](f5-flagger.md) section 2 around F4's cost-gate stop; add G-sub, G-drop, G-perm; freeze; port the F3/F4 network and trainer to PyTorch (about 400 lines) with a parity test against the Rust inference; train (48 GPU hours); score on the held-out sets F4 left unread; one exclusive timing run after 21:00 | the first result of v0.4.0 |

D does not wait for B or C: it trains on the data on hand (LUNO, ESO137, F-SIM) as F2-F4 did, ships
as `f5flag.rs` if #38 is not ready, and moves under the contract afterwards, bit-identical. C's
29-antenna and outer-array blocks join F5 as G-sub data if they are fetched before F5's freeze;
otherwise F5 freezes with simulated sub-arrays and the real blocks are a dated amendment.

Wave 2 starts when A reports (the order may change with its selfcal split):

| Issue | Needs | Host |
| --- | --- | --- |
| #42 DL4b step 0 (ASTRODECONV2019, if downloadable) and step 1 (#24's comparison) | A | nash; glacier for training |
| #41 DL4a gain warm start | A, C | nash; glacier |
| #44 DL4s screenings, #43 DL4c | A; spare slots | nash; glacier |
| #45 DL5 combined selfcal | #41 or #42 passed | nash; glacier |
| #46 DL6 retrain procedure | one passed stage, B | nash; glacier |

Only one training job holds glacier's GPU at a time; queue through `gpu-run`. nash takes many CPU
jobs side by side: book honest slots and memory on its heavy lock and compare the lock's bookings
with real CPU use on every wake.

## Coordinator loop

- One session per package; merge on a full check (`python tools/check_all.py`), push only inside
  `if rc == 0`, read CI after every push and fix a red run before moving on.
- After each merge: a status line on the package's issue, a paragraph in `STATE.md`, a row per tool
  run in `tool-timings.md` with the host named.
- Close an issue only with its recorded outcome (shipped behind the option, or null).
- Owner decisions go to the owner once, with a recommendation; work that does not depend on the
  answer continues.

## Open points to settle early

- nash's state (the running E3-A pass, the kept outputs): owner.
- Whether ASTRODECONV2019 still downloads from archive.kernsuite.info (not confirmed 2026-11-19).
- Publication terms of the nine blocks' proposals (session C); a block whose terms do not allow
  publishing weights is replaced by the next in the frozen rule's order, with a dated note.
- The tokens expire about 2027-01-18: fetch well before.
