# V7: LOFAR in ra-ng, a scoping note

Task V7 of [vision.md](vision.md). Written 2026-11-11 on branch
`claude/silly-cannon-dddff1` from local `main` `3eab67c` (V6 merged;
`origin/main` was `c2fe7cc`).

**Status: proposed; nothing built or measured.** Every plan, tolerance and cost
below is a proposal. Facts about other tools and data are from the sources in
section 9, read on 2026-11-11; several come from search summaries or abstracts
only, and the text says so, or says "not checked", where a fact was not
confirmed. The owner decides whether and when this starts; the vision puts
LOFAR after MeerKAT and before VLBI ([v6-vlbi-scope.md](v6-vlbi-scope.md)).

## 1. Recommendation in one paragraph

The first LOFAR piece is **the direction-independent ionospheric solve on a
calibrator**: per station and solution interval, DP3 DDECal's `scalarphase`,
`diagonal`, `tec` and `rotation+diagonal` modes (TEC as a phase ∝ 1/ν,
differential Faraday rotation as a rotation angle), in Rust, with H5parm out.
Oracle: **DP3 6.6.0 DDECal**, already in rang's formats oracle image
(`rang-formats-oracle:20261030`, [dfio-formats.md](dfio-formats.md)), with
both solvers reading the **same model column** (`ddecal.modeldatacolumns`), so
the solver is tested apart from the station beam and the predict. Data: rang's
own simulated truth in the layout of the second set, then **Edler et al.'s
public simulated LOFAR 2.0 HBA calibrator** (3C196, 3.1 GB Dysco-compressed,
CC BY 4.0, no account), whose known corruptions ship as an H5parm that rang's
reader already reads. Dysco is decompressed on the oracle side by DP3, as V6
lets CASA `importfitsidi` stand in for a FITS-IDI reader. It is LOFAR-specific
(TEC and Faraday rotation are the ionosphere at 120-170 MHz) and not DF4, which
is the multi-direction scalar solve against killMS on a MeerKAT field
(section 6).

## 2. What carries over from rang-core

| rang-core part | Where | Use for LOFAR | Gap |
| --- | --- | --- | --- |
| MS reader and writer | `core/src/ms.rs`, `ms_write.rs`, E4-E6 | LINC, DP3 and Rapthor all read and write MSs | `ms.rs` reads Standard, Incremental, TiledShape and TiledColumn storage managers and refuses others: **DyscoStMan** is refused, and LTA data recorded after 2018 is Dysco-compressed (LoTSS DR2 paper) |
| W4's refusals | [w4-unsupported.md](w4-unsupported.md) | the boundary stays: unsupported layouts are refused before anything is written | LOFAR delivers one MS per subband (LINC concatenates to bands); rang-core commands take one MS with one data description: multi-MS input is new; whether Edler's MSs have one spectral window **not checked** |
| Gain solvers G, K, B | C2a-C2c, `core/src/cal/` | DDECal's `scalar`, `diagonal` and `scalarphase` are the same per-station least-squares problem with DDECal's step size (0.2), tolerance (1e-5) and `maxiter` (50) | TEC (one real parameter per station, phase ∝ 1/ν across the band), rotation angle, DDECal's solver (`directionsolve` default), `smoothnessconstraint`, `uvlambdamin` |
| Polarisation terms | C6 (Xf, Df, KCROSS on linear feeds) | LOFAR dipoles are linear (XX, XY, YX, YY), as MeerKAT's; LINC's calibrator pipeline aligns the polarisations and solves Faraday rotation | differential Faraday rotation as its own term; LINC's polalign is not C6's KCROSS (not compared) |
| Flagging | core-d (Tricolour port), A-FLAG (`core/src/sumthreshold.rs` against AOFlagger 3.5) | AOFlagger is LOFAR's flagger (in DP3 and the observatory's preprocessing) | AOFlagger's LOFAR strategy against rang's SumThreshold (A-FLAG used MeerKAT controls only); AOFlagger's LOFAR strategy file **not read** |
| Formats layer | `python/rang/formats/` (DF-IO) | H5parm is LOFAR's solution format; killMS solutions and DicoModel are ddf-pipeline's; BBS sky models are DP3's | `h5parm.py` writes `amplitude` and `phase` soltabs only: `tec`, `rotation` and many-direction soltabs are not written; DDECal facet solutions were not exercised in DF-IO |
| Imaging | GeMClean, wgridder (DF1-DF2), G-series | the exact w-gridder suits LOFAR's wide fields (HBA beam several degrees across at 144 MHz) | no A-terms, no station-beam correction, no facets (DF3 not built), no IDG; LoTSS imaging is DDFacet (ddf-pipeline) or WSClean with facets (Rapthor) |
| Simulated truth with seeds | [a1-simtruth.md](a1-simtruth.md) | truth sets with injected TEC and rotation | LOFAR station layout, 1/ν phase, rotation; A1 makes MeerKAT layouts only |
| Telescope boundary | `python/rang/meerkat.py` | LOFAR specifics go behind a sibling module (proposed `rang.lofar`), not into the core | none until LOFAR data and an oracle are in hand (AGENTS.md) |

