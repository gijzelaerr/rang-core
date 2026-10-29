# Stack consolidation feasibility: one Rust core for the rang pipeline

Written 2026-10-29 at the user's request. This is a written study, not an
implementation. Measured facts, estimates and proposals are labelled as such.
Measurements were taken on the WSL2 host in [STATE.md](STATE.md) (16 cores,
30 GiB) and are logged in [tool-timings.md](tool-timings.md). Nothing in this
study changes a scientific result; the archived results in `results/` remain
the record.

## Verdict (summary)

**Partially feasible and worth doing for the inner loop; the edges come last.**
Section 9 adds the single-framework port plan with before-and-after step
counts: about 6–8× fewer boundary crossings per pipeline. A single Rust core with a thin Python API can replace everything that
rang runs *between* reading visibilities and writing diagnostics: sky
prediction, the full-Jones gain solve, residual statistics, TV and trend
guidance, the policy loop, the normal-equation rank/response survey, and a
dirty-image gridder for diagnostics. Measured on the LUNO four-station
1934−638 slice, the current chain spends about 0.5 s on arithmetic that rang
already does natively and 28 s (cold) or 3.6 s (warm Numba cache) in the
QuartiCal process, almost all of it start-up, compilation, graph construction
and table I/O rather than the solve. On the five-track fixture campaign, the 63
QuartiCal subprocesses account for 337 s of a 435 s wall, and the campaign
reads 21.7 GB and writes 55.4 GB to serve an 18 MB visibility cube.

What to port **last and validate first**: the CASA Measurement Set table
system (python-casacore stays at the edge until a Rust reader is needed), the
Tricolour/AOFlagger strategy engines and WSClean. All three are portable from
their sources in weeks for the subset rang uses (section 5), but they are not
on the measured hot path, they are the oracles the port is validated against,
and they are GPL, so translating their code makes the core GPL. casacore
Measures need no port: rang never computes UVW or frames itself. The S3
fetches, which dominate the LUNO chain (about 1,220 s of 1,250 s), are a data
layout problem that no rewrite removes.

Under AGENTS.md's novelty rule, none of this is a scientific contribution. The
wins are framed as matched-quality runtime and resource reductions: the same
archived numbers to the tolerances in section 5, in fewer seconds, bytes and
processes. The honest comparator is QuartiCal with a warm cache (3.6 s), not
the cold 28 s that rang's fresh containers currently pay.

## 1. Inventory

Every external tool and routine rang depends on, where it is invoked, and what
flows across the boundary. Line numbers refer to the checkout at `b7069bf`.

| Component | Version | Role in rang | Invoked from | Data across the boundary | Licence (as installed) |
| --- | --- | --- | --- | --- | --- |
| QuartiCal | 0.2.7 (Numba 0.67.0, dask 2024.10.0) | Full 2×2 complex gain solve, `G.type=complex`, 2×32 intervals, 50 iterations; MAD flagging only in the comparator stage | `goquartical` subprocess in [flagging_workflow.py:330-369](../python/rangtoy/flagging_workflow.py:330); comparator MAD at [flagging_comparators.py:228-245](../python/rangtoy/flagging_comparators.py:228); LUNO at [solve_luno.py:22-50](../examples/solve_luno.py:22) | Reads DATA, MODEL column, FLAG, FLAG_ROW, WEIGHT_SPECTRUM from a CASA MS; writes gains as a zarr store `gains.qc::G`; never writes flags in rang (`output.flags=false`) | MIT |
| dask-ms | 0.2.32 | Reads the QuartiCal gain zarr back into Python; inside QuartiCal, reads the MS | [flagging_workflow.py:383](../python/rangtoy/flagging_workflow.py:383), [solve_luno.py:58](../examples/solve_luno.py:58) | zarr → xarray → NumPy `(time, freq, ant, dir, corr)` → `(t, f, ant, 2, 2)` | BSD-3 (wheel metadata states BSD3 for 0.2.23; 0.2.32 wheel lists none) |
| python-casacore | 3.8.1 | All MS table reads and writes: copies, column adds, FLAG/FLAG_ROW round trips, MODEL/CORRECTED columns, LUNO MS construction | [flagging_workflow.py:102-171](../python/rangtoy/flagging_workflow.py:102), [:282-311](../python/rangtoy/flagging_workflow.py:282); [build_luno_ms.py](../examples/build_luno_ms.py); [flagging_imaging.py:390-456](../python/rangtoy/flagging_imaging.py:390); [flagging_response.py:368-511](../python/rangtoy/flagging_response.py:368); [flagging_caracal.py:149-173](../python/rangtoy/flagging_caracal.py:149) | NumPy arrays ↔ casacore storage managers | LGPL-3 (wrapper); casacore C++ LGPL-2+ (to confirm from the casacore repository) |
| numcodecs / zarr | 0.15.1 / 2.18.7 | Blosc-LZ4 decode of public zarr tiles; `json2` object columns | [flagging_public.py:260-275](../python/rangtoy/flagging_public.py:260); [build_luno_ms.py:26-50](../examples/build_luno_ms.py:26); [extract_luno_support.py:25](../examples/extract_luno_support.py:25) | HTTP object → compressed bytes → NumPy chunk → row/channel subset | MIT |
| Stimela | 2.1.4 | Recipe runner for every campaign (`flavour: python` cabs, `for_loop` scatter) | [recipes/tv-flagging-next.yaml](../recipes/tv-flagging-next.yaml), [run-next.sh:24-37](../tools/flagging/run-next.sh:24) and the other `run-*.sh` | Parameters only; orchestration, logging, `stimela.stats` | GPL-2 per repository (wheel lists none) |
| Docker images | `rang-flagging*:local` | Pinned environments; one container per campaign; three venvs because Crystalball needs psutil ≥ 6.1 and Stimela < 6 ([sky/Dockerfile:1-3](../tools/flagging/sky/Dockerfile:1)); Tricolour needs an older Numba ([comparators/Dockerfile:1](../tools/flagging/comparators/Dockerfile:1)) | [tools/flagging/Dockerfile](../tools/flagging/Dockerfile), `run-*.sh` | Bind mounts of the checkout and `outputs/`; `NUMBA_CACHE_DIR=/tmp/numba` ([Dockerfile:14](../tools/flagging/Dockerfile:14)) | – |
| CARACAL strategies via Tricolour | CARACAL `8f7bb363`; Tricolour 0.2.1 (Numba 0.60.0, dask-ms 0.2.23) | Native full-strategy flagging controls (first pass, mild, soft) on diagnostic MS copies, polarisation mode, numpy window backend | [flagging_caracal.py:54-71](../python/rangtoy/flagging_caracal.py:54), [:149-244](../python/rangtoy/flagging_caracal.py:149) | Reads DATA/FLAG from a copied MS; writes FLAG/FLAG_ROW in place; rang re-reads and unions with original flags | Tricolour GPL-2; CARACAL GPL-2 |
| AOFlagger / CASA flagdata | not installed | Inspected only, as CARACAL alternatives ([flagging-caracal.md](flagging-caracal.md)) | – | – | GPL-3 / LGPL-2.1 |
| WSClean | 3.6-1 (Debian snapshot) | 15 fixed dirty inversions and PSFs: 512², 8″, Briggs 0.5, Stokes I, w-stacking 64 layers, `-niter 0` | [flagging_imaging.py:239-279](../python/rangtoy/flagging_imaging.py:239), [:760-790](../python/rangtoy/flagging_imaging.py:760) | Reads CORRECTED_DATA, FLAG, WEIGHT_SPECTRUM from a copied MS; writes FITS; Python reads FITS with astropy | GPL-3 |
| Crystalball + codex-africanus | 0.4.3 / 0.4.4 | DFT prediction of the SARAO 1934−638 L-band WSClean catalogue (5153 components) into `RANG_SARAO_MODEL_DATA` / `RANG_SARAO_PRIMARY_DATA` | [flagging_sky.py:176-231](../python/rangtoy/flagging_sky.py:176); independent NumPy check [:73-100](../python/rangtoy/flagging_sky.py:73); Africanus `wsclean_predict` for response templates [flagging_response.py:336-365](../python/rangtoy/flagging_response.py:336) | Catalogue text → MS column | Crystalball GPL-2; codex-africanus BSD-3 (wheel lists none; confirm) |
| Flux models | Reynolds 1994 polynomial; `setjy` Perley–Butler 2017 (LUNO HISTORY, not run by rang) | Fixture scalar model `RANG_MODEL_DATA` written as a full column | [flagging_workflow.py:158-170](../python/rangtoy/flagging_workflow.py:158) | 2048 flux values broadcast to a 140×4096×4 complex column | – |
| rang Rust kernels | `src/` (Rust 1.93) | Anisotropic full-Jones TV ([tv.rs](../src/tv.rs)), robust phase-trend slopes ([trend.rs](../src/trend.rs)), Jacobian/normal equations/gauge-aware anchored step ([response.rs](../src/response.rs)), QR projector ([projector.rs](../src/projector.rs)), toy pointing experiment ([lib.rs](../src/lib.rs)) | ctypes via [projector.py:14-26](../python/rangtoy/projector.py:14), [flagging.py:73-85](../python/rangtoy/flagging.py:73), [flagging_influence.py:62-80](../python/rangtoy/flagging_influence.py:62); the toy uses a JSON subprocess boundary ([`__init__.py`:3-5](../python/rangtoy/__init__.py:3)) | Contiguous float64 buffers, zero copy | no LICENSE file in the repository |
| JAX reference path | 0.11.1 | Automatic-differentiation reference for the smooth pointing solver (not in the flagging chain) | [pointing.py](../python/rangtoy/pointing.py) | NumPy arrays | Apache-2 |
| NumPy orchestration | 2.5.3 | Residuals, polar gauge, MAD features, policy masks, splits, corrected visibilities, image fits | [flagging_workflow.py:434-470](../python/rangtoy/flagging_workflow.py:434), [flagging.py:101-228](../python/rangtoy/flagging.py:101), [flagging_imaging.py:84-139](../python/rangtoy/flagging_imaging.py:84) | `state.npz` (full cube), `diagnostics.npz` per solve | BSD-3 |

