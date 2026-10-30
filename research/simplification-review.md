# Simplification and optimisation review (big plan task S1)

Written 2026-10-30 on branch `simplification-review` (from origin/main
`df42ea0`) as task S1 of [big-plan.md](big-plan.md). Status: **measured
review; no code changed.** Every number below was measured in this task
unless a source is cited; estimates are labelled as estimates with their
reasoning. Profiles, the inventory and the measurement scripts are in
[results/profiles-20261030/](results/profiles-20261030/); raw run
directories are `outputs/simplification-review-20261030-NN` (ignored).

## Summary

- **The core is single-threaded and FFT-bound at four stations.** In the
  task K chain replayed offline (fetch excluded), 87 % of samples are in
  Rust, 7 % NumPy, under 1 % Python glue; every kernel stage keeps exactly
  one of the host's 16 hardware threads busy (8 physical cores with SMT).
  The six dirty images take 67 % of the non-fetch time, and 83 % of each
  image is the hand-written Bluestein FFT (radix-2 at 2,048 points for a
  616-point padded grid).
- **Memory, not time, blocks the whole array.** The chain peaks at about
  0.87 kB per visibility cell (row × channel, four correlations) against
  84 B of input arrays; at LUNO chunk 0 with 56 stations (100.9 M cells)
  that is about 88 GB against 30 GiB on the host. The amplification is
  Python-side: complex128 residuals retained per arm, NumPy gain
  correction with 2 × 2 temporaries, and 40-byte gridder samples built
  twice.
- **Every archive reproduces today.** The timed suite re-ran the core
  drivers, checkers and comparators against their archives (29 steps: K
  precondition and checker, section 6, phase 2, task F, actions,
  injections, prospective, signal, trend, B, C, D, E, I and the offline K
  replay), and a second batch ran the phase 1 and 3c-a validators, the
  task G fetch checker and the backends comparator against task J's
  suite. Every one reproduces its archived outcome (phase 1 as archived:
  criterion 4 fails as frozen, post-hoc 4b passes), and the offline K
  replay reproduces the archived gains, dirty images and PSFs of three
  arms hash for hash. Not re-run: the oracle generators (containers) and
  the network fetch.
- **Two zero-code wins are measured and bit-identical:** a release
  profile with thin LTO and one codegen unit (−5 % instructions) and
  `x86-64-v3` code generation (−22 % instructions, −24 % to −40 %
  cycles on the K replay); gains, flags, images and the blosc bytes are
  hash-identical.
- **The solver's 50-iteration cap is not convergence.** Held-out MSE is
  within 2e-4 relative of its archived value after 5 iterations and 2e-5
  after 12 (the decision band is ±1 %), but baseline products still move
  1.3e-3 between iteration 50 and 91 (where 99 % of intervals converge).
  Any change to the cap or the criterion moves archived gains far beyond
  their 1e-6 tolerance, so it is a science protocol, not an engineering
  task.
- **Top five proposals** (section 3): P2 gridder (mixed-radix FFT, w-layers
  in parallel, samples bucketed once; about 3.5 s → 0.15–0.3 s per image);
  P5 memory (about 0.87 → 0.15 kB per cell, whole array 88 → about 15 GB);
  P1 solver (rayon over solution intervals, bit-identical; whole-array
  solve estimated 89 s → about 13 s); P3 SumThreshold over baselines
  (bit-identical; whole-array first pass estimated 7 min → about 1 min);
  P0 build profile (−22 % instructions, no code). Then the frozen Python
  hot spots (trend 31 s, signal 35 s), the eigensolver, the test suite
  (98 % of its time in three pointing modules), retiring 23 frozen
  recipes, 8 Dockerfiles and 2,626 recipe-only module lines to `history/`,
  the ctypes path once the wheel lands, and finally the frozen modules
  themselves, of which the live chains execute 31 %.

## 1. Inventory

Counted by `inventory.py` on `df42ea0` ([inventory.json](results/profiles-20261030/inventory.json)).

| Unit | Count | Lines | Live | Frozen / history |
| --- | ---: | ---: | --- | --- |
| Rust files (root crate `src/`, `core/src/`, `core/py/src/`) | 24 | 11,494 | all | – |
| Python modules `python/rangtoy/` | 51 | 22,366 | 16 `core_*` (6,430) + pointing/beam (1,943) | 30 `flagging_*` (13,481), `imaging_sensitivity`, `projector` |
| Examples | 68 | 11,175 | core drivers, checkers, comparators (5,487 lines, 33 files) | LUNO exploration, oracles, pointing studies |
| Tests | 52 files, 442 test functions (739 collected) | 10,969 | – | – |
| Stimela recipes | 30 | 1,343 | 7 `core-*.yaml` (351) | 23 `tv-flagging*.yaml` (992) |
| Dockerfiles | 9 | 166 | `tools/ms-reader` (oracle only) | 8 under `tools/flagging/` |
| Local container images | 10 tagged + 3 dangling | 8.6 GB on disk (5.6 GB reclaimable, `docker system df`) | none needed by the core chains | all `rang-flagging*:local` |
| Shell wrappers `tools/flagging/` | 14 `run-*.sh`, 4 `fetch-*.sh` | 1,131 (all of `tools/`) | `check-all.sh`, `core-j-suite.sh` | the rest |
| Research notes / archives | 93 `.md`, 78 `results/*.json` | 15,949 | – | – |

### 1.1 Rust

| File | Lines | Role | Status |
| --- | ---: | --- | --- |
| `core/src/solve.rs` | 692 | QuartiCal `complex` port | live; reproduces `core-phase2.json`, `core-section6.json` |
| `core/src/fused.rs` | 529 | residuals, split losses, MAD scores, diagonal normals | live; `core-phase1.json` |
| `core/src/grid.rs` | 900 | WSClean w-stacking gridder, own FFT | live; `core-c` pixels, `core-i-imaging-replay.json` |
| `core/src/weights.rs` | 543 | Briggs/uniform/natural weights, Stokes I | live; bit-identical to WSClean (task B) |
| `core/src/sumthreshold.rs` | 1,347 | Tricolour strategies | live; `core-d-tricolour.json` |
| `core/src/blosc.rs` | 633 | blosc/LZ4 decoder, block-selective | live; `core-section6.json` chunk hashes |
| `core/src/ms.rs` | 1,952 | read-only casacore reader | live (imaging replay); `core-e` 173 columns |
| `core/src/predict.rs` | 259 | africanus component predictor | live (signal); `core-phase3c-a.json` |
| `core/src/jones.rs`, `robust.rs`, `lib.rs` | 166 | 2 × 2 algebra, MAD | live |
| `core/src/ffi*.rs` (5 files) | 1,523 | C ABI behind ctypes **and** the extension | live; 22 `extern "C"` functions, 6 without `catch_unwind` (`grid_kernel`, `ms_last_error`, `ms_close`, `ms_free`, `weight_grid_shape`, `padded_size`) |
| `core/py/src/lib.rs` | 681 | PyO3 extension, 17 functions + `MsTable` | live; no function releases the GIL |
| `src/response.rs`, `linalg.rs` | 714 | anchored response, Jacobi eigensolver (survey) | live through ctypes (`flagging_influence`) |
| `src/tv.rs`, `trend.rs`, `projector.rs` | 570 | gain TV, trend slopes, projector | live through ctypes (`flagging`, `flagging_trend`, `projector`) |
| `src/lib.rs`, `main.rs` | 985 | the original pointing toy (`rang-toy` binary) | live for the pointing question (B1) |

The root crate's five C functions are still loaded through
`projector._native_library()`, which runs `cargo build` and `cargo
metadata` at first use, as does `core.library()` whenever the ctypes path
or `core.library()` itself is called (the K driver calls it). With the
default toolchain (`stable`) differing from check-all's `+1.93`, each
alternation recompiles both crates (2.2 s + 1.0 s measured in this task's
first smoke run).

### 1.2 Python, grouped by what reaches it

Import graph from the AST plus `rangtoy.<name>` strings (recipes, tools,
`importlib`); "core closure" is everything a `core_*` module imports
transitively.

