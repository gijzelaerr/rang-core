# PC1: the L1 and L2 preconditions on main

Task PC1 of [big-plan.md](big-plan.md). P11 ([p11-extract.md](p11-extract.md))
reported two pre-existing failures at its base `2da566c`: the L1 precondition
(`examples/precondition_luno_array.py`, `rang-core campaign-array
precondition`) ends `all_equal: false`, `pass: false`, and the L2
precondition (`examples/precondition_luno_1830.py`, `rang-core campaign-1830
precondition`) raises a broadcast `ValueError` in
`core_campaign_array.solve_flags_lean`. This note reproduces both, bisects
them, names the causes and records the fix. Status: **implemented and
measured**; both preconditions pass again with every archived number
unchanged.

Host: the WSL2 workstation of [STATE.md](STATE.md), Python 3.14, Rust 1.93,
`OPENBLAS_NUM_THREADS=1 RAYON_NUM_THREADS=4`. Worktree
`~/Worktrees/rang/pc1-preconditions` (branch `pc1-preconditions` from main
`f6d6a96`); bisect checkouts under `~/Build/tmp/20261030-pc1/<sha>`, each
with its own venv (deleted afterwards). All outputs are
`outputs/pc1-20261030-NN-*` with a `.log` beside each.

## Summary

| Failure | First bad commit (first parent of main) | Cause | Fix |
| --- | --- | --- | --- |
| L1 precondition `all_equal: false` | `cbf9003` (merge of L1) | Merge interaction: L1's branch (precondition passed at `4584936`) never contained P2 (`125d42a`, rustfft gridder), which changed the image bits within 2e-15 and was already on main. L1's precondition compares image hashes, peak and residual RMS **exactly** | `core_campaign_array.precondition` gates part 2 on L2's tolerant comparison (`compare_replay_tolerant`), keeps the exact comparison in the output |
| L2 precondition `ValueError` | `29d67b4` (merge of P5) | Merge interaction: P5 (`ee1b02d`) stores a solve's additions as sorted cell **indices** (`np.flatnonzero`) instead of a dense `(row, chan)` mask and converted every call site in its base; L2's driver merged at `56d5680` 11 minutes before P5 and was not in P5's base. `core_campaign_1830.run` passed the stored indices to `solve_arm` (amendment-1 base) and to `derived_row_flags` / the additions summaries as if they were the mask | `core_campaign_1830.run` expands them with `array.additions_dense(state, ...)` at both sites, as L1's driver does |

Neither is a missing input: `outputs/core-k-20261030-01/result.json` and
`candidates.json` (the replay reference) and the local LUNO tiles are present
and match the archive (K's result hash equals
`results/core-k-luno-campaign.json` in every run). Neither is in P7, P9, L5
or P1.

## 1. Reproduction at `f6d6a96`

**L1** (`outputs/pc1-20261030-01-l1`, 9.3 s, 349 MB): parts 1 (K's
precondition, χ² 0.26823507037914956 equal to the archive) and 3 (gridder
groups) pass; part 2 (the four-station replay of K run `-01`) fails. The
false leaves of `replay` are image products only:

- `arms/<arm>/image_dirty_sha256` and `image_psf_sha256` for all six arms;
- `image_residual_rms` for `original`, `tricolour-firstpass`, `tv-policy`,
  `tricolour-firstpass+tv`; `image_peak_jy_per_beam` for `original`,
  `tv-policy`, `tv-unguided-best`;
- `hypotheses/0` (the residual-RMS ratio of the first hypothesis, an image
  product: 0.9999581520151 against 0.9999581520151007).

Every other field is equal: shape, split counts, every arm's
`additions_sha256`, `gains_sha256`, losses, TV, fixed-support TV, final flag
fraction and additions, all 20 candidates, the Tricolour counts,
`hypotheses/1` and `/2`. L2's `compare_replay_tolerant` (image hashes
reported, peak and residual RMS and the residual-RMS ratio within 1e-9
relative) on the same replay is `all_equal: true`; the largest relative
image difference is 1.2e-15. This is P5's section 1.4 finding exactly
([p5-memory.md](p5-memory.md)).

