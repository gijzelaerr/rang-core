# V1: time-series science, scoping note

Task V1 of [vision.md](vision.md) section 7, written 2026-11-11.
**Status: proposed. Nothing here is built.** The only things measured are
the probes in section 7: one ESO137 metadata chunk, the RATT bucket listing,
the WSClean option text and the DStools licence. Every tolerance in section 5
is a proposal. The build protocol will freeze them, with a dated commit, before
any code exists. No novelty claim.

## 0. The answer in brief

1. **First product (recommended): residual snapshot light curves.** These are
   per-integration (8 s) residual images from a calibrated MeerKAT L-band
   Measurement Set, with two outputs:
   - forced light curves at listed positions;
   - a blind list of snapshot candidates above a threshold.

   It is called **P1** below; a working command name is `rang-core lightcurve`.
   It serves long-period transients (LPTs), flare stars, eclipsing
   millisecond pulsars (MSPs) and the prompt-phase searches of gamma-ray burst
   (GRB) fields. It reuses rang-core's MS reader, calibration and apply chain,
   `-predict` and the wgridder, CPU and GPU.
2. **Beamformed filterbank work is deferred.** This covers dedispersion,
   single-pulse search and folding (FRBs, pulsar searches). No public MeerKAT
   filterbank data were found, and rang-core reuses almost nothing for it
   (section 3).
3. **Data.**
   - **Development:** ESO137 ms1 target (anonymous, CC BY 4.0, 8 s dumps,
     measured), with injected variable sources of known truth, plus A1-style
     simulations.
   - **Held-out:** the TRON ω Cen observation, SSV-20181107-FC-02 (8 s, 4096
     channels; public in the SARAO archive according to its paper). It needs
     the owner's SARAO token. This is owner decision 2.
4. **Oracles.**
   - **Gate:** WSClean 3.7 `-interval`/`-intervals-out` snapshots, and the
     exact DFT of the same residual visibilities.
   - **Literature only:** TRON's published ω Cen eclipse light curve, the
     science check. TRON's code was not found in public.
   - **Second, not gating:** DStools (MIT, CASA-based); it has not been run
     here.
5. **Cost, estimated, not measured:**
   - gridding one 8 s ESO137 dump (about 7.7 M visibilities, 1024², dirty
     image only) takes about 1.8 s on one thread, from DF2's measured
     0.45 µs per visibility;
   - one hour of data is 450 dumps, about 14 min on one thread;
   - input/output dominates: 147 GB per target hour at about 10 MB/s over
     HTTP, measured in core-g.

## 1. Survey, 2024-2026 (brief)

All papers were read through their arXiv abstract or HTML on 2026-11-11.
Details marked *(abstract)* were not checked in the full text.