| Group | Modules | Lines | Status |
| --- | --- | ---: | --- |
| Core wrappers and drivers | `core`, `core_zarr`, `core_fetch`, `core_ms`, `core_flag`, `core_grid`, `core_weights`, `core_workflow`, `core_compare`, `core_cli`, `core_actions`, `core_injections`, `core_prospective`, `core_signal`, `core_imaging`, `core_campaign` | 6,430 | live; about 421 lines are the ctypes branch (struct layouts, `argtypes`, `_ptr`) |
| Frozen campaign modules the core drivers import unedited | `flagging`, `flagging_workflow`, `flagging_actions`, `flagging_injections`, `flagging_prospective`, `flagging_signal`, `flagging_signal_guard`, `flagging_response`, `flagging_trend`, `flagging_structured`, `flagging_structured_proposals`, `flagging_caracal`, `flagging_balanced`, `flagging_equivariance`, `flagging_influence`, `flagging_imaging`, `flagging_next`, `flagging_comparators`, `flagging_prepared`, `imaging_sensitivity`, `projector` | 10,822 | frozen and load-bearing: the phase 3 and I comparators rely on these modules being unedited (the trend archive checks `flagging_trend.py`'s SHA256). Coverage below shows how much of them the core chains execute |
| Frozen, reachable only from the frozen recipes | `flagging_concurrent`, `flagging_parallel`, `flagging_provenance`, `flagging_public`, `flagging_transfer`, `flagging_uncertainty` (+ `flagging_sky`, but `validate_core_phase3c_a.py` imports its `point_catalog_predict`) | 2,626 (+ 595) | history candidates |
| Pointing and beam research | `pointing`, `beams`, `blocked`, `observability`, `gauge`, `uncertainty`, `__init__` | 1,943 | live for B1 (wave 3) |

Coverage of the live chains (`coverage run` with `sys.monitoring` over the
K replay, K precondition and checker, section 6, actions, injections,
prospective, signal, trend mirror, trend, imaging replay and the
Tricolour controls; [coverage-summary.json](results/profiles-20261030/coverage-summary.json)):

| Group | Statements | Executed by the live chains |
| --- | ---: | ---: |
| `core_*` | 2,627 | 1,888 (72 %; the rest is mostly the ctypes branch and checker paths) |
| frozen modules the core imports | 4,281 | **1,340 (31 %)**: `flagging_trend` 89 %, `flagging_structured_proposals` 87 %, `flagging` 79 %, but `flagging_workflow` 10 %, `flagging_prepared` 10 %, `flagging_comparators` 10 %, `imaging_sensitivity` 18 %, `flagging_imaging` 20 % |
| frozen, recipe-only | 1,498 | 0 |
| pointing and beam | 783 | 19 (2 %) |

So about 2,940 statements of frozen code (QuartiCal subprocess
orchestration, MS preparation and copies, container and digest logic) sit
on the live import graph and never run.

### 1.3 Recipes, containers, wrappers

- `recipes/core-*.yaml` (7, 351 lines): live; call `rangtoy.core_cli` or
  `rangtoy.core_imaging`; Stimela needs a 3.13 venv (task I).
- `recipes/tv-flagging*.yaml` (23, 992 lines): frozen. Each ran once in a
  `rang-flagging*:local` container through `tools/flagging/run-*.sh` and is
  hashed into its campaign receipt; `tv-flagging-comparators` and
  `tv-flagging-structured` invoke QuartiCal directly, the others through
  `flagging_workflow.solve` (a `goquartical` subprocess).
- Containers: 8 Dockerfiles under `tools/flagging/` (base, comparators,
  imaging, next, next-imaging, parallel, response, sky) and
  `tools/ms-reader/` (python-casacore oracle). No core chain needs a
  container; the oracles (WSClean, python-casacore, numcodecs, africanus,
  QuartiCal, Tricolour) are needed only to regenerate oracle runs, whose
  outputs are archived.

### 1.4 Superseded stages and the archive that proves each

| Stage (frozen implementation) | Core replacement | Archive | Comparator | Re-run in this task |
| --- | --- | --- | --- | --- |
| QuartiCal `complex` solve (`goquartical` in containers) | `core/src/solve.rs`, `core_workflow.core_solve` | `core-phase2.json`; `meerkat-luno-solved.json` | `validate_core_phase2.py`, `bench_core_f.py` | pass (2.2 s; F check 35 s) |
| zarr → MS → QuartiCal → survey (section 2.1 chain) | `prototype_section6.py` on `core_zarr` | `core-section6.json` | `check_section6.py` | pass (6.0 s + 11.9 s) |
| injections track | `core_injections` | `gain-tv-injections.json` | `compare_core_injections.py` | pass, 864 exact / 940 floats 1.3e-14 (15.9 s) |
| actions stage | `core_actions` | `gain-tv-actions.json` | `compare_core_actions.py` | pass (5.5 s) |
| prospective track | `core_prospective` | `gain-tv-next-prospective.json` | `compare_core_prospective.py` | pass (20.0 s) |
| signal track | `core_signal` + `core/src/predict.rs` | `gain-tv-next-signal.json`, `core-phase3c-a.json` | `compare_core_signal.py` | pass (35.1 s) |
| trend track | core mirror + unedited `flagging_trend` | `gain-tv-next-trend.json` (post-hoc slope rule) | `compare_core_trend.py` | pass (13.6 s + 31.4 s) |
| WSClean imaging (`rang-flagging-next-imaging`) | `core_weights`, `core_grid`, `core_imaging` | `gain-tv-next-imaging.json`, `core-i-imaging-replay.json` | `compare_core_imaging.py`, `compare_core_gridder.py`, `compare_core_weights.py` | pass (I 53.2 s, C 56.2 s, B 0.8 s) |
| Tricolour / CARACAL strategies | `core/src/sumthreshold.rs`, `core_flag` | `core-d-tricolour.json`, `gain-tv-caracal.json` | `compare_core_flags.py` | pass (8.8 s) |
| python-casacore reads | `core/src/ms.rs`, `core_ms` | `core-e` oracle dump | `check_ms_reader.py` | pass (0.5 s) |
| numcodecs decode, whole-tile fetch | `core/src/blosc.rs`, `core_fetch` | `core-section6.json`, `core-g` receipts | `check_core_fetch.py`, K checker | pass (6.9 s; K checker 1.6 s) |
| NumPy residual, loss, score and normal pass | `core/src/fused.rs` | `core-phase1.json` | `validate_core_phase1.py` | as archived: criterion 4 fails as frozen, post-hoc 4b passes (5.2 s) |
| africanus component predictor | `core/src/predict.rs` | `core-phase3c-a.json` | `validate_core_phase3c_a.py` | pass, bit-identical to africanus on all three sets (29.0 s) |
| (new science) K campaign | `core_campaign` | `core-k-luno-campaign.json` | `check_luno_campaign.py` | precondition and checker pass; offline replay hash-equal |

`check_core_fetch.py` on task G's run passes all five criteria (6.9 s).
`compare_core_backends.py` between task J's extension suite and this
task's suite (89 files, 4,313 JSON leaves, 58 arrays, 60 FITS HDUs) finds
no numerical difference; it exits 1 on 27 non-numerical items, read after
the run: 21 absolute paths that contain the worktree name, 4 layout keys
because this suite ran the actions stage through `core_cli` instead of
`run_core_campaign.py`, and section 6's cost criterion, which task J's
cold-cache run failed and this run passed.

## 2. Profiles

### 2.1 Method

- **Timed suite** (`suite.sh`): every chain under `/usr/bin/time` with the
  1-minute load average before and after, sequential, extension backend,
  `RUSTUP_TOOLCHAIN=1.93` so no chain triggers a rebuild. Load 0.4–4.6.
- **Offline K replay** (`profile_campaign.py`): `core_campaign`'s stages
  after the fetch, on the archived fetched bytes of `core-k-20261030-01`
  (read-only), with every kernel wrapper timed (wall, process CPU, peak
  RSS) by patching module attributes in-process; no repository code
  edited. It compares the gains of three arms and the dirty image and PSF
  of the imaged arms with the archived `result.json` hashes: all equal.
- **Sampling**: `py-spy record --native --idle` at 250 Hz (wall-clock
  samples of the Python thread, native frames included), classified by
  `classify.py` walking from the leaf: Rust (`_core.abi3.so`,
  `librang_core`, `librang_toy`), NumPy/OpenBLAS, I/O (read/write/stat,
  SHA256, zip/npz, JSON, pathlib), import time, else Python. `perf record
  -e cpu-clock:u` for CPU by shared object. Walls are from the unprofiled
  suite, not from py-spy runs.
- **Probes** (`probes.sh`): OpenBLAS A/B, subset scaling, and core builds
  outside the checkout (`~/Build/tmp/20261030-rang-s1/{default,lto,v3}`,
  removed at the end) selected with `RANG_CORE_LIB`; `perf stat` counts.
- The probes ran while sibling sessions held the load at 13–27, so their
  walls are noisy; instruction counts and hashes are not.
- Host: Ryzen 7 7700X, **8 physical cores, 16 SMT threads**; 30 GiB.
  GPU at 05:52 UTC: RTX 4070 Ti, 487 MiB of 12,282 MiB used (the 10.5 GB
  holder noted in the plan was absent); no CUDA toolkit (no cuFFT, no
  NVRTC) in WSL, only the driver's `libcuda`.

### 2.2 Every archived chain, timed (suite `-01`)

| Step | Wall s | User s | Sys s | Peak RSS MB | Threads busy (CPU/wall) | Load before |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| precondition | 4.84 | 4.55 | 1.51 | 199 | 1.25 | 0.40 0.40 0.39 |
| precondition-blas1 | 2.37 | 1.62 | 0.75 | 144 | 1.00 | 0.45 0.41 0.40 |
| kcheck | 1.58 | 2.05 | 0.39 | 119 | 1.54 | 0.57 0.44 0.40 |
| campaign | 21.96 | 25.50 | 1.39 | 419 | 1.22 | 0.57 0.44 0.40 |
| campaign-blas1 | 10.97 | 10.19 | 0.74 | 404 | 1.00 | 1.57 0.71 0.50 |
| section6 | 5.95 | 4.47 | 2.16 | 141 | 1.11 | 1.49 0.72 0.50 |
| section6-blas1 | 4.66 | 3.60 | 1.05 | 141 | 1.00 | 1.45 0.72 0.50 |
| section6-check | 11.89 | 8.36 | 4.40 | 427 | 1.07 | 1.41 0.73 0.51 |
| phase2 | 2.19 | 3.84 | 0.12 | 116 | 1.81 | 1.35 0.74 0.51 |
| bench-f | 35.13 | 36.76 | 7.16 | 827 | 1.25 | 1.32 0.74 0.52 |
| actions | 5.45 | 6.07 | 0.20 | 236 | 1.15 | 2.23 1.03 0.62 |
| actions-compare | 0.07 | 0.72 | 0.01 | 37 | 10.43 | 2.21 1.04 0.63 |
| injections | 15.94 | 15.72 | 0.90 | 736 | 1.04 | 2.21 1.04 0.63 |
| injections-compare | 0.09 | 0.94 | 0.01 | 37 | 10.56 | 1.94 1.04 0.64 |
| prospective | 19.97 | 20.45 | 0.38 | 547 | 1.04 | 1.94 1.04 0.64 |
| prospective-compare | 0.11 | 0.80 | 0.02 | 38 | 7.45 | 1.98 1.10 0.67 |
| signal | 35.06 | 38.35 | 0.53 | 819 | 1.11 | 1.98 1.10 0.67 |
| signal-compare | 0.07 | 0.73 | 0.01 | 37 | 10.57 | 2.48 1.33 0.76 |
| trend-mirror | 13.58 | 13.03 | 0.84 | 222 | 1.02 | 2.48 1.33 0.76 |
| trend | 31.38 | 31.95 | 0.30 | 344 | 1.03 | 2.15 1.31 0.76 |
| trend-blas1 | 33.06 | 32.79 | 0.26 | 358 | 1.00 | 2.26 1.41 0.81 |
| trend-compare | 0.12 | 0.84 | 0.01 | 37 | 7.08 | 2.87 1.65 0.92 |
| b | 0.77 | 1.36 | 0.14 | 82 | 1.95 | 2.87 1.65 0.92 |
| c | 56.22 | 56.64 | 0.24 | 137 | 1.01 | 2.87 1.65 0.92 |
| c-compare | 0.38 | 1.05 | 0.13 | 66 | 3.11 | 4.63 2.54 1.28 |
| d | 8.78 | 9.47 | 0.13 | 97 | 1.09 | 4.63 2.54 1.28 |
| d-compare | 0.37 | 1.13 | 0.07 | 64 | 3.24 | 4.31 2.53 1.29 |
| e | 0.51 | 1.11 | 0.23 | 170 | 2.63 | 4.31 2.53 1.29 |
| i | 53.20 | 55.16 | 0.31 | 209 | 1.04 | 4.31 2.53 1.29 |

`precondition` includes one recompilation of both crates (the build
artefacts had been made by `stable` in a smoke run); `precondition-blas1`
is the clean figure. `campaign` imaged three arms, `campaign-blas1` one.
The comparators (`*-compare`) spend 0.07–0.12 s wall but 0.7–0.9 s CPU:
NumPy's OpenBLAS pool (16 threads) spins up at import, 7–10.6 threads busy
for a process that does no linear algebra. Checked by an A/B on the
actions comparator (three runs each, alternating, load 30): 0.37–0.50
CPU-s with the default pool against 0.09–0.12 CPU-s with
`OPENBLAS_NUM_THREADS=1`, verdicts identical.

### 2.3 The K chain, stage by stage (offline replay, load 0.6)

| Stage | Wall s | CPU s | Threads busy | Peak RSS MB |
| --- | ---: | ---: | ---: | ---: |
| decode (2,048 blocks, Rust) + extra objects | 1.00 | 1.00 | 1.00 | 81 |
| section 6 reference | 1.34 | 1.31 | 0.98 | 145 |
| split (seed 7) | 0.04 | 0.04 | 0.98 | 145 |
| solve `original` | 0.36 | 0.36 | 1.00 | 145 |
| Tricolour first-pass port / its solve | 1.63 / 0.34 | 1.63 / 0.34 | 1.00 | 155 |
| Tricolour mild port / its solve | 0.92 / 0.37 | 0.92 / 0.37 | 1.00 | 182 |
| TV loop (scores, TV, 6 candidate solves) | 2.05 | 2.05 | 1.00 | 275 |
| image `original` / `tricolour-firstpass` / `tricolour-mild` | 3.87 / 3.70 / 3.43 | same | 1.00 | 404 / 419 / 419 |

Kernel totals inside the replay: `core_grid.invert` 3 calls 10.41 s (3.47 s
each; 3.29–3.57 s of it inside Rust), `core.solve_complex` 9 calls 3.10 s
(0.345 s each), `core_flag.flag_rows` 2 calls 2.53 s,
`core_zarr.decode_span_rows` 2,048 calls 0.78 s, `apply_gains` (NumPy) 3
calls 0.44 s, `core.fused_pass` 9 calls 0.26 s, `write_fits` 6 calls 0.10 s,
`gain_tv` 16 calls 0.011 s, `policy_mask` 9 calls 0.022 s. Applied to the
archived K run (six images, fifteen solves), the 34.7 s outside the fetch
split as: images 23.4 s (67 %), solves about 5 s (15 %), Tricolour 2.5 s,
section 6 reference 1.2 s, decode 0.4 s, the rest under 2 s.

### 2.4 Where the time goes: Rust, NumPy, I/O, Python glue (py-spy)

| Chain | Samples | Rust | NumPy | I/O | Import | Python |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| K replay (one image) | 3,739 | 87.4 % | 6.5 % | 1.4 % | 3.9 % | 0.8 % |
| K precondition | 846 | 77.1 % | 10.4 % | 5.4 % | 4.7 % | 2.4 % |
| K checker | 490 | 38.2 % | 6.9 % | 39.4 % | 11.2 % | 4.3 % |
| section 6 prototype | 1,528 | 39.5 % | 6.8 % | 50.2 % | 1.6 % | 2.0 % |
| section 6 checker | 4,004 | 64.4 % | 2.3 % | 31.5 % | 1.2 % | 0.5 % |
| actions | 1,831 | 85.7 % | 8.5 % | 2.2 % | 2.9 % | 0.7 % |
| injections | 5,882 | 79.2 % | 13.7 % | 5.7 % | 1.1 % | 0.4 % |
| signal | 12,550 | 51.6 % | 44.8 % | 1.3 % | 0.3 % | 2.0 % |
| trend | 13,284 | 0.1 % | 75.5 % | 7.4 % | 0.3 % | 16.7 % |
| imaging replay (task I) | 18,149 | 97.2 % | 0.8 % | 1.2 % | 0.5 % | 0.4 % |

Hot functions (share of the chain's samples; Rust symbols are the non-inlined
functions py-spy resolves):

- **Imaging replay (task I)**: `grid::FftPlan::radix2` 78.3 %,
  `Gridder::invert` (sample loop, `add_sample`, `project` inlined) 11.7 %,
  `FftPlan::execute` (Bluestein chirps) 5.1 %. The FFT is 83 % of imaging.
- **K replay**: `FftPlan::radix2` 22.4 %, `sumthreshold::box_filter_axis0`
  12.7 %, solver (`solve` 10.9 %, `accumulate_finite` 8.1 %, its
  iterator closure 5.1 %), `sumthreshold::convolve_flags` 4.1 %,
  `rang_toy::linalg::eigen` 4.0 % (section 6 reference), blosc 4.5 %.
  `perf` by shared object: `_core.abi3.so` 79.3 %, `librang_toy.so` 5.0 %,
  OpenBLAS 4.5 %, libc 2.9 %, CPython 2.8 %, NumPy 2.7 %, libm 2.4 %
  (`sin_cos` in the gridder's projection).
- **Signal track**: `rang_toy::linalg::eigen` 33.1 % and
  `response::normals` 7.9 % (the anchored-response survey); NumPy 44.8 %,
  mostly `np.linalg.cond` and `np.linalg.inv` on per-cell 2 × 2 gain
  matrices in `flagging_signal.corrected_intensity` (lines 144–149) and
  `flagging_signal_guard.train_signal_guard` (140–141), which recompute
  per cell what is a property of each gain.
- **Trend track**: 92 % in `flagging_structured_proposals.generate_candidates`
  (lines 212–238): per scope × row group × tile, a slice sum, `np.nonzero`,
  index arithmetic and a SHA256 of the indices, most of them for tiles
  rejected by count. NumPy 75.5 %, Python 16.7 %, Rust 0.1 %.
- **Injections / actions**: solver 72 % / 81 % of samples.
- **Section 6 and its checker**: I/O 50 % / 32 % (reading 752 MB of spans
  and SHA256 of whole chunks); in the checker the extension's
  `blosc_decode` frame itself holds 37 % (fresh 205 MB `bytes` per DATA
  tile: page faults and zero fill), LZ4 12 %.
- **K checker**: I/O 39 % (hashes of the 725 MB of fetched spans), import
  11 %, decode 38 %.

Python glue (interpreter and `rangtoy` frames) is under 1 % of every
Rust-backed chain and 4 % of the K checker. Removing Python is not where
the time is; parallelising and fixing the FFT is.

### 2.5 Cores busy

Every kernel stage of every chain runs on one thread: in-process CPU/wall
is 0.98–1.00 for all K stages; process-level figures above 1.0 come from
OpenBLAS spin threads (K replay 1.22 with the default pool, 1.00 with
`OPENBLAS_NUM_THREADS=1`) or cargo subprocesses. 15 of the 16 hardware
threads are idle during the science work. With 8 physical cores, the
realistic parallel ceiling is about 7–10× (SMT adds 10–30 % for
FP-heavy kernels), not 16×.

OpenBLAS A/B (probes, alternating order, load 13–17): precondition
3.39–3.87 s default against 3.65–4.06 s pinned; K replay with one image
15.3–20.9 s against 19.0–22.9 s. No wall difference is resolvable under
that load; the gain is CPU: 0.7–0.9 CPU-s per short process and about
18 % of the K replay's CPU, released to the sibling sessions.

### 2.6 Build profile and target CPU (no code change)

`perf stat -e instructions:u,cycles:u` of the K replay (one image, no
section 6 reference, two runs each, load 16–19), core built outside the
checkout and loaded with `RANG_CORE_LIB`:

| Build | Instructions | Cycles | Equality |
| --- | ---: | ---: | --- |
| default release profile | 215.58 G (both runs) | 70.9–71.4 G | reference |
| `lto = "thin"`, `codegen-units = 1` | 204.31 G (−5.2 %) | 67.5–68.2 G (−4.8 %) | gains of 3 arms, dirty and PSF hash-equal to the K archive; F solver bit-identical, QuartiCal 3.3e-16 |
| the same + `-C target-cpu=x86-64-v3` | 167.66 G (−22.2 %) | 42.6–54.0 G (−24 % to −40 %) | the same; blosc: 68 chunks equal to the oracle, block-selective rows identical |

Whole-process counts, so the kernel-only gain is larger. Rust does not
contract `a * b + c` into FMA, so AVX2/FMA code generation keeps results
bit-identical; that was checked, not assumed. A wheel cannot assume
`x86-64-v3` (pre-2013 CPUs), so the wheel needs either function
multiversioning of the hot kernels or two builds; that belongs with W1.

### 2.7 Solver convergence (LUNO four-station slice, `original` arm)

`convergence.py` solves with `max_iterations = k` and compares with the
50-iteration solution (the archived one):

| k | Converged fraction | max \|Δg\| vs 50 | max \|Δ(G_p G_q^H)\| vs 50 | Polar TV rel. diff | Validation MSE | Train χ² |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.0000 | 5.7e-02 | 8.5e-02 | 3.7e-01 | 1.2214765 | 1.2158726 |
| 2 | 0.0000 | 3.5e-02 | 4.9e-02 | 1.3e-01 | 0.8566611 | 0.8496082 |
| 3 | 0.0000 | 1.7e-02 | 2.6e-02 | 4.6e-02 | 0.2785596 | 0.2713364 |
| 4 | 0.0000 | 1.5e-02 | 2.4e-02 | 3.7e-02 | 0.2757451 | 0.2680588 |
| 5 | 0.0000 | 1.4e-02 | 2.3e-02 | 3.1e-02 | 0.2752391 | 0.2675096 |
| 6 | 0.0000 | 1.3e-02 | 2.1e-02 | 1.9e-02 | 0.2752438 | 0.2674402 |
| 8 | 0.0733 | 1.1e-02 | 1.8e-02 | 1.3e-02 | 0.2752698 | 0.2674200 |
| 10 | 0.0733 | 1.0e-02 | 1.6e-02 | 9.7e-03 | 0.2752793 | 0.2674153 |
| 12 | 0.0733 | 8.7e-03 | 1.4e-02 | 7.7e-03 | 0.2752833 | 0.2674134 |
| 15 | 0.4920 | 7.2e-03 | 1.1e-02 | 5.9e-03 | 0.2752856 | 0.2674122 |
| 20 | 0.7635 | 4.9e-03 | 7.6e-03 | 3.7e-03 | 0.2752873 | 0.2674112 |
| 25 | 0.8398 | 3.4e-03 | 5.3e-03 | 2.6e-03 | 0.2752880 | 0.2674108 |
| 30 | 0.8874 | 2.2e-03 | 3.4e-03 | 1.6e-03 | 0.2752884 | 0.2674106 |
| 35 | 0.9464 | 1.4e-03 | 2.2e-03 | 1.0e-03 | 0.2752886 | 0.2674105 |
| 40 | 0.9607 | 7.5e-04 | 1.2e-03 | 5.7e-04 | 0.2752888 | 0.2674104 |
| 45 | 0.9833 | 3.4e-04 | 5.4e-04 | 2.6e-04 | 0.2752888 | 0.2674104 |
| 50 | 0.9833 | 0.0e+00 | 0.0e+00 | 0.0e+00 | 0.2752889 | 0.2674104 |
| 60 | 0.9839 | 4.0e-04 | 6.4e-04 | 3.1e-04 | 0.2752890 | 0.2674104 |
| 80 | 0.9863 | 7.3e-04 | 1.2e-03 | 5.7e-04 | 0.2752890 | 0.2674104 |
| 100 | 0.9905 | 8.0e-04 | 1.3e-03 | 6.2e-04 | 0.2752890 | 0.2674104 |
| 150 | 0.9905 | 8.0e-04 | 1.3e-03 | 6.2e-04 | 0.2752890 | 0.2674104 |
| 200 | 0.9905 | 8.0e-04 | 1.3e-03 | 6.2e-04 | 0.2752890 | 0.2674104 |

Held-out MSE is within 2e-4 relative of the archived value by iteration
5 and 2e-5 by 12, training χ² within 1e-5 by 12; 7.3 % of intervals pass
the 1e-7 criterion at 8 iterations, 49 % at 15, 98.33 % at 45; the cap (50)
stops at 98.33 % < 99 %, and without it the solve stops at 91 iterations
(99.05 %) with gain products 1.3e-3 and the polar TV 6e-4 relative away
from the archived 50-iteration values. Subsets of 1–3 baselines (all to
station 0) converge in 8 iterations; every six-baseline subset runs to the
cap. So on this slice the solver's cost is set by the cap, and the archived
gains are a 50-iteration iterate, not a converged solution.

### 2.8 Memory, and the whole-array estimate

Peak RSS of the K replay against cells (row × channel), labelled probes
on station-pair and channel subsets (one image, OpenBLAS pinned): 65,536
cells 116 MB; 131,072 168 MB; 196,608 227 MB; 393,216 401 MB. A linear fit
gives **0.87 kB per cell** above a 58 MB base. Inputs are 84 B per cell
(DATA 32, MODEL_DATA 32, WEIGHT_SPECTRUM 16, FLAG 4). Stage deltas in the
quiet replay: TV loop +93 MB (237 B per cell; by reading the code, mostly
`residuals * sqrt(w)` and the masks), first image +130 MB (330 B per
cell; by reading the code, `apply_gains` builds
complex128 `gp`, `gq`, inverses, `v` and the product, then the gridder
materialises 40-byte samples for the dirty image and again for the PSF).
Each retained solve holds complex128 residuals (64 B per cell) and a
float64 guidance map (8 B); `run()` keeps six solves.

Whole-array LUNO chunk 0 (task L1 measures it; this is an estimate).
Assumptions: 1,540 cross baselines × 32 integrations = 49,280 rows
(256.7× the slice), 2,048 channels, the slice's 70 % flag fraction and
per-cell costs, 50 solver iterations per solve (unknown: 56 stations add
redundancy and may converge earlier), a 512² image with 64 w-layers (L1
may choose finer pixels; the FFT term scales with padded pixels × layers),
the K chain as written, one thread.

| Item | Four stations (measured) | Whole array (estimate) | Basis |
| --- | ---: | ---: | --- |
| visibility cells | 393,216 | 100.9 M | 256.7× |
| input arrays | 33 MB | 8.5 GB | 84 B per cell |
| peak RSS, K chain as written | 461 MB (K run) | **about 88 GB** | 0.87 kB per cell |
| decode | 0.36 s | about 2.3 s | all 12,544 blocks instead of 2,048 (6.5× the bytes) |
| one solve, 50 iterations | 0.345 s | about 89 s | 74 ns per cell-iteration on train cells |
| fused pass | 0.029 s | about 7.5 s | linear in cells |
| Tricolour first-pass / mild | 1.63 / 0.92 s | about 7.0 / 3.9 min | per-baseline windows, linear |
| one image: gain correction (NumPy) | 0.15 s | about 38 s and 33 GB transient | 330 B per cell |
| one image: gridding term | 0.4–0.6 s | about 100–150 s | `Gridder::invert` self time (py-spy), O(64 layers × samples) scan |
| one image: FFT term | 2.9 s | 2.9 s | fixed for 512², 64 layers |
| K-shaped campaign (15 solves, 2 Tricolour, 6 images) | 34.7 s | about 50 min, and out of memory | sum of the rows |

After P1–P5 (estimate, 8 cores): solves about 3 min in all, Tricolour
about 1.5 min, images about 1 min, peak memory about 12–15 GB.

### 2.9 Test suite

`pytest -q --durations=0` once (`outputs/simplification-review-20261030-05/pytest-durations.txt`):
739 passed in 1,058 s, peak RSS 1.8 GB, **7.7 threads busy on average**,
while sibling sessions held the load at 16–33. On an idle host the same
suite took 74.3 s inside check-all (task K). Per module (call time):

| Module | Seconds | Share |
| --- | ---: | ---: |
| `tests/test_pointing.py` | 767.6 | 72.7 % |
| `tests/test_blocked.py` | 213.7 | 20.2 % |
| `tests/test_beams.py` | 50.2 | 4.8 % |
| `tests/test_toy.py` | 10.3 | 1.0 % |
| `tests/test_pointing_example.py` | 5.2 | 0.5 % |
| everything else (47 files, all `core_*` and `flagging_*` tests) | 8.3 | 0.8 % |

Six tests take 913 s of it: `test_correlated_flux_constraints_do_not_create_data_information`
(398 s), `test_flux_anchor_geometry_controls_number_of_common_modes`
(189 s), `test_blocked_matches_dense_and_numpy[True]` (127 s) and
`[False]` (83 s), `test_full_coverage_retains_modes_with_gains_and_differential_pointing`
(61 s), `test_nonquadratic_rotating_beam_breaks_local_gauge` (53 s). They are
the pointing studies' dense linear algebra and JAX/XLA paths: the process
held 145 threads (XLA compile, Eigen and execute pools of 16 each, plus
OpenBLAS), so on a shared host they oversubscribe the cores; the suite
ran about 14× slower than the idle run, while the 47 other test files
(every core and flagging test) took 8 s together. The per-module split of the 74-second idle run
was not measured here; that the same three modules dominate it is an
inference from their thread counts, to be checked by P10.

## 3. Ranked proposals

Ranked by expected gain per effort, whole array in view. "Verdict" is
keep / merge / delete / optimise. Owner files are disjoint between tasks
except where section 4 sequences them.

### P2 Gridder: mixed-radix FFT, w-layers in parallel, samples bucketed once (optimise)

- **What.** In `core/src/grid.rs`: (a) replace the radix-2/Bluestein FFT
  with a mixed-radix transform of the padded length (616 = 2³ · 7 · 11),
  either `rustfft` (MIT/Apache-2.0, public crates.io) or a written
  mixed-radix plan, planned once per `Gridder`; (b) bucket the samples by
  w-layer once (today every layer scans every sample: 64 × N
  `w_to_layer` calls per image) and grid the dirty image and the PSF in
  the same layer loop, sharing the bucket and the per-pixel phasor of
  `project`; (c) process layers in parallel with rayon, each layer into
  its own projected image, and sum the per-layer images **in layer order**
  so the reduction order is the serial one (64 × 616² × 8 B = 194 MB of
  per-layer images, or batches of 16 layers); (d) store samples as f32
  (WSClean grids in single precision) or stream them from the rows rather
  than materialising 40-byte tuples twice. Parallelising over rows within
  a layer instead needs per-thread grids and a reduction that changes the
  sum order; it is the next step only if one layer's gridding dominates
  at the whole array.
- **Gain.** FFT is 83 % of imaging (py-spy: `radix2` 78.3 %, `execute`
  5.1 %). Bluestein turns each 616-point line into two 2,048-point
  radix-2 transforms plus three chirp products (about 260 kflop); a direct
  616-point mixed-radix transform needs roughly 40–60 kflop, about a
  fifth, so 3.5 s → about 0.9–1.3 s per image on
  one thread (estimate); rayon over 64 layers on 8 cores, about 6×: **0.15–
  0.3 s per image** (estimate; WSClean itself took 1.4–1.7 s single-threaded,
  task C). K's six images: 23 s → 1–2 s; the task I family 53 s → about
  3–5 s. Whole array: the gridding term (estimated 105 s per image) falls
  by the 64× layer scan and by threads, to about 2–5 s; memory 8 GB of
  sample tuples → 0 (streamed) or 2 GB (f32 bucketed).
- **Archive.** Not bit-identical to the archived core images (different
  FFT rounding). Within task A's tolerances: dirty L∞ 8.8e-6 of peak, PSF
  2.8e-6, template flux 4.7e-6, response fraction 1.6e-7 (today 6.1e-7,
  4.2e-7, 1.4e-7, 1.3e-7). Archives: `core-i-imaging-replay.json`,
  `gain-tv-next-imaging.json`, task C's fifteen WSClean images, and the K
  arms' image metrics (`core-k-luno-campaign.json`, which stores dirty
  SHA256s: those will change, the metrics must not move beyond A's
  tolerances).
- **Risk.** Medium: today's response-fraction difference is 1.31e-7
  against task A's 1.6e-7 tolerance, so little room is left, and an f32
  grid may exceed it. Mitigation: keep f64 grids, change
  only the FFT and the layer loop first; f32 samples only if the
  comparators allow.
- **Owner files.** `core/src/grid.rs` (+ `core/Cargo.toml` dependency line
  via P0), `examples/bench_p2_gridder.py`, `tests/test_p2_gridder.py`,
  `research/p2-gridder.md`.
- **Validation.** `run_core_gridder.py` + `compare_core_gridder.py`,
  `run_core_imaging.py` (I comparators) and the K image metrics on the
  offline replay, all within task A's tolerances; timing before/after on
  the same load.
- **GPU (feasibility, not proposed for wave 2).** cuFFT of a 616² complex
  layer is tens of microseconds and gridding is embarrassingly parallel,
  so a GPU path would take an image to well under 0.1 s. Against it: the
  CPU path above already reaches 0.15–0.3 s; WSL has the driver but no
  CUDA toolkit (cuFFT and NVRTC would come from the public PyPI
  `nvidia-cufft-cu12`/`nvidia-cuda-nvrtc-cu12` wheels or a toolkit
  install); the RTX 4070 Ti does FP64 at 1/64 of FP32, so a GPU grid
  must be f32, which is WSClean's own precision but needs its own
  tolerance check; GPU memory was 11.8 GB free at 05:52 UTC but 1.7 GB
  when the 10.5 GB holder runs, so whole-array samples (about 2 GB in f32)
  must be streamed in batches either way. Wgpu in WSL depends on the
  D3D12-backed Vulkan layer and was not available (`vulkaninfo` absent).
  Recommendation: revisit after P2 if L1's whole-array images still
  dominate; if so, cudarc behind a `gpu` feature, f32 grid, batches of
  at most 1 GB.

### P5 Memory: one copy of the cube, no per-cell temporaries in Python (optimise)

- **What.** (a) `core_fetch.decode_slice`: decode each run straight into
  the final `(row, chan, corr)` array instead of `out.tobytes()` →
  `np.frombuffer` → `np.concatenate` (three copies of each column);
  (b) solves keep only what the arms need: residual-based MAD scores from
  the fused pass's own `scores=True` path (Rust, already validated in
  phase 1) instead of `residuals * sqrt(weights)` in NumPy, residuals as
  complex64 if kept at all, and no residual retained for arms that are
  only imaged; (c) a Rust `correct_stokes_i` kernel that applies
  `G_p^{-1} V G_q^{-H}`, flags and Stokes I per cell and returns the
  same `(sample, weight)` arrays `core_grid.stokes_i_reader` returns today
  (replaces `apply_gains` + `stokes_i_reader`; `grid.rs` is P2's and is
  not edited here, so P2's streamed samples are the gridder half of the
  saving); (d) local tiles opened with `mmap` rather than `read_bytes` for
  the whole-array tiles.
