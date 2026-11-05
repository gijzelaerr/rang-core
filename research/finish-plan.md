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
| A1 | Simulated truth: known sky, gains and RFI through the rang writer | The chain's input exists, with its seed and provenance | yes | A0 |

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
| G2 | Memory, currently 3-5 × WSClean's | Current images | The pilot fits 24 GB at 512 channels; images identical or within tolerance | yes | G1 |
| G3 | `-channels-out`, `-join-channels`, spectral fit | WSClean on simulated spectral skies, then held-out skies | Flux and spectral index within tolerance on skies not used to build it | yes | G2 |
| G4 | Masks (FITS, automatic), Gaussian taper, uv range | WSClean | Same selection and mask behaviour within tolerance | no | G3 |
| G5 | Multiscale (owner: in) | WSClean `-multiscale` on S2 and an extended real field | Extended flux within tolerance; false flux and cycles reported | yes | G3 |
| G6 | Write `MODEL_DATA`; a predict mode | WSClean `-predict`; casacore read-back | Agreement within tolerance on S1-S3 and the pilot | yes | G3, W1 |
| G9 | Stokes I, Q, U, V and joined polarisations (`-pol`, `-join-polarizations`) | WSClean on simulated polarised skies | Each Stokes image within tolerance; no I-to-QUV leakage from the imager beyond WSClean's | yes | G3 |
| G7 | Settle defaults, including coarse gridding, on the real pilot (owner: after measuring) | WSClean at matched accuracy | Defaults chosen and recorded; figures single-core and threaded | yes, idle host | G2, G3, G5, G9 |
| G8 | In the wheel: extension binding and a `gemclean` console script, not a second binary | Source build | `pip install` runs it on all five platforms; FITS identical to the source build on S1; speed measured **on the wheel**, because current figures come from the fat-LTO `gemclean` profile | yes | G7 |

### C. Calibration

| ID | Task | Oracle | Done when | Heavy | After |
| --- | --- | --- | --- | --- | --- |
| C1 | **Done 2026-11-05** ([c1-calibration-chain.md](c1-calibration-chain.md)). Specify the chain from CARACal's `crosscal_worker.py` sequence ([o-casa.md](o-casa.md)) | none | A frozen list of terms and order, with reasons for anything left out | no | A0 |
| C2 | Gain, delay and bandpass in CARACal's order K, G, B, phase-only terms, chains of terms, and F with `fluxscale` (C1 steps 3-6), in Rust | QuartiCal and CASA | Each term within tolerance on the slice and simulated truth | yes | C1 |
| C3 | Calibrator models (`setjy`), using `fluxstd` and the predictor; the flux-scale transfer moved to C2 | CASA `setjy` | Model visibilities within tolerance on 1934−638 | no | C1 |
| C4 | Interpolate and apply solutions, writing `CORRECTED_DATA` | CASA `applycal` | Corrected data within tolerance; flags propagated as CASA does | no | C2, W1 |
| C6 | Polarisation terms in C1's order: Gpol, cross-hand delay (KCROSS), cross-hand phase (Xf), leakage (Df); parallactic angle throughout | CASA `gaincal` and `polcal` | Each term within tolerance on simulated truth and a polarisation calibrator | yes | C2, C3 |
| C7 | Apply the polarisation solutions; polarised calibrator models | CASA `applycal`; published 3C286 or 3C138 values | Calibrated Q and U, fractional polarisation and angle within tolerance | no | C4, C6 |
| C5 | Self-calibration from `MODEL_DATA`: phase, then amplitude by default, and CARACal's delay form (`Fslope`) as an option | QuartiCal (a substitute for CubiCal); simulated truth | Gains recovered on simulated truth; solution intervals configurable | yes | C4, G6 |

### W. Write-back and general commands

| ID | Task | Oracle | Done when | Heavy | After |
| --- | --- | --- | --- | --- | --- |
| W1 | Write-back to an existing MS: add columns, write `FLAG`, back up flags | casacore, CASA, WSClean read-back | The tools read every column; a failed run leaves the original flags recoverable | no | none |
| W2 | One config schema; `rang-core flag`, `calibrate`, `image`, `selfcal` and `run`; resume; receipts | none | Each runs on an MS outside the repository; research stages move under `rang-core research` | no | W1 |
| W3 | Chunking by time and row for whole-array data | Unchunked output | Same result chunked and unchunked within tolerance, with a stated memory limit | yes | W2 |
| W4 | Unsupported data: multiple spectral windows and fields, autocorrelations, missing weights, other correlations | Written cases | Each case works or is refused with a clear message | no | W2 |
| W5 | The Stimela recipes call the new commands | Recipes run | One recipe runs the chain; research recipes are marked as such | no | W2 |

### E. End to end, and release

| ID | Task | Done when | Heavy | After |
| --- | --- | --- | --- | --- |
| E1 | The whole chain on simulated truth | Gates of A0 pass, or the failure is recorded and fixed | yes | C5, W3, A1 |
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

- **Native data.** Without it E2 and E3 can only finish on weaker data. LUNO's DATA is pre-phased, so KCROSS and Xf are near zero there; A1 must carry them.
- **E3 can come out badly.** A worse result than CARACal would be recorded, then fixed or stated in the release; it would not be reworded.
- **The unexplained floor.** The pilot's floor is 40-60 × thermal in all imagers, for a reason not found. It may limit what E2 can show.

## 6. Waiting, and off the finish line

- **Landman.** The owner pinged him on 2026-11-05. Nothing starts on the flagger until he replies. The non-TV arms (Z, R, F-RES) would need
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
