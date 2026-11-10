# E2: the whole chain on the acceptance data, unseen

Task E2 of [finish-plan.md](finish-plan.md), on branch `fp-e2-acceptance` from
main `8d3becd`, 2026-11-10. Native Windows (`.venv` with uv, Python 3.14);
WSL only for the Linux oracles (CASA 6.7.6.14, Tricolour 0.2.1, WSClean 3.7,
QuartiCal 0.2.7).

**Status: part 1 (finish-plan item 27 and the E1b protocol) written; nothing
of E1b has run. Part 2 (E2's protocol) is not written; no E2 visibility has
been read.**

Owner answers that bind this task (finish-plan section 7): item 6 (split legs,
E2-N open, fetches approved), item 27 (E1's decisions, all done before the
unseen runs), item 29 (C5b: CARACal's selfcal values in E2-A, multiscale gated,
Högbom reported only, FITS masks without regridding).

## 1. Fetches (A0 section 8, owner item 6)

Script [results/e2-acceptance-scripts/e2_fetch.py](results/e2-acceptance-scripts/e2_fetch.py)
(stdlib only, whole objects, SHA-256 per object in `manifest.json`), run
through `e2_fetch_job.sh LEG` (START/END/rc and free space in
`D:\rang\data\e2-LEG.log`). Per MAIN group: DATA, FLAG, WEIGHT_SPECTRUM and
every row column, plus every subtable. Not fetched: CORRECTED_DATA*,
MODEL_DATA, SIGMA_SPECTRUM, IMAGING_WEIGHT, FLAG_CATEGORY, the reserve, the qc
gains. The fetcher writes bytes; it decodes nothing.

| Leg | What | Objects, bytes | Start, end, rc |
| --- | --- | ---: | --- |
| b | LUNO `LBAND_LUNO_CALIBRATORS.zarr` MAIN_16-19 (scans 17-20) | 3,734, 36,273,927,018 | 2026-11-10 17:45:18 to 18:41:12, rc 0 (3,354 s, 10.8 MB/s) |
| a | ESO137 `ms1_primary.zarr` MAIN_4, MAIN_5 (scans 9, 11), `ms1_target.zarr` MAIN_4 (scan 10) | 7,777, 180,018,619,332 | first attempt 18:41 to 19:31, rc 1 (an S3 folder placeholder key `ESO137/ms1_target.zarr/` could not be a file; the fetcher now skips keys that end in `/`); resumed after leg d |
| d | LUNO MAIN_0, MAIN_1 (development scans 1, 2) | see section 10 | after leg a's failure |

**Why leg d (not in the approved list, recorded as the brief requires).**
E2-B's frozen rows "3C 286 transfer" and "1934−638 leakage" (A0 6.3) apply the
development half's B, KCROSS, Xf and Df, solved on LUNO scans 1 and 2, to
scans 17 and 18. No whole copy of scans 1-2 was on the host (A0 section 8 lists
it as a C6/C7 fetch; C6w and C7b used simulations). It is development data,
never held out, 31.5 GB.

## 2. Item 27, part by part (done before E1b)

### 2.1 `refant: auto` as the default

- An unset `calibrate.refant` now means `auto` (CARACal's `get_refant`, E0)
  on every K, G, B, F, Gpol and Df term without its own refant; it was
  refused. Where no antenna qualifies (a MS without a MeerKAT-like core, such
  as most test sets), unset falls back to antenna 0, as CASA takes the first
  antenna for an empty refant, and the calibrate summary records it. An
  explicit `auto` still stops when nothing qualifies (E0 decision 2). A first
  version made `auto` the schema default; it refused the complex term and
  every test set without a qualifying antenna (28 tests), so it was replaced
  before any run. `selfcal.refant` unset follows calibrate's (auto, or antenna
  0), and `selfcal.refant: auto` resolves to the first antenna of the same
  choice, which reads only ANTENNA and OBSERVATION; before, selfcal refused
  auto and took antenna 0 when both were unset. Test:
  `tests/test_e0_refant_extend.py::test_e2_defaults_and_selfcal_auto`.
- **"The leakage-gauge error fixed": the reading adopted, written before E1b.**
  With strategy 1 (Df on an unpolarised calibrator) the reference antenna's
  `d_x,r` is unobservable and leaves about `2 d_x,r Q` in the cross hands of
  polarised sources (A1 2.5). That is a property of the method, in CASA too;
  no chain change fixes it without a polarised Df solve, which CARACal does
  not do (a larger task, owner decision 1 in section 9). What is fixed is the
  **scorer**: E1's class-T measures compared Df and the cross-hand phase with
  the truth in m000's gauge only. `e1b_score.py --refant` compares them with
  the truth in the gauge of the refant the chain actually used (per channel,
  the chain antenna whose `d_x` is exactly 0): `τ_c' = τ_c + τ_x,r − τ_y,r`,
  the refant's B X−Y phase, its G X−Y phase as a circular mean over the
  3C286-SIM integrations Xf uses, then the subtractive Df reference
  `d_x,p −= d_x,r`, `d_y,p += conj(d_x,r)`. With m000 it reproduces E1's
  gauge0 truth (twin: equal to 1e-16).
- **A property of A1's truth found while writing the scorer (measured, before
  E1b):** only m000 has equal X and Y gain phases by construction. Every other
  antenna's X−Y gain phase drifts in time (m022: 59° peak to peak over the
  track), so with any other refant the cross-hand phase on the target varies by
  a part that no constant Xf can follow:

  | Refant | over 3C286-SIM: rms, max | over SIM-TARGET: rms, max |
  | --- | --- | --- |
  | m022 | 22.3°, 36° | 16.3°, 33° |
  | m023 | 13.1°, 21° | 13.2°, 21° |
  | m024 | 14.7°, 19° | 14.7°, 26° |

  Real feeds keep X−Y gain phase far steadier than this truth's independent
  per-hand walks; the drift is a feature of A1's construction. **E1b's
  `auto` arm is therefore expected to fail the polarisation and cross-hand
  gates by construction** (stated here before it runs), and E1b also runs an
  `m000` arm so that the other item-27 changes are measured apart from it.

