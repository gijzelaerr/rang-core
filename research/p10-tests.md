# P10: test-suite speed

Task P10 of [big-plan.md](big-plan.md), cut from section 2.9 and proposal
P10 of [simplification-review.md](simplification-review.md). Branch
`p10-tests` from `4167141`. Status: **implemented and measured** (protocol and baseline committed in
`c9b2335` before any test edit; changes in `d2c6812`). Under the shared
load the suite went from 672 s to 223 s wall and from 6,031 to 188
CPU-seconds in the matched A/B pair; `test_pointing.py` and
`test_blocked.py` met their targets, `test_beams.py` did not.

## Protocol (frozen before changes)

**Scope.** `tests/test_pointing.py`, `tests/test_blocked.py`,
`tests/test_beams.py`, a new `tests/conftest.py`, and pytest configuration
lines in `pyproject.toml` (listed for the coordinator). No library code
under `python/rangtoy` or `src/` changes; a test that is slow because the
library is slow is recorded, not fixed here. `tools/check-all.sh` is not
edited; a change is proposed for the coordinator.

**Rule.** Same tests, same assertions, same numerical tolerances; no test
deleted, skipped or weakened. Allowed:

1. fixture scoping (module- or session-scoped expensive setups computed
   once);
2. de-duplicating repeated identical solves across parametrised cases
   (the same call with the same arguments, computed once and asserted on
   in each case);
3. smaller problem sizes only where the assertion does not depend on the
   size, stated per case;
4. thread pinning (`OPENBLAS_NUM_THREADS`, `XLA_FLAGS`, similar) in
   `tests/conftest.py`, set with `setdefault` so a caller's explicit
   environment wins, so that one pytest process does not oversubscribe a
   shared host;
5. `pytest -n` through `pytest-xdist` only if it is added to the `test`
   extra in `pyproject.toml` (line listed) and the total is measured
   faster.

**Acceptance.**

- identical pass/fail set and test ids: `pytest --collect-only -q` before
  and after must not differ, and every test passes before and after
  (junit outcome files compared);
- measured suite wall and CPU-seconds before and after, in A/B pairs run
  back to back under the same load, load average recorded per run;
- each of the three slow modules below a stated target under the shared
  load of the A/B pairs: `test_pointing.py` below 50 % of its paired
  baseline, `test_blocked.py` below 50 %, `test_beams.py` below 75 %
  (smaller gain expected: fewer dense solves), and suite CPU-seconds below
  50 % of the paired baseline. Wall time is the primary number; CPU-seconds
  matter because sibling sessions share the 8 physical cores.

**Measurement.** `tools`-free scripts in the task scratchpad: each run is
`/usr/bin/time -v python -m pytest -q -p no:cacheprovider --durations=0
--junitxml=...` (durations=0 is a superset of the requested
`--durations=40`), a sampler records the pytest process's thread count
(`ps -o nlwp`) and the 1-minute load every 2 s, and per-module time is the
sum of junit test times per file. Outputs under
`outputs/p10-tests-20261030-NN/`.

## Baseline (2026-10-30, `4167141`, three consecutive full runs)

Host: Ryzen 7 7700X, 8 physical cores / 16 threads, 30 GiB, WSL2; Python
3.14, JAX/jaxlib 0.12.0.1, NumPy 2.5.4 (scipy-openblas 0.3.34, 64 threads
max, `NO_AFFINITY`), SciPy 1.18.1, pytest 9. Sibling sessions were running
(the whole-array LUNO campaign, the P4 eigensolver bench and, during run 1,
another full `pytest`, itself 144 threads). Outputs in
`outputs/p10-tests-20261030-02/` (`base-{1,2,3}.*`, `collect-before.txt`).

| Run | Wall s | CPU s (user+sys) | CPU/wall | Peak RSS MB | Max threads (nlwp) | Mean load1 | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| base-1 | 946 | 7,679 | 8.1 | 1,676 | 144 | 27.1 | 555 passed |
| base-2 | 760 | 6,892 | 9.1 | 1,630 | 145 | 26.5 | 555 passed |
| base-3 | 1,294 | 8,968 | 6.9 | 1,703 | 145 | 33.5 | 555 passed |

Per module (sum of junit test times, s):

| Module | base-1 | base-2 | base-3 |
| --- | ---: | ---: | ---: |
| `tests/test_pointing.py` | 732 | 456 | 917 |
| `tests/test_blocked.py` | 124 | 164 | 252 |
| `tests/test_beams.py` | 55 | 119 | 93 |
| other 42 files (515 tests) | 33 | 18 | 28 |

