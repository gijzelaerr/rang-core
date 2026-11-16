# E2: the whole chain on the acceptance data, unseen

Task E2 of [finish-plan.md](finish-plan.md), on branch `fp-e2-acceptance` from
main `8d3becd`, 2026-11-10. Native Windows (`.venv` with uv, Python 3.14);
WSL only for the Linux oracles (CASA 6.7.6.14, Tricolour 0.2.1, WSClean 3.7,
QuartiCal 0.2.7).

**Status (2026-11-11): E1b measured (section 5: the image gate met, the rest
as E1); `average_time` merged (validated on LUNO except Gpol); E2's protocol
frozen (section 6) before this task decoded any E2 cube. E2-B and E2-A: see
the results section.**

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
  frozen** at the halt; superseded by section 6 and removed at the freeze
  commit). No E2 cube has been decoded.

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

## 6. E2 protocol (FROZEN 2026-11-11, before E2's author decoded any E2 cube cell)

Written after E1b's chain runs and before this task decoded any E2-A or E2-B
cube cell; finalised after E1b's scores (section 5) and the LUNO validation of
6.1, and committed before `e2_convert.py build` reads an E2 cube. Nothing in
this section changes after a result; additions are dated amendments (6.7) or
labelled post hoc. Everything read of the E2 groups by E2's author before
this commit: the fetched bytes (not decoded), row columns, subtables and
group attributes (A0 section 4 allows these), through the metadata-only
preflight MSs of 6.1.

**Held-out integrity, recorded.** E2-B cubes were decoded by the E3 session
on 2026-11-11 before this freeze (its build log: build from 17:14, verify
done 17:26; `D:\rang\outputs\e3-20261111-input\e2b.ms`, all of MAIN_16-19),
and a CARACal or CASA correctness pass ran on it. Nothing of it was read by E2's author
except the conversion metadata that identified the data (`e2b.ms.convert.json`:
groups and row counts; `build.log`); no cube, table, image or score of `e3-*`
was opened. The coordinator embargoed every E3 E2-B number
until this commit. E2-A: the only conversion of `e2-a` on D: is this
task's metadata-only preflight (every `*.convert.json` under `D:\rang\outputs`,
searched at the freeze).

### 6.1 What the metadata preflight found, and the fix (before the protocol)

`e2_convert.py build --no-cubes` writes the row columns and subtables of the
E2 groups with DATA, FLAG and WEIGHT_SPECTRUM left at zero and never read
(`D:\rang\outputs\e2-20261110-10-preflight\e2a-meta.ms`, `e2b-meta.ms`).
`rang-core config check` on them refused the CARACal chains at the default
`data.memory_limit_gb: 8`: W3b solves one solution interval whole, and at
4,096 channels K and G `inf` need 145-176 GiB, KCROSS `inf` 174 GiB, Gpol
`60s` 19 GiB, Gsec and F 26 GiB, K1 and G1 `60s` 23 GiB (the host has 30 GB).
`rang-core selfcal` has no preflight; its Sp and Sa at solint 120 on the
E2-A target would need 333 GiB per interval at 4,096 channels and 42 GiB at
512 ([e2-average-time.md](e2-average-time.md) 4.3). **As frozen in A0, both
legs would have failed gate 1 with a refusal; that was found from metadata
only, so the fix below is pre-registration, not post hoc.**

The fix is CASA's own estimator ([e2-average-time.md](e2-average-time.md),
branch `fp-e2-averaging`, merged here at `8e7acfc` (and origin/main at `eb16cd8`) before this protocol):
`calibrate.average_time` and `selfcal.average_time` (default false; off is
byte-identical to before, stage hashes unchanged): every K, G, B, F, Gpol,
KCROSS, Xf, Df solve, and selfcal's Sp and Sa, on data and model averaged in
time within each solution interval after the pre-applies and P. Its
validation on development data (A1 small; LUNO scans 1 and 2 against CASA
6.7.6.14 at class B) is in that note. Self-calibration with it is not
CubiCal's estimator (which solves every sample); adopted by owner item 33(3)
(finish-plan section 7), off by default, on in the E2 configurations.

