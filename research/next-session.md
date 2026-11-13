# Brief for the next coordinator session (written 2026-11-13)

The owner closed every session on 2026-11-13 and starts over. This is the brief for the new
coordinator. The resume state of each piece of work is in [handoff-2026-11-13.md](handoff-2026-11-13.md);
the finish line and tasks in [finish-plan.md](finish-plan.md); the direction in [vision.md](vision.md);
the rules in `AGENTS.md`.

## State on disk

- `main` is pushed at 7289593 (full check PASS: 1,248 pytest, Rust 270/276, gain hashes), with the WSL mirror synced.
- Nothing is running and no heavy_lock ticket is live. Stale ticket files of dead pids may sit in
  `D:\rang\locks\heavy-queue`.
- Every unmerged branch is pushed to origin with nothing left unpushed: `fp-e2-acceptance`, `e3-caracal`,
  `fp-f4-flagger`, `claude/eloquent-lovelace-8bb556` (V5), `claude/v8a-listobs-1c691e`,
  `claude/chi-offset-80cb6a`, `claude/speedup-tools-73baec`, `claude/feed-poltype-read-ea1d2d`.
- 34 worktrees exist (`git worktree list`), and none has uncommitted tracked changes. Those whose branches
  are merged into main can be removed (CLAUDE.md). Check each for untracked outputs first, and never use
  `--force` on one that holds data.

## Order of work

1. **Merge `claude/speedup-tools-73baec` first.**
   - Read CI run 43368739920 and run its `tools/check_all.py --quick`, then the full check.
   - Benchmark a cold worktree build with and without sccache, in one exclusive hold.
   - Only then set `RUSTC_WRAPPER` and `SCCACHE_DIR=D:\rang\cache\sccache` for the user.
   - From then on, sessions run `--quick`, push their branch and read CI. The coordinator runs one full
     check per merge batch.
2. **Merge the two small ready branches** after one full check: `claude/feed-poltype-read-ea1d2d` and
   `claude/v8a-listobs-1c691e`.
3. **The critical path, one session:**
   - E2-B: the amended arm, then the transfer and leakage rows, then the archive (`research/e2-acceptance.md`
     section 8).
   - Then E2-A.
   - Then E3-B timed on the kept `e2b.ms`, then E3-A (`e3-caracal`, note 10.12).
   - Queue critical jobs with `--priority critical` once merged. Keep `e2b.ms` until E3-B's timed pass has
     run on it.
4. **Alongside, on shared slots:** chi-offset, section 7 steps 1-6. It must settle the 3C 286 absolute-χ
   question before the E2/E3 report says anything about polarisation angle. The leading hypothesis is that
   LUNO's receptor angle is about 0°, not −90°. A fix (`feed_angle_rotation` null) is an owner decision.
5. **After E3:** the E3 report, E5's delta review on `research/e5-final.md` (E5-10, the CHANGELOG, waits
   for E6), then E6.
6. **Off the critical path, after E2/E3's timed passes:**
   - V5's timed s1, p16 and p1 runs, each one exclusive hold (`research/v5-obit.md` section 10);
   - F4's parity runs, then the GPU training audit;
   - V8's next pieces after v0.2.0 (`tfcrop`, then the fixed-rule `flagdata` modes).

## How to coordinate (lessons from 2026-11-12/13)

- **Full check on Windows:** run it from PowerShell with full paths:
  `$env:RANG_ARCHIVE_OUTPUTS='\\wsl.localhost\Ubuntu\home\gijsm\Github\rang\outputs'; .venv\Scripts\python tools\heavy_lock.py run --slots 8 --mem 12 --poll 2 -- C:\Users\gijsm\Github\rang\.venv\Scripts\python.exe -m rang.check`.
  Git Bash mangles the `\\wsl.localhost` path. The speedup wrapper fixes that once it is merged.
- **Exclusive holds:** an exclusive ticket drains every shared job, and FIFO order then blocks everything
  behind it. Batch all timing into one exclusive hold per plan, and never leave a non-critical exclusive
  ticket queued ahead of critical work.
- **Deadlock:** `rang.check`'s own lock (`~/.rang-checkall-v2.lock`) inside heavy_lock slots held 16 slots
  idle for hours. The fix is `RANG_CHECKALL_LOCKED=1` under the heavy lock, set by the wrapper. Pass
  `pytest --timeout` to catch hung tests. The coordinator may stop hung processes: `PowerShell(Stop-Process *)`
  is allowed in user settings.
- **Merge conflicts:** `research/tool-timings.md` and `CHANGELOG.md` conflict on almost every merge. Both
  sides are additions, so keep both.
- **Briefs:** give each session its files, rules and what "done" means, plus "shared slots only" and
  "don't merge". The coordinator merges with `--no-ff`, runs the full check, pushes normally and syncs the
  mirror: `wsl -e bash -c "cd ~/Github/rang && git fetch -q origin && git checkout -q --detach origin/main"`.
- **Commits:** the owner identity, no trailers, never force-push.

## Owner decisions and items

- **Standing:** no pre-releases. No contributions to CASA or NRAO: CASA is only an oracle, and V8 builds an
  open replacement. Other upstreams (casacore, WSClean, RATT and others) are reported. glab is signed in to
  git.astron.nl and gitlab.com, and gh to GitHub.
- **Open:**
  - send the Obit note to Richard Armstrong;
  - set the `pypi` environment protection before E6;
  - decide V6 and P1 (P1 needs a SARAO token);
  - decide the chi-offset fix if H3 holds.
- **Upstream to follow:** WSClean !1068 and radler !238 (when released, rerun the G2, G7 and G9 oracle cases
  and switch `w_limits` and `theoretic_beam` to v). AOFlagger #44-46 have had no answer yet.

## A starting prompt for the owner to paste

> You are the ra-ng coordinator. Read `research/next-session.md`, `research/handoff-2026-11-13.md`,
> `research/STATE.md` and `AGENTS.md`. Then carry out "Order of work" from step 1. Use sessions for
> the work, merge after full checks and push main. Keep going until v0.2.0 is ready for the owner to tag.