Slowest tests (base-1 / base-2 / base-3, s):
`test_correlated_flux_constraints_do_not_create_data_information` 400 /
287 / 395; `test_flux_anchor_geometry_controls_number_of_common_modes` 124 /
94 / 269; `test_blocked_matches_dense_and_numpy[True]` 77 / 41 / 136 and
`[False]` 44 / 122 / 113; `test_full_coverage_retains_modes_with_gains_and_differential_pointing`
89 / 27 / 84; `test_nonquadratic_rotating_beam_breaks_local_gauge` 53 / 17 /
83; `test_chromatic_shape_lifts_the_gaussian_gauge` 36 / 88 / 64.

Observations: the run-to-run spread (760–1,294 s) is the shared load, not
the suite; the process spends 7–9 cores of CPU for the whole run while the
idle-host suite took 74 s (task K), so most of the CPU is spent spinning
or contending in the thread pools (145 threads: XLA's pools, OpenBLAS's 16
threads). All seven slow tests build the full-coverage reference
(2,688 complex rows) and call `sky_locked_information`, whose dense
`lstsq`/`svd` of a 5,376 × 1,934 nuisance design dominates.

## Thread probe (before editing)

One full-coverage test,
`test_full_coverage_retains_modes_with_gains_and_differential_pointing`,
run alone under each setting, two interleaved rounds, load1 30–44
(`outputs/p10-tests-20261030-03/`; wall s / user s / sys s):

| Setting | Round 1 | Round 2 |
| --- | --- | --- |
| default (16-thread OpenBLAS, XLA default) | 148.7 / 749.2 / 1.6 | 141.8 / 754.6 / 1.6 |
| `OPENBLAS_NUM_THREADS=1` | 21.7 / 11.3 / 0.6 | 22.3 / 12.3 / 0.6 |
| `OPENBLAS_NUM_THREADS=2` | 12.8 / 14.3 / 0.7 | 24.2 / 18.0 / 0.7 |
| `OPENBLAS_NUM_THREADS=4` | 13.9 / 26.0 / 0.6 | 20.7 / 32.8 / 0.7 |
| OpenBLAS 1 + XLA single-threaded | 13.6 / 11.1 / 0.6 | 14.4 / 11.0 / 0.7 |
| OpenBLAS 4 + XLA single-threaded | 23.2 / 38.4 / 0.6 | 16.9 / 31.8 / 0.8 |

With the default pools the test spends 750 s of *user* CPU in 145 s of
wall (about 5 cores busy) for about 11 s of useful work: the OpenBLAS
pools (NumPy's and SciPy's bundled scipy-openblas each start 15 extra
threads at import) busy-wait in user space while competing with the other
sessions' threads; system time stays at 0.6–1.6 s in every setting. One
BLAS thread with XLA's
`--xla_cpu_multi_thread_eigen=false intra_op_parallelism_threads=1` was the
cheapest in both rounds and the fastest in round 2 (`OPENBLAS_NUM_THREADS=2`
was 0.8 s faster in round 1 but 9.8 s slower in round 2), so it is the
default in `tests/conftest.py`. jaxlib 0.12.0.1 accepts these flags (an unknown flag
would abort), but XLA's CPU client still creates its pools: a process that
has run one JAX computation holds 82 threads with the flags and 112
without, and the pytest process held 114 threads instead of 144–145. The
gain comes from fewer *busy* threads, not from fewer threads.

## Changes (`d2c6812`)

- **`tests/conftest.py` (new).** `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS`
  and `MKL_NUM_THREADS` default to 1, and `XLA_FLAGS` to the single-thread
  flags. Each default applies only if the caller has not set the variable,
  so `OPENBLAS_NUM_THREADS=16 pytest` restores the old behaviour. No
  installed pytest plugin imports NumPy earlier, so the caps take effect
  (checked: after `import numpy` the process has 1 thread instead of 16).
  Two session fixtures, `pointing_reference` and
  `pointing_full_reference`, build the Rust references once per session.
  Before, three module fixtures and six tests each rebuilt one (`cargo
  build` + `cargo metadata` + the `rang-toy` subprocess + a JSON parse).
  Both references carry the same `sources` (checked), so every test gets
  the same components and `Observation` as before. JAX 64-bit mode is
  enabled inside the fixture before any array is built.
- **`tests/test_blocked.py`.** The dense `sky_locked_information` audit
  with the katbeam predictor does not depend on `frequency_blocking`: that
  flag only reaches `prepare_blocked_design`. A module fixture now
  computes the audit once, and both parametrised cases assert against it
  (rule 2).
