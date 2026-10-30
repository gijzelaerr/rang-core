# Rang big plan: simpler, faster, finished

Written 2026-10-30 on the user's instruction after the core port
([core-parallel-plan.md](core-parallel-plan.md), tasks A–K) was merged. Status: **wave 1 complete 2026-10-30 (U1, S1, W1, L1 merged; L1 null at
array scale); wave 2 running** (P0 applied by the coordinator; P1–P12 merged 2026-10-30; PC1 fixed the L1/L2
preconditions and put them in the tests; next X2 in the order of `simplification-review.md` section 4). S1 found that
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
  be reported too; so may `saopicc` (DDFacet, killMS; user, 2026-10-30), with
  pull requests where a fix is clear. Anything outside those
  (WSClean, casacore, Numba, Zarr/numcodecs, blosc, OpenBLAS) is listed in
  [non-ratt-observations.md](non-ratt-observations.md) and not reported.
- **Distributable wheel.** Build the binary wheel of `rangtoy` with the core
  extension for Linux, test it on clean interpreters, publish the build in CI.
- **Name (user, 2026-10-30, final).** Project, GitHub repository and PyPI
  distribution are **`rang-core`** (`gijzelaerr/rang-core`, renamed the same
  day from `rang` via `ra-ng`; `rang` on PyPI belongs to an unrelated package
  and PyPI's confusable-name rule rejected `ra-ng`). The Python module and
  core module name is **`rang`** (`import rang`, extension `rang._core`).
  "rang" is also Dutch for rank, which the identifiability survey measures
  first. The rename from `rangtoy` is task P12, after P7 and P9, which touch
  the same entry points: package directory, imports, extension module, CLI,
  tests, recipes, docs, CI, the wordmark (`rang-core` with the fringe as the
  hyphen); archived receipts and research notes keep the historical
  `rangtoy` paths. No PyPI upload before the rename.
- **Repository and publishing (user, 2026-10-30).** The GitHub repository is
  `gijzelaerr/rang-core` (renamed 2026-10-30; GitHub redirects the old
  names; remotes updated; the local folders `~/Github/rang` and
  `~/Worktrees/rang` move to `rang-core` with task P12, when no session depends
  on the old path). The user wants the package on PyPI: the `wheels.yml`
  workflow gets a publish job on `v*` tags through PyPI trusted publishing
  (`pypa/gh-action-pypi-publish`, environment `pypi`); the user registers
  the pending publisher on pypi.org once (project `rang-core`, owner
  `gijzelaerr`, repository `rang-core`, workflow `wheels.yml`, environment
  `pypi`) and creates the first tag after P12 and wave 4. The coordinator
  never tags.
- **Solver science (user, 2026-10-30: "do what you propose").** One wave 3
  protocol (task L5) fixes the QuartiCal qp weight swap (issue 452) in the
  core as a validated deviation behind a compatibility flag that keeps the
  archived behaviour, and studies a loss-based or gauge-invariant
  convergence criterion against the 50-iteration cap (S1 section 2.7, L1's
  0.83 at array scale): held-out error, gain products and cost on the
  fixture, the four-station slice and the whole array; the default changes
  only if the protocol passes, and every archive comparator keeps passing
  under the compatibility flag.
- **Cross-platform (user, 2026-10-30).** The core must build and run
  natively on Linux, Windows and macOS, so development no longer depends on
  WSL and the GPU path no longer depends on CUDA. Consequences: wheels and
  tests for `manylinux` x86_64/aarch64, `macosx` arm64/x86_64 and
  `win_amd64` in `wheels.yml`; no bash, `/usr/bin/time`, `/tmp` or
  POSIX-only paths on the live Python paths (pathlib, `subprocess` without a
  shell, `resource`/`psutil` for RSS); the GPU track uses `wgpu`
  (Vulkan/Metal/DX12) behind a cargo feature instead of CUDA; the
  checks run as a Python or Rust entry point (`rang-core check`) that
  `tools/check-all.sh` wraps. Tasks X1 and X2 below. The WSL checkout stays
  the data host for the LUNO runs until a native Windows run reproduces an
  archive.
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
rename `rangtoy` to `rang` (project `rang-core`; after P7, P9 and P11); X1 cross-platform
build, CI matrix and portability of the live paths (after P7; Windows and
macOS wheels and tests, native Windows reproduction of one archive); X2 GPU
gridder and FFT through `wgpu` behind a feature (done 2026-10-30, `x2-wgpu.md`:
f64 passes C/I/K on the RTX 4070 Ti, 2.5–3.3× at four stations, 1.2× whole
array; f32 experimental; after P2 and X1; measured
against the task C/I/K comparators on the RTX 4070 Ti from native Windows,
no CUDA toolkit); PyPI publish job in `wheels.yml` (with X1). Three
CPU-heavy tasks at a time on 8 physical cores.

## Documentation, teaching and upstream fixes (user, 2026-10-30; parallel)

- D1 documentation site (done 2026-10-30, `d1-docs.md`: Sphinx, furo, myst-nb;
  Pages deploy from `main` once the user enables Pages): Sphinx or MkDocs built by CI and published on
  GitHub Pages; installation from the wheel, concepts (MS and zarr ingest,
  gains, TV maps, SumThreshold strategies, weighting, gridding), API
  reference from the core wrappers' docstrings, the research story with
  links to the archives; tutorials are notebooks executed in CI on small
  public data (`nbval`/`papermill`). After P12 (uses the `rang` name).
- D2 notebook tooling: a `notebook` module (`rangtoy.notebook`, renamed with
  P12) for Jupyter: load the fixture scan or the four-station LUNO slice via
  the range fetch, inspect flags and weights per baseline and channel, solve
  and view gain amplitude, phase and TV maps per antenna, run a Tricolour
  strategy step by step, image and compare dirty images and PSFs; plots as
  plain functions, `ipywidgets` as a thin steering layer (solution
  intervals, strategy, robustness, iteration cap → held-out error and
  image). Dependencies in a `[notebook]` extra. Done 2026-10-30
  (`d2-notebook.md`; five notebooks in `notebooks/`).
- D3 science notebooks (done 2026-10-30, `d3-science-notebooks.md`): the two research questions as guided notebooks,
  gain-TV-guided flagging with the null results on real data and the
  decision rule, and the beam and pointing question with the pointing
  solver, observability audits and the JAX reference path; the wave 3
  protocols map onto them. After D1.
- U2 upstream fixes (done 2026-10-30, `upstream-prs.md`: stimela#619/#620,
  tricolour#113/#114, QuartiCal#455; tricolour#112 merged, caracal#1708
  approved): file the remaining findings after
  reproduction (CARACal first-pass strategy on pre-flagged data, Stimela on
  Python 3.14, QuartiCal convergence criterion with the measured curve,
  Tricolour rows-as-lanes if faster in Numba) and open pull requests from
  a fork under the user's account for every filed issue with a fix
  (QuartiCal #452, Tricolour #110 and #111 with the CARACal strategy YAMLs,
  Stimela 3.14, the rest as they are confirmed), each with a regression
  test and the project's own test suite run; `research/upstream-prs.md`.
- Logo (approved by the user 2026-10-30): an interferogram mark, a round
  aperture filled with fringe bands fading to the rim and one amber point,
  the `rang-core` wordmark (drafted as `ra-ng`, to be re-cut with P12) with a
  single fringe as the hyphen; ink `#10131a`,
  white and amber `#e8a33d` only. Assets in `docs/logo/` (SVG); PNG and ICO
  renders come with D1.
- Follow-up: Tricolour 0.5.0 is a rework about to be released (maintainer
  reply on issue 110, 2026-10-30); re-validate the task D port against its
  flags once it ships (the archived oracle came from 0.2.1). RV1 done 2026-10-30 (`rv1-revalidate.md`): 0.5.0-dev `367ff54`
  identical to 0.2.1 and the port on task D's inputs; the `uvrange` rule
  differs (RV2 proposed); QuartiCal v0.2.8-dev reproduced by the core's
  `qp_weights=transposed` (RV3 proposed). Rerun both scripts when the
  releases are tagged. Proposed: RV2, the 0.5.0 `uvrange` rule as an opt-in
  `uvrange_rule="0.5"` of the core flag port (default `"0.2"`, archives
  unchanged; equal to the released 0.5.0 chain on a synthetic 300/700/900 m
  case and one L1 row chunk), when 0.5.0 is released or a campaign needs
  it; RV3, `qp_weights=transposed` as the solver default once 0.2.8 is
  released (`qp_weights=archived` keeps every 0.2.7 comparator; L5 measured
  no held-out effect, so it is alignment, not science; the user decides).
- DDFacet/killMS: feasibility done 2026-10-30 (`ddfacet-feasibility.md`):
  no faithful port. DF0 (oracle container with WSClean 3.7 and a simulated
  MeerKAT field) and DF1 (exact wgridder-algorithm gridder, first protocol)
  can start beside the science wave (DF1 done 2026-10-30, `df1-wgridder.md`:
  all gates pass; item 0 attributed to WSClean padding-1.2 aliasing; DF2a done
  2026-10-30, `df2-wgridder-speed.md`: at ducc0's speed on whole-array inputs,
  1.5–2.3× on four-station images; DF2b done 2026-10-30 (`df2b-wgrid.md`): `gridder="wgrid"` in the C/I/K/L1
  drivers, `wstack` the bit-identical default, every archive within 4e-7 of
  WSClean 3.7's wgridder; `--gridder` for the campaign runs open; it was to add `gridder="wgrid"` to the
  imaging drivers with a tolerance restated from the rounding floor and
  re-tolerance the C/I/K/L1 archives against WSClean 3.7's wgridder from
  DF0); DF2 puts it into the imaging chains
  before B1's imaging; DF3–DF5 (facets with per-facet Jones, scalar
  CohJones, Hogbom/multiscale) after B1 says what it needs; DF1b (w-towers)
  when memory binds; DF6 (facet-IDG on `wgpu`) after X2. User decisions
  (2026-10-30): `saopicc` (DDFacet, killMS) issues and pull requests may be
  filed like the RATT ones (task U3, done 2026-10-30: six issues, four PRs,
  `upstream-saopicc.md`); a simulated MeerKAT target field is the
  DF3–DF5 oracle to start with; the core must read and write the file
  formats of the tools it replaces, not just convert for oracle runs:
  DDFacet `DicoModel` sky models, killMS solution files, QuartiCal gain
  stores, CASA calibration tables, Tigger/`.lsm` sky models, and the
  Measurement Set and zarr stores it already reads (task DF-IO, with DF2;
  done 2026-10-30, `dfio-formats.md`: `rang.formats` and `rang-core formats`,
  each format judged by its own tool; open: the core's own applycal model for
  Df to 1e-6, DicoModel and BBS writes, parametrised QuartiCal terms, H5parm
  fulljones/tec, DDFacet reading a core killMS file).