Two facts shape everything below. First, the science arithmetic rang
needs is small: the fixture cube is 140 rows × 4096 channels × 4 correlations
(18.4 MB complex64) and the LUNO slice is 192 × 2048 × 4 (12.6 MB). Second,
rang already owns native implementations of the normal equations, TV and
trend kernels; what it does not own is prediction, the iterative solve, the
flaggers and the imager.

## 2. Data-movement audit

### 2.1 LUNO path: fetch → zarr decode → casacore MS → QuartiCal → rank survey

All rows are **measured** on 2026-10-29 unless marked. New rows were taken with
`/usr/bin/time` on the host and `resource.getrusage` inside the container
(scripts in the measurement log). Run directory
`outputs/stack-feasibility-20261029-01`.

| # | Step | Tool | Bytes in → out | Wall | Peak RSS | Exists because of |
| --- | --- | --- | --- | ---: | ---: | --- |
| 1 | Fetch support slice (FLAG, WEIGHT_SPECTRUM, MODEL_DATA, ANTENNA1/2, TIME, FLAG_ROW tiles) | curl, sequential | 122 objects, 3.22 GB | 325.7 s (logged) | – | data layout: whole blosc chunks, 50,000 rows × 128 channels per DATA-shaped object |
| 2 | Fetch subtables and row columns | curl, sequential | 2,608 objects, 2.3 MB | 432.4 s (logged) | – | dask-ms export: FEED split into 56 per-antenna groups of single-row chunks |
| 3 | Fetch DATA tiles 8–23 | curl | 17 objects, 2,717,394,982 B | about 461 s (logged) | – | same as 1 |
| 4 | Decode the 16 DATA tiles | numcodecs Blosc | 2,717,394,612 B compressed → 3,276,800,000 B decoded → 12,582,912 B kept (192 of 50,000 rows) | 2.3 s (2.5 s process; 1.0 s user, 3.5 s sys) | 615 MB | chunk shape; 260× overdecode for a four-station subset |
| 5 | Extract support arrays to `.npy` | numcodecs + NumPy | slice → 20 MB `extract/group1/*.npy` | not re-measured | – | host/container split: survey runs on the host venv |
| 6 | Build the four-station MS | python-casacore `default_ms` | 12.6 MB DATA + 12.6 MB MODEL_DATA + 6.3 MB WEIGHT_SPECTRUM + 6.3 MB SIGMA_SPECTRUM (derived, never read) + flags and subtables → 38,257,794 B on disk | 4.1 s (2.3 s user, 6.1 s sys) | 467 MB | QuartiCal reads MS or zarr through dask-ms only; the row-subset selection needs a new table |
| 7 | Solver column read | python-casacore `getcol` | 33,037,824 B (DATA, MODEL_DATA, FLAG, WEIGHT_SPECTRUM, row columns) | 0.02 s | 86 MB | measured alone to isolate the table cost from the solver |
| 8a | QuartiCal solve, cold Numba cache (`/tmp` tmpfs, as every rang container) | `goquartical` | MS → `gains.qc` (240,220 B zarr) | 28.3 s subprocess; 25.2 s "execute graph" | 633 MB | Numba JIT in every fresh container; dask graph |
| 8b | QuartiCal solve, warm cache (3,876,574 B cache directory, bind-mounted) | `goquartical` | same | 3.56–3.66 s subprocess; 1.02 s "execute graph" | 382 MB | process start, 2.4 s `import quartical.executor`, dask graph |
| 9 | Gains back to NumPy | dask-ms `xds_from_zarr` → `np.save` | 240 KB zarr → 262,272 B `gains.npy` + 4,224 B flags | inside 8 | – | solver output lives only on disk |
| 10 | Rank survey: native normals, eigenvalues, anchored response | rang Rust + NumPy, host venv | 20 MB `.npy` + gains → 1024 H blocks (8.4 MB) → `result.json` | 1.5–1.8 s wall (0.47–0.79 s logged earlier the same day) | 97.5 MB | – |
| C | Container start, `python -c pass` | Docker | – | 0.54 s | 32 MB client | per-campaign container |
| I | `import quartical.executor` inside the container | Python | – | 2.4 s (3.25 s with container) | 322 MB | per solve |

Cold versus warm gains: the two caches produce gain arrays that differ at
rounding level (max absolute 1.1e-16, max relative 2.0e-14, identical gain
flags, identical rank survey: 389 status 0, 43 status 3). The cold gains hash
`57809b86…` equals the archived run; the warm gains hash `769a69b1…`. This is
compiled-code arithmetic order, not a bug, but it means bit-identical receipts
depend on the Numba cache state (see [upstream-notes.md](upstream-notes.md)).

Reading the table: of the roughly 1,250 s LUNO chain, about 1,220 s are
network fetches that happened in three sessions, 4 s is MS construction, 28 s
is a cold QuartiCal (of which about 1 s is the solve), and 1.5 s is the survey.
The arithmetic that matters to the science is under 3 s. A fused in-memory
pass does not remove the fetch; it removes steps 5–9, the `SIGMA_SPECTRUM`
column, the MS, the zarr gain round trip and the cold JIT.

### 2.2 Five-track campaign (`run-next.sh`, fixture scan 9)

