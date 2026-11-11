# E2: the whole chain on the acceptance data, unseen

Task E2 of [finish-plan.md](finish-plan.md), on branch `fp-e2-acceptance` from
main `8d3becd`, 2026-11-10. Native Windows (`.venv` with uv, Python 3.14);
WSL only for the Linux oracles (CASA 6.7.6.14, Tricolour 0.2.1, WSClean 3.7,
QuartiCal 0.2.7).

**Status (2026-11-11): E1b measured (section 5: the image gate met, the rest
as E1); `average_time` merged (validated on LUNO except Gpol). E2's protocol:
the draft, being finalised; no E2 cube decoded by this task.**

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
| a | ESO137 `ms1_primary.zarr` MAIN_4, MAIN_5 (scans 9, 11), `ms1_target.zarr` MAIN_4 (scan 10) | 7,777, 180,018,619,332 | first attempt 18:41 to 19:31, rc 1 (an S3 folder placeholder key `ESO137/ms1_target.zarr/` could not be a file; the fetcher now skips keys that end in `/`); resumed after leg d; done 2026-11-11 01:35:12, rc 0 |
| d | LUNO MAIN_0, MAIN_1 (development scans 1, 2) | 3,422, 31,513,806,315 | 2026-11-10 21:22:22 to 22:06:27, rc 0 |

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

## 4. State at the halt (2026-11-11 10:30, owner asked to halt and restart)

Nothing of mine is running; queued runs (waiting on the heavy lock) were
stopped before they started. A host restart at 03:23 had killed the earlier
runs.

**Done and on disk:**
- Fetches complete: `D:\rang\data\e2-b` (36.3 GB, rc 0), `e2-d` (31.5 GB,
  rc 0), `e2-a` (180.0 GB, rc 0 at 01:35); manifests with SHA-256 per object.
  Target row columns also in `D:\rang\data\e2-a-rowcols` (16.5 MB).
- Metadata-only preflight MSs `D:\rang\outputs\e2-20261110-10-preflight\e2{a,b}-meta.ms`
  (no cube read); finding in the draft protocol 5.1: the chains are refused at
  8 GiB without time pre-averaging.
- E1b chains ran, rc 0: `D:\rang\outputs\e2-20261110-04-e1b-auto` (30 min) and
  `-05-e1b-m000` (31 min); twins `-06`, `-07` ran and are scored
  (`result-e1b-twin.json`). The m32 controls failed (rc 1) at gemclean:
  E1's `e1_run.control` passes G8's `python -m rang.gemclean` command as one
  token. Fixed in `e1b_run.py control` (expands it; nothing else changes),
  **not yet run**. No E1b m32 score exists yet.
- `calibrate.average_time` (and, added 2026-11-11, `selfcal.average_time`)
  implemented in worktree `C:\Users\gijsm\Worktrees\rang\fp-e2-averaging`
  (branch `fp-e2-averaging`, **uncommitted**: check-all not yet run on it);
  14 tests in `tests/test_e2_average_time.py` pass; note
  `research/e2-average-time.md` there (4.1 A1 done; 4.2 LUNO pending).
  LUNO validation run `D:\rang\outputs\e2-20261110-11-avg`: build, readable
  and rang steps done (`luno-*.done`); the CASA step was killed twice (WSL
  restart 03:05, host restart 03:23).
- E2 configurations `results/e2-acceptance-scripts/e2a.yaml`, `e2b.yaml`
  (draft; still to gain `average_time: true`), converter `e2_convert.py`
  (tested bit-exact on the pilot subset), timer `e2_timed.py`, and the draft
  protocol `results/e2-acceptance-scripts/e2_protocol_draft.md` (**not
  frozen**). No E2 cube has been decoded.

**Next, in order (resume commands, Git Bash):**
1. E1b controls and scores: `sh research/results/e2-acceptance-scripts/e1b_rest.sh`
   from this worktree (logs `D:\rang\outputs\e2-20261110-0{4,5}-*\e1b.log`).
2. LUNO validation, CASA step then score, from `fp-e2-averaging`:
   `bash research/results/e2-average-time/e2avg_luno_all.sh 'D:\rang\outputs\e2-20261110-11-avg'`
   (skips steps with a `.done` file).
3. check-all in `fp-e2-averaging` (PowerShell, `RANG_ARCHIVE_OUTPUTS` set,
   heavy lock), commit there, merge `fp-e2-averaging` into `fp-e2-acceptance`.
4. E1b results against E1's frozen gates; commit.
5. Finalise the E2 protocol from the draft (set `average_time`, copy A0's
   gates verbatim as appendix A), commit; build the wheel, convert and verify
   the MSs, run E2-B then E2-A under `e2_timed.py`, then the oracle arms.

## 5. E1b results (measured 2026-11-11, against E1's frozen gates)

Runs `D:\rang\outputs\e2-20261110-04-e1b-auto`, `-05-e1b-m000` (chains of
2026-11-10, rc 0; controls and scores 2026-11-11 by `e1b_rest.sh`, rc 0:
`-04` control 12:29-13:16 including lock waits, score 13:16-13:31; `-05`
control 13:31-13:34, score 13:34-16:09 including lock waits), twins `-06`,
`-07`. Numbers: `result-e1b.json` / `result-e1b-twin.json` in each run;
compact copy [results/e2-acceptance/e1b-gates.json](results/e2-acceptance/e1b-gates.json)
(`e1b_table.py`); the full result files and configurations in
[results/e2-acceptance/e1b/](results/e2-acceptance/e1b/). The flag stage's FLAG equals E1's (the same 530 cells
against Tricolour), so Tricolour was not rerun. E1 column: e1-chain.md 7.2.
CASA column: 2.4 (its matching refant arm). Each class T entry is
median(|e| / s), gate ≤ 3.