- **`tests/test_pointing.py`, `tests/test_beams.py`.** The module fixtures
  and the five full-coverage tests take the session references. One
  rule-3 case: in
  `test_correlated_flux_constraints_do_not_create_data_information`, the
  final `pytest.raises(ValueError, match="positive definite")` check now
  runs on the thinned rows. The library validates the log-flux covariance
  only after it has built the whole nuisance design and solved its
  `lstsq`, so this check cost one full-coverage audit. The claim (a
  negative-definite covariance is rejected) does not depend on the row
  count, and the thinned rows have the same four channels, so the
  covariance has the same 16 × 16 shape. Every other assertion, input and
  tolerance is unchanged.
- Not done:
  - `pytest-xdist`: one test takes 60–430 s, and xdist cannot split a
    test, so the critical path stays. Extra workers would also take cores
    from sibling sessions. Not measured, so not added.
  - A `slow` marker: deselection is outside the allowed list, and the
    whole suite now fits in check-all.
  - Shrinking a full-coverage problem: every full-coverage assertion
    checks size-dependent counts or values (336, 1,536 and 46 nuisance
    parameters, `[6.2691, 6.7314]`, `[8.40284, 8.30909]`, `< 1.2`
    arcsec).

## A/B result

Full suite in ABBA order, with `A` = `c9b2335` (protocol commit, original
tests) and `B` = `d2c6812`, same venv and builds
(`outputs/p10-tests-20261030-05/`). During the last `A` run the load rose
from 26 to 68–98: six other `pytest` processes from sibling sessions were
running, with 144–176 threads each. So `A1`/`B1` is the matched pair, and
`B2`/`A2` is reported with that caveat.

| Run | Load1 mean | Wall s | CPU s | CPU/wall | Peak RSS MB | Max nlwp | `test_pointing` s | `test_blocked` s | `test_beams` s | other s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A1 | 26.5 | 672 | 6,031 | 9.0 | 1,638 | 145 | 583.5 | 39.7 | 31.1 | 14.9 |
| B1 | 25.8 | 223 | 188 | 0.84 | 1,631 | 114 | 145.8 | 19.1 | 31.6 | 22.6 |
| B2 | 26.9 | 311 | 235 | 0.76 | 1,777 | 114 | 153.6 | 41.5 | 51.5 | 49.2 |
| A2 | 68.5 | 4,140 | 13,263 | 3.2 | 1,528 | 144 | 2,742.9 | 743.9 | 530.3 | 76.2 |

In the matched pair A1 → B1, suite wall fell to 33 % and CPU-seconds to
3.1 %. Per module:

- `test_pointing.py`: 25 % (target < 50 %: met).
- `test_blocked.py`: 48 % (target < 50 %: met, narrowly).
- `test_beams.py`: 102 % (target < 75 %: **not met**).

Against the three baseline runs of the same tests (mean 1,000 s wall and
7,846 CPU-s, load 26–34), B1 and B2 took 22–31 % of the wall and 2.4–3.0 %
of the CPU.

A second, closer load match for the last `A` run: the pytest step of the
`tools/check-all.sh` run on `B` (below) took 584 s at load 65–82, against
A2's 4,140 s at load 68.5, i.e. 14 % (wall only: check-all runs pytest
without junit or the thread sampler, so no per-module split).

Why `test_beams.py` did not improve:

- Most of the module is short `solve_pointing` fits on the thinned rows
  (1–4 s each). With one BLAS thread under contention they lose a little
  (for example 2.2 → 3.5 s and 1.9 → 4.1 s in A1 → B1).
- Its one full-coverage test fell from 18.1 to 12.9 s. The reference
  builds cost the same in both arms (in `A` its module fixture built the
  thinned reference and that test built the full one).
- Its jitted kernels are module-level (`beams.py`), so sharing predictors
  would not save compilation, and the rule allows no further
  de-duplication.

The other 42 files became somewhat slower (14.9 s → 22.6 and 49.2 s), from
the same single-thread effect on small NumPy work. They are a small share
of the total.

**Pass/fail set.** Every run, `A` and `B`, had 555 passed, and the junit
outcome files are identical. The before and after
`pytest --collect-only -q` outputs (`-02/collect-before.txt`,
`-04/collect-after.txt`) differ only in the "collected in" timing line, so
the 555 test ids are the same.

**Idle host (estimate, not measured).** With one BLAS thread the suite
cannot use idle cores. B's 188 CPU-s suggests roughly 120–190 s on an idle
host, against the 74 s that task K measured with the default pools. On an
idle machine, `OPENBLAS_NUM_THREADS=8 XLA_FLAGS= pytest` restores the
default pools. This host was not idle at any point during this task.

## For the coordinator

