# Branch and worktree triage, 2026-11-13

Taken against `origin/main` = 2a02470. Read-only except the removals listed
below; no merges, no pushes to main, no remote branch deleted.

## Removed (merged into origin/main, clean, nothing unpushed, only build/cache ignored files)

Worktrees (all detached unless noted) and their local branches:
`brave-bassi-eeb218`, `dreamy-shtern-50fb77`, `dreamy-wilson-2ec3c9`,
`elegant-cray-310e3f`, `gallant-cannon-d08450`, `kind-villani-179c45`,
`strange-euclid-db766d`, `vigorous-bouman-fa3a03`, `focused-snyder-580a11`,
`e5-final-early-b94bc5` (branches `claude/<same>`), plus
`~/Worktrees/rang/{e5-decisions,fp-e2-averaging,fp-e2-freqavg}` (branches deleted).
Worktrees went from 35 to 24 (before adding this one).

## Kept although merged and clean (ignored, untracked data inside)

| Worktree | Why kept |
| --- | --- |
| `ms-lock-windows-698bb6` | `outputs/` 77 MB, 152 files (luno-solve work.ms) |
| `u5-upstream-b8efe4` | `outputs/` 100 files (u5 upstream fetches) |
| `sliced-read` | `outputs/` 279 files |
| `v2-front-door` | `outputs/` docs-html build (probably disposable; not inspected beyond the file list) |
| `musing-dewdney-667f5d`, `mystifying-haslett-f2e43c`, `mystifying-mclaren-5c64e0`, `quizzical-murdock-d8b3a7`, `silly-cannon-dddff1`, `youthful-rubin-3d215e` | each holds an untracked `outputs/status/<task>.md` not present in the main checkout (v3-intro-outline, v3b-intro-notebooks, v6-vlbi, v4-digest, v7-lofar, check-speed); copy it to main `outputs/status/` first, then remove |
| `df-flag-rule-0deecc`, `v8-open-casa-a871c6`, `v8a-listobs-1c691e`, `v8b-flagdata-8cce7c` | created today / linked sessions working |

## Active or paused, unmerged (not touched)

| Branch | Ahead / behind main | State |
| --- | --- | --- |
| `fp-e2-acceptance` | 4 / 94 | E2 paused on owner's order, resume state in note section 8 |
| `e3-caracal` | 20 / 120 | E3 stopped by owner; resume state committed |
| `fp-f4-flagger` | 13 / 153 | F4 resume state after Stages 1-3 |
| `docs-polish` | 2 / 0 | live; 4 modified + 6 untracked files in worktree |
| `claude/chi-offset-80cb6a` | 3 / 30 | paused; 2 modified + 1 untracked |
| `claude/speedup-tools-73baec` | 7 / 8 | stopped on owner's order; 3 modified + 2 untracked |
| `claude/feed-poltype-read-ea1d2d` | 7 / 45 | resume state committed |
| `claude/eloquent-lovelace-8bb556` | 3 / 156 | V5 resume state; very stale base |
| `claude/v8a-listobs-1c691e` | 15 / 35 | V8a; its work is the base of `v8b-flagdata` (merge commit), so drop after V8b merges |
| `claude/v8b-flagdata-8cce7c` | 16 / 0 | V8b, up to date with main |

Not a worktree of ours: `~/Build/tmp/20261113-rang-mergetrial` (detached, 24 commits
ahead, on no remote, created today). Whoever owns it should push or delete it.

## The branches named as "finished"

All five are already merged into origin/main, so nothing is unmerged.

| Branch | What | Superseded | Recommendation |
| --- | --- | --- | --- |
| `gemclean-heldout` (remote only) | GeMClean held-out stop-rule test | contained in main | drop remote when convenient |
| `gram-solver` (remote only) | Gram solver | contained in main | drop remote |
| `stop-rule-theorem` (remote only) | stop-rule theorem | contained in main | drop remote |
| `v2-front-door` | front door docs | contained in main | worktree kept for `outputs/`; then drop |
| `df-flag-rule` (`claude/df-flag-rule-0deecc`) | upstream-follow, at main tip | contained | drop once its session ends |

Other merged local branches that can go (not removed: worktree in use or no worktree):
`e5-prereview`, `sliced-read` (worktree has data), plus the `claude/*` branches of the
kept worktrees above. 8 `origin/claude/*` remote branches exist; the unmerged ones are
the paused work above.

## For the coordinator

1. Copy the six untracked status files above into main `outputs/status/`, then remove those six worktrees.
2. Decide on `ms-lock-windows`, `u5-upstream`, `sliced-read` outputs (archive to `D:\rang` or drop).
3. Merge order: `v8b-flagdata` (includes V8a) first, then drop `v8a-listobs`; `docs-polish` is 2 ahead, 0 behind.
4. `eloquent-lovelace`, `fp-f4-flagger`, `e3-caracal` are 120-156 commits behind main: rebase or merge main before resuming.