- **Gain.** Peak per cell 0.87 kB → about 0.12–0.15 kB (inputs 84 B,
  flags and masks 4–8 B, gains negligible, one float64 map); whole array
  88 GB → about 12–15 GB (estimate, fits 30 GiB). Time: `apply_gains`
  0.15 s per image → about 0.02 s; whole array 38 s → about 3 s per image.
- **Archive.** Bit-identical where the arithmetic is unchanged: scores
  from the fused pass equal NumPy's to 1.9e-14 (phase 1 criterion 3),
  so the policy masks must be re-checked for identity (section 6
  criterion 6 already requires nine identical mask hashes); the
  correction kernel must reproduce `apply_gains` to rounding (complex64
  output) and the K image metrics within task A's tolerances; decode is
  byte-identical (K criterion 1 and `check_core_fetch.py`).
- **Risk.** Medium: K's policy masks are hash-checked; a score
  difference at 1e-14 could move a cell across a threshold. Run the K
  precondition's mask check first.
- **Owner files.** `python/rangtoy/core_fetch.py`, `python/rangtoy/core_campaign.py`
  (residual retention; L1's `core_campaign_array.py` is L1's and is not
  touched), new `core/src/correct.rs` and `core/src/ffi_correct.rs`;
  `pub mod` lines and the PyO3 binding through "For the coordinator"
  (`core/src/lib.rs`, `core/py/src/lib.rs`, `python/rangtoy/core.py` are
  coordinator files), `research/p5-memory.md`.