- X1 done 2026-10-30 (`x1-crossplatform.md`): native Windows build, task D
  comparator bit-identical on Windows, five-platform wheel matrix and the
  PyPI publish job; portability fixes for the live paths listed for P7/P9/P12.
- E2 done 2026-10-30 (`casacure-evaluation.md`): verdict (c), rang's own
  writer; casacure stays an optional pinned second oracle. Follow-on tasks:
  E3 done 2026-10-30 (`e3-table-writer.md`); E3 core table writer (in-place `putcol` for SSM and the tiled managers,
  `addcols` as casacore does, `table.dat`/description/keyword writer, lock
  sync record; after P7, parallel with P9); E4 done 2026-10-30 (`e4-table-create.md`); E4 table creation (`default_ms`
  with subtables, CASA caltables G/B/K/Df with `table.info`; after E3; feeds
  DF-IO); E5 ISM arrays, strings and big-endian writes (small, after E3); T1
  casacure as the second oracle in the Windows and macOS test jobs; B1
  freezes the geodetic parallactic-angle convention with astropy as
  reference.
- E2 casacure evaluation (started 2026-10-30; pointer from Oleg Smirnov via
  the user): `casacure` (Tim Molteno, LGPL-3.0-or-later, crate and PyPI
  3.8.35 tracking casacore 3.8) is a pure-Rust casacore table system that
  reads and writes Measurement Sets (StandardStMan, IncrementalStMan,
  TiledColumnStMan), a TaQL subset and a measures subset, with wheels for
  Linux, macOS and Windows up to Python 3.14; dask-ms 0.2.32 passes on it and
  QuartiCal PR #445 routes through it. If it reproduces task E's
  column-exact reads, the core's MS reader (`core/src/ms.rs`) becomes an
  oracle and casacure the MS I/O dependency (reads, writes, calibration
  tables, the Windows gap of X1 and the DF-IO formats). Tim Molteno is also
  porting DDFacet and killMS to casacure (PR #445 discussion), which bears
  on the DF tasks: user item, make contact before DF3.
- Ecosystem survey done 2026-10-30 (`ecosystem-survey.md`); tasks it adds,
  with owner files in its "For the coordinator": O-CASA done 2026-10-30
  (`o-casa.md`; CASA/CARACal matched baseline ×1.10 worse held-out than the
  core's port on the parallel hands; FS1 and L4 unblocked; FS1 done
  2026-10-30, `fs1-flux-standards.md`: setjy standards bit-exact, PB2017
  opt-in pending casarundata) (CASA 6.7.6 oracle
  container on KERN-10, CARACal's crosscal sequence by hand on the LUNO 1934
  slice, tables and CORRECTED_DATA archived; the DF0 base), FS1 (flux
  standards SR2016, PB2010, PB2017 in the core, `setjy` oracle), DF-IO-CT
  (CASA caltables), DF-IO-H5 (H5parm subset), DF-IO-SKY (Tigger lsm, WSClean
  and BBS text, DicoModel read-only), MK1 (done 2026-10-30, `mk1-katdal.md`: `[meerkat]` extra and `rang.meerkat`; exact on a synthetic MVFv4 archive against raw chunks, katdal and mvftoms; the LUNO cross-check waits for a matching MVF) (`[meerkat]` extra with katdal for
  L3), A-FLAG (AOFlagger as second SumThreshold oracle), L5-C (CASA `gaincal`
  as second comparator), DF5-O (WSClean multiscale and pfb-imaging as
  deconvolution oracles), NB-CARTA (optional notebook helper). The matched
  CARACal baseline below is O-CASA plus the Tricolour port.
- Later, not started: a matched full CARACal pipeline baseline on the LUNO
  data (needed if any campaign turns positive) and a benchmark page that CI
  updates from the comparator timings.

## Wave 3 (science, after L1's verdict; parallel where independent)

- L2 PKS 1830−211 (done 2026-10-30, null under both model arms;
  `luno-1830-campaign.md`): model decision in the protocol (stored MODEL_DATA with its
  cross-hand terms, or a scalar point model predicted by the core), then the
  same campaign. Independent of L1's verdict.
- L3 native data: when the observer's full-resolution L-band set arrives,
  record it in `flagging-luno-candidate.md`, fetch the calibrator scans, and
  run the campaign on native FLAG/WEIGHT/SIGMA. Not blocking; starts when the
  data exist.
- L4 done 2026-10-30 (`flagging-verdict.md`): closed as null; 90
  pre-registered calls, 64 null and 26 undecidable, none better or worse;
  cost clause fails on the parallel kernels (4.6–5.9×). L3 stays a standing
  reopening item. B1 started.
- L4 verdict and synthesis: if L1, L2 and (when possible) L3 are null, write
  `research/flagging-verdict.md`: what was tested, every negative result,
  what would still change the answer, and close the experiment in STATE. If
  any is positive, the follow-up is a matched CARACal full-pipeline
  comparison on the same data (quality and cost), which is what the novelty
  rule asks for.
- L1-M done 2026-10-30 (`l1-model-completeness.md`): the stored model is a
  field model and fits best; TV decisions unchanged under all three models;
  model incompleteness did not cause the nulls. C1 proceeds; `rangtoy.lsm`
  is the first DF-IO reader (Tigger ASCII only so far).
- L1-M model completeness (from the literature scan, first wave 3 item after
  P5): re-solve LUNO chunk 0 with CARACal's 196-component PKS 1934−638 field
  model (`caracal/data/meerkat_files/pks1934-638.lsm`, spectral convention
  and apparent-flux question frozen in the protocol; the core predictor
  applies no beam, as CARACal's prediction does not) under the same frozen
  arms as L1; held-out error, gain TV and the decision rule against the point
  model. Heywood et al. 2020 (arXiv:2004.00454): a point model leaves
  0.2–0.5 % structured amplitude errors.
- C1 done 2026-10-30 (`c1-closure-arm.md`): null on the decision; closure TV
  sees GNSS-band and antenna-additive structure that gain TV cannot, none of
  it a flag that helps. L4 verdict next.
- C1 closure-invariant arm (after L1-M, before L4): GL(2,C) closure traces as
  a gauge-free flagging signal and comparator, isolating what per-antenna
  gains cannot absorb. A1 done 2026-10-30 (`a1-rfi-audit.md`): the emptied
  station-bins are GNSS-band residue, excision as intended, no report; L4,
  L1-M and C1 pre-register dropping those bins' held-out samples after the
  split, with the matched-sample rule as fallback.
- B1 additions: B1-0 freezes SARAO's 2023 holography cubes (DOI
  10.48479/wdb0-h061) as the reference beam with katbeam as control; B1-1
  freezes the SARAO/SKA Gaussian pointing-offset fit and physical pointing
  self-calibration as the baselines to beat at matched cost. L4 cites the
  solution-interval and regularisation literature in "what would change the
  answer".
- L5 solver science (done 2026-10-30, `l5-solver-science.md`: no default
  change as frozen; `RANG_SOLVE_OPTIONS` opt-in with the weight fix and
  Anderson m = 3): the issue 452 weight-swap fix behind a compatibility
  flag and the convergence criterion study, one protocol (user decision
  above); after P1 (done) and L1 (done), independent of L2/L3.
- B1-0 and B1-1 (i) done 2026-10-30 (`b1-beam-pointing.md`): holography beam
  product frozen (CC BY-NC 4.0, derived statistics only committed), katbeam
  and EIDOS measured against it, the SARAO/SKA Gaussian fit ported bit-exact
  and found weak on the fixture; ESO137 the target; next B1-2 identifiability
  (`beam_identifiability.py`, `measures.py`, `fetch_eso137_pilot.py`), then
  B1-3 pointing self-calibration (`pointing_selfcal.py`) against both
  baselines at matched cost. B1-2 done 2026-10-30 (`b1-2-identifiability.md`):
  not null. Constrainable on the frozen rule: per-antenna pointing and
  squint (ESO137, 1934), array-common pointing and ellipticity (ESO137
  track); width nowhere. B1-3 starts with a per-channel-bandpass rerun of
  the survey and per-antenna beams, then pointing self-calibration and the
  rang method on the surviving directions. It needs a deeper ESO137 field
  model (track image, or a catalogue: user decision).
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

- Enable GitHub Pages once (Settings → Pages → Source: GitHub Actions) so
  the `docs.yml` deploy job stops failing at `configure-pages`; the build job
  and its artifact already pass (D1, 2026-10-30).
- B1-3: allow or refuse an external catalogue (SUMSS, RACS) for the ESO137
  field model; B1-2's protocol allowed only MODEL_DATA or an image, and the
  self-calibrated model is the central radio galaxy only.
- File or decline B1-2's data-store observations on the RATT trackers
  (`upstream-notes.md`, "B1-2 observations": ESO137 subset MODEL_DATA zero,
  DATA uncalibrated, pickled string columns, RECEPTOR_ANGLE; LUNO
  WEIGHT_SPECTRUM 10–60× too pessimistic) and RV1's Tricolour `uvrange`
  release-note request (`upstream-issues/tricolour-uvrange-semantics.md`).
- Rebase rang's Tricolour PR #114 onto `0.5.0-dev` (a push to the user's
  fork; RV1).