### 2.2 `image.niter`

The schema default is 1,000,000 (CARACal's selfcal `img_niter`; C5b's
images stopped on threshold at most at 102k of 1e6), was 100,000. E1's
configuration sets no `niter`, so E1b takes the new default.

### 2.3 The image scorer's convention (measured, validated on the control first)

Cause of E1's control offset (1.0296), established: E1 ran before G7, and
GeMClean's restoring-beam fit then failed on output channel 7 (1605-1712
MHz), writing BMAJ = BMIN = 2″ (one pixel) where the PSF main lobe is 5.36″ ×
4.28″. The frozen fixed-beam fit there reads 1.29 × truth (1.09-1.46), and
channel 7 carries about 10 % of ΣS. Channels 0-6 alone: median 1.0009,
scatter 0.10 %. Ruled out by measurement: a flag-weighted truth per channel
(≤ 0.4 %), the channel centre instead of the mean (≤ 0.14 %). The MFS fits at
0.95-0.99 follow MF weighting (reference 1348.8 MHz).

**Fixed convention:** per output channel the scorer fits its own restoring
beam to that channel's PSF (WSClean 3.7's method, as G7), re-restores
`residual + model ⊛ beam` and fits the Gaussian fixed to that beam; the truth
stays the plain mean of S over the channel's input channels.

| Measure on the control (35 sources ≥ 50σ) | median r | robust scatter | validates (≤ 0.005, ≤ 0.005) |
| --- | ---: | ---: | --- |
| frozen, E1's control image | 1.0296 | 1.42 % | no |
| fixed, E1's control image | 0.99872 | 0.138 % | **yes** |
| fixed, control re-imaged with current (post-G7) gemclean, same argv | 0.99872 | 0.138 % | **yes** |
| frozen, control re-imaged with current gemclean | 0.99874 | 0.133 % | yes |

