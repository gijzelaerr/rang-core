# DDFacet and killMS in the core: feasibility and plan

Written 2026-10-30 on branch `ddfacet-feasibility` (from origin/main
`07dfb86`) at the user's request: the user asked for DDFacet, and with it
killMS, to be rewritten into the core as the step after the beam/pointing
question (task B1). This note decides how. It is a study, like
[stack-consolidation-feasibility.md](stack-consolidation-feasibility.md):
nothing in `core/` or `python/` changes. Labels used throughout: **measured**
means run on this host for this study (logs in
`outputs/ddfacet-feasibility-20261030-01`); **read** means read from the
upstream source at the commit given; **estimate** and **proposal** are what
they say.

Measurements were taken on a heavily shared host. The one-minute load was 58
to 66 on 16 hardware threads for most of the session, because sibling tasks
were running. Every wall time below is load-contaminated unless the CPU time
is given.

Upstream code was read at these commits (cloned to
`~/Build/tmp/20261030-ddfacet`, since deleted):

- DDFacet `2fe05ab4` (2026-06-23), tag `v1.0.0.0`;
- killMS `350f22c6` (2026-01-29), tag `v3.3.0`;
- ducc `757145c3` (2026-10-29), `ducc0_0_42_0-27-g757145c3`.

## Verdict (summary)

**Do not port DDFacet faithfully. Build the core imager as an exact
w-gridder (the ducc0 wgridder algorithm), facet-free first, then add facets
as shifted sub-images over that gridder. Add the direction-dependent (DD)
solver and deconvolution only as far as the science needs them. Keep
DDFacet and killMS as pinned external oracles.**

1. **What DDFacet is (read).** About 106 k lines of Python and 8.5 k of
   C/C++. The core of it is small:
   - **Gridder.** W-projection per facet (not w-stacking): 100 w-kernels
     with a prolate-spheroidal taper, support 7 growing per plane, 11×
     oversampling. The facet's n−1 term is fitted by a 5th-order 2-D
     polynomial whose linear part becomes a uv shift (`ModCF.py` 273–306,
     403–560).
   - **Facets.** Voronoi facets around the killMS cluster directions.
   - **Data compression.** Baseline-dependent averaging (BDA) blocks bounded
     by a decorrelation budget of 0.02.
   - **Jones.** One 2×2 matrix per facet per BDA block or visibility
     (`gridder.h` 80–420).
   - **Deconvolution.** Most of the code is here: Hogbom, HMP (hybrid
     matching pursuit, the default), the SSD family with genetic-algorithm
     island fits, WSClean-style multiscale, and MORESANE/Orieux hooks that
     carry vendored third-party code.

   killMS is about 24 k lines of Python and 2.8 k of C. Its CohJones solver
   is Levenberg–Marquardt on a per-antenna Jacobian that couples the
   directions. KAFCA is an extended Kalman filter.
2. **A faithful port is the wrong target (estimate).**
   - It would reproduce kernel approximations that an exact gridder no
     longer needs.
   - About 49 k of the 106 k Python lines (46 %) are deconvolution
     heuristics. That count covers `MultiSliceDeconv`, `SSD`, `SSD2`,
     `SSD3`, `GA`, `HOGBOM`, `MSMF`, `WSCMS`, `WSCMS2` and `SASIR`, and
     includes 13.7 k lines of vendored MORESANE and Orieux code. There is
     no clean oracle for a port, and the original has fast-math
     nondeterminism.
     The C++ is built with `-ffast-math` (`pyproject.toml`,
     `ENABLE_FAST_MATH=ON`).
   - WSClean 3.6 itself defaults to the wgridder (`main/settings.h:49`) and
     no longer to w-stacking.
3. **The exact gridder is cheap, accurate and checkable (measured).** On the
   LUNO four-station slice (7,377 visibilities, every 16th channel), the
   ducc0 0.42.0 wheel agrees with a direct Fourier transform (DFT) to:
   - 6.0e-8 of the peak at epsilon 1e-9 (float64);
   - 8.7e-8 at 1e-7;
   - 1.2e-5 at 1e-4 (float32).

   It takes 0.04–0.27 s per 512² image. The DFT took 243 s. A Rust port of
   the algorithm (exponential-of-semicircle (ES) kernel, w-planes spaced by
   the accuracy target, exact w-correction, n−1 recentering,
   `lshift`/`mshift` sub-images) is therefore a gridder with a tolerance set
   by an epsilon, validated against a pip-installable oracle and a DFT. That
   is the first protocol.
4. **Facets cannot carry the pointing science away from their nodes; the
   DFT predictor can (measured).** A facet-constant Jones is exact at the
   facet node, where killMS and DDFacet put the bright sources. Away from
   the node, holding the beam constant misrepresents the MeerKAT L-band beam
   (katbeam, 1284 MHz, power FWHM 1.087°) by more than a 30″ pointing offset
   changes it. These are worst cases at the facet edge:
   - by up to 47× with 9 facets over a 2×FWHM field;
   - by up to 13× with 100 facets;
   - by up to 1.6× even with 6,400 facets.

   The off-node emission is the faint emission B1 asks about. The
   beam/pointing solver must therefore keep evaluating the beam per
   component and per antenna, which the core's DFT predictor and the JAX
   reference path already do. Facets with per-facet Jones serve DD *gain*
   calibration and wide-field imaging of extended emission, not pointing.
5. **Order (proposal).**
   - DF1: exact gridder and degridder.
   - DF2: the same gridder through the C/I/K imaging chains, beside the
     w-stacking path, which stays as the archive reproducer.
   - DF3: facets as shifted sub-images with per-facet 2×2 Jones, beam
     first.
   - DF4: a scalar CohJones DD solver over facet or DFT predicts.
   - DF5: Hogbom and multiscale CLEAN, with major cycles through the
     degridder.
   - DF6: image-domain gridding (IDG) on `wgpu`, only if B1 needs
     antenna-dependent A-terms on extended emission. WSClean 3.7's
     `facet-idg` is the production precedent and the oracle.
   - DF1b: WSClean 3.7's w-towers variant of DF1, only when full-track
     memory binds.

   B1 needs DF1 and DF2, not DF3–DF6. DF3–DF5 are the rewrite the user
   asked for and are sized below. Under AGENTS.md, none of it is a
   scientific contribution until it buys measured quality or cost.

## 1. What DDFacet and killMS do

### 1.1 Inventory (measured line counts; licence read from the files)

| | DDFacet | killMS | ducc0 (wgridder only) |
| --- | --- | --- | --- |
| Version | 1.0.0.0 (2026-06-23) | 3.3.0 (2026-01-29) | 0.42.0 (+27 commits) |
| Python | 106,197 lines (327 files, incl. `SkyModel/` about 10.9 k) | 23,889 (83 files) | bindings only |
| Native | C 4,375, C++ 1,145, headers 2,975 (pybind11 `_pyGridderSmearPols3x`, `_pyArrays3x`; the classic `old_c_gridder` 6,081 lines still built) | C 2,483, headers 340 (`killMS/Gridder/Gridder.c`, `Array/Dot`) | `wgridder_impl.h` 1,885, `gridding_kernel.{cc,h}` 2,128, FFT 4,101 (C++17 header library) |
| Licence | `LICENSE.md` is the GPL-2 text; about 180 files carry "GPL version 2 … or (at your option) any later version"; none is GPL-2-only; the `pyproject.toml` classifier says "GPLv2"; 173 Python/C files have no header, among them vendored third-party code (`tifffile.py`, `viridis.py`, `Imager/MultiSliceDeconv/Orieux/edwin/`) | same pattern: GPL-2 text, 78 files "or later", 17 without header | GPL-2-or-later (header of every file, classifier "GPLv2+"). **Not GPL-3, contrary to the brief** |
| Build | scikit-build-core + CMake, OpenMP, pybind11, `-ffast-math` | same; fails on GCC 15 (below) | CMake or pip wheel |
| Python range | 3.11–3.12 (`requires-python <3.13`) | 3.8–3.12 | 3.9–3.14 wheels |
| Key dependencies | NumPy ≤ 2.3.2, python-casacore ≤ 3.7.1, pyFFTW, SharedArray, Polygon3, DEAP (genetic algorithms), dask < 2024.11, codex-africanus ≤ 0.4.3, astropy, scipy, numexpr, tables; optional Montblanc (DFT/pointing), meqtrees-cattery (FITS beams), pymoresane, bdsf, dask-ms (katdal/zarr), mpi4py | DDFacet[kms-support] (bdsf), numexpr | none |

