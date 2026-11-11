# V6: VLBI in ra-ng, a scoping note

Task V6 of [vision.md](vision.md). Written 2026-11-11 on branch
`claude/mystifying-mclaren-5c64e0` from `main` `c2fe7cc`.

**Status: proposed; nothing built or measured.** Every plan, tolerance and cost
below is a proposal. Facts about other tools and data are from the sources in
section 9, read on 2026-11-11; where a fact was not found or not checked, the
text says so. The owner decides whether and when this starts; the vision puts it
after LOFAR.

## 1. Recommendation in one paragraph

The first VLBI piece is **fringe fitting**: per station and solution interval,
phase, delay and delay rate (dispersive delay off), FFT search then a global
least-squares refinement, single-band and multiband, in Rust. Oracle: **CASA
6.7.6.14 `fringefit`**, the CASA build rang's calibration oracles already pin,
with AIPS FRING as an optional second reference (van Bemmel et al. 2022 found the
two packages agree). Data: a simulated VLBI truth made by rang's own writer in
N14C3's layout, then the public EVN network-monitoring experiment **N14C3**
(2014-10-22, 5 GHz, 8 × 16 MHz) imported by CASA `importfitsidi`, so no FITS-IDI
reader is needed for this piece. It extends code rang already has (C2b's
FFT delay estimate, C2c's Gauss-Newton with a free phase) and needs nothing
unbuilt. Closure imaging, the other candidate, waits on DF5's RML arm, which is
not built (section 6).

## 2. What carries over from rang-core

| rang-core part | Where | Use in VLBI | Gap |
| --- | --- | --- | --- |
| Measurement equation, 2×2 Jones apply and corrupt | C1, C4a, `core/src/cal/apply.rs` | the same RIME; a fringe-fit table is a phase, delay and rate per station | a rate term (phase linear in time) in apply and in CASA's table layout (`FringeJones`) |
| K: FFT initial estimate, reference baselines | C2b, `core/src/cal/delay.rs` (8× padding, CASA's peak rules read in `KJones.cc`) | stage 1 of fringe fitting, along frequency | the time axis (rate) makes it a 2-D FFT; multiband across spectral windows |
| Delay with free phase, Gauss-Newton | C2c, `core/src/cal/delay_offset.rs` | stage 2 (global least squares) with rate added | weights by SNR, all baselines, not reference baselines only |
| G, B, Df and polarisation terms | C2a, C2c, C6 | bandpass and gain after fringe fitting, as in EVN practice; MeerKAT's linear feeds (section 5) | parallactic angle on alt-az stations with different mounts |
| Flagging (Tricolour port, CASA flag versions) | core-d, E0, DF-IO | RFI flagging; the UVFLG files EVN pipelines ship | a UVFLG reader (CASA users convert with `flag.py`) |
| Closure statistics | [c1-closure-arm.md](c1-closure-arm.md) (closure-TV, gauge-free by construction) | closure phases and amplitudes are the VLBI data products for imaging and checks | bispectrum and log closure-amplitude sets with their covariances |
| Formats layer: MS reader and writer, CASA caltables | core-e, E3-E6, DF-IO | read CASA-imported VLBI MSs, write `fringefit`-readable tables | FITS-IDI and UVFITS, ANTAB (owner decision 4) |
| Imaging: GeMClean, wgridder, DF5-O oracles | G-series, DF1-DF2, [df5o-deconv-oracles.md](df5o-deconv-oracles.md) | dirty images, CLEAN on VLBI data with few stations | sparse uv makes CLEAN plus self-calibration (DIFMAP practice) or RML the norm |
| DF5's planned RML arm (TV, sparsity) | [big-plan.md](big-plan.md), not started | the same regularisers eht-imaging and SMILI use | closure-only data terms (Chael et al. 2018); not built |
| Simulated truth with seeds | [a1-simtruth.md](a1-simtruth.md) | VLBI truth sets with injected delays, rates and phases | Earth-scale geometry, independent clocks per station, rates |

## 3. What is new

| Item | What it is | Size of the job (proposed estimate) |
| --- | --- | --- |
| Fringe fitting | per station: phase, delay, rate (and dispersive delay); FFT search to a reference station, then global least squares (Schwab & Cotton 1983; AIPS FRING; CASA `fringefit`: two stages, `minsnr` at the FFT stage, `combine='spw'` for multiband, `zerorates`, `delaywindow`, `ratewindow`, `paramactive`, `corrcomb`) | the first piece (section 7) |
| A priori amplitude calibration | Tsys per station from ANTAB, gain curves (DPFU, polynomial in elevation); CASA users append them to FITS-IDI with `casavlbitools` (`append_tsys`, `append_gc`); at mm also opacity | medium: a parser and two Jones terms; oracle CASA `gencal` and `applycal` |
| Closure phases and amplitudes | gauge-free invariants for imaging and for checks; a non-redundant set and its covariance | small on top of C1's closure arm |
| Sparse-uv imaging | few stations, holes in uv: CLEAN with self-calibration (DIFMAP), RML on closures (eht-imaging, SMILI), Bayesian (Comrade.jl) | large; depends on DF5's RML arm |
| mm-wave atmosphere | coherence times of seconds at 230 GHz, opacity, rapid phase variation; rPICARD handles it for EHT and GMVA | large; only if EHT-class data is in scope |
| FITS-IDI and UVFITS | the EVN archive ships FITS-IDI; EHT releases are UVFITS (CyVerse, 10 s averaging) | medium; precedent in DF-IO (each format judged by its own tool) |
| Mixed feed bases | MeerKAT has linear H/V feeds, most EVN stations circular; JIVE's fringe plot for MeerKAT shows the H/V-to-R/L relabelling at the correlator; PolConvert (Martí-Vidal et al. 2016) converts linear to circular for ALMA in the EHT (from the literature, not rechecked here) | medium; where rang's C6 work (Xf, Df on linear feeds) is closest |
| A tied-array station | MeerKAT joins as one coherent beam of up to 64 dishes; its amplitude scale comes from the phase-up gains, not from a single-dish Tsys (SARAO's proposed ANTAB with DPFU = 1) | small for rang; the beam is formed upstream |

## 4. Tools and papers, 2023-2026

| Tool | What | Language, status (checked here?) | Role for ra-ng |
| --- | --- | --- | --- |
| CASA `fringefit` | Schwab-Cotton two-stage fringe fit; multiband; dispersive delay; developed by JIVE with NRAO support | C++/Python; in casatasks 6.7 (docs checked); rang pins 6.7.6.14 | **primary oracle** for piece 1; algorithm details (FFT padding, SNR formula) are not in the docs: read `FringeJones.cc` before freezing |
| AIPS FRING | the reference fringe fitter | Fortran; NRAO still recommends AIPS for most VLBA work (checked); in 2018 FRING was 2-4× faster than CASA single-core (checked) | second oracle and the speed bar; not installed on the host |
| rPICARD | CASA-based pipeline (Janssen et al. 2019): FITS-IDI or MS in; EVN, VLBA, GMVA, EHT calibrated | Python on CASA; current version **not checked** (no 2024-2026 release found) | the EHT and GMVA recipe to copy later, as CARACal is for MeerKAT |
| EHT-HOPS | the EHT's other pipeline (fourfit); the 2018 M87 release has both HOPS and rPICARD products (checked) | C | a second view on EHT data only |
| Obit | Cotton's package; MeerKAT imaging (MFImage) is V5's oracle | C/Python; VLBI tasks **not checked** | V5 installs it; whether its VLBI side is usable is open |
| DIFMAP | hybrid mapping: CLEAN plus self-calibration on sparse uv | C; status **not checked** | the classical sparse-uv imaging baseline |
| eht-imaging (ehtim) | RML imaging on visibilities, closure phases and log closure amplitudes (Chael et al. 2018), simulation of synthetic data; JOSS paper 2024 (cited, not read) | Python | **oracle for closure imaging** and for synthetic EHT data |
| SMILI | sparse modelling (ℓ1, TV, TSV) for VLBI; v0.2.0 on Zenodo; nothing newer found | Python/Fortran; activity after 2019 **not checked** | second RML oracle |
| Comrade.jl | Bayesian, differentiable VLBI modelling; Enzyme autodiff; used for M87* 2017-2021 variability (2025) and 3C 279 (2026); VLBISkyRegularizers.jl adds RML (JuliaCon 2025) | Julia | the Bayesian reference; JAX-like route already exists, in Julia |
| DoG-HiT, kine | wavelet imaging (Müller & Lobanov 2022); kine is unsupervised-ML imaging, "in prep." in the 2026 3C 279 paper | Python | no oracle use until published |
| Deep learning on closure invariants | arXiv:2411.12233 (2024) | Python | a reading item, not an oracle |
| frinZ | a fringe-fitting tool published as a Rust crate (docs.rs, 4.6.1, a 2025 build date) | Rust; scope and validation **not checked** | the only Rust VLBI code found; inspect before writing ours |
| GPU work | VOLKS2 (GPU fringe fitting for transient search, 2021), ZAGROS (GPU forward modelling, 2020); no JAX VLBI work found | – | no current GPU fringe fitter to compare against |

## 5. Public data

| Data | What | Size | Access | Use |
| --- | --- | --- | --- | --- |
| EVN N14C3 | network monitoring, 2014-10-22, 5 GHz (4934.7-5046.2 MHz), 8 spw × 32 ch × 500 kHz, RR and LL used; EF as refant; 1848+283 and J1640+3946 calibrators, 3C345 and J1849+3024 targets; up to 13 stations named (the tutorial's count is inconsistent: 12 in `listobs`) | `n14c3_1_1.IDI1` and `.IDI2`, reported as 1.9 and 0.9 GB (secondary source; sizes **not checked**) | public, EVN archive, with ANTAB and UVFLG; the CASA tutorial gives the `fringefit` calls (single-band on 1848+283, 13:53:20-13:54:20, `solint='inf'`, `minsnr=50`; multiband on two fields, `solint='60s'`, `combine='spw'`, `minsnr=30`) | **piece 1, real-data arm** |
| EVN RSM07 | 3 h continuum with phase referencing, the 2025 JIVE school data | not checked | public, archive | held-out set for piece 1 |
| EVN with MeerKAT, J0123+3044 | first regular EVN run with MeerKAT (announced 2025-06-08): 12 h, MeerKAT for 4 h; centimetre wavelengths; the run's own setup was not found (SARAO's interim VLBI mode in October 2024 was L band, 2 × 32 MHz, one boresight beam) | not found | project code, date and public status **not found**; EVN's proprietary period is 12 months from distribution (6 for ToO, none for short observations since 2020-12-01), so it may be public by now | the MeerKAT-specific arm; owner decision 4 |
| EHT 2017 M87* and Sgr A* | calibrated UVFITS (2019, 2022); polarimetric sets (CyVerse dates April 2026 are metadata refreshes of 2017 data) | per set, not checked | public, CyVerse | closure imaging, later |
| EHT 2018 M87* | 3 days, 4 bands, HOPS and rPICARD, 10 s, 32 IFs averaged, Stokes I in RR and LL; DOI 10.25739/epm5-r371; PDDL | `EHTC_M872018_uvfits.tgz`, size not checked | public | closure imaging, later |

No raw (pre-fringe-fit) EHT data was found as a public release on CyVerse; the
EHT policy puts raw data in the ALMA archive a year after validation (not
checked further).

## 6. Options weighed

- **Fringe fitting first (recommended).** It extends C2b and C2c; its oracle is
  already installed; truth can be simulated; N14C3 is public and small; every
  later VLBI piece (amplitude calibration, imaging, MeerKAT in the EVN) needs it.
  Risk: no novelty. A port with oracles is not a contribution (AGENTS.md). A
  later claim would need, for example, FRING-level accuracy faster than AIPS, or
  better detections at low SNR against CASA at matched cost.
- **Closure imaging first.** The likelier route to a scientific gain (RML on
  closures is where recent EHT work is), but it rests on DF5's RML arm, which is
  not built, and imager-against-imager comparisons need synthetic truth
  (ehtim can make it). Second piece.
- **A priori amplitude calibration first.** Small, but useless alone: it needs
  fringe-fitted data to show anything.
- **FITS-IDI reader first.** A format port with no science; CASA `importfitsidi`
  covers piece 1.

## 7. Piece 1: fringe fitting (proposed protocol outline, to freeze later)

**Scope.** Per station, polarisation and solution interval: phase, delay, rate;
single-band (per spw) and multiband (`combine='spw'`, `concatspws=True`);
`minsnr`, `zerorates`, `delaywindow`, `ratewindow`, `paramactive`,
`globalsolve`, `niter`; `corrdepflags` and `corrcomb='none'`. Dispersive delay
off (`paramactive` default). A CASA `Fringe Jones` table out, which `applycal`
reads. Rust kernel; Python as `rang.cal_fringe` beside `cal_delay`.

**Before freezing.** Read CASA's `FringeJones.cc` (the FFT padding, peak
interpolation, SNR formula and least-squares weights are not in the docs), as
C2b read `KJones.cc`. Inspect frinZ.

**Data.**

1. *T (simulated truth):* rang's writer in N14C3's layout (its station
   positions, 8 × 32 × 500 kHz, its scan list), a point source, per-station
   delays uniform in ±200 ns, rates in ±20 ps/s, phases uniform, seeds
   recorded; noise-free twins and three SNR levels (5, 20, 100 per baseline per
   interval). Rate means a phase linear in time, which A1's generator does not
   yet make.
2. *C (CASA on real data):* N14C3 imported by CASA 6.7.6.14, ANTAB and UVFLG
   applied as in the tutorial, the tutorial's two `fringefit` calls, then the
   same with `globalsolve=False`.
3. *H (held out):* RSM07, opened only after T and C pass.

**Tolerances (proposed; gauge-free, as C2b learned).** Delays and rates are
compared as station differences or centred on the station mean, never as raw
referenced values, since every referenced value shares the reference station's
error. Units are the resolution cells `1/BW` (BW of the solved band: 16 MHz
single-band, 128 MHz multiband, so 62.5 and 7.8 ns) and `1/(ν T)` (at 5 GHz,
T = 60 s: 3.3 ps/s).

| Arm | Quantity | Proposed bound |
| --- | --- | --- |
| T, twins | delay, rate, phase | ≤ 1e-6 of the cell; phase ≤ 1e-4 rad |
| T, noisy | z = error / formal error, gauge-free | median \|z\| in [0.55, 0.80] and std(z) in [0.8, 1.25] per SNR level; detections: every station at SNR ≥ 7, false detections on a noise-only twin within the rate `minsnr` implies (to be derived from the SNR formula) |
| C, against `fringefit` | delay, rate | median ≤ 0.01 cell, p95 ≤ 0.05 cell |
| C | phase | median ≤ 0.5°, p95 ≤ 2° |
| C | which solutions pass `minsnr` | identical, except where CASA's SNR is within 2 % of `minsnr` |
| C | SNR | within 5 % |
| C, apply | `applycal` with rang's table against CASA's table | C2b's class C (float32 epsilons, flags exact) |
| all | time and peak memory | recorded against `fringefit` (and FRING if installed) at -j1 and -j16; no bound, no claim |

**Cost (estimate, from C2b's logged runs).** C2b's whole oracle cycle ran in
minutes per run (CASA K calls 1-3 s each, rang 0.06-9 s per case, the A1
generator 5 s per set; [tool-timings.md](tool-timings.md)). Piece 1 is larger:
a 2-D FFT, a global solve, multiband and a new table type. Proposed: four to
six agent sessions (protocol and `FringeJones.cc` reading 1; simulator 1;
kernel and table 1-2; runs and write-up 1-2); about 1,500 lines of Rust and
Python; heavy-lock time under an hour; download about 2.8 GB plus RSM07, kept
in `D:\rang\vlbi`, never in the repository.

## 8. Owner decisions (at most five)

1. **Whether and when.** Start after LOFAR (the vision's order), after v0.2.0
   only, or not at all.
2. **First piece.** Fringe fitting against CASA `fringefit` (recommended) or
   closure imaging against eht-imaging (which first needs DF5's RML arm).
3. **AIPS.** Install AIPS in WSL for FRING as a second oracle and the speed bar,
   or use CASA alone.
4. **MeerKAT data and formats.** Ask JIVE or SARAO (the owner's contacts) for
   the 2025 MeerKAT-EVN run or a short MeerKAT test observation (no proprietary
   period), and whether rang reads FITS-IDI and ANTAB natively (DF-IO's rule)
   or goes through CASA `importfitsidi`.
5. **Where it lives.** VLBI in `rang-core` behind the telescope boundary, or a
   separate package (the vision says later packages split off rang-core); the
   AGENTS.md rule "do not generalise before a second telescope's data and
   oracle exist" applies.

## 9. Sources (read 2026-11-11)

- van Bemmel et al. 2022, CASA on the fringe, PASP, arXiv:2210.02275; JIVE 2018 proceedings, PoS 344, 079.
- Janssen et al. 2019, rPICARD, A&A, arXiv:1902.01749.
- CASA `fringefit` documentation, casadocs v6.7.0.
- JIVE CASA tutorial with N14C3 (jive.eu/~small/FringeFitting, now 404) and the DARA CASA 6 version (jb.man.ac.uk/DARA/unit4); `jive-vlbi/casa-vlbi` (casavlbitools).
- EVN archive (archive.jive.nl, N14C3_141022); EVN data access policy (evlbi.org).
- JIVE press release 2025-06-08 and Chalmers news 2025-06-13 (MeerKAT in the EVN, J0123+3044).
- M. Gouws (SARAO), Developing a VLBI observation mode for MeerKAT, IVTW 2024-10-21 (Haystack).
- EHT data on CyVerse: 2017 M87* and Sgr A*, polarised sets, 2018 M87* (DOI 10.25739/epm5-r371).
- Chael et al. 2018, closure-only imaging, arXiv:1803.07088; eht-imaging JOSS 2024 (cited, not read).
- SMILI documentation and Zenodo records; Comrade.jl docs, JuliaCon 2025 (VLBISkyRegularizers.jl); M87* variability 2017-2021, arXiv:2509.24593; 3C 279 with the EHT, arXiv:2607.16104; arXiv:2411.12233.
- frinZ on docs.rs; VOLKS2, arXiv:2108.05602; ZAGROS, arXiv:2005.12655.
- Schwab & Cotton 1983 (global fringe fitting) and Martí-Vidal et al. 2016 (PolConvert): from the literature, not reread.