- **Validation.** K precondition, K checker on a fresh replay with
  `profile_campaign.py`-style stage RSS, `check_core_fetch.py`; peak RSS
  per cell from the subset probes before/after; and L1's archive if L1
  has merged with `core_campaign` functions in its chain.

### P1 Solver: rayon over solution intervals, bit-identical (optimise)

- **What.** In `core/src/solve.rs`, accumulate `J^H W J` and `J^H W r`
  in parallel over (time bin, frequency-bin chunk) partitions: rows are
  sorted by time bin and each gain belongs to one (t, f) interval, so a
  partition that walks its rows in order and its channels in order adds
  every gain's contributions in exactly the serial order. The
  conjugate-gradient update, `finalize_update` and the convergence test
  are per gain and trivially parallel; the converged and flagged counts
  are integer sums. Also hoist `model_at`/`from_f32` conversions out of
  the 50-iteration loop (inputs are converted to f64 on every sweep).
  Parallelising over baselines instead would need per-thread partial
  `J^H W J` blocks and change every gain's summation order; intervals give
  the same parallelism bit-identically. The fused pass (`core/src/fused.rs`,
  no other task touches it) goes the same way over time bins; its split
  sums are global, so it is deterministic for a fixed chunking but not
  bit-identical to today (phase 1 tolerance 1e-12; whole array about 7.5 s
  → 1 s per call, estimate).