## 3. What is new

| Item | What it is | Oracle | Size of the job (proposed estimate) |
| --- | --- | --- | --- |
| Ionospheric DI terms | TEC (phase = −8.448e9 · TEC / ν, TECU and Hz, DP3's convention from memory, **to be read** in DP3's source) and differential Faraday rotation per station; LINC separates clock and TEC on the calibrator | DP3 DDECal (`tec`, `tecandphase`, `rotation+diagonal`); losoto for the H5parm | **piece 1** (section 7) |
| Station beams | HBA tiles (16 dipoles, analogue tile beam) and LBA dipoles, phased into station beams; element models Hamaker, OSKAR and LOBEs (LBA) | EveryBeam (0.7.0 takes the element model from the MS; 0.8.0 added LOBEs coefficients for all LBA stations; PyPI 0.9.1 Linux wheels, [ecosystem-survey.md](ecosystem-survey.md)) | large if ported; medium as an optional dependency (owner decision 3) |
| Model prediction with beam | DP3 `predict` from a BBS sky model through EveryBeam | DP3 `predict`, WSClean `-predict` | medium after the beam |
| Direction-dependent calibration | many directions, smooth TEC screens; DDECal `directionsolve`, `directioniterative`, `hybrid`, `lbfgs`; killMS CohJones/KAFCA; IDGCAL's smooth basis (van der Tol et al. 2026) | DDECal, killMS (both installed), facetselfcal (no licence: oracle only) | large; shared with DF4 |
| Facet imaging | DDFacet (ddf-pipeline, LoTSS DR2/DR3), WSClean facets with H5parm (`-apply-facet-solutions`) | DDFacet 1.0.0.0, WSClean 3.7 | large; DF3 |
| Demixing | subtracting A-team sources (Cas A, Cyg A, Tau A, Vir A) seen in the station sidelobes, by solving and subtracting their predicted visibilities before averaging | DP3 `demixer`; A-team models (LINC ships some, **not checked**) | medium; needs predict with beam |
| Data volume and Dysco | LoTSS: archive at 1 s and 16 channels per 0.195 MHz subband, DI processing averages by about 64 to 8 s and 2 channels; about 8.8 TB per 8 h observation (two pointings); DR3 used 18.6 PB; Dysco lossy compression (Offringa 2016) | DP3 (decompress), casacore with the Dysco storage manager (read) | medium for a Dysco reader in `ms.rs`; streaming and chunking already in W3 |
| International stations | baselines to about 2,000 km for 0.3″ (LOFAR-VLBI pipeline: delay calibration on an in-field calibrator, Morabito et al. 2022, **not reread**); its fringe-fitting needs overlap V6's first piece | LOFAR-VLBI pipeline, facetselfcal | large; after V6 |
| LOFAR 2.0 | one White Rabbit clock for Dutch stations (drift from tens of ns to about 0.1 ns over 8 h at the first five stations, URSI 2024 paper); all LBA dipoles and HBA tiles digitised (3 × 2 × 48 inputs); 32 of 38 stations verified in February 2026; a science programme from 2027 (ERIC 2025 report); simultaneous LBA and HBA **not confirmed** (all from search summaries) | Edler et al.'s simulated LOFAR 2.0 sets; ASTRON commissioning data (owner decision 4) | the clock term may shrink to nothing on Dutch baselines, which would simplify LINC's clock-TEC separation (proposed reading, not checked) |

## 4. Tools and papers, 2023-2026

