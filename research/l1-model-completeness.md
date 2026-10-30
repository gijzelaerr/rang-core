# Rang L1-M: the PKS 1934−638 field model (model completeness)

Protocol frozen 2026-10-30 on branch `l1m-field-model` (from main `5965d37`),
before any campaign code was written. Task L1-M of [big-plan.md](big-plan.md),
first wave 3 item after P5; recommendation 1 of
[literature-2024-2026.md](literature-2024-2026.md).

Status: **implemented and measured.** The premise is corrected (the stored
model is a field model). Field against point: held-out MSE 0.981 (better).
Field against stored: 1.031 (worse). TV changes by at most 0.7 % (null). The
TV policy's decision is unchanged under all three models. Amendment 2 was
made after a frozen PA-bound failure. Details are in "Measured result".

## Why, and what the pre-protocol probes changed

K, L1 and L2 are null ([core-k-luno-campaign.md](core-k-luno-campaign.md),
[luno-array-campaign.md](luno-array-campaign.md),
[luno-1830-campaign.md](luno-1830-campaign.md)). The literature scan's
strongest lead was model completeness:

- Heywood et al. 2020 (arXiv:2004.00454): a point model of 1934−638 imparts
  0.2–0.5 % structured amplitude errors at MeerKAT.
- CARACal ships a 196-component field model,
  `caracal/data/meerkat_files/pks1934-638.lsm`.
- K and L1 were described as solving against "a 14.96 Jy point about 1.5″ off
  the phase centre".

Scratch probes run before this protocol (labelled; numbers below; scripts
copied with their outputs to `outputs/l1m-20261030-00-fieldmodel/probes`)
show that **the premise does not hold as stated**. The stored MODEL_DATA is
not a point model.

1. **The stored MODEL_DATA holds the lsm's compact sources.** The probe
   decomposes stored Stokes I (1,500 random rows × every 16th channel, all
   stations, unflagged, 77,950 samples) by least squares onto the lsm's 25
   brightest components plus the other 171 as one column, each predicted by
   the core and shifted by the fitted common offset (item 2).
   - A0: coefficient 1.001 (standard error < 0.001).
   - The bright point components: E191 1.10 ± 0.01, G163 1.00 ± 0.01,
     H022 1.11 ± 0.01, N043 1.11 ± 0.03, P154 0.96 ± 0.03, R114 1.12 ± 0.03.
     Phases are within 0.04 rad.
   - The Gaussian (extended) components come out at 1.9–9.6 (B301G 5.4,
     I311G 3.7, C023G 9.6), and the other 171 together at 2.1. On short
     baselines a 10″ Gaussian is nearly a point, so these values are not a
     shape-convention effect. The stored model holds more flux at the lsm's
     extended sources than the lsm does.
   - RMS of stored − model: 0.125 Jy for A0 alone, 0.094 Jy for the lsm at
     coefficient 1 (shifted), 0.059 Jy after the free fit. The fit uses 26
     columns and the stored values carry no noise, so 0.059 Jy is structure
     that the lsm does not explain. On baselines under 1 km the three values
     are 0.161, 0.126 and 0.066 Jy.

   The stored model is **consistent with an lsm-based field prediction plus a
   common 0.077″ offset, with 0.06–0.09 Jy rms unexplained** and more flux
   at the extended sources. Its origin is still unlogged. The "14.96 Jy
   point" description in L1 and the literature scan came from the median |I|
   and the phase trend with baseline: the field term is 2.4 % of the flux,
   so the median does not see it.

2. **Position.** A phase fit on the stored model (baselines over 1 km) puts
   its point at (−0.150″, −2.025″) from the FIELD phase direction. The lsm's
   A0 is at (−0.133″, −2.100″). So the "1.5″ off" of L1 is about 2.1″,
   almost all in declination, and the stored model sits 0.077″ from A0. A
   common shift is absorbed by per-antenna phase gains (it is
   antenna-separable up to the w-term).
3. **Sign and spectrum of the core predictor.** The core's A0 against stored
   Stokes I (2,090 rows): the median phase difference is ≤ 0.03 rad in every
   baseline band with the core's positive sign. With the conjugate it is
   1.55 rad at 3–9 km, so the sign is confirmed. The |ratio| per 256
   channels is 1.0001–1.0011, and a per-channel complex scale of A0 against
   the residual is at most 1.4e-3. Stored XX equals YY exactly, and XY and
   YX are zero.
4. **What a model swap can do to MSE_test at most.** The probe takes the
   stored arm's `original` gains, fixed, and runs the fused pass with DATA = 0
   and MODEL = δ (the model difference). Its test loss bounds the change in
   MSE_test from swapping models without re-solving. It is two-sided: it
   does not say which model is right.

   | δ | stations 0–11 (2,112 rows) | every other station (11,745 rows) |
   | --- | ---: | ---: |
   | field − stored | 7.80 % | 25.4 % |
   | field shifted by the common offset − stored | 7.60 % | 2.85 % |
   | field − point (A0), both from the core | 0.98 % | 0.80 % |

   The point → field change that Heywood's argument is about is bounded at
   about **0.8–1.0 % of MSE_test**, right at the frozen ±1 % band. The
   stored → field difference is larger, mostly the A0 offset (which the
   gains absorb) plus the unexplained structure of item 1.