Measured from the reproduction `outputs/tv-next-wsl-20261029-01` (2026-10-29,
Stimela log 09:51:01–09:58:16, 435 s) and its `stimela.stats.summary.txt`.

| Quantity | Measured |
| --- | ---: |
| Visibility cube (140 rows × 4096 × 4 complex64) | 18.4 MB |
| `state.npz` (cube + model + weights + splits) per case | 24.0 MB |
| `work.ms` per case | 59.6 MB |
| QuartiCal subprocesses in the campaign (`command.json` count) | 63 |
| Sum of their recorded `seconds` | 337.2 s of 435 s wall |
| Cold-cache first solves (one per track that solves) | 47.9 s, 48.7 s |
| Remaining 61 warm solves | mean 3.9 s, min 3.4 s |
| WSClean inversions | 15, each 1.4–1.6 s ("Inversion" line in the logs) |
| `initialize` step (hashes 8.8 GB of source trees, [flagging_next.py:49-50](../python/rangtoy/flagging_next.py:49)) | 44.2 s |
| Bytes read / written during the campaign (Stimela stats, whole recipe) | 21.72 GB / 55.41 GB |
| On disk afterwards | 3,420,432,387 B: 26 `.ms` directories, 275 `.npz` (1.91 GB), 382 `.json`, 45 FITS, 63 `gains.qc` |
| Upstream stages this campaign reads: concurrent suite / response / CARACAL / injections | 7.43 GB / 0.89 GB / 0.48 GB / 2.17 GB on disk |

Per QuartiCal solve, the flag cube makes the following trips
([flagging_workflow.py:282-311](../python/rangtoy/flagging_workflow.py:282) and
[:370-377](../python/rangtoy/flagging_workflow.py:370)): `getcol` FLAG and
FLAG_ROW for the "before" snapshot, `np.savez_compressed`, `putcol` both,
`flush`, `getcol` both to assert preservation, a second `savez`, QuartiCal's
own read, and after the solve a further `getcol` of both to verify
`output.flags=false` held. That is four full reads, one write and two
compressed snapshots per solve, 63 times, for a decision (`added`) that is a
boolean array already held in memory.

Per campaign stage, the MS is copied for immutability rather than protected by
type: `original.ms` → `work.ms` → `flagged.ms`
([flagging_workflow.py:102-103](../python/rangtoy/flagging_workflow.py:102),
[:684](../python/rangtoy/flagging_workflow.py:684)), `backups/work-before-DATA.ms`
([flagging_response.py:373](../python/rangtoy/flagging_response.py:373)),
`backups/<name>-input.ms` and `<name>-diagnostic.ms`
([flagging_imaging.py:760-761](../python/rangtoy/flagging_imaging.py:760)),
`native/<label>/diagnostic.ms` per Tricolour strategy
([flagging_caracal.py:153](../python/rangtoy/flagging_caracal.py:153)). Every
stage also hashes whole trees before and after
([flagging_workflow.py:38-48](../python/rangtoy/flagging_workflow.py:38),
[flagging_next.py:91, 137](../python/rangtoy/flagging_next.py:91)): the
five-track run hashes its 8.8 GB of sources at initialize, at each of five
track launches and at gather, which is the main source of the 21.7 GB read.

### 2.3 Steps that exist only because tools disagree

Classified by cause. "Measured" rows carry a number from the tables above.

| Step | Cause | Cost (measured where available) |
| --- | --- | --- |
| zarr → casacore MS (`build_luno_ms.py`) | QuartiCal consumes MS or dask-ms zarr; the public store's chunking does not expose a station subset | 4.1 s, 467 MB, 38 MB on disk; 3.28 GB decoded to keep 12.6 MB |
| `SIGMA_SPECTRUM = 1/√w` ([build_luno_ms.py:99-103](../examples/build_luno_ms.py:99)) | MS schema completeness; QuartiCal reads only WEIGHT_SPECTRUM | 6.3 MB written, never read |
| `WEIGHT` broadcast to a WEIGHT_SPECTRUM-shaped array ([flagging_workflow.py:119-123](../python/rangtoy/flagging_workflow.py:119)) | uniform weight representation for the Python side | 9.2 MB in `state.npz` for 140 scalars per correlation |
| MODEL_DATA written to disk and read back (fixture `RANG_MODEL_DATA` [flagging_workflow.py:160-170](../python/rangtoy/flagging_workflow.py:160); Crystalball columns [flagging_sky.py:192-230](../python/rangtoy/flagging_sky.py:192); LUNO MODEL_DATA copied from zarr) | QuartiCal takes a model column or a Tigger LSM; the fixture model is 2048 flux values | 18.4 MB column for a 16 KB spectrum; 12.6 MB on LUNO |
| Flags round-tripped through the MS and `.npz` (above) | process boundary with QuartiCal; immutability enforced by re-reading | 4 reads + 1 write + 2 snapshots per solve, 63 solves |
| Gains round-tripped through `gains.qc` zarr, dask-ms, `diagnostics.npz` | QuartiCal output format | 240 KB per solve; 63 `gains.qc` directories |
| Residual recomputed in NumPy after the solve ([flagging_workflow.py:434-435](../python/rangtoy/flagging_workflow.py:434)) | QuartiCal does not return residuals | one extra $G M G^H$ pass per solve |
| Container start + `import quartical` + dask graph construction | process boundary | 0.54 s + 2.4 s + about 2.5 s per solve (3.6 s warm subprocess vs 1.0 s graph) |
| Numba JIT per fresh container | `NUMBA_CACHE_DIR=/tmp/numba` inside the image ([Dockerfile:14](../tools/flagging/Dockerfile:14)); `run-next.sh` bind-mounts a persistent cache ([run-next.sh:32](../tools/flagging/run-next.sh:32)) with one subdirectory per track ([flagging_next.py:97-99](../python/rangtoy/flagging_next.py:97)), the LUNO solve containers do not | 24–25 s per solve cold vs 1.0 s warm (LUNO); 47.9 s vs 3.9 s (fixture); a campaign pays it once per track on a fresh host |
| Whole-tree hashing and MS copies for immutability | no in-process ownership model across tools | 44 s initialize; 21.7 GB read, 55.4 GB written per campaign |
| Three Python venvs in one image | psutil and Numba version conflicts between Stimela, Crystalball and Tricolour | image sizes 1.14–2.25 GB; separate JIT caches |
| Stimela recipe + `flavour: python` cabs | reproducible orchestration | parameters only; the `for_loop` scatter of 3 is the only parallelism |

## 3. Mathematical consolidation

Conventions follow the code: visibilities are 2×2 Jones matrices per baseline
$pq$, time $t$ and channel $\nu$, stored as four correlations XX, XY, YX, YY;
weights $w$ are per correlation; parameters are antenna-major with adjacent
real and imaginary parts ([response.rs:3-5](../src/response.rs:3)).

### 3.1 Stages in RIME form

**Prediction.** For a component list with positions $(l_s,m_s)$, spectra
$S_s(\nu)$ and $n_s=\sqrt{1-l_s^2-m_s^2}$ (positive phase, the Africanus and MS
convention used in [flagging_sky.py:73-100](../python/rangtoy/flagging_sky.py:73)):

```math
M_{pq}(t,\nu)=\sum_s S_s(\nu)\,E_s\,
\exp\!\left[\frac{2\pi i\,\nu}{c}\left(u_{pq}l_s+v_{pq}m_s+w_{pq}(n_s-1)\right)\right],
```

with $E_s=I$ for the unpolarized point models rang uses. The fixture and the
LUNO 1934−638 model are scalar, $M_{pq}=S(\nu)\,I$, so prediction is a lookup.

**Forward model and residual.**

