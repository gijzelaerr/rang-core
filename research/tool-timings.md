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
| 2026-10-30 | big plan U1: uv venvs for quartical 0.2.7, tricolour 0.2.1, dask-ms 0.2.32 (Python 3.13/3.12) | 3 venvs | 155.8 s | – |  |
| 2026-10-30 | big plan U1: `goquartical` 0.2.7, cold cache | scan 9, G complex 2×32, 50 iterations | 29.3 s | – | execute graph 25.49 s |
| 2026-10-30 | big plan U1: `goquartical` 0.2.7, warm cache | same | 4.0 s | – | graph 1.65 s; cache 4.3 MB |
| 2026-10-30 | big plan U1: Tricolour 0.2.1 `sum_threshold_flagger`, cold cache | 1×1×64×256 window | 79.7 s | – | compiles 50.8 s (float) + 28.2 s (int) |
| 2026-10-30 | big plan U1: same, warm cache | same | 0.71 s | – |  |
| 2026-10-30 | big plan U1: Tricolour `uvcontsub_flagger` scaling | 32–256 baselines × 20 × 1024 | 1.36 s | – | quadratic in baselines per window |
| 2026-10-30 | big plan U1: dask `ProgressBar(dt=300)`, non-TTY | 1 s task | 300.0 s | – | Tricolour #110 |
| 2026-10-30 | big plan U1: QuartiCal element-kernel JHJ check | synthetic | 3.3 s and 1.4 s | – | two script versions; QuartiCal #452 |
| 2026-10-30 | big plan U1: `dask-ms convert` to zarr | scan 9 | 2.2 s | – |  |
| 2026-10-30 | big plan U1: `uv venv` + editable install (Python 3.14) | worktree | 9 s | – |  |
| 2026-10-30 | big plan U1: `tools/check-all.sh` | repo, 739 tests | 578 s | – | PASS; pytest 554 s under concurrent load |
| 2026-10-30 | big plan U1: `tools/check-all.sh` | repo, 739 tests | 1105 s | – | PASS; pytest 1090 s, four agents sharing the cores |
| 2026-10-30 | big plan S1: `cargo +1.93 build --release --offline` root and `core/`, `maturin develop --release --offline` | worktree (existing `.venv`, Python 3.14) | 0.06 s, 0.01 s, 0.45 s | 37 MB | already up to date |
| 2026-10-30 | big plan S1: `uv pip install numcodecs` and later `coverage` (public PyPI) | `.venv` | not timed | – | numcodecs 0.17.1 for `bench_core_f.py`; coverage 7.17.0 |
| 2026-10-30 | big plan S1: `inventory.py` | checkout at `df42ea0` | under 1 s | – | `inventory.json` |
| 2026-10-30 | big plan S1: labelled smoke of the offline K replay (`outputs/simplification-review-20261030-00-smoke`) | archived K fetch | 19.65 s | 430 MB | included 3.2 s of recompilation by the `stable` toolchain; gains and images hash-equal |
| 2026-10-30 | big plan S1: timed suite `suite.sh` (`-01`), 29 steps | archived inputs of every chain | 377 s in all | 827 MB (task F bench) | load 0.4–4.6; every step exit 0; per-step table in section 2.2 |
| 2026-10-30 | big plan S1: py-spy and perf `pyspy.sh` (`-02`), 10 chains + SVG + 2 perf runs | as the suite | about 6 min | 838 MB | py-spy walls 1.9–73 s (profiler overhead included; not used as walls) |
| 2026-10-30 | big plan S1: probes `probes.sh` (`-03`): OpenBLAS A/B (10 runs), subsets (6), variant builds (3) and checks (7) | archived K fetch, F baseline | 272.5 s of runs + 18.0 s of builds (4.2, 6.9, 6.9 s) | 845 MB | load 13–20; walls noisy, hashes and counts not |
| 2026-10-30 | big plan S1: line-level perf attempt `perfline.sh` (`-04`) | K replay, debug-line build | about 25 s | – | addresses did not resolve to lines reliably; not used |
| 2026-10-30 | big plan S1: `convergence.py` (`-05`, then `-07` with gauge-invariant metrics) | archived K fetch | 11.3 s, 12.4 s | 182 MB | 22 solves each, 1–200 iterations |
| 2026-10-30 | big plan S1: `subset_iters.py` | archived K fetch | not timed (about 10 s) | – | `subset-iterations.jsonl` |
| 2026-10-30 | big plan S1: `perf stat` of the K replay, three builds × 2 | archived K fetch | about 100 s | 413 MB | load 16–19 |
| 2026-10-30 | big plan S1: `pytest -q --durations=0` (once) | 739 tests | 1,060 s | 1.82 GB | 7.7 threads busy; load 16–33 (siblings' check-all running); 739 passed |
| 2026-10-30 | big plan S1: coverage `coverage.sh` (`-06`), 12 chains under `coverage run` (sysmon) | as the suite | 4.4–59.7 s per chain, about 4.5 min | 838 MB | load 18–29 |
| 2026-10-30 | big plan S1: validators and comparators left out of the suite (`-08`): phase 1, phase 3c-a, task G fetch checker, backends comparator against task J, OpenBLAS A/B on the actions comparator (3 + 3) | archived inputs | 5.2 s, 29.0 s, 6.9 s, 1.5 s, 0.12–0.24 s each | 1.9 GB (3c-a) | load 27–30; outcomes in section 1.4 |
| 2026-10-30 | big plan S1: `bash tools/check-all.sh` (once, on commit `7090451`, the review and profiles) | branch | 1,139 s (pytest 739 passed in 1,118 s) | 1.71 GB | overall PASS (root 19 and core 47 Rust tests, clippy, fmt, ext build, ruff, diff-check, 739 pytest); load 18–31 (sibling sessions); log `outputs/simplification-review-20261030-09-check-all.log`; the follow-up commit that adds these rows and the fixups is document-only |
| 2026-10-30 | big plan W1: `docker pull quay.io/pypa/manylinux_2_28_x86_64` | – | 115.8 s | – | 1.75 GB image |
| 2026-10-30 | big plan W1: `uv python install 3.10 3.11 3.12 3.13 3.14` | – | 46.1 s | – | 3.13 already present |
| 2026-10-30 | big plan W1: `tools/wheel/build.sh` x86_64, cold (rustup download 23.5 s, wheel 10.8 s) | – | 43.4 s | 32 MB (host side) | `-01` |
| 2026-10-30 | big plan W1: `tools/wheel/build.sh` x86_64, warm caches (wheel 7.5–10.5 s, sdist 0.2 s, repair 0.7–1.1 s, C ABI 1.4–2.3 s, root lib 0.9 s, wheel from sdist 7.5–11.4 s) | – | 23.0–34.6 s | – | `-02`, `-03`, `-06`; load up to 17 |
| 2026-10-30 | big plan W1: `tools/wheel/build.sh` aarch64 by zig, failed (zig not found) and succeeded | – | 26.4 s, 23.2 s | – | `-08-aarch64` |
| 2026-10-30 | big plan W1: `tools/wheel/test.sh` 5 versions, archive suite on 3.10 and 3.14 | – | 138 s, 273 s, 475 s | 262 MB | `-04`, `-05`, `-07` (iterations) |
| 2026-10-30 | big plan W1: `SUITE_ALL=1 tools/wheel/test.sh` 5 versions, full archive suite on each | – | 1,585 s | 442 MB (section 6 checker) | `-09`; load 15–22; task C 79–185 s and task I 56–178 s per version against 52–54 s in task J on an idle host |
| 2026-10-30 | big plan W1: `tools/wheel/build.sh` x86_64 and aarch64 with the committed scripts and explicit `RUSTFLAGS` | – | 35.2 s, about 25 s | – | `-11`, `-11-aarch64`; same `.so` hashes as before |
| 2026-10-30 | big plan W1: `tools/wheel/test.sh` 5 versions, suite on 3.10 and 3.14, with the classifier | – | 435.4 s | 439 MB (section 6 checker) | `-12`; load 5–16; overall FAIL on section 6 cost only |
| 2026-10-30 | big plan W1: `uv venv` + editable install `.[pointing,beam,test,imaging] ruff maturin` (worktree `.venv`) | – | 24.3 s | – | for check-all |
| 2026-10-30 | big plan W1: `actionlint` (first `uv tool run`, includes download) | – | 4.9 s | – | 0 errors |
| 2026-10-30 | big plan W1: `bash tools/check-all.sh` before the second commit (classifier, `RUSTFLAGS`) | – | 387.9 s (user 4,662 s) | 1.69 GB | overall PASS, 739 pytest passed in 380 s; `outputs/wheel-20261030-13-check-all` |
| 2026-10-30 | big plan W1: `bash tools/check-all.sh`, `CARGO_BUILD_JOBS=8`, before the first commit (this file still being written) | – | 901.7 s (user 6,711 s) | 1.77 GB | overall PASS: root 19 and core 47 Rust tests, clippy, fmt, `ext-build`, ruff, 739 pytest passed in 860 s; load 16–27 from the siblings (80 s on an idle host in task J) |
| 2026-10-30 | big plan P8: `uv venv -p python3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin numcodecs` (public PyPI) | worktree | 23.3 s | – |  |
| 2026-10-30 | big plan P8: `maturin develop --release --offline` (Rust 1.93) | worktree | 24.1 s | 385 MB | first build of the extension in this worktree |
| 2026-10-30 | big plan P8: `manifest.sh before`, `move.sh` (`git mv`), `manifest.sh after` | 70 files | under 1 s each | – | hashes identical |
| 2026-10-30 | big plan P8: `extract.py`, `docs.py`, `pointer.py`, `wrap.py`, `ruff --fix`/`format` on 3 tests | tests, docs, 33 notes | under 1 s each | – |  |
| 2026-10-30 | big plan P8: `pytest` on the five edited or dependent test files | 53 tests | 2.5 s | 107 MB | 53 passed |
| 2026-10-30 | big plan P8: S1 suite `suite.sh` (`-01`), 29 steps | archived inputs of every chain | 613 s in all | 846 MB (F bench) | load 8–20; 28 exit 0, `section6-check` exit 1 (cost criterion) |
| 2026-10-30 | big plan P8: validators (`-02`): phase 1, phase 3c-a, task G fetch checker, backends comparator against S1's `-01` | archived inputs | 1.0 s, 11.4 s, 2.0 s, 4.3 s | 1.90 GB (3c-a) | load 12–17; verdicts above |
| 2026-10-30 | big plan P8: pre-move baseline (`-03`): worktree at `43dc3c7`, venv, extension and both crates built, then `core_cli prospective`, `signal` | archived inputs | build not timed (about 2 min); 20.5 s, 52.7 s | 836 MB | worktree removed afterwards |
| 2026-10-30 | big plan P8: `bash tools/check-all.sh` (once, on `8cb2665`) | branch | 689.5 s (pytest 555 passed in 663 s) | 1.72 GB | overall PASS; load 6–23 |
| 2026-10-30 | big plan P8: `section6`, `section6-check` re-run (`-05`) | archived inputs | 19.0 s, 16.5 s | 437 MB | load 14–20; `8_cost` fails again (7.88 s), all else passes |
| 2026-10-30 | big plan P8: post-hoc section 6 A/B (`-07` pre-first, `-08` post-first): pre-move worktree at `43dc3c7` rebuilt (venv, extension, both crates) twice, 3 + 3 alternating pairs | archived inputs | about 2 min build + about 4 min runs, each time | – | load 26–46; all 12 runs fail `8_cost` only; worktree removed both times |
| 2026-10-30 | big plan P3: `uv venv -p /usr/bin/python3.14 .venv` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` (public PyPI) | worktree | 0.02 s + 20.8 s | 377 MB | load 16–19 |
| 2026-10-30 | big plan P3: `cargo +1.93 build --release --offline` core / root, `maturin develop --release --offline` | `43dc3c7` | 17.9 s, 5.9 s, 17.9 s | 386 MB | load 22 |
| 2026-10-30 | big plan P3: bench smoke (`-00/smoke`, K only, 1 repeat, per-step) | K fetch | 10.8 s | 104 MB | additions equal the archive; layout check only |
| 2026-10-30 | big plan P3: `run_core_flags.py` (`-01/d-port`) | D oracle arrays | 8.74 s | 98 MB | load 3.0 |
| 2026-10-30 | big plan P3: `compare_core_flags.py run` (`-01/d-compare`) | `-01/d-port` | 0.34 s | 65 MB | pass, criteria 1–5 |
| 2026-10-30 | big plan P3: `bench_p3_flags.py run --per-step` (`-01/bench-ext`) | D + K | 73.1 s | 127 MB | load 2.8–4.1; extension |
| 2026-10-30 | big plan P3: `bench_p3_flags.py run` with `RANG_CORE_LIB` (`-01/bench-ctypes`) | D + K | 52.0 s | 125 MB | load 4.1–14.1; a ctypes library rebuilt by the default toolchain; slower per CPU-s than the extension under that load, not used further |
| 2026-10-30 | big plan P3: development builds, unit tests, clippy and smokes (`-02`, post-hoc development, not results) | worktree | `cargo build` 10–18 s each, `maturin develop` 12–18 s, module tests 0.15 s, smoke benches 7–30 s, three `perf record` runs about 30 s each | 186 MB (bench) | load 15–21; every smoke identical to `-01` |
| 2026-10-30 | big plan P3: targeted pytest `tests/test_p3_flags.py tests/test_core_flag.py` | worktree | 4.2 s (3.5 s in pytest) | 167 MB | 12 passed |
| 2026-10-30 | big plan P3: `measure.sh` (`-03`, frozen): bench at 1, 2, 4, 8, 16 threads | D + K | 30.5, 7.4, 4.9, 3.8, 12.1 s | 131–183 MB | load 6–10; per-step replay at 1 and 16 |
| 2026-10-30 | big plan P3: `run_core_flags.py` + `compare_core_flags.py run` at 1 and 16 threads (`-03`) | D oracle arrays | 4.92 + 0.46 s; 1.75 + 0.36 s | 102 / 148 MB | pass 5/5 both |
| 2026-10-30 | big plan P3: A/B at 16 threads (`-03`), new | D + K | 1.64–1.68 s each | 180 MB | the three old runs **failed** (0.1 s, exit 1): the shadow package of the old extension did not resolve `core_root()`; tooling, not a result |
| 2026-10-30 | big plan P3: probe ×16 at 1, 2, 4, 8, 16 threads (`-03`) | K ×16 + K | 64.9, 45.7, 34.0, 21.2, 20.5 s | 800–853 MB | load 6.6 → 24; old-build probe and both `compare` calls **failed** as above |
| 2026-10-30 | big plan P3: post-hoc `-04`: the same old runs with `core/` linked | D + K | old 0.14–1.1 s (exit 1), new 2.1–2.2 s | 309 MB | **failed** again: `core_campaign.STRATEGY_DIR` resolves beside the shadow package |
| 2026-10-30 | big plan P3: post-hoc `-05`: shadow layout with `core`, `outputs`, `research`, `data` linked (`mkold.sh`, validated first in `~/Build/tmp`); A/B three pairs at 16 threads | D + K | old 16.8–16.9 s, new 3.7–3.9 s | 126 / 181 MB | load 20–22; extension hashes `f04c2f4c…` (old) and `72ae90ba…` (new) recorded |
| 2026-10-30 | big plan P3: `-05` old-build probe at 1 thread | K ×16 + K | 75.4 s | 624 MB | load 21–22 |
| 2026-10-30 | big plan P3: `-05` `bench_p3_flags.py compare` (all runs against `-01`) and `compare` of the probes against the old build | bench records | 0.25 s, 0.10 s | 40 MB | 96/96 and 20/20 identical |
| 2026-10-30 | big plan P3: archive script (scratch, not committed) | run directories | under 1 s | – | `results/p3-sumthreshold.json` |
| 2026-10-30 | big plan P3: `bash tools/check-all.sh` (once, `-06`), code of `6b38f6c`/`3155e74` with this file's results in the tree | branch | 1,432 s (pytest 742 passed in 1,401 s) | 1.89 GB | overall PASS; load 16 → 46 (sibling sessions); later commits document-only |
| 2026-10-30 | big plan P3: `git diff --check 43dc3c7 HEAD` | branch | under 1 s | – | clean |
| 2026-10-30 | big plan P1: `bench_core_f.py check --target all` (`-02`, `RAYON_NUM_THREADS=1`) | – | 36.0 s | 827 MB |  |
| 2026-10-30 | big plan P1: `validate_core_phase2.py` (`-03`) | – | 1.96 s | 116 MB |  |
| 2026-10-30 | big plan P1: `validate_core_phase2.py --cost` | – | 0.40 s | 97 MB |  |
| 2026-10-30 | big plan P1: `validate_core_phase1.py` (`-04`) | – | 1.02 s | 383 MB |  |
| 2026-10-30 | big plan P1: `precondition_luno_campaign.py` (`-05-precondition`) | – | 2.34 s | 144 MB |  |
| 2026-10-30 | big plan P1: `bench_p1_solver.py sweep`, base, one thread, 3 rounds × 5 repeats (`-07`) | – | 8.3 s | 204 MB |  |
| 2026-10-30 | big plan P1: venv (`uv venv` + `uv pip install -e .[…]`), core and root release builds, `maturin develop` | worktree | 65 s in all (core build 14.0 s, root 7.0 s, extension 22.5 s) | 385 MB | load 13.8–22.4 |
| 2026-10-30 | big plan P1: baseline: `bench_core_f.py check --target all` (`-02`) | archived LUNO, fixture, blosc oracle | 36.0 s | 827 MB | base library, 1 thread, load 6.4 → 4.2, all 8 checks pass |
| 2026-10-30 | big plan P1: baseline: phase 2 validator (`-03`), `--cost`, phase 1 validator (`-04`), K precondition (`-05`) | archived inputs | 1.96 s, 0.40 s, 1.02 s, 2.34 s | 116, 97, 383, 144 MB | load 4.2; all pass as archived |
| 2026-10-30 | big plan P1: baseline: `bench_p1_solver.py sweep` (`-07`), base, 1 thread, 3 × 5 | LUNO + fixture | 8.3 s | 204 MB | load 3.9–4.1 |
| 2026-10-30 | big plan P1: `bench_core_f.py check --target all` at 1, 4, 16 threads (`-09`–`-11`) | as above | 56.3, 57.5, 54.8 s | 849–861 MB | new library, load 21–23, all checks pass |
| 2026-10-30 | big plan P1: phase 2 validator (`-12`), `--cost` (1 thread / default), phase 1 validator (`-13`), K precondition (`-14-precondition`) | archived inputs | 3.19 s, 0.93 / 0.56 s, 2.17 s, 4.25 s | 120, 100 / 101, 386, 155 MB | load 22.7–23.5; all pass |
| 2026-10-30 | big plan P1: `bench_p1_solver.py sweep` (`-16`), base / v1 / new × 1–16 threads × 3 rounds × 5 | LUNO + fixture | 3 min 20 s | 229 MB | load 14.5–25.9; all 45 processes equal |
| 2026-10-30 | big plan P1: `perf stat` instruction counts, development variants (8 pairs) | one bench run each | 2–4 s each | about 210 MB | load 6–20 |
| 2026-10-30 | big plan P1: `cargo test` core (51 tests, release) | – | 1.0–3.1 s | – | – |
| 2026-10-30 | big plan P1: `tests/test_p1_solver.py` | synthetic | 0.34–0.61 s | – | three subprocesses |
| 2026-10-30 | big plan P1: post-hoc section 6 prototype and checker, actions, injections, prospective with comparators, base (`-20`) and new (`-21`) | archived inputs | base 23.1 + 43.4 + 11.1 + 31.8 + 41.8 s; new 9.9 + 40.0 + 8.1 + 22.1 + 32.6 s (compares 0.2–0.3 s each) | up to 766 MB | load 31–40; all comparators pass identically; section 6 criterion 8 (cost) fails for both at that load; first attempt `-18`/`-19` failed without `cargo` on `PATH` (1–5 s each) |
| 2026-10-30 | big plan P1: `bash tools/check-all.sh` (`-17`) | branch | 28 min 25 s (pytest 740 passed in 1,665 s) | 1.73 GB | PASS; load 13.7–40.0 |
| 2026-10-30 | big plan P2: `uv venv` + `uv pip install` of the worktree venv | – | 14.5 s | – |  |
| 2026-10-30 | big plan P2: `cargo +1.93 build --release --offline` of `core/` (baseline) | – | 10.7 s | 382 MB |  |
| 2026-10-30 | big plan P2: `maturin develop --release --offline` (baseline) | – | 0.8 s | 34 MB |  |
| 2026-10-30 | big plan P2: `bench_p2_gridder.py c-inputs` | – | 0.8 s | 95 MB |  |
| 2026-10-30 | big plan P2: `bench_p2_gridder.py k-replay --dump-inputs` (baseline, precondition) | – | 27.1 s | 333 MB |  |
| 2026-10-30 | big plan P2: `run_core_gridder.py` (baseline) | – | 118.6 s | 138 MB |  |
| 2026-10-30 | big plan P2: `compare_core_gridder.py` (baseline) | – | 0.6 s | 65 MB |  |
| 2026-10-30 | big plan P2: `run_core_imaging.py` (baseline) | – | 96.9 s | 212 MB |  |
| 2026-10-30 | big plan P2: `bench_p2_gridder.py bench` K, old, t1 × 3 | – | about 100 s | 126 MB |  |
| 2026-10-30 | big plan P2: `bench_p2_gridder.py bench` C, old, t1 × 3 | – | about 270 s | 148 MB |  |
| 2026-10-30 | big plan P2: `perf record` + `time` K `original` (baseline) | – | about 6 s | – |  |
| 2026-10-30 | big plan P2: `cargo build` + `cargo test grid` stage (a) | – | 5.0 s + under 1 s | – |  |
| 2026-10-30 | big plan P2: `bench` C and K, stage (a), t1 and t16, one repeat | – | about 140 s | 402 MB |  |
| 2026-10-30 | big plan P2: `maturin develop` run in `core/py` (operator error, at setup and stage a) | – | 0.8 s | – |  |
| 2026-10-30 | big plan P2: `maturin develop --release --offline` from the root (stage a) | – | about 30 s | – |  |
| 2026-10-30 | big plan P2: `k-replay` stage (a) | – | 7.3 s | 611 MB |  |
| 2026-10-30 | big plan P2: `cargo clippy -D warnings`, `cargo fmt --check` (core) | – | about 20 s | – |  |
| 2026-10-30 | big plan P2: `cargo build` + `cargo test grid` + clippy stage (b) | – | 25.5 s + under 1 s | – |  |
| 2026-10-30 | big plan P2: `maturin develop --release --offline` (final) | – | 32.7 s | 681 MB |  |
| 2026-10-30 | big plan P2: `k-replay` final | – | 7.1 s | 708 MB |  |
| 2026-10-30 | big plan P2: `run_core_gridder.py` final | – | 7.5 s | 515 MB |  |
| 2026-10-30 | big plan P2: `compare_core_gridder.py` final | – | 0.8 s | 66 MB |  |
| 2026-10-30 | big plan P2: `run_core_imaging.py` final | – | 7.6 s | 568 MB |  |
| 2026-10-30 | big plan P2: `time --save-images` C and K (t16) + `diff` | – | about 12 s | – |  |
| 2026-10-30 | big plan P2: `perf record` K `original` final | – | about 1 s | – |  |
| 2026-10-30 | big plan P2: `bench` K, old t1 + new t1–16, three repeats | – | 168 s | 466 MB |  |
| 2026-10-30 | big plan P2: `bench` C, old t1 + new t1–16, three repeats | – | 426 s | 494 MB |  |
| 2026-10-30 | big plan P2: scale probes 4×, 16×, 41× | – | 37 s | 774 MB |  |
| 2026-10-30 | big plan P2: `pytest tests/test_p2_gridder.py tests/test_core_grid.py tests/test_core_imaging.py` | – | 1.8 s | 81 MB |  |
| 2026-10-30 | big plan P2: `bash tools/check-all.sh` (final tree) | – | 1702.6 s | 1.88 GB |  |
| 2026-10-30 | big plan L1: `uv venv -p /usr/bin/python3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` (public PyPI) | – | 7.9 s | – | uv cache warm |
| 2026-10-30 | big plan L1: three scratch probes of the archived row columns, UVW and tile headers (row structure, uv extent, dead stations) | – | 1–3 s each | – | before the protocol |
| 2026-10-30 | big plan L1: `pytest tests/test_core_campaign_array.py` while writing (8, then 10 tests) | – | 0.2–1.6 s | 71–209 MB | one run failed on `cargo` missing from `PATH` (the TV kernel builds on demand), as in K |
| 2026-10-30 | big plan L1: **precondition**, `examples/precondition_luno_array.py` (`-00-precondition`, code `4584936`) | – | 47.4 s | 310 MB | all three parts pass |
| 2026-10-30 | big plan L1: labelled smoke, stations 0–11 (`-00-smoke`) | – | 69.9 s | 1.2 GB | **crashed**: the frozen first-pass TV loop raised because its base had no validation loss; bug fix (record the arm as unavailable), see amendment 1 |
| 2026-10-30 | big plan L1: labelled smoke, stations 0–11 (`-00-smoke-b`) | – | 15 min 13 s | 2.6 GB | completed; found the invalid-prediction mechanism |
| 2026-10-30 | big plan L1: scratch mechanism check on `-00-smoke-b` (station-bins 4 and 5 × frequency bin 9) | – | about 10 s | – | after the smoke, before the amendment |
| 2026-10-30 | big plan L1: **precondition** rerun with the amended code (`-00-precondition-b`, code `e6e0d07`) | – | 2 min 34 s | 314 MB | all three parts pass; ran beside the next smoke |
| 2026-10-30 | big plan L1: labelled smoke, stations 0–11 (`-00-smoke-c`, amended code) | – | 19 min 30 s | 2.6 GB | amendment paths exercised |
| 2026-10-30 | big plan L1: **frozen run `-01`**, `examples/run_luno_array.py` under `/usr/bin/time -v`; MemAvailable 27.2 GiB at start; load average 28 from sibling pytest runs | – | **2 h 07 min 40 s** (user 5,164 s, sys 140 s, 69 % CPU) | **12.46 GB** | stage table below |
| 2026-10-30 | big plan L1: `examples/check_luno_array.py` (`outputs/luno-array-campaign-check-20261030-01`) | – | 5.7 s | 210 MB | criteria 2, 4 and 6 FAIL as frozen; 1, 3, 5 and 7 pass |
| 2026-10-30 | big plan L1: post-hoc diagnostic (labelled): derived FLAG_ROW, and model Stokes I by baseline length (`outputs/luno-array-campaign-20261030-01-posthoc.json`) | – | 25.4 s | 5.3 GB | not part of the frozen run |
| 2026-10-30 | big plan L1: `examples/archive_luno_array.py` | – | 0.1 s | 21 MB | 84.7 KB archive |
| 2026-10-30 | big plan L1: `bash tools/check-all.sh`, once before the final commit (`outputs/luno-array-campaign-20261030-01.check-all.log`) | – | 22 min 04 s (pytest 749 passed in 21 min 22 s) | 1.87 GB | overall PASS (criterion 8); load average 19–27 from sibling sessions, against K's 96.6 s on an idle host |
| 2026-10-30 | big plan L1: input integrity (hash 92 objects, 5.9 GB, against the receipts) | – | 3.9 s | 51 MB | 0.62 |
| 2026-10-30 | big plan L1: decode (64 whole tiles, Rust blosc) | – | 38.2 s | 7.25 GB | 0.54 |
| 2026-10-30 | big plan L1: split (seed 7) | – | 31.8 s | 9.87 GB | 0.50 |
| 2026-10-30 | big plan L1: solve `original` + per-baseline features | – | 269.0 s | 10.08 GB | 0.56 |
| 2026-10-30 | big plan L1: plain solve (`tricolour-firstpass`) | – | 90.7 s | 11.47 GB | 1.00 |
| 2026-10-30 | big plan L1: solve `tricolour-mild` | – | 149.6 s | 12.46 GB | 0.89 |
| 2026-10-30 | big plan L1: Tricolour first-pass port (12 steps) | – | 763.5 s | 11.42 GB | 0.62 |
| 2026-10-30 | big plan L1: Tricolour mild port (10 steps) | – | 278.2 s | 12.46 GB | 0.93 |
| 2026-10-30 | big plan L1: TV loop (scores, TV, 9 distinct candidate solves of 86–163 s each) | – | 1,146.9 s | 12.46 GB | 0.90 |
| 2026-10-30 | big plan L1: first-pass TV loop, frozen (its base has no validation loss) | – | 0.0 s | – | – |
| 2026-10-30 | big plan L1: first-pass TV loop, amendment 1 (base re-solve and 8 candidate solves) | – | 1,418.1 s | 12.46 GB | 0.82 |
| 2026-10-30 | big plan L1: image, per arm (correct and weight, 4 × 512-channel grid groups) | – | 232–840 s | 12.46 GB | 0.42–0.97 |
| 2026-10-30 | big plan L1: amendment 1 calls (19 restricted fused passes) | – | 56.2 s | 12.46 GB | 0.92 |
| 2026-10-30 | big plan P4: `uv venv -p python3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin numcodecs` (public PyPI) | worktree | 14.2 s | 390 MB |  |
| 2026-10-30 | big plan P4: `cargo +1.93 build --release --offline` root, core; `maturin develop --release --offline` | base `4167141` | 5.9 s, 12.3 s, 0.5 s | 380 MB | load 9–18; A library frozen from this build |
| 2026-10-30 | big plan P4: `cargo test` / `clippy` / `fmt` / `build` root crate, during implementation | branch | under 1 min each | – | first test run failed my own 2-station rank expectation (scalar model gives rank 8 of 12, as documented); test corrected; clippy `needless_range_loop` allowed on the EISPACK port |
| 2026-10-30 | big plan P4: targeted pytest: `test_p4_eigen.py`, `test_flagging_influence.py`, `test_flagging_response.py`, `test_native_support_diagnostics.py` (B library) | 55 tests | 1.6 s | 78 MB | 55 passed |
| 2026-10-30 | big plan P4: record suite `-02`, both arms (11 steps each) | archived inputs | A: section 6 11.8 s, check 43.5 s, phase 2 5.0 s, bench-f 14.4 s, LUNO solved 1.6 s, support 5.3 s, audit 6.1 s, prospective 40.2 s, signal 94.9 s; B: 9.3, 39.3, 3.3, 8.5, 1.2, 2.7, 2.8, 37.1, 55.9 s | 973 MB (signal) | load 29–33; `section6-check` exit 1 both arms (`8_cost` only) |
| 2026-10-30 | big plan P4: identity analysis `-03`: 14 replays, 7 dumps, 7 `p4_dump_audit` runs, 15 diffs | `-02` recordings | replays 1–80 s (signal 80 s, 77 s), audits 0.5–30 s | 480 MB | load 28–34; all pass |
| 2026-10-30 | big plan P4: timing suite `-04`: 6 × bench-f survey, 6 × section 6 + check, 6 × prospective, 6 × signal, interleaved; 3 × replay microbenchmark | archived inputs | 15.5 min in all; replays 9.6–10.5 s | 838 MB (signal) | load 18–32; Jacobi `section6-check` exit 1 (`8_cost`) 3 of 3, QL exit 0 3 of 3 |
| 2026-10-30 | big plan P4: `bash tools/check-all.sh` (once, on `6d3199b` plus this document) | branch | 1,380 s (pytest 558 passed in 1,296 s) | not measured | load 31–41; overall PASS; log `outputs/p4-eigen-20261030-05/check-all.log` |
| 2026-10-30 | big plan P6: trend | – |  | – |  |
| 2026-10-30 | big plan P6: signal | – |  | – |  |
| 2026-10-30 | big plan P6: trend | – |  | – |  |
| 2026-10-30 | big plan P6: signal | – |  | – |  |
| 2026-10-30 | big plan P6: trend | – |  | – |  |
| 2026-10-30 | big plan P6: signal | – |  | – |  |
| 2026-10-30 | big plan P6: base | – |  | – |  |
| 2026-10-30 | big plan P6: new | – |  | – |  |
| 2026-10-30 | big plan P6: `uv venv` + `uv pip install -e .[...]` + `maturin develop --release` | – | about 2 min | – | background; cached wheels |
| 2026-10-30 | big plan P6: root crate first build (`_native_library()`) | – | 10.3 s | – | `cargo` on `PATH` |
| 2026-10-30 | big plan P6: baseline `-01`, trend and signal × 3 | – | 0.6–1.3 s each | 44–190 MB | **failed as frozen**: `cargo` not on `PATH` |
| 2026-10-30 | big plan P6: baseline `-02`, trend × 3 | – | 89.9, 68.2, 84.8 s | 340–344 MB | exit 1: `runtime_unchanged` audit (files created during the runs); load 26–32 |
| 2026-10-30 | big plan P6: baseline `-02`, signal × 3 | – | 59.2, 0.2, 93.4 s | 828–834 MB | repeat 2 failed (`NameError`, half-written file); load 28–32 |
| 2026-10-30 | big plan P6: cProfile signal base / new (`-03`) | – | 85.2 / 60.8 s (profile totals) | – | load about 30; first signal port |
| 2026-10-30 | big plan P6: cProfile trend frozen / prefix-sum-only port (`-04`) | – | 121.4 / 103.2 s | – | load 35–45; identity pass (all 9 files) |
| 2026-10-30 | big plan P6: one case, 8 calls, frozen / ported (scratch, development) | – | 12.4–17.8 / 2.7–8.0 s | – | load 30–44; same results checked each time |
| 2026-10-30 | big plan P6: pytest P6 files (development, several runs) | – | 3–8 s | – |  |
| 2026-10-30 | big plan P6: A/B `-05` | – | 0.05 s each | – | **failed as frozen**: `/usr/bin/time` cannot run shell functions (exit 127) |
| 2026-10-30 | big plan P6: A/B `-06` (frozen measurement) | – | 12 runs, see Results | 340–872 MB | load 42 → 7 |
| 2026-10-30 | big plan P6: identity and comparators in `-06` | – | under 1 s each | – | all pass |
| 2026-10-30 | big plan P6: cProfile signal base / new (`-07`) | – | 60.3 / 44.1 s | 833 / 868 MB | load 15–22 |
| 2026-10-30 | big plan P6: diagnostic `-08` (post hoc), 4 signal runs | – | 91.0, 71.2, 98.2, 65.8 s | – | load 25–38 |
| 2026-10-30 | big plan P6: labelled trial `-09`: switched `rang-core trend` / `signal` | – | 31.7 / 34.2 s | 414 / 870 MB | load 30–33; comparators pass; reverted |
| 2026-10-30 | big plan P6: `bash tools/check-all.sh` | – | 4,539 s | – | PASS; pytest 584 passed, 1 skipped (4,280 s); load 27 → 99 |
| 2026-10-30 | big plan P6: `micro.py` (`cond`/`inv` per cell vs per run, 70,000 matrices) | – | about 1 s | – | load 13; default and one OpenBLAS thread |
| 2026-10-30 | big plan P6: `negzero.py` (signed zeros, post hoc) | – | under 1 s | – | all agree |
| 2026-10-30 | big plan P6: identity pre-P6 vs `-06` (`-10`, post hoc) | – | under 1 s | – | pass, both arms |
| 2026-10-30 | big plan P10: base-1 | – |  | – |  |
| 2026-10-30 | big plan P10: base-2 | – |  | – |  |
| 2026-10-30 | big plan P10: base-3 | – |  | – |  |
| 2026-10-30 | big plan P10: A1 | – |  | – |  |
| 2026-10-30 | big plan P10: B1 | – |  | – |  |
| 2026-10-30 | big plan P10: B2 | – |  | – |  |
| 2026-10-30 | big plan P10: A2 | – |  | – |  |
| 2026-10-30 | big plan P10: `uv venv` / `uv pip install -e .[pointing,beam,test,imaging]` / `maturin develop --release` | P10 worktree | 0.01 / 10.6 / 10.5 s | 22 / 377 / 382 MB | setup, `outputs/p10-tests-20261030-01/` |
| 2026-10-30 | big plan P10: pytest 9, full suite base-1/2/3 (tests of `4167141`) | 555 tests | 946 / 760 / 1,294 s | 1,676 / 1,630 / 1,703 MB | CPU 7,679 / 6,892 / 8,968 s; load 27–34; 145 threads |
| 2026-10-30 | big plan P10: pytest, one full-coverage test, 6 thread settings × 2 | 1 test | 12.8–148.7 s | 747–848 MB | probe table in `research/p10-tests.md` |
| 2026-10-30 | big plan P10: pytest, three pointing modules after the change | 71 tests | 95.5 s | 1,370 MB | user 110 s, load 19 |
| 2026-10-30 | big plan P10: pytest full suite A1 / B1 / B2 / A2 | 555 tests | 672 / 223 / 311 / 4,140 s | 1,638 / 1,631 / 1,777 / 1,528 MB | CPU 6,031 / 188 / 235 / 13,263 s; load 26.5 / 25.8 / 26.9 / 68.5 |
| 2026-10-30 | big plan P10: `bash tools/check-all.sh` on `d2c6812` + first version of this note | repo | 758 s (pytest step 584 s) | 1,770 MB | PASS; user 281 s, sys 18 s; load 65–82 (A2 took 4,140 s at load 68); `outputs/p10-tests-20261030-06/`; no lock |
| 2026-10-30 | big plan P10: `bash tools/check-all.sh` on the corrected note | repo | 838 s (pytest step 701 s) | 1,813 MB | PASS; user 223 s, sys 12 s; load 73–83; `outputs/p10-tests-20261030-07/`; no lock (started before the lock instruction), lock wait 0 |
| 2026-10-30 | big plan U2: stimela 2.2.0rc1 `stimela run` echo recipe, Python 3.14.8 | 1 native cab | 3.8 s | 95 MB | fails (no event loop); 2.1.4: 2.6 s, 91 MB, fails |
| 2026-10-30 | big plan U2: same, Python 3.13.16 | 1 native cab | 2.9 s | 89 MB | exit 0 |
| 2026-10-30 | big plan U2: same, 3.14.8 with the U2 fix | 1 native cab | 2.1 s | 94 MB | exit 0 |
| 2026-10-30 | big plan U2: stimela `pytest tests` (fix branch), Python 3.14.8 | 72 tests | 368 s | 88 MB | 72 passed |
| 2026-10-30 | big plan U2: stimela `pytest tests` (fix branch), Python 3.13.16 | 72 tests | 762 s | 82 MB | 72 passed |
| 2026-10-30 | big plan U2: tricolour 0.5.0-dev #111 test, before fix, empty Numba cache | 2x2x32x64 | 98.5 s | 583 MB | 2 signatures |
| 2026-10-30 | big plan U2: tricolour 0.5.0-dev #111 test, after fix | same | 51.6 s | 480 MB | 1 signature |
| 2026-10-30 | big plan U2: tricolour 0.5.0-dev `pytest -m "not acceptance"` (#111 branch) | 60 tests | 69.0 s | 579 MB | 58 passed, 2 skipped |
| 2026-10-30 | big plan U2: tricolour 0.5.0-dev `pytest -m "not acceptance"` (lanes branch) | 59 tests | 105.4 s | 558 MB | 57 passed, 2 skipped |
| 2026-10-30 | big plan U2: lanes benchmark, first round per variant (cold JIT) | 3 shapes x 6 calls | 239.9 s base, 142.2 s lanes | 444 / 458 MB | `bench.sh` |
| 2026-10-30 | big plan U2: lanes benchmark, warm rounds 2-7 | 3 shapes x 6 calls | 21.7-33.6 s base, 19.5-27.9 s lanes | 232 / 235 MB | `taskset` one core |
| 2026-10-30 | big plan U2: CARACal `pytest tests` | 13 tests | 12.1 s | 98 MB | 13 passed |
| 2026-10-30 | big plan U2: QuartiCal v0.2.8-dev conjugate-baseline test (8 cases), before fix | – | not recorded | – | 8 failed; incl. JIT (wall line cut from the log) |
| 2026-10-30 | big plan U2: same, after fix | – | 792 s | – | 8 passed; incl. JIT, load about 60 |
| 2026-10-30 | big plan U2: QuartiCal 0.2.7 `goquartical` scan 9, cold Numba cache, 5 iterations | 140 rows x 4096 ch | 99.1 s | 795 MB | trial |
| 2026-10-30 | big plan U2: QuartiCal 0.2.7 sweep, 1 x 1 intervals, k = 1-100 (16 runs + k26, k51) | same | 10.4-45.2 s per run | 545-550 MB | warm cache |
| 2026-10-30 | big plan U2: QuartiCal 0.2.7 sweep, 2 x 32 intervals (16 runs + k26, k51) | same | 11.4-18.8 s per run | 431-432 MB | warm cache |
| 2026-10-30 | big plan U2: Tricolour 0.2.1 CARACal first-pass strategy, native flags, cold cache | scan 9 | 514.9 s | 764 MB | under `script` (TTY) |
| 2026-10-30 | big plan U2: same, 60.7 % pre-flags, warm cache | scan 9 | 12.7 s | 440 MB |  |
| 2026-10-30 | big plan D2: `uv venv` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` + notebook packages | public PyPI | 132 s | – | Python 3.14 |
| 2026-10-30 | big plan D2: `maturin develop --release` | `core/py` | 82 s | 606 MB | – |
| 2026-10-30 | big plan D2: `core_ms` probe (`probe1.py`) | fixture scan 9 MS | 0.23 s read | – | every needed column and subtable readable |
| 2026-10-30 | big plan D2: loader probe (`probe2.py`) | fixture + local LUNO slice | 62 s | 222 MB | includes the root crate's first cargo build, 33.6 s, triggered by `gain_tv`; fixture load 3.6 s (first extraction), LUNO load 17.0 s (cold 724 MB decode), LUNO solve 0.67 s |
| 2026-10-30 | big plan D2: function smoke (`probe3.py fixture`) | fixture | 145 s | 1.28 GB | survey 2.5 s, strategies 0.8–3.5 s, solve 0.9 s, image 2.0 s each, robust sweep (3 images) 15.7 s, arms 9.1 s, arm images 12.3 s; first attempt stopped on a widget constructor bug (fixed) |
| 2026-10-30 | big plan D2: function smoke (`probe3.py luno`) | local LUNO slice | 110 s | 1.05 GB | load 20.5 s, survey 5.6 s, arms 3.9 s, arm images 6.1 s |
| 2026-10-30 | big plan D2: nbconvert, five notebooks in series, LUNO on | fixture + slice | 755 s | 1.16 GB (children) | 01 22.3 s, 02 8.9 s, 03 20.9 s, 04 636.8 s, 05 66.3 s; 04's cells summed 37 s, the rest was a kernel-shutdown stall ("KeyboardInterrupt caught in kernel") not reproduced on rerun |
| 2026-10-30 | big plan D2: nbconvert, 04 alone | fixture | 37.4 s | 809 MB | – |
| 2026-10-30 | big plan D2: `pytest tests/test_notebook_functions.py tests/test_notebook_execute.py` | fixture + slice | 78 s | 839 MB | 15 passed; the concurrent notebook fixture 47.6 s |
| 2026-10-30 | big plan D2: `data.download_fixture` + `data.load_luno(fetch=True)` (`fetchcheck.py`) | public LFS fixture; RATT bucket | 116 s | 179 MB | fixture 45,452,147 bytes in 5.9 s, hash verified; slice and extra objects 754.9 MB fetched and loaded in 101.9 s with the polled progress line every 10 s; `.partial` renamed, nothing left over; split, original-arm TV 0.018794641730921754 and losses equal to the local copy; the 769 MB cache was deleted afterwards (log `outputs/d2-notebook-20261030-02/fetch.log`) |
| 2026-10-30 | big plan D2: `bash tools/check-all.sh` | branch tree | 4,755 s | 2.28 GB | **PASS**; pytest 585 passed, 1 skipped in 4,276 s at load 70–100; started before the coordinator's `flock` rule, so no lock wait; log `outputs/d2-notebook-20261030-01/check-all.log`. After it, only notebook 05's markdown changed (the model-limited caveat); the no-outputs test passes on the rebuilt notebooks |
| 2026-10-30 | big plan U2: `tools/check-all.sh` | branch u2-upstream-prs, 560 tests | 4,738.6 s | 1.86 GB | PASS; before the lock; load 55–98 |
| 2026-10-30 | big plan L2: `uv venv -p /usr/bin/python3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` (public PyPI) | – | 83.4 s | – |  |
| 2026-10-30 | big plan L2: `maturin develop --release` | – | 1.1 s | – |  |
| 2026-10-30 | big plan L2: probe 1: 16-byte ranged GETs of the 19 objects, MAIN_2 row columns, UVW, stored MODEL_DATA statistics (`-00-probe/probe.json`) | – | 13.1 s | 1.34 GB |  |
| 2026-10-30 | big plan L2: probe 2: FLAG structure, eligible support per tile, short-baseline support (`-00-probe/probe2.json`) | – | 6.8 s | 516 MB |  |
| 2026-10-30 | big plan L2: `pytest tests/test_core_campaign_1830.py` while writing (17, then 18 tests) | – | 0.5–4.2 s | 67 MB |  |
| 2026-10-30 | big plan L2: **fetch**, `examples/fetch_luno_1830.py` (`-01-fetch`) under `/usr/bin/time -v` | – | 2 min 23 s (fetch 136.5 s) | 194 MB |  |
| 2026-10-30 | big plan L2: precondition, `examples/precondition_luno_1830.py` (`-00-precondition`, code `df01a01`) | – | 4 min 50 s | 615 MB |  |
| 2026-10-30 | big plan L2: labelled smoke, stations 0–11, stored model (`-00-smoke-stored`) | – | 4 min 47 s | 1.31 GB |  |
| 2026-10-30 | big plan L2: labelled smoke, stations 0–11, scalar model (`-00-smoke-scalar`) | – | 2 min 49 s | 1.30 GB |  |
| 2026-10-30 | big plan L2: **precondition** rerun (`-00-precondition-b`, code `262ba2c`) | – | 1 min 09 s | 607 MB |  |
| 2026-10-30 | big plan L2: **frozen run, stored** (`-02-stored`), `examples/run_luno_1830.py` under `/usr/bin/time -v`; MemAvailable 12.7 GiB; load average 47–62 | – | **25 min 15 s** (user 1,431 s, sys 113 s, 101 % CPU) | **6.43 GB** |  |
| 2026-10-30 | big plan L2: **frozen run, scalar** (`-02-scalar`); MemAvailable 14.0 GiB; load average 46–97 | – | **36 min 39 s** (user 1,417 s, sys 106 s, 69 % CPU) | **6.48 GB** |  |
| 2026-10-30 | big plan L2: `examples/check_luno_1830.py` (`-02-check`) | – | 17.8 s | 104 MB |  |
| 2026-10-30 | big plan L2: `examples/archive_luno_1830.py` | – | 0.3 s | 22 MB |  |
| 2026-10-30 | big plan L2: `bash tools/check-all.sh`, once before the final commit (`outputs/l2-1830-20261030-02.check-all.log`) | – | 57 min 31 s (pytest 588 passed, 1 skipped in 46 min 20 s) | 1.93 GB |  |
| 2026-10-30 | big plan DDF: `git clone` ×3 (DDFacet, killMS, ducc) | GitHub | 11 s | – | 22 MB, 32 MB, 7.7 MB |
| 2026-10-30 | big plan DDF: `uv venv -p 3.12` | – | 0.05 s | – |  |
| 2026-10-30 | big plan DDF: `uv pip install ./DDFacet ./killMS` | sources | 49.8 s | – | **failed** (killMS on GCC 15) |
| 2026-10-30 | big plan DDF: `uv pip install ./DDFacet` | source | 94.5 s | – | built; 3 pybind11 modules |
| 2026-10-30 | big plan DDF: `uv pip install ./killMS` | source | 9.9 s | – | **failed**: `Gridder.c:309` incompatible pointer types |
| 2026-10-30 | big plan DDF: `uv pip install ./killMS` with `CFLAGS=-Wno-error=incompatible-pointer-types` | source | 24.5 s | – | built |
| 2026-10-30 | big plan DDF: `DDF.py` dirty, field 0 default | LUNO slice MS | 7.9 s | – | **failed**: "no rows" (data are field 1) |
| 2026-10-30 | big plan DDF: `DDF.py` dirty, 1 facet | LUNO slice, 2,048 ch, Briggs 0.5, 512→525 px at 8″, NCPU 4 | 16.6 s | – | CPU 58 % |
| 2026-10-30 | big plan DDF: `DDF.py` dirty, 3×3 facets | same | 32.4 s | – | 1 vs 9 facets: 2.5 % L∞, 0.49 % RMS of peak |
| 2026-10-30 | big plan DDF: `DDF.py` clean, Hogbom, 3 major cycles | same | stopped after about 10 min | – | stalled in the first minor cycle with an overflow warning; killed |
| 2026-10-30 | big plan DDF: `DDF.py` clean, SSD | same | killed at start | – | no result (the run was cancelled with Hogbom's chain) |
| 2026-10-30 | big plan DDF: `DDF.py` clean, HMP, 2 major cycles, 2,000 minor | same | 234.5 s | – | CPU 126 %; 161 minor iterations; degrid 61 s single-core per facet job; DDFacet reports 3 min 41.5 s |
| 2026-10-30 | big plan DDF: `uv venv -p 3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` | worktree | 194.9 s | – | rang venv for the core comparisons and check-all |
| 2026-10-30 | big plan DDF: `uv pip install ducc0` | PyPI | 3.9 s | – | 0.42.0 wheel |
| 2026-10-30 | big plan DDF: `export_and_ref.py` (export, DFT, ducc0) | slice, every 16th channel | 244.2 s | – | DFT 243 s; ducc0 variants at the default convention (4 % off: `divide_by_n` and w sign) |
| 2026-10-30 | big plan DDF: `orient.py`, `tiny.py` | same; 64² synthetic | under 30 s each (not wrapped in `time`) | – | convention pinned: w sign flipped, `divide_by_n=False` |
| 2026-10-30 | big plan DDF: `ducc_cmp.py` | slice export | 2.4 s | – | the table in section 3.1 |
| 2026-10-30 | big plan DDF: `core_cmp.py`, `core_cmp2.py`, `core_point.py` | slice export | 2.9 s; others under 1 min (not wrapped) | – | core against the DFT: unresolved convention |
| 2026-10-30 | big plan DDF: `core_psf.py` | slice export, exact DFT PSF | under 10 min (not wrapped) | – | PSF sidelobes 0.80 at the edge |
| 2026-10-30 | big plan DDF: `core_psf2.py`, `core_psf3.py` | same | under 2 min each (not wrapped) | – | padding 2, kernel 15, 512 layers: still 1.6 % on the PSF |
| 2026-10-30 | big plan DDF: `facet_beam.py` | katbeam 0.1 | seconds (not wrapped) | – | the table in section 3.1 |
| 2026-10-30 | big plan DDF: `uv pip install meqtrees-cattery` | PyPI | 9.5 s | – | 1.8.0; imports |
| 2026-10-30 | big plan DDF: `kMS.py` CohJones, scalar, `--DicoModel` from the HMP run | LUNO slice | 8.3 s | – | **failed**: `AsyncProcessPool._init_default` missing in DDFacet 1.0.0.0 |
| 2026-10-30 | big plan DDF: evidence copy and SHA256SUMS | – | seconds | – | `outputs/ddfacet-feasibility-20261030-01`, 15 MB |
| 2026-10-30 | big plan DDF: `bash tools/check-all.sh` (first attempt, without the lock) | worktree at `e2296e0` | about 60 min, then stopped | – | stopped during pytest on the coordinator's load-control instruction; log `check-all-aborted-unlocked.log` |
| 2026-10-30 | big plan DDF: `flock /home/gijsm/.rang-checkall.lock bash tools/check-all.sh` | worktree at `5aaf758` (documents only) | 2,534.8 s; lock wait 0 s | – | **PASS**; pytest 570 passed and 1 skipped in 2,225.6 s; root 19 and core 55 Rust tests; clippy, fmt, ruff clean; load 77–81 at the start; log `check-all.log` |
| 2026-10-30 | big plan X1: clone | – | 21.2 s | – |  |
| 2026-10-30 | big plan X1: toolchain | – | not timed | – |  |
| 2026-10-30 | big plan X1: core | – | 56.3 s (cold, including the crate download) | – |  |
| 2026-10-30 | big plan X1: root | – | 8.1 s | – |  |
| 2026-10-30 | big plan X1: venv | – | 0.2 s; 83.7 s | – |  |
| 2026-10-30 | big plan X1: extension | – | 3.8 s failed; 2.1 s warm | – |  |
| 2026-10-30 | big plan X1: import | – | <1 s | – |  |
| 2026-10-30 | big plan X1: backend tests | – | 52.1 s | – |  |
| 2026-10-30 | big plan X1: suite | – | 414.5 s | – |  |
| 2026-10-30 | big plan X1: Windows `build.py ../wheel-win-01 --sdist` | – | 127.4 s (rustc 24.1 s, which includes rustup fetching the `1.93.1` name; wheel 63.4; sdist 4.8; ctypes 33.5) | – |  |
| 2026-10-30 | big plan X1: Windows `build.py ../wheel-win-02 --no-ctypes`, after the `.gitignore` fix | – | 64.9 s | – |  |
| 2026-10-30 | big plan X1: Windows `test.py` on `wheel-win-01`, py3.10 / py3.14 / py3.14 `--no-ctypes` | – | 4.5 / 3.3 / 4.2 s | – |  |
| 2026-10-30 | big plan X1: Windows `test.py` on `wheel-win-02`, py3.10 / py3.14, ctypes from `-01` | – | 4.6 / 3.1 s | – |  |
| 2026-10-30 | big plan X1: Windows `test.py` on `wheel-win-02`, py3.14, **uv removed from PATH** (the CI path: `python -m venv` and pip, `PIP_INDEX_URL` public PyPI) | – | 49.0 s (install 37.0 s) | – |  |
| 2026-10-30 | big plan X1: Linux (WSL) `build.py` | – | 271.7 s (wheel 139.3 s, ctypes 104.4 s, load about 50) | – |  |
| 2026-10-30 | big plan X1: Linux `test.py`, py3.10 / py3.14 / `--no-ctypes` | – | 5.9 / 7.5 / 6.0 s | – |  |
| 2026-10-30 | big plan X1: Windows: clone from WSL main repository | – | 21.2 s | – | CRLF by default; converted to LF |
| 2026-10-30 | big plan X1: Windows: `cargo +1.93 build --release --locked` core, cold | – | 56.3 s | – | includes the crate download |
| 2026-10-30 | big plan X1: Windows: `cargo +1.93 build --release --locked` root | – | 8.1 s | – | pdb collision warning |
| 2026-10-30 | big plan X1: Windows: `uv pip install -e ".[pointing,beam,test,imaging]" ruff maturin` | – | 83.7 s | – | includes the extension build |
| 2026-10-30 | big plan X1: Windows: `maturin develop --release`, warm | – | 2.1 s | – | after one failure (uv cache) |
| 2026-10-30 | big plan X1: Windows: `pytest tests/test_core_backends.py` | – | 52.1 s | – | 10 passed, 1 skipped; includes the cargo build of core |
| 2026-10-30 | big plan X1: Windows: full pytest | – | 414.5 s | – | 529 passed, 17 failed, 5 skipped, 3 collection errors |
| 2026-10-30 | big plan X1: WSL → `/mnt/c` copy of the task D inputs (585 MB) | – | 116.0 s | – |  |
| 2026-10-30 | big plan X1: Windows: task D port run / comparator | – | 2.8 s / 1.1 s | – | criteria 1–4 pass, 5 fails as frozen (path separators) |
| 2026-10-30 | big plan X1: WSL: task D port run / comparator, same commit | – | 6.5 s / 2.1 s | – | all pass; load about 50 |
| 2026-10-30 | big plan X1: Windows: `tools/wheel/build.py --sdist` | – | 127.4 s | – |  |
| 2026-10-30 | big plan X1: Windows: `tools/wheel/build.py --no-ctypes` | – | 64.9 s | – |  |
| 2026-10-30 | big plan X1: Windows: `tools/wheel/test.py`, per Python version | – | 3.1–4.6 s | – | 15.8 s on the first run (cold uv cache) |
| 2026-10-30 | big plan X1: WSL: `tools/wheel/build.py` | – | 271.7 s | – | load about 50 |
| 2026-10-30 | big plan X1: WSL: `tools/wheel/test.py`, per run | – | 5.9–7.5 s | – |  |
| 2026-10-30 | big plan X1: actionlint with shellcheck | – | 11.7 s | – | 0 errors |
| 2026-10-30 | big plan X1: WSL: `uv venv` + editable install for check-all | – | 89.3 s | – |  |
| 2026-10-30 | big plan X1: WSL: `bash tools/check-all.sh`, first run, started before the coordinator's lock rule and without it | – | 4,709 s (78 min 29 s; pytest 4,350 s) | – | overall FAIL on `ext-build` only: `maturin develop` found no pip in the uv-created venv ("if working with a uv venv try `maturin develop --uv`"); every other step passed: root 19 and core 55 Rust tests, clippy, fmt, ruff, ruff format, diff-check, **570 passed, 1 skipped**; load 50-96 from five concurrent check-all runs. Fix of the environment, not the tree: `uv pip install pip` into `.venv` |
| 2026-10-30 | big plan X1: WSL: `flock /home/gijsm/.rang-checkall.lock bash tools/check-all.sh` (coordinator's load rule), `OPENBLAS_NUM_THREADS=1 RAYON_NUM_THREADS=4`, after pip was added to `.venv` | – | lock wait 1,803 s (requested 13:25:24, acquired 13:55:27, load 80 then 22); run 229.3 s (pytest 153.6 s) | – | **overall PASS**: root 19 and core 55 Rust tests, clippy, fmt, `ext-build`, ruff, ruff format, diff-check, 570 passed and 1 skipped; the first run's FAIL was the venv. Logs in `outputs/x1-crossplatform-20261030-01/check-all/` |
| 2026-10-30 | big plan P5: `uv venv` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin psutil` | – | 1 min 20 s | – |  |
| 2026-10-30 | big plan P5: `maturin develop --release --offline` | – | 1 min 21 s | – |  |
| 2026-10-30 | big plan P5: `cargo build --release` (core) | – | 55 s | – |  |
| 2026-10-30 | big plan P5: bench `campaign` stations 0–3 (`k4-before`) | – | 45 s (run), 1 min 14 s (process) | 577 MB (bench); 621 MB `time -v` (includes `cargo`) |  |
| 2026-10-30 | big plan P5: bench `campaign` stations 0–7 (`s8-before`) | – | 44 s | 1,470 MB (bench) |  |
| 2026-10-30 | big plan P5: bench `campaign` stations 0–11 (`s12-before`) | – | 1 min 44 s | 2,909 MB (bench) |  |
| 2026-10-30 | big plan P5: `examples/precondition_luno_array.py` unmodified (`precondition-before`) | – | 39 s | 614 MB |  |
| 2026-10-30 | big plan P5: scratch score pre-check, stations 0–3 and 0–11 | – | 14 s, 43 s | 155 MB, 1.19 GB |  |
| 2026-10-30 | big plan P5: unmodified whole-array run (`array-before`) | – | 14 min 57 s | 13.2 GB at kill |  |
| 2026-10-30 | big plan P5: standalone P5 crate: build, test (11), clippy `-D warnings`, rustfmt (twice; one clippy fix `collapsible_if`, one rustfmt rewrite) | – | about 1 min each | – |  |
| 2026-10-30 | big plan P5: scratch unit checks, stations 0–3 (includes the first standalone build) | – | 48 s | 332 MB |  |
| 2026-10-30 | big plan P5: scratch unit checks, stations 0–11 | – | 40 s | 2.97 GB |  |
| 2026-10-30 | big plan P5: unmodified whole-array run from a pristine export (`array-before-b`), `time -v`, 8 threads, load 50–90 | – | **1 h 21 min 38 s** | **13,308,612 kB** |  |
| 2026-10-30 | big plan P5: bench `campaign` 0–3 with the group check (`k4-after`) | – | 45 s | 380 MB (bench) |  |
| 2026-10-30 | big plan P5: `precondition_luno_array.py` with P5 (`precondition-after`) | – | 51 s | 440 MB |  |
| 2026-10-30 | big plan P5: targeted pytest (`test_p5_memory`, `test_core_campaign_array`, `test_core_fetch`, `test_core_zarr`, `test_core_campaign`) | – | 41 s | 161 MB |  |
| 2026-10-30 | big plan P5: bench `campaign` 0–7 and 0–11 (`s8-after`, `s12-after`) | – | 1 min 30 s, 1 min 58 s | 646 MB, 885 MB (bench) |  |
| 2026-10-30 | big plan P5: coordinator lines in a scratch copy (`exttest.log`): uv venv, core build/test/clippy/fmt, `maturin develop`, extension clippy/fmt, pytest on both backends, bench through the extension | – | about 20 min (load 60–90) | – |  |
| 2026-10-30 | big plan P5: bench `campaign` 0–3 without the group check (`k4-after-b`) | – | 58 s | 366 MB (bench) |  |
| 2026-10-30 | big plan P5: bench `campaign` all stations (`array-after`), 4 threads, `OPENBLAS_NUM_THREADS=1`, load 36–70 | – | **37 min 28 s** | **10,406 MiB (bench composed)**; `time -v` 9,070,168 kB is invalid under the HWM reset |  |
| 2026-10-30 | big plan P5: `compare` after vs before; scratch archive comparisons (before and after vs L1) | – | seconds | – |  |
| 2026-10-30 | big plan P5: `flock /home/gijsm/.rang-checkall.lock bash tools/check-all.sh` (4 threads, `OPENBLAS_NUM_THREADS=1`; lock wait 0 s) | – | 3 min 24 s (pytest 586 passed, 1 skipped in 2 min 17 s) | 1.50 GB |  |
| 2026-10-30 | big plan L5: `cargo build --release` (core) | – | 54.5 s | – |  |
| 2026-10-30 | big plan L5: `validate_core_phase2.py` | – | 12.4 s | – |  |
| 2026-10-30 | big plan L5: `precondition_luno_campaign.py` (K) | – | 7.4 s | – |  |
| 2026-10-30 | big plan L5: `bench_core_f.py check --target solve` vs `core-f-20261029-01` | – | 5.2 s | – |  |
| 2026-10-30 | big plan L5: venv + `maturin develop` (setup) | – | 83 s | – |  |
| 2026-10-30 | big plan L5: precondition `-01` (build, validator, K precondition, bench) | – | 54.5 + 12.4 + 7.4 + 5.2 s | 151 MB |  |
| 2026-10-30 | big plan L5: compatibility `-02` (build 94 s, maturin 148 s, bench ×4, validator, K precondition) | – | ≈ 5 min | 151 MB |  |
| 2026-10-30 | big plan L5: `cargo test --release --lib solve::` | – | 2 min 45 s build, 9.3 s tests | – |  |
| 2026-10-30 | big plan L5: `pytest tests/test_l5_solver.py` | – | 3.5 s | – |  |
| 2026-10-30 | big plan L5: fixture sweeps `-03`, `-06`, `-08` | – | 57–59 s each | 205–211 MB |  |
| 2026-10-30 | big plan L5: slice sweeps `-04`, `-07`, `-09` | – | 63–84 s each | 231 MB |  |
| 2026-10-30 | big plan L5: diagnostic `-05` (slice, R to 5,000 iterations) | – | 4 min 46 s | 93 MB |  |
| 2026-10-30 | big plan L5: confirms `-10`…`-14` | – | 7–35 s each | 118–506 MB |  |
| 2026-10-30 | big plan L5: 32-station sweep `-15` | – | 52 min 50 s | 3.5 GB |  |
| 2026-10-30 | big plan L5: 32-station confirms `-16` (images), `-17` | – | 1 min 59 s, 43 s | 5.8 GB |  |
| 2026-10-30 | big plan L5: whole-array lean sweep `-18` | – | 25 min 41 s | 10.1 GB |  |
| 2026-10-30 | big plan L5: whole-array confirm `-19` (3 A/B pairs, images of D and C, 59 s and 55 s) | – | 4 min 38 s | 12.2 GB |  |
| 2026-10-30 | big plan L5: `flock ~/.rang-checkall.lock bash tools/check-all.sh` (`-20.check-all.log`), head 4f9f70e | – | 5 min 16 s (lock wait 0 s) | – |  |
| 2026-10-30 | big plan L5: `validate_core_phase2.py` `-21` on the check-all extension (Rust 1.93 build) | – | 2.1 s | – |  |
| 2026-10-30 | big plan U3: `git clone` DDFacet, killMS | GitHub | 10.8 s | – |  |
| 2026-10-30 | big plan U3: `uv pip install ./DDFacet` (v1.0.0.0) | source | 80.2 s | 874 MB | Python 3.12.15 |
| 2026-10-30 | big plan U3: `uv pip install DDFacet==0.9.1` | PyPI | 4.3 s | 72 MB | **failed**: astlib 0.13.2 on GCC 15; retries with CFLAGS 0.9-1.0 s, failed |
| 2026-10-30 | big plan U3: `uv pip install --no-deps ./killMS` (3.3.0) | source | 13.4 s | 68 MB | **failed**: `Gridder.c:309` |
| 2026-10-30 | big plan U3: same with `CFLAGS=-Wno-error=incompatible-pointer-types` | source | 13.3 s | 76 MB | built |
| 2026-10-30 | big plan U3: `uv pip install ./DDFacet ./killMS` (fix branch, no CFLAGS) | source | 132.7 s | 874 MB | built |
| 2026-10-30 | big plan U3: `gcc -c Gridder.c` before/after + `objdump` | one file | seconds | – | disassembly identical |
| 2026-10-30 | big plan U3: `uv build --sdist` licence branches | DDFacet, killMS | 0.9 s, 1.8 s | – | `GPLv2+` in PKG-INFO |
| 2026-10-30 | big plan U3: new `TestClassMSSelection` (pytest) | 3-row MS | 0.5-0.8 s | 106 MB | fails before, passes after |
| 2026-10-30 | big plan U3: `nosetests DDFacet.Tests.FastUnitTests` | 35 / 36 tests | 19.4 s / 17.9 s | 351 MB | OK / OK |
| 2026-10-30 | big plan U3: `DDF.py` dirty, default field 0 | LUNO slice copy, 128 px | 5.4 s (before), 2.2 s (after) | 296 / 279 MB | exit 1 both; new message after |
| 2026-10-30 | big plan U3: `DDF.py` dirty, `//F1` and `--Selection-Field 1` | same | 6.7 s, 6.6 s | 445 MB | exit 0 |
| 2026-10-30 | big plan U3: `DDF.py` Hogbom 3×3 facets, synthetic point source | slice geometry, 2048 ch, 512 px | 101.7 s | 8.9 GB | diverges to inf; CPU 299 % |
| 2026-10-30 | big plan U3: same, UVW ×30 | same | 104.2 s | 9.0 GB | diverges (8.3e15 Jy) |
| 2026-10-30 | big plan U3: same, 1 facet | same | 273.1 s | 21.5 GB | converges; CPU 71 % |
| 2026-10-30 | big plan U3: rang worktree venv (`uv venv -p 3.14` + editable install) | worktree | 61.7 s | 501 MB |  |
| 2026-10-30 | big plan U3: `flock ... bash tools/check-all.sh` | worktree at 6e7444b | 259.0 s; lock wait under 1 s | 1.58 GB | **FAIL**, not from U3: see below |
| 2026-10-30 | big plan U3: issue #75 snippet check (`field_snippet_check.sh`) | slice copy, 2 `DDF.py` runs | under 30 s | – | exit 0, then exit 1 as reported |
| 2026-10-30 | big plan E2: `docker build` of `tools/ms-reader` (`rang-ms-reader:local`), first try | Dockerfile | 0 s | — | started with `&` inside `wsl -e bash -lc`; died with the shell, empty log |
| 2026-10-30 | big plan E2: same, as a background tool run | Dockerfile | 28.3 s | 53 MB | python-casacore 3.8.1, NumPy 2.5.3 |
| 2026-10-30 | big plan E2: `uv venv` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin casacure` | worktree | 36.2 s | — | builds the extension |
| 2026-10-30 | big plan E2: `git clone` casacure | GitHub | 1.5 s | — | 4.7 MB, 240 commits |
| 2026-10-30 | big plan E2: casacure probe of the three MSs | 3 MSs | < 1 s | — | before the protocol (see the header) |
| 2026-10-30 | big plan E2: `eval_casacure.py reads` (R1, R2, R4) | oracle `-01`, 173 columns | 1.86 s | 285 MB | casacure reads 0.26 s in process; full columns 97 ms (`core_ms` 105 ms) |
| 2026-10-30 | big plan E2: container `describe`, `bigendian`, `taql` ×2 | 3 MSs | 0.99, 1.50, 0.77, 0.77 s | 31 MB | container start included |
| 2026-10-30 | big plan E2: casacure `describe`, `compare-describe` | 3 MSs | 0.09, 0.17 s | 43, 38 MB |  |
| 2026-10-30 | big plan E2: `eval_casacure.py bigendian` (R6) | 2 big-endian copies | 4.88 s | 276 MB | casacure and `core_ms` |
| 2026-10-30 | big plan E2: TaQL host / container, three rounds (scripts fixed between) | ms0, ms1 | 0.16–0.80 s / 0.61–1.86 s | 300–320 MB / 31 MB |  |
| 2026-10-30 | big plan E2: `eval_casacure.py write` W1(a, b) | fixture columns | 0.53 s | 226 MB |  |
| 2026-10-30 | big plan E2: `inplace` W4, `caltable` W5 | 2 copies; synthetic G | 0.55, 0.16 s | 221, 45 MB |  |
| 2026-10-30 | big plan E2: container read-backs (`oracle_ms_columns.py` ×5, `putflag`, `info`) | written tables | 0.54–1.27 s each | 30–31 MB | W1(b), W1(c) read-backs fail (casacore cannot open them) |
| 2026-10-30 | big plan E2: `write` variants c, d (post hoc) | fixture columns | 0.50, 0.59 s | 172 MB |  |
| 2026-10-30 | big plan E2: `eval_casacure_tiled_reference.py` (container) | — | 2.84 s | 30 MB |  |
| 2026-10-30 | big plan E2: `verify-writes` | `-04` | 1.07, 0.69 s | 433–451 MB |  |
| 2026-10-30 | big plan E2: `measures-cases` + container `measures` | 30 cases | 0.78 s | 31 MB |  |
| 2026-10-30 | big plan E2: `measures` (casacure, astropy) | 30 cases | 1.08 s | 170 MB |  |
| 2026-10-30 | big plan E2: `uvw` | LUNO, fixture | 0.93, 0.87 s | 169 MB | plus one scratch variant (CIRS/ERA and J2000/GMST) |
| 2026-10-30 | big plan E2: `cargo +1.93 fetch` + `cargo +1.93 build --release` of `examples/casacure_rs` | crate + 13 dependencies | 44.3 s | 499 MB | first build; rebuild 0.5 s; fmt and clippy clean |
| 2026-10-30 | big plan E2: `eval-casacure-rs` (R3) | 15 tables | 0.46 s | 128 MB |  |
| 2026-10-30 | big plan E2: copy MSs and oracle to the Windows scratchpad | 257 MB | 2.9 s | — |  |
| 2026-10-30 | big plan E2: Windows `uv venv` + `uv pip install casacure==3.8.35 numpy` | PyPI | failed, then 3.1 s | — | uv cache "too many temporary files"; retried with `UV_CACHE_DIR=~/Build/cache/uv` |
| 2026-10-30 | big plan E2: Windows `eval_casacure.py reads --no-core` (P1) | local copies | 1.17 s | 249 MB | 0.29 s in process |
| 2026-10-30 | big plan E2: same, in place over `\\wsl.localhost` | WSL outputs | 15.1 s | — | hashing over 9P dominates |
| 2026-10-30 | big plan E2: Windows `cargo +1.93 build --release` (P2) | crate | 17 s (fail); 13.1 s | — | fails without `date` on PATH (`celestial-eop-data` build script); passes with Git `usr\bin` on PATH |
| 2026-10-30 | big plan E2: Windows `eval-casacure-rs` + compare | 15 tables | 0.45 s | — |  |
| 2026-10-30 | big plan E2: performance runs (section 5), 5 repeats × 8 runs | LUNO, fixture | about 1 min | see the table |  |
| 2026-10-30 | big plan E2: `eval_casacure_robustness.py` | LUNO, fixture | 0.81, 0.79 s | 69, 72 MB | 8 child processes each |
| 2026-10-30 | big plan E2: casacure `cargo test --workspace --release` (stable 1.99.1) | clone | 87.1 s | 987 MB | 323 passed |
| 2026-10-30 | big plan E2: casacure `cargo +1.93 build -p casacure --release` | clone | 18.2 s | 498 MB |  |
| 2026-10-30 | big plan E2: casacure `maturin build` (for 3.14 by mistake, then 3.12) | clone | 25.2, 42.0 s | 517, 505 MB |  |
| 2026-10-30 | big plan E2: casacure `make_fixtures.py` + `pytest tests/` | clone | 28.6 s | 460 MB | the first attempt failed at collection (wheel for the wrong interpreter) |
| 2026-10-30 | big plan E2: python-casacore `addcols` on a LUNO copy (post hoc) | LUNO copy | < 2 s | — | container |
| 2026-10-30 | big plan E2: `uvw` rerun with the GCRS method (post hoc, after review) | LUNO, fixture | 1.02, 0.96 s | 170 MB | 4.1 and 3.3 mm |
| 2026-10-30 | big plan E2: python-casacore `truncate-after-open` probe (post hoc) | fixture copy | < 2 s | — | container; raises |
| 2026-10-30 | big plan E2: ghcr manifest and config of `tmolteno/killms:v3.15.12` | registry metadata | < 2 s | — | source label |
| 2026-10-30 | big plan E2: `RANG_CHECKALL_LOCKED=1 flock ~/.rang-checkall.lock bash tools/check-all.sh` | repository at `c183430` plus this table's edits | 287 s | 1.64 GB | PASS; pytest 634 passed, 3 skipped in 171 s (`RANG_CHECKALL_LOCKED=1`, because the script takes the same lock itself and would wait on the outer `flock`) |
| 2026-10-30 | big plan E2: `pytest tests/test_casacure_optional.py` | — | 0.52 s | 136 MB | 3 passed |
| 2026-10-30 | big plan A1: `uv venv` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` (public PyPI) | – | 38.3 s | – |  |
| 2026-10-30 | big plan A1: `maturin develop --release --offline` | – | 0.3 s | – |  |
| 2026-10-30 | big plan A1: `audit_emptied_bins.py run l2` under `/usr/bin/time -v` (MemAvailable 14 GiB) | – | 3 min 12 s | 3.38 GB |  |
| 2026-10-30 | big plan A1: `audit_emptied_bins.py run l1` (MemAvailable 25 GiB) | – | 5 min 24 s | 10.05 GB |  |
| 2026-10-30 | big plan A1: `summarise` (L2 only, then both, without figures) | – | 0.2 s | – |  |
| 2026-10-30 | big plan A1: `uv pip install -e '.[…,plot]'` (matplotlib, public PyPI) | – | 30.3 s | – |  |
| 2026-10-30 | big plan A1: `summarise` with archive and figures | – | 2.1 s | – |  |
| 2026-10-30 | big plan A1: scratch probe: input-FLAG coverage of the static channels by baseline length (both calibrators, labelled) | – | 5.8–7.4 s | 7.3 GB |  |
| 2026-10-30 | big plan A1: scratch probe: the rule that can run before the split against the emptied set, from `bins.npz` | – | about 1 s | – |  |
| 2026-10-30 | big plan A1: `ruff check --fix` / `ruff format` on the script | – | < 1 s | – |  |
| 2026-10-30 | big plan A1: `flock ~/.rang-checkall.lock bash tools/check-all.sh` (first attempt) | – | killed after about 20 min | – |  |
| 2026-10-30 | big plan A1: `bash tools/check-all.sh`, run plainly, once before the commit (`outputs/a1-rfi-audit-20261030-01/check-all.log`) | – | 4 min 15 s (pytest 631 passed, 3 skipped in 2 min 41 s) | 1.66 GB |  |
| 2026-10-30 | big plan P7: `tools/wheel/build.py` | worktree | 32.7 s | – | wheel-only acceptance wheel |
| 2026-10-30 | big plan P7: wheel-only acceptance suite (cargo absent) | archived inputs | about 120 s | – | F 32 s, signal 13 s, notebooks 18 s, trend 17 s; every archived verdict reproduced |
| 2026-10-30 | big plan P7: Windows clone / editable install / maturin develop / full pytest | native Windows, Rust 1.93 MSVC, CPython 3.14 | 7 / 64 / 67 / 153 s | – | 622 passed, 43 skipped, 0 failed |
| 2026-10-30 | big plan P7: golden archive generation (both old backends) | 5965d37 | 19 s | – | identical bytes |
| 2026-10-30 | big plan P7: `bash tools/check-all.sh` | branch, 664 tests | 3 min 9 s | – | PASS |
| 2026-10-30 | big plan DF1: `git clone` ducc (GitLab) + checkout | `ducc0_0_42_0` | 4.2 s | – | read-only reference; deleted at the end |
| 2026-10-30 | big plan DF1: `uv venv` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin ducc0==0.42.0` | worktree | 60.2 s | – |  |
| 2026-10-30 | big plan DF1: `maturin develop --release --offline` | worktree | 0.5 s | – |  |
| 2026-10-30 | big plan DF1: `oracle_ducc0.py export` | LUNO slice MS | 0.30 s | – | nvis 7,377, weight sum 129,363.328125 (study's numbers) |
| 2026-10-30 | big plan DF1: `oracle_ducc0.py synthetic` | 4 cases | 1.6 s | – |  |
| 2026-10-30 | big plan DF1: `oracle_ducc0.py convention` | `wide-0p3rad` | 0.42 s | – | `flip_w=True, divide_by_n=False` 9.2e-13 |
| 2026-10-30 | big plan DF1: `oracle_ducc0.py dft-slice` | slice, 512² | 47.4 s | – | dirty and PSF |
| 2026-10-30 | big plan DF1: `oracle_ducc0.py ducc` | synthetic, 4 ε | 0.86 s | – |  |
| 2026-10-30 | big plan DF1: `oracle_ducc0.py ducc` | slice, 4 ε | 0.29 s | – |  |
| 2026-10-30 | big plan DF1: `compare_core_wgridder.py item0` | slice | 48.1 s | – | 680 ducc0 calls for the aliasing prediction |
| 2026-10-30 | big plan DF1: `oracle_ducc0.py kerneldb` (first) | `gridding_kernel.cc` | 0.08 s | – | **failed**: 938 rows, the last row's `}};` not matched; fixed |
| 2026-10-30 | big plan DF1: `oracle_ducc0.py kerneldb` | same | 0.08 s | – | 939 rows, SHA256 `0427f594…` |
| 2026-10-30 | big plan DF1: `cargo build` standalone (first) | `df1-standalone` | 6.5 s | – | **failed**: trait bounds (13 errors); fixed |
| 2026-10-30 | big plan DF1: `cargo test` standalone | same | 32.1 s | – | **1 failed**: wrong expected `good_size_complex` values in the test (181 → 189, 1025 → 1029); test fixed |
| 2026-10-30 | big plan DF1: `cargo test` standalone | same | 39.5 s | – | 7 passed |
| 2026-10-30 | big plan DF1: `compare_core_wgridder.py gates` (smoke, labelled) | 2 synthetic cases | 77.7 s | – | includes a core library build; all checks pass |
| 2026-10-30 | big plan DF1: `compare_core_wgridder.py gates` | all cases | 33.6 s | – | **pass**; about 28 s was a standalone rebuild (wrapper rewrote its files each process; fixed later) |
| 2026-10-30 | big plan DF1: `compare_core_wgridder.py threads` | 1, 2, 4, 8, 16 | 141.0 s | – | identical; 26–30 s per process, the same rebuild |
| 2026-10-30 | big plan DF1: pytest `test_core_wgridder.py` | 6 tests | 37.4 s | – | pass |
| 2026-10-30 | big plan DF1: `cargo clippy -D warnings` standalone | same | 2.8 s | – | **failed**: 6 lints (needless range loops, `chunks_exact`, items after tests, negated comparisons); fixed |
| 2026-10-30 | big plan DF1: `cargo clippy -D warnings`, `rustfmt --check`, `cargo test` | same | 0.3 s, –, 26.8 s | – | clean; 7 passed |
| 2026-10-30 | big plan DF1: pytest `test_core_wgridder.py` without cargo on PATH | 6 tests | 0.7 s | – | **6 errors**: the shell lacked `~/.cargo/bin` (environment, not code); rerun below |
| 2026-10-30 | big plan DF1: pytest `test_core_wgridder.py test_core_grid.py` | 10 tests | 23.9 s | – | pass |
| 2026-10-30 | big plan DF1: `bench_df1.py time` smoke ×3 (labelled) | K `original` | 0.64 s / 28.5 s / 0.24 s | – | the 28.5 s was the rebuild; fixed (`_write_if_changed`), then 0.11 s per call |
| 2026-10-30 | big plan DF1: `bench_df1.py bench` | K six arms, 1/4/16 threads, 2 repeats | 35.0 s | – | table above |
| 2026-10-30 | big plan DF1: `bench_df1.py bench --single --epsilon 1e-4` | K six arms, 1/16 | 4.0 s | – |  |
| 2026-10-30 | big plan DF1: `bench_df1.py bench --tile 4/16/41` | K `original` | 3.9 / 9.1 / 18.4 s | – |  |
| 2026-10-30 | big plan DF1: `compare_core_wgridder.py science` + `run_core_gridder.py` | task C, 15 jobs | 7.9 s | – | driver criteria pass |
| 2026-10-30 | big plan DF1: `compare_core_gridder.py` (first) | C images | 0.26 s | – | **failed**: wrong candidate path (`c-run` instead of `c-run/images`); rerun 0.36 s |
| 2026-10-30 | big plan DF1: `compare_core_wgridder.py science` + `run_core_imaging.py` | task I | 8.4 s | – | exit 1: comparisons fail (reported above) |
| 2026-10-30 | big plan DF1: `compare_core_wgridder.py science` + `bench_p2_gridder.py k-replay` | task K | 0.15 s | – | **failed**: `outputs/core-k-20261030-01/fetch/result.json` no longer on the host |
| 2026-10-30 | big plan DF1: `compare_core_wgridder.py kpixels` | K six arms | 2.7 s | – |  |
| 2026-10-30 | big plan DF1: `compare_core_wgridder.py gates` / `threads` (final code) | all | 1.1 s / 2.5 s | – | all outputs identical to the first runs |
| 2026-10-30 | big plan DF1: `bash tools/check-all.sh` (takes the host lock itself) | worktree at `d682714` plus the uncommitted examples/research edits | 283.5 s | – | **PASS**: root 23 and core 60 Rust tests, clippy, fmt, extension build, ruff, format, diff check; pytest 637 passed, 3 skipped in 176.2 s; load 5–9; log `logs/check-all.log` |
| 2026-10-30 | big plan DF1: `compare_core_wgridder.py fitscheck` (post hoc) | slice uvw, w ×±100 | 12.8 s | – | `fits_image` and padded w-stacking agree to 5.3e-5, same peak pixel |
| 2026-10-30 | big plan DF1: probes (scratch scripts, not wrapped in `time`) | wide case, single rows, border and corner pixels | seconds each | – | edge difference scales with ε; not rounding |
| 2026-10-30 | big plan DF1: `cargo build` of a mirrored-tap prototype (scratch crate `core/target/df1-mirror`, deleted) | `wgridder.rs` copy | about 40 s (not wrapped) | – | mirrored taps change the edge difference only 1.7e-10 → 1.4e-10; not adopted |
| 2026-10-30 | big plan DF1: `bench_df1.py bench --impls ducc,wgrid` with `OMP_NUM_THREADS` unset (post hoc) | K six arms, 1/4/16 | 6.6 s | – | ducc0 0.039 s per image at 4 threads, 0.059 s at 16 |
| 2026-10-30 | big plan DF1: same, `--tile 41` | K `original` × 41 | 19.3 s | – | ducc0 2.35 / 0.69 / 0.38 s at 1 / 4 / 16 threads |
| 2026-10-30 | big plan DF1: `compare_core_wgridder.py summary`; ruff check, format check, `git diff --check` on the later edits | outputs, examples | under 1 s each | – | clean; result file with repository-relative paths |
| 2026-10-30 | big plan L1-M: `uv venv -p /usr/bin/python3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` (public PyPI) | – | 27.5 s | – |  |
| 2026-10-30 | big plan L1-M: `maturin develop --release --offline` | – | 0.3 s | 38 MB |  |
| 2026-10-30 | big plan L1-M: GitHub API (commit of the lsm, master) and `curl` of the lsm, LICENSE and master copy into `outputs/l1m-20261030-00-fieldmodel` | – | about 3 s | – |  |
| 2026-10-30 | big plan L1-M: download and unpack of the astro-tigger-lsm 1.8.0 wheel (PyPI, SHA256 `44e8516b…`) into the scratchpad, read only | – | about 2 s | – |  |
| 2026-10-30 | big plan L1-M: `curl` of CARACal's `crosscal_worker.py`, `crosscal_schema.yml`, `southern_calibrators.txt`, tree listing | – | about 3 s | – |  |
| 2026-10-30 | big plan L1-M: probe 1: phase centre, stored model vs A0, predictor sign and speed (all stations) | – | 10.9 s | 9.3 GB |  |
| 2026-10-30 | big plan L1-M: probe 2: lsm content and weights (stations 0–11) | – | 1.6 s | 0.45 GB |  |
| 2026-10-30 | big plan L1-M: **L1 precondition** unedited (`-00-precondition`) | – | 1 min 23 s | 568 MB |  |
| 2026-10-30 | big plan L1-M: probe 3: DFT check, PA bound, first ceiling (stations 0–11) | – | 38.5 s | 1.2 GB |  |
| 2026-10-30 | big plan L1-M: probe 4: stored − A0 structure (stations 0–11, then all) | – | about 12 s each | 7.1 GB |  |
| 2026-10-30 | big plan L1-M: probes 5–7: least-squares decomposition of the stored model onto the lsm | – | 9.5–12.8 s each | 7.1 GB |  |
| 2026-10-30 | big plan L1-M: probe 8: model-swap ceilings (stations 0–11; every other station) | – | 22.2 s; 2 min 9 s | 1.2 GB; 6.4 GB |  |
| 2026-10-30 | big plan L1-M: `fetch_l1m.py` (file present, hash verified) and the three four-station smokes (`-00-smoke-{stored,point,field}`, labelled) | – | 22.8 s, 23.3 s, 25.7 s | 0.87 GB each |  |
| 2026-10-30 | big plan L1-M: `check_l1m.py` on the smokes (`-00-smoke-check`, labelled) | – | about 15 s | 0.2 GB |  |
| 2026-10-30 | big plan L1-M: the new tests from the scratchpad (`pytest`, 25 then 26 tests) | – | 0.3–1.0 s | 70 MB |  |
| 2026-10-30 | big plan L1-M: **frozen stored run `-01-stored`** (`run_l1m.py` under `time -v`; MemAvailable 23 GiB, load 6) | – | **13 min 02 s** | **10.57 GB** |  |
| 2026-10-30 | big plan L1-M: frozen point run `-02-point` | – | 24 s | – |  |
| 2026-10-30 | big plan L1-M: targeted tests after amendment 2 (`test_lsm`, `test_core_campaign_fieldmodel`, `test_core_campaign_array`) | – | 0.2 s | – |  |
| 2026-10-30 | big plan L1-M: **frozen point run `-02b-point`** (MemAvailable 28 GiB, load 3–6) | – | **11 min 57 s** | **10.64 GB** |  |
| 2026-10-30 | big plan L1-M: **frozen field run `-03-field`** (MemAvailable 29 GiB) | – | **14 min 36 s** | **10.57 GB** |  |
| 2026-10-30 | big plan L1-M: `check_l1m.py` (`-04-check`) | – | 12.7 s | 0.21 GB |  |
| 2026-10-30 | big plan L1-M: `archive_l1m.py` | – | 0.1 s | 41 MB |  |
| 2026-10-30 | big plan L1-M: `bash tools/check-all.sh` (plain; it takes the host lock itself), once before the final commit (`outputs/l1m-20261030-check-all.log`) | – | 3 min 31 s (pytest 657 passed, 3 skipped in 1 min 58 s) | 1.65 GB |  |
| 2026-10-30 | big plan O-CASA: `uv venv -p /usr/bin/python3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` | worktree `o-casa`, public PyPI | 28.7 s | 638 MB |  |
| 2026-10-30 | big plan O-CASA: KERN-10 probes (apt versions, PyPI closure of casatools/casatasks, casalite deb listing), scratch | `ubuntu:24.04@sha256:fe815609…` + `ppa:kernsuite/kern-10` | ~1–3 min each | – |  |
| 2026-10-30 | big plan O-CASA: `build.sh` first image | Dockerfile + `requirements.lock` with the casatools `manylinux_2_34` wheel | 170.7 s | 53 MB (client) |  |
| 2026-10-30 | big plan O-CASA: `build.sh` final image | same with the `manylinux_2_28` wheel; apt layer cached | 56.1 s | – |  |
| 2026-10-30 | big plan O-CASA: labelled smoke `run.sh` ×6 | `-00-smoke` … `-00-smoke-f` | 5–90 s each | ≤ 521 MB |  |
| 2026-10-30 | big plan O-CASA: **`run.sh` `-01`** under `/usr/bin/time -v` | archived slice + solve inputs + `work.ms`, code `7162468` | 47.4 s | 521 MB |  |
| 2026-10-30 | big plan O-CASA: **`run.sh` `-02`** | same | 44.9 s | 521 MB |  |
| 2026-10-30 | big plan O-CASA: post-hoc WSClean `-j 1` ×2 (`posthoc.sh`, `-03-wsclean-j1`) | copy of `-01`'s `c.ms` | 0.91 s, 0.92 s | 77 MB |  |
| 2026-10-30 | big plan O-CASA: post-hoc arms E, F (`posthoc.sh`, `-04-arm-e`, `-05-arm-f`), solve + apply | copies of `-01`'s `work.ms` | 1.8 + 1.1 s each | 320 MB |  |
| 2026-10-30 | big plan O-CASA: `archive.py` | `-01`, `-02`, `-00-build2/image.json`, `-03`/`-04`/`-05` | < 1 s | – |  |
| 2026-10-30 | big plan O-CASA: `bash tools/check-all.sh`, once before the final commit | branch at `6ef269d` minus the commit itself (log `outputs/o-casa-20261030-01.check-all.log`) | 404.7 s (pytest 645 passed, 4 skipped in 120.3 s) | 1.53 GB |  |
| 2026-10-30 | big plan O-CASA: solve-c (setjy, K, G, B) | – |  | – |  |
| 2026-10-30 | big plan O-CASA: apply-c | – |  | – |  |
| 2026-10-30 | big plan O-CASA: solve-ch / restore / apply | – |  | – |  |
| 2026-10-30 | big plan O-CASA: solve-sh / restore / apply | – |  | – |  |
| 2026-10-30 | big plan O-CASA: flagdata tfcrop / rflag | – |  | – |  |
| 2026-10-30 | big plan O-CASA: setjy SR2016 / PB2010 | – |  | – |  |
| 2026-10-30 | big plan O-CASA: WSClean (`-j 4`) | – |  | – |  |
| 2026-10-30 | big plan O-CASA: summarize / compare (host) | – |  | – |  |
| 2026-10-30 | big plan P9: WSL: `uv venv` + editable install + `maturin develop --release --offline` | – | 60 s | – |  |
| 2026-10-30 | big plan P9: identity suite `before` at `f36ff80` (20 cases) | – | 6.8 s | – | outputs above |
| 2026-10-30 | big plan P9: identity suite `wrapper` (thin wrappers) | – | 5.7 s | – | identical to `before` |
| 2026-10-30 | big plan P9: identity suite `cli`, `cli-final` (`517e07b`), `cli-head` (`ed3e18c`) through `rang-core STAGE VERB` | – | 5.5 s, 7.9 s, 6.5 s | – | identical to `before` |
| 2026-10-30 | big plan P9: WSL: `rang-core check --all` at `902a74d` | – | 206 s (pytest 126 s) | – | PASS, 681 passed, 2 skipped |
| 2026-10-30 | big plan P9: thread caps, flags comparator, 5 pairs | – | 0.45–0.52 s each | – | 0.33–0.39 vs 1.15–1.18 user CPU-s |
| 2026-10-30 | big plan P9: bench smokes: P2 `bench` (one label, two runs), P1 `sweep` (one round) | – | 1.2 s, 1.8 s | – | hash-equal |
| 2026-10-30 | big plan P9: Windows: clone over `\\wsl.localhost` | – | 8.1 s | – | first attempt refused (`safe.directory`) |
| 2026-10-30 | big plan P9: Windows: `uv venv` + editable install (builds the extension) | – | 60.6 s | – |  |
| 2026-10-30 | big plan P9: Windows: `rang-core.exe check --all` at `902a74d` | – | 212 s | – | FAIL on ext-build only (launcher in use) |
| 2026-10-30 | big plan P9: Windows: `rang-core.exe check --all` at `252c823`; `python -m rangtoy.check --python` | – | 113 s; 105 s | – | FAIL on ext-build only (uv cache) |
| 2026-10-30 | big plan P9: Windows: `python -m rangtoy.check --only ext-build`; `rang-core.exe check --all` at `ed3e18c` | – | 1.9 s; 106 s | – | PASS, 640 passed, 44 skipped |
| 2026-10-30 | big plan P9: WSL: `bash tools/check-all.sh` at `ed3e18c` + report | – | 227 s (pytest 140 s) | – | PASS, 682 passed, 2 skipped |
| 2026-10-30 | big plan P9: identity `cli-head2` (`-m`) and `console` (`.venv/bin/rang-core`), final CLI | – | about 7 s each | – | identical to `before` |
| 2026-10-30 | big plan P9: legacy cab path `rang-core compare` on 7 real-archive cases | – | about 1 s | – | receipts minus `comparator` equal `before` |
| 2026-10-30 | big plan P9: WSL: `bash tools/check-all.sh`, after the review fixes | – | 157 s (pytest 150 s) | – | PASS at `00c4be2`, 683 passed, 2 skipped |
| 2026-10-30 | big plan C1: `uv venv -p /usr/bin/python3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` (public PyPI) | – | 45.2 s | 0.93 GB |  |
| 2026-10-30 | big plan C1: `maturin develop --release --offline` | – | 0.3 s | 37 MB |  |
| 2026-10-30 | big plan C1: probe 1 (closure SNR and weight scale, stations 0–11), run twice (scratch, then archived) | – | 12.1 s; 12.9 s | 0.54 GB |  |
| 2026-10-30 | big plan C1: standalone crate: rustfmt, `cargo test`, clippy `-D warnings`, build | – | 9.0 s | 0.29 GB |  |
| 2026-10-30 | big plan C1: `pytest tests/test_core_closure.py` | – | 3.6 s | 0.30 GB |  |
| 2026-10-30 | big plan C1: **L1 precondition** unedited (`-00-precondition`) | – | 9.9 s | 0.35 GB |  |
| 2026-10-30 | big plan C1: four-station smoke (`-00-smoke-4`, labelled) | – | 22.1 s | 0.87 GB |  |
| 2026-10-30 | big plan C1: R²_add debug on the four-station data (scratch) | – | about 3 s | 0.3 GB |  |
| 2026-10-30 | big plan C1: twelve-station smoke (`-00-smoke-12`, labelled) | – | 1 min 06 s | 1.34 GB |  |
| 2026-10-30 | big plan C1: `check_c1.py` and `archive_c1.py` on the smoke (`-00-smoke-check`, labelled) | – | 3.1 s | 55 MB |  |
| 2026-10-30 | big plan C1: targeted pytest (both C1 test files) | – | 0.4 s | 0.3 GB |  |
| 2026-10-30 | big plan C1: **frozen run `-01`** (`run_c1.py` under `time -v`; MemAvailable 27.5 GiB, load 1–2) | – | **19 min 48 s** | **10.9 GB** |  |
| 2026-10-30 | big plan C1: `check_c1.py` (`-02-check`) | – | 8.8 s | 0.21 GB |  |
| 2026-10-30 | big plan C1: `archive_c1.py` | – | 0.1 s | 40 MB |  |
| 2026-10-30 | big plan C1: `bash tools/check-all.sh` (plain; it takes the host lock itself), once before the final commit (`outputs/c1-20261030-check-all.log`) | – | 4 min 18 s (pytest 701 passed, 5 skipped in 2 min 06 s) | 1.66 GB |  |
| 2026-10-30 | big plan C1: post-hoc probe 2, the split-half null (`-03-posthoc`, labelled; MemAvailable 28 GiB) | – | 2 min 42 s | 9.0 GB |  |
| 2026-10-30 | big plan C1: `bash tools/check-all.sh` (plain), again before the commit of the post-hoc text (`outputs/c1-20261030-check-all-2.log`) | – | 1 min 41 s (pytest 701 passed, 5 skipped in 1 min 36 s) | 1.62 GB |  |
| 2026-10-30 | big plan E3: `git clone --depth 1 --branch v3.8.1 casacore` | 43 MB | 17.7 s | – | format reference, `~/Build/tmp/20261030-e3/casacore-src` |
| 2026-10-30 | big plan E3: `uv venv` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin casacure==3.8.35` | worktree | 41.4 s | – |  |
| 2026-10-30 | big plan E3: determinism inventory, python-casacore 3.8.1 in `rang-ms-reader:local` | 19 cases × 2 copies | 4.2 s | – | container included |
| 2026-10-30 | big plan E3: `cargo +1.93 test` (core, 85 tests, fixture set) | `core/` | 35.8 s | – | build included; 0.8 s of tests |
| 2026-10-30 | big plan E3: `maturin develop --release --offline` (with the binding lines) | extension | 31–43 s | – |  |
| 2026-10-30 | big plan E3: `pytest tests/test_core_ms_write.py tests/test_core_ms.py` | fixture, LUNO | 4.5 s | – | 9 passed, 4 skipped (before the oracle run) |
| 2026-10-30 | big plan E3: `oracle_ms_write.py write` (run `-01`) | 24 cases | 2.7 s | – | container included |
| 2026-10-30 | big plan E3: `oracle_ms_write.py scale-build` / `scale-write` | 2 tables, 342 M flags | 0.6 s / 2.3 s | – | container; casacore `putcol` 0.056 s and 0.089 s |
| 2026-10-30 | big plan E3: `check_ms_writer.py cases` (`-02`) | 24 cases | 2.1 s | – |  |
| 2026-10-30 | big plan E3: `check_ms_writer.py readback` | 48 tables | 6.3 s | – | container 3.4 s |
| 2026-10-30 | big plan E3: `check_ms_writer.py roundtrip` | 41 tables | 3.4 s | – | casacore container 1.1 s, read-back container 1.0 s |
| 2026-10-30 | big plan E3: `check_ms_writer.py reader` | task E oracle | 0.9 s | – |  |
| 2026-10-30 | big plan E3: `check_ms_writer.py addcols` | 6 columns | 4.3 s | – | 6 containers |
| 2026-10-30 | big plan E3: `check_ms_writer.py locks` | fixture copies | 22.2 s | – | includes the 12 s and 8 s holds |
| 2026-10-30 | big plan E3: `check_ms_writer.py serialisation` | 41 tables | 0.07 s | – |  |
| 2026-10-30 | big plan E3: `check_ms_writer.py scale` | 2 × 342 M flags | 0.7 s | – | peak RSS 460 MB (input 342 MB) |
| 2026-10-30 | big plan E3: `check_ms_writer.py locks` post hoc (`-03`) | fixture copies | 22.4 s | – |  |
| 2026-10-30 | big plan E3: `check_ms_writer.py scale` post hoc (`-04`) | 2 × 342 M flags | 0.7 s | – | peak reset per table |
| 2026-10-30 | big plan E3: `oracle_ms_write.py write` post hoc (`-05`) | 24 cases | 2.9 s | – | container; padding comparison with `-01` |
| 2026-10-30 | big plan E3: `bash tools/check-all.sh` (with the wiring diff of the appendix present) | repo | 3.5 min | – | PASS: root 23, core 85 Rust tests; pytest 661 passed, 3 skipped (98 s); log `outputs/e3-20261030-02/check-all.log` |
| 2026-10-30 | big plan FS1: oracle_setjy.py (docker) | run fs1-20261030-01 | 166.1 s | 295 MB | 114 arrays |
| 2026-10-30 | big plan FS1: oracle_setjy.py --dense-1934 | fs1-20261030-03 | 29.8 s | 282 MB | 303 SPWs |
| 2026-10-30 | big plan FS1: oracle_setjy.py rerun | fs1-20261030-04 | 146.2 s | 293 MB | bit-identical to 01 |
| 2026-10-30 | big plan FS1: oracle_setjy.py --reread-ocasa | fs1-20261030-05/-06 | 1.8 / 1.6 s | 351 MB | 06 is evidence |
| 2026-10-30 | big plan FS1: uv venv + install | worktree | 63.4 s | 891 MB | |
| 2026-10-30 | big plan FS1: check_fluxstd.py | 01,03,04,06,O-CASA | 0.1 s | 46 MB | all acceptance true |
| 2026-10-30 | big plan FS1: bash tools/check-all.sh | eb88550 / 078eb4f | 333.5 / 214.8 s | 1.67 / 1.59 GB | PASS, 698 passed 5 skipped |
| 2026-10-30 | big plan L4: `examples/verdict_tables.py --check` | 11 archives | 0.04 s | 20 MB | stdlib |
| 2026-10-30 | big plan L4: `bash tools/check-all.sh` | branch l4-verdict | 8 min 25 s incl. lock wait | 1.6 GB | PASS, 726 passed 5 skipped (pytest 150.6 s) |
| 2026-10-30 | big plan P11: venv (uv) and `maturin develop --release --offline` | – | about 2 min | – |  |
| 2026-10-30 | big plan P11: suite `-01` under coverage, base | – | 134 s (steps) | – |  |
| 2026-10-30 | big plan P11: suite `-01b` (`bench f`), base | – | 36 s | – |  |
| 2026-10-30 | big plan P11: suite `-01r`, base repeat | – | 164 s | – |  |
| 2026-10-30 | big plan P11: suite `-02`, extracts, frozen present | – | 169 s | – |  |
| 2026-10-30 | big plan P11: suite `-02b` (phase 3c-a, `bench f`) | – | 41 s | – |  |
| 2026-10-30 | big plan P11: suite `-03`, after the move | – | 174 s | – |  |
| 2026-10-30 | big plan P11: targeted pytest (new live copies) | – | 2.4 s | – |  |
| 2026-10-30 | big plan P11: targeted pytest (rewired tests, notebooks) | – | 23 s | – |  |
| 2026-10-30 | big plan P11: pytest collect-only at the base (temporary worktree, removed) | – | 2.4 s | – |  |
| 2026-10-30 | big plan P11: `bash tools/check-all.sh` at `61e3b26` | – | 482 s (pytest 136 s) | – |  |
| 2026-10-30 | big plan P11: suite `-04` at `a04766d` | – | 170 s (steps) | – |  |
| 2026-10-30 | big plan P11: `archive` verbs and `imaging legacy-archive` on `-01r` and `-04` | – | about 10 s | – |  |
| 2026-10-30 | big plan P11: `bash tools/check-all.sh` at the final tree | – | 196 s (pytest 106 s) | – |  |
| 2026-10-30 | big plan DF2a: `git clone` ducc (GitLab) + checkout | `ducc0_0_42_0` | 3.2 s | – | read-only reference; deleted at the end |
| 2026-10-30 | big plan DF2a: `uv venv` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin ducc0==0.42.0` | worktree | 45.2 s | – |  |
| 2026-10-30 | big plan DF2a: `maturin develop --release --offline` | worktree | 43.4 s | – |  |
| 2026-10-30 | big plan DF2a: `perf record` of DF1 (labelled) | K × 41, one thread | 7.7 s (not wrapped) | – | **inconclusive**: perf could not resolve the cdylib's symbols; replaced by scratch experiments |
| 2026-10-30 | big plan DF2a: `bench_df2.py refs` (DF1 code) | gate cases, K, K × 41, array | 19.8 s | – | 55 arrays; 20 gated hashes equal DF1's archive |
| 2026-10-30 | big plan DF2a: `bench_df2.py bench` DF1 baseline | K / K × 41 / array, 1/4/16, 3 repeats | 15.0 / 46.8 / 254.9 s | – | interleaved with ducc0 |
| 2026-10-30 | big plan DF2a: `cargo build` standalone (first, step c) | `df1-standalone` | 0.2 s | – | **failed**: 5 errors (closures capturing raw pointers); fixed |
| 2026-10-30 | big plan DF2a: `cargo build` + `cargo test` standalone (per step, 9 builds) | same | 28–41 s + 36–44 s | – | 7 passed each time |
| 2026-10-30 | big plan DF2a: `bench_df2.py compare` (first) | step c | 24.0 s | – | **failed**: summary key error in the script (zero-data counters); fixed |
| 2026-10-30 | big plan DF2a: probes (scratch scripts, labelled) | edge pixels per border width, PSF identity, K plans | seconds each | – |  |
| 2026-10-30 | big plan DF2a: `bench_df2.py bench` quick (wgrid, 1 repeat) ×8 steps | K / K × 41 / array, 1/4/16 | 2.4–5.5 / 4.3–19.9 / 19.0–61.9 s | – | table "Per step" |
| 2026-10-30 | big plan DF2a: scratch experiment crates (labelled) ×10 | K × 41, array, one thread | 40–80 s each | – | taps/accumulation split, FMA, AVX-512, store forwarding, split loops, even/odd |
| 2026-10-30 | big plan DF2a: `cargo rustc --emit asm` (scratch, labelled) | experiment crate | ~40 s ×2 | – | accumulation found unvectorised |
| 2026-10-30 | big plan DF2a: `compare_core_wgridder.py gates` ×4 | all cases | 7.0–7.4 s | – | pass every time |
| 2026-10-30 | big plan DF2a: `compare_core_wgridder.py threads` ×4 | 1, 2, 4, 8, 16 | 13.3–20.0 s | – | identical every time |
| 2026-10-30 | big plan DF2a: `bench_df2.py compare` ×6 | all reference outputs | 8.4–12.9 s | – |  |
| 2026-10-30 | big plan DF2a: `compare_core_wgridder.py hashes` per SIMD level ×4 runs | gate cases | 2.1–2.6 s each | – | identical at every level |
| 2026-10-30 | big plan DF2a: plane-group experiment (`groups.sh`) | K / K × 41 / array, G 1–8, 1/16 | about 4 min (not wrapped) | – | table "(a)" |
| 2026-10-30 | big plan DF2a: `cargo clippy -D warnings` standalone (first) | same | 2.7 s | – | **failed**: 2 lints (`as_deref_mut` on a reference); fixed, clean |
| 2026-10-30 | big plan DF2a: pytest `test_core_wgridder.py test_core_grid.py` (first) | 11 tests | 39.2 s | – | **1 failed**: the new test asked for f32 at ε 1e-7 (no kernel); test fixed |
| 2026-10-30 | big plan DF2a: pytest same | 11 tests | 0.4 s | – | pass |
| 2026-10-30 | big plan DF2a: `bench_df2.py edge` (first) | 2 cases × 4 ε | 5.9 s | – | **failed**: ducc0 called with its default `do_wgridding=False`; fixed |
| 2026-10-30 | big plan DF2a: `bench_df2.py edge` | same | 6.8 s | – | table "(f)" |
| 2026-10-30 | big plan DF2a: f32 probe (labelled) | K arms | 0.9 s | – |  |
| 2026-10-30 | big plan DF2a: `bench_df2.py bench` final | K / K × 41 / array / K f32, 3 repeats | 24.0 / 50.2 / 118.1 / 9.0 s | – | load 2–5 |
| 2026-10-30 | big plan DF2a: `bench_df2.py bench` repeat (labelled) | K / K × 41 | 11.4 / 22.4 s | – | load 3.8–4.1 |
| 2026-10-30 | big plan DF2a: `bench_df2.py summary` | both runs | < 1 s | – | `research/results/df2-wgridder-speed.json` |
| 2026-10-30 | big plan DF2a: DF2a against DF1 over the correction (post-hoc probe, scratch script) | 0.3 rad cases, f64 ε 1e-7 | 0.8 s | – | flat: 1.8e-14 border and inside (`df2-vs-df1-correction.json`) |
| 2026-10-30 | big plan DF2a: `bash tools/check-all.sh` (takes the host lock itself; wall from timestamps, not wrapped) | worktree at `7240935` | 293.1 s | – | **PASS**: root 23 and core 74 Rust tests, clippy, fmt, extension build, ruff, format, diff check; pytest 656 passed, 4 skipped in 96.2 s; log `outputs/df2-20261030-02/logs/check-all.log` |
| 2026-10-30 | big plan PC1: venv at the worktree (`uv venv`, `uv pip install`, `maturin develop --release --offline`) | – | about 2 min | – |  |
| 2026-10-30 | big plan PC1: `precondition_luno_array.py` at `f6d6a96` (`-01-l1`) | – | 9.3 s | 349 MB | reproduces: image-only fail |
| 2026-10-30 | big plan PC1: `precondition_luno_1830.py` at `f6d6a96` (`-01-l2`) | – | 6.2 s | 150 MB | reproduces: `ValueError` |
| 2026-10-30 | big plan PC1: bisect worktrees and venvs, four commits | – | about 30 s each | – | `uv` and cargo caches warm |
| 2026-10-30 | big plan PC1: bisect runs `-02` to `-05` | – | 1.5–1.8 s each | 120–126 MB | harness failure: no `cargo` on `PATH` for the pre-P7 ctypes build |
| 2026-10-30 | big plan PC1: L1 precondition at `4584936` (`-06`) | – | 47.9 s | 309 MB | pass |
| 2026-10-30 | big plan PC1: L1 precondition at `cbf9003` (`-07`) | – | 33.7 s | 622 MB | fail, image-only |
| 2026-10-30 | big plan PC1: L2 precondition at `a279d34` (`-08`) | – | 34.9 s | 626 MB | pass |
| 2026-10-30 | big plan PC1: L2 precondition at `29d67b4` (`-09`) | – | 28.9 s | 627 MB | fail, `ValueError` |
| 2026-10-30 | big plan PC1: L1 precondition with the fix (`-10`) | – | 8.7 s | 333 MB | pass |
| 2026-10-30 | big plan PC1: L2 precondition with the fix (`-11`) | – | 8.8 s | 310 MB | pass |
| 2026-10-30 | big plan PC1: `check_c1.py` against the new precondition (`-12`) | – | 4.3 s | 209 MB | all criteria pass |
| 2026-10-30 | big plan PC1: `check_l1m.py` against the new precondition (`-13`) | – | 12.4 s | 209 MB | all criteria pass |
| 2026-10-30 | big plan PC1: `precondition_luno_campaign.py` (`-14`) | – | 1.7 s | 150 MB | all pass |
| 2026-10-30 | big plan PC1: pytest, the two new tests | – | 17.7 s | – | 2 passed |
| 2026-10-30 | big plan PC1: `bash tools/check-all.sh` (`-15-check-all.log`) | – | 4 min 44 s | 1.9 GB | PASS: 106 Rust tests, clippy, fmt, ruff, 599 passed and 5 skipped in pytest |
| 2026-10-30 | big plan PC1: `bash tools/check-all.sh` plain, after the report fixes (`-16-check-all.log`) | – | 2 min 0 s | – | PASS: 599 passed and 5 skipped in pytest |
| 2026-10-30 | CLEAN theory: `cargo test --release --manifest-path core/Cargo.toml clean::` | core crate, 5 new tests | 63 s (build; tests 0.00 s) | – | Windows workstation, native; [clean-theory.md](clean-theory.md) |
| 2026-10-30 | CLEAN theory: `clean_theory` example, four MeerKAT configurations, E1-E6 | 64 antennas; 2,016 and 26,208 visibilities; 64² grid | 68.8 s compute (2 min 54 s with the release build) | – | PSFs 0.02-0.33 s; CG for Q_∞ 3-4 s each; E2 (9,600 CLEAN runs) dominates; `results/clean-theory.json` |
| 2026-10-30 | CLEAN theory: `lake update mathlib && lake exe cache get` | Mathlib v4.33.1, 8,690 cached files | 290 s | – | Windows, first time, clone included; `formal/.lake` ignored |
| 2026-10-30 | CLEAN theory: `lake build` (`Clean.lean` + axiom audit) | `formal/` | 44 s (48.9 s first build) | – | all but 2 s is loading Mathlib |
| 2026-10-30 | CLEAN theory: `python -m rangtoy.check` on native Windows (`.venv\Scripts\python`) | repo at the `clean-theory` branch tip | 321 s (first attempt 228 s) | – | root 23 and core 111 Rust tests, clippy, fmt, extension build, ruff, format, diff check PASS; pytest 537 passed, 31 skipped, **37 failed**, all pre-existing Windows-environment failures in untouched modules (`test_core_closure` builds `core/target/c1-standalone` with an unescaped Windows path in `core_closure.py`; `test_p11_extract`, `test_core_wgridder`, `test_core_grid`, `test_fluxstd`); the first attempt failed earlier because the venv lacked maturin (installed 1.16.0) |
| 2026-10-30 | big plan B1: zip central-directory probe of `MeerKAT_L_band_primary_beam.npz` by HTTP range | – | ~5 s | – |  |
| 2026-10-30 | big plan B1: small arrays + metrics file | – | 9.1 s | 83 MB |  |
| 2026-10-30 | big plan B1: upstream sources, shallow clones | – | – | – |  |
| 2026-10-30 | big plan B1: fixture extract | – | ~3 s | – |  |
| 2026-10-30 | big plan B1: ESO137 metadata probe | – | 74.3 s + 2.2 s | 26 MB / 45 MB |  |
| 2026-10-30 | big plan B1: Python urllib, zip central-directory probe | L-band npz, 6 range reads | ~5 s | – | not timed; member offsets and npy headers |
| 2026-10-30 | big plan B1: Python urllib, small arrays + metrics npz | 4 range reads + 28,235,140 B | 9.1 s | 83 MB | `b1-20261030-01` |
| 2026-10-30 | big plan B1: git shallow clones + wheel | 3 GitLab repos, scikits.fitting 0.7.2 | – | – | not timed; `b1-20261030-02-ska-pointing-src` |
| 2026-10-30 | big plan B1: Python zipfile, fixture extract | `outer_scans.zip` | ~3 s | – | not timed; `b1-20261030-03-fixture` |
| 2026-10-30 | big plan B1: Python urllib, ESO137 S3 listing + `.zarray` probe | 3 stores, 15 MAIN groups | 74.3 s | 26 MB | latency-bound listings |
| 2026-10-30 | big plan B1: core blosc decode, PHASE_DIR / CHAN_FREQ | 5 small chunks | 2.2 s | 45 MB |  |
| 2026-10-30 | big plan B1: uv venv + install, `maturin develop --release --offline` | worktree | 0.35 s (maturin) | 37 MB | extension already built in the checkout's target |
| 2026-10-30 | big plan B1: Python urllib, holography product fetch | 24,320 + 64 range reads, 3.72 GB | 1993.4 s | 6.9 GB | about 1.9 MB/s; RSS is the memmap's resident pages; user 82 s, sys 33 s |
| 2026-10-30 | big plan B1: `examples/b1_baselines.py` G1a, run 1 | fixture, 5 scans | 0.65 s | 226 MB | **failed**: refused a fully flagged reference antenna (upstream keeps it) |
| 2026-10-30 | big plan B1: `examples/b1_baselines.py` G1a, run 2 | fixture | 1.20 s | 221 MB | **G1a failed**: 4.4e-6 rad; current datamodels time stamps |
| 2026-10-30 | big plan B1: `examples/b1_baselines.py` G1a, run 3 | fixture | ~1.2 s | – | pass, 8.9e-16; wall not captured (the run 4 row times the same code) |
| 2026-10-30 | big plan B1: scikits.fitting 0.7.2 oracle | 56 chunk fits | 0.99 s | 87 MB | separate venv; 0.0′ difference |
| 2026-10-30 | big plan B1: EIDOS 1.1.2 probe, three attempts | 3 frequencies | 0.9 s each | 112 MB | **failed**: `recon_par` location; NumPy 2.5.4 refuses `np.sum(generator)` inside EIDOS (an error since 2.4.0); scipy `spline_filter` has no `axes` |
| 2026-10-30 | big plan B1: EIDOS probe, re-expressed reconstruction | 3 frequencies | 1.64 s | 131 MB | 0.2 s per channel |
| 2026-10-30 | big plan B1: `examples/b1_beam_product.py`, smoke | every 20th channel | 1.79 s | 2.93 GB |  |
| 2026-10-30 | big plan B1: `examples/b1_beam_product.py`, full | 82 channels, 815 held-out channels | 23.3 s | 4.17 GB | rerun with the compact archive 23.8 s, 4.17 GB |
| 2026-10-30 | big plan B1: `examples/b1_baselines.py` with G1b, run 4 | fixture + 13 injections × 200 seeds | 55.9 s | 494 MB | baseline 0.37 s, sep-pol 0.38 s, G1b 54.5 s |
| 2026-10-30 | big plan B1: post-hoc EIDOS flip check | 82 channels × 2 flips | 36.1 s | 717 MB | labelled post hoc |
| 2026-10-30 | big plan B1: pytest, the two new test files | 13 tests | 1.6 s | – |  |
| 2026-10-30 | big plan B1: `bash tools/check-all.sh` | worktree | 254.8 s | 1.67 GB | PASS; pytest 739 passed, 5 skipped in 123.9 s; log `outputs/b1-20261030-check-all.log` |
| 2026-10-30 | big plan B1: post-hoc squint decomposition of G1b | 4 antennas × 14 chunks | 2.65 s | 296 MB | first attempt gave NaN (NaN-σ chunks not excluded); `squint.log` is the rerun |
| 2026-10-30 | big plan B1: post-hoc stuck-chunk check | fixture amplitudes | ~1 s | – | not timed; `stuck.log` |
| 2026-10-30 | big plan B1: `bash tools/check-all.sh`, after the post-hoc edits | worktree | 95 s | – | PASS; pytest 739 passed, 5 skipped in 91.6 s (Rust steps cached); log `outputs/b1-20261030-check-all-2.log` |
| 2026-10-30 | CLEAN theory (continued): `clean_theory` example with E2c and E7 | four MeerKAT configurations | 71.1 s compute | – | Windows; E2c 100 trials × 5 k per config, E7 Gram-exact blob inner products |
| 2026-10-30 | CLEAN theory (continued): `lake build` with `FiniteDim.lean`, `Projection.lean` and the audit | `formal/` | 40.6 s | – | thirteen theorems, standard axioms only |
| 2026-10-30 | big plan P12: venv + editable install, before / after (WSL, uv) | – | 69 s / 64 s | – |  |
| 2026-10-30 | big plan P12: targeted pytest (pc1, notebooks, P11, receipts, CLI), before / after / final | – | 31.7 s / 29.6 s / 24.6 s | – |  |
| 2026-10-30 | big plan P12: P9 identity suite through `rang-core`, before / after / final | – | 6.2 s / 6.2 s / 8.1 s | – |  |
| 2026-10-30 | big plan P12: full pytest, before / after | – | 168.2 s / 165.0 s | – |  |
| 2026-10-30 | big plan P12: `bash tools/check-all.sh` at `86e2a8d` (cold extension build) / `0085b36` | – | 334.9 s / 134.8 s | – |  |
| 2026-10-30 | big plan P12: `rang-core check` (Linux) | – | 132.5 s | – |  |
| 2026-10-30 | big plan P12: `tools/wheel/build.py` Linux, `86e2a8d` / `0085b36` | – | 73.8 s / about 70 s (maturin step 67.2 s) | – |  |
| 2026-10-30 | big plan P12: `tools/wheel/test.py` Linux | – | 11.1 s | – |  |
| 2026-10-30 | big plan P12: Windows clone / venv / editable install (MSVC extension) | – | 11.5 s / 0.1 s / 124.8 s | – |  |
| 2026-10-30 | big plan P12: Windows `rang-core check`, `86e2a8d` (FAIL, pre-existing) / `0085b36` (PASS) | – | 339.8 s / 112.3 s | – |  |
| 2026-10-30 | big plan P12: Windows `build.py` / `test.py`, at `86e2a8d` and at `0085b36` | – | 102.9 s and 102.2 s / 8.7 s and 8.7 s | – |  |
| 2026-10-30 | big plan P12: Windows clone of main, install and the 4 failing test files | – | 140.5 s | – |  |
| 2026-10-30 | big plan P12: `build.py --sdist` Linux / `maturin build` from the unpacked sdist | – | 62 s / 68 s | – |  |
| 2026-10-30 | CLEAN implicit objective: full Rust checks before the first commit (fmt, clippy, test) | worktree | 137 s | – | Windows; 111 tests pass |
| 2026-10-30 | CLEAN implicit objective: `clean_implicit`, first version with a coordinate-descent lasso | first case only | about 9 min, aborted | – | negative: coordinate descent crawls on correlated atoms; replaced by an exact homotopy |
| 2026-10-30 | CLEAN implicit objective: `clean_implicit` with the lasso homotopy, three levels | 4 cases | 9.5 s | – | |
| 2026-10-30 | CLEAN implicit objective: `clean_implicit`, five levels, tied-set eigenvalues on every path | 4 cases | 147.9 s | – | 50 s of it on the γ = 1 run's huge tolerance sets; eigenvalues then restricted to FS |
| 2026-10-30 | CLEAN implicit objective: `clean_implicit`, final run | 4 cases, 5 levels | 36.5 s | – | deterministic (identical to the previous run but timings); track disc 28.7 s, other cases 0.7-3.9 s |
| 2026-10-30 | CLEAN implicit objective: `lake build RangFormal.Stagewise`, first build / rebuild after fixes | `formal/` | 248 s / 22 s | – | first build ran alongside the aborted example |
| 2026-10-30 | CLEAN implicit objective: `lake build` of `Separation` and `Clark`, failing / passing | `formal/` | 38 s / 38 s | – | |
| 2026-10-30 | CLEAN implicit objective: clean `lake build` of all seven files and the audit | `formal/` | 121 s | – | 33 theorems, standard axioms only |
| 2026-10-30 | CLEAN implicit objective: fmt check / clippy / test, after the example (incremental) | worktree | 1 s / 0.3 s / 3 s | – | |
| 2026-10-30 | CLEAN implicit objective: `lake build` after adding `stagewise_pick_optimal` | `formal/` | 120 s | – | Stagewise and its dependents rebuilt; 34 theorems, standard axioms only |