5. **Prediction checks.**
   - A NumPy direct DFT of all 196 components, written independently from
     the formulas (point phase `+2π f/c (ul + vm + w(n−1))`, Gaussian
     envelope `exp(−π²/(4 ln 2) (θ_maj² u_∥² + θ_min² u_⊥²))` with the major
     axis at PA east of north), on 200 rows × 64 channels of stations 0–11,
     differs from the core by 1.9e-15 of the peak (1.1e-13 of the field
     term's maximum).
   - Rotating the 15 Gaussians by 90° changes the prediction by at most
     2.0e-4 Jy, 4.0e-5 Jy rms. The field term itself is 0.072 Jy rms on
     stations 0–11. The position-angle convention is therefore immaterial
     here, and it is not chased.
   - Prediction speed: 22 ns per row × channel × source for points (one
     source, 2,090 rows); all 196 components on 2,112 rows took 13.6 s.
6. **Smearing (a limitation).** Integrations are 8.0 s (32 times) and
   channels 209 kHz. On an 8 km baseline at 1.5 GHz, the time-smearing phase
   over one integration is 0.5 rad at E191 (12′) and 2.9 rad at 68′. The
   channel phase is 0.12 and 0.69 rad. The core predicts unsmeared
   visibilities, so far components are overpredicted on long baselines.
   They are weak (apparent fluxes ≤ 27 mJy), and Q1 is reported by baseline
   band.
7. **Comparator precondition on this host.** `outputs/l1m-20261030-00-precondition`
   (L1's `precondition`, unedited, 1 min 23 s, 568 MB):
   - K's precondition passes.
   - The gridder-group check passes.
   - The four-station replay differs from K's run `-01` only in image keys:
     the dirty and PSF hashes, and peak and residual RMS at 5e-16 and 1e-15
     relative. That is P2's documented change of image bits
     ([p5-memory.md](p5-memory.md) §1.4).
   - Judged with L2's `compare_replay_tolerant` (the P2 exemption,
     tolerance 1e-9), it is all equal.

The task is therefore reframed, but not dropped. The question "does a more
complete calibrator model change the gains, the held-out loss and the TV
policy's decision?" is now asked with three models, all on L1's frozen arms.

## Question

On LUNO row chunk 0 (PKS 1934−638, 53 stations, 1070–1498 MHz), compare
three calibrator models under L1's frozen campaign:

- **stored**: L1's MODEL_DATA, an lsm-like field model;
- **point**: the lsm's A0 alone, predicted by the core;
- **field**: all 196 lsm components, predicted by the core.

Do they change held-out error, chi-squared, convergence, gain TV, and the
TV-guided flagging decision?

- **Q1.** Does the field model lower held-out error and χ²? Primary: field
  against stored, the model K and L1 used. Secondary, pre-registered:
  field against point, which is Heywood's question with one predictor and
  one convention.
- **Q2.** Does gain TV drop under the field model, i.e. was part of the TV
  model error? Field against stored, and field against point.
- **Q3.** Does the TV policy's decision change? L1's decision rule and
  amendment 1's matched calls, under each model.

## The field model (frozen)

- **Source.** CARACal, file
  `caracal/data/meerkat_files/pks1934-638.lsm`:
  - pinned at master commit `8f7bb363876f5f0daecbf2167c36bb597c7e5160`
    (2026-09-14; the same commit as `outputs/caracal-strategy-inputs-8f7bb363`);
  - the file was last changed in `59ad90deffa4d25b76c91d2b0ce6435cfbaed229`
    (2020-04-09, "Renamed into CARACal");
  - 31,241 bytes, 197 lines, SHA256
    `0964b9f4c547bb802bfb16a2e8fdccddff84beeec05b6f3492521a46fa77d101`,
    the same on master on 2026-10-30;
  - URL `https://raw.githubusercontent.com/caracal-pipeline/caracal/<commit>/caracal/data/meerkat_files/pks1934-638.lsm`.
- **Licence.** CARACal is `GPL-2.0` (pyproject `license = "GPL-2.0"`, the
  GPLv2 classifier; LICENSE SHA256 `db296f2f…c2fc73`). No "or later" grant
  was found, so the file is not compatible with redistribution inside
  GPL-3.0-or-later Rang. **It is not committed.** The driver downloads it
  into the run's outputs directory and refuses to use it unless the SHA256
  matches. Tests use a synthetic lsm written in the test.
- **Content.** 196 components; 15 Gaussians; one reference frequency,
  1.3 GHz; no Q, U, V or RM columns; separations up to 68.2′.
  - A0 is 15.069 Jy at 1.3 GHz with a four-term curvature (15.00 Jy at
    1.070 GHz, 14.68 Jy at 1.498 GHz).
  - The other 195 sum to 0.364 Jy at 1.3 GHz (0.661 Jy at 1.070 GHz,
    0.253 Jy at 1.498 GHz), 0.050 Jy root-sum-square.
  - The brightest field source is E191, 27 mJy at 12.1′.

### Reading the lsm (`rangtoy.lsm`)

The file is Tigger's ASCII format with a `#format:` header line:

    name ra_h ra_m ra_s dec_d dec_m dec_s i i_err emaj_s emin_s pa_d freq0 spi spi_err spi2 spi2_err spi3 spi3_err spi4 spi4_err

The reader follows Tigger's ASCII loader (astro-tigger-lsm 1.8.0,
`Tigger/Models/Formats/ASCII.py`, read on 2026-10-30 to fix the conventions;
Tigger is not a dependency):

- Columns are found by the names in the header. Rows beginning with `#` and
  blank rows are skipped.
- **RA** = `ra_h + ra_m/60 + ra_s/3600` hours × 15°. **Dec** = `|dec_d| +
  dec_m/60 + dec_s/3600` degrees, negative if the `dec_d` *string* starts
  with `-`, so −0° declinations are handled. Also accepted:
  `ra_d`/`ra_rad`/`dec_rad`.
- **Flux.** `i` in Jy at `freq0`. `q`, `u` and `v` are 0 when absent.
  `_err` columns are read and kept but never used.