```math
\hat V_{pq}=G_p\,M_{pq}\,G_q^{H},\qquad r_{pq}=V_{pq}-\hat V_{pq}.
```

**Weighted least squares.** With $W_{pq}=\operatorname{diag}(w_{pq,c})$ over
the four correlations,

```math
\chi^2=\sum_{pq,t,\nu}\operatorname{vec}(r_{pq})^{H}W_{pq}\operatorname{vec}(r_{pq}).
```

**Gauss–Newton normal equations.** Let $J_{pq}$ be the 8×16 real Jacobian of
$\operatorname{vec}(\hat V_{pq})$ with respect to the 16 real parameters of
$(G_p,G_q)$ ([response.rs:62-91](../src/response.rs:62); the $q$ imaginary
column carries a minus sign from conjugation). Per gain bin $b$ (one
2-integration × 32-channel cell), rang's native kernel accumulates

```math
\mathbf H_b=\sum_{(pq,t,\nu)\in b}\operatorname{Re}\!\left(J_{pq}^{T}W_{pq}J_{pq}\right),
\qquad
\mathbf b_b=\sum_{(pq,t,\nu)\in b}\operatorname{Re}\!\left(J_{pq}^{T}W_{pq}\,r_{pq}\right),
```

a 32×32 block and a 32-vector for four stations
([response.rs:94-154](../src/response.rs:94)). QuartiCal's `complex` solver
uses the block-diagonal approximation of the same $\mathbf H$ (one 2×2-complex
block per antenna, `compute_jhj_jhr` then `per_array_jhj_jhr` and
`compute_update` in `quartical/gains/complex/kernel.py:120-150` of the
installed 0.2.7), iterated with its step-finalisation rule and per-interval
convergence test at $10^{-7}$. Holding the other antennas fixed, the exact
per-antenna least-squares update is

```math
G_p\leftarrow\Big(\sum_{q,t,\nu\in b} V_{pq}\,W_{pq}\,Y_{pq}^{H}\Big)
\Big(\sum_{q,t,\nu\in b} Y_{pq}\,W_{pq}\,Y_{pq}^{H}\Big)^{-1},
\qquad Y_{pq}=M_{pq}G_q^{H},
```

with the weights applied per correlation. Matching QuartiCal to the
tolerances in section 5 requires copying its exact damping/averaging of this
step and its gain-flagging rule from the kernel source, not just the equation.

**Gauge.** For a scalar (unpolarized) model, $G_p\to G_pU$ with $U\in U(2)$
leaves $\hat V$ invariant, so each bin has a four-dimensional null space and
$\operatorname{rank}\mathbf H_b=8n_{\text{active}}-4$ when fully identified
([survey_luno_solved.py:75](../examples/survey_luno_solved.py:75); gauge basis
in [response.rs:156-197](../src/response.rs:156)). rang fixes the gauge after
the solve with the reference antenna's polar factor, $G_r=H_rU_r$,
$G_p\leftarrow G_pU_r^{H}$ ([flagging.py:101-120](../python/rangtoy/flagging.py:101)).

**Anchored deletion response.** For a candidate deletion with partial
statistics $(\Delta\mathbf H,\Delta\mathbf b)$, the gauge-projected damped step

```math
\delta g=\left(Q^{T}(\mathbf H_b-\Delta\mathbf H)Q+\lambda I\right)^{-1}Q^{T}(\mathbf b_b-\Delta\mathbf b),
\qquad \lambda=10^{-6}\lambda_{\max},
```

with $Q$ the orthogonal complement of the U(2) tangent basis
([response.rs:252-404](../src/response.rs:252)).

**TV regularisation (guidance, not a solver penalty).** With
$s_0$ the baseline median gain norm and gap-aware axis weights,

```math
T(G)=\operatorname{mean}_{e\in E_t}\frac{\|G_{e^+}-G_{e^-}\|_F}{s_0}\frac{\widetilde{\Delta t}}{\Delta t_e}
+\operatorname{mean}_{e\in E_\nu}\frac{\|G_{e^+}-G_{e^-}\|_F}{s_0}\frac{\widetilde{\Delta\nu}}{\Delta\nu_e}
```

([tv.rs:3-68](../src/tv.rs:3); maps and fixed-support variant in
[flagging.py:123-181](../python/rangtoy/flagging.py:123)). The trend variant
first removes a per-antenna median phase gradient of $\det G$ along each axis
([trend.rs:31-104](../src/trend.rs:31)).

**Flagging statistics.** rang's policy uses whitened residual amplitudes
$a=\|\sqrt{w}\circ r\|_F$ and, per baseline on TRAIN cells only,

```math
z=\max\!\left(0,\frac{\log a-\operatorname{med}(\log a)}{\max(1.4826\,\operatorname{MAD}(\log a),\,0.05)}\right),
```

then proposes $z\,[1+\alpha\min(h/\operatorname{med}(h>0),5)]>\tau$ with $z\ge2$,
capped at 2 % of TRAIN cells by score
([flagging.py:184-228](../python/rangtoy/flagging.py:184)). QuartiCal's MAD
flagger, used only as a comparator, thresholds $|\operatorname{Re} r|$ and
$|\operatorname{Im} r|$ against per-baseline and global medians and MADs per
chunk, channel and correlation (`quartical/flagging/flagging.py:124-248`).
Tricolour's SumThreshold strategies operate on amplitude time–frequency
planes with static masks, polynomial background cycles and dilation; they are
not residual-based and are not reproduced here.

**Objective for policy selection.**

```math
L=\frac{T(G(F))}{\max(T(G(F_0)),10^{-30})}+2f
+0.25\frac{\mathrm{MSE}_{\mathrm{val}}(F)}{\max(\mathrm{MSE}_{\mathrm{val}}(F_0),10^{-30})},
\qquad \mathrm{MSE}_{\mathrm{val}}(F)\le1.01\,\mathrm{MSE}_{\mathrm{val}}(F_0),
```

with $\mathrm{MSE}=\operatorname{mean}_{\text{split}}\sum_c w_c|r_c|^2$
computed once per solve for train, validation and test
([flagging_workflow.py:455-464](../python/rangtoy/flagging_workflow.py:455)).

**Correction and imaging.** On the diagnostic support,
$V'_{pq}=G_p^{-1}V_{pq}G_q^{-H}$ with condition-number guards
([flagging_imaging.py:84-139](../python/rangtoy/flagging_imaging.py:84)), then
WSClean's w-stacked dirty image of Stokes $I=(V'_{XX}+V'_{YY})/2$ with Briggs
0.5 weights $\omega_k$:

```math
I_D(l,m)=\frac{1}{\sum_k\omega_k}\sum_k\omega_k\operatorname{Re}\!\left[V'_k\,
e^{-2\pi i\,(u_kl+v_km+w_k(n-1))}\right],
```

evaluated by FFT on 64 w-layers at 512² pixels of 8″, plus the PSF with
$V'_k=1$. The analysis fits known templates to these images
([flagging_imaging.py:185-237](../python/rangtoy/flagging_imaging.py:185)).

### 3.2 Quantities computed more than once (measured from the code)

- $\hat V=GMG^{H}$ and $r$: inside QuartiCal at every iteration (needed),
  again in NumPy after each solve for TV/MSE
  ([flagging_workflow.py:434-435](../python/rangtoy/flagging_workflow.py:434)),
  again as $J$ in the rank/response survey over all TRAIN cells
  ([training_normals](../python/rangtoy/flagging_influence.py:100)), and again
  as $G^{-1}VG^{-H}$ for imaging.
- The model: predicted or copied once, then written and read as a column by
  every consumer (QuartiCal, the NumPy residual, Crystalball verification,
  injection templates).
- Flags: the same boolean cube is re-derived (`protected_flags`) and
  re-verified (`assert_preserved`) on every write and after every solve.