| Tool | What | Language, status (checked here?) | Role for ra-ng |
| --- | --- | --- | --- |
| DP3 | streaming preprocessing: flag (AOFlagger), average, demix, predict, DDECal, applycal; H5parm out | C++, GPL-3.0; v6.6 2026-05-07 on git.astron.nl, PyPI 6.6.0 Linux wheels; in `rang-formats-oracle:20261030` since DF-IO (checked then) | **primary oracle** for piece 1; DDECal mode list and defaults read in the current docs |
| EveryBeam | beam library for LOFAR, MWA, SKA-Low, OSKAR | C++, GPL-3.0-or-later; changelog 0.7.0 (2025-01) to 0.8.x (2026-02); PyPI 0.9.1 2026-10-21, Linux wheels only (survey) | oracle for the station beam; dependency only if the owner accepts Linux-only |
| LINC | LOFAR initial calibration: calibrator (polalign, Faraday rotation, bandpass, clock/TEC) and target (DI phase on a sky model) | CWL over DP3, losoto, AOFlagger; version **not found** | the LOFAR recipe to copy, as CARACal is for MeerKAT |
| Rapthor | LOFAR DD pipeline after LINC: facets with WSClean and DDECal | Python/CWL; v2.1 2025-12-04 (changelog: better calibration strategy, about 2× faster than 2.0); PyPI 2.1.post1 | the DD baseline for LOFAR |
| ddf-pipeline | LoTSS's DD pipeline (killMS and DDFacet) behind DR2 and DR3 | Python; version **not checked** | the survey baseline; DDFacet and killMS already oracles here |
| facetselfcal | DI and DD self-calibration over DP3 and WSClean, used for LOFAR-VLBI | Python; no licence file (survey) | oracle only |
| LOFAR-VLBI pipeline | international-station calibration (Morabito et al. 2022) | Python/CWL; status **not checked** | after V6 |
| losoto | H5parm inspection, smoothing, clock/TEC separation | Python, GPL-3.0-or-later; 2.7.1 2026-04-29 | H5parm oracle (DF-IO already uses it) |
| AOFlagger | RFI flagging; LOFAR's default | C++; 3.5 (A-FLAG) | flagging oracle, LOFAR strategy not yet run |
| Dysco | lossy MS compression (Offringa 2016) | C++ casacore storage manager, GPL-3 (from memory, **not checked**) | decompress via DP3 for piece 1; a native reader later |
| WSClean, IDG | imager with facets and A-terms (IDG on GPU) | C++; WSClean 3.7 installed | imaging oracle |
| IDGCAL | DD calibration in a smooth image-domain basis instead of facets (van der Tol et al. 2026, arXiv:2602.06002; follow-up arXiv:2608.10762) | abstracts only | the state of the art a later DD claim must meet |
| Papers | Brackenhoff et al. 2025 (beam-weighted smoothness in DDECal on HBA, arXiv:2504.02483); de Jong et al. 2025 (automated DD selfcal, factor 4-6 cost, arXiv:2508.12115); Edler et al. 2021 (ionospheric calibration for LOFAR 2.0, simulated, arXiv:2105.04636, abstract only); Shimwell et al. 2022 (LoTSS DR2) and the LoTSS DR3 paper (2026) | – | the comparison points |

## 5. Public data

| Data | What | Size | Access | Use |
| --- | --- | --- | --- | --- |
| Edler et al., simulated LOFAR 2.0 (DOI 10.25592/uhhfdm.8587, 2021-01-29) | raw simulated, Dysco-compressed MSs: HBA and LBA calibrator (3C196) and target; the input corruptions as H5parm (`corruptions_calibrator.h5`, `corruptions_target.h5`); BBS sky models; simulator, stations and frequency setup **not stated on the record** | HBA cal 3.1 GB, LBA cal 56.4 GB, HBA target 149.6 GB, LBA target 56.4 GB, H5parms 21 MB and 0.83 GB | public, CC BY 4.0, University of Hamburg repository, no account | **piece 1, arm R** (HBA cal); the LBA cal as held-out (section 7) |
| LoTSS DR2 | DI-calibrated, averaged visibilities and DD solutions per pointing, facet layouts, images, catalogues (DOI 10.25606/SURF.LoTSS-DR2) | per pointing **not checked** | lofar-surveys.org, ASTRON VO, SURF Data Repository; whether a login is needed **not checked** | a real-data arm after piece 1 |
| LoTSS DR3 | 88 % of the northern sky, 13,667,877 sources, median 92 µJy/beam; 12,950 h, 18.6 PB, observed 2014-05-23 to 2024-08-19; uv data and calibration solutions stated public (A&A 707, A198, 2026) | – | access route for the uv data **not found** | later; the DD baseline at survey scale |
| LTA | the raw and pipeline archive | – | metadata public without an account; data public after a 1-year proprietary period; staging and download need an account with LTA privileges from SDC Operations (SDC helpdesk); the old stager was replaced by StageIT | any real calibrator observation (owner decision 4) |
| DP3 and LINC test sets | DP3's unit tests use small MSs (`tNDPPP-generic.MS`); LINC's CI jobs live in `test_jobs` | download location **not found** | – | ask ASTRON (owner decision 4) |