- **Spectrum.** Tigger's `SpectralIndex.normalized_intensity`:
  `S(ν) = i (ν/ν0)^(spi + spi2 L + spi3 L² + spi4 L³)` with `L = ln(ν/ν0)`
  (natural log). That equals `i exp(spi L + spi2 L² + spi3 L³ + spi4 L⁴)`,
  the core's `log_poly` form with `coeffs = [spi, spi2, spi3, spi4]`.
  Trailing zero terms are exact no-ops (Tigger trims them).
- **Shape.** `emaj_s` and `emin_s` are the major and minor **FWHM** in
  arcseconds. Tigger's `Imaging.py` divides the extents by FWHM to get σ.
  `pa_d` is the position angle in degrees east of north. A component is
  Gaussian if either extent is non-zero (Tigger's rule with
  `min_extent = 0`). These map to the core's `gauss_shape` (major FWHM,
  minor FWHM in radians, PA in radians); item 5 bounds the PA convention.
- **Unknown columns** are kept as strings and never interpreted. This
  reader is also the first piece of the DF-IO decision, so it is a plain
  module with its own tests.

### Apparent or intrinsic flux (frozen: apparent at the pointing centre)

The components are read as **apparent** flux densities for a MeerKAT
L-band pointing on 1934−638, and the model is predicted **without a beam**.
The evidence:

- the off-axis spectral indices run from −3 to −8.6, while A0's is −0.1,
  which is the primary-beam signature of a model fitted on a MeerKAT image
  without primary-beam correction;
- CARACal predicts it with `cab/simulator` (MeqTrees) and passes no beam
  option (`crosscal_worker.py`, `set_model`, `meerkat_skymodel`);
- the stored model already carries the lsm's compact sources at
  coefficients near 1 (item 1).

LUNO scan 2 points at J1939−6342, which is the lsm's centre (A0 is 2.1″
from the phase direction), so the apparent reading applies. Limitations:

- the model is static, so it ignores the rotation of the non-circular
  beam with parallactic angle;
- the model's epoch is 2017 (CARACal's `southern_calibrators.txt`) or
  earlier;
- smearing (item 6).

### Prediction (frozen)

- `l = cos δ sin Δα`, `m = sin δ cos δ0 − cos δ sin δ0 cos Δα` relative to
  the FIELD `PHASE_DIR` of the field in the decoded rows (SIN projection),
  `n − 1` as in the core.
- `core.predict_components` on the kept rows' UVW and the 2048 channel
  frequencies, in row blocks, into a complex64 array.
- **Stokes I only**: XX = YY = I, XY = YX = 0. CORR_TYPE must be
  (9, 10, 11, 12) = XX, XY, YX, YY; otherwise the run stops. Q = U = V = 0
  in this lsm; a non-zero Q/U/V makes the driver stop rather than guess the
  feed convention.
- **point** = A0 alone and **field** = all 196 components, both through the
  same call. **stored** = the decoded MODEL_DATA, untouched.
- **Checks (gated, per run):**
  - **DFT check.** The NumPy direct DFT of item 5 on 200 evenly spaced rows
    × 64 evenly spaced channels of the run's rows: max |core − DFT| ≤ 1e-9
    of the DFT's max |V|.
  - **PA bound.** The Gaussians rotated by 90° on the same subset: max |Δ| ≤
    1 % of the field term's (field − A0) rms.
  - **Finite.** The predicted model is finite everywhere.

### The model hook (frozen)

L1's `core_campaign_array.run` runs **unedited**, so every L1 arm, the
policy loops and amendment 1 run as frozen. Only the model changes:

- the driver patches the module's `build_state`, in a scoped
  `try/finally` that restores it;
- the wrapper calls L1's `build_state` on the decoded arrays with the
  **stored** MODEL_DATA, so eligibility and the seed-7 split are L1's;
- it records the SHA256 of the eligible, train, validation and test masks;
- only then does it overwrite `state["model"]` in place, in row blocks,
  with the point or field prediction (stored: no change).

The **split is therefore identical across the three model arms by
construction**, and the hashes prove it. The Tricolour ports do not read
the model, so their additions must be identical across the model arms too,
which keeps "same flags" true for `original`, `tricolour-firstpass` and
`tricolour-mild`.

## Arms and runs (frozen)

Three full L1 campaigns on all stations of chunk 0, one per model arm, run
sequentially in separate processes. Each one starts only if `MemAvailable`
is at least **14 GiB**; P5 measured a 10.4 GiB peak, and the prediction adds
under 0.1 GiB. Starting is waited for, never forced.

1. `outputs/l1m-20261030-01-stored`, run first. **Comparator gate:** every
   non-image, non-timing field equals L1's frozen run `-01`
   (`outputs/luno-array-campaign-20261030-01/result.json` and
   `candidates.json`). That covers:
   - the split counts;
   - for every arm: `additions_sha256`, `gains_sha256`, the losses, TV,
     raw TV, fixed-support TV, the converged and valid-gain fractions, the
     invalid-prediction counts and the final flag fraction;
   - the Tricolour checks and counts;
   - every candidate's mask hash, count and objective;
   - the hypothesis MSE calls;
   - amendment 1's calls.

   P5 reports exactly this for the current code. If it fails, the
   difference is recorded. The field and point arms are then compared with
   this rerun only (the same code), never with L1's archive.
2. `outputs/l1m-20261030-02-point`.
3. `outputs/l1m-20261030-03-field`.

L1's arms within each run, unchanged: `original`, `tricolour-firstpass`,
`tricolour-mild`, `tv-policy`, `tv-unguided-best`, `tricolour-firstpass+tv`
(frozen; expected unavailable as in L1) and `tricolour-firstpass+tv-a1`.
Everything else is unchanged too: the seed-7 split, the solver (50
iterations, 2 × 32 bins, polar gauge on m000), the policy grid and
objective, L1's image geometry with the boxes from each run's own
`original` PSF, four channel groups, and the ±1 % decision band.

