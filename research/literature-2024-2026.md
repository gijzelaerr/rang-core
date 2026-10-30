# Literature and software scan, 2023 to 2026-10

Written 2026-10-30 as a read-only study for [big-plan.md](big-plan.md). It answers
the user's question (2026-10-30) of which recent findings in mathematics,
physics, astronomy and interferometry should change the core or the science
protocols. No code was changed and nothing here is a measured result. Every claim
below is cited, and every source was accessed on 2026-10-30. Wall time was 11:25
to 13:03 CAT, 1 h 38 min. The survey and writing took about 25 min; the rest was
`tools/check-all.sh` (11:43–12:59 CAT, PASS). Its pytest stage took 66 min
(570 passed, 1 skipped) at load 55–75, with five other sessions' pytest runs on
the host.

## How this was done, and its limits

- **Papers** come from the arXiv API (`export.arxiv.org/api/query`): topic
  keywords, authors (Offringa, Yatawatta, Smirnov, Wiaux, Bester, Thyagarajan,
  Mesarcik) and date windows from 2023. Each cited paper's metadata, journal
  reference and abstract were fetched. **[abs]** = abstract only; **[page]** =
  documentation or release note; **[repo]** = source file or repository API. No
  full texts were read.
- **Software versions** come from PyPI, crates.io and the GitHub, GitLab and
  ASTRON GitLab release APIs, not from search snippets.
- **Gaps.** General web search returned little from 2025–26. ADS, journals,
  proceedings (URSI, ADASS, SPIE), SARAO memos and SKAO Confluence are
  under-covered; absence here is not evidence of absence. *Unverified* marks
  claims from memory or snippets.

Effort scale: **small** is days, **medium** is one to three weeks of a session,
and **large** is more than a month. **Confidence** is my estimate that the item
improves the MeerKAT L-band goals: the gain-TV flagging verdict (L2–L4) and the
beam and pointing question (B1).

## 1. Calibration algorithms

### 1.1 QuartiCal paper and current release (direct baseline)

- **Summary.** Africanus II describes QuartiCal: complex optimisation with
  Wirtinger derivatives, arbitrary chains of gain terms, and Dask task graphs.
  It is demonstrated on MeerKAT PSR J2009−2026 data, with wall-time and memory
  analysis. The current release is v0.2.7 (2026-06-12), after v0.2.6
  (2026-01-08); the v0.2.6 and v0.2.7 GitHub releases have empty notes.
  `solver.robust` (reweighting) defaults to False. `solver.convergence_criteria`
  defaults to 1e-6, `convergence_fraction` to 0.99, and `iter_recipe` to [25].
- **Citation.** Kenyon et al. 2024, arXiv:2412.10072, <https://arxiv.org/abs/2412.10072>
  [abs]. Releases: <https://github.com/ratt-ru/QuartiCal/releases> [repo]. Options:
  <https://quartical.readthedocs.io/en/latest/options.html> [page].
- **Change.** None to the port. QuartiCal's robust mode is a ready comparator if
  a protocol wants Student-t-like reweighting (Mbou Sob et al. 2019,
  arXiv:1910.08136, is the method paper; not re-read here). The core's
  50-iteration cap differs from QuartiCal's default recipe of 25, so protocols
  should state which one they copy.
- **Effort** none. **Confidence** n/a (baseline).

### 1.2 Anderson acceleration of the fixed-point solve (coordinator item, kept)

- **Summary.** No published application of Anderson acceleration (AA) to radio
  gain calibration was found (arXiv keyword queries; a web search turned up only
  StEFCal hyperparameter tuning). The theory does apply:
  - AA provably improves the rate of *linearly* converging fixed-point
    iterations, but not quadratically converging ones (Evans et al. 2020).
  - De Sterck and He (2021) quantify the asymptotic factor.
  - Dallas (2025) proves safeguarded AA converges for perturbed-Newton and
    Levenberg–Marquardt methods on *singular* (2-regular) problems, and that
    the safeguard backs off when the base method is already superlinear.

  The core's QuartiCal port uses a block-diagonal approximate Gauss–Newton
  step, with per-antenna 4×4 `jhj` blocks in `core/src/solve.rs`. That is the linearly converging class AA targets, and the
  calibration gauge (the unitary ambiguity in `flagging.md`) makes the problem
  singular in exactly Dallas's sense. StEFCal's even/odd averaging (Salvini and
  Wijnholds 2014) is a fixed one-step relaxation of the same kind.
- **Citations.** Evans et al., arXiv:1810.08455, <https://arxiv.org/abs/1810.08455>
  (SINUM 2020, journal ref *unverified*) [abs]. De Sterck and He,
  arXiv:2007.01996, <https://arxiv.org/abs/2007.01996> [abs]. Dallas, *Advances in
  Computational Science and Engineering* 6 (2025) 57–75, arXiv:2508.12513,
  <https://arxiv.org/abs/2508.12513> [abs]. Salvini and Wijnholds,
  arXiv:1410.2101, <https://arxiv.org/abs/1410.2101> [abs].
- **Change.** Add an optional AA(m) wrapper, with a γ-safeguard and restart, around
  the per-interval update in `core` solve. Measure it against the L1 array
  convergence (0.83 at the cap; held-out MSE flat after 12 iterations; products
  moving 1.3e-3 between 50 and 91 iterations, per S1). It must reach the same
  fixed point within frozen tolerance, so first fix QuartiCal #452 (swapped qp
  weights) as a separate validated deviation; otherwise the two effects confound.
  Under the novelty rule this is a cost result only: comparable quality with
  fewer iterations.
