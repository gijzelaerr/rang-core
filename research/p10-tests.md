# P10: test-suite speed

Task P10 of [big-plan.md](big-plan.md), cut from section 2.9 and proposal
P10 of [simplification-review.md](simplification-review.md). Branch
`p10-tests` from `4167141`. Status: **protocol and baseline measured;
changes not yet made** (this section is committed before any test edit).

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