A **labelled smoke** on stations 0–3 for all three models
(`outputs/l1m-20261030-00-smoke-<model>`) precedes the runs. It may fix
bugs only.

## Metrics (frozen)

Per run: everything L1's `run` writes. That includes per-arm held-out MSE
(validation and test), χ²_train (section 6: the mean over training cells
of the four-correlation mean of `w|r|²`), the converged fraction at the
50-iteration cap, the valid-gain fraction, polar-gauge TV and its time and
frequency parts, the dirty peak, the PSF-box metrics, the far-region noise
and the residual RMS. Amendment 1's matched calls are included.

Added by this task, computed after each run in the same process from the
run's own state and stored gains (`l1m.json` beside L1's outputs):

1. **Model record:** the arm, the lsm SHA256, the component counts, the
   prediction seconds, the DFT and PA checks, and model Stokes I by
   baseline band (median |I| and mean Re I, on eligible samples).
2. **Split hashes** (eligible, train, validation, test) and the gain-grid
   coordinates.
3. **Band losses of the `original` arm:** the fused-pass test loss of its
   own gains restricted to test samples in each baseline band (0–200,
   200–1000, 1000–3000 and 3000–9000 m) and each 512-channel quarter.
   Reported, not gated.
4. **Per-antenna gain TV of the `original` arm**, from the polar-gauge
   aligned gains (reference m000) on the valid support:
   - amplitude TV_a = mean over the time-adjacent and frequency-adjacent
     valid pairs of `| |g_pp|(x) − |g_pp|(x') |` over both diagonals,
     divided by the stored `original` arm's scale;
   - phase TV_a = mean of `|wrap(arg g_pp(x) − arg g_pp(x'))|` in radians,
     over the same pairs;
   - time and frequency pairs pooled with equal weight per pair.

Cross-model (the checker):

- **Q1, primary:** `original` arm MSE_test, field against stored, by the
  frozen rule: *better* if the ratio is ≤ 0.99, *worse* if ≥ 1.01, *null*
  otherwise.
  - Beside it: MSE_val, χ²_train and converged-fraction ratios; the same
    call for `tricolour-firstpass` and `tricolour-mild` on samples that
    both models predict validly (amendment 1's matched loss, computed in the
    field run's process with the stored run's gains reloaded); the band
    losses.
  - **Q1 secondary:** the same for field against point.
- **Q2:** fixed-support polar-gauge TV of each model's `original` gains,
  computed **at the stored `original` arm's scale and on its edge
  support** (`flagging.fixed_support_tv` against the stored edges; `None`
  if the field arm loses a stored edge). Called by the same ±1 % rule:
  *drops* if the ratio is ≤ 0.99, *rises* if ≥ 1.01. Primary: field
  against stored; secondary: field against point. Per-antenna amplitude and
  phase TV are reported with the median per-antenna ratio.
- **Q3:** each model's L1 decision calls (frozen pairs; amendment 1
  matched pairs), the `tv-policy` selection (τ, α, count) and whether any
  TV-guided (α > 0) candidate is admissible and selected. "The decision
  changes" means that any headline call (primary or matched) or the
  `tv-policy` selection's α differs between field and stored.

## Acceptance criteria (frozen)

Gated:

1. **Comparator precondition.** `-00-precondition` passes K's precondition
   and the group check, and the replay is all equal under L2's tolerant
   comparison (already measured: pass).
2. **Field model integrity.** The lsm's SHA256 equals the pinned value; it
   parses to 196 components, 15 Gaussians and Q = U = V = 0; per run the
   DFT check (≤ 1e-9 of peak), the PA bound (≤ 1 % of the field-term rms)
   and a finite model pass.
3. **Identical split and Tricolour flags across the three model arms:** the
   four split hashes, and both Tricolour arms' `additions_sha256`.
4. **Stored comparator gate** (run `-01` equals L1's run `-01` on the
   listed fields). A failure is recorded and the comparison stays within
   the reruns.
5. **L1's criteria 1–7 per run**, by L1's `check` unedited, recorded as
   they come out. L1 failed 2, 4 and 6 as frozen; the same failures are
   expected and are not this task's gate. What this task gates is that
   they are evaluated and archived.
6. **Q1–Q3 decidable or explicitly undecidable**, with the numbers. If a
   pair's arm is unavailable, the call is "undecidable", as in L1.
7. **Outputs and archive.** Each run dir has L1's files plus `l1m.json`;
   the checker writes `outputs/l1m-20261030-04-check/result.json`;
   `research/results/l1-model-completeness.json` is under 200 KB, holds no
   visibilities and pins the hashes of the run `result.json` files.
8. `flock /home/gijsm/.rang-checkall.lock bash tools/check-all.sh` passes
   on the branch before the final commit.

Never modified: input FLAG and FLAG_ROW, and the archived inputs (L1's
side-effect audit runs in every run). Nothing is written outside
`outputs/l1m-20261030-*` except the committed files.

## Expected outcome, stated before running

- **Q1, primary (field against stored): null or worse.** The stored model
  already holds the lsm's compact sources (item 1). The core's field model
  differs from it mainly by:
  - the 0.077″ common offset, which the gains absorb;
  - less flux at the extended sources;
  - about 0.06 Jy rms of structure that the lsm lacks.

  If the stored model's extra structure is real sky, the field model is
  less complete and MSE rises, possibly by more than 1 % (the bound with
  the offset removed is 2.9–7.6 %). If it is an artefact, MSE falls. The
  measured residual decides; we expect "null" or "worse", not "better".
- **Q1, secondary (field against point): field better by at most about
  1 %.** The bound with the gains fixed is 0.8–1.0 % of MSE_test, and
  re-solving can only lower it. The frozen rule therefore probably calls
  this **null** even if the field model is right. χ² moves by the same
  order. The per-band losses should show the gain on short baselines and at
  the bottom of the band, where the field sum is largest (0.66 Jy at
  1.07 GHz).