Licence consequence (read): every file with a header is GPL-2-or-later and
can be translated into rang (GPL-3.0-or-later). The unheaded files fall
under a GPL-2 `LICENSE.md` with no version statement. The vendored
subtrees are third-party code under their own terms. Both are marked **do
not port** in the plan below; nothing the plan ports lives there. ducc0 is
GPL-2-or-later, so its algorithm and even its kernel parameter table may be
carried into rang under GPL-3. The user has settled the licence question
([big-plan.md](big-plan.md)); this is recorded only so the port touches
nothing whose terms are unclear.

**Installation (measured).** In a uv venv on Python 3.12 from public PyPI:

- **DDFacet** built and installed in 94.5 s (874 MB RSS).
- **killMS 3.3.0** failed to build. GCC 15.2 makes
  `-Wincompatible-pointer-types` an error at `killMS/Gridder/Gridder.c:309`.
  It built in 24.5 s with
  `CFLAGS=-Wno-error=incompatible-pointer-types`.
- **killMS cannot run against DDFacet 1.0.0.0.** `kMS.py` calls
  `DDFacet.Other.AsyncProcessPool._init_default()` (`kMS.py:556`), which
  DDFacet commented out in `51a1d352` (2026-05-29). A killMS oracle
  therefore needs DDFacet pinned to v0.9.1, or to a commit before
  `51a1d352`.
- **meqtrees-cattery** 1.8.0, needed for DDFacet's FITS beams, installed
  in 9.5 s and imports.

The DDFacet acceptance tests read a private `test-data` directory on the
Jenkins host (`Jenkinsfile.sh:8,29`; killMS's LOFAR J1329+4729 test does
the same), so there is no public regression set to borrow.

### 1.2 DDFacet stage by stage (read)

1. **Data handling.**
   - `Data/ClassMS.py` reads through python-casacore, or dask-ms with
     `--Data-Dask`, column `CORRECTED_DATA` by default.
   - The selection defaults to FIELD_ID 0. The LUNO slice is field 1, which
     made the first measured run fail with "no rows".
   - Chunks are set by `--Data-ChunkHours` or `--Data-ChunkRows`.
     `ClassVisServer` loads the next chunk in the background.
   - All workers share arrays through `/dev/shm` (`SharedArray`,
     `shared_dict`). DDFacet warns when `/dev/shm` is under 90 % of RAM;
     here it is 16 GB of 30.
   - Flags are made the same across the four polarisations.
   - Weights come from `ClassWeighting.py` (Natural, Uniform, Briggs).
2. **Facet geometry** (`Imager/ClassFacetMachineTessel.py` 80–480).
   - Facet centres come from `--Facets-CatNodes`, from the `ClusterCat` of a
     killMS solution file, or from a regular `NFacets × NFacets` grid.
   - `scipy.spatial.Voronoi` plus Polygon3 clipping gives the tessels
     (line 428). Tessels larger than `DiamMax` are split; ones smaller than
     `DiamMin` are merged.
   - Each facet is imaged as a square around its centre, padded by
     `--Facets-Padding` 1.7.
   - The main image size is adjusted to fit the facets: 512 became 525 in
     the measured runs.
   - Facets are stitched in `FacetsToIm` (`ClassFacetMachine.py:1214`),
     with Jones normalisation images and a Gaussian mixing width of 10
     pixels at the edges.
3. **W-term and convolution functions** (`Imager/ModCF.py`).
   - The prolate spheroidal comes from `SpheMachine` (line 90).
   - `ClassWTermModified.InitW` (403) does the following:
     - finds the largest support at which the w-kernel for `wmax` drops to
       1e-3 (`SupMax` from a 501-pixel FFT);
     - interpolates the supports linearly from `Support` 7 up to that value
       over `Nw` 100 planes (line 477);
     - computes each plane at oversampling 11 as the FFT of
       `exp(-2πi w (n−1)) × spheroidal`, plus a conjugate set for w < 0.
   - The facet-centred n−1 comes from `Give_dn` (273): a 5th-order
     polynomial fit over the facet, with the linear terms (`Cu`, `Cv`)
     removed and applied as the uv shift `U + W·Cu` in the gridder
     (`gridder.h:303`).
   - Per facet this is w-projection about the facet centre, as in Tasse et
     al. 2018.
4. **Gridding and degridding kernels** (`Gridder/gridder.h`,
   `degridder.h`).
   - For each BDA block (`iBlock` loop, line 197), each row is
     phase-rotated to the facet centre (line 236), Jones is applied, and
     the block's visibilities are summed with a decorrelation factor.
   - The block is gridded once at its mean uvw on its nearest w-plane
     (line 355) with the oversampled CF. Visibilities whose full support
     falls off the grid are skipped (line 373).
   - Jones is applied per visibility (`BDAJones=0`, the default) or once per
     block (`DoApplyJones==2`, line 322). It is `J_p^H V J_q`, with the
     accumulated `∑ w |J|²` used for normalisation (`SumJones`) and an
     optional full Mueller `MTilde` correction (`_applyMTilde`,
     `ClassFacetMachine.py:2160`).
   - Gridding accumulates in double; the CFs are complex64.
5. **BDA and smearing** (`Data/ClassSmearMapping.py`).
   - Per baseline, rows and channels are grouped into blocks so that the
     phase change across the facet radius stays under
     `dPhi = sqrt(6(1−Decorr))`. That is 0.35 rad for the default
     `--Comp-GridDecorr` 0.02 (line 190).
   - `DecorrMode` (T, F, FT) puts time and frequency smearing into the PSF
     through `DecorrelationHelper`.
   - `--Comp-Sparsification` grids random subsets in early major cycles.
6. **Beam and Jones sources** (`Data/ClassJones.py`, `ClassFITSBeam.py`,
   `ClassLOFARBeam.py`, `ClassEveryBeam.py`, …).
   - The beam is evaluated per facet (or per tessel) and re-evaluated every
     `DtBeamMin` 5 min and every 5° of parallactic angle.
   - MeerKAT uses FITS beam cubes (8 files per pattern; the per-station-type
     JSON configuration is in the parset). The FITS beam needs Cattery.
   - DD solutions are read from `killMS.<name>.sols.npz` or from losoto
     h5parm (`ReadH5`, line 649).
   - `[PointingSolutions]` applies pointing offsets only in the Montblanc
     DFT predict mode. Montblanc is the TensorFlow-1 predictor, an optional
     extra.
7. **Deconvolution** (`--Deconv-Mode`, default HMP). Line counts:

   | Module | Lines |
   | --- | ---: |
   | `HOGBOM` | 1,228 |
   | `MSMF` (HMP) | 3,194 |
   | `SSD` | 7,304 |
   | `SSD2` | 8,721 |
   | `SSD3` | 10,217 |
   | `GA` | 925 |
   | `WSCMS` | 1,631 |
   | `WSCMS2` | 2,016 |
   | `MultiSliceDeconv` (MORESANE and Orieux, mostly vendored) | 13,657 |

   - Every model component carries a frequency polynomial (`PolyFitOrder`,
     `ClassFrequencyMachine.py`).
   - SSD fits islands jointly with a DEAP genetic algorithm or MCMC.
   - Major cycles subtract the degridded model per facet, with
     `--Freq-NDegridBand 0` meaning every channel.