- **Gain.** Four stations: 16 time bins × 64 frequency bins, 0.345 s →
  about 0.05–0.07 s on 8 cores (estimate, 5–7×). Whole array: about 89 s
  → about 13 s per solve, a K-shaped campaign's 15 solves 22 min → about
  3 min (estimate). The solver is 72–81 % of the injections and actions
  stages (15.9 s → about 5 s; 5.5 s → about 2 s).
- **Archive.** Bit-identical: `bench_core_f.py check` (gains, flags,
  iterations, converged fraction SHA256 against task F's baseline),
  `validate_core_phase2.py` (QuartiCal 3.3e-16), and every phase 3
  comparator unchanged.
- **Risk.** Low. Threads must not reorder per-gain sums; a test that
  compares the parallel result hash with `RAYON_NUM_THREADS=1`.
- **Owner files.** `core/src/solve.rs`, `core/src/fused.rs`,
  `examples/bench_p1_solver.py`, `tests/test_p1_solver.py`,
  `research/p1-solver.md`.
- **Validation.** `bench_core_f.py check … --target solve` passes all
  solver equalities at 1, 4 and 16 threads; phase 2 validator; phase 1
  validator and section 6 checker for the fused pass.
- **Not in P1 (science):** the convergence criterion and initialisation.
  Section 2.7 shows the held-out MSE within 2e-5 by 12 iterations while gain
  products still move 1.3e-3 between 50 and 91 iterations. A gauge- and
  loss-based stop (e.g. relative change of the training χ² below 1e-8)
  would cut 50 iterations to about 10–15 (3–5×), and warm-starting the TV
  candidates from the base solve would cut more; both change archived
  gains by up to about 1e-3, far outside the 1e-6 tolerance, and the K
  candidate objectives sit 4.8e-4 relative above the baseline. That is a
  frozen-protocol study for wave 3 (decision-equivalence on every
  archived selection), not an engineering task.

### P3 SumThreshold and the Tricolour strategies: parallel over baselines (optimise)

- **What.** In `core/src/sumthreshold.rs`, run the per-baseline window
  work (`box_filter_axis0`, `sum_threshold`, `convolve_flags`,
  `background_2d`, `baseline_flags`) under rayon over baselines, with
  per-thread scratch buffers; vectorise `box_filter_axis0`'s column loop
  (its inner loops are already column-contiguous).
- **Gain.** `box_filter_axis0` 12.7 %, `convolve_flags` 4.1 %,
  `sum_threshold_axis0` 2.4 % of the K replay. Four stations have six
  baselines, so at most 6×: first pass 1.63 s → about 0.35 s. Whole
  array (1,540 baselines): about 7.0 min → about 1 min first pass, 3.9 →
  0.6 min mild (estimate, 7× on 8 cores).
- **Archive.** Bit-identical flags: `core-d-tricolour.json` (four
  controls, `run_core_flags.py` + `compare_core_flags.py`) and the K arms'
  addition hashes (`additions_sha256` in `core-k-luno-campaign.json`).
- **Risk.** Low; per-baseline windows are independent; the `or`
  accumulation across steps stays serial.
- **Owner files.** `core/src/sumthreshold.rs`, `research/p3-sumthreshold.md`,
  `tests/test_p3_flags.py`.
- **Validation.** D comparator flag-for-flag; K replay additions hashes.

### P0 Release profile, target CPU and the new crates (optimise; coordinator)

- **What.** `[profile.release] lto = "thin"`, `codegen-units = 1` in
  `core/Cargo.toml` (and the root crate); `cargo fetch` of `rayon` and
  `rustfft` (neither is in `~/.cargo/registry/cache` today, so `--offline`
  builds fail without one fetch); x86-64-v3 for local builds via
  `.cargo/config.toml` or `RUSTFLAGS`, and for the wheel either
  multiversioned hot kernels or a v3 build beside a baseline build
  (with W1). Drop the `#[inline(always)]` copies in `solve.rs` once LTO
  makes them redundant (task F noted this).
- **Gain.** Measured on the K replay: −5.2 % instructions with LTO,
  −22.2 % instructions and −24 % to −40 % cycles with v3; solver and blosc
  bit-identical.
- **Archive.** Measured bit-identical: K gains (3 arms), dirty and PSF
  hashes; `bench_core_f.py` solver and blosc equalities.
- **Risk.** Low. Build time of `core/` grows from about 2 s to about 6–8 s
  (one codegen unit).
- **Owner files.** `core/Cargo.toml`, `Cargo.toml`, `Cargo.lock`,
  `core/py/Cargo.toml`, `.cargo/config.toml`; applied by the coordinator
  before P1–P3 start, because all three add `rayon` to the same manifest.
- **Validation.** `bench_core_f.py check`, the K replay hashes,
  `tools/check-all.sh`.

### P6 Frozen Python hot spots in the trend and signal tracks (optimise; port, do not edit)

- **What.** (a) Trend: a core mirror of
  `flagging_structured_proposals.generate_candidates` (92 % of the trend
  stage's 31 s): tile counts from 2-D prefix sums of the TRAIN mask per
  row group, so only admissible tiles are materialised and hashed; same
  candidate order, same SHA256 mask ids. (b) Signal: compute
  `np.linalg.cond` and `np.linalg.inv` once per gain on the
  `(bin, antenna)` grid and index per cell, instead of per cell
  (`flagging_signal.corrected_intensity`, `flagging_signal_guard.train_signal_guard`;
  about 45 % of the signal stage's 35 s). The frozen modules stay as they
  are (the trend archive checks `flagging_trend.py`'s SHA256 and the
  comparators rely on unedited consumers); the faster versions live in
  `core_*` modules that the core drivers call, and the comparators prove
  them equal.
- **Gain.** Trend 31.4 s → about 3 s (estimate: prefix sums make the
  per-tile cost O(1), the admissible tiles are a small fraction). Signal
  35.1 s → about 20 s with (b) alone, about 12 s with P4 (estimate).
- **Archive.** Exact: `gain-tv-next-trend.json` (875 exact fields, the
  168 floats under the adopted slope rule), `gain-tv-next-signal.json`
  (261 exact, 208 floats 1.7e-11). Per-gain `cond`/`inv` are elementwise
  the same LAPACK calls on the same matrices, so bit-identical.
- **Risk.** Low–medium: candidate order and hash identity must be
  preserved exactly.
- **Owner files.** new `python/rangtoy/core_trend.py`,
  `python/rangtoy/core_signal.py`, `tests/test_p6_*.py`,
  `research/p6-python-hotspots.md`; `core_cli.py`'s `trend` subcommand
  switch through "For the coordinator".
- **Validation.** `core_cli compare trend … --posthoc-slope-scale` and
  `compare signal` pass with the same counts.

### P4 Survey eigensolver: same decision, faster algorithm (optimise)

- **What.** Replace `rang_toy::linalg::eigen` (classical Jacobi, O(n²)
  pivot search per rotation) with Householder tridiagonalisation plus
  implicit QL for the two 32 × 32 symmetric problems per bin in
  `response::anchored_step`, keeping `checked_eigen`'s residual check and
  the status thresholds. An exact-rank test (pivoted LDLᵀ) instead of the
  eigenvalues is the more radical option and changes the decision rule;
  not proposed first.
- **Gain.** Task F measured LAPACK doing the 864 decompositions in
  0.056 s against 0.51 s: the survey 0.73 s → about 0.28 s (section 6
  pass 1.46 s → about 1.0 s; K precondition and reference about −0.45 s
  each). Signal track: eigen is 33 % of its samples, 35 s → about 24 s.
- **Archive.** Statuses and counts identical: 389 / 43 / 592 / 0 with
  389 × status 0 and 43 × status 3 (`core-section6.json`,
  `core-phase2.json`), the signal and prospective archives' ranks and
  statuses; eigenvalues to about 1e-13 relative (reported, not gated).
- **Risk.** Medium: a discrete decision on near-degenerate spectra.
- **Owner files.** `src/linalg.rs`, `src/response.rs`, `research/p4-eigen.md`,
  `tests/test_p4_eigen.py`.
- **Validation.** `bench_core_f.py check --target survey`, section 6
  checker, signal and prospective comparators.

### P8 Retire frozen recipes, containers and recipe-only modules to `history/` (delete from the live tree; archives kept)

- **What.** Move to `history/` (git mv, so `git log --follow` works):
  23 `recipes/tv-flagging*.yaml` (992 lines); `tools/flagging/` (35
  files: 14 `run-*.sh`, 4 `fetch-*.sh`, 8 Dockerfiles, preflight, locks;
  1,040 lines); the six recipe-only modules
  `flagging_{concurrent,parallel,provenance,public,transfer,uncertainty}`
  (2,626 lines) and their six test files (1,502 lines);
  `flagging_sky` and its test stay because `validate_core_phase3c_a.py`
  imports `flagging_sky.point_catalog_predict`. Pruning the 8.6 GB of
  local `rang-flagging*` images is a user item, not code. Keep every
  `research/results/*.json` and every research note.
- **Gain.** Live tree: −70 files, about −6,200 lines, −23 recipes,
  −8 Dockerfiles; pytest loses the tests of history modules (they take
  under 2 s; section 2.9).
- **Archive.** None changes; the moved recipes are referenced by hash in
  their campaign receipts, and the archives cite paths that `history/`
  keeps resolvable by a note in each archive's report.
- **Risk.** Low; 34 research notes mention `recipes/tv-flagging*` or
  `tools/flagging/` and need a link sweep.
- **Owner files.** the moved files, `history/README.md`,
  `research/p8-history.md`; README/STATE lines through the coordinator.
- **Validation.** `tools/check-all.sh` passes; every live comparator
  (the suite of this task) still passes.

### P10 Test-suite speed (optimise)

- **What.** Mark the six tests above `slow` (a registered pytest marker,
  deselected by `tools/check-all.sh` and run by a separate
  `check-all.sh --slow` once per merge wave), and cap their threads in a
  `tests/conftest.py` fixture (XLA's CPU thread flags
  `--xla_cpu_multi_thread_eigen=false intra_op_parallelism_threads=1`,
  `OPENBLAS_NUM_THREADS` or `threadpoolctl` at 1–2) so parallel sessions
  do not oversubscribe; shrink problem sizes only where the assertion
  does not depend on them (each test's docstring names its claim).
- **Gain.** Default check-all pytest under the same shared load: 1,058 s
  → about 140 s (the other 733 tests took 144 s together here, mostly
  the remaining pointing and beam tests), less with the thread caps;
  idle 74 s → about 15–30 s (estimate). The slow set still runs once per
  wave.
- **Archive.** None: the same assertions run; only scheduling and thread
  counts change.
- **Risk.** Low; a slow test that is never run rots, so the wave
  checklist must include `--slow`.
- **Owner files.** `tests/test_pointing.py`, `tests/test_blocked.py`,
  `tests/test_beams.py`, new `tests/conftest.py`, `research/p10-tests.md`;
  the marker registration (`pyproject.toml`, shared with W1's metadata
  lines) and the `check-all.sh` flag through the coordinator.
- **Validation.** Both modes of check-all pass; durations before/after.

### P7 Architecture: drop the ctypes path, the root crate into the extension, GIL, `catch_unwind` (merge/delete)

- **What.** After W1's wheel is on main: (a) delete the ctypes branch of
  `core.py`, `core_grid.py`, `core_weights.py`, `core_flag.py`,
  `core_zarr.py`, `core_ms.py` (about 421 lines) and `RANG_CORE_LIB`;
  (b) expose the root crate's five kernels (`gain_tv`, `trend_slopes`,
  `response_{jacobian,normals,step}`, `project_out`) through the extension
  so no Python path runs `cargo build`/`cargo metadata` at import
  (`projector._native_library`, `rangtoy.build`); (c) release the GIL
  (`py.detach`) around every kernel call in `core/py/src/lib.rs`, which
  lets drivers overlap decode, solves and images with threads;
  (d) `catch_unwind` on the six C functions without it (task J found
  `rang_core_grid_kernel(7, 2)` aborting the process); (e) later, bind
  PyO3 directly to the Rust APIs and shrink `ffi*.rs` (1,523 lines) to
  what a C consumer needs, or delete it if none.
- **Gain.** About −420 Python lines now and up to about −1,200 Rust lines
  later; no rebuild flip-flop between toolchains (2–3 s per process when
  it happens); first-call latency 28–32 ms → under 1 ms (task J). No
  kernel speed change.
- **Archive.** `compare_core_backends.py` (94 files, 4,544 JSON leaves,
  60 arrays, 60 FITS HDUs identical in task J) before deleting ctypes,
  then the suite of this task.
- **Risk.** Low–medium: the frozen modules `flagging.py`,
  `flagging_influence.py`, `flagging_trend.py` and `flagging_equivariance.py`
  load the root crate through `projector._native_library`, and
  `flagging_trend.py` is hash-checked; route through `projector.py`
  only (not frozen-hashed), keeping the function names.
- **Owner files.** `python/rangtoy/core.py`, `core_grid.py`,
  `core_weights.py`, `core_flag.py`, `core_zarr.py`, `core_ms.py`,
  `projector.py`, `core/py/src/lib.rs`, `core/src/ffi*.rs`, `src/*.rs` C
  ABI only, `tests/test_core_backends.py`, `research/p7-architecture.md`.
  These include coordinator files: P7 runs alone, after P1–P6 merge.
- **Validation.** Backends comparator, then this task's suite, then
  `check-all`.

### P9 One CLI, one archive format, one comparator engine; OpenBLAS pinned (merge)

- **What.** `rang-core` gains `campaign`, `section6`, `flags`, `grid`,
  `weights`, `ms-check`, `bench` subcommands so the 33 example drivers,
  checkers and comparators (5,487 lines) become thin entry points or go;
  every run directory has the same four files (`result.json`,
  `receipt.json`, `side-effects.json`, `environment.json`, which K
  already writes) and every comparator uses `core_compare`'s exact /
  float / difference classes (4 of 10 comparators do today). Set
  `OPENBLAS_NUM_THREADS=1` (or `threadpoolctl`) before NumPy is imported
  by the CLI and the drivers.
- **Gain.** About −1,500 lines of examples (estimate), one place to add a
  stage; 0.7–0.9 CPU-s per short process and about 18 % of a chain's CPU
  returned to sibling sessions (measured above).
- **Archive.** Every comparator's verdict and counts identical before
  and after (the suite of this task as the oracle).
- **Risk.** Low; comparators encode post-hoc rules that must survive
  verbatim.
- **Owner files.** `python/rangtoy/core_cli.py`, `core_compare.py`,
  `examples/compare_core_*.py`, `examples/run_core_*.py`, `recipes/core-*.yaml`,
  `tests/test_core_cli.py`, `research/p9-cli.md`. After P7 (both touch
  driver entry points).
- **Validation.** This task's suite through the new CLI, same verdicts.

### P11 Extract what the core uses from the frozen modules, then retire them (merge/delete; after P6 and P7)

- **What.** Copy verbatim into `core_*` modules the 31 % of frozen-module
  statements the live chains execute (split and protected flags, policy
  masks, the TV objective, trend and structured proposals, signal and
  prospective guards, the imaging algebra), switch the core drivers to
  those copies, prove with every phase 3 and I comparator that nothing
  changed, then move the 21 frozen modules (10,822 lines) and their tests
  to `history/` beside P8's. Refactor the copies only afterwards.
- **Gain.** Live Python about −10,800 + 3,500 extracted ≈ −7,300 lines
  (estimate from coverage: 1,340 executed statements of 4,281); one
  implementation per algorithm instead of a frozen module plus a core
  mirror; the QuartiCal, MS-copy and container orchestration (about 2,940
  never-executed statements on the live path) leaves the import graph.
- **Archive.** Every row of section 1.4; the trend archive's
  `module_sha256` criterion then checks the history copy, which stays
  unedited.
- **Risk.** Medium–high: "the frozen consumer runs unedited" is part of
  the phase 3, trend and I validation arguments. Verbatim copies first
  keep that argument checkable by diff.
- **Owner files.** `python/rangtoy/flagging*.py`, `imaging_sensitivity.py`
  (moved), new `python/rangtoy/core_policy.py` and siblings, the imports of
  `core_actions.py`, `core_injections.py`, `core_prospective.py`,
  `core_signal.py`, `core_imaging.py`, `core_campaign.py`, `core_workflow.py`,
  the frozen-module tests (moved), `research/p11-extract.md`.
- **Validation.** This review's suite before and after with identical
  comparator counts; a coverage run shows no `history/` module imported by
  a live chain.

### Considered and not proposed

- **TV "in one pass with the residuals".** TV is a function of the gains
  only: 16 calls take 11 ms in the K replay (0.03 %). No gain.
- **Folding the fused pass into the solver's last sweep.** The fused pass
  is 0.029 s per call against 0.345 s per solve (about one sweep in 51);
  it must use the final gains, so it would still be a separate sweep.
  Keep separate.
- **Reading the data once.** Already true for the K chain (one decode; the
  solves and images read memory). What remains is P5's copies.
- **SIMD of the 2 × 2 complex kernels by hand.** `x86-64-v3` code
  generation already gives −22 % instructions bit-identically; explicit
  SIMD (e.g. four cells at once in `accumulate_finite`) changes no
  operation order per gain and could add 1.5–2× on the solver, but after
  P1's threads the solver is no longer the bottleneck at four stations.
  Revisit with L1's profile.
- **GPU solver normal equations.** The per-gain 4 × 4 blocks need f64 for
  QuartiCal-level agreement and consumer GPUs run f64 at 1/64 rate; the
  CPU path with P1 is the better first step.
- **Fetch.** 75 s of the K run is HTTP transfer at 8 workers, unchanged
  by any proposal here; L1 uses local tiles.

## 4. Proposed wave 2 tasks

In the format of the plan's wave 1 table, ordered by gain per effort.
Gains are the estimates of section 3; each task measures its own before
and after on the same load and reports both.

| | Task | Owns | Done when |
| --- | --- | --- | --- |
| P0 | **Release profile and crates** (coordinator, before P1–P3). `lto = "thin"`, `codegen-units = 1`; `cargo fetch` of `rayon` and `rustfft` (one network use of crates.io); `x86-64-v3` for local builds; note for W1 on multiversioning. Measured −5 % / −22 % instructions, bit-identical. | `core/Cargo.toml`, `Cargo.toml`, `Cargo.lock`, `core/py/Cargo.toml`, `.cargo/config.toml` | check-all passes; `bench_core_f.py check` and the K replay hashes equal |
| P2 | **Gridder**: mixed-radix FFT, layer bucketing, dirty and PSF in one loop, rayon over w-layers with an ordered reduction; GPU spike only if time allows and behind a feature. 3.5 s → 0.15–0.3 s per image (estimate). | `core/src/grid.rs`, `examples/bench_p2_gridder.py`, `tests/test_p2_gridder.py`, `research/p2-gridder.md` | C, I and K image comparators within task A's tolerances; measured speed-up |
| P5 | **Memory**: decode into place, Rust gain correction + Stokes I, no retained complex128 residuals, scores from the fused pass, mmap of local tiles. 0.87 → about 0.15 kB per cell (estimate). | `python/rangtoy/core_fetch.py`, `python/rangtoy/core_campaign.py`, new `core/src/correct.rs`, `core/src/ffi_correct.rs`, `research/p5-memory.md`, `tests/test_p5_*.py` (bindings through the coordinator) | K precondition masks identical, K replay metrics within A's tolerances (and L1's archive if it imports `core_campaign`), peak RSS per cell measured; `grid.rs` untouched |
| P1 | **Solver and fused pass**: rayon over (time bin, frequency chunk), conversions hoisted out of the iteration loop. Solver bit-identical; fused pass within 1e-12. 0.345 s → about 0.06 s; whole array about 89 → 13 s per solve (estimate). | `core/src/solve.rs`, `core/src/fused.rs`, `examples/bench_p1_solver.py`, `tests/test_p1_solver.py`, `research/p1-solver.md` | `bench_core_f.py check --target solve` bit-identical at 1, 4, 16 threads; phase 2 validator |
| P3 | **SumThreshold**: rayon over baselines, per-thread scratch, vectorised box filter. Bit-identical. 1.63 → about 0.35 s; whole array about 7 → 1 min (estimate). | `core/src/sumthreshold.rs`, `tests/test_p3_flags.py`, `research/p3-sumthreshold.md` | D comparator flag for flag; K additions hashes |
| P6 | **Frozen Python hot spots, ported**: trend candidates by prefix sums (31 s → about 3 s), signal `cond`/`inv` per gain (35 s → about 20 s). Frozen modules untouched. | new `python/rangtoy/core_trend.py`, `python/rangtoy/core_signal.py`, `tests/test_p6_*.py`, `research/p6-python-hotspots.md` | trend and signal comparators pass with identical counts |
| P4 | **Survey eigensolver**: tridiagonal QL replaces Jacobi; statuses identical. Survey 0.73 → about 0.28 s; signal −11 s (estimate). | `src/linalg.rs`, `src/response.rs`, `tests/test_p4_eigen.py`, `research/p4-eigen.md` | section 6, phase 2, signal and prospective comparators; survey counts and statuses identical |
| P8 | **History**: 23 frozen recipes, `tools/flagging/`, 6 recipe-only modules and their tests to `history/`; archives untouched. About −6,200 live lines in 70 files. | the moved files, `history/README.md`, `research/p8-history.md` | check-all passes; this review's suite passes unchanged |
| P10 | **Test-suite speed** (section 2.9). | the slow test files named there, `research/p10-tests.md` | same tests, same assertions, suite time measured |
| P7 | **Architecture** (after W1 and P1–P6): drop ctypes, root-crate kernels into the extension, GIL released, `catch_unwind` everywhere. | `python/rangtoy/core.py`, `core_grid.py`, `core_weights.py`, `core_flag.py`, `core_zarr.py`, `core_ms.py`, `projector.py`, `core/py/src/lib.rs`, `core/src/ffi*.rs`, `src/*.rs` C ABI, `tests/test_core_backends.py`, `research/p7-architecture.md` | backends comparator, then the suite; no `cargo` call at import |
| P9 | **One CLI and archive format**, comparators on `core_compare`, OpenBLAS pinned at entry (after P7). | `python/rangtoy/core_cli.py`, `core_compare.py`, `examples/compare_core_*.py`, `examples/run_core_*.py`, `recipes/core-*.yaml`, `tests/test_core_cli.py`, `research/p9-cli.md` | every comparator verdict and count identical through the new CLI |
| P11 | **Extract and retire the frozen modules** (after P6, P7): verbatim copies of the executed 31 % into `core_*`, then the 21 frozen modules and their tests to `history/`. About −7,300 live lines (estimate). | `python/rangtoy/flagging*.py`, `imaging_sensitivity.py` (moved), new `core_policy.py` and siblings, the imports of the `core_*` drivers, the frozen-module tests, `research/p11-extract.md` | the suite of this review passes with identical counts; coverage shows no `history/` import on a live chain |

**Sequencing.** P0 first (it edits the manifests every Rust task needs).
P2, P5, P1, P3, P6, P4, P8 and P10 own disjoint files and run in
parallel; P5's PyO3 binding and `pub mod` line, and P6's `core_cli`
switch, go through "For the coordinator" because `core/src/lib.rs`,
`core/py/src/lib.rs`, `python/rangtoy/core.py` and `core_cli.py` are
coordinator files. P10 must not edit tests that P8 moves (P8 first if
both touch `tests/test_flagging_{concurrent,parallel,provenance,public,transfer,uncertainty}.py`).
P7 needs W1's wheel on main and runs alone after P1–P6 (it rewrites the
wrappers those tasks bind into). P9 runs after P7 (both change entry
points and `core_cli.py`); P11 after P6 and P7 (it rewires the drivers' imports). Three CPU-heavy tasks at a time is the useful
limit on 8 physical cores.

## 5. For the coordinator

- **Files.** Added only: `research/simplification-review.md` and
  `research/results/profiles-20261030/` (inventory, timings, classified
  profiles, one SVG flamegraph, convergence curve, coverage summary, and
  the measurement scripts, which reference this task's scratch path for
  the driver and need `S=` adjusted to rerun). No code, recipe, test or
  shared file changed.
- **big-plan.md status line.** "S1 done 2026-10-30 (`simplification-review.md`):
  every archive reproduces; the core is single-threaded and FFT-bound at
  four stations and memory-bound (≈0.87 kB per cell, ≈88 GB) at the whole
  array; wave 2 cut as P0–P11 (P0 by the coordinator first)." Replace the
  plan's "Wave 2 (expected shape)" list with section 4's table, or link it.
- **STATE.md, new top entry.** "Simplification review S1 (big plan wave 1),
  2026-10-30 (measured; no code changed). Every archived chain was re-run
  and reproduces its archived outcome (29 timed steps plus the phase 1
  and 3c-a validators, the fetch checker and the backends comparator; the
  offline task K
  replay matches the archived gains, dirty images and PSFs hash for hash).
  The core runs one thread per stage: 87 % of the K chain's samples are in
  Rust, under 1 % in Python glue, and 15 of 16 hardware threads stay idle.
  The six K images are 67 % of the non-fetch time and 83 % of each image
  is the hand-written Bluestein FFT. Peak memory is about 0.87 kB per
  visibility cell against 84 B of inputs, so the whole-array chunk (100.9 M
  cells) would need about 88 GB as the K code is written. Thin LTO plus
  `x86-64-v3` code generation cut instructions by 22 % with bit-identical
  results. The 50-iteration solver cap is not convergence: held-out MSE
  settles within 2e-5 by 12 iterations, but gain products move 1.3e-3
  between 50 and 91 iterations, so changing the cap is a science protocol.
  The test suite's time is 98 % in three pointing modules (JAX/XLA and
  dense algebra, 145 threads). Wave 2 tasks P0–P11 are cut in
  `simplification-review.md` section 4 with owner files and archives."
- **tool-timings.md rows.** The "Timings" table below, prefixed "S1".
- **README.md.** An index line for `simplification-review.md`.
- **For L1 (whole array), if not already handled.** `core_campaign`'s
  `run()` keeps six solves with complex128 residuals (64 B per cell) and
  computes gain correction in NumPy (about 330 B per cell transient);
  reusing those functions at 56 stations needs about 88 GB. Keep one
  solve's residuals at a time, take the MAD scores from the fused pass
  (`scores=True`), and image arms one at a time; P5 makes this permanent.
- **Upstream, RATT (for U1).** QuartiCal `complex` convergence (extends the
  existing 50-iteration-cap note with a measured curve, reproduced on the
  port that equals QuartiCal to 3.3e-16 at 50 iterations): on the LUNO
  1934−638 four-station slice, 7.3 % of intervals pass the 1e-7 criterion
  at 8 iterations, 49 % at 15, 98.33 % at 45; the default stop fraction
  0.99 is reached only at 91 iterations; held-out MSE is within 2e-5
  relative by 12 iterations while gain products still move 1.3e-3 between
  50 and 91. A loss-based or gauge-invariant criterion would stop an
  estimated 3–5× earlier. U1 should reproduce it on QuartiCal's latest release before
  filing. No Tricolour, dask-ms, africanus, Stimela or CARACal item.
- **Upstream, non-RATT (for `non-ratt-observations.md`).** (1) NumPy's
  bundled OpenBLAS (scipy-openblas64) starts 16 spinning threads at import:
  a 0.07 s comparator process burns 0.7–0.9 CPU-s (7–10.6 threads busy);
  with `OPENBLAS_NUM_THREADS=1` the same comparator used 0.09–0.12 CPU-s
  against 0.37–0.50 CPU-s (A/B at load 30). (2) JAX/XLA on CPU starts compile,
  Eigen and execute pools of 16 threads each (145 threads in one pytest
  process), which oversubscribes a shared host; the pointing tests slowed
  about 14× under load 16–33. (3) The extension's `blosc_decode` builds a
  fresh `bytes` per 205 MB DATA tile; 37 % of the section 6 checker's
  samples sit in that frame (first-touch page faults and fill), a cost of
  the decode-to-new-object API rather than of LZ4.
- **User items.** Optional: `docker image prune` and removal of the
  `rang-flagging*:local` images once P8 moves their Dockerfiles to
  `history/` (8.6 GB on disk, 5.6 GB reclaimable now; rebuildable from the
  Dockerfiles, but the frozen campaigns ran in exactly these builds).
- **Evidence to keep.** `outputs/simplification-review-20261030-01`
  (timed suite and its re-runs of every chain), `-02` (py-spy and perf),
  `-03` (probes), `-05` (pytest durations, perf stat), `-06` (coverage),
  `-07-convergence.json`, `-08` (validators, backends, A/B), `-09-check-all.log`; `-00-smoke` and `-04` (an unresolved line-level
  perf attempt) may be deleted. Scratch builds in
  `~/Build/tmp/20261030-rang-s1` were removed at the end of the task.

## Timings (every tool run of this task)

Date for every row: 2026-10-30. Load is the 1-minute average.

| Tool run | Input | Wall | Peak RSS | Notes |
| --- | --- | ---: | ---: | --- |
| `cargo +1.93 build --release --offline` root and `core/`, `maturin develop --release --offline` | worktree (existing `.venv`, Python 3.14) | 0.06 s, 0.01 s, 0.45 s | 37 MB | already up to date |
| `uv pip install numcodecs` and later `coverage` (public PyPI) | `.venv` | not timed | – | numcodecs 0.17.1 for `bench_core_f.py`; coverage 7.17.0 |
| `inventory.py` | checkout at `df42ea0` | under 1 s | – | `inventory.json` |
| labelled smoke of the offline K replay (`outputs/simplification-review-20261030-00-smoke`) | archived K fetch | 19.65 s | 430 MB | included 3.2 s of recompilation by the `stable` toolchain; gains and images hash-equal |
| timed suite `suite.sh` (`-01`), 29 steps | archived inputs of every chain | 377 s in all | 827 MB (task F bench) | load 0.4–4.6; every step exit 0; per-step table in section 2.2 |
| py-spy and perf `pyspy.sh` (`-02`), 10 chains + SVG + 2 perf runs | as the suite | about 6 min | 838 MB | py-spy walls 1.9–73 s (profiler overhead included; not used as walls) |
| probes `probes.sh` (`-03`): OpenBLAS A/B (10 runs), subsets (6), variant builds (3) and checks (7) | archived K fetch, F baseline | 272.5 s of runs + 18.0 s of builds (4.2, 6.9, 6.9 s) | 845 MB | load 13–20; walls noisy, hashes and counts not |
| line-level perf attempt `perfline.sh` (`-04`) | K replay, debug-line build | about 25 s | – | addresses did not resolve to lines reliably; not used |
| `convergence.py` (`-05`, then `-07` with gauge-invariant metrics) | archived K fetch | 11.3 s, 12.4 s | 182 MB | 22 solves each, 1–200 iterations |
| `subset_iters.py` | archived K fetch | not timed (about 10 s) | – | `subset-iterations.jsonl` |
| `perf stat` of the K replay, three builds × 2 | archived K fetch | about 100 s | 413 MB | load 16–19 |
| `pytest -q --durations=0` (once) | 739 tests | 1,060 s | 1.82 GB | 7.7 threads busy; load 16–33 (siblings' check-all running); 739 passed |
| coverage `coverage.sh` (`-06`), 12 chains under `coverage run` (sysmon) | as the suite | 4.4–59.7 s per chain, about 4.5 min | 838 MB | load 18–29 |
| validators and comparators left out of the suite (`-08`): phase 1, phase 3c-a, task G fetch checker, backends comparator against task J, OpenBLAS A/B on the actions comparator (3 + 3) | archived inputs | 5.2 s, 29.0 s, 6.9 s, 1.5 s, 0.12–0.24 s each | 1.9 GB (3c-a) | load 27–30; outcomes in section 1.4 |
| `bash tools/check-all.sh` (once, on commit `7090451`, the review and profiles) | branch | 1,139 s (pytest 739 passed in 1,118 s) | 1.71 GB | overall PASS (root 19 and core 47 Rust tests, clippy, fmt, ext build, ruff, diff-check, 739 pytest); load 18–31 (sibling sessions); log `outputs/simplification-review-20261030-09-check-all.log`; the follow-up commit that adds these rows and the fixups is document-only |
