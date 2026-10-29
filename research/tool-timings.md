# Tool timings

Started 2026-10-29 at the user's request. Every pipeline tool run is wall-timed
and logged here, failures included. The log feeds an investigation of upstream
bugs and performance (QuartiCal, dask-ms, python-casacore, Stimela2, CARACAL)
and a later review of pipeline complexity. Each row gives one run. The host is
the WSL2 workstation in [STATE.md](STATE.md) (16 cores, 30 GiB) unless noted.
Rows marked "archived" are copied from earlier reports, not re-measured.

| Date | Tool / stage | Input | Wall | Peak RSS | Notes |
| --- | --- | --- | ---: | ---: | --- |
| 2026-10-29 | pytest 9.1.1, full suite (654 tests) | repo | 986 s | – | dominates every pre-commit check |
| 2026-10-29 | curl, `fetch-luno-support.sh` | 122 S3 objects, 3.22 GB | 325.7 s | – | about 9.9 MB/s from af-south-1; user 14 s, sys 13 s |
| 2026-10-29 | curl, `fetch-luno-solve.sh` subtables + MAIN_1 row columns | 2,608 small S3 objects, 2.3 MB | 432.4 s | – | about 6 objects/s; sequential per-object curl, latency-bound (FEED is 56 groups × many tiny chunks) |
| 2026-10-29 | casacore 3.8.1 + numcodecs, `build_luno_ms.py` | 192 rows × 2048 ch × 4 corr | 2.4 s | 32 MB | pinned container, dry run (DATA = MODEL) |
| 2026-10-29 | QuartiCal 0.2.7 `goquartical`, G complex 2×32, 50 iter | dry MS, 4 stations | 27 s (28.0 s with container) | 32 MB (container wrapper) | single-threaded; converged immediately (DATA = MODEL), so this is mostly start-up cost (Numba JIT) |
| 2026-10-29 | rang native normals + NumPy rank, `survey_luno_solved.py` | 117,556 TRAIN cells, 1024 bins | 0.47 s | 98 MB | host venv |
| 2026-10-29 | `run-injections.sh` (QuartiCal 0.2.7 trials) | prepared SKA fixture | 296 s | – | archived; 400 s on the previous Mac host |
| 2026-10-29 | CARACAL native strategies | fixture | 1265 s | – | archived |
| 2026-10-29 | response stage | fixture | 96 s | – | archived |
| 2026-10-29 | concurrent suite | fixture | 445 s | – | archived |
| 2026-10-29 | five-track `run-next.sh` campaign | fixture | 436 s | – | archived |
