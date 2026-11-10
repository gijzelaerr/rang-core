# Rang: plan to finish GeMClean and rang-core

Status, 2026-11-05: **confirmed by the owner, in execution; nothing here is measured yet.** Owner's answer, verbatim: "1 include polirasation. 2 yes. 3 after
measuring. Execute plan, good luck". So polarisation is on the finish line, multiscale is in, and the coarse-gridding default is decided after measuring. Written at main `94f95b2`. Open questions and earlier tasks stay in [big-plan.md](big-plan.md).

## 1. The finish line

rang-core is done at **v0.2.0**, when all of this holds:

1. **One command.** After `pip install rang-core`, `rang-core run config.yaml my.ms` flags, calibrates, applies, images with GeMClean and
   self-calibrates a MeerKAT L-band Measurement Set that was not used in development, in full polarisation.
2. **Written back.** `FLAG` (with a backup of the original flags), `CORRECTED_DATA`, `MODEL_DATA`, calibration tables, FITS images and a receipt.
   CASA, WSClean and QuartiCal can read them.
3. **Each stage against an oracle.** Flags against Tricolour, solutions against CASA and QuartiCal, images against WSClean, each within a
   tolerance written before the run.
4. **The whole run against the state of the art.** One comparison with CARACal's shipped MeerKAT strategy on the same data, reporting
   image quality, flux, wall time and memory, whatever the result.
5. **Usable by someone else.** A tutorial goes from a Measurement Set to an image, unsupported data is refused with a clear error, and CI runs a
   small end-to-end job on all five wheels.

These are parity gates, so meeting them makes rang-core a working toolchain. It claims no novelty, and the novelty rule in `AGENTS.md` is unchanged.

**GeMClean is done** when it installs with the wheel, handles the 2:1 L-band frequency range, masks, multiscale and Stokes I, Q, U and V, writes `MODEL_DATA`,
fits the pilot at 512 channels in 24 GB, and has its defaults settled.

**Outside the finish line unless the owner adds them:**

- Direction-dependent calibration and facets (DF3 onwards).
- UHF and S band.
- The full 7 h ESO 137 track (about 126 GB to fetch and, roughly, 110 GB of memory).
- GPU imaging in GeMClean.
- DF5 with an RML arm, and B1 with an external catalogue.
- The trained flagger: it waits for Landman's reply (section 6).

## 2. Where it stands

| Area | Exists | Missing |
| --- | --- | --- |
| Reading | MS reader, zarr, MVFv4 through katdal (`python/rang/meerkat.py`) | Whole-array chunking in a general command |
| Flagging | Tricolour strategies (`core_flag.flag_rows`), flag versions (`formats/flagversions.py`) | A command for any MS; it is now `examples/run_core_flags.py` |
| Calibration | The `complex` solve only (`core.solve_complex`), flux standards (`fluxstd.py`), component predictor (`predict_components`) | Delay, bandpass, phase-only and amplitude terms, chains of terms, interpolation, apply ([core-phase2.md](core-phase2.md): "Not ported") |
| Writing | Table writer (`core_ms_write.py`), calibration tables (`formats/caltable.py`) | Use by the stages |
| Imaging | `gemclean`: Stokes I, one flat-spectrum term, weighting, restored image | Wheel and Python entry, channels and spectral fit, masks, multiscale, `MODEL_DATA` |
| Command line | `rang-core STAGE VERB`, which replays and compares the research chains | Commands for a user's own data; one config |

## 3. Tasks

All proposed. **Heavy** tasks run one at a time under `flock ~/.rang-heavy.lock`. Every task writes its tolerance into a note before
its first comparison and records runs, seeds and timings as usual.

### A. Acceptance data and protocol (first, because every gate depends on it)

| ID | Task | Done when | Heavy | After |
| --- | --- | --- | --- | --- |
| A0 | **Done 2026-11-05** ([a0-acceptance.md](a0-acceptance.md)). Choose the data and freeze the acceptance protocol | A frozen note names the development and acceptance data, tolerances and the CARACal settings | no | owner confirms section 1 |
| A1 | **Done 2026-11-06** ([a1-simtruth.md](a1-simtruth.md)). Simulated truth: known sky, gains and RFI through the rang writer | The chain's input exists, with its seed and provenance | yes | A0 |

Settled by A0 ([a0-acceptance.md](a0-acceptance.md)): E1 simulated truth; E2-A ESO137 ms1 (Stokes I, raw phases); E2-B LUNO scans 17-20 (full polarisation, processed); E2-N native, open. Ben Hugo's set is LUNO's own scheduling block and adds native flags, not independence. The candidates as first listed:

- **Ben Hugo's native data (L3):** the right test, but it is not here and its date is outside our control.
- **LUNO 1934−638 and 1830−211:** calibrate on one and check the transfer on the other. Available now, but processed data.
- **A public archive observation through `rang-core meerkat fetch`:** real calibrator and target scans, if a suitable and permitted one exists.

Polarisation needs more: a polarised calibrator (3C286 or 3C138) and an unpolarised one (1934−638) in the same observation. A0 must say whether any candidate has them.

The fallback is simulated truth plus LUNO, labelled as weaker. The final gate then stays open for native data, and v0.2.0 says so.

### G. GeMClean

| ID | Task | Oracle | Done when | Heavy | After |
| --- | --- | --- | --- | --- | --- |
| G1 | **Done 2026-11-05:** kept, off by default ([gemclean-speed.md](gemclean-speed.md), G1 section). Finish the interleaved `-beam-band` test | Itself, flag off | The flag is kept or removed, on the measured saving | yes, idle host | none |
| G2 | **Done 2026-11-06** ([g2-memory.md](g2-memory.md)): pilot-512 19.7 GB (coarse 15.7), so E2-A and E3-A image at 512 channels; 2.0-3.6x WSClean. Memory, currently 3-5 × WSClean's | Current images | The pilot fits 24 GB at 512 channels; images identical or within tolerance | yes | G1 |
| G3 | **Done 2026-11-06** ([g3-spectral.md](g3-spectral.md)): one held-out MFS bound failed (H1s); joined-channel memory on the pilot not measured (for G7). `-channels-out`, `-join-channels`, spectral fit | WSClean on simulated spectral skies, then held-out skies | Flux and spectral index within tolerance on skies not used to build it | yes | G2 |
| G4 | **Done 2026-11-09** ([g4-masks.md](g4-masks.md)): selection, mask confinement and multiscale finishing met, held-out H included; restoring beam, X2, M3 and the Högbom automatic mask not met as frozen. Masks (FITS, automatic), Gaussian taper, uv range | WSClean | Same selection and mask behaviour within tolerance | no | G3 |
| G5 | **Done 2026-11-08** ([g5-multiscale.md](g5-multiscale.md)): every gate met; pilot flux −0.12 % of WSClean's; memory 2-3 × WSClean's. Multiscale (owner: in) | WSClean `-multiscale` on S2 and an extended real field | Extended flux within tolerance; false flux and cycles reported | yes | G3 |
| G6 | **Done 2026-11-07** ([g6-predict.md](g6-predict.md)); C5 uses `image.write_model: true` or `rang.core_model.write_model_data`. Write `MODEL_DATA`; a predict mode | WSClean `-predict`; casacore read-back | Agreement within tolerance on S1-S3 and the pilot | yes | G3, W1 |
| G9 | **Done 2026-11-09** ([g9-stokes.md](g9-stokes.md)): held-out C, D, E not met as frozen; C′, D′ pass. Stokes I, Q, U, V and joined polarisations (`-pol`, `-join-polarizations`) | WSClean on simulated polarised skies | Each Stokes image within tolerance; no I-to-QUV leakage from the imager beyond WSClean's | yes | G3 |
| G7 | **Done 2026-11-10** ([g7-defaults.md](g7-defaults.md)): coarse gridding (1e-4, single precision) adopted as the default (owner decision 3 answered, revertible); restoring beam fitted as WSClean 3.7's binary (G9 decision 6 and G4 decision 2 answered); G8 measures speed on the wheel with the new defaults. Settle defaults, including coarse gridding, on the real pilot (owner: after measuring); the gridder plane group (about 1.1 GB on S1) is not bit-neutral and needs a class B rule of its own (G2) | WSClean at matched accuracy | Defaults chosen and recorded; figures single-core and threaded | yes, idle host | G2, G3, G5, G9 |
| G8 | **Done 2026-11-10** ([g8-wheel.md](g8-wheel.md)) but for the five-platform CI read: identity and speed on the wheel met; owner decision 4 answered with a recommendation (keep the name). In the wheel: extension binding and a `gemclean` console script, not a second binary | Source build | `pip install` runs it on all five platforms; FITS identical to the source build on S1; speed measured **on the wheel**, because current figures come from the fat-LTO `gemclean` profile | yes | G7 |

### C. Calibration