- **Effort** small–medium. **Confidence** medium that iterations drop on L1
  (untested here); high that the result is clean to measure.

### 1.3 Solution intervals and regularised or smooth gains (the closest relatives of gain TV)

- **Summary.** Mbou Sob et al. (2021) show that the choice of solution interval
  trades noise fitting against gain variability. It depends on SNR, model
  incompleteness and RFI, and an automatic interval selector works except when
  data are inhomogeneously flagged. The authors call for regularised calibration
  instead. Brackenhoff et al. (MNRAS 2025) find smooth spectral gain constraints
  fail near beam nulls and weight the regularisation by the station's expected
  response to the sky model (in DDECal, on LOFAR-HBA).
- **Citations.** arXiv:2103.12508, <https://arxiv.org/abs/2103.12508> (2021,
  before the window but directly relevant) [abs]. arXiv:2504.02483,
  <https://arxiv.org/abs/2504.02483> [abs].
- **Change.** Both bear on why gain TV may be uninformative. TV of a
  per-interval solution mixes noise-fitting (interval too short) with model
  error (incomplete sky), and neither is RFI. Use them in L4's "what would still
  change the answer" section. A TV-*regularised* solve, as opposed to TV-guided
  flagging, is the natural follow-up the literature points to; it is not
  proposed as a new task here.
- **Effort** small (L4 text). **Confidence** high for interpretation, low for a
  positive flagging result.

### 1.4 Rust calibration precedent: MWA hyperdrive

`mwa_hyperdrive` (MPL-2.0; v0.9.0 released 2026-10-30) is the MWA's Rust
calibrator. Its DI solver is the antenna-wise fixed-point update its docs equate
with StEFCal, MitchCal and "antsol"; model visibilities run on CPU or GPU. It is
a reference for Rust GPU prediction and for a StEFCal-family comparator to the
AA result; no port. Sources: <https://github.com/MWATelescope/mwa_hyperdrive>
(README, releases, `mdbook/src/user/di_cal/how_does_it_work.md`) [repo].

### 1.5 Direction-dependent calibration, 2025–26

- **IDGCAL** replaces discrete facet directions with a smooth image-domain
  gridding basis and improves LOFAR image quality (van der Tol et al. 2026,
  arXiv:2602.06002). A follow-up adds cheaper high-order A-terms and a stochastic
  basis (van der Tol 2026, arXiv:2608.10762). Both are [abs] at
  <https://arxiv.org/abs/2602.06002> and <https://arxiv.org/abs/2608.10762>.
- **LOFAR facet calibration at scale.** De Jong et al. (2025) automate
  self-calibration with an SNR metric and a neural-network artefact detector,
  for a factor 4–6 in cost (arXiv:2508.12115, <https://arxiv.org/abs/2508.12115>)
  [abs].
- **MeerKAT DD mosaicing.** Trehaeven et al. (2025, arXiv:2512.16440) combine DD
  calibration with visibility-plane joint deconvolution and primary-beam
  correction. They report about 50 % more dynamic range, flux scale consistent to
  10 % across the field, and compute comparable to per-pointing DD calibration
  [abs] <https://arxiv.org/abs/2512.16440>. This paper is already cited in
  `meerkat-scope.md`.
- **Change.** None now. The calibrator campaigns (L1–L3) are single-field and
  direction-independent. For B1, IDGCAL's smooth A-term basis is the published
  form closest to "pointing derivatives as a smooth DD basis"; record it as
  prior art in the B1 protocol. **Effort** none now (large to port).
  **Confidence** low for L-band calibrator work, medium for B1 framing.

### 1.6 Other items checked

- **Algorithm architecture.** Bhatnagar et al. (AJ 170, 246, 2025,
  arXiv:2508.17187) [abs] cast calibration and imaging as one optimisation
  framework in LibRA, with Kokkos for portability: the NRAO counterpart of the
  core's design (section 6). RL for workflow choices (Kirk et al., AJ 169, 43,
  2025, arXiv:2410.17135) [abs] is not relevant.
- **Kalman, Riemannian or consensus calibration.** No 2023–26 radio paper found.
  The known references (killMS Kalman, Tasse 2014; Yatawatta 2012–2019) predate
  the window and were *not re-read*.

## 2. RFI detection and flagging

### 2.1 SumThreshold remains state of practice

- **Summary.** AOFlagger 3.5 (released 2026-01-27; v3.4 was 2023-10-06) moves
  its GUI to Gtkmm 4 and adds a Lua `normalize_bandpass()` and faster winsorised
  statistics. It adds no new detection algorithm. The last substantive change to
  its algorithm was the Apertif strategy (Offringa et al., A&A 670, A166, 2023),
  which handles invalid-data ranges in SumThreshold and the scale-invariant rank
  operator, flags autocorrelations, and avoids flagging HI. Tricolour (Hugo et
  al. 2022) is the MeerKAT SumThreshold implementation the core ports.
- **Citations.** <https://gitlab.com/aroffringa/aoflagger/-/releases> and
  <https://aoflagger.readthedocs.io/en/latest/changelogs/v3.05.html> [page].
  arXiv:2301.01562 [abs]. arXiv:2206.09179 [abs].