- **Q2: null in both comparisons.** Heywood's 0.2–0.5 % amplitude errors are
  small against the gain noise that the TV of 2 × 32 bins sees, and most
  of the missing field is not antenna-factorable, so it goes to the
  residual rather than to the gains. A TV drop of 1 % or more would be a
  surprise.
- **Q3: no change.** Every TV-guided mask was rejected in K, L1 and L2;
  the model swap changes neither the outlier scores' support much nor the
  data. All three models are expected to give L1's calls: the headline
  undecidable as frozen and null under amendment 1.
- **Convergence** stays near L1's 0.83 at the cap. The model is not the
  reason for the slow tail (U2 found the same on QuartiCal itself).
- **Images** are made from corrected DATA, so a model swap reaches them
  only through the gains. E191, D291a and B301G lie in the 25.6′ field, and
  partly in the far region, in every arm. Far-region noise and the
  point-source residual RMS are therefore not expected to show the field
  model.

Cost: each run should take about 30–40 min at four threads on a shared
host (P5 measured 37 min). The field prediction adds about 6 min
single-threaded (41,786 rows × 2048 channels × 196 components at about
22 ns), less with threads.

## Code to write after this commit (own files only)

- `python/rangtoy/lsm.py`: the Tigger ASCII reader (plain module, no
  Tigger).
- `python/rangtoy/core_campaign_fieldmodel.py`:
  - imports `core_campaign` and `core_campaign_array` and reuses
    `core_campaign_1830.compare_replay_tolerant`;
  - the fetch with hash check, the component conversion, block prediction,
    the DFT and PA checks and the model hook;
  - `run`, the stored gate, the cross-model comparison, the checker and
    the archive.
- `examples/{fetch,run,check,archive}_l1m.py`.
- `tests/test_lsm.py`, `tests/test_core_campaign_fieldmodel.py`:
  synthetic, offline.

No Rust, no shared file.

## Amendment 2 (after the frozen point run failed, before any point or field result)

Committed 2026-10-30 after the frozen stored run `-01-stored` (13 min 02 s,
exit 0) and the first frozen point run `-02-point`, which stopped in the
model hook before its split was used.

**What failed.** Criterion 2's PA bound failed as frozen on the whole
array. Rotating the 15 Gaussians by 90° changes the prediction on the
200 × 64 check subset by up to **0.0281 Jy**. The bound was 1 % of the
field-term rms of 0.0575 Jy, i.e. 5.8e-4 Jy. The pre-protocol bound
(item 5: 2.0e-4 Jy) was measured on stations 0–11 only, with baselines up
to 1 km, where a 12″ Gaussian is almost a point. On 8 km baselines it is
resolved, so its orientation matters. The direct-DFT check passed (2.0e-15
of the peak). Run `-02-point` wrote nothing beyond its log, and no point or
field number exists. The failed run directory is kept as evidence.

**Amendment.** The PA bound stays computed and archived, but it no longer
gates (`PA_GATED = False`). Its max and rms are reported per run. The
convention is fixed by documentation instead:

- in Tigger's lsm the position angle comes from PyBDSF Gaussian fits
  (`PyBDSMGaul.py` maps `PA`/`DC_PA` to `pa_d`), and PyBDSF measures PA east
  of north;
- the core's Gaussian follows africanus `wsclean_predict`, whose WSClean
  `Orientation` is also east of north;
- the independent DFT (major axis along (sin PA, cos PA) in (l, m)) matches
  the core to 2e-15.

What remains unverified is that CARACal's file follows PyBDSF's
convention. The stored model cannot settle this, because it carries 2–10×
the lsm's flux at these Gaussians (item 1). Q1 is therefore read with that
caveat. The 15 Gaussians hold 0.057 Jy of the 0.364 Jy field at 1.3 GHz.

**Also fixed (checker bug, labelled).** The stored comparator gate compared
amendment 1's residual-RMS ratio, which is an image product and therefore
outside the protocol's "non-image fields". `-01-stored` differs from L1 only
there, by 1.3e-15 relative (P2's image bits). The checker now exempts
image-derived ratios in amendment 1. Everything else is unchanged: arms,
split, solver, policy, decision rule, the memory gate and the run order.
Point and field are rerun as `-02b-point` and `-03-field`.

## Measured result (2026-10-30)

Runs:

- `outputs/l1m-20261030-01-stored`: 13 min 02 s, 10.6 GB peak (`time -v`);
- `outputs/l1m-20261030-02b-point`: 11 min 57 s, 10.6 GB;
- `outputs/l1m-20261030-03-field`: 14 min 36 s, 10.6 GB, of which 164 s is
  the field prediction.

All three ran at `RAYON_NUM_THREADS=4` with `OPENBLAS_NUM_THREADS=1` and
23–29 GiB available at start, on a host at load 3–7. The checker wrote
`outputs/l1m-20261030-04-check`. Archive:
[results/l1-model-completeness.json](results/l1-model-completeness.json)
(175.5 KB).

### Criteria

| Criterion | Measured | Result |
| --- | --- | --- |
| 1 comparator precondition | K's precondition and the group check pass; the replay is all equal under L2's tolerant comparison (image hashes only differ, P2) | **pass** |
| 2 field model | SHA256 pinned; 196 components, 15 Gaussians, Q = U = V = 0. DFT check 2.0e-15 of the peak. The PA bound **failed as frozen** in the first point run (max 0.028 Jy against 5.8e-4 Jy); under amendment 2 it is reported: max 0.028 Jy, rms 0.0040 Jy, against a field-term rms of 0.058 Jy (6.9 %) | **pass under amendment 2** (frozen: fail) |
| 3 same split and Tricolour flags | all four split hashes and both Tricolour `additions_sha256` identical across the three models | **pass** |
| 4 stored = L1 | every compared non-image, non-timing field equal to L1's run `-01` (0 differences); before amendment 2's checker fix the only difference was amendment 1's residual-RMS ratio at 1.3e-15 relative | **pass** |
| 5 L1's criteria per run | each model: 1, 5 and 7 pass; 2, 4 and 6 fail as in L1 (the derived FLAG_ROW clause; convergence 0.83 and the Tricolour arms' invalid predictions; the undecidable headline); 3 fails because L1's unedited precondition flag is false on the image hashes (P2), see criterion 1 | evaluated, as L1 |
| 6 Q1–Q3 decidable | every call below is decidable except the frozen headline (undecidable in every model, as in L1) | **pass** |
| 7 outputs and archive | every run has L1's files plus `l1m.json`; the archive is 175.5 KB, numbers and hashes only | **pass** |
| 8 check-all | `bash tools/check-all.sh`: 657 passed, 3 skipped; overall PASS | **pass** |