- Whole-tree digests: at least seven passes over the 8.8 GB of campaign
  sources in one five-track run.

### 3.3 Single-pass fusions

One sweep over the visibility cells in a gain bin can accumulate everything
downstream needs, with no stored MODEL_DATA, no residual column and no flag
round trip:

```math
\text{for each cell }(pq,t,\nu)\in b:\quad
M\;\to\;\hat V=G_pMG_q^{H}\;\to\;r=V-\hat V\;\to\;
\begin{cases}
\mathbf H_b\mathrel{+}=\operatorname{Re}(J^{T}WJ),\ \mathbf b_b\mathrel{+}=\operatorname{Re}(J^{T}Wr)\\
\mathrm{SS}_{\text{split}}\mathrel{+}=\sum_c w_c|r_c|^2\ \text{(train/val/test)}\\
\log a\ \text{appended to the baseline's robust-statistics buffer}\\
\text{policy mask bit if } z,\ h \text{ are available from the previous round}
\end{cases}
```

The solver iteration itself is the same sweep with the per-antenna blocks of
$\mathbf H_b$ and $\mathbf b_b$ as its update. Everything after the sweep
operates on gains ($16\times64\times4$ Jones on LUNO), on per-bin blocks
($1024\times32\times32$ doubles, 8.4 MB) or on per-baseline buffers; TV,
trend, rank, response and policy selection never touch visibilities again.
Only MAD needs a second look at the per-baseline $\log a$ buffers, which at
rang's scale (six baselines × 117,556 cells) stay in memory.

Prediction on the fly costs one complex multiply for the scalar models and
$O(n_{\text{src}})$ complex exponentials per cell for the catalogue model
(5153 components × 12.6 M cells on the LUNO slice is $6.5\times10^{10}$
exponentials, about a minute single-threaded; so for catalogue models the
prediction is computed once per dataset and kept in memory, not per
iteration, exactly as QuartiCal does, but without the column write).

### 3.4 Redundant or no-op under rang's settings

- `solver.robust=false`, `mad_flags.enable=false`, `output.flags=false`: the
  solver's flagging path is configured out, yet rang reads the flag cube
  twice more to prove it. In-process, immutability of `original_flags` is a
  type property and needs no check.
- `SIGMA_SPECTRUM` and the broadcast `WEIGHT_SPECTRUM` exist only to satisfy
  table schemas.
- `dask.scheduler=single-threaded`, `dask.threads=1`, `solver.threads=1`:
  the dask graph is pure overhead (about 2.5 s of the 3.6 s warm subprocess).
- The polar gauge fix is a post-processing rotation; a solver that holds the
  reference antenna's polar factor fixed during iteration produces
  gauge-fixed gains directly. This changes the iterate path, so it is a
  proposal to be validated, not a free no-op.
- For the scalar model, MODEL_DATA stores $S(\nu)$ broadcast over rows and
  correlations; the Jacobian needs only $S(\nu)G_q^{H}$.
- Whole-MS copies and tree digests enforce "never clear an observatory flag";
  a core that holds `original_flags` immutable and exposes
  `effective = original | row | additions` as a view enforces the same
  invariant without copies ([flagging.py:44-60](../python/rangtoy/flagging.py:44)).

### 3.5 Sufficient statistics instead of full passes

The rank survey already does this: 117,556 TRAIN cells reduce to 1024 blocks
$\mathbf H_b$ in 0.47 s and every later question (rank, status, anchored
response, deletion forecasts of $|\mathcal{C}|$ candidates) is answered from
the blocks ([survey_luno_solved.py](../examples/survey_luno_solved.py),
[flagging_influence.py:329-465](../python/rangtoy/flagging_influence.py:329)).
The same blocks are the Gauss–Newton curvature of the solve, so a fused core
gets them for free at the last iteration. Scaling note (estimate): with
$n_a$ stations the dense block is $(8n_a)^2$ doubles, 2 MB per bin at
$n_a=64$; it is sparse in baseline couplings and the solver only needs its
antenna-diagonal blocks, so the full block should be formed on demand for
survey bins, not stored for every bin.

## 4. Architecture sketch (proposal)

A single Rust crate, `rang-core`, with a thin Python layer, consistent with
AGENTS.md (Rust kernels, Python interfaces). The existing `src/` kernels
become modules of it; the ctypes boundary is replaced by PyO3 with zero-copy
NumPy views.

**In-memory data model.**

- `VisBlock`: one gain-bin-aligned chunk (a block of integrations × a block of
  channels, for example 2 × 32 or multiples) holding `data: [row, chan, 4]
  Complex<f32>` as received, `weights: [row, chan, 4] f32`, row metadata
  (`antenna1`, `antenna2`, `time`, `uvw`, `scan`, `field`), channel
  frequencies, and `flags`: an immutable `original: BitCube` plus
  `original_rows`, and a mutable `additions: BitCube`. The effective flag is a
  lazy view `original | rows | additions`; nothing can clear `original`.
- `GainGrid`: `[t_bin, f_bin, ant] Jones<f64>` with validity, reference
  antenna and gauge convention recorded; serialisable to the QuartiCal zarr
  layout for comparison.
- `Model`: an enum `ScalarSpectrum(flux[ν])`, `StoredColumn(view)`,
  `Components{sources, spectra, DFT}`; prediction is a method, cached per
  block only for component models.
- `BinStats`: per gain bin `H: [32×32]` (or antenna-diagonal blocks), `b`,
  counts, split sums of $w|r|^2$, per-baseline robust buffers.
- Splits (`train/validation/test`) are `BitCube`s derived from metadata and a
  seed, as now ([flagging.py:229](../python/rangtoy/flagging.py:229)).

**Streaming and chunking.** A `Source` trait yields `VisBlock`s in gain-bin
order from zarr (blosc/LZ4 decode in Rust; chunks selected by row range and
channel range; `json2` object columns parsed as JSON; pickle refused) or from
an MS (through python-casacore at the edge, handing contiguous arrays across
PyO3). Blocks larger than memory are processed one at a time: the solve,
statistics and policy features are all bin-local, so the only cross-block
state is `GainGrid`, `BinStats` and the per-baseline buffers. Parallelism is
`rayon` over blocks or bins; there is no dask. For the catalogue model the
per-block prediction is cached to disk only if the block set does not fit.

**I/O at the edges only.** Ingest: zarr (Rust) or MS (python-casacore).
Export: gains to zarr in QuartiCal's layout, flags to an MS `FLAG`/`FLAG_ROW`
column via python-casacore for external tools, corrected visibilities to a
column only when an external imager is requested, FITS for images. Receipts
(hashes of inputs, code, settings, seeds) are written once per run from the
in-memory inputs, not by re-hashing trees.

**Interfaces.** Python: `rang.open(path, select=...) -> Dataset`;
`Dataset.solve(G(2, 32), iterations=50, reference=0) -> Solution`;
`Solution.tv()`, `.trend()`, `.stats()`, `.rank_survey()`, `.response(...)`;
`Dataset.policy_search(grid, objective) -> Trials`; `Dataset.dirty_image(...)`.
Rust: the same as traits plus a C ABI for the existing ctypes callers during
the transition. External oracles stay callable from Python: QuartiCal,
Tricolour and WSClean are invoked exactly as today by the validation harness,
never by the core.

**What stays external.** MS writing, Measures, deconvolution, the strategy
flaggers, Stimela recipes (replaced by plain Python entry points with the
same receipts; Stimela can still wrap them if astronomers prefer).

## 5. Validation and risk

**Oracles.** `research/results/*.json` and the reproduced run directories
hold the regression targets, already reproduced on this host to 1e-11 or
better for science floats ([STATE.md](STATE.md) tables). Specific targets:

| Quantity | Oracle | Tolerance to prove equivalence |
| --- | --- | --- |
| $\mathbf H_b$, $\mathbf b_b$, counts | existing `rang_response_normals` | 1e-13 relative (summation order only) |
| TV total, edges, maps; trend slopes | existing kernels | exact or 1e-12 relative given identical gains |
| Rank classification, native status | `meerkat-luno-solved.json`, `gain-tv-next-gain-support.json` | exact integers |
| QuartiCal gains, `G.type=complex` | `gains.npy` `57809b86…` (cold) / `769a69b1…` (warm), `diagnostics.npz` in `tv-response-wsl-20261029-01/clean/trials/clean-t2-f32` | gauge-invariant products $G_pG_q^{H}$ within 1e-6 on intervals QuartiCal marks converged; gain flags exact; post-solve χ² within 1e-3 of 0.27 |
| MAD $z$, policy masks, objective, selected policy | `gain-tv-actions.json`, `gain-tv-balanced.json` | $z$ to 1e-12, masks exact, selections exact |
| Corrected visibilities | `checkpoints/*-written.npz` | 1e-10 Jy wide precision, as `VISIBILITY_CLOSURE_JY` |
| Dirty image, PSF | `images/*.fits` from WSClean 3.6 | a Rust w-stacking gridder will not match WSClean's kernel and layer choices bit-wise; target 1e-6 Jy/beam on the paired *differences* (as `IMAGE_CLOSURE_JY`) and report absolute image differences separately; keep WSClean as the oracle |

**Numerical-equivalence procedure (proposal).** Run the harness in the
existing containers, compare field by field as STATE.md's reproduction tables
do (exact integers/strings; floats with a recorded worst relative error),
archive the comparison as a JSON receipt, and only then retire the external
call for that quantity.

**What is expensive or constrained to port (estimates from the sources).**
Everything below is portable because the source is available; the numbers
are for the subset rang uses, not feature parity.

- CASA MS tables: a read-only Rust reader for the `StandardStMan` and
  `TiledStMan` columns rang's data use is 2–4 weeks from the casacore source;
  writing a valid MS is more and is optional, since the fused path needs an
  MS only to hand data to external tools.
- casacore Measures and frame conversions: rang reads UVW and never converts
  frames; nothing to port now, but a future pointing experiment with real
  parallactic angles would need them.
- Tricolour as CARACAL runs it (SumThreshold, polynomial background cycles,
  static masks, dilation, polarisation mode): 3–6 weeks to translate
  faithfully plus validation against the four archived runs, including the
  dask chunk boundaries that shape its windows
  ([flagging-caracal.md](flagging-caracal.md)). It is a control, run four
  times per campaign, so there is no runtime win to buy; a port is a
  completeness choice.
- WSClean as rang uses it (dirty image and PSF, w-stacking with 64 layers,
  Briggs 0.5, Stokes I, FITS): 3–5 weeks. Multi-scale clean, IDG, beam
  application and mosaicing are person-years and are not called by any rang
  recipe. Porting the gridder moves the imaging oracle inside the thing under
  test, so the first validation still runs the external binary.
- QuartiCal's other terms (delay, bandpass, TEC, parallactic angle, leakage)
  and its direction-dependent machinery: rang uses none, so no port.

**Licence constraints.** QuartiCal (MIT), dask-ms (BSD-3), numcodecs/zarr
(MIT), Numba (BSD-2) and codex-africanus (BSD-3, to confirm) impose nothing
on an algorithmic reimplementation. python-casacore (LGPL-3) and casacore
(LGPL) are fine to link from Python at the edge. Stimela (GPL-2), CARACAL
(GPL-2), Tricolour (GPL-2), Crystalball (GPL-2), WSClean (GPL-3) and AOFlagger
(GPL-3) must not have code copied into a core under a different licence;
calling them as subprocesses is unaffected. The rang repository itself has no
LICENSE file, which should be settled before any public release of a core.

**Effort per component (estimates, person-weeks, ranges).**

| Component | Weeks | Notes |
| --- | ---: | --- |
| zarr ingest in Rust (blosc/LZ4, `json2`, chunk selection, receipts) | 1–2 | crates exist for LZ4 and blosc framing |
| MS ingest/export through python-casacore at the edge | 0.5–1 | mostly moving existing code |
| Native Rust MS reader (not recommended) | 6–12 | only if the Python edge must go |
| Prediction: scalar spectra, point/Gaussian components with polynomial spectra | 1–2 | an independent NumPy DFT already exists for checks |
| Full-Jones `complex` solver matched to QuartiCal to the tolerances above | 3–6 | the step rule, convergence and gain-flag semantics must be copied from the kernel source and validated |
| Fused per-bin statistics (normals, split MSE, MAD buffers, TV, trend) | 1–2 | the kernels exist; fusion and PyO3 wrapping are new |
| Policy loop, splits, objective, trial bookkeeping, receipts | 2–3 | port of `flagging_workflow.train` without MS/npz round trips |
| Dirty gridder (w-stacking, Briggs weights, PSF) + FITS writer | 3–5 | diagnostic use only |
| Validation harness against the archives | 2–4 | field-by-field comparisons, tolerance receipts |
| PyO3/maturin packaging, CI, container update | 1–2 | |
| Documentation and recipe migration | 1 | |
| **Inner-loop core (without gridder and MS reader)** | **12–22** | |
| **With the gridder** | **15–27** | |
| Strategy-flagger equivalence (not recommended) | 6–12 | GPL and semantics risk |

## 6. Prototype proposal (not built)

**Slice.** One fused Rust pass on the LUNO four-station 1934−638 slice,
`outputs/luno-solve-20261029-02` inputs (DATA tiles 8–23 plus the support
slice), selection as in [build_luno_ms.py:20-58](../examples/build_luno_ms.py:20):
scan-2 row chunk 0, stations m000–m003, cross rows with `FLAG_ROW` false
(192 rows), channels 1024–3071. The pass does: zarr decode → scalar
prediction → 50 iterations of the matched full-Jones solve on the 2×32 grid
→ residuals → per-bin $\mathbf H_b,\mathbf b_b$ → split MSE → per-baseline MAD
$z$ → TV → rank survey, with no MS, no MODEL_DATA column and no flag
serialisation.

**Baseline to beat (measured above).** fetch-independent chain: MS build 4.1 s
+ QuartiCal 28.3 s cold / 3.6 s warm + survey 1.5 s = 33.9 s cold, 9.2 s
warm; peak RSS 633 MB (cold) / 467 MB (MS build); 38 MB MS + 240 KB zarr
written.

**Frozen acceptance criteria.** These are frozen with this document; a change
needs a new commit before implementation starts.

1. Gain flags identical to `gain_flags.npy` (59.0088 % flagged, exactly the
   unsupported station-bins).
2. On intervals QuartiCal marks converged (98.3 %), $\max|G_pG_q^{H}|$
   difference against the archived gains ≤ 1e-6 per entry; the remaining
   intervals reported separately with their χ².
3. Post-solve χ² ≤ 0.275 against the archived 0.27, which the QuartiCal log
   prints to two decimals; the receipt records the exact value recomputed
   from the archived gains and the same residual definition.
4. Rank survey: 389 bins status 0 covering 116,805 cells; 43 bins status 3
   covering 751 cells; 592 no-data bins; exact.
5. $\mathbf H_b$ equal to the existing native normals at the same gains to
   1e-13 relative.
6. TV total equal to the NumPy-plus-Rust value at the same gains to 1e-12
   relative; MAD $z$ to 1e-12; the (τ, α) policy masks identical.
7. Same pass on the fixture clean case reproduces
   `tv-response-wsl-20261029-01/clean/trials/clean-t2-f32/diagnostics.npz`
   (gains under criterion 2, TV under criterion 6).
