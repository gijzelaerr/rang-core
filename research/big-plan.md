# Rang big plan: simpler, faster, finished

Written 2026-10-30 on the user's instruction after the core port
([core-parallel-plan.md](core-parallel-plan.md), tasks A–K) was merged. Status: **wave 1 complete 2026-10-30 (U1, S1, W1, L1 merged; L1 null at
array scale); wave 2 running** (P0 applied by the coordinator; P1, P2, P3, P8 merged 2026-10-30; P4, P6, P10
running; P5 after L1, then P7, P9, P11 in the order of `simplification-review.md` section 4). S1 found that
every archive reproduces, that the core is single-threaded and FFT-bound at
four stations and memory-bound (about 0.87 kB per cell, about 88 GB) at the
whole array. Read this, [STATE.md](STATE.md) and the task files it
names before starting work. The coordinating session merges waves day and
night without waiting for the user; nothing in this plan blocks on a user
answer except the two items under "User items".

## User decisions recorded here (2026-10-30, in chat)

- **Licence is settled.** The LUNO data may be used, and any upstream software
  may be rewritten in the core. Stop asking, stop labelling results
  "provisional pending licence", stop carrying the SARAO confirmation as a
  precondition. The observer's permission (Ben Hugo, 2026-10-29 15:36 SAST)
  is the basis; publications cite the SARAO data usage acknowledgement. Raw
  visibilities are still never committed or redistributed, as a data-size
  and provenance rule, not a licence rule.
- **Upstream reporting.** Report bugs and improvements to RATT software
  (QuartiCal, Tricolour, dask-ms, codex-africanus, Stimela, CARACal,
  Crystalball, pfb-imaging and other `ratt-ru` repositories) as GitHub
  issues, after reproducing each on the latest release. Added 2026-10-30
  (user, in chat): CARACal and Stimela (`caracal-pipeline` repositories) may
  be reported too. Anything outside those
  (WSClean, casacore, Numba, Zarr/numcodecs, blosc, OpenBLAS) is listed in
  [non-ratt-observations.md](non-ratt-observations.md) and not reported.
- **Distributable wheel.** Build the binary wheel of `rangtoy` with the core
  extension for Linux, test it on clean interpreters, publish the build in CI.
- **Name (user, 2026-10-30).** The distribution is published as **`ra-ng`**
  ("radio astronomy next generation"; `rang` on PyPI belongs to an unrelated
  package). The import name becomes `rang` unless the user objects (it
  would collide only with that unrelated package installed side by side;
  the alternative is `ra_ng`). The rename from `rangtoy` is task P12, after
  P7 and P9, which touch the same entry points: package directory, imports,
  extension module `rang._core`, CLI, tests, recipes, docs and CI; archived
  receipts and research notes keep the historical `rangtoy` paths. No PyPI
  upload before the rename.
- **Science continues until there is no more research to do**, in parallel
  sessions, under frozen protocols as before. "The original experiment" is read
  as the active one, gain-TV-guided flagging, run to a positive or a settled
  negative result; after that the beam/pointing question that started the
  project returns on real data with the core.
- **Simplification and speed first.** A holistic review of the whole process
  (mathematical, computational, architectural) with measured proposals, then
  implementation in parallel.

## Goals and how each is judged

| Goal | Done when |
| --- | --- |
| G1 Simpler | Measured: fewer stages, modules, recipes and lines for the same archived results; the comparators still pass bit-for-bit or within frozen tolerance. Every removal names what replaces it. |
| G2 Faster | Measured on the archived LUNO chunk-0 inputs and the fixture: per-stage wall and RSS before/after, same results. Targets below. |
| G3 Science finished | Each open question has a frozen protocol, a run and a verdict in STATE; negative results count. |
| G4 Upstream | Every RATT observation either filed as an issue (link in `upstream-notes.md`) or recorded as not reproducible on the latest release. |
| G5 Wheel | `pip install rangtoy-*.whl` on clean Python 3.10–3.14 Linux runs the comparators; CI builds it. |

Speed targets (measured 2026-10-30 baselines on the four-station slice,
`core-k-luno-campaign.md`): solve 0.32 s per arm, Tricolour port 1.55 s,
TV loop 1.7 s, dirty image 3.9 s, decode 0.36 s. Whole-array chunk 0 (56
stations, 1540 baselines, 2048 channels) is the real target and has no
baseline yet; wave 1 task L1 measures it. Targets: solve and gridder scale
near-linearly with cores (16) and the gridder also runs on the GPU; the fused
pass is memory-bound at the decode rate; one process, one pass over the data.

## Rules for every session