### The three models (`original` arm, same flags, same split)

| Model | MSE_test | MSE_val | χ²_train | Converged | Fixed-support TV at the stored scale | Median diag. amp. | Far residual robust σ (Jy/beam) | Peak (Jy/beam) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| stored (L1) | 0.2088876 | 0.2089667 | 0.2081362 | 0.8333 | 0.0260508 | 0.79019 | 0.0039958 | 14.8004 |
| point (lsm A0, core) | 0.2195760 | 0.2196819 | 0.2187850 | 0.8324 | 0.0264200 | 0.79034 | 0.0082616 | 14.7638 |
| field (196 lsm components, core) | 0.2153148 | 0.2154051 | 0.2145448 | 0.8323 | 0.0262305 | 0.79037 | 0.0082629 | 14.7634 |

The valid-gain fraction is 0.85435 in all three.

**Q1, primary (field against stored): worse.**

- MSE_test ratio 1.0308, MSE_val 1.0308, χ²_train 1.0308.
- On matched samples: first pass 1.0308 (678 test samples dropped), mild
  1.0308 (111 dropped).
- By band: 0–200 m 1.084, 200–1000 m 1.043, 1–3 km 1.012, 3–9 km 1.004
  (null); by channel quarter: 1.035, 1.006, 1.039, 1.025.

The core's prediction of CARACal's field model fits the data 3 % worse
than the stored MODEL_DATA, mostly on short baselines. That is consistent
with item 1: the stored model holds more flux at the extended sources and
0.06 Jy rms of structure the lsm lacks, and the data prefer it. It is at
the low end of the pre-run bound (2.9–7.6 %).

**Q1, secondary (field against point): better.**

- MSE_test ratio 0.9806, MSE_val 0.9805, χ²_train 0.9806.
- On matched samples: first pass 0.9806, mild 0.9806.
- By band: 0–200 m 0.962, 200–1000 m 0.976, 1–3 km 0.988, 3–9 km 0.992
  (null); by channel quarter: 0.969 at the bottom of the band, then 0.993,
  0.978, 0.986.

Adding the 195 field components to the point lowers held-out error by
1.9 %, largest on short baselines and at low frequency, where the field
term is largest. That is Heywood's effect, measured with one predictor.

- **The pre-run expectation was wrong in size.** The bound with the gains
  fixed (0.8–1.0 % on two station subsets) is not an upper bound for the
  re-solved gains. Solving against an incomplete model also biases the
  gains, and that bias costs held-out error which a fixed-gain swap does
  not see. The protocol's sentence "re-solving can only lower it" is
  wrong.
- **Stored against point:** the stored model is 4.9 % better than the
  point (0.20889 against 0.21958). K and L1 therefore did not suffer from a
  point model.

**Q2: null in both comparisons.** Fixed-support polar-gauge TV at the
stored `original` scale and on its support:

| Comparison | TV ratio | Call | Median per-antenna amplitude TV ratio | Median per-antenna phase TV ratio |
| --- | ---: | --- | ---: | ---: |
| field vs stored (primary) | 1.0069 | null | 1.027 | 1.005 |
| field vs point (secondary) | 0.9928 | null | 0.977 | 0.994 |

The point → field change lowers TV by 0.7 % and the per-antenna amplitude
TV by a median 2.3 %. That is the right sign for "part of the TV is model
error", but it is inside the ±1 % band on the frozen metric. The
convergence and valid-gain fractions do not move (0.832–0.833, 0.854).

**Q3: no change.** In all three models:

- the frozen headline is undecidable (the first-pass comparator's
  held-out loss is unavailable, as in L1);
- amendment 1's matched headline is null (TV policy against first pass:
  0.99943 stored, 0.99940 point, 0.99942 field);
- `tv-policy` against `original` is null (0.999998);
- the amended first-pass loop selects no change (1.000000);
- the TV policy selects the unguided τ = 5, α = 0 mask (21, 30 and 18
  cells), and no TV-guided (α > 0) mask is selected under any model.

The decision does not depend on the calibrator model.

**Cost clause.** The TV chain against the first-pass port: 5.66 (stored),
5.07 (point), 5.55 (field), against the frozen factor 3. On the parallel
kernels the Tricolour port takes 45–50 s and the TV loop 213–252 s, so the
clause now fails, as L2 found. L1's single-threaded 1.85 no longer holds.

### What this shows

- **The premise "K and L1 solved against a point model" is wrong.** The
  stored MODEL_DATA is a field model. It is consistent with CARACal's lsm
  compact sources plus more extended flux, and it fits LUNO 1934−638 3 %
  better than the lsm predicted without a beam and 4.9 % better than the
  point.