8. **Sky model and outputs.**
   - The model is a pickled `DicoModel`: `DicoSMStacked` with `Type`,
     `RefFreq`, `ListScales`, `ModelShape` and per-pixel `Comp` entries with
     spectral coefficients (`HOGBOM/ClassModelMachineHogbom.py` 48–210).
   - Images are FITS through `ClassCasaImage`: dirty, apparent and
     corrected, PSF, model, residual, restored.
   - `SkyModel/` converts BBS catalogues, makes masks and clusters
     catalogues (`ClusterCat.py`) into the `dtypeClusterCat` record
     `(Name, ra, dec, SumI, Cluster, l, m)` (`SkyModel/Sky/ClassSM.py:33-40`).
9. **Interface to killMS.**
   - killMS reads the `DicoModel` (`--DicoModel`) and the cluster nodes
     (`--NodesFile`), and predicts per direction with DDFacet's
     degridder (`ImageSkyModel`).
   - It writes `killMS.<OutSolsName>.sols.npz` (`kMS.py` 866–876). The keys
     are `Sols`, a record array `(t0, t1, G complex64 (nchan, nant, ndir,
     2, 2), Stats)`, plus `StationNames`, `ClusterCat`, `SkyModel`,
     `FreqDomains` and `BeamTimes`.
   - DDFacet reads that file (`--DDESolutions-DDSols`) and tessellates on
     its `ClusterCat`.

### 1.3 killMS (read)

- **Solvers** (`[Solvers]` `SolverType`). CohJones is the default.
  - It solves a 30-minute `dt`, scalar, by default.
  - For each antenna, `ClassJacobianAntenna` builds the Jacobian over all
    directions at once (`CalcJacobianAntenna`, line 483). Its blocks are
    sparse because of the Wirtinger (complex half-Jacobian) formulation of
    Tasse 2014.
  - `doLMStep` (`ClassSolverLM.py:75`) inverts the `ndir × ndir`
    normal matrix by SVD. It applies optional Tikhonov regularisation and
    damps the step by `1/(1+λ)`.
  - Antennas are updated in turn within each of the `NIterLM` 7
    iterations.
- **KAFCA** (`ClassSolverEKF.doEKFStep`, line 242) is the extended Kalman
  filter of Tasse 2014 (non-linear Kalman filters). It evolves the
  covariance (`CovQ`, `evPStep`) across solution intervals.
- **Polarisation modes.** `Scalar`, `IDiag` or `IFull`. `GiveSols`
  expands them into 2×2 matrices (`ClassWirtingerSolver.py:227`).
- **DD sky partitioning.**
  - A catalogue (`--SkyModel` npy) or a DDFacet `DicoModel` is clustered
    into directions by `ClusterCat.py`.
  - The prediction is a numexpr DFT for point and Gaussian catalogues
    (`Predict/PredictGaussPoints_NumExpr5.py`), or DDFacet facet degridding
    for image models (`Predict/ClassImageSM2.py`).
- **Solution format.** The npz above. h5parm comes from external conversion
  (losoto); DDFacet reads both.

## 2. What the core has, what is missing, and the oracle for each

Core capabilities from STATE and the core notes:

- MS reader (task E) and zarr/blosc/HTTP ingest (G);
- WSClean Briggs weights (B);
- WSClean w-stacking dirty image and PSF (C, P2);
- DFT component predictor for points and Gaussians with spectra (3c-a);
- direction-independent 2×2 solver (phase 2, P1);
- Tricolour (D, P3);
- katbeam and JAX pointing reference (Python);
- FITS writing through astropy.

There is no degridder, no deconvolution and no DD anything.