## 6. Options weighed

- **DI ionospheric solve against DDECal (recommended).** LOFAR-specific
  physics (TEC, Faraday rotation) on top of solvers rang already has; the oracle
  is installed; public data with known truth needs no account; the model column
  keeps the beam and predict out of the first comparison. Risk: no novelty.
  Matching DDECal is a port. A later claim would need, for example, better TEC
  recovery against Edler's truth at matched cost, or DDECal's accuracy at
  materially lower cost.
- **Multi-direction solve against DDECal.** This is DF4 in
  [big-plan.md](big-plan.md) (scalar CohJones, killMS oracle, DDECal as a
  second reference) on a simulated MeerKAT field. Doing it under V7 would
  duplicate DF4; the LOFAR arm is Edler's HBA target (149.6 GB) once DF4 and
  piece 1 exist.
- **Station beam against EveryBeam.** Needed for any real prediction, but a
  port of a beam library is large and has no science until a solver or imager
  uses it; EveryBeam itself is the oracle and could be the dependency (owner
  decision 3). Second piece.
- **Dysco reader.** A format port with no science; DP3 decompresses for piece
  1. Needed before rang-core reads LTA data natively (DF-IO's rule:
  owner decision 5).
- **LINC calibrator chain.** Piece 1 is its solver core; the chain (polalign,
  bandpass, clock/TEC separation in losoto) follows once piece 1 passes.
- **Demixing against DP3.** Needs predict with the beam; later.

Two survey verdicts change for LOFAR: EveryBeam and Dysco (both IGNORE for
MeerKAT in [ecosystem-survey.md](ecosystem-survey.md)) become an oracle and a
format respectively.

## 7. Piece 1: DI ionospheric solve (proposed protocol outline, to freeze later)

**Scope.** One direction; per station and interval: `scalarphase`, `diagonal`,
`tec` and `rotation+diagonal`; DDECal's `solint`, `nchan`, `stepsize`,
`tolerance`, `maxiter`, `uvlambdamin`, `smoothnessconstraint` off then on;
`modeldatacolumns` for the model. H5parm out with `phase`, `amplitude`,
`tec` and `rotation` soltabs as DDECal writes them (`h5parm.py` extended), read
by losoto and applied by DP3 `applycal`. Rust kernel; Python as
`rang.cal_iono` behind a `rang.lofar` boundary module.

**Before freezing.** Read DDECal's solver source for each mode (the TEC
constant, `approximatetec`, the rotation parametrisation, the convergence test
and the weights), as C2b read `KJones.cc`. Read Edler et al.'s paper for the
simulator and corruptions. Check that DP3 6.6.0's PyPI wheel decompresses
Dysco and that the MS has one spectral window.

**Data.**

1. *T (simulated truth):* rang's writer in the Edler HBA calibrator's layout
   (its ANTENNA table, channels and times), a 3C196 point model, per-station
   TEC differences uniform in ±0.5 TECU, rotation angles in ±0.5 rad,
   amplitudes 1 ± 10 %, seeds recorded; noise-free twins and SNR levels 5, 20,
   100 per station per interval.
2. *R (Edler HBA calibrator):* decompressed by DP3, model column predicted by
   DP3 from `skymodel_3c196.sky` with EveryBeam, then DDECal and rang on the
   same column; truth from `corruptions_calibrator.h5`.
3. *H (held out):* the Edler LBA calibrator (56.4 GB, stronger ionosphere),
   opened only after T and R pass; or an LTA calibrator if the owner prefers
   real data and an account is granted.

**Tolerances (proposed; gauge-free).** Phases and TEC are compared as station
differences or centred on the station mean, never as values referenced to one
station. Iterates are not compared; converged solutions and costs are.