| Gate (E1 4) | E1 (m000) | E1b `auto` (m022, m023, m024) | E1b m000 | CASA arm | Verdict, both arms |
| --- | ---: | ---: | ---: | ---: | --- |
| K, class T (m32) | 5,160 | 5,680 | 5,160 | 5,860 / 6,040 | **not met**, CASA too |
| Target 1GC composite (median \|e\|) | 33.2 (4.2e-3) | 35.7 (4.7e-3) | 32.4 (4.1e-3) | 55.5 / 46.0 | **not met**, CASA too |
| Cross-hand `arg(Kc Xf)` | 195 | 760 | 150 | 820 / 75.6 | **not met**; `auto` CASA too; m000 about half rang only |
| KCROSS | 14,628 | 17,146 | 11,158 | 1.7e4 / 1.1e4 | **not met**, CASA too |
| Xf | 1,788 | 1,790 | 1,301 | 1,970 / 1,310 | **not met**, CASA too |
| Df | 18.9 | 71.8 | 14.2 | 69.9 / 27.7 | **not met**, CASA too |
| Twins, class T (1e-5) | composite max 1.2e-4 | composite median 1.0e-6, p95 1.6e-5, max 1.2e-4 | 1.6e-6, 1.7e-5, 1.2e-4 | CASA m000 the same | **not met**, CASA too |
| Flags: recall ≥ 0.90 | 0.8858 | 0.8858 | 0.8858 | Tricolour 0.8858 | **not met** (the strategy) |
| Flags: false positives = Tricolour's; 3a | +234, 530 cells | +234, 530 cells | +234, 530 cells | – | **not met** (owner item 33(2): accepted, documented) |
| Image, Stokes I: \|median r − 1\| ≤ 0.01, scatter ≤ 0.01, offsets ≤ 0.1 beam (scorer 2.3, validated) | 1.0233, 1.44 % (scorer not validated) | 1.0020, 0.59 %, max 0.049 beam | 0.9942, 0.52 %, max 0.046 beam | – | **met**, both arms (frozen scorer: 1.0022, 0.52 %; 0.9942, 0.53 %) |
| Residual ≤ 1.1 × control | 3.16 × | 2.40 × | 3.07 × | – | **not met** |
| Polarisation (components 0, 17, 30, 40: \|Δp\| ≤ 0.2 points, \|Δχ\| ≤ 1°), final column | not met | Δp −0.31, −0.75, −0.58, +0.41 points; Δχ +4.67, +0.34, +2.41, +0.18° | Δp −0.15, +0.03, +0.53, +0.65; Δχ +4.08, −1.78, −0.30, −2.18° | m000 asecflags: Δp −0.12 to −1.55, Δχ −2.0 to +1.4° | **not met** |
| Polarisation, 1GC column (reported) | Δp −0.10 to −1.62 | Δp −0.19, −0.74, −0.93, +0.17; Δχ −0.76, −0.23, +8.07, +1.21° | Δp −0.10, −0.31, −0.48, −1.62; Δχ +0.19, −1.68, +1.31, −0.73° | – | – |
| Leakage ≤ 0.1 %: SIM-GCAL median; every target point | 0.54 %; 0.47-1.1 % | 1.07 % (p95 8.6 %); 0.25-1.27 % | 0.54 % (p95 2.6 %); 0.46-1.11 % | 2.0 % / 0.47 % | **not met**, CASA too |
| Self-calibration, class T | 32.6, 45.7 | 30.3, 39.5 | 34.4, 45.4 | – (no CASA selfcal) | **not met**, as expected (item 29) |
| Selfcal against C5's T2 (reported): r1 phase median, p95; r2 phase; r2 amplitude | 0.76°, 3.15°; 0.61°, 2.32°; 0.97 %, 2.93 % | 0.77°, 3.08°; 0.56°, 3.64°; 1.02 %, 9.07 % | 0.80°, 3.28°; 0.62°, 2.39°; 0.95 %, 2.87 % | – | r1 p95 and r2 phase miss in both arms; `auto` r2 amplitude p95 misses too |

On the control column (`CORRECTED_TRUTH`) every polarisation and leakage
measure passes in both arms (|Δp| ≤ 0.14 points, |Δχ| ≤ 0.25°, points ≤ 0.06 %),
so the visibility-domain estimators stay validated.

**Reading, against "Expected before the run" (section 3).** As expected: the
`auto` arm's cross-hand (760 against m000's 150), Df (71.8 against 14.2) and
SIM-GCAL leakage (1.07 % against 0.54 %) are worse through A1's refant X−Y
drift (2.1), and CASA's `auto` arm is as bad (820, 69.9, 2.0 %);
self-calibration fails class T in both arms; the flag gates are E1's. Not
expected: the image gate is **met** in both arms once the scorer is validated
(E1 had only the unvalidated reading); and the m000 arm's cross-hand error
(150) is below E1's 195 (between them: `niter`, now 1e6, and the code of item 27,
and the selfcal refant rule; not traced). m000 reproduces E1's K (5,160) and
composite (32.4 against 33.2). 3C286-SIM (reported): p 0.0952 both (truth
0.095); |χ − 33°| median 0.95° (`auto`), 2.49° (m000).

**Owner item 33(1)**: polarisation is reported for both arms above; on A1's
truth every refant except m000 drifts 13-22° rms in X−Y (2.1), so with
CARACal's strategy 1 the `auto` arm's leakage limit is the method's, in CASA
too. A Df solve on the polarised calibrator is a post-release option.

## For the coordinator

(written at the end)
