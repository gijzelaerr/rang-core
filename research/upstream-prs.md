# Upstream issues and pull requests (big plan task U2, 2026-10-30)

Task U2 of [big-plan.md](big-plan.md): after the user allowed CARACal and Stimela reports
(2026-10-30), file the remaining findings that reproduce on the latest release and open pull
requests for every filed issue with a fix. U1's issues are in
[upstream-notes.md](upstream-notes.md) ("Upstream status after task U1"). Per-finding
records: [upstream-issues/](upstream-issues/). Scripts and compact results:
[upstream-prs-files/](upstream-prs-files/). All issues and PRs are under the user's account
(gijzelaerr); commits as Gijs Molenaar <gijsmolenaar@gmail.com>.

Maintainer replies that shaped the PR list (and coordinator direction): QuartiCal #452
(JSKenyon: "I will fix it on the dev branch as soon as possible") and #453 (he will look at
it): no PRs. Tricolour #110 (sjperkins: 0.5.0, without `ProgressBar`, is about to replace the
0.2 line): no PR. Tricolour #111 (sjperkins asked for a PR on `0.5.0-dev`): done, merged.

## Summary

| Finding | Issue | PR | Tests run | Upstream CI / review |
|---|---|---|---|---|
| Tricolour integer `spike_width_time` recompiles (U1) | [tricolour#111](https://github.com/ratt-ru/tricolour/issues/111) | [tricolour#112](https://github.com/ratt-ru/tricolour/pull/112) (`0.5.0-dev`) | new test fails before (2 signatures, 93 s) / passes after (47 s); `pytest -m "not acceptance"` 58 passed, 2 skipped; ruff 0.13.2 | 4/4 green; **merged** 2026-10-30 by sjperkins; #111 still open (non-default base) |
| same, CARACal strategy files | refs tricolour#111 | [caracal#1708](https://github.com/caracal-pipeline/caracal/pull/1708) | new strategy-type test 9 failed / 9 passed; `pytest tests` 13 passed; ruff 0.16.6 | 3.10-3.12 pass, 3.9 fails at "Set up Python 3.9" (runner); **approved** by paoloserra |
| Stimela on Python 3.14 | [stimela#619](https://github.com/caracal-pipeline/stimela/issues/619) | [stimela#620](https://github.com/caracal-pipeline/stimela/pull/620) | new xrun test fails before on 3.13.16 and 3.14.8, passes after; `test_scatter` fails before / passes after on 3.14; full suite 72 passed on 3.13.16 and 3.14.8; ruff 0.12.9 | 3.10-3.14 pass, 3.9 runner failure as above; review required |
| Tricolour frequency axis, rows as lanes | [tricolour#113](https://github.com/ratt-ru/tricolour/issues/113) | [tricolour#114](https://github.com/ratt-ru/tricolour/pull/114) (`0.5.0-dev`) | equivalence test passes before and after; `pytest -m "not acceptance"` 57 passed, 2 skipped; flags bit-identical in the benchmark | no checks yet (fork PR awaiting admin approval) |
| QuartiCal `complex` convergence, cap ends half the solves | [QuartiCal#455](https://github.com/ratt-ru/QuartiCal/issues/455) | none (proposal) | sweep on 0.2.7, see below | – |
| QuartiCal qp JHJ weights (U1) | [QuartiCal#452](https://github.com/ratt-ru/QuartiCal/issues/452) | none (maintainer fixes it) | local fix + test on v0.2.8-dev: 8/8 fail before, 8/8 pass after; not pushed | – |
| QuartiCal HISTORY row (U1) | [QuartiCal#453](https://github.com/ratt-ru/QuartiCal/issues/453) | none (feature, maintainer looking) | – | – |
| Tricolour non-TTY ProgressBar (U1) | [tricolour#110](https://github.com/ratt-ru/tricolour/issues/110) | none (0.5.0 drops it) | `0.5.0-dev` b01ac8f has no `ProgressBar` | – |
| CARACal first pass empties station-bins | not filed | – | reproduced on scan 9, see below | – |

Forks created: gijzelaerr/stimela, gijzelaerr/tricolour, gijzelaerr/caracal,
gijzelaerr/QuartiCal (the last unused: no PR). Branches: `python314-event-loop`,
`issue-111-float-parameters`, `lanes-frequency-axis`, `tricolour-float-parameters`.

## 1. Stimela on Python 3.14 (filed, PR)

Details: [upstream-issues/stimela-python314.md](upstream-issues/stimela-python314.md). Latest
release 2.1.4 (`<3.14`), pre-release 2.2.0rc1 and `master` 9747611 (`<=3.14`). A one-cab
recipe (`upstream-prs-files/echo.yml`, `repro.sh`) fails on 3.14.8 with 2.1.4 and 2.2.0rc1
("There is no current event loop", `xrun_asyncio.py:116`), passes on 3.13.16. `<=3.14` admits
only 3.14.0 (pip refuses 2.2.0rc1 on 3.14.8; uv does not enforce it). Fixing the loop exposed
a second 3.14 failure: scattered loops break under the new `forkserver` default
(`AttributeError: ... 'StimelaLibrary'`). PR: get-or-create-and-set loop, `loop.create_task`,
fork context for the scatter pool on Linux, `requires-python <3.15`, 3.14 in CI.

## 2. Tricolour #111 and the CARACal strategies (PRs)

[upstream-issues/tricolour-int-spike-width.md](upstream-issues/tricolour-int-spike-width.md).
On `0.5.0-dev` the code moved to `src/tricolour/core/kernels/flagging.py` and
`conf/default_config.yaml` (same `spike_width_time: 2`). The PR casts the seven float
parameters in `sum_threshold_flagger` and `SumThresholdFlagger.__init__` and writes `2.0`;
integer and float values give identical flags (tested). CARACal: all nine MeerKAT strategy
files had one integer `spike_width_time` against floats in the other steps (two signatures
each, `types.py`); `outlier_nsigma` is an integer in every step, so it adds no compilation.

## 3. Tricolour rows as lanes (benchmarked, filed, PR)

[upstream-issues/tricolour-frequency-lanes.md](upstream-issues/tricolour-frequency-lanes.md).
Measured on `0.5.0-dev` first, as required: `sum_threshold_flagger`, one pinned core, one
thread, 35 warm calls per variant interleaved: minimum 0.610 -> 0.438 s (4 x 64 x 4096),
0.240 -> 0.183 s (8 x 32 x 2048), 0.338 -> 0.159 s (2 x 256 x 1024): 1.3-2.1x, flags
bit-identical. Faster, so filed and PR'd.

## 4. QuartiCal `complex` convergence (filed as a proposal)

[upstream-issues/quartical-complex-convergence.md](upstream-issues/quartical-complex-convergence.md).
On 0.2.7 and scan 9 with the defaults (25 iterations, 1e-6, stop fraction 0.99) the cap ends
46 % of interval solves; the 0.99 fraction is not reached by 100 iterations; chi-squared is
within 0.2 % of final by iteration 10 (2 x 32 intervals). Negative result: the gauge-invariant
products G_p G_q^H change as slowly as the gains, so a gauge-invariant criterion would not
help; the proposal is reporting/documentation plus an opt-in chi-squared criterion. Unit
weights (QuartiCal default), so #452 is not involved (bit-identical control).

## 5. QuartiCal #452 on v0.2.8-dev (no PR, recorded)

v0.2.8-dev 059c806 (2026-10-29) has no fix yet. All terms now share
`gains/general/solver_components.py`, which passes the pq weights `w` to both qp
accumulations (single-direction fast path and general path), so `complex`, `rotation`,
`rotation_measure` and `crosshand_phase` (the terms that read w_XY/w_YX) are affected. Test
(`upstream-prs-files/test_conjugate_baseline.py`): writing every row the other way round
(swap ANTENNA1/2, conjugate-transpose DATA and MODEL, transpose WEIGHT) must leave JHJ and
JHR unchanged; on dev JHR is invariant and JHJ differs by up to 2.0e3 (8/8 cases fail). The
two-line fix `w_qp = tuple_unpackct(w)` (`fix452.diff`) makes all 8 pass (730 s incl. JIT).
Kept local per the maintainer's reply; available if he wants it.

## 6. CARACal first-pass station-bins (not filed)

[upstream-issues/caracal-firstpass-station-bins.md](upstream-issues/caracal-firstpass-station-bins.md).
Reproduced with Tricolour 0.2.1 and the 1.2.1 strategy on scan 9 (native 51.5 % and widened
60.7 % pre-flags): 357 and 383 station x (2 x 32) bins lose every usable sample, but 318 and 328
of them are lost by all four stations at once (whole channels and dumps), i.e. RFI excision as
designed; no evidence of good data removed, and a minimum-unflagged guard would keep what the
flagger found. Not filed.

## Tool timings (for `tool-timings.md`)

Host: WSL2, 16 CPUs shared with four sibling tasks, load average 20-62 throughout.

| Date | Tool / stage | Input | Wall | Peak RSS | Notes |
| --- | --- | --- | ---: | ---: | --- |
| 2026-10-30 | stimela 2.2.0rc1 `stimela run` echo recipe, Python 3.14.8 | 1 native cab | 3.8 s | 95 MB | fails (no event loop); 2.1.4: 2.6 s, 91 MB, fails |
| 2026-10-30 | same, Python 3.13.16 | 1 native cab | 2.9 s | 89 MB | exit 0 |
| 2026-10-30 | same, 3.14.8 with the U2 fix | 1 native cab | 2.1 s | 94 MB | exit 0 |
| 2026-10-30 | stimela `pytest tests` (fix branch), Python 3.14.8 | 72 tests | 368 s | 88 MB | 72 passed |
| 2026-10-30 | stimela `pytest tests` (fix branch), Python 3.13.16 | 72 tests | 762 s | 82 MB | 72 passed |
| 2026-10-30 | tricolour 0.5.0-dev #111 test, before fix, empty Numba cache | 2x2x32x64 | 98.5 s | 583 MB | 2 signatures |
| 2026-10-30 | tricolour 0.5.0-dev #111 test, after fix | same | 51.6 s | 480 MB | 1 signature |
| 2026-10-30 | tricolour 0.5.0-dev `pytest -m "not acceptance"` (#111 branch) | 60 tests | 69.0 s | 579 MB | 58 passed, 2 skipped |
| 2026-10-30 | tricolour 0.5.0-dev `pytest -m "not acceptance"` (lanes branch) | 59 tests | 105.4 s | 558 MB | 57 passed, 2 skipped |
| 2026-10-30 | lanes benchmark, first round per variant (cold JIT) | 3 shapes x 6 calls | 239.9 s base, 142.2 s lanes | 444 / 458 MB | `bench.sh` |
| 2026-10-30 | lanes benchmark, warm rounds 2-7 | 3 shapes x 6 calls | 21.7-33.6 s base, 19.5-27.9 s lanes | 232 / 235 MB | `taskset` one core |
| 2026-10-30 | CARACal `pytest tests` | 13 tests | 12.1 s | 98 MB | 13 passed |
| 2026-10-30 | QuartiCal v0.2.8-dev conjugate-baseline test (8 cases), before fix | – | not recorded | – | 8 failed; incl. JIT (wall line cut from the log) |
| 2026-10-30 | same, after fix | – | 792 s | – | 8 passed; incl. JIT, load about 60 |
| 2026-10-30 | QuartiCal 0.2.7 `goquartical` scan 9, cold Numba cache, 5 iterations | 140 rows x 4096 ch | 99.1 s | 795 MB | trial |
| 2026-10-30 | QuartiCal 0.2.7 sweep, 1 x 1 intervals, k = 1-100 (16 runs + k26, k51) | same | 10.4-45.2 s per run | 545-550 MB | warm cache |
| 2026-10-30 | QuartiCal 0.2.7 sweep, 2 x 32 intervals (16 runs + k26, k51) | same | 11.4-18.8 s per run | 431-432 MB | warm cache |
| 2026-10-30 | Tricolour 0.2.1 CARACal first-pass strategy, native flags, cold cache | scan 9 | 514.9 s | 764 MB | under `script` (TTY) |
| 2026-10-30 | same, 60.7 % pre-flags, warm cache | scan 9 | 12.7 s | 440 MB | |

## Scratch deleted

`~/Build/tmp/20261030-upstream-prs/` (clones of QuartiCal, tricolour, caracal, stimela; the
`tricolour-base` and `tricolour-lanes` worktrees; venvs `venv-stimela-*`,
`venv-tricolour-dev`, `venv-quartical-dev`, `venv-qc027`, `venv-tric021`, `venv-caracal`,
`venv-pip-check`; `conv/` and `guard/` scan 9 copies and gain stores; `bench-lanes/`; logs).
Everything needed to reproduce is in `upstream-prs-files/` and on the fork branches.

## For the coordinator

- **Lines for `upstream-notes.md`** (new section "Upstream status after task U2"):
  - Stimela Python 3.14: **filed** caracal-pipeline/stimela#619, **PR** #620 (event loop in
    `xrun`, fork context for scatter workers, `requires-python <3.15`, 3.14 in CI).
  - Tricolour #111: **PR** ratt-ru/tricolour#112 on `0.5.0-dev`, **merged**; CARACal
    companion caracal-pipeline/caracal#1708 (float `spike_width_time` in nine strategies),
    approved.
  - Tricolour rows as lanes: **filed** ratt-ru/tricolour#113, **PR** #114 (1.3-2.1x for
    `sum_threshold_flagger` on one thread, bit-identical).
  - QuartiCal convergence: **filed** ratt-ru/QuartiCal#455 (cap ends about half of the
    default solves; gauge-invariant criterion would not help; chi-squared settles by 10-15).
  - QuartiCal #452/#453, Tricolour #110: no PRs by maintainer direction; #452 also affects
    `rotation`, `rotation_measure`, `crosshand_phase` on v0.2.8-dev (local test 8/8).
  - CARACal first-pass station-bins: not filed (whole-channel excision, no demonstrated harm).
- **STATE paragraph.** "Big plan task U2, 2026-10-30 (implemented; measured): filed
  stimela#619, tricolour#113 and QuartiCal#455; opened stimela#620, tricolour#112 (merged),
  tricolour#114 and caracal#1708 (approved). No PRs for QuartiCal #452/#453 and Tricolour
  #110 by maintainer direction. Rows-as-lanes in Tricolour 0.5.0-dev: 1.3-2.1x with
  bit-identical flags. QuartiCal 0.2.7 defaults on scan 9: 46-54 % of intervals converged at
  the 25-iteration cap, chi-squared settled by 10-15; the slow tail is not gauge drift. The
  CARACal first-pass station-bin loss reproduces on scan 9 but is whole-channel excision,
  not filed. Report: `research/upstream-prs.md`."
- **Timing rows**: the table above.
- **Open items**: watch #620 (review required), #114 (CI needs admin approval), #1708 (approved,
  not merged), #111 (open although #112 merged); the Python 3.9 CI failures on Stimela and
  CARACal are a runner change (3.9 unavailable on Ubuntu 26.04), not these PRs.