Unchanged from `core-parallel-plan.md`: WSL, own worktree
`~/Worktrees/rang/<slug>` on branch `<slug>` from `origin/main`, `outputs`
symlinked read-only, fresh `outputs/<slug>-<date>-NN` directories, own files
only, shared files (README, STATE, tool-timings, upstream-notes, `core/src/lib.rs`,
`core/src/ffi.rs`, `python/rangtoy/core.py`, `core/py/src/lib.rs`,
`core_cli.py`) edited only by the coordinator from each task's "For the
coordinator" section, frozen protocol before code, comparator precondition,
failures recorded as frozen, post-hoc steps labelled, every tool run timed,
`bash tools/check-all.sh` once before the final commit with
`PATH=$HOME/.cargo/bin:$PATH`, Rust 1.93, public PyPI only, commits as
Gijs Molenaar <gijsmolenaar@gmail.com> without AI attribution or co-author
trailers, no pushes to main, no force-push. Exception for this plan: a
simplification task may delete or move files owned by nobody else once its
proposal is merged in the review (wave 2), listing every deletion.

Host: 16 cores, 30 GiB RAM, 908 GB free, NVIDIA RTX 4070 Ti 12 GB with CUDA
13.5 visible in WSL (about 10.5 GB of it is held by another process at the
time of writing; GPU tasks must check free memory and record it). Run work
likely to exceed two minutes in the background. Avoid more than one full
pytest run per task; share the 16 cores.

## Wave 1 (independent; started 2026-10-30)