| Stage | Core today | Missing | Oracle (data, cost) |
| --- | --- | --- | --- |
| Visibility I/O and chunking | MS reader, zarr ingest, row blocks (L1's 12.5 GB array driver) | nothing structural; a streaming per-chunk gridding API | python-casacore (existing comparators) |
| Weighting | Briggs/uniform/natural as WSClean (bit-identical, task B) | DDFacet's Briggs differs in grid and units; not needed | task B archive |
| Gridder, image direction | w-stacking, KB 7 px, 1023× oversampling, 64 layers, padding 1.2; matches WSClean to 6.1e-7 of peak | an exact gridder (ES kernel, epsilon control, n−1 recentering, sub-image shift) | **ducc0 wheel** `vis2dirty` (pip, seconds), direct DFT on small cases, task C/I/K archives reported; WSClean 3.6 `-gridder wgridder` after the container is rebuilt (the pinned `rang-flagging*:local` images are no longer on this host) |
| Degridder (image → visibilities) | none (the predictor is a DFT) | `dirty2vis`, the adjoint of the above | ducc0 `dirty2vis`; core DFT predictor on component skies (3c-a archive, 5,153-component catalogue) |
| Facets and tessellation | none | Voronoi tessels around nodes, padded sub-images, stitching and normalisation | DDFacet `--Output-Mode Dirty` with given `CatNodes` on the same MS (measured feasible: 16.6–32.4 s on the slice) |
| Per-facet Jones (beam first) | katbeam (Python/JAX), per-component beam in the pointing solver | beam per facet and time block on the grid side; `J_p^H V J_q` per visibility or block; `SumJones` normalisation | DDFacet with the FITS beam (Cattery installs; a MeerKAT FITS beam cube from katbeam/eidos must be made first) |
| BDA and smearing | none | optional; the core grids every sample | DDFacet with `--Comp-GridDecorr 0` versus default, to bound its effect |
| DD solver | DI 2×2 solver only | CohJones (scalar, then diagonal), multi-direction predicts | killMS 3.3.0 with DDFacet pinned to v0.9.1 (the current pair is incompatible, measured); a simulated MeerKAT field with known DD gains as ground truth |
| Deconvolution | none | Hogbom; multiscale (WSClean-style; DDFacet's `WSCMS` follows it); restoring beam fit; masks; major cycles | DDFacet Hogbom/HMP `DicoModel` and residual FITS, WSClean on the same data; ground truth from simulated skies. Not the four-station slice (below) |
| Sky model formats | component lists for the predictor | reading `DicoModel` (pickle) and `ClusterCat`; writing a component list | DDFacet's own files |
| Solution formats | core gain arrays, QuartiCal zarr | killMS npz writer and reader; h5parm optional | killMS/DDFacet reading the core's files |

**Data for the oracles (measured or read).**

- **LUNO four-station slice** (`outputs/luno-solve-20261029-02/work.ms`,
  37 MB, 192 rows × 2,048 channels, field 1).
  - It is good for gridder and dirty-image checks.
  - It cannot serve deconvolution or DD calibration. The 74 m maximum
    baseline gives a PSF of about 9′ (about 70 pixels at 8″), whose
    sidelobes reach 0.80 at the edge of a 68′ field (measured, exact DFT
    PSF).
  - In DDFacet on this slice:
    - Hogbom stalled in its first minor cycle with an overflow warning
      (`ClassModelMachineHogbom.py:184`) and was stopped after about
      10 min.
    - HMP stopped after 161 minor iterations ("diverging w.r.t. floor")
      and finished in 234 s with an **8.9 GB** peak (measured).
    - The degrid jobs averaged 61 s of single-core time per facet. With
      `NDegridBand 0` the model is a cube over all 2,048 channels; the log
      prints the model image at every channel frequency. That this cube
      causes the 8.9 GB peak and the degrid time is inferred from the log,
      not measured.
- **Fixture scan 9** (58 MB). Same four stations, same limits.
- **Whole-array LUNO chunk 0** (L1: 53 stations, 1,378 baselines, 41,786
  rows, 342 M cells).
  - It is local as zarr tiles. It would need an MS export (about 11 GB of
    complex64 DATA, an estimate) for DDFacet.
  - It is a calibrator field (`LBAND_LUNO_CALIBRATORS.zarr`), so it has no
    off-axis sky for DD work.
  - DDFacet holds its data in `/dev/shm`, 16 GB here. An array-scale
    oracle run therefore needs a channel subset (for example 256 of 2,048
    channels, about 1.4 GB) and `--Freq-NDegridBand` of a few bands
    (estimate).
- **A target field with off-axis sources** is needed for DF3–DF5. None is
  on this host:
  - the observer's full-resolution set (L3) is pending;
  - public MeerKAT and LOFAR archives need accounts;
  - the killMS/DDFacet test data are private.

  The concrete plan is therefore a **simulated MeerKAT L-band target
  field**:
  - the core DFT predictor on L1's whole-array uvw, about 50 channels;
  - katbeam per antenna with known pointing offsets, known DD gains and
    thermal noise;
  - written to an MS with python-casacore.

  DDFacet and killMS run on it in a pinned container. Truth is known, so
  each tool is judged against the truth and not only against the other.
  Cost (estimate):
  - about 0.5 GB of MS;
  - minutes to predict;
  - DDFacet dirty and clean runs of a few minutes to tens of minutes;
  - killMS of the same order.

## 3. Architecture options

### 3.1 Evidence measured for this study

**ducc0 against a direct DFT.** LUNO slice, every 16th channel (128
channels, 7,377 unflagged Stokes I visibilities, natural weights), 512² at
8″, w up to 160 λ.

ducc0's `vis2dirty` divides by n by default and uses the opposite w sign to
the DFT here. With `divide_by_n=False` and w negated, it matches. A
synthetic 64² case at 0.25 rad field, 200 rows, matched to 4e-12 at
epsilon 1e-10 with the same convention, which pins it.

| epsilon (precision) | L∞ / peak, 1 thread | L∞ / peak, 4 threads | RMS / peak | wall per image (1–16 threads) |
| --- | ---: | ---: | ---: | ---: |
| 1e-3 (f32) | 1.8e-4 | 1.8e-4 | 3.7e-5 | 0.04–0.11 s |
| 1e-4 (f32) | 1.2e-5 | 8.4e-6 | 1.5e-6 | 0.05–0.09 s |
| 1e-5 (f32) | 2.8e-6 | 2.2e-6 | 3.5e-7 | 0.06–0.13 s |
| 1e-6 (f64) | 1.9e-7 | 1.9e-7 | 2.9e-8 | 0.12–0.18 s |
| 1e-7 (f64) | 8.7e-8 | 8.7e-8 | 1.9e-8 | 0.09–0.21 s |
| 1e-9 (f64) | 6.0e-8 | 6.0e-8 | 1.7e-8 | 0.09–0.27 s |

The floor near 6e-8 is the reference: the visibilities are complex64 and
the DFT sums 7,377 terms in float64. The DFT itself took 243 s (3.2 GB).

At epsilon 1e-4 the result depends on the thread count (1.2e-5 against
8.4e-6). `getNuNv` (`wgridder_impl.h` 1555–1640) divides the gridding cost
by `nthreads` when it picks the kernel and grid size. A protocol must
therefore fix `nthreads`, or the kernel, for the oracle.

**The core w-stacking gridder against the same DFT (measured, unresolved).**
The best of every combination of transpose, flips and ±1-pixel rolls, with
both w signs, gives:

- 19 % of the peak (L∞) at the default padding 1.2;
- 12 % with padding 2, a 15-pixel kernel and 512 layers;
- 1.6 % of the PSF peak on the PSF.

The core already matches WSClean's w-stacking images to 6.1e-7 (task C), so
this is not an accuracy statement about the core. Position and flux of a
single point are right: a synthetic point source at (+20, +5) pixels lands
at (col 276, row 251) with peak 0.99999.

The full-image residual (19 %, 12 % and 1.6 % above) is unexplained, and
this study does not attribute it. Candidates are:

- a convention difference that the brute-force search did not cover;
- aliasing of the padded w-stacking grid, on a PSF whose sidelobes reach
  0.80 at the field edge.

Pinning it against the DFT is item 0 of the first protocol.

**DDFacet faceting on the slice (measured).** Dirty images, Briggs 0.5, 525²
at 8″:

- 1 facet against 9 facets differ by 2.5 % of the peak (L∞) and 0.49 %
  (RMS);
- the dirty image of the 9-facet dirty run and of the clean run agree to
  2.6e-7.

That is the size of DDFacet's facet approximation on a sidelobe-dominated
four-station PSF: kernel truncation, per-facet polynomial n−1 and
stitching. A faceted core must agree with DDFacet to about this level,
not to rounding.

**Facet-constant beam against the pointing signal (measured).** katbeam 0.1
`MKAT-AA-L-JIM-2020`, HH, 1284 MHz, power FWHM 1.087°. Field 2 × FWHM
square. Facets are centred at 0.25, 0.5 and 1 FWHM from the pointing centre.

- **Error.** Largest |E(x) − E(facet centre)| over the facet, in units of
  the on-axis voltage beam.
- **Signal.** Largest |E(x − δ) − E(x)| over the same facet, for a pointing
  offset δ.

| Facets in field | Facet half-width | Facet-constant error | Signal, δ = 30″ | Error / signal |
| ---: | ---: | ---: | ---: | ---: |
| 9 | 21.8′ | 0.35–0.43 | 0.0084–0.0086 | 40–50 |
| 25 | 13.1′ | 0.20–0.25 | 0.0074–0.0086 | 24–29 |
| 100 | 6.5′ | 0.08–0.12 | 0.0062–0.0085 | 12–14 |
| 400 | 3.3′ | 0.04–0.06 | 0.0055–0.0082 | 6.3–6.7 |
| 1,600 | 1.6′ | 0.017–0.027 | 0.0051–0.0081 | 3.2–3.3 |
| 6,400 | 0.8′ | 0.008–0.013 | 0.0049–0.0080 | 1.6–1.7 |

To first order both are a beam gradient times a distance (half-width
against δ). The table is the worst case at the facet edge; at the node
itself a facet-constant Jones is exact. For emission away from the nodes,
a facet-constant Jones model is therefore blind to pointing offsets
smaller than the facet half-width. That off-node emission is what B1's
faint-emission question is about.

DDFacet partly compensates in the image plane: per-pixel average-beam
correction and `SumJones` normalisation. That corrects the image's
amplitude scale but not the visibility model a solver fits. **For B1 the
forward model must keep per-component, per-antenna beams.** That means the
core DFT predictor plus katbeam, as the JAX reference already does, or
A-terms per antenna inside the gridder (IDG, option c).

### 3.2 The options

| | (a) Faithful DDFacet port | (b) Facets over an exact wgridder port | (c) IDG on the GPU via `wgpu` |
| --- | --- | --- | --- |
| Kernel | prolate spheroidal × w-kernel, support 7 → about 50 over 100 w-planes, oversampling 11, CF tables per facet | ES kernel `exp(β(√(1−x²)−1))^e0`, support 4–16 chosen per epsilon, oversampling σ 1.2–2.5, piecewise-polynomial evaluation (no tables) | subgrids of 24–32 pixels; per-visibility DFT onto each subgrid; A-terms and w applied in the subgrid's image domain; taper of van der Tol et al. |
| w-term | w-projection with per-facet polynomial n−1, nearest plane, 100 planes | w-stacking with `dw = 1/(2σ max|n−1+nshift|)`, planes combined with the kernel's exact w-correction; `nshift` and Wortmann recentering (ducc0 0.42) cut the planes for off-centre facets | exact per subgrid (w in the subgrid DFT, w-stacking of subgrids for large w) |
| Accuracy | fixed by support and plane count; no epsilon; 2.5 % facet differences on the slice (measured); fast-math | set by epsilon; measured 1e-4 → 1.2e-5, 1e-7 → 8.7e-8 against the DFT | about 1e-3 to 1e-4 with the optimal taper (van der Tol et al. 2018, read; not measured here) |
| Cost (relative) | CF build per facet per w-plane (FFT 501²), Python orchestration; HMP clean on 37 MB took 234 s and 8.9 GB (measured) | 0.04–0.27 s per 512² image at 7 k visibilities (ducc0, measured); P2's w-stacking is 0.5–0.8 s on the same scale | GPU-bound; per-visibility work about subgrid² and independent of w; good when A-terms vary per antenna and time |
| DD effects | per-facet 2×2 Jones (constant over a facet) | same, through `lshift/mshift` sub-images; or Jones per visibility block | **per-antenna A-terms varying across the field and in time**, which the pointing science needs for extended emission |
| Code to write | gridder about 1.5 k C++ equivalent, CF/facet machinery about 5 k Python equivalent, deconvolution 10–40 k | gridder and degridder about 2–3 k Rust (estimate from `wgridder_impl.h` 1,885 + kernel 2,128 lines of C++), facets about 1 k | about 3–5 k Rust plus WGSL shaders; FFT on the GPU (no `rustfft` there) |
| Oracle | DDFacet itself (fast-math, nondeterministic sums) | ducc0 wheel (pip, deterministic at fixed threads), DFT, WSClean `-gridder wgridder` | DFT (exact), ducc0 on the A-term-free case, IDG (`idg` library, GPL-3) |
| Measurable now | yes (DDFacet installs) | yes (measured above) | **no**: the GPU had 11.3 of 12.3 GiB in use by another process during this study, and S1 found no Vulkan loader in WSL; X2 (wgpu behind a feature, native Windows) is not merged |
| Licence | GPL-2-or-later (fine) | GPL-2-or-later (fine) | algorithm published; IDG code GPL-3 (fine) |

**WSClean's own switch (read).** WSClean 3.6 defaults to `-gridder
wgridder` (`main/settings.h:49`) with `wgridderAccuracy` 1e-4 (`:132`),
gridding in float above 1.01e-5 and double below
(`wgridder/wgriddingmsgridder.cpp:43-52`). The vendored ducc0 lives in
`external/schaapcommon/external/ducc0`. rang's imaging chain chose
`-gridder wstacking` explicitly, and task C ported that.

ducc0 0.42 removed the experimental "tuning" methods. WSClean 3.6 still
offers `tuned-wgridder` (`main/commandline.cpp:1348`). Whether that option
survives a WSClean built against ducc0 0.42 is not checked.

### 3.3 Later inputs: WSClean 3.7 and an active DDFacet

Added after the coordinator's literature scan; read from the changelog, not
run.

WSClean 3.7 was released on 2026-02-16 ([changelog](https://wsclean.readthedocs.io/en/latest/changelogs/v3.7.html)).
It adds three things relevant here:

- **A w-towers gridder** (`-gridder wtowers`). W-towers comes from the
  SKA streaming-imaging work of Wortmann, Kent and Nikolic
  ("Imaging swiFTly", [arXiv:2108.10720](https://arxiv.org/abs/2108.10720);
  SKAO `ska-sdp-func` `gridder_wstack_wtower`).
  - The uv plane is split into subgrids, and each subgrid stacks its own
    small set of w-planes (a "tower").
  - Image facets and subgrids are processed in a streaming,
    distributable way, without assembling the full uvw grid.
- **Facet-IDG** (`-gridder facet-idg`): faceted IDG runs with facet
  corrections.
- **Frequency-direction BDA**, which the changelog calls its largest
  feature.

**Weighed against the recommendation:**

- **W-towers is a memory and distribution strategy over the same
  exact-gridding mathematics, not a different accuracy class.** It still
  uses a separable kernel with w-stacking and a w-correction. DF1's kernel,
  w-correction and degridder carry over to it.
  - It matters when the full grid and image stack do not fit. That is the
    full-track MeerKAT case on a 30 GiB host (section 5), not the
    one-chunk images rang makes now.
  - It therefore becomes a **DF1b** follow-on (subgrid towers over DF1's
    kernel), measured against DF1 at L1 scale and beyond. It does not
    replace DF1 as the first step.
  - Its oracle is WSClean 3.7 `-gridder wtowers`; `ska-sdp-func` is a
    second implementation. Its licence was not checked here.
- **Facet-IDG is the precedent for combining (b) and (c).** WSClean now
  applies per-antenna A-terms through IDG inside facets, with facet
  corrections on top.
  - This supports keeping per-antenna, direction-varying beams in IDG
    (DF6) rather than in facet-constant Jones (DF3).
  - It makes WSClean 3.7 the oracle for DF3 and DF6 beside DDFacet.
  - DF0 should therefore build WSClean **3.7** (Ubuntu resolute carries
    `3.7-1`) rather than rebuilding the 3.6-1 container. 3.6-1 is kept
    only to reproduce the task C archive.
- **DDFacet is actively maintained** (v1.0.0.0, 2026-06-23, with
  dependency pins updated for NumPy 2.3 and Python 3.12). That strengthens
  "oracle, not fork".
  - A faithful port would diverge from a moving upstream.
  - Pinning DDFacet as an oracle keeps the reference current at the cost
    of one container per version.
  - The killMS/DDFacet break measured above shows the cost of that motion.

The recommendation below is unchanged in order (exact gridder first). Two
things change: DF6 is now backed by a production precedent (facet-IDG),
and a w-towers variant is added as DF1b.

### 3.4 Recommendation

**(b), with the beam/pointing path outside the facets, and (c) deferred.**

- **Exact gridder first, and for itself.** The core needs a degridder
  anyway for major cycles and for model prediction from images. The
  wgridder algorithm gives both directions, with a dial (epsilon) and an
  oracle anyone can `pip install`. At MeerKAT L-band, 1° FWHM and 8 km
  baselines, w spans thousands of wavelengths across a 2° field, where
  100 fixed w-planes are an approximation and an epsilon-controlled
  scheme is not. WSClean, the community reference, has moved to the same
  algorithm.
- **Facets as sub-images of that gridder.** A facet is a dirty sub-image
  with `lshift/mshift`, its own Jones and, from ducc0 0.42, recentering
  that keeps its w-plane count small. Tessellation and stitching are a few
  hundred lines over that, with no CF tables. DDFacet stays the oracle for
  what a faceted image looks like at a stated tolerance (2.5 % on the
  slice), not for bit-identity.
- **Not facets for pointing.** The measured beam table shows a
  facet-constant beam is blind to 30″ offsets away from the facet nodes
  unless facets are under about 1′. B1's forward model stays the DFT predictor with per-component,
  per-antenna beams. That already exists in the core (predictor) and in
  JAX (beam, pointing). The exact gridder makes the residual and
  injection images of meerkat-scope step 4 fast and accurate.
- **IDG when an extended-emission A-term is needed.** If B1's
  faint-emission test needs extended emission imaged with per-antenna
  pointing-perturbed beams (images, not just visibilities), IDG is the
  method that applies those A-terms exactly. It is the GPU task, after X2
  makes `wgpu` measurable on native Windows. Until then a CPU IDG
  prototype is possible but has no cost advantage.

## 4. Phased plan (proposal)

Same rules as [core-parallel-plan.md](core-parallel-plan.md) and
[big-plan.md](big-plan.md):

- own worktree and branch;
- frozen protocol before code;
- the comparator precondition, measured on oracle against oracle, before
  freezing;
- failures recorded as frozen;
- every tool run timed;
- coordinator-only shared files.

Owner files are new modules. `pub mod` lines and bindings go through "For
the coordinator".

Sizes are estimates in working sessions. Past ports took about one session
where weeks were estimated, but they were narrow ports with clean oracles,
and DF4–DF5 are not.

| | Task | Inputs and oracle | Done when | Owner files | Size | Parallel with |
| --- | --- | --- | --- | --- | --- | --- |
| DF0 | **Oracle container and simulated target field.** Pinned image with DDFacet v1.0.0.0, Cattery, ducc0 0.42.0, and killMS 3.3.0 on DDFacet v0.9.1 (second venv), built with `-Wno-error=incompatible-pointer-types`; a WSClean 3.7 build (Ubuntu resolute `3.7-1` source, verified like task C's 3.6-1) for `wgridder`, `wtowers` and `facet-idg`, and the 3.6-1 build from `outputs/wsclean-3.6-1-source-20261029/` only to reproduce task C; the simulated MeerKAT L-band target-field MS (core predictor, katbeam, known DD gains and pointing offsets, seeds recorded); a MeerKAT FITS beam cube from katbeam for DDFacet | the tools reproduce themselves (two runs equal, or a recorded nondeterminism bound under fast-math); DDFacet dirty on the slice equals this study's FITS | image digests and SHA256SUMS recorded; nondeterminism bound measured; simulated MS hashed | `tools/oracles/ddfacet/`, `examples/simulate_target_field.py`, `research/df0-oracles.md` | 1–2 | DF1 |
| DF1 | **Exact gridder and degridder (wgridder algorithm), facet-free.** First protocol, below | ducc0 0.42.0 wheel at fixed threads; DFT on small and wide-field synthetic cases; this study's slice export; C/I/K archives reported | gated criteria below pass; speed and memory reported against P2's w-stacking and ducc0 | `core/src/wgrid.rs`, `core/src/es_kernel.rs`, `core/src/ffi_wgrid.rs`, `python/rangtoy/core_wgrid.py`, `examples/{oracle,compare}_wgrid*.py`, `tests/test_core_wgrid.py`, `research/df1-wgridder.md` | 1–3 | DF0, science tasks |
| DF1b | **W-towers over DF1's kernel (only when memory binds).** Subgrids with local w-stacks, streaming visibility chunks, image facets never assembled on the uv side | WSClean 3.7 `-gridder wtowers`; DF1 on the same inputs (exact to DF1's epsilon) | same images as DF1 within epsilon; peak memory and wall at L1 scale and on a multi-chunk track against DF1 | `core/src/wtowers.rs`, `research/df1b-wtowers.md` | 2–3 | DF3 |
| DF2 | **Exact gridder in the imaging chains**, beside w-stacking: `core_imaging`/`core_campaign` take `gridder="wgrid"`; w-stacking stays the default and the archive reproducer | task I/K replays with `wgrid`; WSClean `-gridder wgridder` FITS from DF0 on the fifteen C jobs | every K/I science call unchanged, or the changes listed with their size; WSClean wgridder pixels within the DF1 epsilon plus WSClean's float tolerance | `python/rangtoy/core_imaging.py` option (coordinator edit), `research/df2-imaging.md` | 1 | B1 |
| DF3 | **Facets with per-facet Jones, beam first.** Tessellation (Voronoi, clipping, `DiamMax`), padded sub-images through DF1's shift, stitching and normalisation (`SumJones`, a smooth-beam image); Jones per facet and time block from katbeam; then from killMS-format solutions | DDFacet `Dirty` on the slice and the simulated field with the same `CatNodes`, `NFacets`, padding and FITS beam; tolerance from the DDFacet-to-DDFacet facet spread (2.5 % on the slice, to be measured on the simulated field) | facet geometry identical to DDFacet's `facetCoord.txt`/`NodesCatImaged.npy`; images within the frozen spread; beam-corrected flux of the injected sources against truth | `core/src/facets.rs`, `python/rangtoy/core_facets.py`, `research/df3-facets.md` | 2–4 | DF4 design |
| DF4 | **DD solver (CohJones, scalar then diagonal).** Per-antenna Jacobian over directions, LM with `1/(1+λ)` damping and SVD inverse as killMS; directions from a `ClusterCat`; predicts per direction from the DFT predictor (components) or DF3's degridded facets (images) | killMS on the simulated field (pinned pair); truth gains | gains within a frozen tolerance of killMS on intervals both converge; truth recovery no worse than killMS; npz readable by DDFacet | `core/src/dd_solve.rs`, `python/rangtoy/core_dd.py`, `research/df4-dd-solver.md` | 3–5 | DF5 |
| DF5 | **Deconvolution.** Hogbom then WSClean-style multiscale with major cycles through DF1's degridder; frequency polynomial per component; restoring beam fit; component-list model and a `DicoModel` reader | DDFacet Hogbom and WSCMS, WSClean `-multiscale` on the simulated field; truth sky | model flux and positions against truth within frozen tolerances; residual RMS no worse than both tools at matched iterations; the ported loop's per-iteration peaks equal a NumPy transcription | `core/src/deconv.rs`, `python/rangtoy/core_deconv.py`, `research/df5-deconvolution.md` | 3–6 | – |
| DF6 | **IDG on the GPU (only if B1 asks).** Subgrid gridder with A-terms per antenna and time on `wgpu` | DFT with per-antenna beams (exact); DF1 on the A-term-free case; WSClean 3.7 `-gridder facet-idg` with the same beams | A-term images within a frozen tolerance of the DFT; measured cost against DF1 plus DFT predict | `core/src/idg/`, `research/df6-idg.md` | 4–8 | after X2 |

**Anderson acceleration** (a user interest) applies to the CohJones and
StefCal fixed-point iterations. In DF4 it is an option, measured against
plain LM on the same intervals. For the direction-independent solver it
belongs with L5's convergence study, which already questions the
50-iteration cap.

**Deviations from the brief.**

- **WSClean wgridder output moves out of the first phase.** The brief put
  it in DF1. It is now in DF0, which rebuilds the container, and DF2,
  which uses it. The pinned WSClean container is gone from this host. The
  ducc0 wheel is the same algorithm that WSClean vendors
  (`external/schaapcommon/external/ducc0`). WSClean adds only its reader,
  weighting and normalisation chain, which DF2 covers.
- **The C/I/K archives are reported in DF1, not gated.** Task A's
  tolerances compare w-stacking with w-stacking (see 4.1).

Not proposed:

- SSD, SSD2, SSD3, the genetic-algorithm and MCMC island fitters,
  MORESANE and Orieux. Heuristics without an oracle that would separate
  a port's error from the method's.
- KAFCA.
- BDA. The core grids every sample; BDA is an optimisation to measure
  against DF1's cost only if needed.
- Sparsification.
- Montblanc.
- MPI.

Each can be revisited with a measured need.

### 4.1 First protocol to freeze: DF1, exact gridder

**Scope.** A Rust port of the wgridder algorithm (Arras et al. 2021; ducc0
0.42 `wgridder_impl.h`, `gridding_kernel.{h,cc}`), facet-free:

- the ES kernel with ducc0's `(W, σ, β, e0)` parameter sets for the chosen
  epsilon;
- grid sizes `nu, nv` from σ;
- w-planes as in `countRanges` (`wgridder_impl.h` 708–725), with `nshift`
  and the global correction `apply_global_corrections` (1397–1430);
- `vis2dirty` and `dirty2vis`;
- `lshift/mshift` and `divide_by_n` as options;
- f32 and f64 paths;
- rayon over w-planes with an ordered sum, as P2 did.

The kernel choice is made by an explicit rule, independent of the thread
count. Out of scope: facets, BDA input, the tuned variants.

**Inputs.**

1. Synthetic: random uvw and visibilities, seeds recorded, fields from
   8′ to 0.3 rad, w up to 10⁴ λ, with N up to 128² so the DFT is cheap.
2. This study's LUNO slice export (`inputs.npz`, 7,377 visibilities), with
   its DFT image.
3. The task C fifteen-job inputs and the K six-arm inputs. `inputs-c` and
   `inputs-k` are still in `outputs/p2-gridder-20261030-01` and can be
   regenerated with `bench_p2_gridder.py c-inputs` and `k-replay
   --dump-inputs`.

**Oracle step.** ducc0 0.42.0 from PyPI, `nthreads=1`, the same epsilon,
`divide_by_n` as the core, outputs hashed. The DFT is computed in float64.

**Precondition, measured before freezing.**

- ducc0 against the DFT on (1) and (2) at each epsilon. This study's table
  is the template.
- The core w-stacking image's convention pinned against the DFT on (2):
  item 0, unresolved here.

**Gated criteria (proposed).**

1. Core `vis2dirty` against the DFT: L∞/peak ≤ 10 × epsilon in f64, for
   epsilon in {1e-5, 1e-7, 1e-9} and every synthetic case. In f32, ≤ 10 ×
   epsilon with epsilon ≥ 1e-5.
2. Core against ducc0 at the same epsilon and kernel: L∞/peak ≤ epsilon,
   in both directions.
3. Adjointness: `⟨dirty2vis(x), y⟩ = ⟨x, vis2dirty(y)⟩` to 1e-12 relative
   in f64.
4. The same SHA256 at 1, 2, 4, 8 and 16 threads.
5. The kernel table equals ducc0's parameters for the epsilons used.

**Reported, not gated.**

- C/I/K science metrics with `wgrid` at epsilon 1e-6, against the archived
  w-stacking FITS and against core w-stacking. Task A's tolerances measure
  w-stacking against w-stacking, and an exact gridder may move the
  response fraction (today 1.31e-7 of 1.6e-7) by more. A move is
  information, not a failure.
- Wall, CPU and RSS against ducc0 and P2's w-stacking on the K inputs and
  on 4×, 16× and 41× tiles.

**Freezing note.** Read ducc0's defaults against its own `verbosity=1`
report (plane count, kernel support, σ) before freezing. Task C's lesson
was that a misread default (padding) cost two post-hoc runs.

## 5. Risks

- **Licence.** No blocker.
  - DDFacet, killMS and ducc0 headers are GPL-2-or-later.
  - Unheaded files and vendored subtrees are not ported.
  - Translation is allowed; verbatim copying of headerless files is
    avoided.
  - ducc0's kernel parameter table, if carried, keeps its notice.
- **Numerical fidelity of the deconvolution.**
  - DDFacet and killMS are built with `-ffast-math` and parallel
    shared-memory reductions, so two runs need not agree bit for bit. DF0
    must measure that spread first.
  - The heuristics (HMP gain schedules, "diverging w.r.t. floor" stops,
    island GA fits) are not specified outside the code. A port can match
    them only at the level of decisions per iteration, and those diverge
    after the first differing peak.
  - DF5 therefore gates on truth from simulated skies and on matched
    residual RMS, not on equality with DDFacet. Fidelity to DDFacet's
    heuristics is not a goal.
- **Data volume at MeerKAT scale on a 30 GiB host.**
  - L1's chunk 0 is 342 M cells, about 11 GB of complex64 DATA alone.
    The core's array driver caps at 12.5 GB.
  - A full L-band track is 10–100× that, so the imager must stream
    chunks into the grids. The wgridder design allows this: grids are
    small (σ² × pixels × planes in flight), samples are streamed per
    w-bunch.
  - DF1's API should take visibility chunks from the start.
  - DDFacet as an oracle at array scale is bounded by `/dev/shm` (16 GB
    here) and by its per-channel model cubes (8.9 GB on a 37 MB MS with
    `NDegridBand 0`, measured). Oracle runs must use channel subsets and
    a few degrid bands.
- **The oracle pair is fragile.** The current killMS cannot run on the
  current DDFacet, and killMS does not build with GCC 15 out of the box
  (both measured). The DF0 container pins both.
- **Scope creep.** DDFacet is about 115 k lines; the plan ports perhaps 5 %
  of them. Every further piece needs a measured reason.
- **Uncertain** (not settled here):
  - the core w-stacking convention against the DFT;
  - whether WSClean `tuned-wgridder` still works;
  - DDFacet's nondeterminism bound;
  - IDG's cost on this GPU;
  - whether B1 needs images (DF6) or only visibilities (DFT predict).

**What it buys the science, against using DDFacet only as an external
oracle.**

- **B1 (beam and pointing).** The constraint lives in the visibilities and
  the predictor. A core imager adds:
  - fast, exact residual and injection images for the faint-emission
    distortion test (meerkat-scope step 4);
  - one process with no MS round trip;
  - per-component, per-antenna beams kept, which DDFacet's facets cannot
    represent at pointing scales (measured table).
- **DD calibration and deep images** (DF3–DF5). These are what DDFacet and
  killMS are for, and they are already good at it. A core version buys
  integration (one process, the same data path as the DI solver and the
  flagger) and possibly cost. It does not buy faint-emission fidelity by
  itself.
- **Under the novelty rule,** the defensible deliverable is DF1/DF2
  (matched-quality, measured cost) plus whatever B1 shows it needs. DF3–DF5
  are worth doing as an integrated imager only if they reach DDFacet's
  quality at lower cost on the simulated field, which is measurable by
  DF0's design.
- **Using DDFacet only as an external oracle** costs nothing beyond DF0 and
  keeps the community tool as the reference for any image-domain claim.

## 6. Tool runs (every run of this study)

Date 2026-10-30 for all rows. Load was 58–66 (one-minute) from about 11:44
onwards, and walls are load-contaminated. RSS is GNU `time`'s maximum for
the largest single process, not the sum over DDFacet's forked workers.

| Tool | Input | Wall | Max RSS | Notes |
| --- | --- | ---: | ---: | --- |
| `git clone` ×3 (DDFacet, killMS, ducc) | GitHub | 11 s | – | 22 MB, 32 MB, 7.7 MB |
| `uv venv -p 3.12` | – | 0.05 s | 22 MB | |
| `uv pip install ./DDFacet ./killMS` | sources | 49.8 s | 174 MB | **failed** (killMS on GCC 15) |
| `uv pip install ./DDFacet` | source | 94.5 s | 874 MB | built; 3 pybind11 modules |
| `uv pip install ./killMS` | source | 9.9 s | 69 MB | **failed**: `Gridder.c:309` incompatible pointer types |
| `uv pip install ./killMS` with `CFLAGS=-Wno-error=incompatible-pointer-types` | source | 24.5 s | 106 MB | built |
| `DDF.py` dirty, field 0 default | LUNO slice MS | 7.9 s | 292 MB | **failed**: "no rows" (data are field 1) |
| `DDF.py` dirty, 1 facet | LUNO slice, 2,048 ch, Briggs 0.5, 512→525 px at 8″, NCPU 4 | 16.6 s | 353 MB | CPU 58 % |
| `DDF.py` dirty, 3×3 facets | same | 32.4 s | 452 MB | 1 vs 9 facets: 2.5 % L∞, 0.49 % RMS of peak |
| `DDF.py` clean, Hogbom, 3 major cycles | same | stopped after about 10 min | 441 MB | stalled in the first minor cycle with an overflow warning; killed |
| `DDF.py` clean, SSD | same | killed at start | – | no result (the run was cancelled with Hogbom's chain) |
| `DDF.py` clean, HMP, 2 major cycles, 2,000 minor | same | 234.5 s | **8.9 GB** | CPU 126 %; 161 minor iterations; degrid 61 s single-core per facet job; DDFacet reports 3 min 41.5 s |
| `uv venv -p 3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` | worktree | 194.9 s | 495 MB | rang venv for the core comparisons and check-all |
| `uv pip install ducc0` | PyPI | 3.9 s | – | 0.42.0 wheel |
| `export_and_ref.py` (export, DFT, ducc0) | slice, every 16th channel | 244.2 s | 3.2 GB | DFT 243 s; ducc0 variants at the default convention (4 % off: `divide_by_n` and w sign) |
| `orient.py`, `tiny.py` | same; 64² synthetic | under 30 s each (not wrapped in `time`) | – | convention pinned: w sign flipped, `divide_by_n=False` |
| `ducc_cmp.py` | slice export | 2.4 s | 79 MB | the table in section 3.1 |
| `core_cmp.py`, `core_cmp2.py`, `core_point.py` | slice export | 2.9 s; others under 1 min (not wrapped) | 443 MB | core against the DFT: unresolved convention |
| `core_psf.py` | slice export, exact DFT PSF | under 10 min (not wrapped) | – | PSF sidelobes 0.80 at the edge |
| `core_psf2.py`, `core_psf3.py` | same | under 2 min each (not wrapped) | – | padding 2, kernel 15, 512 layers: still 1.6 % on the PSF |
| `facet_beam.py` | katbeam 0.1 | seconds (not wrapped) | – | the table in section 3.1 |
| `uv pip install meqtrees-cattery` | PyPI | 9.5 s | 55 MB | 1.8.0; imports |
| `kMS.py` CohJones, scalar, `--DicoModel` from the HMP run | LUNO slice | 8.3 s | 221 MB | **failed**: `AsyncProcessPool._init_default` missing in DDFacet 1.0.0.0 |
| evidence copy and SHA256SUMS | – | seconds | – | `outputs/ddfacet-feasibility-20261030-01`, 15 MB |
| `bash tools/check-all.sh` (first attempt, without the lock) | worktree at `e2296e0` | about 60 min, then stopped | – | stopped during pytest on the coordinator's load-control instruction; log `check-all-aborted-unlocked.log` |
| `flock /home/gijsm/.rang-checkall.lock bash tools/check-all.sh` | worktree at `5aaf758` (documents only) | 2,534.8 s; lock wait 0 s | 1.83 GB | **PASS**; pytest 570 passed and 1 skipped in 2,225.6 s; root 19 and core 55 Rust tests; clippy, fmt, ruff clean; load 77–81 at the start; log `check-all.log` |

## For the coordinator

- **STATE paragraph (proposed).** "DDFacet/killMS feasibility (2026-10-30;
  study, no core code): DDFacet 1.0.0.0 (about 106 k lines of Python, 8.5 k
  C/C++, GPL-2-or-later headers) does w-projection per facet with Voronoi
  tessels, BDA and per-facet 2×2 Jones; most of its code is deconvolution
  heuristics. killMS 3.3.0's CohJones is LM over a per-antenna,
  all-direction Jacobian. Recommendation: no faithful port. Instead:
  - DF1 an exact gridder/degridder porting the ducc0 wgridder algorithm
    (GPL-2-or-later), facet-free, validated against the ducc0 wheel and a
    DFT. ducc0 matches a DFT to 1.2e-5 of peak at epsilon 1e-4 and 8.7e-8
    at 1e-7 on the LUNO slice, in 0.04–0.27 s.
  - Then facets as shifted sub-images with per-facet Jones, a scalar
    CohJones and Hogbom/multiscale, against DDFacet/killMS on a simulated
    MeerKAT target field.
  - B1 keeps per-component beams in the DFT predictor: away from the facet
    nodes, a facet-constant beam errs by up to 13–50× a 30″ pointing signal
    at 9–100 facets (katbeam, measured, worst case at the facet edge).

  Measured on the host:
  - killMS 3.3.0 does not build on GCC 15 without a flag and does not run
    on DDFacet 1.0.0.0;
  - DDFacet HMP on the 37 MB slice peaks at 8.9 GB;
  - Hogbom stalls there.

  [ddfacet-feasibility.md](ddfacet-feasibility.md)."
- **Plan status line (proposed for big-plan.md).** "DDFacet/killMS
  rewrite: feasibility done 2026-10-30 (`ddfacet-feasibility.md`); tasks
  DF0 (oracle container and simulated field) and DF1 (exact wgridder,
  first protocol) can start now beside the science wave; DF2 before B1's
  imaging; DF3–DF5 after B1's protocol says what it needs; DF1b (w-towers)
  when memory binds; DF6 after X2 (facet-IDG in WSClean 3.7 as oracle)."
- **Correction to the brief.** ducc0 is GPL-2-or-later, not GPL-3
  (`src/ducc0/wgridder/wgridder.h` 1–5, classifier "GPLv2+").
- **Upstream observations, `saopicc` (RATT-adjacent; list separately, not
  filed).**
  - killMS 3.3.0 fails to build with GCC 15: `killMS/Gridder/Gridder.c:309`
    passes an incompatible pointer type to the NumPy C API, an error by
    default since GCC 14/15. Workaround
    `CFLAGS=-Wno-error=incompatible-pointer-types`.
  - killMS 3.3.0 calls `DDFacet.Other.AsyncProcessPool._init_default()`
    (`kMS.py:556`), which DDFacet commented out in `51a1d352`
    (2026-05-29). The latest killMS cannot run on DDFacet 1.0.0.0.
  - DDFacet and killMS `pyproject.toml` classifiers say "GPLv2" while the
    file headers say "GPL-2 or (at your option) any later version", and
    173 (DDFacet) and 17 (killMS) source files have no header.
  - DDFacet's `--Selection-Field` defaults to 0 and silently skips an MS
    whose data are in another field ("no rows, skipping", then a
    `RuntimeError`). A clearer error naming the fields present would help.
  - DDFacet Hogbom on a four-station, 2,048-channel slice raises
    `RuntimeWarning: overflow encountered in add` at
    `HOGBOM/ClassModelMachineHogbom.py:184` and stalls in the first minor
    cycle. Not reproduced on other data, so not reportable yet.
- **Non-RATT observations.**
  - ducc0's kernel and grid choice depends on `nthreads` (`getNuNv`,
    `wgridder_impl.h` 1555–1640): measured 1.2e-5 against 8.4e-6 of peak
    at 1 and 4 threads, epsilon 1e-4. This is a property, not a bug, but
    oracles must fix it.
  - ducc0's `wgridder.vis2dirty` defaults to `divide_by_n=True` and to the
    opposite w sign from rang's DFT convention.
  - WSClean 3.6 defaults to wgridder.
- **Evidence to keep.** `outputs/ddfacet-feasibility-20261030-01` (15 MB):
  - DDFacet logs, parsets, FITS and region files of the five runs;
  - the HMP `DicoModel`;
  - the killMS log;
  - comparison JSONs (`ref`, `ducc`, `core`, `core_psf*`, `facet_beam`);
  - install logs and the DDFacet venv freeze;
  - the scripts;
  - upstream commits;
  - `SHA256SUMS`.

  The 7,377-visibility slice export and the DFT image (`inputs.npz`,
  `dft.npy`) were not kept. They are regenerated by
  `scripts/export_and_ref.py` in 4 min.
- **Deleted scratch.** `~/Build/tmp/20261030-ddfacet` (clones, both venvs,
  the copied MSs and DDFacet caches). `/dev/shm/ddf.*` segments of the
  killed runs were removed during the study. The `uv` cache in
  `~/Build/cache/uv` keeps the wheels.
- **Shared files.** None edited.
- **Tool timings rows.** Section 6.

## Open questions for the user

1. **May `saopicc` issues be filed** (the killMS GCC 15 build and the
   killMS/DDFacet API break)? The reporting decision covers `ratt-ru` and
   `caracal-pipeline` only.
2. **Is a simulated MeerKAT target field acceptable as the oracle for
   DF3–DF5,** with truth known and DDFacet/killMS run on it? The
   alternatives are to wait for L3's full-resolution data or to get an
   archive account for a public target field.
3. **Are DF3–DF5 (facets, DD solver, deconvolution) wanted before B1 asks
   for them?** The alternative is DF0–DF2 now and the rest when B1's
   protocol shows a need.
4. **Is compatibility with DDFacet's `DicoModel` and killMS's npz formats
   a requirement,** or are a core component list and gain arrays enough,
   with converters only for the oracle runs?

## References

- C. Tasse et al. 2018, "Faceting for direction-dependent spectral
  deconvolution", A&A 611, A87, [arXiv:1712.02078](https://arxiv.org/abs/1712.02078)
  (DDFacet).
- C. Tasse 2014, "Applying Wirtinger derivatives to the radio
  interferometry calibration problem",
  [arXiv:1410.8706](https://arxiv.org/abs/1410.8706) (CohJones).
- C. Tasse 2014, "Non-linear Kalman filters for calibration in radio
  interferometry", A&A 566, A127,
  [arXiv:1403.6308](https://arxiv.org/abs/1403.6308) (KAFCA).
- O. Smirnov and C. Tasse 2015, "Radio interferometric gain calibration as
  a complex optimization problem", MNRAS 449, 2668,
  [arXiv:1502.06974](https://arxiv.org/abs/1502.06974).
- P. Arras, M. Reinecke, R. Westermann and T. Enßlin 2021, "Efficient
  wide-field radio interferometry response", A&A 646, A58,
  [arXiv:2010.10122](https://arxiv.org/abs/2010.10122) (wgridder).
- P. Wortmann, J. Kent and B. Nikolic, "Imaging swiFTly: streaming
  widefield Fourier transformations for large-scale interferometry",
  [arXiv:2108.10720](https://arxiv.org/abs/2108.10720) (w-towers; WSClean
  3.7 `-gridder wtowers`).
- S. van der Tol, B. Veenboer and A. Offringa 2018, "Image Domain
  Gridding: a fast method for convolutional resampling of visibilities",
  A&A 616, A27, [arXiv:1909.07226](https://arxiv.org/abs/1909.07226) (IDG).