**Reproduction of E1 with m000 (the refant generalisation must be the
identity there).** On the twin `e1b_score.py --refant m000` equals E1's
`result-twin.json` (two values differ by 1e-16; the generalised gauge equals
gauge0 to 2e-16). On m32 (`-03`) neither scorer now reproduces E1's frozen
`result.json`: the frozen `e1_score.py`, rerun today on the same run
(`m32-frozen-rescore.json`; E1's file restored afterwards byte for byte),
counts 147,273,634 target cells where E1 counted 196,231,168, so the run
directory's flag state changed after E1 was scored (a later diagnostic or the
control's write; not traced). On today's state `e1b_score` and the frozen
scorer agree on K, the composites and the cross-hand phase. E1b scores fresh
runs, so this does not affect it; E1's archive stands as written then.

Run `D:\rang\outputs\e2-20261110-02-scorer` (re-image 138.4 s under the lock).
Script `e1b_score.py` (E1's `e1_score.py` is unchanged), probes
`e2_scorer_probe.py`, `e2_control_reimage.py`.

### 2.4 The CASA-chain arm (m32 and the twin)

`e1b_casa.py`: CARACal's full-Stokes chain in CASA 6.7.6.14 as E1's
configuration (setjy SR2016; K, G, B; Gsec, F, `fluxscale`; `flagdata
extend`; Gpol, KCROSS, Xf, Df with clip; `applycal(parang=True)`), scored by
`e1b_casa_score.py` with E1b's measures where they apply (terms, 1GC
composite, polarisation and leakage in the visibility domain; no image or
selfcal). On m32 it starts from rang's FLAG after the flag stage. Deviations:
no A step (Tricolour on corrected data has no CASA counterpart, as C2e), so a
labelled post-hoc arm `m32-m000-asecflags` also gives CASA rang's Asec flags;
CASA's own parallactic frame (E1 uses `polcal.frame: rang`). Runs
`D:\rang\outputs\e2-20261110-03-casaarm\<arm>` (CASA 1,458-1,512 s per m32
arm, 34 s per twin arm). This is an oracle arm, measured before the E1b
protocol; it does not run rang.

| Arm | K | target 1GC | cross-hand | KCROSS | Xf | Df | polarisation, leakage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| CASA m32-m000 | 6,040 | 46.0 | 75.6 (0.0089 rad) | 1.1e4 | 1,310 | 27.7 | SIM-GCAL leakage 3.2 % |
| CASA m32-m000-asecflags (post hoc) | as above | 42.9 | 75.6 | 1.1e4 | 1,310 | 27.7 | Δp −0.12 to −1.55 points, Δχ −2.0 to +1.4°; SIM-GCAL 0.47 %, target points 0.07-0.68 % |
| rang E1 (m000), 1GC | 5,160 | 33.2 | 195 (0.017 rad) | 1.5e4 | 1,788 | 18.9 | Δp −0.10 to −1.62, Δχ −1.7 to +1.3°; SIM-GCAL 0.54 %, points 0.05-0.74 % |
| CASA m32-auto (m022, m023, m024) | 5,860 | 55.5 | 820 (0.085 rad) | 1.7e4 | 1,970 | 69.9 | Δχ −5.9 to −21.6°; SIM-GCAL 2.0 % |

Each entry is median(|e|/s) of E1 4.1 (median |e| in brackets). Twins: CASA
m000 and rang agree (K max 0.095 against 0.089 ns; composite median 1.63e-6
against 1.6e-6, max 1.22e-4 both; F 4.2921 Jy both); with auto (on the twin
m008, m024, m032) CASA's cross-hand max is 0.89 rad, rang's 0.26.

**Split of E1's failures (m000):** CASA too: K, the target composite, KCROSS,
Xf, Df, polarisation and leakage (with matched flags CASA's polarisation and
leakage equal rang's 1GC; its composite is worse). Rang only: about half of
the cross-hand phase error (rang 195, CASA 75.6). One table disagreement:
KCROSS on the fourth 3C286-SIM scan (scan 22): rang 2.926 ns, CASA 3.038 ns,
rang nearer the truth; cause not traced.

### 2.5 The 530 flag cells (probe)

Run `D:\rang\outputs\e2-20261110-01-flagprobe`, scripts `e2_flagprobe_*`.
Scan 1, baseline m014-m053 holds 413 of the 530 cells (329 rang only, 84
Tricolour only); the other 117 on 26 baselines were not probed.

- Neither untested candidate of E1: rang's Windows and Linux (glibc 2.43)
  builds are bit-identical (intensity, every step's flags, final flags), and
  a single baseline gives the same cells as the whole array on both sides
  (Tricolour's windows are whole scans per baseline).
- **Cause, shown:** the port's documented departure in
  `core/src/sumthreshold.rs` (lines 45-48, `lowpass_fit`): an exact float64
  DFT rounded to complex64, where Tricolour uses a complex64 pocketfft round
  trip. At step 3 (`residual_flag_initial`), cycle 2, one cell (time 12,
  channel 218) sits +1.6e-7 relative above the threshold 5.885589 with
  Tricolour's fit (about 2 float32 ulps) and −5.7e-7 below with rang's. That
  cell leaves channel 218 at 31 of 32 times flagged against 32 of 32; step 9
  (`or_original_from_cycle 0`) then moves its threshold by 1.35-1.8 % and whole
  channels flip: 413 cells in 18 channels. A NumPy copy of Tricolour's flagger
  reproduces Tricolour's step 3 exactly with pocketfft and rang's with the
  float64 DFT; Tricolour's own code on rang's step-8 flags gives rang's 2,073.
- Not a port bug. Owner decision 2 (section 9).

## 3. E1b protocol (frozen before any E1b run)

**What E1b is:** E1's chain rerun as a new, labelled run after item 27,
reported against **E1's frozen gates** (e1-chain.md section 4, unchanged;
not refrozen). E1 is not held out (A0 6.5).

**Arms** (runner `e1b_run.py`, job wrapper `e2_job.sh`, heavy lock):

| Run | Data | Configuration |
| --- | --- | --- |
| `e2-20261110-04-e1b-auto` | copy of m32 (`e1-20261109-02-data`) | E1's `e1_config.yaml` with both `refant: m000` lines removed: calibrate `auto` (expected m022, m023, m024, E0), selfcal its first; `niter` the new default 1e6 |
| `e2-20261110-05-e1b-m000` | copy of m32 | E1's configuration unchanged; `niter` the new default |
| `e2-20261110-06-e1b-twin-auto`, `-07-e1b-twin-m000` | copies of the small twin | as E1's twin tier (no flag stage, no A step) |

Each m32 arm: `rang-core run config.yaml ms`, then the control
(`e1b_run.py control`, E1's), then `e1b_score.py chain RUN --refant <the
arm's list> --tricolour D:\rang\outputs\e1-20261109-04-tricolour` (the flag
stage's code is unchanged since E1, so E1's Tricolour run is the oracle; if
the flag stage's FLAG differs from E1's `-03` at all, that is reported and
Tricolour reruns). Twins: `e1b_score.py twin RUN --refant <list>`.

**Measures and gates:** E1's section 4, every gate as frozen, with two
scorer changes (2.1 and 2.3) applied to both arms. Beside each, the frozen
scorer's reading (image) and the CASA arm's number (2.4), so each failure is
labelled "CASA too" or "rang only". The image scorer is validated (2.3), so
the image gate is read directly.

**Expected before the run:** the `auto` arm fails the cross-hand,
polarisation and leakage gates through A1's refant X−Y drift (2.1), CASA too;
self-calibration fails its class T gate (C5's model absorption, owner item 29
accepts it); the flag gates stay as E1's (2.5).

**Rules:** nothing in this section changes after a result; added analyses
are labelled post hoc. A bug located with truth is fixed with a test and the
arm reruns under a new number.

## For the coordinator

(written at the end)