- **A point model does cost held-out error.** Field against point is
  1.9 % better, which is Heywood's effect. It barely moves gain TV
  (−0.7 %, null) and does not change convergence.
- **TV-guided flagging stays null under all three models**, with identical
  decisions. Model incompleteness is therefore not what made K and L1
  null.

### What it does not show

- **Which model is closest to the sky.** The stored model's origin is still
  unlogged. Its extra flux may be a more complete model or an artefact the
  gains partly absorb. The held-out loss prefers it.
- **Whether the lsm's Gaussian PA convention is right.** It is
  documentation-based (amendment 2), and a 90° error moves 0.004 Jy rms.
- **The beam.** No primary beam and no parallactic rotation are applied,
  and smearing is ignored (protocol item 6). The core's field prediction
  is the apparent-flux, no-beam reading of CARACal's own simulator call.

### Post-hoc steps, labelled

- **Amendment 2**, before any point or field result: the PA bound became
  a reported number, and the stored gate exempts amendment 1's
  image-derived ratio. The failed run `-02-point` is kept, empty apart
  from its log.
- The checker fix above is the only code change after the frozen stored
  run. The stored run's result files are unchanged.
- The smoke runs (`-00-smoke-*`, four stations) and their check are
  labelled smokes, not results.

## For the coordinator

- **Shared files.** None edited. No Rust; `core/` unchanged. Added:
  - `python/rangtoy/lsm.py`
  - `python/rangtoy/core_campaign_fieldmodel.py`
  - `examples/{fetch,run,check,archive}_l1m.py`
  - `tests/test_lsm.py` (9 tests, 12 with parameters) and `tests/test_core_campaign_fieldmodel.py`
    (14 tests)
  - this report and `research/results/l1-model-completeness.json`
- **`STATE.md`**, new top entry:

  > L1-M model completeness (big plan wave 3), 2026-10-30 (implemented;
  > measured; [l1-model-completeness.md](l1-model-completeness.md)). The
  > premise was wrong: LUNO's stored 1934−638 MODEL_DATA is not a point but
  > a field model. A least-squares decomposition shows CARACal's lsm compact
  > sources in it at coefficients near 1, more flux at the lsm's extended
  > sources, and a common 0.077″ offset; A0 sits 2.1″ from the phase centre,
  > not 1.5″. Three models ran through L1's frozen campaign unedited (scoped
  > model hook; identical split and Tricolour flags):
  >
  > - stored;
  > - the lsm's A0 alone, predicted by the core;
  > - all 196 lsm components, predicted by the core (apparent flux, no
  >   beam, as CARACal's simulator).
  >
  > Results:
  >
  > - Field against point: held-out MSE 0.981 ("better"; 0.962 under 200 m),
  >   which is Heywood's point-model effect.
  > - Field against stored: 1.031 ("worse"). The stored model fits best, and
  >   the point model is 4.9 % worse than it.
  > - Gain TV moves by at most 0.7 % (null), and convergence stays at 0.83.
  > - The TV policy's decisions are identical under all three models: the
  >   headline is undecidable as frozen and null under amendment 1, and no
  >   TV-guided mask is selected.
  >
  > Model incompleteness did not cause the nulls. Amendment 2: the Gaussian
  > PA bound failed as frozen on the whole array (0.028 Jy max) and is now
  > reported, not gated. The cost clause now fails (5.1–5.7×) on the
  > parallel kernels. Archive `results/l1-model-completeness.json`.

- **`README.md`**, one line: L1-M compared the stored, point and CARACal
  field calibrator models on LUNO 1934−638 under L1's frozen campaign
  (`rangtoy.core_campaign_fieldmodel`, Tigger lsm reader `rangtoy.lsm`,
  `research/l1-model-completeness.md`). The field model beats a point by
  1.9 % in held-out MSE, the stored model beats both, and the TV-flagging
  decision is unchanged.
- **`tool-timings.md`**: the rows of the timing table below.
- **`big-plan.md`**: L1-M done (measured). The premise is corrected: the
  stored model is a field model. C1 can proceed. `rangtoy.lsm` is the
  DF-IO reader candidate for Tigger ASCII lsm. It does not yet read
  Tigger's native `.lsm.html` or the BBS/WSClean text formats.
- **Corrections to existing text** (not edited here):
  - `luno-array-campaign.md` and STATE's L1 entry ("a 14.96 Jy point about
    1.5″ off"): the model is a field model, and A0 is 2.1″ from the phase
    direction, almost all in declination.
  - The literature scan's recommendation 1 and STATE's literature entry
    ("K and L1 solved against a 14.96 Jy point"): same correction.
  - `flagging-luno-candidate.md`, "Still open": MODEL_DATA is consistent
    with an lsm-based field prediction. Its origin is still unlogged.
- **Upstream observations** (observed, not raised):
  1. RATT, caracal-pipeline: `meerkat_skymodel` defaults to False although
     the schema advises using the lsm. Here the lsm improves on a point by
     1.9 % in held-out MSE, which supports the advice. The schema still says
     "for UHF band only models for PKS 1934-638 and PKS 408-65" in the
     `meerkat_band` text, which reads oddly for an L-band lsm.
  2. RATT, caracal-pipeline: the lsm has no header comment giving its
     flux convention (apparent, fitted without primary-beam correction) or
     its origin. Its steep off-axis indices (−3 to −8.6) only make sense as
     apparent spectra. A one-line header would help other users.
  3. RATT, caracal-pipeline: the file is GPL-2.0 (only) as part of
     CARACal. A data-licence note (or CC-BY) would let GPL-3 projects
     redistribute it.
  4. RATT, Tigger lsm format: the Gaussian PA convention is
     documented only by the PyBDSF import path. This is the reason for
     amendment 2.
  5. Non-RATT (SARAO, LUNO store): MODEL_DATA's origin is not logged in the
     store. It is a field model with a 0.077″ offset from the lsm's A0.
     Asking the observer for the prediction step would close this.
- **Evidence to keep:**
  - `outputs/l1m-20261030-00-fieldmodel` (the lsm, LICENSE, probes and
    their outputs, chain scripts)
  - `-00-precondition`, `-01-stored`, `-02b-point`, `-03-field` and
    `-04-check` (about 220 MB), with their logs and `-chain.log`
- **Evidence that may be deleted:** the smokes `-00-smoke-{stored,point,field}`
  and `-00-smoke-check` (171 MB), and `-02-point`, which is empty apart
  from its log; keep the log.
- **What the L4 verdict can say about model error.**
  - The calibrator model is not why TV-guided flagging is null.
  - Under three models, the policy makes the same decision, the
    TV-guided masks are rejected, and gain TV changes by less than 1 %. The
    models are: the stored field model (the best fit), a point model (4.9 %
    worse held-out error), and CARACal's 196-component lsm (1.9 % better
    than the point, 3.1 % worse than the stored).
  - Model completeness does change held-out error at the percent level,
    concentrated on short baselines and at low frequency. Most of it goes
    to the residual, not to the gains.
  - What remains untested: a beam-applied model (B1) and a closure-invariant
    detector that ignores per-antenna gains (C1).