| Arm | Quantity | Proposed bound |
| --- | --- | --- |
| T, twins | TEC, rotation, phase, amplitude | TEC ≤ 1e-6 TECU, phase and rotation ≤ 1e-4 rad, amplitude ≤ 1e-6 relative |
| T, noisy | z = error / formal error (rang's formal error from the Jacobian) | median \|z\| in [0.55, 0.80] and std(z) in [0.8, 1.25] per SNR level ≥ 20 |
| T and R, against DDECal | cost (weighted χ²) at convergence per interval | rang ≤ DDECal × (1 + 1e-3) |
| R, against DDECal | gauge-free phase, rotation | median ≤ 0.5°, p95 ≤ 2° |
| R, against DDECal | gauge-free TEC | median ≤ 1e-3 TECU, p95 ≤ 5e-3 TECU |
| R, against truth | median gauge-free TEC and phase error | rang ≤ DDECal's error × 1.05 |
| R, apply | DP3 `applycal` with rang's H5parm against DDECal's | DF-IO's H5parm bound (4.0e-7 measured there) |
| all | time and peak memory | recorded against DDECal at -j1 and -j16; no bound, no claim |

**Cost (estimate).** DF-IO's DP3 `applycal` ran in 1.3 s on 470 k cells;
DDECal on a 3.1 GB set should take minutes (not measured). Proposed: four to
six agent sessions (DDECal source and protocol 1; simulator 1; kernels and
H5parm soltabs 1-2; runs and write-up 1-2); about 1,200 lines of Rust and
Python; heavy-lock time under an hour; download 3.1 GB (plus 56.4 GB for H),
decompressed size **not known** (Dysco ratios are several-fold), kept in
`D:\rang\lofar`, never in the repository.

## 8. Owner decisions (at most five)

1. **Whether and when.** After v0.2.0, alongside it as a light task, or not
   at all; and LOFAR before V6's VLBI, as the vision orders it.
2. **First piece.** The DI ionospheric solve against DDECal (recommended), or
   the station beam against EveryBeam first.
3. **EveryBeam.** Depend on it (Linux wheels only, against the five-platform
   rule), port the LOFAR element models to Rust, or keep it oracle-only.
4. **ASTRON contacts.** Ask:
   - for a small public LOFAR calibrator observation (HBA, Dysco, with LINC's
     outputs) and a LOFAR 2.0 commissioning set, without an LTA account;
   - for an LTA account with staging rights for ra-ng's tests (SDC helpdesk);
   - which DP3 and LINC versions LINC and Rapthor pin, and whether DDECal's
     `tec` and `rotation+diagonal` code paths are the ones LoTSS uses;
   - whether the LOFAR 2.0 single clock removes the clock term on Dutch
     baselines, and when simultaneous LBA and HBA observing is offered;
   - whether EveryBeam would ship Windows and macOS wheels, or accept that
     ra-ng ports its LOFAR models.
5. **Where it lives and Dysco.** LOFAR in `rang-core` behind a `rang.lofar`
   boundary or a separate package; DP3 decompression on the oracle side only,
   or a native Dysco reader in `ms.rs` (DF-IO's rule).

## 9. Sources (read 2026-11-11)

- DP3 DDECal documentation (dp3.readthedocs.io, latest): modes, `modeldatacolumns`, `solveralgorithm`, defaults; DP3 `CalType.h` (doxygen) for the full mode enum.
- EveryBeam changelog and LOBEs page (everybeam.readthedocs.io).
- Rapthor changelog v2.1 and data preparation pages (rapthor.readthedocs.io); LINC docs (linc.readthedocs.io) and repository tree (git.astron.nl/RD/LINC), from search summaries.
- Edler, de Gasperin, Rafferty: dataset record DOI 10.25592/uhhfdm.8587 (fdr.uni-hamburg.de/record/8587, opened); paper arXiv:2105.04636 (title only).
- Shimwell et al. 2022, LoTSS DR2, arXiv:2202.11733; LoTSS DR3 paper, A&A 707, A198, arXiv:2602.15949 (abstracts and search summaries).
- LTA (lta.lofar.eu) and ASTRON's LOFAR data archive page, LOFAR newsletter March 2025: from search summaries.
- LOFAR 2.0: LOFAR newsletter February 2026, LOFAR ERIC Activity Report 2025, URSI AT-AP-RASC 2024 paper 1247, ASTRON 2023 slides: from search summaries, not opened.
- rang notes: [dfio-formats.md](dfio-formats.md), [ddfacet-feasibility.md](ddfacet-feasibility.md), [ecosystem-survey.md](ecosystem-survey.md), [literature-2024-2026.md](literature-2024-2026.md) (IDGCAL, Brackenhoff, de Jong), [a-flag-aoflagger.md](a-flag-aoflagger.md), [w4-unsupported.md](w4-unsupported.md).
- Offringa 2016 (Dysco) and Morabito et al. 2022 (LOFAR-VLBI): from the literature, not reread.
