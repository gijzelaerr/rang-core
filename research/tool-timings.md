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
| 2026-10-29 | core phase 3: injection campaign on the Rust core, frozen run `-01` | prepared fixture, 49 solves | 25.9 s (user 25.5 s, sys 1.0 s) | 708 MB | one process, no MS or container; host reproduction 296 s |
| 2026-10-29 | core phase 3: injection campaign on the Rust core, post-hoc run `-02` | same | 24.6 s (user 24.5 s, sys 1.0 s) | 738 MB | |
| 2026-10-29 | core phase 3b: prospective track on the Rust core | five-track prepared inputs, 54 solves | 32.8 s (user 33.2 s, sys 0.4 s) | 548 MB | one process; the reproduced track took 6 min 23 s inside the 435 s campaign |
| 2026-10-29 | core phase 3: actions stage on the Rust core | prepared fixture, 17 solves | 9.2 s (user 10.0 s, sys 0.2 s) | 234 MB | one process; host reproduction about 6 min |
| 2026-10-29 | core phase 3 trend chain test: mirror build, seven core baseline solves | concurrent suite states | 14.5 s | 196 MB | `build_core_trend_mirror.py` |
| 2026-10-29 | frozen `flagging_trend.run` on the core mirror (host venv) | seven baselines × four patterns | 31.3 s | 355 MB | unedited consumer |
| 2026-10-29 | core phase 3c-a: africanus oracle in `rang-flagging:local` | 84 rows × 2048 channels, three sets | 21.9 s with container | 32 MB (client) | catalogue 8.1 s per call |
| 2026-10-29 | core phase 3c-a: Rust component predictor, 5153-component catalogue | 84 × 2048 | 8.3 s | – | single-threaded, bit-identical to africanus |
| 2026-10-29 | core phase 3c-a: validator rerun `-02` | three sets + NumPy oracles | 11.3 s | 1853 MB | NumPy catalogue oracle on three rows dominates memory |
| 2026-10-29 | core phase 3c-b: UVW export of the two signal cases in `rang-flagging:local` | 140 rows each | 0.47 s each with container | – | both arrays.npz SHA256 `6e8e7e6c…` |
| 2026-10-29 | core phase 3c-b: signal track on the Rust core | two seeds, 9 solves | 34.5 s (user 38.1 s, sys 0.6 s) | 817 MB | one process; reproduced track 2 min 39 s inside the campaign |
| 2026-10-29 | core section 6: numcodecs chunk oracle in `rang-flagging:local` | 68 chunks | 10.7 s with container (decode 1.48 s) | – | c-blosc 1.21.6 |
| 2026-10-29 | core section 6 prototype, run `-01` (zarr → solve → survey) | LUNO slice | 9.26 s process; pass 3.70 s, 2.86 s excluding decode | 299 MB | criterion 8 failed |
| 2026-10-29 | core section 6 prototype, run `-02` | LUNO slice | 5.18 s process; pass 2.96 s, 1.67 s excluding decode | 140 MB | all eleven criteria pass |
| 2026-10-29 | core section 6 checker, runs `-01` and `-02` | reruns the pass with oracles | 23.0 s | – | untimed rerun plus 68 full chunk decodes |
| 2026-10-29 | core task G: curl probe: HEAD, 16-byte ranged GET, two-range GET | `FLAG/0.8.0` | 0.32 s, 0.21 s, (not timed) | – | see precondition |
| 2026-10-29 | core task G: `python3 -m venv` | worktree | 0.04 s, failed | – | no `ensurepip` on this Ubuntu; recreated with `uv venv` |
| 2026-10-29 | core task G: `uv venv` + `uv pip install -e .[pointing,beam,test] ruff` | public PyPI | 23.3 s | – |  |
| 2026-10-29 | core task G: `cargo +1.93 build --release` (core, 4 jobs) | `core/` | 2.4 s | – | warm cache |
| 2026-10-29 | core task G: run planning from archived tiles (Python, no network) | 64 tiles | about 3 s | – | 2048 runs, 751,619,313 B |
| 2026-10-29 | core task G: pytest, `test_core_fetch.py` + `test_core_zarr.py` | local HTTP server | 1.1–8.4 s | – | the 8.4 s run included retry backoff on a wrong test store |
| 2026-10-29 | core task G: `fetch_luno_slice.py`, 8 workers, run `-01` | 2,124 requests, 751,848,436 B | 74.5 s fetch; 75.3 s process (user 4.3 s, sys 2.9 s) | – | 817 MB peak RSS (see above) |
| 2026-10-29 | core task G: `check_core_fetch.py` | run `-01` against 4.87 GB of archived tiles | 3.0 s | – | streams only the needed spans |
| 2026-10-29 | core task G: `bash tools/check-all.sh` (4 cargo jobs) | repo, 671 tests | 1531 s (pytest 1517 s) | – | PASS; host load average 58–72 on 16 cores from the eight wave 1 sessions |
| 2026-10-29 | core task H: `uv venv` + `uv pip install -e '.[pointing,beam,test]' ruff` (public PyPI) | – | 26.0 s | 69 MB | `python3 -m venv` fails on WSL (no `ensurepip`); uv chose its managed Python 3.13 |
| 2026-10-29 | core task H: `uv pip install stimela==2.1.4` | – | 3.8 s | – | pulls omegaconf 2.4.0; no QuartiCal |
| 2026-10-29 | core task H: `cargo +1.93 build --release` core crate, `CARGO_BUILD_JOBS=4` | – | 1.8 s | 193 MB | shared cargo cache warm |
| 2026-10-29 | core task H: `cargo +1.93 build --release` root crate | – | 2.0 s | 194 MB |  |
| 2026-10-29 | core task H: five phase 3 comparators, host versus archive (precondition) | – | 0.02–0.03 s each | 17 MB | `outputs/core-h-20261029-01-precondition` |
| 2026-10-29 | core task H: ten phase 3 comparators, phase 3 core runs versus archive and host | – | 0.01–0.02 s each | 17 MB | same directory, `core3-*` |
| 2026-10-29 | core task H: `pytest tests/test_core_cli.py` (8 tests), three times while writing | – | 0.2 s | – |  |
| 2026-10-29 | core task H: Stimela `core-actions` | – | 9.3 s | 254 MB | first recipe run, passed first time |
| 2026-10-29 | core task H: Stimela `core-injections` | – | 27.4 s | 752 MB |  |
| 2026-10-29 | core task H: Stimela `core-trend` | – | 79.9 s | 355 MB | concurrent with the CLI batch |
| 2026-10-29 | core task H: Stimela `core-prospective`, failed YAML load, then rerun | – | 0.8 s; 51.9 s | 73 MB; 568 MB |  |
| 2026-10-29 | core task H: Stimela `core-signal`, failed YAML load, then rerun | – | 1.0 s; 56.7 s | 73 MB; 840 MB |  |
| 2026-10-29 | core task H: CLI actions, injections, trend-mirror, trend, prospective, signal | – | 8.4, 26.6, 18.5, 60.4, 50.8, 57.8 s | 245, 728, 215, 356, 564, 837 MB | concurrent with the Stimela batch |
| 2026-10-29 | core task H: 23 comparator runs through `core_cli compare` (archive, host, phase 3 oracles) | – | 0.1–0.3 s each | – | receipts beside the results |
| 2026-10-29 | core task H: `bash tools/check-all.sh` (cargo, clippy, fmt, ruff, 676 pytest tests) | – | 3042 s (pytest 3027 s) | 1999 MB | once, before the final commit; PASS, concurrent with sibling sessions |
| 2026-10-29 | core task A: `compare_imaging_reproduction.py`, archive vs WSL reproduction | two result JSONs | 0.12 s | 44 MB | 0 failures; precondition |
| 2026-10-29 | core task A: venv creation (`uv venv --seed` + README pip line) | public PyPI | 51 s | – | `python3 -m venv` fails on this host: no `ensurepip` for 3.14 |
| 2026-10-29 | core task A: `run_imaging_sensitivity.py` smoke, 2 jobs × 2 variants, in `rang-flagging-next-imaging:local` | archive checkpoints | 5.7 s with container | – | pixel digests equal the archive |
| 2026-10-29 | core task A: `run_imaging_sensitivity.py` frozen run `-01`, 19 variants × 15 jobs | archive checkpoints, two 58 MB MS copies | 552 s with container (20 s per variant at defaults; 12 s for 1 w-layer, 71 s for 256) | – (client 33 MB) | 285 inversions, 730 MB of FITS and receipts |
| 2026-10-29 | core task A: `cargo +1.93 build --offline --release` root and core, `CARGO_BUILD_JOBS=4` | fresh worktree | 4.4 s | – |  |
| 2026-10-29 | core task A: `pytest tests/test_imaging_sensitivity.py` | 11 tests | 0.06 s | – |  |
| 2026-10-29 | core task A: `bash tools/check-all.sh`, `CARGO_BUILD_JOBS=4` | whole tree | 53 min 13 s (pytest 679 passed in 3180 s) | – | overall PASS; run once, with seven sibling sessions sharing the 16 cores |
| 2026-10-30 | core task B: task B oracle: 21 WSClean 3.6-1 inversions with `-store-imaging-weights` in `rang-flagging-next-imaging:local` | 15 jobs + 2 repeats + 2 uniform + 2 natural, 84 × 2048 × 4 | 33.4 s in-container (34.2 s with `docker run`) | – | 1.3–1.8 s per WSClean call, 0.11–0.16 s per MS copy and checkpoint write, 0.04–0.24 s per export; first attempt failed at once because the flag followed the MS argument |
| 2026-10-30 | core task B: task B comparator, `--oracle-only` | 21 oracle runs | about 1 s | – | precondition, all identical |
| 2026-10-30 | core task B: task B comparator, full (19 core jobs + oracles) | same | 3.4 s process including a 2.0 s core rebuild | – |  |
| 2026-10-30 | core task B: core Stokes I formation, in-process | 140 × 2048 × 4 | 1.5–2.3 ms (5.9 ms once) | – | first call 2.0 s includes the ctypes library load |
| 2026-10-30 | core task B: core imaging weights (grid, Briggs finish, rank filter, lookup), in-process | 84 rows × 2048 channels on 616 × 308 | 4.7–9.2 ms | – | WSClean's "Precalculating weights" is not separately timed in its log |
| 2026-10-30 | core task B: `cargo test` (core, weights filter) and `pytest tests/test_core_weights.py` | 7 + 6 tests | 0.9 s and 2.0 s | – |  |
| 2026-10-30 | core task B: `bash tools/check-all.sh` | repo (674 pytest tests, 25 core and 19 root Rust tests) | 3046 s (pytest 3028 s) | – | overall PASS, once before the final commit; pytest slow because eight sibling sessions shared the 16 cores |
| 2026-10-29 | core task C: `uv pip install` of the venv extras | – | 19.4 s | – |  |
| 2026-10-29 | core task C: `cargo +1.93 build --release` of `core/` before the port | – | 1.3 s | – |  |
| 2026-10-29 | core task C: Oracle: fifteen WSClean runs in the container | – | 23.6 s | – |  |
| 2026-10-29 | core task C: WSClean diagnostic variants (three runs, one job) | – | about 6 s | – |  |
| 2026-10-29 | core task C: Core run `-02`, fifteen jobs (gridding only) | – | 62.0 s | – |  |
| 2026-10-29 | core task C: Core run `-03`, fifteen jobs (wall) | – | 659.6 s | – |  |
| 2026-10-29 | core task C: Core run `-04`, fifteen jobs (wall) | – | 420.6 s | – |  |
| 2026-10-29 | core task C: Core run `-05`, fifteen jobs (wall) | – | 467.8 s | – |  |
| 2026-10-29 | core task C: `compare_core_gridder.py`, 30 images | – | 2.4 s | – |  |
| 2026-10-29 | core task C: `cargo test` of the gridder (5 tests) | – | under 0.1 after a 3 s build s | – |  |
| 2026-10-29 | core task C: `pytest tests/test_core_grid.py` (4 tests) | – | 3.4–9.3 s | – |  |
| 2026-10-29 | core task C: `bash tools/check-all.sh` | – | 1978 (pytest 1943, 672 tests, PASS) s | – |  |
| 2026-10-29 | core task D: PyPI JSON for tricolour 0.2.1 and crystalball 0.4.3 | 2 requests | 1.0 s | – |  |
| 2026-10-29 | core task D: curl sdist + wheel of tricolour 0.2.1, extract | 2 files | 1.7 s | – | hashes equal PyPI |
| 2026-10-29 | core task D: `uv venv` + `uv pip install -e .[pointing,beam,test] ruff` | worktree | 2 s | – | cached wheels; `python3 -m venv` fails on this host (no `ensurepip` for Python 3.14), so `uv venv` was used with the same public index |
| 2026-10-29 | core task D: `cargo +1.93 build --release` core and root | worktree | 2 s + 1 s | – |  |
| 2026-10-29 | core task D: `docker run` + python-casacore facts script in `rang-flagging-parallel:local` | 4 diagnostic MSs | 2.0 s | – |  |
| 2026-10-29 | core task D: `compare_core_flags.py archive-host` | 2 JSON + 8 npz | 0.22 s | – | pass |
| 2026-10-29 | core task D: oracle step, `oracle_tricolour.py` in the container | 4 controls | 123.9 s (121.2 s in Python) | – | control 0: 116.5 s, of which Numba compilation of `sum_threshold_flagger` 74.9 s at step 2 and 39.2 s again at step 8 (the narrow step passes `spike_width_time: 2`, an int, so Numba specialises a second time); controls 1–3 warm: 2.2 s, 1.2 s, 1.3 s |
| 2026-10-29 | core task D: port run `-01` (`run_core_flags.py`) | 4 controls | 40.8 s | – | failed criteria 1–3 |
| 2026-10-29 | core task D: port run `-02` | 4 controls | 60.9 s (19.0, 17.4, 11.3, 10.5 s) | – | pass; load 68 |
| 2026-10-29 | core task D: port run `-03` after speedups | 4 controls | 50.7 s (12.7, 15.5, 10.8, 9.0 s) | – | pass; load 59–65 |
| 2026-10-29 | core task D: `compare_core_flags.py run` | 3 runs | 1.9 s each | – |  |
| 2026-10-29 | core task D: port, control 0 first-pass strategy, CPU | 140 rows × 4096 ch | 4.16 s CPU (18.4 s wall) | – | step 2 `sum_threshold` 2.40 s CPU, `uvcontsub` steps 0.13 s and 0.17 s CPU |
| 2026-10-29 | core task D: Tricolour 0.2.1 warm kernels, same inputs, in the container | same | step 2: 1.19 s CPU; `uvcontsub` step 3: 0.11 s CPU | – | first call of step 2: 73.9 s CPU (JIT) |
| 2026-10-29 | core task D: `tools/check-all.sh` (pytest 677 tests) | repo | 2119 s (pytest 2092 s) | – | PASS; load 60–74, against 175–986 s for the suite on a quiet host |
| 2026-10-29 | core task E: `uv venv` + `uv pip install -e '.[pointing,beam,test]' ruff` (README's `python -m venv` fails: no `ensurepip` on this Python 3.14) | worktree | 0.5 s | – | cached wheels |
| 2026-10-29 | core task E: `cargo +1.93 build --release` core crate, `CARGO_BUILD_JOBS=4` | `core/` | 2.6 s | – | before any task E code |
| 2026-10-29 | core task E: `git clone --depth 1 --branch v3.8.1 casacore` | 43 MB | 4.5 s | – | format reference |
| 2026-10-29 | core task E: python-casacore `getdminfo` inventory in `rang-flagging:local` | 2 MSs, 6 tables each | 0.73 s | – | container included |
| 2026-10-29 | core task E: `oracle_ms_columns.py` in `rang-flagging:local`, run `-01` | 3 MSs, 15 tables, 103 columns | 1.16 s | – | container included; `getcol` of the 140 × 4096 × 4 DATA 27 ms, of LUNO DATA 8 ms |
| 2026-10-29 | core task E: same, run `-02` | same | 1.22 s | – | byte-identical dumps |
| 2026-10-29 | core task E: `check_ms_reader.py --self-check` | the two dumps | 0.61 s | – | precondition passes |
| 2026-10-29 | core task E: `cargo +1.93 test` of `ms::` unit tests and the fixture smoke test | `core/` | 4.8 s build + 0.3 s | – |  |
| 2026-10-29 | core task E: `pytest tests/test_core_ms.py` (4 tests, includes a core rebuild) | fixture, LUNO | 10 s | – |  |
| 2026-10-29 | core task E: `check_ms_reader.py` run `-02` | 173 columns, 414 reads | 3.2 s | – | peak RSS 165 MB |
| 2026-10-29 | core task E: `check_ms_reader.py` run `-03` | same | 2.8 s | – | peak RSS 161 MB |
| 2026-10-29 | core task E: `bash tools/check-all.sh` (with the two `lib.rs` lines present) | repo | 51.6 min | – | PASS; pytest 672 passed in 3,070 s while seven sibling sessions shared the 16 cores (175–986 s earlier on a quiet host) |
| 2026-10-29 | core task F: `uv venv` + `uv pip install -e .[pointing,beam,test] ruff numcodecs` (public PyPI) | – | 20.7 s | – | numpy 2.5.4 (archive 2.5.3), numcodecs 0.17.1 |
| 2026-10-29 | core task F: `cargo +1.93 build --release` of `core/` (warm cache) | – | 1.9 s | – | `CARGO_BUILD_JOBS=4` |
| 2026-10-29 | core task F: venv recreated on `/usr/bin/python3.14` (`uv venv -p`, same packages) | – | 1.4 s | – | uv cache warm; first venv had picked uv's 3.13 |
| 2026-10-29 | core task F: `examples/bench_core_f.py baseline outputs/core-f-20261029-01` | – | 48.0 s | – | solve 7.3 s, blosc 34.7 s, survey 5.9 s; load 0.8–0.9 |
| 2026-10-29 | core task F: perf record of solve (5 solves), blosc (16 tiles × 2), survey (3 passes) | – | 3.6 s, 5.5 s, 3.3 s | – | debug-symbol builds in `~/Build/tmp/20261029-rang-core-f` |
| 2026-10-29 | core task F: `cargo +1.93 build --release` of `core/` after each kernel change | – | 0.9–1.4 s | – |  |
| 2026-10-29 | core task F: `bench_core_f.py check … --target solve`, runs `-02`, `-03` | – | 6.6 s, about 12 s | – | load 15 and 20–23; all solver checks pass |
| 2026-10-29 | core task F: `bench_core_f.py check … --target blosc`, runs `-04`, `-05` | – | 93.7 s, about 120 s | – | load 45 and 57; all blosc checks pass |
| 2026-10-29 | core task F: paired `perf stat` old/new, 2 rounds × (5 solves + 48 tile decodes) | – | about 190 s | – | load 52–60; counts in the table above |
| 2026-10-29 | core task F: LAPACK `eigh` timing for the survey note | – | 10 s | – | 5 repeats, `OPENBLAS_NUM_THREADS=1` |
| 2026-10-29 | core task F: `bench_core_f.py check outputs/core-f-20261029-06 …` (all targets, final library) | – | 183 s | – | load about 55; all eight equality checks pass; timings not usable |
| 2026-10-29 | core task F: `bash tools/check-all.sh` (once, before the final commit) | – | 51 min 32 s (user 158 min) | – | PASS: root 19 tests, core 20 tests, clippy, fmt, ruff, 668 pytest; load 55–75 (siblings' suites running) |
| 2026-10-29 | core task F: `bench_core_f.py check outputs/core-f-20261029-07 …` (all targets, final library, quiet load 1.4–1.8) | – | 34.5 s | – | all checks pass; the wall table above; results-only commit followed, no code change |
| 2026-10-29 | core task I: `uv venv -p /usr/bin/python3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff` (public PyPI) | – | 1.6 s | – | uv cache warm from wave 1 |
| 2026-10-29 | core task I: `cargo +1.93 build --release` core and root crates, `CARGO_BUILD_JOBS=8` | – | 3.8 s | – |  |
| 2026-10-29 | core task I: `uv pip install stimela==2.1.4` | – | 2.9 s | – | for criterion 9 |
| 2026-10-29 | core task I: input probe: core MS reads of both backups, task C export check, one job's Briggs weights | – | 2.8 s (2.5 s first library load) | – | scratch, not committed |
| 2026-10-29 | core task I: `compare_core_imaging.py` archive vs host reproduction with 30 task C rerun images (precondition) | – | 0.59 s, then 0.27 s | 68 MB | first run found the unit-flux gap |
| 2026-10-29 | core task I: `pytest tests/test_core_imaging.py` (8 tests), four times while writing; `tests/test_core_cli.py` (8) once | – | 0.1–0.5 s | – |  |
| 2026-10-29 | core task I: one-job smoke (`omitted-total`) through `image_job`, scratch script | – | 4.3 s | 119 MB | labelled smoke; FITS deleted |
| 2026-10-29 | core task I: **frozen run `-01`**, `examples/run_core_imaging.py` (15 jobs, both comparisons) | – | 61.9 s | 213 MB | gridding 3.96–4.09 s per job (60.6 s), Stokes I + weights 6 ms per job, FITS 10 ms, MS reads 0.04 s each; comparators 0.3 s and 0.1 s |
| 2026-10-29 | core task I: Stimela `core-imaging`, Python 3.14 venv (failed load of the native backend) | – | 1.2 s | 93 MB | `outputs/core-i-20261029-02-stimela`, logs only |
| 2026-10-29 | core task I: direct CLI run `-03` + two `compare` subcommands | – | 60.5 s + 0.27 s + 0.08 s | 222 MB | criterion 9 |
| 2026-10-29 | core task I: `uv venv -p 3.13 .venv313` + extras + `stimela==2.1.4` | – | 1.9 s | – | environment step for criterion 9; not committed, deleted after the run |
| 2026-10-29 | core task I: Stimela `core-imaging` run `-04`, Python 3.13 venv, + host comparison | – | 62.7 s + 0.07 s | 221 MB | `image` cab 60.7 s; Stimela overhead 1.5 s |
| 2026-10-29 | core task I: `examples/archive_core_imaging.py` (three runs) | – | 0.09 s | – |  |
| 2026-10-29 | core task I: `bash tools/check-all.sh`, `CARGO_BUILD_JOBS=8` | – | 216 s (pytest 721 passed in 208 s) | 1.76 GB | once before the final commit; overall PASS, machine otherwise idle |
| 2026-10-29 | core task J: `uv venv -p /usr/bin/python3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` (public PyPI) | – | 3.9 s | – | uv cache warm; numpy 2.5.4, maturin 1.16.0 |
| 2026-10-29 | core task J: `cargo +1.93 build --release` core and root crates, `CARGO_BUILD_JOBS=8` | – | 2.6 s + 1.0 s | – | before any task J code |
| 2026-10-29 | core task J: `cargo +1.93 fetch` of the `core/py` skeleton (pyo3 0.30.1, numpy 0.30.0 and 22 dependencies) | – | 3.3 s | – | the only network use of the crate build |
| 2026-10-29 | core task J: precondition suite on ctypes, `tools/core-j-suite.sh outputs/core-j-20261029-00-ctypes` (the table above) | – | about 150 s | 637 MB (checker) | load 0.7–2.9; section 6 cold-cache cost failure, warm repeat 4.5 s + 18.2 s; task I repeat 52.7 s |
| 2026-10-29 | core task J: first `cargo +1.93 build --offline --release` of `core/py` (cold, after the freeze) | – | 7.5 s | – | compiled first time; clippy and fmt clean after one type alias |
| 2026-10-29 | core task J: `uv pip install -e '.[pointing,beam,test,imaging]'` through the maturin backend (public PyPI, crates.io) | – | 4.3 s | – | warm cargo target; writes `python/rangtoy/_core.abi3.so` and `rangtoy.pth` |
| 2026-10-29 | core task J: `pytest` of the eight core test modules (38 tests) under `RANG_CORE_BACKEND=extension` and `=ctypes` | – | 1.6 s, 1.4 s | – | all pass on both |
| 2026-10-29 | core task J: `pytest tests/test_core_backends.py` (11 tests), several times while writing | – | 0.35 s | – | one abort found on the way: `rang_core_grid_kernel(7, 2)` panics with no `catch_unwind` (either backend); the test now uses WSClean's settings |
| 2026-10-29 | core task J: `maturin develop --release --offline` warm | – | 0.46 s | – | the `ext-build` step of check-all |
| 2026-10-29 | core task J: extension suite, `RANG_CORE_BACKEND=extension tools/core-j-suite.sh outputs/core-j-20261029-02-extension` (the table above) | – | about 145 s | 437 MB (checker) | load about 1; section 6 cold-cache cost failure as in the precondition; warm repeat 4.5 s + 11.7 s |
| 2026-10-29 | core task J: `examples/compare_core_backends.py` ctypes versus extension (three comparisons) | – | 0.5 s each | – | 94 + 34 + 3 files, zero differences |
| 2026-10-29 | core task J: `bench_boundary.py` under each backend, two repeats | – | 0.14–0.17 s per process | 40 MB | the cost table above |
| 2026-10-29 | core task J: `maturin develop --release --offline` cold (`core/py/target` removed) and `maturin build --release` wheel | – | 7.45 s, 0.14 s | – | wheel 800 KB |
| 2026-10-29 | core task J: `bash tools/check-all.sh`, `CARGO_BUILD_JOBS=8`, first run | – | 245 s (user 3,085 s) | 1.78 GB | every step PASS and `overall: PASS`, but pytest `1 failed, 731 passed in 234 s` (the `core_cli` environment test, masked by the pipeline; see the post-hoc note) |
| 2026-10-29 | core task J: `pytest tests/test_core.py tests/test_core_cli.py tests/test_core_backends.py` after the fix | – | 0.5 s | – | 27 passed, `_core` imported first |
| 2026-10-29 | core task J: `bash tools/check-all.sh`, second run on the final code | – | 80 s (user 574 s) | 1.71 GB | overall PASS: root 19 and core 47 Rust tests, clippy, fmt, `ext-build` 0.5 s, `ext-clippy`, `ext-fmt`, ruff, 732 pytest passed in 73 s; host idle |
| 2026-10-30 | core task K: `uv venv -p /usr/bin/python3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` (public PyPI, maturin backend builds `rangtoy._core`) | – | 9.0 s | – | uv cache warm |
| 2026-10-30 | core task K: `cargo +1.93 build --release` core and root, `CARGO_BUILD_JOBS=8` | – | 3.3 s | – |  |
| 2026-10-30 | core task K: `pytest tests/test_core_campaign.py` (7 tests), three times while writing | – | 0.1–1.5 s | – | the first run failed on `cargo` missing from `PATH` (the root crate's TV kernel builds on demand); passes with `~/.cargo/bin` on `PATH` as check-all sets it |
| 2026-10-30 | core task K: labelled smoke of the chain on the archived local objects, no network (`outputs/core-k-20261030-00-smoke`, scratch script) | – | 13.2 s | 391 MB | found the UVW chunk key (`0.0`, not `0`) and a `protected_flags` broadcast shape; both fixed before the freeze of the code commit `50cb137`; one Tricolour arm, one TV loop, two images |
| 2026-10-30 | core task K: **precondition**, `examples/precondition_luno_campaign.py` (`outputs/core-k-20261030-00-precondition`) | – | 3.6 s | 147 MB | all eight checks pass |
| 2026-10-30 | core task K: **frozen run `-01`**, `examples/run_luno_campaign.py` under `/usr/bin/time -v` (`outputs/core-k-20261030-01`), started 04:09:05 UTC, load 0.7 | – | 110.4 s (107.5 s inside Python) | 461 MB | fetch 75.7 s of it; stage times below |
| 2026-10-30 | core task K: `examples/check_luno_campaign.py`, first call | – | 0.6 s | 54 MB | **failed in the checker, not the run**: the checker looked for `MAIN/MAIN_1/UVW/.zarray` in the support slice; post-hoc fix of the archive-path lookup (checker only; the run's bytes and results are untouched) |
| 2026-10-30 | core task K: `examples/check_luno_campaign.py`, after the fix (`outputs/core-k-check-20261030-01`) | – | 1.3 s | 121 MB | criteria 1–7 pass |
| 2026-10-30 | core task K: `examples/archive_luno_campaign.py` | – | 0.1 s | – | 43 KB archive |
| 2026-10-30 | core task K: `bash tools/check-all.sh`, once before the final commit (`outputs/core-k-20261030-01.check-all.log`) | – | 96.6 s (pytest 739 passed in 74.3 s) | 1.68 GB | overall PASS; machine otherwise idle |
| 2026-10-30 | core task K stage: fetch (2,124 ranged/whole requests + 17 extra objects) | run `outputs/core-k-20261030-01` | 75.7 s (74.2 s for the slice, 1.5 s for the extras) | 75 MB | task G 74.5 s, 751.8 MB; whole tiles 679 s |
| 2026-10-30 | core task K stage: decode (2048 blocks, 751.6 MB, Rust) | run `outputs/core-k-20261030-01` | 0.36 s | 110 MB | task G 0.74 s |
| 2026-10-30 | core task K stage: section 6 reference pass | run `outputs/core-k-20261030-01` | 1.23 s | 172 MB | section 6 1.67 s |
| 2026-10-30 | core task K stage: split (seed 7) | run `outputs/core-k-20261030-01` | 0.04 s | 172 MB |  |
| 2026-10-30 | core task K stage: solve `original` | run `outputs/core-k-20261030-01` | 0.32 s | 172 MB | QuartiCal 27.5 s cold / about 3 s warm; section 6 0.62 s |
| 2026-10-30 | core task K stage: Tricolour first-pass port (12 steps) | run `outputs/core-k-20261030-01` | 1.55 s | 172 MB | task D 4.16 s CPU on 140 × 4096; Tricolour 1.19 s warm + 74 s JIT |
| 2026-10-30 | core task K stage: Tricolour mild port (10 steps) | run `outputs/core-k-20261030-01` | 0.89 s | 182 MB |  |
| 2026-10-30 | core task K stage: TV loop (scores, TV, 6 distinct candidate solves) | run `outputs/core-k-20261030-01` | 1.68 s | 293 MB |  |
| 2026-10-30 | core task K stage: TV loop on the first-pass arm | run `outputs/core-k-20261030-01` | 1.67 s | 323 MB |  |
| 2026-10-30 | core task K stage: each inversion (six arms) | run `outputs/core-k-20261030-01` | 3.87–3.96 s | 461 MB | task I 3.96–4.09 s; WSClean 1.4–1.7 s |