| | Task | Owns | Done when |
| --- | --- | --- | --- |
| S1 | **Simplification and optimisation review.** Profile the whole chain (fixture and LUNO chunk 0 four-station, then whole-array when L1's inputs exist) with `perf`/`py-spy`/`cargo flamegraph`; inventory every stage, module, recipe, comparator and container; for each propose keep/merge/delete with the replacement and the archived result that proves it; list optimisation opportunities with expected gain: rayon parallelism (baselines, channels, w-layers), SIMD/vectorisation of the fused pass and SumThreshold, GPU (wgpu or cudarc) for gridding/FFT and the solver's normal equations, mathematical shortcuts (solver initialisation and convergence criterion, exact-rank tests replacing the eigensolver, TV in one pass with the residuals, step fusion so the data are read once), architectural (one CLI, drop the ctypes path once the wheel exists, retire the frozen QuartiCal recipes and containers to history, one results archive format). Deliver ranked proposals with measured profiles, each sized as a wave 2 task with owner files. Read-only: no code changes. | `research/simplification-review.md`, `research/results/profiles-20261030/` | report merged; wave 2 tasks cut from it |
| L1 | **Whole-array LUNO campaign.** Protocol then run of the gain-TV-guided flagging campaign on LUNO row chunk 0 with all 56 stations (DATA tiles already in `outputs/luno-solve-20261029-02/inputs`; FLAG/WEIGHT/MODEL tiles fetched as needed by `core_fetch`), 1934−638, same arms and decision rule as task K, PSF box set from the array resolution, Tricolour first-pass and mild as baselines, cost and quality per stage. This is the first measurement at the scale the method was designed for and the speed baseline for G2. | `python/rangtoy/core_campaign_array.py` (may import `core_campaign`), `examples/*_luno_array.py`, `tests/test_core_campaign_array.py`, `research/luno-array-campaign.md`, `research/results/luno-array-campaign.json` | criteria pass as frozen or failure recorded; verdict positive or null. **Done 2026-10-30: null**; criteria 2, 4, 6 failed as frozen (FLAG_ROW derivation, 0.83 convergence, undecidable headline), amendment 1 matched calls null on every pair. |
| W1 | **Distributable wheel.** `maturin build --release --manylinux 2_28` (abi3-py310) in the `quay.io/pypa/manylinux_2_28_x86_64` container, auditwheel-repaired, installed into fresh uv venvs for 3.10–3.14 and smoke-tested with the backend comparator and the task I imaging check; aarch64 by zig cross if it works in an hour, else recorded; a GitHub Actions workflow `.github/workflows/wheels.yml` that builds, tests and attaches wheels to a release on tags `v*`; `tools/wheel/build.sh`. Publication to PyPI is prepared as one documented command but not executed (user item). | `.github/workflows/wheels.yml`, `tools/wheel/`, `research/wheel.md`, `pyproject.toml` version/metadata lines only | wheel installs and runs on clean 3.10–3.14; CI green on the branch. **Merged 2026-10-30**: x86_64 and aarch64 (unrun) wheels, sdist, workflow; first CI run on the merge push. |
| U1 | **Upstream reporting.** For every RATT observation in `upstream-notes.md` (QuartiCal: JIT cost and cache, no HISTORY row, `fastmath`, `complex` ignores `reference_antenna`, conjugate-baseline weight reuse, 50-iteration cap convergence; dask-ms: FEED fan-out, object-column encoding; Tricolour: licence metadata, compile cost; CARACal strategy intermediate state): reproduce on the latest release in a fresh uv venv (3.13) with a minimal public-data or synthetic script, write the issue text to `research/upstream-issues/<repo>-<slug>.md` (title, versions, reproduction, expected, observed, proposed fix or PR sketch), file it with `gh issue create` on the `ratt-ru` repository, record the URL. Observations that do not reproduce on the latest release are recorded as such and not filed. Non-RATT items (WSClean `CalculateMsLimits`, `-store-imaging-weights`, OpenBLAS/eigensolver, Zarr chunking of the public store, blosc block tables) go to `research/non-ratt-observations.md`. | `research/upstream-issues/`, `research/non-ratt-observations.md` | every observation filed or closed with a reason. **Done 2026-10-30**: QuartiCal #452, #453; Tricolour #110, #111 filed; nine closed; non-RATT list written. |

## Wave 2 (cut from the review, 2026-10-30)

The task table with owner files, archives and sequencing is section 4 of
[simplification-review.md](simplification-review.md). In short: P0 release
profile and crates (coordinator, done on main); P2 gridder FFT and parallel
w-layers; P5 memory (one copy of the cube; after L1 merges, since it edits
`core_campaign.py`); P1 solver and fused pass parallel over intervals; P3
SumThreshold parallel over baselines; P6 frozen Python hot spots ported; P4
survey eigensolver; P8 frozen recipes, containers and recipe-only modules to
`history/`; P10 test-suite speed (after P8); P7 architecture (drop ctypes, GIL,
`catch_unwind`; after W1 and P1–P6, alone); P9 one CLI and archive format
(after P7); P11 extract and retire the frozen modules (after P6 and P7); P12
rename `rangtoy` to `ra-ng`/`rang` (after P7, P9 and P11). Three CPU-heavy
tasks at a time on 8 physical cores.

## Wave 3 (science, after L1's verdict; parallel where independent)

- L2 PKS 1830−211: model decision in the protocol (stored MODEL_DATA with its
  cross-hand terms, or a scalar point model predicted by the core), then the
  same campaign. Independent of L1's verdict.
- L3 native data: when the observer's full-resolution L-band set arrives,
  record it in `flagging-luno-candidate.md`, fetch the calibrator scans, and
  run the campaign on native FLAG/WEIGHT/SIGMA. Not blocking; starts when the
  data exist.
- L4 verdict and synthesis: if L1, L2 and (when possible) L3 are null, write
  `research/flagging-verdict.md`: what was tested, every negative result,
  what would still change the answer, and close the experiment in STATE. If
  any is positive, the follow-up is a matched CARACal full-pipeline
  comparison on the same data (quality and cost), which is what the novelty
  rule asks for.
- B1 beam and pointing on real data: protocol for the original research
  question on LUNO with the core (predictor, solver, the existing pointing
  solver and JAX reference path): can small pointing/beam corrections be
  constrained on the calibrator and target scans, selected by
  distinguishability from the sky, without distorting faint emission? Starts
  once L4 is written, or earlier if L1 is null and cores are free.

## Wave 4 (consolidation)

- Documentation pass: README, `research/README.md`, STATE trimmed to current
  truth with history linked; AGENTS.md updated for the simplified layout.
- Release candidate: version bump, wheel built by CI from a tag, the PyPI
  command handed to the user.
- Final review session (`/code-review` style) on the simplified core.

## Coordinator loop (this session, day and night)

1. Start every task of the current wave (sessions when the app allows,
   background agents otherwise), each with a brief that stands alone.
2. On each report: verify the branch (log, diff stat, check-all log, the
   research file's measured section), merge with `--no-ff`, apply "For the
   coordinator", run `bash tools/check-all.sh`, commit, push, remove the
   worktree and branch, update this plan's status line and STATE.
3. When a wave is merged, cut the next wave from the plan and the review,
   and start it. Never wait for the user; put what needs them under "User
   items" and carry on.
4. Keep `tool-timings.md`, `upstream-notes.md` and memory current.

## User items (not blocking)

- Publish to PyPI as `ra-ng` after task P12 (rename): create the project on
  PyPI with trusted publishing for the `wheels.yml` workflow of
  `gijzelaerr/rang`, or run the command in `research/wheel.md`.
- Delete `~/Build/tmp/20261029-rang-core`, the root-owned
  `outputs/core-a-20261029-00-smoke`, and the 725 MB
  `outputs/core-k-20261030-01/fetch` (same bytes as `core-g-20261029-01`).
- Forward the observer's full-resolution LUNO set when it arrives.
- Prune the pinned `rang-flagging*:local` Docker images and the three
  dangling ones (about 11.6 GB) if the disk is wanted; no live chain uses
  them, and `history/README.md` says how the frozen campaigns were run.
