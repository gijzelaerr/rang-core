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
| 2026-10-29 | curl, `fetch-luno-solve.sh --data` | 17 objects, 2.72 GB | about 461 s | – | about 5.9 MB/s; from file mtimes, because `time` output was lost in the background run |
| 2026-10-29 | casacore, `build_luno_ms.py` (real DATA) | 192 rows × 2048 ch | 4.4 s | 32 MB | |
| 2026-10-29 | QuartiCal 0.2.7, real 1934−638 solve, 50 iter | 4-station MS | 27.5 s (28.7 s with container) | – | 24.6 s graph execution against 23.9 s for the trivial dry run, so JIT dominates and the solve itself costs about 1 s |
| 2026-10-29 | `survey_luno_solved.py` | 117,556 cells | 0.79 s | 97 MB | host |
| 2026-10-29 | pytest full suite, repeated | repo | 175 s | – | against 986 s earlier the same day; load-dependent |
| 2026-10-29 | `run-injections.sh` (QuartiCal 0.2.7 trials) | prepared SKA fixture | 296 s | – | archived; 400 s on the previous Mac host |
| 2026-10-29 | CARACAL native strategies | fixture | 1265 s | – | archived |
| 2026-10-29 | response stage | fixture | 96 s | – | archived |
| 2026-10-29 | concurrent suite | fixture | 445 s | – | archived |
| 2026-10-29 | five-track `run-next.sh` campaign | fixture | 436 s | – | archived |
| 2026-10-29 | feasibility: `docker run` + `python -c pass`, `rang-flagging:local` | – | 0.54 s | 32 MB (client) | container start-up alone; [feasibility study](stack-consolidation-feasibility.md) |
| 2026-10-29 | feasibility: `import quartical.executor` in the container | – | 2.4 s (3.25 s with container) | 322 MB | per-solve import cost |
| 2026-10-29 | feasibility: numcodecs Blosc decode of LUNO DATA tiles 8–23 | 2,717,394,612 B compressed → 3,276,800,000 B decoded → 12,582,912 B kept | 2.3 s (process 2.5 s; user 1.0 s, sys 3.5 s) | 615 MB | 192 of 50,000 rows per tile kept: 260× overdecode |
| 2026-10-29 | feasibility: `build_luno_ms.py` real DATA (repeat) | same slice → 38,257,794 B MS | 4.1 s (user 2.3 s, sys 6.1 s) | 467 MB | `outputs/stack-feasibility-20261029-01/work.ms` |
| 2026-10-29 | feasibility: python-casacore `getcol` of the solver columns | 33,037,824 B | 0.02 s | 86 MB | DATA, MODEL_DATA, FLAG, WEIGHT_SPECTRUM, row columns |
| 2026-10-29 | feasibility: `solve_luno.py`, cold Numba cache (`/tmp` tmpfs) | 4-station MS | 28.3 s subprocess (25.2 s graph); 29.1 s with wrapper | 633 MB | gains hash `57809b86…`, equal to the archived run |
| 2026-10-29 | feasibility: `solve_luno.py`, first run with a bind-mounted cache | same | 27.2 s (24.3 s graph) | 633 MB | populates 3,876,574 B of cache |
| 2026-10-29 | feasibility: `solve_luno.py`, warm cache, two repeats | same | 3.56 s and 3.66 s subprocess (1.02 s graph) | 382 MB | gains hash `769a69b1…`; differ from cold by ≤1.1e-16 absolute, ≤2.0e-14 relative; gain flags identical |
| 2026-10-29 | feasibility: `survey_luno_solved.py`, cold-cache and warm-cache gains | 117,556 cells | 1.78 s and 1.50 s | 98 MB | identical 389/43 classification for both |
| 2026-10-29 | core phase 1: `validate_core_phase1.py`, frozen run `-01` (fixture + LUNO) | 140×4096×4 and 192×2048×4 cubes | 1.31 s (user 1.86 s, sys 0.29 s) | 391 MB | whole script with NumPy oracles; [protocol](core-phase1.md) |
| 2026-10-29 | core phase 1: fused Rust pass, fixture, in-process | 140×4096×4 | 0.058 s | – | replaces the NumPy residual and split-MSE path, 0.194 s in the same process; reported, not an end-to-end speedup |
| 2026-10-29 | core phase 1: fused Rust pass, LUNO, in-process | 192×2048×4 | 0.056 s | – | antenna-diagonal normals; the existing full-normal kernel with its NumPy preparation took 0.168 s |
| 2026-10-29 | core phase 1: `validate_core_phase1.py`, rerun `-02` with criterion 4b | same inputs | 1.08 s (user 1.74 s, sys 0.22 s) | 391 MB | fused pass 0.057 s fixture, 0.046 s LUNO in-process |
| 2026-10-29 | core phase 2: `validate_core_phase2.py`, frozen run `-01` | fixture + LUNO | 5.09 s (user 7.25 s, sys 0.78 s) | 187 MB | whole validator, including QuartiCal-gain comparisons and the in-memory rank survey |
| 2026-10-29 | core phase 2: Rust `complex` solve, LUNO, 50 iterations | 192×2048×4 | 0.77 s | – | in-process; QuartiCal 28.3 s cold / 3.6 s warm on the same MS |
| 2026-10-29 | core phase 2: load arrays + Rust solve + fused pass, LUNO | 33 MB arrays.npz | 0.94 s | 96 MB | `/usr/bin/time` on the cost subprocess |
| 2026-10-29 | core phase 2: Rust `complex` solve, fixture, 50 iterations | 140×4096×4 | 0.49 s | – | archived QuartiCal subprocess 29.4 s |
| 2026-10-29 | `export_ms_arrays.py` in `rang-flagging:local`, LUNO work.ms (repeat, `-02`) | 8 columns | 0.73 s with container | – | 33,035,408 B arrays.npz; SHA256 `8b221f7b…` equal to the first export |