**STATE paragraph.** P10 (test-suite speed, branch `p10-tests`): a
`tests/conftest.py` caps OpenBLAS/OMP/MKL at one thread and XLA's CPU
backend at one intra-op thread, and builds the pointing references once
per session. The caps are defaults, and the caller's environment wins.
`test_blocked` computes its dense audit once, and one validation check
moved to the thinned rows. The 555 test ids are unchanged and all pass. In
the matched A/B pair under load 26, full pytest went from 672 to 223 s
wall and from 6,031 to 188 CPU-s: `test_pointing` 584 → 146 s,
`test_blocked` 40 → 19 s, `test_beams` unchanged (31 s). On an idle host
the cap is estimated to cost about 1.5–2.5× wall; `OPENBLAS_NUM_THREADS`
overrides it.

**pyproject / check-all.** No `pyproject.toml` line is needed (no xdist,
no marker). The thread caps need no `tools/check-all.sh` change: its
pytest step picks up `tests/conftest.py`. Proposed separately, following
the coordinator's load-control instruction of 2026-10-30 (load 55–98 with
up to seven concurrent suites, as seen in A2): check-all takes a host-wide
lock itself, so suites queue instead of overlapping, near the top after
`cd`:

```bash
# One check-all at a time on a shared host; RANG_CHECKALL_LOCK overrides.
lock=${RANG_CHECKALL_LOCK:-$HOME/.rang-checkall.lock}
if [ -z "${RANG_CHECKALL_LOCKED:-}" ]; then
  export RANG_CHECKALL_LOCKED=1
  exec flock "$lock" bash "$0" "$@"
fi
```

The two check-all runs of this task (`-06`, `-07`) started before that
instruction and ran without the lock.

**Timing rows** (for `tool-timings.md`):

| Date | Tool / stage | Input | Wall | Peak RSS | Notes |
| --- | --- | --- | ---: | ---: | --- |
| 2026-10-30 | `uv venv` / `uv pip install -e .[pointing,beam,test,imaging]` / `maturin develop --release` | P10 worktree | 0.01 / 10.6 / 10.5 s | 22 / 377 / 382 MB | setup, `outputs/p10-tests-20261030-01/` |
| 2026-10-30 | pytest 9, full suite base-1/2/3 (tests of `4167141`) | 555 tests | 946 / 760 / 1,294 s | 1,676 / 1,630 / 1,703 MB | CPU 7,679 / 6,892 / 8,968 s; load 27–34; 145 threads |
| 2026-10-30 | pytest, one full-coverage test, 6 thread settings × 2 | 1 test | 12.8–148.7 s | 747–848 MB | probe table in `research/p10-tests.md` |
| 2026-10-30 | pytest, three pointing modules after the change | 71 tests | 95.5 s | 1,370 MB | user 110 s, load 19 |
| 2026-10-30 | pytest full suite A1 / B1 / B2 / A2 | 555 tests | 672 / 223 / 311 / 4,140 s | 1,638 / 1,631 / 1,777 / 1,528 MB | CPU 6,031 / 188 / 235 / 13,263 s; load 26.5 / 25.8 / 26.9 / 68.5 |
| 2026-10-30 | `bash tools/check-all.sh` on `d2c6812` + first version of this note | repo | 758 s (pytest step 584 s) | 1,770 MB | PASS; user 281 s, sys 18 s; load 65–82 (A2 took 4,140 s at load 68); `outputs/p10-tests-20261030-06/`; no lock |
| 2026-10-30 | `bash tools/check-all.sh` on the corrected note | repo | 838 s (pytest step 701 s) | 1,813 MB | PASS; user 223 s, sys 12 s; load 73–83; `outputs/p10-tests-20261030-07/`; no lock (started before the lock instruction), lock wait 0 |

**Upstream observations.** These tests exercise no RATT software (no
caracal-pipeline, QuartiCal, Tricolour or dask-ms), so there is nothing
for U1's RATT list. Non-RATT items, for `non-ratt-observations.md`:

1. The NumPy and SciPy wheels each bundle scipy-openblas, and each starts
   a pool of `ncpu - 1` threads at import. Under oversubscription the
   pools busy-wait in user space: 750 s of user CPU (1.6 s system) in a
   single 149 s test whose single-threaded run needs 11 s of CPU.
   Setting `OPENBLAS_NUM_THREADS` before import caps both pools.
2. jaxlib 0.12's CPU client creates about 80 threads even with
   `--xla_cpu_multi_thread_eigen=false intra_op_parallelism_threads=1`.
   The flags reduce the work in those pools but not their creation, and
   no documented single switch gives a one-thread CPU client.
3. A local library note, not upstream: `sky_locked_information` validates
   `log_flux_prior_covariance` only after it has built and solved the
   whole nuisance design. Validating first would make bad input fail
   fast. Not changed here, because library code is out of scope.

**Open items.**

- The `test_beams.py` target was missed (see above).
- The idle-host cost of the caps is estimated, not measured.
- Whether `pytest-xdist` with single-threaded workers would help on idle
  hosts is untested.