## Timings (every tool run of this task)

| When (UTC) | Tool run | Wall | Peak RSS | Note |
| --- | --- | ---: | ---: | --- |
| 12:20 | `uv venv -p /usr/bin/python3.14` + `uv pip install -e '.[pointing,beam,test,imaging]' ruff maturin` (public PyPI) | 27.5 s | – | |
| 12:21 | `maturin develop --release --offline` | 0.3 s | 38 MB | already built |
| 12:22 | GitHub API (commit of the lsm, master) and `curl` of the lsm, LICENSE and master copy into `outputs/l1m-20261030-00-fieldmodel` | about 3 s | – | 31,241 + 18,092 bytes |
| 12:23 | download and unpack of the astro-tigger-lsm 1.8.0 wheel (PyPI, SHA256 `44e8516b…`) into the scratchpad, read only | about 2 s | – | conventions only |
| 12:24 | `curl` of CARACal's `crosscal_worker.py`, `crosscal_schema.yml`, `southern_calibrators.txt`, tree listing | about 3 s | – | read only |
| 12:26 | probe 1: phase centre, stored model vs A0, predictor sign and speed (all stations) | 10.9 s | 9.3 GB | |
| 12:28 | probe 2: lsm content and weights (stations 0–11) | 1.6 s | 0.45 GB | |
| 12:31 | **L1 precondition** unedited (`-00-precondition`) | 1 min 23 s | 568 MB | replay differs on image keys only; tolerant comparison all equal |
| 12:33 | probe 3: DFT check, PA bound, first ceiling (stations 0–11) | 38.5 s | 1.2 GB | |
| 12:35 | probe 4: stored − A0 structure (stations 0–11, then all) | about 12 s each | 7.1 GB | |
| 12:37 | probes 5–7: least-squares decomposition of the stored model onto the lsm | 9.5–12.8 s each | 7.1 GB | probe 6's last line is a bug (it subtracts twice) and is not cited |
| 12:44 | probe 8: model-swap ceilings (stations 0–11; every other station) | 22.2 s; 2 min 9 s | 1.2 GB; 6.4 GB | first try failed: `cargo` not on `PATH` |
| 12:50 | `fetch_l1m.py` (file present, hash verified) and the three four-station smokes (`-00-smoke-{stored,point,field}`, labelled) | 22.8 s, 23.3 s, 25.7 s | 0.87 GB each | all ran; stored fits best on four stations too |
| 12:55 | `check_l1m.py` on the smokes (`-00-smoke-check`, labelled) | about 15 s | 0.2 GB | exercised every path; the stored gate fails on a subset, as it must |
| 12:56 | the new tests from the scratchpad (`pytest`, 25 then 26 tests) | 0.3–1.0 s | 70 MB | first runs found the PA check failing on synthetic resolved Gaussians (a test-data issue) |
| 12:57 | **frozen stored run `-01-stored`** (`run_l1m.py` under `time -v`; MemAvailable 23 GiB, load 6) | **13 min 02 s** | **10.57 GB** | exit 0; equals L1 on every non-image field |
| 13:10 | frozen point run `-02-point` | 24 s | – | **stopped: PA bound failed as frozen** (0.028 Jy against 5.8e-4 Jy); amendment 2 |
| 13:11 | targeted tests after amendment 2 (`test_lsm`, `test_core_campaign_fieldmodel`, `test_core_campaign_array`) | 0.2 s | – | 35 passed, then 14 for the fieldmodel file |
| 13:12 | **frozen point run `-02b-point`** (MemAvailable 28 GiB, load 3–6) | **11 min 57 s** | **10.64 GB** | exit 0; prediction 2.2 s |
| 13:24 | **frozen field run `-03-field`** (MemAvailable 29 GiB) | **14 min 36 s** | **10.57 GB** | exit 0; the field prediction took 164 s (single-threaded; 196 components × 85.6 M samples) |
| 13:39 | `check_l1m.py` (`-04-check`) | 12.7 s | 0.21 GB | criteria 1–7 pass (2 under amendment 2) |
| 13:40 | `archive_l1m.py` | 0.1 s | 41 MB | 175.5 KB |
| 13:40 | `bash tools/check-all.sh` (plain; it takes the host lock itself), once before the final commit (`outputs/l1m-20261030-check-all.log`) | 3 min 31 s (pytest 657 passed, 3 skipped in 1 min 58 s) | 1.65 GB | **overall PASS** (criterion 8) |