**The LUNO validation (e2-average-time.md 4.2), as frozen there:** class B met
on K (median 0.0032 ns), KCROSS (0.00086 ns), Xf (0.064°), Df gauge-free
(2.7e-5) and the fcal K G B composite (4.5e-5, p95 2.2e-3); **not met on Gpol**:
phase median 0.250° against ≤ 0.1° (p95 2.03°), largest on the outer antennas
(m049, m055-m059, m062, m063: 1.0-3.0°, 1.2-4.1 km from the centre), nearly
constant in time and equal in both hands. Not the time averaging, the weights,
the refant gauge or the model; partly CASA's frequency pre-averaging of G-type
solves (emulated: median 0.108°, p95 0.94°); the rest not traced. The code is
frozen as it stands (coordinator's decision, 2026-11-11, under owner item 33);
**the expectation is recorded in 6.5.**

### 6.2 The Measurement Sets (exact paths; built after this commit)

| Leg | Built by | Groups, in time order | MS |
| --- | --- | --- | --- |
| E2-B | `e2_convert.py build` then `verify` | LUNO MAIN_16 (scan 17, J1331+3030), MAIN_17 (18, J1939-6342), MAIN_18, MAIN_19 (19, 20, J1833-2103) of `D:\rang\data\e2-b\LBAND_LUNO_CALIBRATORS.zarr`: 272,916 rows, 56 antennas, 4,096 channels | `D:\rang\data\e2-b\e2b.ms` |
| E2-A | the same | ESO137 `ms1_primary.zarr` MAIN_4 (scan 9), `ms1_target.zarr` MAIN_4 (scan 10, ESO137-001), `ms1_primary.zarr` MAIN_5 (scan 11) under `D:\rang\data\e2-a\ESO137`: 1,047,614 rows, 61 antennas, 4,096 channels | `D:\rang\data\e2-a\e2a.ms` |

- `verify` must report 0 differing cells and row-column values (it prints
  counts only); otherwise the leg stops and the converter is fixed (not a
  gate). Right after `verify`, the SHA-256 of FLAG and FLAG_ROW is recorded
  (gate 2a's reference).
- Conversion deviations, fixed now: FEED's single row is expanded to one per
  antenna; POINTING, HISTORY, FLAG_CMD, SOURCE are not written; FIELD and
  STATE are merged over the two ESO137 stores. RECEPTOR_ANGLE stays as
  stored (LUNO 0, ESO137 −90°); E2-B's rang arm rotates it in memory
  (`feed_angle_rotation: -90`), and every CASA or CARACal copy of `e2b.ms`
  gets RECEPTOR_ANGLE −90° written, as CARACal's `set_receptor_angle` does.
- Each leg's rang arm runs on this MS itself (gate 1: `rang-core run config.yaml
  my.ms`). Oracle arms run afterwards on the same file after FLAG is restored
  from `rang_original` and rang's added columns are dropped, or on a fresh
  build from the zarr (A0 amendment 1 item 3: one copy at a time).
- **Disk and order (fixed now; measured).** E1b's m32 MS after the whole
  chain (`e2-20261110-05-e1b-m000\ms`) holds five complex columns of 8.6 GB
  each (DATA, MODEL_DATA, CORRECTED_DATA, CORRECTED_1GC and the scorer's
  CORRECTED_TRUTH), WEIGHT_SPECTRUM 4.3 GB, bit-packed FLAG 0.13 GB, flag
  versions 0.83 GB and a run directory of 2.2 GB: 48 GB, or 39.4 GB without
  CORRECTED_TRUTH, for 2.69e8 cells. E2-A has 4.29e9 cells (16.0 ×), so its
  MS needs about **630 GB of columns plus 13 GB of flag versions**. Of that,
  about 225 GB (DATA, WEIGHT_SPECTRUM, FLAG) is written by the build and
  about 420 GB by the chain. E2-B (272,916 rows) needs about 58 GB at the
  build and 135 GB after its chain.
- **Order:** E2-B first (rang arm, then its oracle arms and the transfer and
  leakage rows), its compact results archived and committed, then `e2b.ms`
  deleted; then E2-A (rang arm, then its oracle arms). A leg's MS is deleted
  only after its archive is committed; the zarr stores are kept.
- **Start rule for E2-A's rang arm:** at least **470 GB free on D: after
  `e2a.ms` is built and verified** (the chain's 420 GB plus 50 GB for images,
  tables and logs). If it is short, the shortfall is reported to the
  coordinator before the run, and the run waits. Space is freed from this
  task's own outputs first (this note records each deletion), then, with the
  owner's approval only, the F2/F3 simulation data.
  E2-A never starts on a disk that cannot hold it, because a full disk mid-run
  would be a gate 1 failure that costs the reserve.
- **Deleted before this freeze** (results committed first): the LUNO
  validation's CASA copy `e2-20261110-11-avg\casa\luno-dev.ms` (73 GB; its
  tables kept; scores in `results/e2-average-time/archive/`). After the
  config checks of 6.3 (`results/e2-acceptance/config-check-*.txt`), the
  preflight MSs `e2-20261110-10-preflight\e2{a,b}-meta.ms` (245 GB of
  zero-filled cubes; `e2_convert.py build --no-cubes` rebuilds them in
  minutes).
  After the E1b commit (`3320258`, results in `results/e2-acceptance/e1b/`),
  E1b's m32 MSs `e2-20261110-04-e1b-auto\ms` and `-05-e1b-m000\ms` (51 GB
  each; their run directories, controls and images kept). D: then had 1.1 TB
  free.
- **Development MS for E2-B's transfer and leakage rows:**
  `D:\rang\outputs\e2-20261110-11-avg\luno\luno-dev.ms` (LUNO MAIN_0, MAIN_1 =
  scans 1, 2; built and verified by the same converter, 0 cells differ). Its
  rang tables are re-solved by the E2-B configuration (6.5), not taken from
  the validation run.

### 6.3 The configurations (frozen)

[results/e2-acceptance-scripts/e2a.yaml](results/e2-acceptance-scripts/e2a.yaml)
and [e2b.yaml](results/e2-acceptance-scripts/e2b.yaml), as committed with
this section, with the strategy file
[mk_rfi_flagging_calibrator_fields_firstpass.yaml](results/e2-acceptance-scripts/mk_rfi_flagging_calibrator_fields_firstpass.yaml)
(CARACal `8f7bb363`, SHA-256 `ce9ac66a…1774`, as `results/caracal-strategies.json`
and E1) beside them. Beyond their header comments:

- `calibrate.average_time: true` in both, `selfcal.average_time: true` in
  E2-A (6.1); `data.memory_limit_gb` the default 8.
- A0 amendment 1 item 3, decided now on G2's measured number: GeMClean's
  peak on the pilot at 512 channels is 19.72 GB, below 24 GB, so E2-A images
  at 512 channels (`average_channels: 8`) and the scorer keeps the inner 0.7°.
- refant: `auto` in both; on the preflight MSs it resolves to m022, m023, m024
  on both legs (it reads ANTENNA and OBSERVATION only).
- `rang-core config check CONFIG PREFLIGHT_MS` (merged code): e2a valid for
  flag, calibrate, apply, image and selfcal; e2b for flag, calibrate, apply
  and image, including the 8 GiB memory preflight
  (`results/e2-acceptance/config-check-*.txt`). Selfcal has no preflight; its
  plan at solint 120 with `average_time` is 4 chunks of one interval each
  (e2-average-time.md 4.3).
- E2-B images: no automatic mask (rang refuses one on joined IQUV images);
  the oracle arm does the same.

### 6.4 The run (gate 1) and its cost

- **Wheel:** `maturin build --release` at this branch's head (the commit that
  carries this section), installed with `uv pip install` into a fresh venv
  `~/Build/tmp/20261111-e2-wheel` (Python 3.14, plus psutil for the timer);
  its SHA-256 goes in the result. `rang-core run CONFIG MS` from that venv,
  the strategy file beside the configuration.
- **Timing method:** `e2_timed.py` around the one command: wall time end to
  end, peak resident set summed over the process tree sampled every second,
  host CPU load before and during; per stage the receipt's own times. Under
  the main checkout's `tools/heavy_lock.py` **exclusive** (no other heavy job
  on the host); the load at start is recorded. Peak disk: `du` of the MS and
  its run directory after the run. Every other step (conversion, oracles,
  scorers, builds) runs as a shared job of the lock, untimed except by its log.
- **Development dry runs, before this freeze** (`e2_dryrun.py`, merged code
  in the worktree venv, shared lock slots; `D:\rang\outputs\e2-20261111-12-dryrun`):
  - `b`: e2b.yaml's shape on LUNO scans 1-2, 20,000 rows each, 4,096
    channels. Exit 0; flag 59.7 s, calibrate 311.2 s (K, G, B, Gpol,
    KCROSS, Xf, Df, `average_time`), apply 32.0 s, IQUV image 77.3 s.
  - `a`: e2a.yaml's shape on A1 small. **First attempt: image exit 2**,
    "the PSF convolved with scale 55.2 has no positive peak": GeMClean
    refuses a multiscale scale whose PSF convolution has no positive peak,
    and A1 small has 960 target rows and no short spacings. E2-A's geometry
    (4,096², 3″, multiscale) on MeerKAT coverage is G5's run D on the ESO 137
    pilot (passed), so the second attempt turned multiscale off on A1 small
    only. Exit 0, every stage done: flag, calibrate with the A step (A0 on
    K0, G0, B0) and both K G B passes, apply, image with the automatic mask,
    and two selfcal rounds with `selfcal.average_time` (12.4 s). **Recorded
    risk:** if E2-A's largest automatic scale has no positive PSF peak, gate
    1 fails at the image stage; that is reported as frozen, not retuned.
- **Wheel smoke, before E2-B:** `e2_dryrun.py b` from the wheel venv under
  `e2_timed.py` on the development slice (LUNO scans 1-2, 20,000 rows each,
  `D:\rang\outputs\e2-20261111-12-dryrun\b-src\luno-slice.ms`): exit 0 and every
  stage in the receipt, or E2-B does not start.
  - **Amendment 2026-11-12 (before any E2 run):** smoke 1 (wall 260.8 s,
    `b-wheel.log`) exit 1. Flag done, calibrate failed at Gpol's parallactic
    angle with `ModuleNotFoundError: astropy`. The wheel venv had only the
    wheel's required dependencies; astropy is the `imaging` extra, which
    rang's FITS output and `frame='casa'` need. Fix, environment only (same
    wheel, SHA-256 2d222c60…ee2f): `uv pip install` of `rang-core[imaging]`
    from that wheel with astropy 8.0.2, pyerfa 2.0.1.5 and astropy-iers-data
    0.2026.11.9.0.35.9 pinned to the development venv's versions
    (`freeze-2.txt`). Smoke 2 ran the same way and met the rule: exit 0;
    flag, calibrate, apply and image done; wall 493.2 s, peak tree RSS
    8.28 GB (`b-wheel2-timed.json`).
    A scan of every third-party import in the installed `rang` tree (in
    functions too) against the venv found nothing else missing on the E2
    path (jax, scipy, h5py, katdal, matplotlib and pandas modules are
    outside it). E2-A's path is wider than smoke b's (A step, Gsec, F,
    automatic mask, selfcal), so `e2_dryrun.py a` also runs from the wheel
    venv before E2-A, under the same rule. It ran on 2026-11-12 and met it:
    exit 0; flag, calibrate, apply, image and selfcal done (multiscale off
    on A1 small, as the development run); wall 20.4 s, peak 1.41 GB
    (`a-wheel-timed.json`). The packaging gap (Gpol and FITS
    output need an optional extra) is a finding for the coordinator. Gate
    1's "no hand step" is read on the run itself; this environment fix
    precedes it and is reported beside it.
- One shot per leg (A0 rule 2). Order: E2-B, then E2-A (6.2's disk rule).

### 6.5 Gates and how each is computed

A0's gates are copied verbatim in appendix A,
[results/e2-acceptance/appendix-a.md](results/e2-acceptance/appendix-a.md)
(A0 at `a373a4c`: sections 5, 6.1 rows 1-3c, 6.2, 6.3's E2-A and E2-B, 6.5,
6.6; byte-checked by `e2_appendix_a.py`). How each is computed here:

| Gate | E2-B | E2-A |
| --- | --- | --- |
| 1 | exit 0, every stage of `run.stages` in the receipt, no hand step | the same |
| 2a | FLAG and FLAG_ROW restored from `rang_original` equal the hashes of 6.2 | the same |
| 2b | python-casacore (`rang-formats-oracle`) opens every table and column; CASA `listobs`, `flagmanager(mode='list')`, and `applycal` with rang's tables on a copy against rang's CORRECTED_DATA (class C); WSClean `-niter 0` on CORRECTED_DATA and MODEL_DATA; QuartiCal reads the MS through dask-ms | the same, on E2-A's tables |
| 2c | astropy WCS parses every FITS rang wrote | the same |
| 3a | Tricolour 0.2.1 (`rang-tricolour:0.2.1-e1`), the same strategy, `-fs polarisation`, `-dc DATA`, input flags as converted, on the restored MS; cells against rang's flag stage | the same, with rang's `flag.fields` (fcal and target) |
| 3b | CASA 6.7.6.14 runs CARACal's full-Stokes sequence (as `e1b_casa.py`, with `average_time` not applicable: CASA pre-averages itself) on a copy with rang's FLAG after its calibrate stage, the same refant list and models; per term class B / the term limits on gauge-free composites (K, KCROSS, Xf, Df with the refant as in A0 rule 5) | CASA runs CARACal's KGB, KGB sequence on the primaries (no A step: it has no CASA counterpart) on a copy carrying rang's FLAG after calibrate (after A), same refant and model; **gated: K1, G1, B1 and their fcal composite** (the tables applied); K0, G0, B0 reported, since rang solved them before A |
| 3c | WSClean 3.7 dirty and cleaned images of rang's CORRECTED_DATA with matched settings (2048 × 2″, robust 0, 8 joined channels, IQUV joined, no mask, 3σ); dirty L∞ / peak; cleaned through the scorer | WSClean of rang's CORRECTED_DATA at the image stage's settings (multiscale, auto-mask 5, threshold 3, 512 channels); dirty L∞; compact-source ratios through the scorer (inner 0.7°) |
| E2-B rows | 3C 286 parity: p and χ per 100 MHz (1.0-1.65 GHz, ≥ 10 % unflagged) in the visibility domain (mean over unflagged cells of the calibrated cross hands after derotation to the sky frame) from rang's and CASA's calibrated scan 17. Transfer: the development half's tables, solved by the same configuration's calibrate on LUNO scans 1 and 2 (the development MS of 6.2: `e2b.yaml` with `data.scans: [1, 2]`, no `secondary` block and `run.stages: [flag, calibrate]`, so K, G, B on 1934−638 and KCROSS, Xf on 3C 286 and Df on 1934−638 of scans 1-2; CASA's development tables by the same calls on a copy carrying rang's flags after that calibrate) with Gpol (p, 60 s, parang) solved on scan 17, applied to scan 17 (rang library apply), p and χ at 1.3-1.5 GHz; both arms (CASA likewise). 1934−638 leakage: development Df applied to scan 18; peak of the Q, U, V MFS images over I. 1830−211: I, p, χ against CASA after the full chain | – |
| E2-A rows | – | Flux scale: K, G, B solved on scan 9 only (same configuration, `data.scans: [9]` for calibrate), applied to scan 11, 1934−638's Stokes I per 100 MHz against SR2016. Target: ≥ 10σ isolated sources in rang's and the oracle's image-stage images (CASA-corrected data, WSClean): ratio, robust scatter; off-source rms and dynamic range. Self-calibration: off-source rms of selfcal's image 1 (from CORRECTED_1GC) and of its final image (after ≤ 1.02 × before); gains class B against QuartiCal 0.2.7 on the same MODEL_DATA and solint, unaveraged (stated) |

Images go through E1b's scorer convention (2.3) where a truth is not
available: compact sources are fitted with a Gaussian fixed to each image's
PSF-fitted beam, matched between arms by position (within 0.5 beam).

**Expected before the run (written now, from development data only).**
- E2-B gate 3b **Gpol: expected not met** at class B, as on LUNO scans 1-2
  (6.1: 0.250° against 0.1°, outer antennas). K, KCROSS, Xf, Df and the fcal
  composite are expected met; Gsec, F and the 1830−211 row were not
  validated on development data.
- E2-B 3a: expected not exactly 0 differing cells (owner item 33(2): the
  port's float64 DFT against Tricolour's complex64 pocketfft, about 2 ulp at a
  threshold; E1 had 530 cells in 288 M). Read against the gate as frozen.
- E2-A self-calibration: CubiCal's estimator differs from the averaged one
  (item 33(3)); C5's model absorption (item 29) applies.

**Scorers and oracle scripts.** Each one is committed, and run once on the
development dry runs (6.4) or on LUNO scans 1-2, before it reads an E2
result. A scorer bug found on E2 data is fixed with a test, and both
readings are reported, labelled.

**Anything not run is reported as "not checked", never as met.** Where an
oracle cannot run on this host (memory, disk), the reason is recorded.

### 6.6 Failure rules (A0 6.5, verbatim in appendix A)

E2-A failure: recorded as frozen; after a fix, one rerun on the reserve
(scans 12, 11, 13), which needs the owner-approved reserve fetch (164 GB):
fetched only then, and the reason recorded. E2-B failure: recorded; a rerun
after a fix is labelled "seen". Nothing here is retuned against E2 data and
presented as a pass.

### 6.7 Pre-registered extra arm and amendments

- **E2-B amended (pre-registered now; coordinator's decision 2026-11-11 under
  owner item 33).** CASA's frequency pre-averaging of G-type solves (G, Gpol,
  Gsec, F) is implemented as a configuration key, off by default, on its own
  branch, and validated on LUNO scans 1-2 against CASA (development data)
  while E2-B and E2-A run. **Sealed until that amendment is committed:**
  every E2-B gate 3b and 3c score and every E2-B row (3C 286, transfer,
  1934−638 leakage, 1830−211), all of which depend on Gpol directly or
  through KCROSS, Xf and the images. Readable before it: the exit code,
  receipt and timing (gate 1), gate 2, and gate 3a (the flag stage precedes
  every solve). The amendment names the key, its commit and its LUNO
  validation. The arm runs whatever that validation shows (pre-registered),
  and its LUNO numbers are reported beside. The arm
  is then `e2b.yaml` plus that key. It runs on `e2b.ms` restored as in 6.2
  (FLAG from `rang_original`, rang's columns dropped) before `e2b.ms` is
  deleted if the key is ready by then; otherwise after E2-A is archived and
  `e2a.ms` deleted, on a fresh build from the zarr (6.2's disk rule), with
  the same gates and scorers. It is reported beside the frozen arm, and the
  frozen arm stays the record. If the key is not ready, the amended arm is
  "not run".
- Amendments: 2026-11-12, the wheel venv's `imaging` extra (6.4, wheel
  smoke), before any E2 run. 2026-11-12, the E2-B amended arm's key,
  `calibrate.average_freq` (below), before any sealed E2-B score was read.
- **Amendment 2026-11-12 (E2-B amended arm's key; committed before any
  sealed E2-B 3b, 3c or row score was read; E2-B's gate 1 numbers, read
  before it, are readable under the rule above).** The key is
  `calibrate.average_freq: true`, commit `e75fcfc` (branch `fp-e2-freqavg`,
  merged here as `50ba873`): every G (primary and secondary), F and Gpol
  solve averages data and model over the window's channels before the
  solve; K, B, KCROSS, Xf, Df, A and selfcal are unchanged
  ([e2-average-freq.md](e2-average-freq.md)). LUNO validation
  (development data, with `average_time`, against CASA 6.7.6.14, class B):
  met on K (median 0.0032 ns), KCROSS (0.00062 ns), Xf (0.053°, p95 0.30°),
  Df (2.4e-5, p95 2.2e-4) and the fcal composite (4.5e-5, p95 2.2e-3);
  **not met on Gpol**, median 0.108° against 0.1° (0.250° without the key).
  The arm runs as pre-registered: `e2b.yaml` plus the key, under
  `e2_timed.py`, exclusive, on `e2b.ms` restored as in 6.2, from a wheel
  built at `50ba873` in its own venv with the frozen venv's pins
  (`freeze-2.txt`). The frozen wheel and venv stay E2-A's. Same gates and
  scorers as the frozen arm; its Gpol class B miss is expected at about
  the LUNO size.

## 7. E2-B results

Measured 2026-11-12. Each gate is read against 6.5 as frozen. Sealed scores
were read only after `0477e54` (the 6.7 amendment, pushed).

### 7.1 Scorer and oracle decisions written before reading the sealed scores

Written on 2026-11-12, after the 6.7 amendment and before any E2-B 3b, 3c or
row value was read. Each scorer was run on the development dry run first
(`D:\rang\outputs\e2-20261111-12-dryrun\post-dev`).

- **Gate 3c's oracle as committed is not matched in weights.**
  - `wsclean3c` (`e2_post.py`) images with the MS's WEIGHT_SPECTRUM. On
    `e2b.ms` that column ranges from 0.13 to 0.17 within a scan and from 1.1
    to 17 in others.
  - Rang's image stage passes `-unit-weights` (`data.weights: uniform`).
  - The gridder matches: WSClean 3.7's default is wgridder at 1e-4, which is
    rang's `image.wgridder_accuracy`.
  - This was found from the two argv lists, not from a 3c value.
  - Under 6.5's scorer-bug rule, both readings are reported, labelled:
    - "as committed" (`R/wsclean3c`);
    - "matched" (`R/wsclean3c-unit`). The new step `wsclean3c-unit` images
      RANG_CORRECTED_DATA with rang's FLAG after apply. It runs on the CASA
      copy with WEIGHT_SPECTRUM renamed away and a unit WEIGHT, so WSClean
      falls back to WEIGHT (W6). The renames are undone afterwards.
  - Development reading, as committed: dirty L∞/peak 0.11 (J1939−6342) and
    0.022 (J1331+3030).
  - Development reading, matched (`wsclean3c-unit` on the dry run's copy):
    - Imaging weights and flags are equal: WSCIMGWG 4904650.0106 in both,
      no FLAG_ROW outside rang's flags.
    - The MFS I peak is 14.4097 against 14.4079 Jy (1.2e-4 relative).
    - **Dirty L∞/peak is 0.050 (J1939−6342) and 0.022 (J1331+3030)**,
      largest on the image edge in output channel 6:

      | Field, image | Full image | 5 % border excluded | Inner two-thirds | Median |
      | --- | --- | --- | --- | --- |
      | J1939−6342, MFS | 8.5e-3 | 6.1e-4 | 2.6e-4 | 4.4e-5 |
      | J1939−6342, channel 6 | 5.0e-2 | 3.8e-3 | 1.1e-3 | 1.2e-4 |
      | J1331+3030, MFS | 3.3e-3 | 1.9e-4 | 7.6e-5 | 1.3e-5 |

    - Both imagers run wgridder at ε 1e-4, rang's frozen
      `image.wgridder_accuracy`. A0 measured its dirty bound (6.5e-8 to
      2.2e-7) at matched higher accuracy.
    - **Expected on E2-B, written before reading it: dirty L∞ not met** at
      1e-6. The other 3c measures as measured. Off-source |model| on dev
      was 1.58 (J1939−6342) and 3.16 (J1331+3030) against the 1.6 limit.
    - The region profile is reported beside, never as the gate.
  - The step's first version added the unit WEIGHT to the shared
    StandardStMan and removed it afterwards. casacore reads that table; rang's
    reader then refuses it ("StandardStMan column count mismatches the
    table"), found on the dry run's copy.
    - Reproduced on a 10-row table; a follow-up for rang's reader.
    - Fixed before any E2-B use: the unit WEIGHT gets its own storage
      manager, and the frozen copy's queued run was stopped before it
      started.
- **3c scorer** (`e2_score3c.py`): the measures and limits are listed in its
  docstring. **Q/Q₀ is not checked**: it needs both models predicted through
  one gridder on the MS. 3c is therefore reported at best as "met where
  checked", never as met.
  The compact-source gate is "not checked" below 3 matched sources (added
  before any 3c read: on dev it read met with n = 1, where the scatter is 0 by
  construction).
- **Visibility-domain rows** (`e2_rows_b.py`: 3C 286 parity, 1830−211; the
  transfer reuses its estimator):
  - Both arms apply with parang true, so the apply performs the derotation to
    the sky frame and the scorer adds none.
  - Development reading on LUNO scan 1 (parallactic angle −169°):

    | Column (both arms) | χ |
    | --- | --- |
    | MODEL_DATA | 32.6–33.0° (the model's 33.0°) |
    | DATA | 10–16° |
    | CORRECTED_DATA | 86–89° (rang and CASA within 0.1°) |

  - This frame difference is shared by both arms, so it cancels in parity.
    The transfer row's absolute χ will show it.
- **The χ offset, measured at 1.3–1.5 GHz** (scan 17 on the frozen CASA copy;
  dev scan 1 on the dry run's), written before the transfer row ran:

  | Scan | ψ (array centre) | Model χ | Corrected χ, rang and CASA | Offset |
  | --- | --- | --- | --- | --- |
  | Dev scan 1 | −169.2° | 32.7° | 88° | +55.0° |
  | Scan 17 | +146.4° | 30.0° | −3.2° | −33.2° |

  - On scan 17: model q +0.052, u +0.090; corrected q +0.099, u −0.011.
    Corrected |q| carries almost all of p, so this is a rotation, not a
    mirror (Q or U flipped).
  - The offset changes by −88.2° (≡ 91.8° mod 180) for Δψ = −44.4°. A
    residual +2ψ predicts 91.2° and −2ψ predicts 88.8°, so the data favour
    P removed with the wrong sign. Two scans cannot settle it.
  - Separate study, early reading, not an E2 measurement (2026-11-13,
    `research/chi-offset.md` on branch claude/chi-offset-80cb6a). ψ agrees
    with astropy to 0.07°, so P's sign is not the cause.
    - In the feed frame on scan 17, data q_f −0.049 against model +0.063,
      while u_f agrees (−0.087 against −0.083).
    - That fits a receptor angle near 0° rather than −90°, with Xf then
      matching U to the model: χ = −χ₀ + 2ψ − 90°. This predicts −10° and
      +79°; E2 saw −3° and +88°.
    - That study's simulation and LUNO tests are still running.
  - It is shared by rang and CASA, so it is the configured frame
    (RECEPTOR_ANGLE −90°, `feed_angle_rotation: -90`, parang true), not
    one package's apply.
  - **Expected for the transfer row:** χ near the own-scan −3° (the
    development Xf cannot remove a ψ-dependent rotation), so **not met** on
    χ; p inside [9.0, 10.1] %.
- **Transfer and leakage recipe, the same for both scans and arms:**
  1. A per-scan phase-only G (p, 60 s, parang), with the development K, G
     and B preapplied. It is solved on scan 17 against the 3C 286 model, and
     on scan 18 against 1934−638's.
  2. Development K, G, B, that G, and development Kcross, Xf and Df applied.
  - The development tables come from `e2b-dev.yaml` or
    `e2b-amended-dev.yaml`: `e2b.yaml` or `e2b-amended.yaml` with scans
    [1, 2], no secondary block, stages [flag, calibrate], and the gcal apply
    target dropped with the secondary block.
  - `e2_devtables.py` saves FLAG after calibrate as flag version
    `e2dev_<arm>_after_calibrate` for the CASA development copy.
  - Leakage only: scan 18's own amplitude-and-phase G is reported beside it.
    A phase-only G with scan 2's amplitudes would put the X/Y amplitude drift
    between scans into Q.
- **The amended arm's CASA input differs from the frozen arm's**
  (`e2_fvcmp.py`, `R_amended/flagversions-frozen-vs-amended.json`):
  - FLAG after rang's flag stage is identical.
  - FLAG after calibrate (the CASA copy's flags) differs in 5,916 of
    4.47e9 elements: 4,392 frozen only, 1,524 amended only.
  - So the amended arm gets its own CASA 3b run, `e2_casa3b.py` on its copy.
- **Transfer and leakage, the remaining choices** (`e2_transfer.py`,
  `e2_casa_xfer.py`, `e2_rows_b.py transfer`, `e2_leakage.py`):
  - **Where:** both arms run on the frozen CASA copy, `R/casa/e2b.ms`. It
    holds rang's model (RANG_MODEL_DATA, rang's solve model) and CASA's
    setjy MODEL_DATA.
  - **Flags:** FLAG is restored before every case from rang's flag-stage
    version (`rang_calibrate_*`: FLAG after rang's flag stage, identical in
    the frozen and amended arms; the own-half solves do not enter).
  - **Receptor angle:** rang's apply gets −90° explicitly, as the chain does.
    CASA reads the −90° written into the copy's FEED.
  - **Rang's arm** uses the chain's own calls and term specs
    (`core_pipeline.chain_terms`), unit weights and `average_time`, plus
    `average_freq` for the amended arm. A selftest must first reproduce
    RANG_CORRECTED_DATA at class C: the run's own tables applied by the
    library to scan 17.
  - **CASA's arm:**
    - Development tables from `e2_casa3b.py`'s calls (no secondary, no
      applycal), on a copy of `luno-dev.ms` carrying rang's development FLAG
      after calibrate.
    - On E2-B: gaincal of the per-scan G, then applycal with parang true.
    - One CASA run serves both arms when the two development flag versions
      are equal.
    - Measured equal (0 elements differ,
      `devtables/dev-flags-frozen-vs-amended.json`), and the flag-stage FLAG
      is identical in both arms. So CASA's transfer and leakage results are
      one run, reported beside both rang arms.
  - **Transfer measure:** the parity estimator in one bin, 1.3–1.5 GHz.
  - **Leakage measure:**
    - Image: WSClean 3.7 dirty IQUV MFS of J1939−6342 at gate 3c's size and
      weighting (MS weights; a ratio of one source).
    - Per Stokes Q, U, V: peak |P| within 3 beams of the I peak, over that I
      peak.
    - Gate: each ≤ 0.3 %.
- **Weights in 3b (stated, not changed):** rang solves with unit weights;
  CASA's arm (`e2_casa3b.py`, as `e1b_casa.py` and the LUNO validation) uses
  WEIGHT_SPECTRUM. On LUNO the weights were
  ruled out as the cause of the Gpol miss (6.1).

### 7.2 Gate 2b's flag rule (cause found on main)

- **Development slice:** CASA's applycal flagged extra parallel-hand cells
  where rang did not.
  - The cause is CASA's P term, not Df. With `parang=True` on linear feeds,
    P is a general 2×2 Jones, so CASA flags all four correlations where any
    one is flagged ([p-flag-spread.md](p-flag-spread.md), main merge
    `305fdf8`).
  - Main now has `apply.parang_flags`, default `spread` (CASA's rule). `none`
    is the frozen behaviour, and CORRECTED_DATA is bit-identical under both.
  - E2 runs on its frozen wheel, which has `none`.
- **On E2-B both settings give the same flags:** no cell there is partly
  flagged. Measured: CASA applycal's FLAG equals rang's in all 408,827,131
  compared cells (`g2b-applycal.json`, `flag_elements_differ` 0).

### 7.3 E2-B frozen arm, gates as frozen

Outputs are in `D:\rang\outputs\e2-20261111-20-e2b` (R).

| Gate | Result | Reading |
| --- | --- | --- |
| 1 | met | exit 0, every stage in the receipt; wall 6,195 s (`e2b-timed.json`) |
| 2a | met | FLAG, FLAG_ROW hashes equal the input's after restore (272,916 rows) |
| 2b casacore | met | 27 tables, every column |
| 2b CASA listobs, flagmanager | met | – |
| 2b CASA applycal (class C) | **not met** | flags equal (0 of 408,827,131 cells differ; 7.2); **42 cells** over 11 float32 eps of the cell max: 11.0–25.6 eps (median 11.6; 36 of them ≤ 15 eps), max relative 0.22. They lie on field 1 scan 18 (30) and field 2 scans 19–20 (12), mostly in channels 1862–1879, 17 on baseline (35, 55) |
| 2b WSClean -niter 0 | met | CORRECTED_DATA and MODEL_DATA |
| 2b dask-ms (QuartiCal's reader) | met | 4 datasets, 272,916 rows; met on its rerun after a helper named `daskms.py` shadowed the package (first reading: import error, a scorer bug) |
| 2c | met | 459 FITS files parse |
| 3a | met, **exact** | Tricolour against rang's flag stage: 0 of 1,117,863,936 cells differ, every scan. 6.5 expected a few ulp cells |
| 3b | **not met** | below |

**Gate 3b** (`g3b.json`, CASA 6.7.6.14, 18 tasks, 0 errors, 3,672 s; class B
as 6.5):

| Term | Result | Reading |
| --- | --- | --- |
| K | met | \|Δτ\| median 0.00072 ns, p95 0.0047, max 0.0057 |
| KCROSS | met | 0.00053 ns |
| Xf | met | median 0.047°, p95 0.60°, max 3.9° |
| Df | met | median 1.7e-5, p95 2.2e-4 |
| Gpol | **not met (expected)** | median 0.278°, p95 2.17° against 0.1° |
| fcal K G B composite | **not met** (expected met) | median 1.14e-3, p95 1.52e-2 against 7e-4 / 3e-3; flags 0 differ |
| gcal K F B composite | **not met** | median 1.12e-3, p95 1.51e-2 |

- Reported only, not gated:
  - G: relative 1.4e-4 median, 0.0074°.
  - B: relative 1.1e-3 median, p95 7.0e-3, 0.062°; 5,242 solution flags
    differ.
  - Gsec: 3.6e-4.
  - F: 2.3e-4.
  - Df: 8,670 solution flags differ.

**Rows (frozen arm):**

| Row | Result | Reading |
| --- | --- | --- |
| 3C 286 parity | **met** | 6 bins scored: \|Δp\| ≤ 0.030 points, \|Δχ\| ≤ 0.077° |
| 1830−211 | **not met** | 7 bins: I within 0.025 %, \|Δp\| ≤ 0.062 points; \|Δχ\| up to 13.1° in 4 bins |

- 1830−211's polarisation is 0.02–0.09 %, so its χ is mostly noise. The row
  is still read as frozen.
- **3C 286's absolute χ on scan 17 is −0.5° to −4.2°, the same in both arms,
  against the model's 33°** (the development scan read 86–89°). The offset
  differs between scans, so the frame difference of 7.1 depends on
  parallactic angle and is shared by rang and CASA. The transfer row, which
  is judged on absolute χ, measures it.

### 7.4 E2-B frozen arm: matched 3c, transfer and leakage rows (2026-11-13)

Resumed from 8.3 on 2026-11-13. Records: `results/e2-acceptance/e2b/frozen/`
(R's text records; the transfer cases in `transfer/`, `transfer-amended/`,
`transfer-casa/`) and `e2b/devtables/`. Each step a shared heavy_lock job.

**Gate 3c, matched oracle** (`R\g3c-matched.json`, unit weights as rang's
`-unit-weights`; 7.1). Not met, as expected in 7.1:

| Measure | As committed (8.1) | Matched | Limit |
| --- | --- | --- | --- |
| Dirty L∞ / peak, max over images | 0.032 | 3.5e-3 (J1331+3030), 2.9e-3 (J1833−2103), 1.2e-3 (J1939−6342) | 1e-6 |
| — inner two-thirds (reported) | 0.032 | 3.0e-5, 2.4e-5, 2.2e-5 | – |
| Compact sources, median ratio, scatter | 37, 0.9936, 1.4 % | 35, 0.9942, 0.97 % | within 0.5 %, ≤ 1 % |
| Δα, 12 sources ≥ 50σ | 0.023 | 0.0097 | ≤ 0.05 |
| Off-source \|model\| ratio (J1939, J1833, J1331) | 1.28, 1.70, 2.29 | 1.27, 1.67, 2.27 | ≤ 1.6 |
| Unpolarised Q, U, V (J1939−6342) | not met (V) | met | – |
| Q/Q₀ | not checked | not checked | – |

- Matched 3c: "met where checked" is false. Δα and the unpolarised test are
  met; dirty L∞, the compact-source median (0.58 % from 1) and off-source on
  J1833−2103 and J1331+3030 are not.

**Library selftest** (`transfer/selftest.json`): the run's own K, G, B, Gpol,
Kcross, Xf, Df applied by the library to J1331+3030 scan 17 reproduce
RANG_CORRECTED_DATA and RANG_FLAG **bit for bit**: 171,242,769 cells, 0 over
class C, max relative difference 0, 0 flag elements differ. The transfer
cases' route is the chain's.

**Leakage scorer, development rerun** (fixed field and beam, 8.3 item 3):
J1939−6342 (OBJECT asserted), beam 19.1 px, Q/I 0.073 %, U/I 0.071 %,
V/I 0.008 %: met on the dry run's slice.

**CASA development tables** (`e2_casa_xfer.py dev`, CASA 6.7.6.14): 11 tasks,
0 errors, on a copy of `luno-dev.ms` carrying rang's frozen development FLAG
after calibrate (equal to the amended one, 7.1).

**Rows** (one bin 1.3–1.5 GHz for the transfer; 73.6 % of scan 17's cells
unflagged in every arm):

| Row | Rang frozen | Rang amended | CASA | Limit | Verdict |
| --- | --- | --- | --- | --- | --- |
| 3C 286 transfer, p | 9.668 % | 9.672 % | 9.677 % | [9.0, 10.1] % | p met in all arms |
| 3C 286 transfer, χ criterion | not met | not met | not met | \|χ − 33.1°\| ≤ 7° | **not met** as frozen (all arms) |
| 1934−638 leakage, phase-only G (gated): Q/I, U/I, V/I | 0.302 %, 0.288 %, 0.053 % | 0.302 %, 0.288 %, 0.053 % | 0.298 %, 0.288 %, 0.053 % | each ≤ 0.3 % | **rang not met** (Q by 0.002 points), CASA met |
| 1934−638 leakage, scan 18's own ap G (reported beside) | 0.026 %, 0.029 %, 0.054 % | 0.026 %, 0.029 %, 0.054 % | 0.025 %, 0.028 %, 0.053 % | – | – |

- The χ criterion is reported as frozen and not interpreted here. The
  absolute polarisation angle belongs to the chi-offset task
  (`research/chi-offset.md`, branch `claude/chi-offset-80cb6a`). The three
  arms agree in χ to 0.04°.
- Rang's phase-only leakage is 0.004 points of Q/I above CASA's: rang 0.0018
  points over the limit, CASA 0.0025 points under it. With scan 18's own amplitudes the
  leakage is about 10 × lower in all arms. So the gated number is mostly the
  X/Y amplitude drift between the development scans and scan 18 (7.1). The
  verdict stays as frozen: not met.
- The amended arm's development tables (with `average_freq`) change nothing
  above the fourth digit.

**Scorer fixes found on E2 data (no value had been read):**
- `e2_transfer.py`'s first `xfer17` run stopped with a 27.8 GiB allocation:
  the script did not pass the chain's memory budget
  (`core_chunks.budget(...).chain()`, as `core_pipeline` passes it to
  `cal_chain.run`). Fixed in b5fc631. Nothing had been written, and the
  rerun ran the same case.
- `e2_leakage.py` writes `OUT/<label>.json`, the same name as
  `e2_transfer.py`'s case record. The rang leak cases' solve and apply
  records were therefore overwritten by the leakage result. The tables
  (`<case>-Gscan`) are kept. Values are unaffected; this is recorded only.

**Flags left on `R\casa\e2b.ms`:**
- Before the cases, the FLAG there was the CASA 3b chain's (`e2_casa3b.py
  run` ends with its applycal). It was saved as flag version
  `e2_casa_applycal` and restored after the CASA cases (272,916 rows).
- CORRECTED_DATA on J1331+3030 scan 17 and J1939−6342 scan 18 now holds
  CASA's transfer and leakage applies (the last case, `leak18ap`, on scan 18),
  not the 3b chain's. E2_XFER holds rang's last cases.
- J1833−2103 (scans 19-20) is unchanged.

**Disk, freed 2026-11-13** (each one's records committed first, 27d9684,
`results/e2-acceptance/dev-archive/`; D: 299 → 595 GB free):
- this task's outputs `e2-20261111-12-dryrun` (79 GB), `e2-20261110-11-avg`
  (77 GB, including `luno-dev.ms`), `e2-20261111-13-freqavg` (74 GB);
- the CASA development copy `DEV\casa-dev\casa\luno-dev.ms` (78 GB; tables
  kept);
- F2's `f2-20261106-04-sim-test` (48 GB; owner item 32, results on main).
- **Kept:** `f2-20261106-02-sim-train`, `-01-sim-v` and
  `f3-20261110-03-sim-test`, because branch `fp-f4-flagger`'s `f3flag.py`
  reads them.
- The deleted dry-run copy `e2-20261111-12-dryrun\b\luno-slice.ms` is the one
  `chi-offset-20261113-04-qf` read (its readings are kept there).

**Departure from 6.2's order (dated 2026-11-13, before any E2-A cube was
decoded).**
- 6.2 has E2-B archived and `e2b.ms` deleted before E2-A starts.
- `D:\rang\data\e2-b\e2b.ms` is kept on the coordinator's word, for E3. (E3
  note 10.12 names `e3-20261111-input\e2b.ms` as E3-B's input; the
  coordinator decides which copies stay.)
- `e2a.ms` is built and verified while the amended arm's post chain runs.
  D: had 590 GB free before the build. The build is about 225 GB and the
  amended CASA copy about 215 GB with WSClean temporaries. If D: runs short,
  `e2a.ms` is deleted first: it rebuilds from the zarr in about an hour.
- E2-A's rang arm still waits for 6.2's start rule: 470 GB free after the
  build.

### 7.5 E2-B amended arm (6.7, `calibrate.average_freq`), gates as frozen

Outputs: `D:\rang\outputs\e2-20261112-21-e2b-amended` (RA). Records:
`results/e2-acceptance/e2b/amended/`. The post chain was resumed on
2026-11-13 from wsclean0, and the same scorers were used as for the frozen
arm. The frozen arm stays the record.

| Gate | Amended | Frozen (7.3, 7.4) |
| --- | --- | --- |
| 1 | met: exit 0, 6,249 s, 49.1 GB | met: 6,195 s, 49.0 GB |
| 2a | met (272,916 rows) | met |
| 2b casacore, CASA listobs and flagmanager, WSClean, dask-ms | met (30 tables; 4 datasets) | met |
| 2b CASA applycal (class C) | **not met**: 40 cells over (max 25.2 eps, relative 0.21), flags exact (0 of 408,827,848) | not met: 42 cells |
| 2c | met (459 FITS) | met |
| 3a | met, **exact** (0 of 1,117,863,936 cells) | exact |
| 3b | **not met** | not met |
| 3c as committed | **not met** | not met |
| 3C 286 parity | **met**: 6 bins, \|Δp\| ≤ 0.024 points, \|Δχ\| ≤ 0.055° | met |
| 1830−211 | **not met**: \|Δχ\| up to 13.0° (I within 0.025 %, \|Δp\| ≤ 0.061 points) | not met |
| Transfer, leakage | as 7.4 (the amended development tables) | 7.4 |

**Gate 3b, amended** (`RA\g3b.json`; CASA 6.7.6.14, 18 tasks, 0 errors, 4,782 s
with the queue):

| Term | Amended | Frozen |
| --- | --- | --- |
| K | met, median 0.00072 ns | the same |
| KCROSS | met, 0.00031 ns | 0.00053 ns |
| Xf | met, median 0.027°, p95 0.28° | 0.047°, 0.60° |
| Df | met, median 1.5e-5, p95 2.2e-4 | 1.7e-5, 2.2e-4 |
| Gpol | **not met**: median 0.124°, p95 0.94°, max 1.21° (limit 0.1°) | 0.278°, 2.17° |
| fcal K G B composite | **not met**: median 1.14e-3, p95 1.52e-2 | the same to 3 digits |
| gcal K F B composite | **not met**: median 1.12e-3, p95 1.51e-2 | the same |

- As 6.7 expected, the key moves Gpol about halfway to the limit:
  0.278° → 0.124°, against LUNO's 0.250° → 0.108°. It does not meet it.
- The composites do not move. Their miss is not Gpol's.

**Gate 3c as committed, amended** (`RA\g3c-as-committed.json`): not met.
- Compact sources: 36, median 0.9955, scatter 1.46 %.
- Δα: 0.018 (met).
- Dirty L∞: 0.032, 2.8e-3, 4.9e-3.
- Off-source ratios: 1.61, 1.68, 2.19.
- Unpolarised V: not met.
- Q/Q₀: not checked.

**Gate 3c matched, amended** (`RA\g3c-matched.json`, oracle images made
2026-11-14 03:16): not met, like the frozen arm's.
- Dirty L∞: 3.5e-3 (J1331+3030), 2.9e-3 (J1833−2103), 1.2e-3 (J1939−6342).
  Over the inner two-thirds: 3.0e-5, 2.4e-5, 2.2e-5.
- Compact sources: 38, median 0.9946, scatter 1.07 %.
- Δα: 0.022 (met).
- Off-source ratios: 1.30, 1.66, 2.23.
- Unpolarised Q, U, V: met.
- Q/Q₀: not checked.

**E2-B summary (both arms, gates as frozen).**
- Met: 1, 2a, 2b (casacore, listobs, flagmanager, WSClean, dask-ms), 2c, 3a
  (exact), 3C 286 parity, and the transfer row's p.
- Not met: 2b CASA applycal (42 and 40 cells over class C), 3b (Gpol, both
  composites), 3c (as committed and matched), 1830−211 (χ), the transfer
  row's χ criterion, and rang's phase-only 1934−638 leakage (0.302 %).
- Not checked: Q/Q₀.

**Resume repairs (post hoc, recorded):**
- The amended arm's `restore` stopped because `RA\columns-before.json` was
  missing. The frozen arm wrote that file before its run; the amended arm's
  launch did not. It was copied from R's: the amended run started on `e2b.ms`
  after the frozen chain's last drop, and `R\g3a-restore-drop.json` lists the
  same 23 columns (`RA\columns-before.provenance.txt`). Its restore then met
  2a. FLAG had already been restored from `rang_original` before the stop.
- `e2_casa3b.py run` needs `casa3b-spec.json` from its `spec` step. That
  step was run before it (as for R).
- `D:\rang\data\e2-b\e2b.ms` is back to the converter's columns and FLAG:
  2a met, 51 GB.

## 8. Paused 2026-11-13 07:00 (owner's order: stop everything)

All queued heavy_lock tickets were cancelled while waiting; no job was
running, so none stopped mid-write. Runs:

| Name | Directory |
| --- | --- |
| R (frozen) | `D:\rang\outputs\e2-20261111-20-e2b` |
| RA (amended) | `D:\rang\outputs\e2-20261112-21-e2b-amended` |
| DEV | `D:\rang\outputs\e2-20261112-22-devtables` (`frozen\`, `amended\`, `casa-dev\`) |

The scripts are in `research/results/e2-acceptance-scripts/`; run them from the
worktree with `.venv\Scripts\python.exe`, each under `heavy_lock.py run --slots
8 --mem G`. The scorers were committed in 9c2c478 before any of their values
was read.

### 8.1 Gates read (frozen arm, 7.3)

- 1: met.
- 2a: met.
- 2b: casacore, listobs, WSClean and daskms met; CASA applycal not met.
- 2c: met.
- 3a: exact.
- 3b: not met (Gpol 0.278°, composites 1.1e-3 / 1.5e-2).
- Rows: parity met; 1830−211 not met.
- 3c as committed (`R\g3c-as-committed.json`): not met.
  - Compact sources: 37, median 0.9936, scatter 1.4 %; not met.
  - Δα: 12 sources, 0.023; met.
  - Dirty L∞: up to 0.032; not met.
  - Off-source: 1.28, 1.70, 2.29; not met.
  - Unpolarised Q/U/V: not met.

### 8.2 Done, not yet read

- Matched unit-weight 3c oracle images are in `R\wsclean3c-unit\` (rc 0).
  `unit-on.json` has `flag_row_not_all_rang_flag` 0, and rang reads the copy.
- DEV tables for both arms (rc 0); their after-calibrate flags are equal.
- Amended arm, steps done: timed run, gate 1, archive, wcs, casacore, casa-ro.

### 8.3 Not started, or must be rerun

Resumed 2026-11-13: items 1-5 done (7.4). Item 6 runs; item 7 follows it.
Item 7's deletion of `e2b.ms` is withdrawn: E3-B's timed pass needs the
data (coordinator, 2026-11-13).

1. **Matched 3c score:**
   `e2_score3c.py R R\wsclean3c-unit R\g3c-matched.json`.
2. **Selftest.** The first try failed on an import, before it touched the MS;
   the import is fixed. Before the selftest or any transfer case, first save
   CASA's applycal FLAG on `R\casa\e2b.ms`:
   `core_writeback.backup_flags(ms, "e2_casa_applycal")`.
   Then run `e2_transfer.py selftest R R\transfer`; it must meet class C.
3. **Leakage dev test (rerun).** The first try imaged the wrong field and had
   no beam; both are fixed, and its output is kept in `leakage-dev-wrongfield`.
   Command:
   `e2_leakage.py D:\rang\outputs\e2-20261111-12-dryrun\post-dev\casa luno-slice.ms RANG_CORRECTED_DATA ...\post-dev\leakage-dev dev-rang`.
   Check that OBJECT is J1939-6342 and the beam is above 0.
4. **CASA dev tables (not started):**
   `e2_casa_xfer.py dev D:\rang\outputs\e2-20261110-11-avg\luno\luno-dev.ms DEV\frozen\rang-run e2dev_frozen_after_calibrate DEV\casa-dev`.
5. **Transfer and leakage rows,** run in this order. Each case restores the
   flag-stage FLAG first.
   1. Frozen arm: `e2_transfer.py rang R DEV\frozen\rang-run R\transfer --case xfer17`,
      then `e2_rows_b.py transfer R\casa\e2b.ms E2_XFER FLAG R\transfer\xfer17-row.json`.
   2. Frozen arm, leak18p and leak18ap: run `e2_transfer.py` with that case, then
      `e2_leakage.py R\casa e2b.ms E2_XFER R\transfer <case>`.
   3. Amended arm: the same with `DEV\amended\rang-run --average-freq`.
   4. CASA arm, once: `e2_casa_xfer.py rows R DEV\casa-dev <case>`, then score
      CORRECTED_DATA and FLAG.
6. **Amended post chain:** rerun `e2_post.sh` on RA (the arguments are in
   `RA\post.log`) from the step after casa-ro. Then run its CASA 3b on its own
   copy and score3b, 3c (as committed and matched), and the parity and 1830 rows.
7. **Close out E2-B:** write the rest of section 7, the tool-timings rows, the
   archive and a full check-all. The last full check-all was stopped by the
   coordinator after it hung; rerun it with `pytest --timeout 600`. The one
   before failed only on the timing test
   `test_heavy_lock_queue::test_waiters_acquire_in_ticket_order`, which passes
   alone. Then delete e2b.ms, its copies and luno-dev, and report D: free
   (486 GB at 00:40).
8. **E2-A:** follow 6.2. The wheel venv is
   `C:\Users\gijsm\Build\tmp\20261111-e2-wheel\venv`; keep it and the
   `~/Build/tmp` E2 folders until E2 ends.

The χ-offset session reads `R\casa\e2b.ms` only after it is told "done".
Send that after step 5.

## 9. E2-A

### 9.1 The Measurement Set (built and verified 2026-11-13)

`e2_convert.py build D:\rang\data\e2-a\e2a.ms` from ms1_primary MAIN_4
(scan 9), ms1_target MAIN_4 (scan 10) and ms1_primary MAIN_5 (scan 11), then
`verify` and `e2_flaghash.py`. Each step was a shared heavy_lock job at
critical priority. Records: `results/e2-acceptance/e2a/`; logs in
`D:\rang\outputs\e2-20261113-30-e2a`.

- 1,047,614 rows (98,332 + 850,950 + 98,332), 61 antennas, 4,096 channels;
  fields J1939−6342 and ESO137-001. This matches 6.2.
- Build 1,304 s, verify 706 s, hash 30 s. The MS is 194 GB.
- `verify`: 0 differing cells in DATA, WEIGHT_SPECTRUM and FLAG (17,164,107,776
  each), and 0 in every row column.
- Gate 2a's reference: FLAG SHA-256 `1aec438d…3baa`, FLAG_ROW `b528098a…89d6`
  (`flaghash-input.json`).

### 9.2 Start rule for the rang arm (not met on 2026-11-13; met 2026-11-14)

- D: has 400 GB free after the build. 6.2 needs 470 GB, so the arm is
  **70 GB short**, and the amended arm's CASA copy (about 185 GB) is still to
  come.
- The run waits, as 6.2 says, and the shortfall goes to the coordinator.
- What would free enough, none of it deleted here:
  - `D:\rang\data\e2-b\e2b.ms` (118 GB), once the amended arm's `restore` and
    tricolour have run. E3-B's input is `e3-20261111-input\e2b.ms`.
  - `R\casa\e2b.ms` (221 GB), once chi-offset no longer reads it.
  - The amended arm's own CASA copy, after its scores.
- The rang arm runs under `e2_timed.py`, exclusive, from the frozen wheel venv
  `C:\Users\gijsm\Build\tmp\20261111-e2-wheel\venv` (6.4), on this MS.
- **Met on 2026-11-14 03:19: D: had 475 GB free.** This followed two
  deletions, both after the amended arm's records were committed (784b714):
  - `RA\casa\e2b.ms` and its flag versions (189 GB; CASA's tables kept);
  - `RA\wsclean3c`, the amended arm's as-committed oracle images (11 GB;
    the scores are in `g3c-as-committed.json`).
- Before the run, `columns-before.json` was written. The run was then
  queued: exclusive, critical priority, host CPU load 6 % at queueing. The
  command was `e2_timed.py e2a-timed.json -- python -m rang.core_cli run
  e2a.yaml e2a.ms` (log `e2a-run.log`).
- `D:\rang\data\e2-b\e2b.ms` (51 GB, restored) and `R\casa\e2b.ms` are kept.

### 9.3 Polarisation sealed (coordinator, 2026-11-13; before any E2-A run)

- The chi-offset study found a defect in the simulation:
  `calibrate.average_time: true` with Xf `combine: scan` across scans at
  different parallactic angles puts Xf 78° off. `e2a.yaml` has both. E2-B's
  Xf is solved on a single scan.
- A fix and a pre-registered amended E2-A arm are being prepared on branch
  `xf-avg-fix`. The amended arm is `e2a-amended.yaml`, the fix on and nothing
  else changed. It runs after the frozen arm, on the same MS, from the
  calibrate stage.
- The frozen arm runs as frozen and stays the record.
- **Sealed:** every E2-A polarisation result (Xf, χ, leakage) is unread until
  the amended arm is committed.
- **Withdrawn the same day (coordinator's correction, before any E2-A run).**
  E2-A is not exposed. `e2a.yaml` has no polcal block and no Xf, KCROSS,
  Gpol or Df term (checked: none of them appears in the file), and `e2a.ms`
  has no polcal scans. The earlier reading came from `e2b.yaml`. There is no
  amended E2-A arm and no seal. E2-A runs as frozen.

### 9.4 The rang arm: interrupted, no result (2026-11-14)

This attempt gives no E2-A result. It is recorded so the next attempt starts from it.

- The run (`e2_timed.py`, exclusive, critical priority) started at 03:19 local (01:24 UTC). Its records are in `D:\rang\outputs\e2-20261113-30-e2a` and `D:\rang\data\e2-a\e2a.ms.rang-run` (`state.json`).
- Stages finished:

  | Stage | Wall time |
  | --- | --- |
  | flag | 2,556 s |
  | calibrate | 4,545 s |
  | apply | 599 s |
  | image | 5,386 s |

  The image stage at `auto_threshold` 3.0 and mask 5σ cleaned 684,794 components in 5 major cycles.
- **Selfcal round 1 ran into the component cap.** Its image used CARACal's selfcal values: mask 10σ, `clean_cutoff` 0.5σ, `-niter 1000000`. It ran from 07:11 to 15:38 local, 30,615 s wall, and stopped at exactly 1,000,000 components after 5 major cycles (Q/Q0 3.68e-2). That is 5.7 times the first image's wall time.
- Round 2 had started when a power cut at about 17:30 local (2026-11-14) rebooted the host and killed the run. Nothing of round 2 survives.
- **Deleted 2026-11-14 20:00 local (owner's approval).** The run's columns had filled D:’s last space and made WSL read-only, so `e2a.ms` (578 GB, 386 GB of it the run's columns), `e2a.ms.flagversions` and `e2a.ms.rang-run` were deleted. The run's JSON and log records (13 files) are archived in `research/results/e2-acceptance/e2a-interrupted/`. The ESO137 zarr source and its manifest remain, and the next attempt rebuilds `e2a.ms` with `e2_convert.py build` and `verify` (1,304 s + 706 s on 2026-11-13).
- **Wall time is not clean in any case.** The coordinator ran lock-free full checks (5 threads) at 10:52-11:52 UTC and 12:15-13:40 UTC. Per-stage CPU seconds were not captured: the timer process died with the run.
- **Next attempt (v0.3.0, coordinator's judgement):** as frozen, round 1 alone costs about 8.5 h of the host, so two rounds and the final image come to about a day. Rerunning E2-A as frozen requires a pre-registered amendment.
  - Candidate change: a selfcal `niter` or depth that keeps the CARACal stop rule reachable, such as CARACal's own niter for these images.
  - The amendment is written and committed before the rerun. The run above stays as the record of the frozen settings' cost.

### 9.5 Amendment 2026-11-15: selfcal image depth for the rerun (committed before any rerun step)

Branch `e2a-rerun`, from main `8eb5b4d`. Nothing of the rerun had been built or run when this was committed.
**Post hoc** with respect to the interrupted run's cost and logs (9.4). Its author read the archived stage
summaries, `state.json` and the two GeMClean logs: σ per major iteration, component counts, wall times. No
gate was computed on that run and no score was read. The rerun stays on scans 9-11 by the coordinator's
decision in 9.4 (an interruption, not a failure under 6.6), so 6.6's reserve is not used.

**Why the frozen depth cannot finish.** Each selfcal image used C5b's CARACal values (owner item 29): mask
10σ, then 6σ; clean to `clean_cutoff` 0.5σ inside it; multiscale (gated); `niter` 1,000,000. Round 1's image
stopped at exactly 1,000,000 components after 30,615 s, 5.7 × the image stage. Its threshold
(2.8e-5 Jy, 0.5 × σ) was not reached.
- 9.4's candidate, "CARACal's own niter", changes nothing. CARACal's `img_niter` is 1,000,000
  (c5b-selfcal-masks.md section 1), which is what ran. Whether WSClean with these values would also
  stop on the cap is an inference, not measured.
- The remaining difference from CARACal's default is multiscale. CARACal's selfcal image is Högbom, and
  owner item 29 keeps multiscale as the gated setting. That multiscale at 0.5σ is what makes the cap bind
  is an inference too: no Högbom run at this depth exists.
- At about 30,615 s per image, selfcal's three images alone take about 25 h. The 30,615 s is also inflated: both
  lock-free full checks of 9.4 (10:52-11:52 and 12:15-13:40 UTC) fall inside round 1's image
  (05:11-13:38 UTC).

**The change (one key group, nothing else).** [e2a-rerun.yaml](results/e2-acceptance-scripts/e2a-rerun.yaml)
is `e2a.yaml` with `selfcal.cleanmask_method`, `cleanmask_thr` and `clean_cutoff` removed, plus a header.
Every selfcal image then takes the image section unchanged (`core_config.selfcal_image_settings` with empty
lists), which is A0 rule 6: automatic mask 5σ, clean to 3σ.
- A0 rule 6 says "This holds for every imager" and binds rang and the oracle chain in E2 (appendix A). The
  frozen selfcal images departed from it under item 29, so the amendment returns them to the A0 rule.
- Its cost on this data is measured: the image stage stopped on threshold at 684,794 components in
  5,386 s, before both overlap windows.
- **This overrides owner item 29's "CARACal's values in E2-A's configuration" for the selfcal images.** It
  needs the coordinator's acceptance before launch (For the coordinator).
- **Accepted by the owner, 2026-11-15** (relayed by the coordinator, before any rerun step): A0 rule 6
  for the selfcal images, overriding item 29, labelled post hoc as above.
- Stage hashes: flag, calibrate, apply and image are unchanged, because their sections are byte-equal.
  Only selfcal's hash changes.

**Hypothesis and decision rule (frozen now).**
- H: under rule 6, each of selfcal's three images (rounds 1 and 2, and the final image) stops on threshold
  below `niter`, at about the image stage's cost.
- Read: per image, the stop reason and component count from `gemclean.log`, and its wall time.
- If an image still stops on `niter`, that is recorded as frozen and the run is not retuned. Gate 1 is
  read on the exit code as before.
- Gates, tolerances, scorers and oracles are unchanged (6.5, appendix A). The self-calibration row compares
  image 1 (CORRECTED_1GC) with the final image at the same rule 6 depth. Under this amendment, selfcal's
  image 1 has the image stage's settings on a copy of the same column.
- 6.5's expectation for self-calibration (C5's model absorption, item 29) stands.

**Run conditions (amended).**
- **Wheel:** the frozen one, unchanged: `C:\Users\gijsm\Build\tmp\20261111-e2-wheel\venv`, wheel SHA-256
  `2d222c60…ee2f` with `freeze-2.txt`'s imaging extra (6.4).
- **MS path (deviation from 6.2):** `D:\rang\outputs\e2a-20261115\e2a.ms`, rebuilt from the same zarr
  groups (9.1) and verified against 9.1's records (9.8). Main's extension ran the converter, not the
  frozen wheel. Its `core_ms_write` is the frozen wheel's apart from read-side additions, and the
  discriminating checks are `verify`'s 0 differing cells and the FLAG/FLAG_ROW hashes.
- **Host:** exclusive heavy lock, as 6.4. **No lock-free job may run on the host during the run**, the
  coordinator's full checks included. `e2_diskguard.py` (9.6) samples the host's CPU load and process
  count every 60 s, durably, so an overlap is visible in the record.
- **Interruption:** a power cut, a host failure or a disk halt (9.6) gives "interrupted", not a gate-1
  failure, as in 9.4. The same command resumes it after any interrupted write-back is restored:
  `rang-core run` skips finished stages whose hash is unchanged. Gate 1 is then reported as "met with
  one resume after <cause>", labelled, and wall time per stage as measured. **Not tested:** a resume
  after a kill in the middle of a stage on this MS; the write-back journal (W1) is what should allow it.

**What changed on main since the frozen wheel, and whether it is in the rerun.** All three are **out**,
because the frozen wheel stays. None is on E2-A's path in any case:

| Change | Where | E2-A's path | In the rerun |
| --- | --- | --- | --- |
| Parallactic angle follows casacore (`parallactic_angle_casa`, `720c8de`) | e2b-misses.md 9.15-9.16 | Not evaluated: `e2a.yaml` has no polcal term (`calibrate.polcal.terms: []`) and `apply.parang: false` (`config.resolved.json`). K, G and B do not call it. Gate 2b's CASA applycal runs with `parang=False` too | out (no effect either way) |
| GeMClean joined-IQUV auto-mask (as WSClean radler) | e2b-misses.md 9.21-9.22 | Stokes I, `join_polarizations: false`. The Stokes I auto-mask is in the frozen wheel and ran in 9.4 | out (no effect) |
| Chunk-task API and local executor (`core_tasks`, issue #3) | chunk-task-api.md | `data.processes` defaults to 1, in process. The frozen wheel predates it, and its timing runs are still open | out |

### 9.6 Disk budget and stop rule (2026-11-15)

Units are GiB (2^30 bytes), as `shutil.disk_usage` and `du` report them.

- One cell column is 1,047,614 rows × 4,096 × 4 = 17,164,107,776 cells.
- A complex64 column is 127.9 GiB, WEIGHT_SPECTRUM (float32) 63.9 GiB and FLAG (bit-packed) 2.0 GiB.
- A flag version is 2.0 GiB, bit-packed: e2b.ms's versions measure 535 MiB at 272,916 rows.
- The run directory holds images, tables and logs. A 4,096², 8-channel image set is about 3 GiB, and
  5 GiB per imaging run is budgeted.
- Write-back adds columns in place (`ensure_column`, TiledShapeStMan) and makes no transient copy, so the
  peak is the end state.

| Stage | Creates | New GiB | MS + run dir after |
| --- | --- | --- | --- |
| build (`e2_convert.py`) | DATA, WEIGHT_SPECTRUM, FLAG, row columns, subtables | 194 (measured 9.1) | 194 |
| flag | flag versions `rang_original`, `rang_flag_*` | 4 | 198 |
| calibrate | MODEL_DATA (setjy), version, tables | 130 | 328 |
| apply | CORRECTED_DATA, version | 130 | 458 |
| image | images | 5 | 463 |
| selfcal | CORRECTED_1GC (copy of CORRECTED_DATA), version, 3 images. MODEL_DATA and CORRECTED_DATA are rewritten in place | 145 | **608** |

9.4's run matches this: 578 GB MS, 386 GB of it the run's columns.

**Dropped or reused.**
- MODEL_DATA and CORRECTED_DATA are already reused: selfcal rewrites them in place.
- None of the four complex columns can be dropped. MODEL_DATA is calibrate's and selfcal's model, and gate
  2b's WSClean and QuartiCal read it. CORRECTED_DATA is apply's output, selfcal's output and gate 2b's
  input. CORRECTED_1GC is selfcal's input in every round and the row's image 1. DATA is the input.
- `apply.column: CORRECTED_1GC` with `image.column: CORRECTED_1GC` only skips the copy (about 600 s).
  Selfcal still creates CORRECTED_DATA, so the peak is the same. Not adopted.
- WEIGHT_SPECTRUM (64 GiB) is never read by the rang arm, which uses `data.weights: uniform` and
  `-unit-weights`. Dropping it is a converter change to the verified input, though, and the oracle copies
  use it. Not adopted, and the run would still be short without it.
- Flag versions of 2 GiB each are not worth deleting.

**Start rule (replaces 9.2's 470).** Free space on D: right before launch must be at least the chain's
writes, 414 GiB, plus the 150 GiB floor plus a 40 GiB margin for other sessions and WSL's `ext4.vhdx`
during an 8-12 h run: **605 GiB**. Before the build, that is **799 GiB**. 9.2's 470 had no floor, and in
9.4 the other sessions took about 75 GiB during the run.

**It does not fit today.**
- D: had 508 GiB free at 13:00 on 2026-11-15, so after the build it has 314 GiB.
- That is **291 GiB short** of the start rule. With no space freed, the chain would take D: to about
  -100 GiB.
- No configuration change in the frozen chain closes this. The fix is disk.
- Candidates (sizes by `du` today; none deleted here, and each deletion needs the coordinator or owner):

| Path | GiB | What it is |
| --- | --- | --- |
| `D:\rang\outputs\e2-20261111-20-e2b\casa\e2b.ms` (+ `.flagversions`) | 222 | E2-B frozen arm's CASA copy (8.3, 9.2; chi-offset read it; 2b was re-scored on an ext4 copy, e2b-misses 9.24) |
| `D:\rang\data\e2-b\e2b.ms` (+ `.flagversions`) | 55 | E2-B input, restored; rebuildable from the zarr (34 GiB, kept) |
| `R\wsclean3c`, `R\wsclean3c-unit` | 22 | E2-B 3c oracle images, scored |
| WSL `D:\wsl\Ubuntu\ext4.vhdx` | 135 reclaimable | file 303 GiB, 168 GiB used inside (`df`). Compacting needs `wsl --shutdown`, which stops every WSL session |
| `outputs\20261104-speed`, `20261103-gemclean-heldout`, `e1-20261109-03`, `e3-20261111-input` | 69, 56, 52, 51 | other tasks' data (E3-B's input among them) |

- E2-B's own three rows free 299 GiB. That leaves 613 GiB at launch and about 199 GiB at the end of the
  run, so it meets the rule **for the rang arm's run (gate 1) only**. Compacting the vhdx adds margin.
- E: (464 GiB free) is not used, because rang's large data stays on D:.
- **Deleted 2026-11-15 (owner's approval; the coordinator deleted them, after the rebuild of 9.8):**
  - `D:\rang\outputs\e2-20261111-20-e2b\casa\e2b.ms` and `.flagversions`;
  - `D:\rang\data\e2-b\e2b.ms` and `.flagversions`;
  - `R\wsclean3c` and `R\wsclean3c-unit`. Their small `.out` and `.json` logs are kept.
  - WSL's `ext4.vhdx` is now sparse and trimmed. Its allocated space returns only after an
    administrator `Optimize-VHD`, which the owner runs.
  - **D: had 645.4 GiB free at 14:55 local** (`(Get-PSDrive D).Free / 1GB`; the coordinator read
    600.7 GiB earlier), above the 605 GiB start rule, with `e2a.ms` (194 GiB) already built.

**The post chain (6.5) does not fit as written** (resolved by the in-place order of 9.9).
- `e2_post.py` runs `copy` before `restore`: the whole MS and its flag versions go to `R\casa\`, about
  598 GiB for E2-A against 218 GiB for E2-B. `prep` then adds RANG_FLAG (2 GiB) on the copy, and CASA
  `applycal` writes CORRECTED_DATA (128 GiB).
- That is about 728 GiB on top of the run's 608, while the original still exists. With E2-B's 299 GiB
  freed, D: would need about 680 GiB more than it will have. Freeing everything listed above does not
  cover it either.
- **Proposed here; the owner chose it, and 9.9 implements it in a corrected form:** an E2-A in-place
  order for `e2_post.py`.
  1. Every read of rang's columns runs on `e2a.ms` itself: casacore, casa-ro, wsclean0, daskms, the 3c
     WSClean images, and QuartiCal's self-calibration gains on CORRECTED_1GC against MODEL_DATA, with no
     output column.
  2. CORRECTED_1GC is dropped (−128).
  3. CORRECTED_DATA is renamed RANG_CORRECTED_DATA, and CASA applycal writes a new CORRECTED_DATA (+128).
  4. `compare`, then `restore`.
  The peak stays at about 610 GiB, inside the start rule's figure, and no copy is made.
- The oracle arms run after `restore`, when rang's columns are dropped: CASA's K G B with its own
  MODEL_DATA and CORRECTED_DATA, then WSClean. They peak at about 450 GiB.
- `e2_diskguard.py` does not wrap the post chain. Its steps should run inside it too.
- Without that change, gate 2b's CASA applycal row is "not checked" on E2-A for disk (6.5's rule).

**Stop rule (new harness, flagged).**
[e2_diskguard.py](results/e2-acceptance-scripts/e2_diskguard.py), tested in
`tests/test_e2_diskguard.py`, wraps the timed command inside the lock.
- Every 5 s it reads D:'s free space. Below **165 GiB** it stops the command's own process tree. psutil's
  terminate is already a hard kill (TerminateProcess) on Windows, so there is no grace period here. It
  writes a `halt` record and exits 75.
- The 15 GiB above the floor covers one poll at the measured write rate (a 128 GiB column in apply's
  599 s, 0.22 GiB/s, about 1 GiB per poll) and other sessions' writes.
- `--start-min-free-gib 605` refuses to start below the start rule. It is checked when the exclusive lock
  is granted, not when the run was queued; the launch script's earlier check only refuses to queue. It
  touches no other process.
- Every 60 s it appends a durable JSON line: free GiB, tree RSS, tree CPU seconds, host load and host
  process count. These are the per-stage records that 9.4 lost with `e2_timed.py`.
- A halt is an interruption under 9.5 and is resumed by the same command. The guard does not change the
  timing method: `e2_timed.py` still runs inside it.

### 9.7 Wall time, memory and lock (estimate, from 9.4's records)

- **Flag, calibrate, apply, image: 13,086 s, measured in 9.4** (2,556 + 4,545 + 599 + 5,386). It ran
  01:24-05:03 UTC, before both overlap windows, so it is clean.
- **Selfcal (estimated):**
  - copy into CORRECTED_1GC: about 600 s, as apply's column write;
  - three images at rule 6: about 5,400 s each, 16,200 s;
  - two rounds of predict, solve and apply. Round 1's took under 6,700 s: it ran from 13:38 UTC, and
    round 2 had started before the cut at about 15:30 UTC. Each round writes MODEL_DATA and
    CORRECTED_DATA (about 600 s each, as apply), so 1,500-6,700 s per round.
  - Selfcal total: **19,800-30,200 s**.
- **Whole run: about 33,000-43,000 s (9-12 h)**, plus the post chain (6.5), which runs separately and
  shared.
- **Lock: exclusive** (6.4, A0 rule 7). Memory: the image-stage peak was not captured in 9.4. G2's
  pilot at 512 channels peaked at 19.7 GB in GeMClean, calibrate plans within `data.memory_limit_gb` 8,
  and smoke b peaked at 8.3 GB. Exclusive use of the 63 GB host covers this, and the guard's records
  give the measured peak.
- **Priority:** critical, as 9.2, only on the coordinator's word.
- **Launch** (Git Bash, from the worktree):
  `PRIORITY=critical bash research/results/e2-acceptance-scripts/e2a_rerun_launch.sh`.
  [e2a_rerun_launch.sh](results/e2-acceptance-scripts/e2a_rerun_launch.sh) checks the start rule and writes
  `columns-before.json`. It then runs heavy lock exclusive → `e2_diskguard.py` (165 GiB) → `e2_timed.py` →
  `rang-core run e2a-rerun.yaml e2a.ms` from the frozen wheel venv. Logs go to
  `D:\rang\outputs\e2a-20261115\e2a-run.log`, `e2a-guard.jsonl` and `e2a-timed.json`.

### 9.8 The rebuilt MS (built and verified 2026-11-15, after 9.5-9.7 were committed at `2cefa7f`)

`D:\rang\outputs\e2a-20261115\e2a.ms`, built by
[e2a_rerun_build.sh](results/e2-acceptance-scripts/e2a_rerun_build.sh). It runs `e2_convert.py build`
and `verify`, then `e2_flaghash.py`, from the worktree's `.venv` (main `8eb5b4d`'s extension, built by
`check_all.py --quick`). Each step is a shared heavy-lock job inside `e2_diskguard.py`. Records are in
[results/e2-acceptance/e2a-rerun/](results/e2-acceptance/e2a-rerun/).

- **Equal to 9.1's archive:**
  - `e2a.ms.convert.json`: groups, row ranges, attributes, 1,047,614 rows, 61 antennas, 4,096 channels
    and both fields, apart from `seconds`.
  - `verify.json`: 0 differing cells in DATA, WEIGHT_SPECTRUM and FLAG (17,164,107,776 each) and 0 in
    every row column.
  - FLAG SHA-256 `1aec438d…3baa` and FLAG_ROW `b528098a…89d6`: gate 2a's reference is unchanged.
  - The main-table column set equals 9.4's `columns-before.json`, 23 columns.
  - `du` is 194 GiB.
- **Cost:**

  | Step | Wall | Booked | CPU | Peak tree RSS |
  | --- | --- | --- | --- | --- |
  | build | 822 s (9.1: 1,304 s) | 4 slots, 8 GB | 0.93 cores | 0.56 GiB |
  | verify | 777 s | 4 slots, 8 GB | 0.91 cores | 0.67 GiB |
  | hash | 30 s | 2 slots, 4 GB | – | 0.16 GiB |

  The converter is single-threaded, so 1 slot and 2 GB would be the honest booking next time.
- `rang-core config check e2a-rerun.yaml e2a.ms` from the frozen wheel venv:
  "valid for flag, calibrate, apply, image, selfcal" (`config-check-rerun.txt`).
- **Smoke:** `e2_dryrun.py a-rerun` ran from the frozen wheel venv on A1 small (shared, 4 slots) and met
  6.4's rule.
  - Exit 0, 26 s wall, 1.35 GiB peak; all five stages done.
  - Every selfcal image ran with `-auto-mask 5.0 -auto-threshold 3.0` and stopped on threshold.
- **Launch nesting smoke:** shared lock (4 slots) → `e2_diskguard.py --start-min-free-gib 300` →
  `e2_timed.py` → `e2_dryrun.py a-rerun`, the launch's chain with the smoke in place of the run. It
  gave rc 0, 25 s and 1.26 GiB, with both records written (`nesting-smoke-*.json`).
  `e2_post.py columns-before` ran from the worktree `.venv` on the new MS and listed 23 columns.
- **Revised 2026-11-15 14:10, before any run** (the amendment's change itself is unaltered):
  - the start rule is now checked inside the lock;
  - the post-chain disk paragraph is added;
  - two statements are relabelled as inference, and the untested resume is labelled.
- An attempt 0 at 13:20 failed in 5 s, before writing anything, because the extension was not yet built.
  Its logs are `attempt0-*` in the output directory.
- **D: after the build: 313 GiB free, 292 GiB short of 9.6's start rule (605).** The run is ready to
  launch once that space exists and the coordinator accepts 9.5. Both conditions were met later on
  2026-11-15 (9.5, 9.6).

### 9.9 Gate 2b in place on E2-A (implemented 2026-11-15, before any run; owner's choice)

`e2_post.py` gains `ORDER_INPLACE`, which E2-A uses in place of `ORDER`.
- **Steps, in order:** gate1, archive, wcs, casacore, casa-ro, wsclean0, daskms, then
  **`prep-inplace`, `applycal-inplace`, `compare-inplace`, `snapshot-inplace`**, then restore and
  tricolour. There is no `copy` step.
- **The proposal in 9.6 was corrected in one point before any code ran.** With selfcal, rang's apply
  output is **CORRECTED_1GC**: selfcal copied apply's CORRECTED_DATA into it before overwriting
  CORRECTED_DATA with its own output. Gate 2b compares CASA applycal with rang's 1GC tables (K1, G1,
  B1) against rang's apply output, so that is the column to compare. Comparing CORRECTED_DATA, as E2-B's
  order does, would compare against selfcal's output.
- `inplace_plan` reads the run directory.
  - If `selfcal-input.json` records a copy of this run's apply output (same column and apply
    timestamp), rang's column is CORRECTED_1GC. RANG_FLAG is then the flag version that selfcal saved
    at its start, which is FLAG after apply.
  - Otherwise rang's column is apply's own column, and RANG_FLAG is FLAG as it stands (E2-B's
    reading).
  - FLAG is reset from the version saved before apply, as in E2-B's `prep`.
- `prep-inplace` renames rang's column to RANG_CORRECTED_DATA and MODEL_DATA to RANG_MODEL_DATA, and
  adds RANG_FLAG (2 GiB).
  - It refuses to run unless RECEPTOR_ANGLE is already −90°, which it is in ESO137's stores (6.2), so
    FEED is not written.
  - CASA `applycal` then writes CORRECTED_DATA. With selfcal, that column exists and holds rang's
    selfcal output, which is overwritten in place, so no new 128 GiB column appears. Every read of it
    (casacore, wsclean0, daskms) comes earlier in the order.
- `compare-inplace` and `snapshot-inplace` are E2-B's `compare` and `snapshot` with the MS's own
  directory mounted as `/c`. `restore` then drops every column not in `columns-before.json` (RANG_*
  included) and restores FLAG from `rang_original` (gate 2a).
- **Peak:** the run's 608 GiB plus 2 GiB for RANG_FLAG.
- **Must also run before `prep-inplace`, not written here:** E2-A's own reads of CORRECTED_1GC and
  MODEL_DATA, which are gate 3c's WSClean images at the image stage's settings and QuartiCal's
  self-calibration gains. After `prep-inplace` they read RANG_CORRECTED_DATA and RANG_MODEL_DATA.
  `e2_post.py wsclean3c` is E2-B's (IQUV, `-join-polarizations`) and reads CORRECTED_DATA, so it does
  not serve E2-A.
  Both are written in 9.10, after `snapshot-inplace`.
- **Tests:** `tests/test_e2_post_inplace.py`, 8 tests.
  - The plan, with and without selfcal, and a stale copy refused.
  - The order: no copy, the reads before prep, restore and tricolour last.
  - The CASA steps mount the MS itself.
  - `PREP_INPLACE_PY` run against a casacore stand-in: renames, RANG_FLAG from selfcal's version, FLAG
    from the version before apply, refusal of another RECEPTOR_ANGLE.
  - Not tested here: the scripts inside the containers against a real MS. The first real run is E2-A's
    post chain.

### 9.10 Amendment 2026-11-15: E2-A's gate 3c and self-calibration oracles in the in-place order (written after the rerun started, before any E2-A output was read)

Branch `e2a-post`, from main `948efd0`. First committed as `341b711` at 15:28 local on 2026-11-15, while the
rang arm's timed run (9.7, started 14:41) was in its flag stage; revised before any step ran (below). **Frozen before any step below runs.** Its author read no
E2-A output: no receipt, stage summary, log, table, image or column of the rerun. Read on the host: D:'s free
space, and one record of `e2a-guard.jsonl` (15:07: 641.4 GiB free, the run's tree at 3.5 GiB, host load 60 %).
Gates, tolerances and scorers of 6.5 are unchanged, except the self-calibration oracle's form, which is
labelled below. Code: [e2_post.py](results/e2-acceptance-scripts/e2_post.py) (`ORDER_INPLACE`) and the launcher
[e2a_post.sh](results/e2-acceptance-scripts/e2a_post.sh). Tests: `tests/test_e2a_post_reads.py`, 19 tests (21 cases) on
stand-ins.

**Order (adds to 9.9).** gate1, archive, wcs, casacore, casa-ro, wsclean0, daskms, prep-inplace,
applycal-inplace, compare-inplace, snapshot-inplace, then:

| Step | What | Lock (slots, GB) |
| --- | --- | --- |
| `drop-corrected-inplace` | CASA's CORRECTED_DATA (2b's applycal output) removed, after compare and snapshot have read it (−128 GiB); refuses unless compare's record shows exit 0, compared cells and no applycal error | 1, 2 |
| `qc-avg` | native, frozen wheel venv: the self-calibration oracle's inputs (below) → `R\qc-selfcal\` (about 5 GiB) | 4, 16 |
| `qc-selfcal` | per round: a small MS on WSL ext4, QuartiCal 0.2.7, the small MS deleted; class B → `R\qc-selfcal.json` | 1, 8 |
| `unit-on-a` | gate 3c's matched state, E2-B's `UNIT_PY`: renames and a unit WEIGHT, no data written | 1, 2 |
| `wsclean3c-a-dirty` | WSClean 3.7, `-niter 0`, `-j 2` → `R\wsclean3c-a\` | 2, 6 |
| `wsclean3c-a-clean` | WSClean 3.7 cleaned, `-j 4` | 4, 10 |
| `unit-off-a` | the matched state undone; `restore` now refuses while any `E2_*` column exists | 1, 2 |

then restore and tricolour. `bash e2a_post.sh [FIRST] [LAST]` runs each step as a shared heavy-lock job
inside `e2_diskguard.py` (165 GiB floor), and logs rc and wall time to `R\post-steps.log`. The earlier steps'
bookings are in the launcher too, at one job each: wsclean0 4/8, daskms 8/24 (its 8 dask workers),
snapshot 1/12, tricolour 8/24. They are not re-measured here.

**Why after prep-inplace, not before (9.9 allows both).**
- After prep-inplace, FLAG after rang's apply exists as RANG_FLAG, so 3c's matched state is renames only.
  Before it, FLAG would have to be rewritten (2 GiB, over 9p).
- Disk: WSClean writes its reordered data beside the run. That is about 850,950 target rows × 4,096 channels ×
  12 B = 39 GiB for the dirty run, and about 65 GiB with the model for the clean run (an estimate, Stokes I).
  The chain leaves about 60 GiB above the floor (below). Only CASA's CORRECTED_DATA can be given back, and
  only after compare and snapshot.

**Disk (GiB; estimates from 9.6's arithmetic).**
- End of the run: 645.4 − 414 ≈ 231 free, less other sessions' writes.
- `archive` copies the run directory (images and tables, about 12-20). 9.6 did not budget this.
- prep-inplace +2. snapshot-inplace +8: its npz holds FLAG and RANG_FLAG packed, 4.3 each.
- Lowest point before the drop: about 200 free, 35 above the floor.
- After the drop: about 330 free. qc-avg +5. The ext4 MS takes about 2.4 of WSL's `ext4.vhdx` per round;
  vhdx growth is not returned before an `Optimize-VHD`. WSClean clean takes 65 while it runs, and its FITS
  about 3.
- Lowest point after the drop: about 255 free.
- **No ext4 copy for WSClean.** The target rows of RANG_CORRECTED_DATA and FLAG are about 106 GiB, written
  into the vhdx for good. Before the drop that is below the floor. After the drop, with WSClean's temporary
  files also on ext4, it ends at about the floor. So WSClean reads the MS over 9p, which E2-B measured as
  4.4 times slower (9.17, 9.18 of e2b-misses).

**Gate 3c's oracle (as frozen).**
- Input: RANG_CORRECTED_DATA, which is CORRECTED_1GC, the image stage's input. Selfcal copied it there
  complex64 to complex64. FLAG is rang's FLAG after apply, and weights are unit, as `-unit-weights`.
- Settings: the image stage's own gemclean argv (`R\rang-run\image\summary.json`), passed to WSClean
  argument for argument (`wsclean_argv`; tested on the interrupted run's archived argv): 4096² at 3″, Briggs
  0.5, `-niter` 1e6, `-mgain` 0.9, `-auto-threshold` 3, `-auto-mask` 5, `-multiscale`, 8 joined channels,
  `-fit-spectral-pol` 2, `-wgridder-accuracy` 1e-4, `-field 1`. Added: `-gridder wgridder`, as E2-B's
  matched oracle.
- Dropped:
  - `-unit-weights` (the matched state does that);
  - `-scans 9,10,11` (the step checks that the list selects every row of the field);
  - **`-average-channels 8`, which WSClean 3.7 does not have**: `rang-wsclean-native:3.7` answers
    "Unknown parameter: average-channels", where it accepts `-no-small-inversion` (checked 15:50 with no
    MS; its `--help` lists neither). WSClean grids all 4,096 channels, where
    GeMClean grids 512 averaged ones. 6.5's "512 channels" cannot be matched this way.
- **Expected before reading (stated):** rang's image carries the bandwidth smearing of 1.67 MHz channels
  and WSClean's does not. β = Δν/ν · r/θ is about 1.3e-3 · r/θ, about 0.25 at 0.35° from the centre for a 6.5″
  beam. So compact-source ratios rang/WSClean are expected to fall with radius by a few per cent at the
  edge of the scored region. Dirty L∞ includes the same term. Not computed further.
- **`-no-small-inversion` is not used.** Neither the frozen protocol nor an amendment says to.
  - E2-B's A4b (e2b-misses 9.12) found WSClean's small inversion was all of 3c's dirty edge difference:
    8.1e-8 without it at ε 1e-6, and 2.0e-6 to 2.2e-5 at ε 1e-4 (9.17).
  - The same edge term is expected in E2-A's dirty L∞ as frozen.
  - The step takes a `nosi` argument that writes into `R\wsclean3c-a-nosi\`. It runs only under a later
    amendment (the owner's decision under A4b), as a labelled seen reading.
- Cost (estimate):
  - E2-B's dirty IQUV runs took 2,030-2,485 s over 9p for 272,916 rows, at 0.2 cores. With 3.1 times the
    target rows, each E2-A run should spend about 6,000-8,000 s reordering. The clean run adds deconvolution:
    GeMClean's image stage took 5,386 s in 9.4.
  - Memory: WSClean on G5's ESO 137 pilot (4096² at 3″, multiscale) peaked at 5.11 GB, hence the 10 GB
    booking.
- Scoring E2-A's 3c (dirty L∞ and compact-source ratios over the inner 0.7°) needs an E2-A reading of
  `e2_score3c.py`, which is written for E2-B. It is not written here.

**The self-calibration row's oracle (amended form, labelled).**
- **As frozen (6.5): "gains class B against QuartiCal 0.2.7 on the same MODEL_DATA and solint, unaveraged
  (stated)". It cannot run here.**
  - One solution interval is 120 integrations × 1,830 baselines × 4,096 channels × 4 correlations, or
    3.6e9 samples.
  - Data and model in complex64 plus float32 weights come to 72 GB per QuartiCal chunk. WSL has 44 GB and
    the host 63.
  - Under 6.5's rule that form is "not checked (memory)". `qc-selfcal.json` records it (`unaveraged_form`).
- **Amended form (written now, before any reading).** QuartiCal solves the time-averaged arrays that
  rang's `selfcal.average_time` solves (CASA's estimator, e2-average-time.md 1).
  - Per round, per (interval, baseline), qc-avg takes the unit-weighted means of CORRECTED_1GC and of
    that round's model over unflagged samples.
  - Rows with FLAG_ROW and autocorrelations are left out. An empty cell is flagged, and an averaged row
    with no live source row is flagged as a row.
  - The averaging is written in `e2_post.py` (`qc_layout`, `QcSums`) and does not call rang's `cal_chunks`
    or `time_bins`. Tests check it against a per-row loop and against rang's `time_bins`.
  - A small MS on WSL ext4 holds the averages: 7,320 rows (4 intervals × 1,830), taking template rows'
    metadata from the MS read-only, and TIME set to each interval's mean time.
  - QuartiCal runs with C5's options (`examples/check_c5.py` `QC_OPTIONS`) and `G.type` phase (Sp) or
    diag_complex (Sa), selfcal's refant, `G.time_interval=1`, `G.freq_interval=0`, `input_ms.time_chunk=1`,
    and the term's stop rule. The keys were checked against the container's `argument_schema.yaml`.
- What this tests and what it does not.
  - It tests rang's averaged solve (kernel, flags, intervals, reference-free products) on the averages.
  - It does not test the averaged-against-unaveraged difference that "(stated)" was to state.
  - **This changes the oracle's form after the protocol was frozen. It is labelled post hoc with respect
    to 6.5, and was written before any E2-A output.** The coordinator accepts or rejects it before
    `qc-avg` runs. If it is rejected, the row's gains are "not checked (memory)".
- **Models.** The MS holds only the last round's model.
  - qc-avg predicts each round's model again from its model images, with the frozen wheel's predictor.
    It uses `core_model.write_model_data`'s rows, blocks of `gemclean_block_rows` rows, cells and unmapped
    channels.
  - **Control C-model:** the last round's prediction equals RANG_MODEL_DATA in every element of every
    target cross row.
  - The last round always sums the MS's own column. If C-model is not met, the earlier rounds are void.
- **Flags.**
  - Round 1 uses selfcal's flag version, which is FLAG after apply.
  - Round k + 1 uses that version ORed with the apply flags of rounds 1 to k. Those are recomputed from
    the rounds' stores: all four correlations wherever either antenna's gain is invalid.
  - **Control C-flags:** the recomputed count equals each round's `cells_flagged_after −
    cells_flagged_before` in selfcal's summary.
  - **Control C-bins:** qc-avg's interval times equal rang's stored gain times within 1e-6 s, or the
    step refuses.
- **Measure and tolerance (C5's G2, frozen there):** the gauge-free products g_p g_q* (p < q, per hand)
  where both arms hold a valid gain. Relative difference median ≤ 7e-4 and p95 ≤ 3e-3. QuartiCal's
  gain times must equal rang's within 1e-6 s. Solutions flagged in either arm (rang's gain clip included)
  are not compared, and are counted.
- **Expected before reading:** near class A. Both arms solve the same averaged arrays up to float64
  summation order before the complex64 cast, and C5 found 1e-15 on identical inputs.
- Cost (estimate):
  - qc-avg reads 2 × 104 GiB natively (36 GB in 102 s in 9.20 of e2b-misses) and runs two predictions
    of 850,950 rows. The prediction time on E2-A is not recorded (9.4 lost it), so 1-2 h is a guess.
    Memory: 2 × 4.3 GB of sums plus 2 × 1.1 GB of predictions.
  - qc-selfcal: about 1.5 GB read over 9p per round, and QuartiCal on 30 M row-channels per round. C5 took
    28-71 s at 3.5 M. So about 10-30 min per round.

**Also fixed here (found while writing):** `snapshot-inplace`'s script read FLAG and RANG_FLAG whole. On
E2-A that is 69 GB each, beyond WSL's memory. It now reads in blocks of 4,000 rows, with the same output (tested).

**Consequence of the drop.** After it, a second 2b reading (6.5 allows a re-read after a scorer bug)
needs CASA applycal to write a new 128 GiB column over 9p, which is 9.20's failure in e2b-misses. Gate 2b's
compare and snapshot are therefore read before the drop step runs, and the coordinator accepts the drop.

**Not tested:**
- `QC_MS_PY` and every container step against a real MS, and the WSL `$HOME` mount. The first real run is
  E2-A's post chain.
- The guard's halt on a container step: it kills the `wsl.exe` tree. Whether the docker container then
  stops is not tested, so for WSClean's reorder writes the 165 GiB floor rests on the disk budget above.
- The launcher ran only in its `DRY=1` mode (all 20 steps visited with a stdin-draining stand-in, tested).

**Revised 2026-11-15, before any step ran** (after `341b711`): the drop's compare gate; the launcher's stdin
from `/dev/null` (wsl.exe could drain the step list and end the chain after one step) and its `DRY` mode;
WSClean's `-average-channels` checked by running it; the timestamps; the drop's consequence; the untested
guard halt.

**Host incident while writing (recorded, nothing of the run read or changed).** At 15:34 a mistaken shell
command started the launcher for real instead of `DRY=1`. It queued one shared ticket (`gate1`, 1 slot)
behind the run's exclusive lock and created an empty `post-steps.log` in `D:\rang\outputs\e2a-20261115`.
It was stopped within minutes, before the lock was granted: no step ran, nothing was read. The four
processes it had started were stopped, the empty log was deleted, and the dead ticket is removed by
`heavy_lock`'s stale-ticket rule.


**Coordinator decisions on 9.10, 2026-11-15, before any 9.10 step ran and before any E2-A output was read**
(the owner delegated judgement):
- **QuartiCal form:** accepted as amended, post hoc. QuartiCal runs on the time-averaged inputs,
  averaged independently in numpy, against C5's class B, with the round-2 prediction control. The frozen
  unaveraged form is recorded as "not checked (memory)": it needs 72 GB per interval, and WSL has 44.
- **Drop step:** accepted. CASA's CORRECTED_DATA is dropped only after compare's record shows exit 0 and
  compared cells. This rules out a second gate 2b reading on E2-A; that limitation is recorded.
- **Gate 3c channels:** run as frozen. WSClean images 4,096 channels and GeMClean 512. The scorer must
  report the inner two-thirds next to the full image, so channel-smearing toward the edge is visible. This
  caveat goes in the reading.
- **`-no-small-inversion`:** the frozen run is the primary reading, without it. After the primary is
  scored, one `nosi` dirty run adds a second, seen reading, as A4b motivates.

**Gate 3c's E2-A scorer and the nosi steps (written 2026-11-15 after the decisions above, during the
rerun, before any E2-A image existed).**
- [e2_score3c_a.py](results/e2-acceptance-scripts/e2_score3c_a.py), Stokes I, one field, A0 6.1's 3c
  tolerances on the two measures 6.5 names for E2-A:
  - **Dirty L∞ (gated, full image):** max |rang − WSClean| / WSClean's peak per output channel and MFS,
    ≤ 1e-6. Reported beside: the inner two-thirds (the decision above), the image without a 5 % border,
    within 0.7°, and the largest median.
  - **Compact sources (gated within 0.7° of the centre, appendix A's field limit):** E2-B's candidate,
    isolation, beam and fit rules (`e2_score3c.py`). Median ratio within 0.5 % of 1, robust scatter
    ≤ 1 %, not checked below 3 sources. Reported beside: the same over the inner two-thirds and the full
    image, sources too near the edge counted, and the median ratio in radial bins (0-0.35-0.7-1.0-1.4-2.5°).
  - Reported, not gated: spectral index (≥ 50σ within 0.7°) and off-source |model|, with A0's 0.05 and
    1.6 shown. Not checked: Q/Q₀ and MODEL_DATA against `-predict`. Not applicable: the unpolarised Q, U, V
    measure.
- Steps in `ORDER_INPLACE`, before `unit-off-a` (restore drops RANG_CORRECTED_DATA, so nothing that reads
  it can come after): `score3c-a` (→ `R\g3c-a.json`, the primary reading; 1 slot, 12 GB), then the optional
  `wsclean3c-a-nosi-dirty` (refuses until `g3c-a.json` exists; 2 slots, 6 GB, about 39 GiB of reorder
  files while it runs) and `score3c-a-nosi` (dirty only, → `R\g3c-a-nosi.json`, seen; 1 slot, 8 GB).
  The launcher's `NOSI=0` skips the two.
- Tests: `tests/test_e2a_score3c.py` (4, synthetic image sets in both arms' file names) and 2 more in
  `tests/test_e2a_post_reads.py`. The launcher's dry-run test is now opt-in (`E2A_LAUNCHER_DRY=1`), so no
  test runs the launcher during E2-A.

### 9.11 E2-A's oracle arms and rows: estimators frozen 2026-11-16 01:45, before any of their values was read

Branch `e2a-score`, from main `fca103a` (9.10 merged). The rang arm ended at 01:02: rc 0, 37,272 s, peak
RSS 45.4 GB, D: 240 GiB free (coordinator). The in-place post chain (`e2a_post.sh`, NOSI=1) started at 01:36.
**Read before this commit:** gate 1, 2c, and 2b's casacore and casa-ro records, as the chain printed them
(all met). None of them depends on anything below. **Not read:** every 3b, 3c and row value, and every
post-chain record after casa-ro.

**What 6.5 needs that 9.9-9.10 did not write.** Gate 3b's CASA arm, and the rows (flux scale, target,
self-calibration rms). They run after the post chain's `restore` and `tricolour`, on `e2a.ms` itself, with no
copy (9.6). Code: [e2_casa3b_a.py](results/e2-acceptance-scripts/e2_casa3b_a.py),
[e2_score3b_a.py](results/e2-acceptance-scripts/e2_score3b_a.py),
[e2_rows_a.py](results/e2-acceptance-scripts/e2_rows_a.py); launcher
[e2a_rows.sh](results/e2-acceptance-scripts/e2a_rows.sh), one shared heavy-lock job per step inside
`e2_diskguard.py` (165 GiB). Tests: `tests/test_e2a_rows.py` (5).

| Step | What | Lock (slots, GB) |
| --- | --- | --- |
| `casa3b-prep` | FLAG and FLAG_ROW natively from rang's FLAG after calibrate (the version rang's apply saved, after A) | 1, 4 |
| `casa3b-run` | CASA 6.7.6.14: setjy SR2016 on J1939−6342 with `usescratch=False` (virtual model: no 128 GiB column over 9p), then K0 inf, G0 ap inf (K0), B0 inf combine scan fillgaps 70 solnorm false (K0, G0), K1 60s (G0, B0), G1 ap 60s (K1, B0), B1 as B0 (K1, G1); E2-B's common arguments (K without uvrange, `>150` on G and B, minsnr 3, minblperant 4, rang's refant list, refantmode flex) | 4, 16 |
| `score3b` | **gated:** K1 by its limit (median ≤ 0.01 ns, p95 ≤ 0.03 ns) and the fcal composite of K1, G1, B1 (class B: relative median ≤ 7e-4, p95 ≤ 3e-3; E2-B's `composite`, every 8th time). Reported: G1, B1, K0, G0, B0 alone and the K0 G0 B0 composite | 1, 8 |
| `selfcal-score` | **Self-calibration rms:** off-source rms of selfcal's image 1 and its final image (MFS restored); met when after ≤ 1.02 × before | 1, 8 |
| `target-prep` | FLAG from rang's FLAG after calibrate; CORRECTED_DATA added natively as a copy of DATA, so CASA writes into an existing column (9.20's failure was creating one over 9p) | 1, 8 |
| `target-applycal` | CASA applycal of CASA's K1, G1, B1 to the target, with rang's apply entry (gainfield nearest, nearest, J1939−6342; interp linear; calwt false; calflag) | 2, 12 |
| `target-unit-on`, `-off` | unit weights for WSClean (WEIGHT_SPECTRUM renamed away, a unit WEIGHT); CASA's FLAG kept | 1, 2 |
| `target-wsclean` | WSClean 3.7 cleaned at the image stage's argv (`wsclean_argv`, as 3c) on CASA's CORRECTED_DATA → `R\oracle-a\` | 4, 10 |
| `target-score` | **Target rows**, rang's image stage against this oracle: compact ratios within 0.7° (3c's candidates and fit; median within 1 %, robust scatter ≤ 1.5 %, not checked below 3); off-source rms rang ≤ 1.2 × oracle and dynamic range rang ≥ 0.8 × oracle | 1, 12 |
| `flux-prep`, `flux-run` | FLAG from rang's flag stage; `rang-core run` (frozen wheel) of `e2a-rerun.yaml` with `data.scans: [9]` and `run.stages: [calibrate]`; its run directory moved to `R\flux-run` | 1, 4; 4, 16 |
| `flux-score` | **Flux scale:** scan 11's J1939−6342 cross rows corrected in memory by flux-run's K1, G1, B1 (rang's library apply, interp linear); per 100 MHz bin from the first channel, the median over channels of I / SR2016 I; met when within 2 % in every bin with ≥ 10 % unflagged cells. The full run's tables on the same rows are reported as context, not as the row | 4, 12 |
| `final-restore` | every column not in `columns-before.json` dropped, FLAG from `rang_original`, hashes against 9.1 | 1, 4 |

**Estimators fixed here (not in 6.5's text).**
- **Off-source rms** (self-calibration and target rows): the MFS restored images compared, within 0.7° of the
  centre (appendix A's field limit). Outside the mean of the images above 5σ, where σ is 1.4826 MAD of the
  first image's residual (selfcal) or the oracle's residual (target) over the inner two-thirds, dilated by
  2 beams; rms is the root mean square. Dynamic range is the peak within 0.7° over that rms.
- **Stokes I per channel** (flux scale): the mean over cross rows of Re((XX + YY) / 2) over cells whose four
  correlations are unflagged after the apply (E2-B rows' rule); SR2016 from `rang.fluxstd` (FS1 validated it
  against CASA).

**Smoke on A1 small** (`D:\rang\outputs\e2a-score-smoke-20261116`, a fresh `e2_dryrun.py a-rerun`, 19 s):
- `e2a_post.sh` gate1 through tricolour: rc 0 on every step.
  - qc-avg: control C-model met (61,440 cells, 0 elements differ); C-flags equal (round 2: 22,420).
  - QuartiCal on the averages agrees to 1e-16 in both rounds.
  - WSClean refused A1 small's `-scans 1,4,23` (the field has more scans) as written. For the smoke only, `-scans`
    was removed from the run's archived image summary, so its 3c scores mean nothing by design.
  - g2a met.
- `e2a_rows.sh`: rc 0 on every step after two fixes (target field from the image summary; the smoke's flux
  overrides).
  - On A1 small, the full run's tables give I / SR2016 0.99-1.00 per bin. Scan 1's tables applied to scan 23
    give about 0 (A1 small's gains change between scans), a transfer failure. That is what the row measures,
    not a bug.

### 9.12 Gate 3a on E2-A: Tricolour as frozen did not run (memory); a per-scan reading on the primaries (2026-11-16 15:00, before it ran)

- As frozen (`e2_post.py tricolour`, the whole MS, 16 threads): Tricolour 0.2.1 stopped at 9 % after 336 s
  with `FiledesIO::read ... Cannot allocate memory` while reading DATA through dask-ms
  (`R	ricolour.out`). It packs a scan's visibilities in memory. Target scan 10 is 850,950 rows × 4,096
  channels × 4 correlations, 111 GB of complex64, and WSL has 44 GB. E2-B's whole MS was 35 GB.
  The step's own restore ran (`g3a-restore.json` met: FLAG and FLAG_ROW equal 9.1's hashes).
- **Under 6.5's rule, gate 3a is "not checked (memory)" on E2-A as frozen.**
- **Added reading, labelled post hoc** (`e2_post.py tricolour-scans`): Tricolour once per primary scan
  (`-sn 9`, then `-sn 11`, 8 workers), the same strategy and options. Cells are compared with rang's flag
  stage on those scans' rows only (→ `R\g3a-scans.json`), then FLAG is restored (`g3a-scans-restore`). The
  target scan stays not checked. Lock: 8 slots, 32 GB.

## For the coordinator

(written at the end)