- The PyPI pending publisher is registered (user, 2026-10-30) and the tree
  is renamed (P12): tag `v0.1.0` and push the tag; the workflow publishes
  `rang-core`. (Originally: register the pending publisher for `rang-core`, owner `gijzelaerr`,
  repository `rang-core`, workflow `wheels.yml`, environment `pypi`, and, after
  P12 and wave 4, create the tag `v0.1.0`; the workflow publishes.
- Delete `~/Build/tmp/20261029-rang-core`, the root-owned
  `outputs/core-a-20261029-00-smoke`, and the 725 MB
  `outputs/core-k-20261030-01/fetch` (same bytes as `core-g-20261029-01`).
- Forward the observer's full-resolution LUNO set when it arrives.
- Approve the download of CASA's casarundata tables
  (`nrao/VLA/standards/PerleyButler2017Coeffs`, `…2013Coeffs`) so FS1 can
  verify the paper-transcribed PB2017/PB2013 against `setjy`.
- Contact Tim Molteno about casacure and his DDFacet/killMS ports before the
  DF tasks start, to coordinate rather than duplicate.
- Prune the pinned `rang-flagging*:local` Docker images and the three
  dangling ones (about 11.6 GB) if the disk is wanted; no live chain uses
  them, and `history/README.md` says how the frozen campaigns were run.