**L2** (`outputs/pc1-20261030-01-l2`, 6.2 s):

```
File "python/rangtoy/core_campaign_1830.py", line 1145, in precondition
    replay = run(
File "python/rangtoy/core_campaign_1830.py", line 790, in run
    base_m = solve_arm(
        state_m, fp["added"], "tricolour-firstpass", scale=scale0, features=True
    )
File "python/rangtoy/core_campaign_array.py", line 692, in solve_arm
    flags, rows = solve_flags_lean(state, added)
File "python/rangtoy/core_campaign_array.py", line 541, in solve_flags_lean
    np.logical_or(f, (~train[s] | added[s])[..., None], out=f)
ValueError: operands could not be broadcast together with shapes (192,2048) (128,)
```

`fp["added"]` is the first-pass arm's 128 addition indices; `np.asarray(...,
bool)` turned them into a length-128 boolean vector, which the row block of
192 rows cannot broadcast against. Had it got past that line,
`derived_row_flags(..., solve["added"])` in the image loop would have failed
the same way (`np.broadcast_to` of an `(n, 1)` index vector to the cube).

## 2. Bisection

Each candidate commit was checked out with `git worktree add --detach` under
`~/Build/tmp/20261030-pc1/<sha>` with its own venv (`uv venv`, `maturin
develop --release --offline`; the pre-P7 checkouts also need `cargo` on
`PATH` for the ctypes library, which the first attempt `-02` to `-05` lacked:
those four runs stopped at `FileNotFoundError: 'cargo'` and are harness
failures, not results). The first-parent history has no intermediate commit
to bisect in either case: the failing code first appears on main in the merge
itself.

| Run | Commit | What it is | Result |
| --- | --- | --- | --- |
| `-06-l1-4584936` | `4584936` | L1's branch head (base before P2) | **pass**, all three parts (47.8 s, 309 MB) |
| `-07-l1-cbf9003` | `cbf9003` | merge of L1 into main (P2 on main since `125d42a`) | **fail**, the same 22 false leaves as at `f6d6a96` |
| `-08-l2-a279d34` | `a279d34` | main after the L2 merge, before P5 | **pass**, all three parts (34.9 s, 626 MB) |
| `-09-l2-29d67b4` | `29d67b4` | merge of P5 | **fail**, the same `ValueError` at the same line |

`git merge-base --is-ancestor`: P2 (`125d42a`) is not an ancestor of
`4584936`; L2 (`56d5680`) is not an ancestor of P5's branch head `f902011`.

## 3. Why the merge checks did not catch them

- **L1.** L1's precondition ran on its branch (`4584936`, before P2) and
  passed; the merge `cbf9003` was not re-run against the precondition. P5
  then ran it unmodified at `07dfb86` and recorded the image-only failure as
  P2's state (p5-memory.md 1.4) and compared its own replay by pixels and
  metrics. L2 wrote `compare_replay_tolerant` for exactly this, and L1-M and
  C1 gate their criterion 1 on it, computed from an L1 precondition
  directory whose own `passed.replay` is false. So every later task passed
  its gate while L1's own gate kept saying `pass: false` on every host since
  `cbf9003`.
- **L2.** P5's identity claims are true for what P5 ran: K, the L1 driver
  and its four-station replay. L2's driver was not in P5's base, and no test
  reaches `core_campaign_1830.run` (`tests/test_core_campaign_1830.py`
  covers the helpers on synthetic data). L1-M and C1 import only L2's
  comparator, not its driver, so their preconditions passed after P5. L2's
  archived campaign (`results/luno-1830-campaign.json`) was produced before
  P5 and is unaffected; any rerun of `campaign-1830 run` since `29d67b4`
  would have failed at the same line.

## 4. Fix (this branch)

- `python/rangtoy/core_campaign_1830.py`, `run`: the amendment-1 base solve
  gets `array.additions_dense(state, fp["added"])`, and the image loop's
  `added` is `array.additions_dense(state, solve["added"])` (feeds
  `derived_row_flags`, the additions count, fraction, holdout count, hash
  and the saved `flags/<arm>.npz`, which are again the dense mask, as
  archived). This mirrors `core_campaign_array.run` lines 1575 and 1679.
- `python/rangtoy/core_campaign_array.py`, `precondition`: part 2 passes if
  `core_campaign_1830.compare_replay_tolerant` is `all_equal` and K's result
  hash matches the archive (lazy import, as in L1-M and C1, to avoid the
  import cycle). The exact `compare_replay` dict stays the body of
  `replay` and the tolerant one is stored under `replay.tolerant`. This is
  recorded as an amendment in
  [luno-array-campaign.md](luno-array-campaign.md) (post hoc, PC1).
- `tests/test_pc1_preconditions.py`: runs `array.precondition` (asserts all
  three parts pass and that the exact comparison differs on `image_*` keys
  only) and `core_campaign_1830.precondition` (all three parts pass) into
  `tmp_path`. About 10 s and 7.5 s; skipped when K run `-01` or the local
  LUNO tiles are absent (CI). With the two driver edits reverted both tests
  fail (the L1 one on `passed.replay`, the L2 one on the same `ValueError`).

P5's memory gains are untouched: the stored solves keep their index form;
the dense mask exists only transiently, per arm, as in L1's driver.

## 5. Identity after the fix

| Check | Run | Result |
| --- | --- | --- |
| L1 precondition | `-10-l1-fix` (8.7 s, 333 MB) | **pass**, all three parts; exact comparison false on the same image leaves only |
| L1 replay against the merge `cbf9003` | `-10` vs `-07`, `replay/result.json`, 1,073 leaves | identical on every field except timings, memory and `cost_clause.ratio` (a wall-time ratio), images included |
| L1 replay against L1's own pre-P2 run | `-10` vs `-06`, 823 leaves | differs only on image products (hashes; metrics ≤ 2e-15 relative) and the amendment-1 arm that `4584936` predates; `candidates.json` identical bar that arm |
| L2 precondition | `-11-l2-fix` (8.8 s, 310 MB) | **pass**, all three parts (K, tolerant replay, MAIN_2 survey) |
| L2 replay against pre-P5 main | `-11` vs `-08`, `replay/result.json` 1,158 leaves, `candidates.json` 345 | identical on every field except timings, memory, `cost_clause.ratio` and the absolute input roots; all 28 saved `flags/*.npz` and FITS files byte-identical |
| K precondition | `-14-k-precondition` (1.7 s) | all checks pass, χ² 0.26823507037914956 equal to the archive |
| C1 checker on the archived run with the new precondition | `-12-c1-check` vs `c1-20261030-02-check` | identical except `passed_as_l1.replay` and L1 criterion `3_precondition`, both false → true, and the precondition path |
| L1-M checker on the archived runs with the new precondition | `-13-l1m-check` vs `l1m-20261030-04-check` | identical except `passed_as_l1.replay` and the three per-model L1 `3_precondition`, false → true, and the path |
| Campaign tests | `tests/test_pc1_preconditions.py tests/test_core_campaign*.py` | 59 passed, none skipped (16.3 s) |

No archived number changes. The full L2 campaign (`campaign-1830 run` on
MAIN_2) was not rerun: it is the same `run` function whose four-station
replay is identical to pre-P5 main on every field, and the two edited lines
are shape conversions with no arithmetic.

## Timings (every tool run of this task)

| Start | Run | Wall | Peak RSS | Notes |
| --- | --- | ---: | ---: | --- |
| 17:31 | venv at the worktree (`uv venv`, `uv pip install`, `maturin develop --release --offline`) | about 2 min | – | |
| 17:33 | `precondition_luno_array.py` at `f6d6a96` (`-01-l1`) | 9.3 s | 349 MB | reproduces: image-only fail |
| 17:33 | `precondition_luno_1830.py` at `f6d6a96` (`-01-l2`) | 6.2 s | 150 MB | reproduces: `ValueError` |
| 17:34 | bisect worktrees and venvs, four commits | about 30 s each | – | `uv` and cargo caches warm |
| 17:34 | bisect runs `-02` to `-05` | 1.5–1.8 s each | 120–126 MB | harness failure: no `cargo` on `PATH` for the pre-P7 ctypes build |
| 17:36 | L1 precondition at `4584936` (`-06`) | 47.9 s | 309 MB | pass |
| 17:37 | L1 precondition at `cbf9003` (`-07`) | 33.7 s | 622 MB | fail, image-only |
| 17:37 | L2 precondition at `a279d34` (`-08`) | 34.9 s | 626 MB | pass |
| 17:38 | L2 precondition at `29d67b4` (`-09`) | 28.9 s | 627 MB | fail, `ValueError` |
| 17:39 | L1 precondition with the fix (`-10`) | 8.7 s | 333 MB | pass |
| 17:39 | L2 precondition with the fix (`-11`) | 8.8 s | 310 MB | pass |
| 17:41 | `check_c1.py` against the new precondition (`-12`) | 4.3 s | 209 MB | all criteria pass |
| 17:41 | `check_l1m.py` against the new precondition (`-13`) | 12.4 s | 209 MB | all criteria pass |
| 17:41 | `precondition_luno_campaign.py` (`-14`) | 1.7 s | 150 MB | all pass |
| 17:44 | pytest, the two new tests | 17.7 s | – | 2 passed |
| 17:45 | `bash tools/check-all.sh` (`-15-check-all.log`) | 4 min 44 s | 1.9 GB | PASS: 106 Rust tests, clippy, fmt, ruff, 599 passed and 5 skipped in pytest |
| 17:52 | `bash tools/check-all.sh` plain, after the report fixes (`-16-check-all.log`) | 2 min 0 s | – | PASS: 599 passed and 5 skipped in pytest |

## Open items

- Main moved to `e3dd42a` (P11 record, DF2a) during this task. DF2a changes
  only the w-gridder (`core/src/wgridder.rs`, `core_wgridder.py`), which no
  campaign driver uses, and the C1 import; the branch merges cleanly
  (`git merge-tree`). The preconditions were not rerun on the merge.
- After the fix the exact `replay.all_equal` of the L1 precondition is still
  false by design (image hashes); only `replay.pass`, from
  `replay.tolerant.all_equal`, gates.

- The L2 campaign run itself has not been re-executed since P5; the replay
  identity covers its code path, not MAIN_2's 64-station memory.
- A full-scale task that edits a shared helper's return form should grep the
  whole package for its consumers; the new test makes the L1 and L2
  preconditions part of `check-all` on hosts that hold the inputs, which
  would have caught both merges.

## For the coordinator

- **STATE paragraph.** "PC1 merged: the L1 and L2 preconditions pass again
  (research/pc1-preconditions.md). Both failures were merge interactions,
  not regressions inside a task. L1's precondition compared image hashes
  exactly and has failed on main since the L1 merge `cbf9003`, because P2
  (rustfft gridder, image pixels within 2e-15) merged first; it now gates on
  L2's tolerant comparison, as L1-M and C1 already did, and keeps the exact
  comparison in its output (so `replay.all_equal` stays false by design;
  `replay.pass` follows `replay.tolerant.all_equal`). L2's driver broke at the P5 merge `29d67b4`: P5
  stores additions as cell indices and L2's `run` (not in P5's base) passed
  them as a mask; it now expands them with `additions_dense`. No archived
  number changes; the L2 replay equals pre-P5 main on every non-timing field
  and file. `tests/test_pc1_preconditions.py` runs both preconditions (about
  18 s) when the LUNO inputs are on the host. P11's suite listed both as
  identity-of-failure steps; they now pass, which is the expected
  difference, not a regression."
- **Timing rows** for `research/tool-timings.md`: the table above, as
  `2026-10-30 | big plan PC1: ...` rows.
- **Plan line** for `research/big-plan.md`: "PC1 preconditions — done
  2026-10-30: L1 precondition gated on the tolerant replay comparison (P2
  image bits), L2 driver fixed for P5's index-form additions; both
  preconditions in `tests/` (research/pc1-preconditions.md)."
- **P11 suite.** The L1 and L2 precondition steps of
  `results/p11-extract/suite.sh` change from fail to pass after this merge.