| Work | What it does | Relevance |
| --- | --- | --- |
| TRON: Smirnov et al. 2025, MNRAS 538 L62, [arXiv:2501.09488](https://arxiv.org/abs/2501.09488) | Blind search of MeerKAT visibilities. Calibrated, self-calibrated, model-subtracted data; one undeconvolved snapshot per 8 s integration; peak finding at 7σ (6σ at the longest scales); smoothing from 15 to 960 s in ×2 steps; V, η, ξ_max. It detects eclipsing MSPs in ω Cen, Terzan 5 and 47 Tuc | The closest published analogue of P1. Its project IDs are public: SSV-20180615-FC-01, SSV-20181107-FC-02, SSV-20190605-FC-01. The data statement reads "publicly available via the SARAO archive". The code is not public (GitHub search, 2026-11-11) |
| PARROT: Smirnov et al. 2024, MNRAS 528 6517, [arXiv:2312.12165](https://arxiv.org/abs/2312.12165) | A scintillating pulsar, PSR J2009−2026 (P = 1.6 s, DM 21.2), found by dynamic imaging of MeerKAT L-band data taken on 2020-12-21 | Dynamic spectra made from imaging data. Its dump time and data statement were not found in the abstract |
| Fijma et al. 2024, MNRAS 528 6985, [arXiv:2306.16383](https://arxiv.org/abs/2306.16383) | Commensal MeerKAT image-plane search at 8 s, 128 s and 1 h (NGC 5068). No transients; at 8 s, 6.7e-5 deg⁻² at 56.4 mJy *(abstract)* | Gives the measured 8 s snapshot sensitivity in practice, against about 0.08 mJy thermal (section 4) |
| Chastain et al. 2025, ApJ 988 227, [arXiv:2412.02832](https://arxiv.org/abs/2412.02832) | Commensal MeerKAT L band in GRB and SN fields. 30 min and 8 s images, the band split in halves; one 8-16 s polarised event (likely a stellar flare) *(abstract)* | The GRB use of P1 |
| de Ruiter et al. 2025, Nat. Astron., [arXiv:2408.11536](https://arxiv.org/abs/2408.11536) | ILT J1101+5521, a 125.5 min LPT (a white dwarf and M dwarf binary), found in LoTSS 8 s snapshots | The LOFAR case for the same product |
| DStools ([askap-vast/dstools](https://github.com/askap-vast/dstools), MIT, last push 2026-05-04) | Dynamic spectra from visibilities: subtract a model, rotate to the target, average baselines. Used on MeerKAT for ASKAP J1448−6856 ([arXiv:2507.13453](https://arxiv.org/abs/2507.13453)) and in [arXiv:2406.12352](https://arxiv.org/abs/2406.12352) | A second oracle for P1's forced light curve; candidate P2. It has not been run here |
| TraP: Swinbank et al. 2015, [arXiv:1503.01526](https://arxiv.org/abs/1503.01526), [docs](https://transients-pipeline.readthedocs.io/) | The LOFAR transients pipeline: source association over image series; V, η | Definitions of the variability metrics |
| TransientX (Men & Barr 2024, [arXiv:2401.13834](https://arxiv.org/abs/2401.13834)), Heimdall, Heimdall++ ([arXiv:2512.00398](https://arxiv.org/abs/2512.00398)), PRESTO, PrestoZL, DSPSR | Single-pulse search on the CPU (TransientX) and the GPU (Heimdall: 2.66× from Heimdall++ *(abstract)*); search and folding (PRESTO, DSPSR) | Oracles for a later beamformed product; papers from 2025 run TransientX and Heimdall side by side as a cross-check |

[literature-2024-2026.md](literature-2024-2026.md) has no time-domain
entries. [ecosystem-survey.md](ecosystem-survey.md) marked the pulsar, SETI
and FRB packaging repositories as out of scope.

## 2. The options compared

| | P1 residual snapshot light curves (recommended) | Dynamic spectrum at one position (P2) | Beamformed: dedispersion, single pulse, folding |
| --- | --- | --- | --- |
| Science | LPTs (minutes), flares, eclipsing MSPs, GRB-field prompt searches; blind | Spectro-temporal structure of a known source (LPTs, scintillation, flares) | FRBs, pulsar discovery and timing (ms) |
| Public MeerKAT data | yes: ESO137 anonymous; TRON's sets through a SARAO token | as P1 | **none found**. MeerTRAP and TRAPUM filterbanks are not public; MPTA DR1 and the TRAPUM LMC release are folded PSRFITS, not filterbanks |
| Tight oracle | WSClean `-intervals-out`; exact DFT | DFT; DStools | PRESTO, Heimdall, TransientX, DSPSR |
| rang-core reuse | high | high | none beyond the GPU plumbing |
| New code | per-interval selection in the gridder path; forced photometry; peak search; variability metrics | phase rotation and baseline averaging (one pass) | readers (SIGPROC, PSRFITS), dedispersion (FDMT or tree), matched filter, folding |

P2 is nearly a by-product of P1, since both use the same residual
visibilities. It comes second because its tightest oracle, the DFT, is
already inside P1's gate T2.

**FRBs are out of reach at 8 s dumps.** A burst of 1 Jy ms averages to
0.125 mJy over 8 s. That is at the thermal noise and far below measured
snapshot noise, so FRB work needs the beamformed path.

## 3. What rang-core already has, and what P1 adds

| Need | Exists | Gap |
| --- | --- | --- |
| Read MS and MVF data | MS reader (`core/src/ms.rs`, [core-e-ms-reader.md](core-e-ms-reader.md)); MVFv4 loader ([mk1-katdal.md](mk1-katdal.md)); HTTP range fetch of zarr ([core-g-http-fetch.md](core-g-http-fetch.md)); chunking ([w3-chunking.md](w3-chunking.md)) | none |
| Calibrate and apply | `rang-core flag`, `calibrate`, `apply` ([w2-commands.md](w2-commands.md), [c4b-apply-ms.md](c4b-apply-ms.md)) | none for P1; gated by v0.2.0 |
| Deep model and subtraction | GeMClean, MODEL_DATA and `-predict` ([g6-predict.md](g6-predict.md)) | a residual column (DATA − MODEL) or the same subtraction on the fly |
| Snapshot gridding | wgridder at ducc0 speed ([df2-wgridder-speed.md](df2-wgridder-speed.md)); GPU w-stacking through wgpu, f64 ([x2-wgpu.md](x2-wgpu.md)); `-scans` selection ([w6-imaging-inputs.md](w6-imaging-inputs.md)) | **no per-interval selection**: GeMClean has no `-interval` or `-intervals-out` (grep, 2026-11-11). Snapshot batching for the GPU, unmeasured |
| Light curves, search, metrics | nothing | forced photometry (snapshot pixel and DFT), peak finding, V, η, ξ_max, time smoothing |
| Telescope boundary | `python/rang/meerkat.py`, W4 refusals | add a time-cadence refusal (for example, `INTERVAL` not constant within a scan) |

## 4. Cost and feasibility (estimates, not measured)

- **Data rate.** One ESO137 8 s dump has 1891 rows (61 antennas with
  autocorrelations; 850,950 rows over 450 dumps per hour). At 4096 channels
  that is 7.7 M visibilities per correlation product.
- **Gridding.** DF2 measured about 11 s for 23.8 M visibilities (dirty plus
  PSF, 1024², one thread), about 0.45 µs per visibility. A dirty-only
  snapshot then takes about 1.8 s, and one hour about 14 min on one thread.
  The estimate at 16 threads is 1-2 min. The image size for the full primary
  beam (about 4k²) moves the cost to the FFT, which is unmeasured. Averaging
  to 512 channels cuts the gridding about 8×; bandwidth smearing at 0.5°
  stays within tolerance (to check).
- **Input and output dominate.** One target hour is 147 GB (DATA 105 GB,
  WEIGHT_SPECTRUM 42 GB). At the 7-10 MB/s measured in core-g, that is 4-6 h
  to fetch; it goes in `D:\rang` (memory: C: is nearly full).
- **Noise.** The thermal noise of an 8 s snapshot is about 0.08 mJy. This is
  computed (SEFD 443 Jy, 500 MHz usable, 64 antennas, 2 polarisations), not
  measured. Fijma et al.'s practical 8 s figure of 56.4 mJy shows that
  sidelobes of the residual sky, not thermal noise, set the floor. The quality
  of the deep model therefore sets the product's reach.
- **Feasibility.** Every part is a known algorithm with an oracle. P1 is
  engineering, and its claim is parity with WSClean. A novelty claim would
  need a matched comparison with TRON or WSClean plus TraP at equal cost, for
  example deeper snapshot noise from better residuals; that is out of scope
  here.

## 5. Tolerances to freeze before any build (proposed)

| ID | Quantity | Reference | Proposed bound |
| --- | --- | --- | --- |
| T1 | Snapshot dirty image, per interval | WSClean 3.7 (`rang-wsclean-native:3.7`), same `-interval` or `-intervals-out`, natural weighting, `-gridder wgridder -wgridder-accuracy 1e-6 -no-min-grid-resolution`, `-pol I` | L∞ difference ≤ 1e-5 of the snapshot peak, on every interval (DF and G-task gridder parity is 1e-7-1e-6) |
| T2 | Forced light curve at a position | exact DFT of the same residual visibilities, weights and flags | ≤ 1e-3 σ_snap per point, where σ_snap is that interval's thermal σ from the weights |
| T3 | Injection recovery (A1-style simulation and ESO137 ms1 residuals) | injected point sources of known flux at 0.0°, 0.3° and 0.5°: square pulses of 8, 16 and 64 s and a 30 s pulse every 20 min; 5-50 σ_snap; apparent flux, no beam | flux bias \|mean\| ≤ 0.1 σ_snap; reduced χ² of the residual in [0.8, 1.2]; time stamps equal the MS TIME (centroid) of each interval exactly; every pulse ≥ 7σ recovered at its true interval |
| T4 | False alarms | noise-only simulation with ESO137's u-v coverage and weights | candidates ≥ 7σ in all snapshots ≤ 2× the Gaussian expectation, with its counting error. On real residuals the rate is reported, not gated |
| T5 | GPU against CPU | the CPU path | ≤ 1e-6 relative L∞ on snapshots, f64 (X2 reached 6e-7) |
| T6 | Cost | WSClean `-intervals-out` on the same hour at `-j 16` | wall time ≤ 1.5× and peak memory ≤ 1.5×, reported with the heavy lock held. Comparable cost, no novelty |
| T7 | Science check, held-out (not a numeric gate) | TRON's ω Cen eclipse light curve | eclipses at TRON's phases. Named before the run; looked at once |

The development and held-out split is to be named in the protocol before any
build:

- **Development:** A1-style simulations, and ESO137 ms1 target scan 2
  (MAIN_0, already read as the GeMClean pilot).
- **Held-out:** the TRON ω Cen observation (owner decision 2).
- **Not usable:** ESO137 ms1 target scan 10 (MAIN_4, E2-A) and its reserve MAIN_5, which
  [a0-acceptance.md](a0-acceptance.md) reserves.

## 6. LOFAR in mind

- **Same product:** ILT J1101+5521 was found in LoTSS 8 s snapshots, so P1 is
  the same product at LOFAR.
- **The difference:** at LOFAR the residuals need direction-dependent
  calibration (ionosphere, station beams), and the data are orders of
  magnitude larger.
- **Boundary:** keep P1 behind the MeerKAT boundary (vision.md section 2).
  Generalise it only when LOFAR data and a LOFAR oracle (the LoTSS snapshot
  products, TraP) are in hand.
- **Beamformed:** the LOFAR beamformed data in the LTA are the natural first
  public filterbank source if the beamformed path is opened; availability
  was not checked.

## 7. Probes run for this note (2026-11-11)

| Probe | Result |
| --- | --- |
| RATT bucket listing (anonymous) | ESO137/, G330/, LBAND_LUNO_*.zarr, LUNO/, MGCLS_HI/, MeerKATbeams/, … as in A0 |
| ESO137 `ms1_target.zarr/MAIN/MAIN_0/INTERVAL/0` (1.7 KB, blosc lz4) | 50,000 rows, all 7.99661697 s; shape 850,950 rows |
| WSClean 3.6 source, `main/commandline.cpp:360` | `-interval <start> <end>` and `-intervals-out <count>` exist; 3.7 is assumed to keep them (to confirm in the protocol) |
| GitHub API `askap-vast/dstools` | MIT, not archived, last push 2026-05-04 |
| GitHub search for TRON | no public repository |
| ATNF psrcat cone search (ESO137 field, Vela as control) | the query returned nothing for Vela either, so the form query failed. **Open: is there a known pulsar or variable in the ESO137 field?** |

## 8. Owner decisions

1. **Approve P1 as the first product**, with P2 (dynamic spectrum) next and
   the beamformed path deferred until public filterbank data and a reason are
   in hand.
2. **SARAO archive access.** A SARAO account and token for
   SSV-20181107-FC-02 (TRON ω Cen) as the held-out set. Data from 2018 may
   need restaging from tape, which can take weeks. Without it, the held-out
   set is an ESO137 hour that A0 does not reserve, and there is no real
   variable to check against.
3. **Disk and download.** About 150 GB per 4096-channel target hour on
   `D:\rang`. Alternatively, accept a 512-channel averaged copy (about 8×
   less) for development.
4. **Oracles.** WSClean 3.7 snapshots plus the DFT as the gate (T1, T2), with
   DStools as a non-gating cross-check. Or require DStools (CASA) to run on
   the WSL host as part of the gate.
5. **Schedule.** The P1 build is light. The T3, T4 and T6 runs are heavy and
   join the queue after E2 to E6 through `tools/heavy_lock.py`, or before
   them if the owner prefers.