8. Runtime, excluding the blosc decode (2.3 s, bounded by the 260×
   overdecode): ≤ 2.0 s wall single-threaded and ≤ 200 MB peak RSS, that is
   ≥ 4.5× the warm chain and ≥ 15× the cold chain; measured with
   `/usr/bin/time -v` and logged in `tool-timings.md`.
9. No file other than the result JSON, the gain export and the receipt is
   written; no MS is created.
10. The receipt records input object hashes, code hash, settings and the
    Numba-cache-independent gain hash of the oracle it was compared with.

Passing 1–7 proves matched quality; 8–9 are the resource claim. Failing 2
while passing 3 would mean a different fixed point of the same objective and
would be reported as such, not hidden.

## 7. Ranked consolidation wins

Speedups are relative to the measured chain on this host; "available now"
marks wins that need no rewrite.

| Rank | Win | Measured basis | Estimated gain | Effort | Available now? |
| --- | --- | --- | --- | --- | --- |
| 1 | Persist the Numba cache for every container (or run QuartiCal in-process once per campaign) | 28.3 s → 3.6 s per LUNO solve; 47.9 s → 3.9 s per fixture solve; the fresh-host five-track run paid two cold solves (97 s of 435 s) | 2–8× per solve; about 20 % of a first campaign, nothing on a repeat | hours | yes: `run-next.sh` already mounts one; the LUNO solve and the older `run-*.sh` wrappers do not |
| 2 | Fused in-process solve + statistics (section 3.3) | 3.6 s warm subprocess vs about 1 s graph vs ≤ 0.5 s native normals | 61 warm solves × 3.9 s = 238 s → est. ≤ 20 s; campaign 435 s → est. 150–200 s | 12–22 weeks | no |
| 3 | Flags and gains never serialised; immutability by type instead of MS copies and tree digests | 21.7 GB read / 55.4 GB written per campaign; 44 s initialize; 26 MS dirs, 275 npz | est. 60–100 s per campaign and about 3 GB disk | part of 2 | partially: drop repeated `tree_digest` calls now |
| 4 | Predict on the fly / no MODEL_DATA column | 18.4 MB and 12.6 MB columns for scalar spectra; Crystalball column writes | small at this scale; grows linearly with rows × channels | part of 2 | no |
| 5 | Sufficient statistics for rank/response/forecasts | already native: 0.47 s for 117,556 cells | none further at four stations; sparse blocks needed beyond | 1–2 weeks at $n_a=64$ | yes |
| 6 | Direct zarr ingest, no MS build | 4.1 s, 467 MB, 38 MB on disk per slice | 4 s per slice; nothing on the 1,220 s of fetches | 1–2 weeks | no |
| 7 | Rust dirty gridder for diagnostics | 15 inversions × 1.5 s + MS copies | small; removes the imaging MS copies | 3–5 weeks | no, and WSClean stays the oracle |

The honest ceiling: with wins 1–4 the five-track campaign is bounded below by
the 15 WSClean inversions and the four Tricolour runs it reuses from earlier
stages (302 s each in the CARACAL stage), none of which this consolidation
touches.

## 8. Open questions

1. Does QuartiCal's `complex` step rule in 0.2.7 (`finalize_update`,
   `update_gain_flags`) admit an exact Rust replica, or only convergence to
   the same fixed point? This decides whether criterion 2 can be tightened to
   1e-10.
2. Is the 1.0 s "execute graph" on the warm LUNO run the solve, or still
   dominated by dask-ms table reads? A profile of the warm run would split the
   remaining 3.6 s.
3. Can the public zarr stores be re-chunked (or served with a station-subset
   layout) so that a four-station slice does not decode 3.3 GB? This is a
   question for the data publishers, collected in
   [upstream-notes.md](upstream-notes.md), not filed.
4. Licence of the rang repository, needed before a core is published.
5. Whether astronomers want a Stimela front end kept; the proposal keeps
   plain Python entry points and lets Stimela wrap them.
6. Whether the MAD robust statistics should be computed exactly (buffers) or
   streamed (P² quantiles) at 64-station scale; rang's current sizes do not
   force the choice.

## 9. Single-framework port plan: recombining the logic (proposal)

Added 2026-10-29 after the first version, at the user's request: if everything
is ported into one framework, how far does the architecture compress? This
section counts steps before and after. A **step** is one boundary crossing
(a process start, a subprocess, a container, a table or file read, write,
copy or hash) or one full pass over the visibility cube. "Before" counts come
from reading the code and are cross-checked against the artefacts the
reproduced runs left on disk (section 2.2). "After" counts are estimates for
the architecture in section 4. Counting rules are deliberately coarse; the
point is the ratio, not the last digit.

### 9.1 Architecture, before and after

| Unit | Before (checkout `fe9f049`) | After (proposal) |
| --- | --- | --- |
| Languages and runtimes | Python, Rust, Numba-JIT Python (two Numba versions), C++ via python-casacore and WSClean, dask graphs, Stimela recipes, bash wrappers | Rust core; Python API; bash only for fetches |
| Orchestration units | 23 recipes in `recipes/`, 15 `run-*.sh` and `fetch-*.sh` wrappers, 3 Stimela cab flavours | one Python package with about six entry points (`open`, `solve`, `policy_search`, `survey`, `image`, `export`) and one receipt writer; Stimela optional on top |
| Python orchestration | 35 modules, about 14,800 lines in `python/rangtoy/` | about 8 modules: API, splits, policy objective, campaign drivers, receipts, plots, oracles (external-tool adapters), tests |
| Native code | 7 Rust files (TV, trend, normals, projector, toy) behind ctypes | one crate, about 10 modules: `io::zarr`, `io::edge` (MS via Python), `model`, `predict`, `solve`, `stats`, `tv`, `trend`, `rank`, `image`, `receipt`; PyO3 |
| Processes per solve | 3 (Python driver, `goquartical`, dask scheduler threads) plus the container | 1 |
| Container images and venvs | 8 images, 3 venvs (solver, Crystalball, Tricolour), 2 Numba versions | 1 image or a plain wheel; external tools only in a validation image |
| Persistent intermediate formats | CASA MS (copies), zarr gain stores, `.npz` cubes and snapshots, `.json` receipts, FITS | in-memory `VisBlock`/`GainGrid`/`BinStats`; one result JSON and one receipt per run; gains and flags exported on request |
| Immutability mechanism | whole-MS copies, before/after snapshots, tree digests, re-reads | immutable `original` flags and data by type; receipts hash inputs once |

### 9.2 Step counts per pipeline

**LUNO path (section 2.1).** Before: 13 steps (three fetch sessions, blosc
decode, `.npy` extraction, MS build, container start, QuartiCal import and
table read, solve, gain zarr write, zarr read plus `.npy` save, survey
normals, survey classification). After: 7 (three fetches, decode, one fused
pass that predicts, solves and accumulates $\mathbf H_b$, classification
from the blocks, receipt). The fetches and the decode are 5 of the 7 and are
untouched.

**Base recipe `tv-flagging` (prepare, train, report;
[recipes/tv-flagging.yaml](../recipes/tv-flagging.yaml)).** Per trial, the
current code performs about 16 steps: two `getcol` for the before-snapshot,
one `savez`, two `putcol`, `flush`, two `getcol` to assert preservation, a
second `savez`, the `goquartical` process start and import, its table read,
the solve, the gain zarr write, `xds_from_zarr`, the NumPy residual pass, two
TV passes (raw and polar), `diagnostics.npz`, `metrics.json`, and two final
`getcol` to verify `output.flags=false`
([flagging_workflow.py:282-470](../python/rangtoy/flagging_workflow.py:282)).
Prepare is about 20 steps (unpack, two `copytree`, about ten `getcol`, model
`putcol`, snapshot, `state.npz`, manifest, two digests); the final export is
about 6 (`set_flags`, `copytree flagged.ms`, two digests, two JSON files).