| ID | Task | Oracle | Done when | Heavy | After |
| --- | --- | --- | --- | --- | --- |
| C1 | **Done 2026-11-05** ([c1-calibration-chain.md](c1-calibration-chain.md)). Specify the chain from CARACal's `crosscal_worker.py` sequence ([o-casa.md](o-casa.md)) | none | A frozen list of terms and order, with reasons for anything left out | no | A0 |
| C2 | C2a **done 2026-11-06** ([c2a-gain.md](c2a-gain.md)): G; C2b **done 2026-11-06** ([c2b-delay.md](c2b-delay.md)): K as QuartiCal's `delay`, equal to CASA only with a G pre-applied; C2c **done 2026-11-06** ([c2c-bandpass.md](c2c-bandpass.md)): K as `delay_and_offset` with rang's offset start, B with `fillgaps`, the chain K, G, B equal to CASA's on the composite (later tasks gate a chain on the composite or pre-apply the oracle's earlier tables; `holdout256` is a fresh held-out set); C2d **done 2026-11-06** ([c2d-fluxscale.md](c2d-fluxscale.md)): `fluxscale` and bootstrap, classes B and C met, P and T not as frozen; C2e (the terms in `rang-core calibrate`) open. Gain, delay and bandpass in CARACal's order K, G, B, phase-only terms, chains of terms, and F with `fluxscale` (C1 steps 3-6), in Rust | QuartiCal and CASA | Each term within tolerance on the slice and simulated truth | yes | C1 |
| C2e | **Done 2026-11-06** ([c2e-calibrate.md](c2e-calibrate.md)): gates 1, 2, 4 met; E2-B still refused for C6 and `refant: auto`. Wire K, G, B, F (bootstrap) and CARACal's A step (flag the corrected calibrators) into `rang-core calibrate` in C1's order, with secondary models from `fluxscale`; re-point the refusals that still name C2a-C2d | C2a-C2d's own results; CASA's chain on the slice and A1 | `rang-core calibrate` equals the library chain bit for bit; E2's calibrate stage no longer refused | yes | C2c, C2d, W4 |
| C3 | C3a **done 2026-11-06** ([c3a-models.md](c3a-models.md)); the polarised model stays with C7a. Calibrator models (`setjy`), using `fluxstd` and the predictor; the flux-scale transfer moved to C2 | CASA `setjy` | Model visibilities within tolerance on 1934−638 | no | C1 |
| C4 | **Done 2026-11-06** apart from owner decisions: C4a ([c4a-apply.md](c4a-apply.md)), the in-memory kernel; C4b ([c4b-apply-ms.md](c4b-apply-ms.md)), MS write-back, `calwt` weights and field maps (frozen run failed, held-out run passed after three post-hoc ports). Interpolate and apply solutions, writing `CORRECTED_DATA` | CASA `applycal` | Corrected data within tolerance; flags propagated as CASA does | no | C2, W1 |
| C6 | **Done 2026-11-06** ([c6-polterms.md](c6-polterms.md)) as library functions: P, T, C met; class B and chain not met as frozen (vanishing cross hands, Df flags in RFI channels, a CASA-dropped Gpol interval). Polarisation terms in C1's order: Gpol, cross-hand delay (KCROSS), cross-hand phase (Xf), leakage (Df); parallactic angle throughout | CASA `gaincal` and `polcal` | Each term within tolerance on simulated truth and a polarisation calibrator | yes | C2, C3 |
| C6w | **Done 2026-11-06** ([c6w-polwire.md](c6w-polwire.md)): bit-identical to the library; polcal source within 0.003° of CASA's chain. Wire Gpol, KCROSS, Xf, Df and P into `rang-core calibrate` and `apply` as proposed in [c6-polterms.md](c6-polterms.md) ("For the coordinator"), after W3's chunking lands in `core_pipeline` | C6's library chain | `rang-core calibrate` equals C6's library chain bit for bit on `poldx`; apply equals `cal_pol.apply`; E2-B's polcal no longer refused | yes | C6, C2e, W3 |
| E0 | **Done 2026-11-07** ([e0-refant-extend.md](e0-refant-extend.md)): E2-B's flag, calibrate and apply validate; gates 1 and 2 met after labelled post-hoc additions. E2-B's last refusals: `refant: auto` (port CARACal's `get_refant`) and `extendflags` (CASA `flagdata` mode `extend` after the polcal solves, as CARACal runs it) | CARACal's source; CASA `flagdata` | E2-B validates; refant equals CARACal's choice on the slice and A1; extended flags equal CASA's | no | C2e, C6w |
| C7 | C7a **done 2026-11-06** ([c7a-polmodels.md](c7a-polmodels.md)): polarised models, tabular path 0 ulps, `spix` path 2 ulps; C7b **done 2026-11-06** ([c6w-polwire.md](c6w-polwire.md)): applied end to end, χ within 0.003° of CASA's chain and 0.4-0.6° of the truth. Apply the polarisation solutions; polarised calibrator models | CASA `applycal`; published 3C286 or 3C138 values | Calibrated Q and U, fractional polarisation and angle within tolerance | no | C4, C6 |
| C5 | **Done 2026-11-08** ([c5-selfcal.md](c5-selfcal.md)): solves equal QuartiCal's; full-loop truth gate not met (model absorption), follow-up C5b. Self-calibration from `MODEL_DATA`: phase, then amplitude by default, and CARACal's delay form (`Fslope`) as an option | QuartiCal (a substitute for CubiCal); simulated truth | Gains recovered on simulated truth; solution intervals configurable | yes | C4, G6 |
| C5b | **Done 2026-11-09** ([c5b-selfcal-masks.md](c5b-selfcal-masks.md)): per-image masks and cut-offs implemented; T2 not met on the held-out cases (masks, an oracle mask included, do not remove C5's model absorption); owner decides on a rounds or intervals follow-up. Per-round masks and image settings in `rang-core selfcal` (CARACal's `cleanmask_thr`, `clean_cutoff`, auto-masking from G4) | C5's truth sets | C5's T2 gate met on its held-out cases | yes | C5, G4 |

### W. Write-back and general commands

| ID | Task | Oracle | Done when | Heavy | After |
| --- | --- | --- | --- | --- | --- |
| W1 | **Done 2026-11-06** ([w1-writeback.md](w1-writeback.md)). Write-back to an existing MS: add columns, write `FLAG`, back up flags | casacore, CASA, WSClean read-back | The tools read every column; a failed run leaves the original flags recoverable | no | none |
| W2 | **Done 2026-11-06** ([w2-commands.md](w2-commands.md)); W2b (models and apply in the commands) done with C4b. One config schema; `rang-core flag`, `calibrate`, `image`, `selfcal` and `run`; resume; receipts | none | Each runs on an MS outside the repository; research stages move under `rang-core research` | no | W1 |
| W3 | **Done 2026-11-06** ([w3-chunking.md](w3-chunking.md)): bit-identical chunked and unchunked; 8 GiB default limit, whole-array 4096-channel set at 3.0-5.0 GiB; K, G, B, A, F unchunked (W3b). Chunking by time and row for whole-array data | Unchunked output | Same result chunked and unchunked within tolerance, with a stated memory limit | yes | W2 |
| W3b | **Done 2026-11-07** ([w3b-chainchunks.md](w3b-chainchunks.md)): bit-identical chunked and unchunked on the slice, A1, poldx, held-out polholdout; whole-array K, G, B at 3.35 / 1.66 GiB. Chunk C2e's K, G, B, A and F (and C6w's polarisation terms) through `core_chunks.read_rows` within `core_chunks.budget`, replacing the preflight refusal above the limit | The unchunked chain | Bit-identical chunked and unchunked on the slice, A1 and the whole-array set; peaks within the limit | no | W3, C2e |
| W4 | **Done 2026-11-06** ([w4-unsupported.md](w4-unsupported.md)): 27 of 28 cases as frozen; uniform imaging weights, scan selection and unwritten WEIGHT_SPECTRUM cells moved to W6. Unsupported data: multiple spectral windows and fields, autocorrelations, missing weights, other correlations | Written cases | Each case works or is refused with a clear message | no | W2 |
| W5 | **Done 2026-11-06** ([w5-stimela.md](w5-stimela.md)); `core-actions` and `core-imaging` stay research recipes (archive replays). The Stimela recipes call the new commands | Recipes run | One recipe runs the chain; research recipes are marked as such | no | W2 |
| W6 | **Done 2026-11-07** ([w6-imaging-inputs.md](w6-imaging-inputs.md)). Imaging inputs left by W4: scan selection in `rang-core image` (a gemclean scan selection or a split), `data.weights: uniform` for imaging (a gemclean option to ignore the MS weights, not a write into the user's MS), and gemclean falling back to WEIGHT when WEIGHT_SPECTRUM cells are unwritten | W4's cases; WSClean on the same selection | E2-A and E2-B configurations image their selected scans; W4's ws-undefined case images; images otherwise byte-identical | no | W4, G3 |

### E. End to end, and release

| ID | Task | Done when | Heavy | After |
| --- | --- | --- | --- | --- |
| E1 | The whole chain on simulated truth | **Run 2026-11-09** ([e1-chain.md](e1-chain.md)): no gate met as frozen; shared with CASA (K flags, one delay), known limit (selfcal), rang-only K class-B miss on m32, the rest not established; owner decisions (section 7 item 27) before a rerun after C5b and G4. Gates of A0 pass, or the failure is recorded and fixed | yes | C5, W3, A1 |
| E2 | The whole chain on the acceptance data, unseen | Gates of A0 reported as frozen, on E2-A and E2-B; E2-N open | yes | E1, G8 |
| E3 | Against CARACal on the same data | Report with quality, flux, wall time and memory, any outcome | yes, idle host | E2 |
| E4 | Tutorial, command reference and landing pages; a small end-to-end job in CI | A reader goes from MS to image following the docs alone | no | E2 |
| E5 | Final review, as W4 did for 0.1.0, and fixes | No release-blocking finding | no | E3, E4 |
| E6 | v0.2.0 candidate: the owner tags and publishes | Wheels green on the tagged commit; `pip install` verified | no | E5 |

## 4. Order

**The critical path:** A0 → C1 → C2 → C4 → C6 → C7 → C5 → E1 → E2 → E3 → E5 → E6. C4 also needs W1, and C5 needs G6.

C1 splits C4: its Rust apply kernel (C4a, C1 step 2) comes before C2, because C2 pre-applies tables; the write-back part (C4b) stays after C2 and W1. C1's section 6 lists the thirteen steps in order.

**Parallel where it is light:** W1, W2, W4, C1, C3 and G4 can run alongside others. Everything marked heavy takes turns, so the heavy tasks in
practice form one queue: G1, G2, G3, C2, G6, G5, G9, C6, G7, C5, G8, then E1 to E3. Timing runs need the machine to themselves.

**Gridding and calibration feed each other** only at G6 and C5, so the G and C streams can advance separately until then.

## 5. Size (an estimate, not a measurement)

29 tasks. The big plan merged about 37 in several days, but many of those were ports with an oracle to match. C2, G3 and G5 are new
algorithms with new failure modes. Polarisation adds three tasks and one more data requirement. **Expect two to four weeks of agent time, plus API limits** (the weekly limit stopped work once, on 2026-10-31).
The largest risks are outside that count:

- **Parallactic angle.** CASA's `parang=True` angle differs from rang's frame by up to 0.5° near the zenith (A1, section 7.2); C6 must choose a convention, and either uses half of E1's 1° budget on χ. CASA's K pivot is the band centre (A1, 7.1), which C2 must follow.
- **Native data.** Without it E2 and E3 can only finish on weaker data. LUNO's DATA is pre-phased, so KCROSS and Xf are near zero there; A1 must carry them.
- **E3 can come out badly.** A worse result than CARACal would be recorded, then fixed or stated in the release; it would not be reworded.
- **The unexplained floor.** The pilot's floor is 40-60 × thermal in all imagers, for a reason not found. It may limit what E2 can show.

## 6. Waiting, and off the finish line

- **Landman.** He replied on 2026-11-06 (supervised fast network fine; weights per observatory and band; separate calibrator and target strategies). F2 ran 2026-11-06/07 ([f2-flagger.md](f2-flagger.md)): outcome F in both classes; not a second flagger for `rang-core flag`. Continuing needs a new protocol (owner decision). Earlier: nothing started on the flagger until he replied. The non-TV arms (Z, R, F-RES) would need
  a new frozen protocol. If one succeeds, it joins through `rang-core flag` as a second flagger; it is not a condition of v0.2.0.
- **Upstream replies, Tricolour 0.5.0 and QuartiCal 0.2.8** (RV2, RV3) continue as they arrive. A new upstream release may move an oracle.
- **The paper and the WSClean report** remain owner decisions ([clean-overview.md](clean-overview.md)).

## 7. Owner decisions

1. **Finish line:** confirmed 2026-11-05, with polarisation added.
2. **Multiscale (G5):** in.
3. **Coarse gridding as GeMClean's default (G7):** decided after the measurements on the real pilot; until then the default stays at 1e-6.
4. **The GeMClean name:** a proper clash check as part of G8, before the name reaches PyPI as a console script.
5. **C1's three decisions** (owner, 2026-11-05: "Do what you think is best"): self-calibration defaults to phase then amplitude, with the delay form also built and E3 stating the difference; the Tricolour port replaces tfcrop inside crosscal, with E3 reporting flagged fractions per step; K is estimated by FFT then Gauss-Newton.
6. **A0's four decisions, open:** accept the split legs with E2-N open; the native-data source (a different block from Ben Hugo, a SARAO archive token, or open); the fetches to `D:\rang`; and whether the polarisation claim may rest on processed LUNO data plus simulation.
7. **C4a's two decisions** (coordinator's provisional choice, open to the owner): accept the 1-2 ulp residual on random-phase per-channel B tables (33 eps, 4e-6 relative) and state it in C4's acceptance; copy CASA's Df substitution (unflagged cross hands corrected with −1 leakages) rather than flagging both cross hands, for parity with the oracle.
8. **A1's two decisions, open:** the parallactic-angle convention (rang's geodetic, ICRS north, or CASA's geocentric, apparent north; the coordinator proposes CASA's in C6); and a second truth with a reference antenna whose d_x ≠ 0.
9. **C2a's three decisions** (coordinator's provisional choice, open to the owner): the solution-TIME failure (up to 0.054 s, 0.41 s with `combine`) stands, and TIME is reported, not gated, in later tasks until CASA's centroid weighting is ported; `combine='scan'` keeps QuartiCal's estimator, with CASA-style pre-averaging as a possible option; SIGMA-based weights when tables are pre-applied, as CASA does, with the weight source in the receipt.
10. **C4b's five decisions** (open; [c4b-apply-ms.md](c4b-apply-ms.md) section 11): whether the complex term keeps CASA's general-Jones flag rule; whether complex gains are ever transferred to a target (refused now, naming C2a); who owns the `data.weights: uniform` imaging refusal that still names C4 (the coordinator proposes W4); models written on the primary fields only; the end-to-end and E2 solve settings (`freqint: 16` did not converge, `freqint: 1` did).
11. **C2b's four decisions** ([c2b-delay.md](c2b-delay.md) section 9): the K model (coordinator's provisional choice: QuartiCal's `delay_and_offset`, a delay plus a free phase per antenna, ported in C2c, since CARACal solves K before any G and `delay` misses CASA by 0.06-1.3 ns without one); CASA's K solution-TIME rule (reported, not gated, as for G); the delay error, low by 1.5-2 (open: accept, or rescale weights by pre-applied amplitudes); the gauge-free (centred) class T bias test for later C tasks (provisionally adopted). C2c's decisions ([c2c-bandpass.md](c2c-bandpass.md) section 9): the K model is implemented as proposed; rang's offset start, which is not QuartiCal's (provisionally accepted); K offsets not written to the K table, G absorbs them (provisionally kept, to be stated wherever a K table is applied alone); later chains gated on the composite or with the oracle's earlier tables pre-applied (provisionally: both, per task); B's TIME and INTERVAL differ from CASA's (reported, not gated).
12. **W4's three decisions** ([w4-unsupported.md](w4-unsupported.md) section 8): uniform imaging weights (coordinator's provisional choice: a gemclean option, in W6, so the user's weights are never overwritten); gemclean's fallback to WEIGHT for unwritten WEIGHT_SPECTRUM cells (provisionally yes, in W6); autocorrelations left out of the solve (provisional). C4b's decision 3 (who owns the uniform-weights refusal) is answered: W4, then W5.
13. **C2d's four decisions** ([c2d-fluxscale.md](c2d-fluxscale.md) section 12): the fit-error gate at `fitorder=2` (provisionally: report, not gate, as CASA's χ² cancels); the noisy class T gate based on the scatter of per-antenna ratios (provisionally adopted for later tasks); a spectral index on one window (provisionally none, as CASA); the command wiring (task C2e, added by the coordinator).
14. **C7a's five decisions** ([c7a-polmodels.md](c7a-polmodels.md) section 10): copy CASA's channel-0 LSRK conversion on the one-term `spix` path (provisionally yes, for parity); refuse `polindex` without `polangle` (provisionally yes); accept the 2-ulp residual or port casacore's frame conversion (provisionally accept); ship Taylor & Legodi's table (open); lift the polcal-field model refusal so a 3C286 polcal model can be written (needed by C6 and C7b; provisionally yes, in C2e or C6). Also open: `core_ms` fails reading FEED's string-array `POLARIZATION_TYPE` (a garbage-offset read, not a refusal); `rang.simtruth` references RM to λ = 0, CASA to `reffreq`.
15. **C2e's decisions** ([c2e-calibrate.md](c2e-calibrate.md) section 9): `refant: auto` (coordinator's provisional choice: port CARACal's `get_refant` as part of E2's preparation); `data.weights: uniform` in the solves as unit weights where a solve reads WEIGHT_SPECTRUM (provisional, not checked against CASA); the A step's 63 % flagging of A1's corrected calibrators (for E1); options still refused with no owner (`solnorm: true`, `calmode: a`, `gainfield` on pre-applied tables, complex terms mixed with K, G, B, A, F). C7a's decision 5 is answered: the C2d refusal of models on secondary and polcal fields is lifted; C6 writes and uses the 3C286 polcal model.
16. **C6's five decisions** ([c6-polterms.md](c6-polterms.md) section 10): the parallactic-angle frame (provisionally CASA's; answers A1's item 8 provisionally); a truth with d_x ≠ 0 on the refant (provisionally yes, `poldx`); Df on 68-88 % RFI-flagged channels (keep rang's solutions or add a data-fraction flag rule to match CASA; open, before C6w freezes defaults); KCROSS combining scans rather than per scan as CARACal does (open); CASA's KCROSS estimator bias (keep it or add a Gauss-Newton refinement; open). Also: C2e's `holdout128` and C6's `poldx` share seeds 20261146-49 (different designs, both kept; neither is held out for the other). C7 should use C7a's `calmodels` and `rang.cal_pol.apply`.
17. **W3's four decisions** ([w3-chunking.md](w3-chunking.md) section 8): the 8 GiB default `data.memory_limit_gb` (provisionally yes, so a 16 GB machine runs every stage); `data.chunk_rows` becomes a cap on every chunk (provisionally yes); neither key in the stage hash, so stages finished before W3 need `--force` once (provisionally yes); the exact two-pass replay of the stop test rather than QuartiCal-style independent chunks (provisional). Also: W3's `w3` design shares seeds 20261136-39 with C2c's `holdout256` (different designs; both kept).
18. **W5's decisions** ([w5-stimela.md](w5-stimela.md)): keep `core-actions` and `core-imaging` as marked research recipes in `recipes/` (provisionally yes; moving them to `recipes/research/` is open); accept that Stimela passes the MS as a relative path (provisionally yes; outputs are identical). New recipes must start with `# rang-recipe: research` or `user`.
19. **C6w's decisions** ([c6w-polwire.md](c6w-polwire.md) section 7): Df on RFI-heavy channels keeps rang's solutions (`min_data_fraction` exists, off; CASA has no such rule); KCROSS per scan as CARACal (`combine: scan` available); CASA's KCROSS estimator (`refined` available); `extendflags` not ported (task E0); `feed_angle_rotation` applied in memory only, FEED not rewritten, so CASA reading the MS would apply a different P where FEED holds 0 (provisional). These answer C6's decisions 3-5 provisionally.
20. **G3's decisions** ([g3-spectral.md](g3-spectral.md)): `-fit-spectral-log-pol` refused (its non-linear fitter not ported); `average_channels` as rang's own option (Stokes I weighted means after the channel range, CASA the oracle); the joined loop keeps GeMClean's minor step, values and fit follow WSClean; `-deconvolution-channels`, squared joining and channel division by frequencies refused, and with several output channels also the certified rule, `-gram-operator`, `-floor-iterations`, `-audit`; WSClean's default MF weighting; grids released per channel in multi-channel runs (all provisional).
21. **E0's five decisions** ([e0-refant-extend.md](e0-refant-extend.md) section 7): port CARACal's code, not its comment (refant by name); stop the calibrate stage when no antenna qualifies (CARACal passes an empty refant to CASA); both steps work within `data.scans`; the new keys change the calibrate stage hash once (`--force`); the frozen casacore observatory table (all provisional). For E2 and E3: CARACal's own `refant: auto` crashes on an MS with a FIELD row without data (msutils 1.2.0).
22. **W3b's decisions** ([w3b-chainchunks.md](w3b-chainchunks.md) section 7): read blocks are not capped by `data.chunk_rows`; the counted kernels and `*_trace` functions are public; the A step's summary gains a `chunking` record and its `flag_sha256` comes from FLAG re-read after the write (same bytes) (all provisional). Channel chunks re-read the whole interval per chunk (slow: 30-52 min arms); a sliced read in the reader would fix it.
23. **G6's and W6's decisions** ([g6-predict.md](g6-predict.md), [w6-imaging-inputs.md](w6-imaging-inputs.md)): gemclean writes the model column by default as WSClean does (scripts imaging a shared MS must pass `-no-update-model-required`); an added column starts at zero (WSClean), not clearcal's unity; an existing model column of another shape is refused where WSClean resets it; `image.write_model` stays false by default in rang-core; WriteBack copies DATA's `UNIT` for a non-default model column, the binary does not; `-scans` and `-unit-weights` are rang's own names (for G8's clash check). Item 12's decisions 1 and 2 are implemented as provisionally chosen (all provisional).
24. **G5's decisions** ([g5-multiscale.md](g5-multiscale.md) section 8): without `-mgain`, `-multiscale` uses GeMClean's measured rule (gated runs used 0.8); a `-multiscale-*` option without `-multiscale` is refused (WSClean ignores it); linear shape convolutions with an exact residual after each sub-minor loop, so convolution padding and the non-fast sub-minor loop are refused; two 2 GB caches; the run ends after a cycle at the final threshold, as WSClean (all provisional).
25. **C5's decisions** ([c5-selfcal.md](c5-selfcal.md) section 9): accept the loop now with its model-absorption limit stated, C5b after G4 (coordinator's provisional choice); Sd starts at zero delay; QuartiCal's per-channel trend flags kept for Sd; flags accumulate over rounds and an invalid gain flags all four correlations; selfcal solutions only as QuartiCal stores, no CASA tables; `complex` terms and `refant: auto` refused in selfcal (all provisional).
26. **G9's decisions** ([g9-stokes.md](g9-stokes.md) section 8): follow WSClean's binary (linear sum) rather than its help text (open: a squared rule, or an upstream report); XY, YX, circular feeds and `-link-polarizations` refused; beams shared only where gridding weights are bit-identical; WSClean's header-weight run-order copied; the frozen C/D or the post-hoc C′/D′ (open); GeMClean's fitted restoring beam (10.7″ against WSClean's 14.3″, also on main's I path) goes to G7/G8; model writing, multiscale and selfcal with polarisations other than I refused as follow-ups (all provisional).
27. **E1's decisions** ([e1-chain.md](e1-chain.md) section 9, all open): refant m000 (loses five antennas to CASA's K rule) or `auto` (brings back the leakage-gauge error); raise `image.niter` (100,000 too small for the selfcal images); add a CASA-chain arm on m32 and the twin so each failure splits into CASA-too and rang-only, rerun after C5b and G4; fix and validate the image scorer's convention on the control first; probe the 530 flag cells that differ from Tricolour (native against Linux build).
28. **G4's decisions** ([g4-masks.md](g4-masks.md), all open): whether the Linux G2/G3 identity hashes stay the reference now that native Windows builds of main differ in every file, dirty image included (likely UCRT against glibc maths, not investigated), or native-against-native becomes the rule; the restoring-beam fit (G9 finding 6) goes to G7/G8 or a task of its own; whether to relax X2's 1 % bound on sigma per iteration (sequences diverge after iteration 2, as in G5); whether the Högbom automatic mask finishing early is acceptable (C5b uses multiscale, which matched); the MFS `WSCNVIS`/`WSCVWSUM` convention (WSClean one channel, GeMClean the total).
29. **C5b's decisions** ([c5b-selfcal-masks.md](c5b-selfcal-masks.md) section 8, open): accept C5's model-absorption limit (masks do not lift it) or a follow-up on rounds, longer first intervals or a phase-only first round; the new keys default to empty, CARACal's values proposed for E2-A's configuration; multiscale gated, Högbom (CARACal's default) reported only; FITS masks used without regridding; the selfcal stage hash changes once (existing runs need `--force`).
30. **G7's decisions** ([g7-defaults.md](g7-defaults.md) section 13): coarse gridding adopted under the pre-written rule, which also sets selfcal's MODEL_DATA prediction to 1e-4 (WSClean's own default), revertible; GeMClean copies WSClean's one-quadrant beam fit because the binary is the oracle (whole box would give 13.58" x 9.47" on S1 against WSClean's 13.88" x 8.34"; open: an upstream report to schaapcommon, a whole-box option); -beam-band, -tau-min and the plane group stay options, off; image hashes from before G7 no longer carry over.
31. **G8's decisions** ([g8-wheel.md](g8-wheel.md) section 15): keep the name `gemclean` (no clash on PyPI, crates.io, RubyGems, npm, conda-forge, Homebrew, Debian, GitHub; recommended); CPU baseline stays x86-64 (provisional; x86-64-v3 is 1.5 % faster at -j16 but refuses CPUs without AVX2/FMA); `image.gemclean: auto` runs the installed extension only, no PATH or core/target search (provisional); on Linux the extension uses gemclean's huge-page allocator for all allocations (provisional); open: the sdist does not build because `core/src/gemclean/sim.rs` includes `data/meerkat.itrf.txt`, which the sdist leaves out (already so on main; follow-up needed).