- **Change.** None. The Apertif features (invalid ranges in SumThreshold, the
  scale-invariant rank operator) are the only algorithmic gap between the core's
  Tricolour port and AOFlagger. Port them only if a protocol needs AOFlagger as a
  comparator. **Effort** medium. **Confidence** low.

### 2.2 Machine-learning flaggers

2023–26 learned RFI work is LOFAR system-anomaly detection (ROAD, Mesarcik et
al., A&A 680, A74, 2023, arXiv:2307.01054), spiking networks on simulated HERA
data (Pritchard et al., arXiv:2406.06075), single-dish/FAST work, and
probabilistic time-series mixtures on MWA data that give per-sample RFI
probabilities matching or beating SSINS (Ducharme et al. 2026,
<https://arxiv.org/abs/2609.26904>) [abs]. No learned flagger trained and tested
on MeerKAT interferometric visibilities was found after R-Net (Vafaei Sadr et
al. 2020, arXiv:2005.08992). No change to the core; for L4, a soft per-sample
RFI probability is a better-posed target than a binary mask (untested; low
confidence).

### 2.3 Low-rank plus sparse (robust PCA) separation (coordinator item, drop)

- **Summary.** Kim (PASP 2026, arXiv:2601.00046) studies single-epoch low-rank RFI
  mitigation with controlled simulations and HERA data. Aggressive rank
  truncation distorts diffuse and low-SNR signal, and beyond a critical
  interference strength information loss is irreversible ("operational
  non-identifiability"). No MeerKAT test of low-rank or robust PCA flagging was
  found.
- **Citation.** <https://arxiv.org/abs/2601.00046> [abs].
- **Change.** Drop it from the plan. It adds a separation whose failure mode is
  the one the project's science-distortion criterion forbids. **Effort** n/a.
  **Confidence** low.

### 2.4 Satellite RFI at L-band, and ephemeris-aware mitigation (coordinator item, demote)

- **Starlink unintended emission is documented below 250 MHz, not at L-band:**
  703 v2-mini satellites in 150–153 MHz on an SKA-Low prototype (Grigg et al.,
  A&A 699, A307, 2025, arXiv:2506.02831; count from a search snippet) and
  broadband polarised emission below 100 MHz with NenuFAR (Zhang et al., A&A
  698, A244, 2025, arXiv:2504.10032; metadata only). Cerardi et al. (2026,
  arXiv:2604.22694) [abs] forecast that SKA-Mid's higher frequencies are mostly
  spared, while below 1 GHz satellites sit in the main beam or first sidelobe
  at least 30 % of the time.
- **At MeerKAT L-band, satellite RFI is intended emission in allocated bands.**
  GNSS in 1100–1350 MHz was simulated and fitted to MeerKAT single-dish data;
  non-linearity complicates the fit (Engelbrecht et al. 2024, arXiv:2404.17908)
  [abs]. L-band RFI is dominated by DME, GSM and GPS, with occupancy varying in
  time and direction (Sihlangu et al. 2022, arXiv:2211.08879) [abs]. The core's
  copy of Tricolour's L-band static mask (`core/data/4k_lband_meerkat.staticmask`,
  read here) already masks 915.8–960.0, 1145.9–1300.9 and 1519.3–1626.7 MHz
  among 29 ranges: the GSM, GNSS and Inmarsat/GNSS-L1/Iridium allocations.
- **TABASCAL** jointly fits RFI trajectories and gains (Finlay et al., MNRAS
  2023, arXiv:2301.04188). Paper II (A&A 701, A286, 2025, arXiv:2502.00106) [abs]
  removes up to nine satellites from *simulated* MeerKAT data in *one channel*,
  reaching RFI-free image noise (10–100× below AOFlagger for strong RFI). It
  needs trajectories a priori.
- **Moving sources.** Ducharme et al. (2026, arXiv:2609.35983) [abs] model the
  sinc-like suppression correlator averaging gives a moving source, bright on
  some baselines and suppressed on others (MWA). No flagging treatment fully
  recovered the clean spectrum.
- **Change.** Ephemeris flagging at L-band would mostly re-derive the static
  mask. The useful version is an *audit*: label LUNO chunk-0 first-pass flags
  and TV maps by allocated band and time, to explain the station-bins whose
  training samples are all flagged (L1 criterion 6). The moving-source baseline
  pattern is also a hypothesis for why antenna-factorised gain TV misses RFI
  (5.1). TABASCAL is subtraction, not flagging, at single-channel scale; later.
- **Effort** small (audit). **Confidence** low–medium that the audit explains L1;
  low for ephemeris flagging as a method.

### 2.5 Other

Yatawatta et al. (2024, arXiv:2412.14775) [abs] detect RFI in the correlator
from energy plus polarisation alignment (half precision, GPU, real LOFAR data):
the closest published use of polarisation structure for RFI, relevant to 5.1.
CHARIZARD (Pal et al. 2026, arXiv:2610.21158) [abs] is a sub-band-parallel
MeerKAT full-Stokes pipeline, a cost reference rather than an algorithm.

## 3. Gridding, imaging and deconvolution

### 3.1 wgridder and ducc0 (coordinator item: correct, but not recent)

- **Summary.** W-gridding is Arras et al., A&A 646, A58 (2021,
  arXiv:2010.10122), with accuracy analysis by Ye et al. (arXiv:2101.11172)
  [abs]. WSClean had `-wgridding-accuracy` by v3.0 (2021-08-26), consolidated
  gridder options in v3.2 (2022-10-21), and 3.6 *defaults* to wgridder (already
  recorded in `flagging-imaging.md`). WSClean 3.7 (2026-02-16) adds a
  **w-towers** gridder, facet-IDG, frequency baseline-dependent averaging and
  Sisco model compression, and turns deconvolution boosting off. ducc0 is at
  0.42.0 (2026-10-20), GPL-2.0-or-later (FFT files dual BSD-3), compatible with
  rang's GPL-3.0-or-later.
- **Citations.** WSClean changelogs <https://wsclean.readthedocs.io/en/latest/changelogs/v3.0.html>
  (via search result), `.../v3.6.html`, `.../v3.7.html` [page];
  <https://github.com/mreineck/ducc> (README, `wgridder.h` header) [repo].
- **Change.** P2 already made the w-stacking gridder fast (0.53–0.80 s per
  four-station image). W-gridding would add an explicit accuracy parameter ε in
  place of a w-layer count, and ducc0's wheel is a second oracle with known error
  bounds. Use ducc0 as an oracle first; port (Rust, from the GPL-2+ source) only
  if whole-array imaging is still the bottleneck after P5.
- **Effort** small (oracle); medium (port). **Confidence** medium for speed and
  accuracy control; none for science.

### 3.2 Image-domain gridding and GPU imagers (coordinator item: 2018, now with GPU and calibration)

- **Summary.**
  - IDG is van der Tol et al., A&A 616, A27 (2018), arXiv:1909.07226.
  - New in the window: **Pigi**, a GPU IDG implementation for NVIDIA and AMD at
    almost 5e8 visibilities/s, demonstrated on simulated MWA data with extreme
    ionosphere (Hodgson 2025, arXiv:2502.17789) [abs].
  - **IDGCAL** (1.5 above).
  - **BRISK**, which compresses w-projection kernels by randomised SVD and
    claims speedups against CASA and WSClean on simulated data (Ogden et al.
    2026-10-16, arXiv:2610.23671) [abs]. It is the one randomised-linear-algebra
    result found in imaging.
  - **Dabbech and Wiaux (2026, arXiv:2605.26347)** pick the number of w-bins
    automatically under a memory budget in hybrid w-stacking/w-projection [abs].
- **Change.** IDG matters only if B1 needs time-varying per-antenna A-terms
  (pointing) inside imaging. Until B1 shows that pointing corrections are
  constrained, keep pointing in the visibility-domain predictor. Dabbech's
  memory-budgeted w-bin choice fits P5's memory work if whole-array imaging
  exceeds 30 GiB.
- **Effort** large (IDG). **Confidence** low now, medium after a positive B1.

### 3.3 RATT imaging and learned deconvolution

- **pfb-imaging** (Bester et al. 2024, arXiv:2412.10073) [abs] implements uSARA
  in a framework that scales with image size, not data volume. It is validated
  on TB-scale MeerKAT data, on one node and on AWS. The PyPI release is 0.0.11
  (2026-07-28); the repository was pushed 2026-10-29
  (<https://github.com/ratt-ru/pfb-imaging>) [repo]. If the core ever deconvolves,
  this is the RATT-aligned, MeerKAT-validated first target.
- **Wiaux group.** uSARA and AIRI validated on ASKAP (Wilber et al. 2023,
  arXiv:2302.14148, 2302.14149); R2D2, a learned CLEAN-like DNN series
  (arXiv:2403.05452; robust version ApJS 280, 63, 2025, arXiv:2503.02554;
  spherical arXiv:2503.01462; ensembles arXiv:2403.18052) [abs]. No MeerKAT
  validation found; R2D2 needs training per telescope.
- **Score-based or diffusion priors (coordinator item, drop for now).** Morales
  et al. (2026, arXiv:2601.15844) [abs] train a DDPM on VLA FIRST and test on
  simulated VLBA, EHT and ALMA data; the authors say their samples are not yet
  calibrated uncertainty estimates. Other diffusion work is VLBI with closure
  invariants (Lai et al., PASA 42, e148, 2025, arXiv:2510.12093) [abs]. Nothing
  at MeerKAT wide-field data volume was found.
- **Change.** None until deconvolution is in scope. The science protocols use
  dirty images and PSFs only. **Effort** large. **Confidence** low for current
  goals.

### 3.4 Uncertainty quantification and data volume

- **UQ.** QuantifAI (Liaudat et al., arXiv:2312.00125: convex learned prior,
  MAP credible intervals without MCMC) and a conformalised equivariant bootstrap
  (Cherif et al. 2024, arXiv:2410.23178) [abs]. If B1 needs error bars on "no
  suppressed faint emission", the bootstrap is the cheapest to add to a
  dirty-image pipeline; the existing injection tests are the frequentist
  version. Medium effort, low confidence.
- **Compression.** Sisco (Offringa et al., A&A 706, A68, 2026, arXiv:2512.23490)
  compresses noiseless model visibilities to 24 % losslessly and ships in
  WSClean 3.7. Lossy compression at about 10× preserved MeerKAT MHONGOOSE
  spectra to about 0.01 % (Dodson et al., MNRAS 2026, arXiv:2609.25988) [abs].
  Not needed: the core never stores model data.

## 4. Primary beam and pointing

### 4.1 MeerKAT beam products are unchanged since 2023

- **Summary.** No 2024–26 arXiv paper on MeerKAT holography or L-band beam
  modelling was found (queries: MeerKAT with primary beam, holography, pointing).
  - The SARAO knowledge-base page (last updated 2024-05-31) still points to the
    de Villiers (2023, AJ 165, 78) holography models in the SARAO repository
    (DOI 10.48479/wdb0-h061). It quotes pointing errors of σ = 0.6′, and
    antenna-to-antenna beam deviations of 0.3 % mean (up to 1.4 %) in the lower
    L-band and 0.9 % (up to 5 %) in the upper half.
  - It says reference pointing procedures are still under development.
  - katbeam's only PyPI release is 0.1 (2020-10-15); its repository was pushed
    2026-06-01. EIDOS is at 1.1.2 (2024-01-24).
- **Citations.**
  <https://skaafrica.atlassian.net/wiki/spaces/ESDKB/pages/1481572357> [page].
  arXiv:2202.02101 and arXiv:2301.06752 (already in `meerkat-scope.md`).
  <https://pypi.org/project/katbeam/>, <https://pypi.org/project/eidos/> [repo].
- **Change.** B1 should take the per-antenna holography cubes (DOI above) as
  E_p,0, with katbeam as the smooth control. Freeze the beam product, its
  version or DOI, and its frequency sampling in the B1 protocol. The page
  recommends sampling at 10 MHz or finer.
- **Effort** small (protocol); medium (ingest cubes). **Confidence** high that
  this is the right reference beam.

### 4.2 Pointing calibration in practice and pointing self-calibration

- **SKA SDP pointing-offset pipeline**
  (<https://developer.skao.int/projects/ska-sdp-wflow-pointing-offset/en/latest/>)
  [page]. It fits 2-D Gaussian beams to visibility or gain amplitudes from
  pointing scans, following SARAO's MeerKAT procedure, and writes cross-elevation and elevation offsets with uncertainties. The
  project's first fixture (`outer_scans.zip`) is this pipeline's test data.
- **katpoint.** v0 is in bug-fix mode (0.10.2, 2024-10-31) and is superseded by
  katpoint 1 hosted by SKAO. This is from a search snippet of the PyPI page,
  *partly unverified*.
- **ngVLA** makes routine pointing self-calibration part of its baseline
  high-dynamic-range calibration strategy (Sridharan et al., URSI GASS 2023,
  arXiv:2504.14449) [abs]. A companion memo argues image errors from
  antenna-based gain errors scale as √N rather than N in the stringent limit
  (arXiv:2504.18733) [abs].
- **SKA-Mid** reached first fringes with two dishes on 7 January 2026; a
  four-dish image was the next goal (<https://www.skao.int/en/news/693/ska-mid-milestone>)
  [page]. No AA0.5 completion date was confirmed.
- **Change.** B1's baselines should be:
  - the SARAO and SKA Gaussian-fit offsets on pointing scans (the established
    method);
  - physical pointing self-calibration on science scans (Bhatnagar-style; the
    2017 paper was not re-read).

  Rang's candidate (distinguishability-selected corrections with a
  science-distortion budget) must beat both at matched cost. The √N scaling
  memo gives a quick analytic budget for how much pointing error matters at 64
  dishes.
- **Effort** small (protocol). **Confidence** high for framing.

### 4.3 Calibrator field models: the strongest finding for the current campaign

- **Summary.**
  - Heywood et al. (2020) simulate a wide-field sky model around PKS B1934−638.
    For MeerKAT, a central point model during bandpass calibration imparts
    0.2–0.5 % amplitude errors and ripples in target spectra. The errors depend
    on baselines, solution interval, primary beam, hour angle and imaging
    weights. They conclude pipelines should use complete calibrator field
    models.
  - CARACal ships such a model: `caracal/data/meerkat_files/pks1934-638.lsm`,
    196 components, central A0 15.07 Jy at 1.3 GHz with a four-term spectral
    polynomial, last changed 2020-04-09. Its `crosscal` worker documents
    `meerkat_skymodel` (default False) as the MeerKAT local sky model, with a
    Crystalball variant.
  - L1's post-hoc diagnosis is that the LUNO MODEL_DATA is a 14.96 Jy point
    about 1.5″ off the phase centre. Two consequences follow:
    - The gain solutions absorb unmodelled field-source structure, which
      varies with time through the hour angle, into apparent gain variation.
    - That is a mechanism for gain TV unrelated to RFI.
- **Citations.** Heywood et al. 2020, arXiv:2004.00454,
  <https://arxiv.org/abs/2004.00454> [abs].
  <https://github.com/caracal-pipeline/caracal/blob/master/caracal/data/meerkat_files/pks1934-638.lsm>
  and `docs/sphinx/manual/workers/crosscal/index.rst` [repo]. Taylor and Legodi
  2024 (arXiv:2405.04131) [abs] give full-Stokes properties of 98 MeerKAT
  calibrators: 0.16 % residual instrumental linear polarisation, 0.05 %
  circular. This is the reference for whether the "unpolarized calibrator"
  convention in `flagging.md` holds.
- **Change.** Add a model-completeness arm to L2, or as a short L1
  re-analysis: predict the 196-component field with the core's component
  predictor and re-solve chunk 0. Compare convergence, held-out loss and TV maps
  against the point model, under the same frozen arms. If TV structure drops,
  the L1 null partly measured model error. The core predictor (`core/src/predict.rs`,
  `core-phase3c-a.md`) already handles points and Gaussians with ordinary or
  logarithmic polynomial spectra, but applies no primary beam. Two things to
  freeze in the protocol:
  - the lsm's spectral convention (`spi`, `spi2`… against the predictor's
    log-polynomial), checked on A0;
  - whether the fluxes are apparent or intrinsic. CARACal's `crosscal` worker
    passes the lsm to its simulator cab with no beam option, so the
    CARACal-equivalent prediction is beam-free (apparent fluxes). The sources
    reach about 0.5° off-axis, so this matters.

  The model file is GPL-2 (CARACal) and is data; the core reads it and does not
  copy code.
- **Effort** small if beam-free prediction is accepted, medium if a beam is
  needed. **Confidence** high that it changes the solutions, medium that it
  changes the flagging verdict.

## 5. Mathematics

### 5.1 Closure invariants for full-Jones (GL(2,C)) gauge freedom (coordinator item, kept and sharpened)

- **Summary.**
  - **Closure traces.** Broderick and Pesce (2020) build closure quantities from
    all four correlations that are independent of *every* station-based linear
    corruption: gains and leakage.
  - **Gauge-theory framing.** Samuel, Nityananda and Thyagarajan (PRL 128,
    091101, 2022) treat per-element 2×2 complex distortions as GL(2,C) gauge
    transformations. They give a complete, independent invariant set built from
    triangles without autocorrelations. The co-polar (abelian) case is
    Thyagarajan et al. (PRD 105, 043019, 2022): N²−3N+1 real invariants.
  - **Incomplete graphs.** Kumar, Nityananda and Samuel (2024) extend the set to
    graphs where some baselines are missing, as flagged data are, and show the
    invariants stay informative with noise.
  - **Recent use** is VLBI imaging (Müller, A&A 689, A299, 2024; Lai et al. 2025,
    2026) and classification (Thyagarajan et al. 2023–24).
  - No use of closure invariants as a flagging statistic was found.
- **Citations.** arXiv:2010.00612 [abs]. arXiv:2108.11400 [abs].
  arXiv:2108.11399 [abs]. arXiv:2407.00583, <https://arxiv.org/abs/2407.00583>
  [abs]. arXiv:2407.20190 [abs]. arXiv:2311.06349 [abs].
- **Why it matters here.**
  - Gain TV measures structure in the *antenna-factorable* part of the data.
    By construction, a closure invariant of the data is blind to that part and
    sees only what no per-antenna Jones matrix can absorb: baseline-based
    errors, the RFI pattern on some baselines (Ducharme, 2.4), and model error.
  - On a calibrator with a known model, the residual of data invariants against
    model invariants is a gauge-free, solve-free detector. It needs no choice
    between raw and polar-gauge TV.
  - Counting real degrees of freedom gives generic data 4N(N−1) real numbers
    and a gauge group of 8N−1 effective dimensions (the common scalar phase acts
    trivially). That leaves 4N²−12N+1 invariants for N≥4: 17 at N=4, 10,601 at
    N=53. For
    an *unpolarised* point model a common unitary also acts trivially, which is
    the ambiguity `flagging.md` records. This count is my derivation, *not
    checked against the papers' text*.
- **Change.** Add a frozen comparator arm to L2 or L4: per-(time, channel-block)
  closure-phase and closure-trace residuals against the model, on a
  reference-antenna triangle basis (O(N²) quantities), turned into a flag mask
  with the same budget and held-out loss as the TV arms. A null here as well
  would strengthen the L4 negative result: neither the antenna-factorable nor
  the non-factorable statistic helps. Kernel: 2×2 products and inverses on
  existing blocks, in Rust.
- **Effort** medium. **Confidence** medium (a better-posed hypothesis; untested).

### 5.2 Identifiability, randomised linear algebra, optimal transport

- **Identifiability.** Beyond the gauge counts above, no 2023–26 paper on
  full-Jones identifiability was found. The directions a gain solve cannot see
  are the model's stabiliser: a common phase (1) for generic models, and a
  common U(2) (4) for an unpolarised point. The rank survey already uses the
  latter: rank 8n−4 per fully identified bin
  (`stack-consolidation-feasibility.md` section 3; `src/response.rs`). Nothing
  new to add.
- **Randomised linear algebra.** BRISK (3.2) is the only randomised-SVD result
  found in imaging; sketched AA (Bucci et al. 2026, arXiv:2607.04904, title
  only) links AA to sketched GMRES. The core's per-interval normal equations are
  small (8N), so randomisation is not needed there.
- **Optimal transport and TV theory.** No interferometry-specific 2023–26
  result was found. Not pursued.

## 6. Software and hardware

| Item | Version, date (source) | Relevance |
| --- | --- | --- |
| QuartiCal | 0.2.7, 2026-06-12 (GitHub) | baseline; #452 open in the port |
| Tricolour | 0.2.1, 2026-04-01 (PyPI) | baseline (port exists) |
| codex-africanus / dask-ms | 0.4.5, 2026-10-09 / 0.2.32, 2026-05-18 (PyPI) | upstream of the predictor and the ingest |
| pfb-imaging | 0.0.11, 2026-07-28 (PyPI) | future deconvolution comparator |
| DDFacet | v1.0.0.0, 2026-06-23 (GitHub): EveryBeam, NenuFAR beam, rectangular mosaicing, SSDv3, WSCMSv2, MPI gridding | alive; no rewrite needed |
| killMS | 3.3.0, 2026-01-29 (PyPI) | DD comparator |
| WSClean | v3.7, 2026-02-16; v3.6, 2025-02-07 (GitLab) | oracle; w-towers, facet-IDG |
| AOFlagger | v3.5.0, 2026-01-27 (GitLab) | no new algorithm |
| DP3 | v6.6, 2026-05-07 (ASTRON GitLab) | DDECal comparator |
| EveryBeam | 0.9.1, 2026-10-21 (PyPI) | beam library for WSClean/DP3/DDFacet |
| ducc0 | 0.42.0, 2026-10-20 (PyPI), GPL-2.0-or-later | wgridder oracle |
| FINUFFT / cuFINUFFT | 2.5.1, 2026-04-08 (PyPI) | NUFFT reference; not needed for w-stacking |
| CARACal / Stimela | 1.2.1, 2025-10-28 / 2.1.4, 2026-04-15 (PyPI) | strategies; 1934 field model |
| xradio | 1.3.0, 2026-10-16 (PyPI); implements the **Measurement Set v4.0.1** schema (docs) | future MS-free interchange |
| zarr-python / numcodecs | 3.4.2, 2026-10-27 / 0.17.1, 2026-10-20 (PyPI) | ingest stack |
| Rust crates | rustfft 6.4.1; wgpu 30.0.1; cudarc 0.19.10; cubecl 0.11.3; faer 0.24.4; zarrs 0.23.14; arrow 60.1.0; pyo3 0.30.1; rayon 1.12.0 (crates.io) | GPU and format options |
| mwa_hyperdrive / Birli | 0.9.0, 2026-10-30 / 0.21.0, 2026-10-15 (GitHub) | Rust radio precedent |

Notes:

- **GPU portability.** In astronomy the published route is Kokkos (LibRA,
  Bhatnagar et al. 2025), and CUDA/HIP for Pigi (Hodgson 2025). No published
  wgpu or Vulkan-compute radio imager was found. For the core, `cudarc` (CUDA
  only, matches the host's RTX 4070 Ti) is the lowest-risk path. `cubecl` and
  `wgpu` buy portability at the cost of less mature FFT support. This was not
  measured.
- **Formats.** `zarrs` (Rust, zarr v3) would let the ingest read zarr v3 stores
  without Python. xradio's MSv4 is the NRAO/CASA-NG direction (docs page:
  <https://xradio.readthedocs.io/en/latest/> [page]; the backend and the
  observatories behind it were not stated on that page).

## 7. Ranked recommendations for the plan (at most twelve)

Each line gives the first protocol to freeze.

1. **PKS 1934−638 field model (4.3).** Protocol "L1-M model completeness":
   chunk 0, the same arms and split as L1, CARACal's 196-component lsm predicted
   by the core against the point model, with the spectral convention and the
   apparent/intrinsic (beam) choice frozen; report convergence, held-out loss,
   TV maps and the policy call. Small to medium; high confidence that solutions
   change.
2. **Solver: #452 fix, then safeguarded Anderson acceleration (1.2).** Protocol
   "S2 solver": (a) a #452 weight fix against the frozen fixed point; (b) AA(m),
   m ∈ {2, 4, 8}, with γ-safeguard, on LUNO 4-station and 53-station, measured
   by iterations to QuartiCal's 1e-6 criterion and by the S1 product-drift
   metric. Small–medium; medium confidence.
3. **Closure-invariant comparator arm (5.1).** Protocol "C1 gauge-free
   detector": closure phase and closure trace residuals against the model, the
   same mask budget, held-out loss and decision rule as the TV arms, on the
   four-station K slice first, then chunk 0. Medium; medium confidence.
4. **B1 reference beam frozen to the SARAO holography cubes (4.1).** Protocol
   "B1-0 beam product": DOI 10.48479/wdb0-h061, frequency sampling of 10 MHz or
   finer, katbeam as control, beam rotation convention. Small; high confidence
   in the choice.
5. **B1 baselines (4.2).** Protocol "B1-1 comparators": the SARAO/SKA Gaussian
   offset fit on pointing scans, and physical pointing self-calibration on
   science scans, matched in cost against the distinguishability-selected
   method. Small; high confidence for framing.
6. **RFI-band audit of L1's empty station-bins (2.4).** Protocol "A1 audit":
   label every first-pass flag in chunk 0 by allocated band (GNSS, Iridium,
   Inmarsat, DME) and time; no new flags, explanation only. Small; low–medium
   confidence.
7. **L4 text: solution-interval and regularisation literature (1.3)** as the
   "what would still change the answer" section: interval choice, response-weighted
   smoothness, TV-regularised solving as the untested alternative. Small.
8. **Polarisation check of the calibrator convention (4.3, Taylor and Legodi
   2024)** before C1: confirm that 1934−638's measured fractional polarisation
   is below the closure-trace noise, so that the unpolarised-model invariants
   are valid. Small.
9. **ducc0 wgridder as a second imaging oracle (3.1).** Protocol: dirty and PSF
   on the task C/I fixtures at ε ∈ {1e-5, 1e-7} against the core and WSClean
   `-gridder wstacking`. Port only if whole-array imaging stays the bottleneck.
   Small.
10. **Memory-budgeted w-bin choice (3.2, Dabbech and Wiaux 2026)** folded into P5
    if whole-array images exceed the 30 GiB host. Small–medium.
11. **GPU path via `cudarc` for the gridder and FFT (6)**, only after P5–P7,
    with free-memory checks (the host shares the GPU). Medium; speed only.
12. **pfb-imaging as the first deconvolution comparator (3.3)**, only if a
    science protocol needs deconvolved images (none does today). Large.

Not recommended now: diffusion or score-based priors (3.3), robust PCA RFI
separation (2.3), ephemeris-based flagging as a method (2.4), an IDG port
(3.2), a DDFacet rewrite (DDFacet 1.0 is maintained), TABASCAL (simulated,
single-channel, needs trajectories).

## 8. What the coordinator's list got wrong or out of date

- **"ducc0 wgridder" is not a recent finding.** It is Arras et al. 2021, was in
  WSClean by v3.0 (2021-08-26), and is WSClean's default gridder, as this
  repository already records. What is new: WSClean 3.7's w-towers gridder and
  facet-IDG (2026-02-16), and ducc0 0.42.0 (2026-10-20).
- **"Image-domain gridding for DD effects"** dates from 2018 (A&A 616, A27). The
  2025–26 news is GPU IDG (Pigi) and IDG-based *calibration* (IDGCAL), both
  LOFAR or MWA, not MeerKAT.
- **"A DDFacet rewrite"** assumes DDFacet is stagnant. It released v1.0.0.0 on
  2026-06-23 (EveryBeam, MPI gridding, mosaicing), and MeerKLASS used it in 2025
  (arXiv:2512.11978). Nothing in the current science needs DD imaging.
- **"Closure quantities as a gauge-invariant flagging signal"** is sound, but the
  invariants are 2020–22 work (closure traces; the GL(2,C) gauge papers). The
  2024 incomplete-graph extension is what makes them usable with flags. No
  flagging use is published, so it is a hypothesis, not a finding.
- **"Anderson/quasi-Newton acceleration of gain solves"** has no radio
  publication that I found. The support is general fixed-point theory (2020–25),
  which predicts help only for linearly converging solvers.
- **"Low-rank plus sparse RFI separation"** has a 2026 negative result
  (single-epoch non-identifiability, PASP) and no MeerKAT test.
- **"Satellite-aware flagging from ephemerides".** The prominent constellation
  results (Starlink unintended emission) are below 250 MHz. At MeerKAT L-band the
  satellite RFI is intended emission in allocated bands, which static masks
  already cover. TABASCAL is subtraction on simulated single-channel data.
- **"Score-based diffusion priors for deconvolution"** are demonstrated on
  simulated VLBA, EHT and ALMA and on VLBI. Their own authors say the samples
  are uncalibrated. The core has no deconvolution.
- **Missed by the list:** the calibrator field model (Heywood 2020; CARACal's
  lsm), which bears on L1's post-hoc diagnosis; the solution-interval and
  regularised-gain literature, which explains gain TV; and the SARAO holography
  product and SKA pointing-offset pipeline as B1 baselines.

## For the coordinator

**STATE paragraph (proposed).** Literature scan (big plan, read-only),
2026-10-30, in `literature-2024-2026.md`. arXiv, release APIs and changelogs
were surveyed for 2023–2026-10 across calibration, RFI, imaging, beams and
pointing, mathematics and software; every source was accessed 2026-10-30, and
most papers were read at abstract level. The strongest finding for the active
experiment is calibrator model completeness. Heywood et al. (2020) show a point
model of PKS 1934−638 imparts 0.2–0.5 % structured amplitude errors at MeerKAT,
and CARACal ships a 196-component 1934 field model. L1 solved against a 14.96 Jy
point, so part of the gain structure that TV measures may be model error. Other
recommendations:
- safeguarded Anderson acceleration after the #452 fix, for the 0.83 array
  convergence (theory only; no radio precedent found);
- a closure-invariant (GL(2,C) gauge-free) comparator arm, which isolates
  exactly the non-antenna-factorable part that gain TV cannot see;
- the SARAO holography cubes and the SARAO/SKA pointing-offset fit as B1's
  reference beam and baseline.

Dropped from the candidate list: diffusion priors, robust PCA RFI separation,
ephemeris flagging as a method, an IDG port and a DDFacet rewrite. No code was
changed.

**Plan additions (wave 3).**
- **L1-M** model-completeness re-analysis: before or with L2. Owns
  `research/l1-model-completeness.md`, plus an example script and a test.
- **S2** solver: #452 fix and AA. Owns solver files after P7. Science protocol,
  because the cap and convergence change.
- **C1** closure-invariant comparator arm: after L1-M, before L4.
- **A1** RFI-band audit of the L1 empty station-bins: small, any time.
- **B1** additions: B1-0 (beam product frozen) and B1-1 (baselines frozen) as the
  first two protocols of B1.
- **L4** must cite the solution-interval and regularisation literature in its
  "what would change the answer" section.

**Upstream observations (no issue proposed).**
- CARACal's `meerkat_skymodel` defaults to False although its docs advise the
  field model to avoid calibrator-field substructure effects. This is a
  design choice, not a bug; record it in `upstream-notes.md` as context for L1.
- QuartiCal's v0.2.6 and v0.2.7 GitHub releases carry no notes, so checking
  whether #452 or #453 was fixed requires the commit log.
- katbeam has had no PyPI release since 0.1 (2020) and EIDOS none since 1.1.2
  (2024-01). Neither is a bug.