| Pipeline | Before | After | Ratio |
| --- | ---: | ---: | ---: |
| LUNO path | 13 | 7 | 1.9× |
| `tv-flagging`, 1 baseline + 9 grid trials | about 186 (20 + 10 × 16 + 6) | about 29 (2 + 10 × 2.5 + 2: open, fused pass with TV, record, export) | 6× |
| Five-track `tv-flagging-next` | about 490 visibility-side steps (below), plus 85 HTTP provenance objects | about 60 with a Rust gridder, about 75 with WSClean kept | 6.5–8× |

**Five-track campaign, per track** (measured artefacts: 63 QuartiCal
processes, 26 MS directories, 275 `.npz`, 382 `.json`, 45 FITS, 21.7 GB read,
55.4 GB written):

| Track | Before (code reading) | After | What merges or disappears |
| --- | ---: | ---: | --- |
| initialize ([flagging_next.py:33-82](../python/rangtoy/flagging_next.py:33)) | about 10: five tree digests over 8.8 GB, source receipts over about 100 files, input copies, two JSON | 1 receipt | digests of inputs replace digests of trees; copies disappear |
| trend ([flagging_trend.py:194](../python/rangtoy/flagging_trend.py:194)) | about 23: 7 × (`diagnostics.npz` + `metrics.json` reads), 7 checkpoints, 2 digests; the 28 replays are already in-memory | about 8: 7 solution objects from the campaign store, 1 result | reads of saved gains become references to in-memory solutions; the trend and TV kernels are unchanged |
| prospective ([flagging_prospective.py:375](../python/rangtoy/flagging_prospective.py:375)) | about 140: 3 cases × (3 clone copies, injection `.npz`/`.json`, `state.npz`, baseline solve at 16, full and per-candidate normals, forecast `.npz`/`.json`, 1–2 confirmation solves at 16 each, checkpoints) | about 12: 3 × (fused baseline, forecasts from the baseline's own $\mathbf H_b$, fused confirmation, record) | the normal equations are a by-product of the last solver iteration; the 51 forecasts need no visibility pass |
| signal guard ([flagging_signal_guard.py:412](../python/rangtoy/flagging_signal_guard.py:412)) | about 160: 9 paired solves at 16 each, normals, guards, `.npz`/`.json` | about 12: 9 fused solves, guards from blocks, record | same as prospective |
| provenance ([flagging_provenance.py](../python/rangtoy/flagging_provenance.py)) | 85 HTTP objects, text decoding, 18 JSON writes | unchanged | metadata inspection, not visibility work |
| imaging ([flagging_imaging.py:609](../python/rangtoy/flagging_imaging.py:609)) | about 154: 4 MS copies, 15 × (NumPy correction pass, three `putcol`, three verifying `getcol`, checkpoint `.npz`, WSClean process, three FITS reads, result `.npz`) | about 30 with a Rust gridder (15 × correct-and-grid in memory, 15 FITS writes); about 45 with WSClean kept (15 column writes, 15 processes, 15 FITS reads) plus 2 MS copies | corrected visibilities never leave memory; FLAG/CORRECTED_DATA round trips disappear |
| gather ([flagging_next.py:127](../python/rangtoy/flagging_next.py:127)) | about 10: five digests, source receipts, five result reads | 1 | |

Where the compression comes from, in order of size: (1) the 16-step solve
wrapper collapses to one fused pass, about 63 × 15 ≈ 945 boundary crossings
in the campaign (the "about 490" above counts a solve as one row, so the
table understates this); (2) whole-tree digests and MS copies for
immutability disappear; (3) the normal equations, residual statistics and
TV come out of the solver's last sweep instead of separate passes; (4) the
imaging track stops writing columns to disk. What does not compress: the
fetches, the provenance inspection, and the external oracles while they are
still being used to validate the port.

### 9.3 Equation-level recombination

The current pipeline computes the following distinct objects from the
visibilities, each in its own tool or pass: $\hat V$ (QuartiCal, NumPy,
survey, imaging), $r$ (QuartiCal, NumPy), per-antenna $\mathbf H$ blocks
(QuartiCal), full $\mathbf H_b$ (survey), $w|r|^2$ split sums (NumPy),
$\log a$ features (NumPy), $G^{-1}VG^{-H}$ (NumPy), and the gridded image
(WSClean). After the port there are two sweeps over a gain bin:

1. the **solver sweep**, repeated to convergence, which forms $\hat V$, $r$
   and the per-antenna blocks, and on its last iteration also the full
   $\mathbf H_b$, $\mathbf b_b$, split sums and the $\log a$ buffers;
2. the **imaging sweep**, run only for diagnostic jobs, which forms
   $G^{-1}VG^{-H}$ and grids it.

Everything else (TV, trend, polar gauge, rank, anchored response, forecasts,
MAD $z$, policy masks, objective, selection) is a function of `GainGrid` and
`BinStats` and never reads the cube. Prediction is a lookup for scalar
models and a cached per-block DFT for component models.

### 9.4 Port order and gates

Each phase ends with a validation receipt against the archives (section 5)
before the next starts; a phase that fails its gate is reported, not skipped.

| Phase | Weeks | Content | Gate |
| --- | ---: | --- | --- |
| 0 | hours | Persistent Numba cache in every wrapper; gain comparisons by tolerance instead of hash | `tool-timings.md` rows; identical rank survey |
| 1 | 3–5 | Crate skeleton: `VisBlock`, `GainGrid`, `BinStats`, zarr ingest, scalar prediction, fused statistics, PyO3 | normals to 1e-13, TV/trend exact, MAD $z$ to 1e-12 against the archives |
| 2 | 3–6 | Full-Jones `complex` solver ported from the QuartiCal kernel (MIT) | section 6 criteria 1–9 on the LUNO slice and the fixture clean case |
| 3 | 2–3 | Policy loop and the trend, prospective and signal tracks on the core; `goquartical` retired from campaigns | `gain-tv-actions`, `gain-tv-next-trend`, `-prospective`, `-signal` reproduced to the STATE.md tolerances |
| 4 | 3–5 | Dirty gridder and FITS; imaging track on the core with WSClean as oracle | paired-difference images within 1e-6 Jy/beam; absolute differences reported |
| 5 | 3–6, optional | Tricolour strategies ported from source (GPL decision first) | the four archived native controls reproduced flag-for-flag |
| 6 | 2–4, optional | Rust MS reader; python-casacore dropped from the hot path | column-exact reads of the fixture and LUNO MSs |
| Total to phase 3 | 8–14 | | |
| Total to phase 4 | 11–19 | | |
| Total, all phases | 16–29 | | |

These ranges replace the per-component table in section 5 where they
overlap; the earlier table remains as the component view.

### 9.5 What the port does not change

The archived scientific results are the gate, not the goal: the port must
reproduce them and may not improve them. Under AGENTS.md's novelty rule the
deliverable is "the same results in one process, with 6–8× fewer steps and
without the MS, snapshot and digest traffic", measured and logged, and
nothing more.

## Measurement log

New measurements for this study are logged in
[tool-timings.md](tool-timings.md) under 2026-10-29 with the prefix
"feasibility". Scripts: `timed.py` (child wall/CPU/RSS via `getrusage`),
`decode_tiles.py` and `read_ms.py` in the session scratchpad; outputs in
`outputs/stack-feasibility-20261029-01` (ignored). The scratch directory
`~/Build/tmp/20261029-rang-feasibility` was removed after the run.
