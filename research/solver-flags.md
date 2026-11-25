# Rang: residual flags inside the gain solve, a mild raw strategy and a MeerKAT known-RFI preset (issues #58, #59)

Status, 2026-11-25: **proposed; frozen before any code or run.** Branch `solver-flags` from origin/main
`de22d05e`, for v0.5.0 (the testers' priorities 2 and 4, Killick for Prof. O. Smirnov). Route:
[docs/agents/propose-and-measure.md](../docs/agents/propose-and-measure.md). Results go under
"Measured result"; nothing above it changes except by a dated, labelled amendment.

## 1. Origin and prior

- **#58:** flag on residuals inside the gain solver, as QuartiCal's `mad_flags` does, with a mild
  strategy on the raw data, so the tester's external residual-flagging script can be retired.
- **#59:** a MeerKAT L-band known-RFI preset with the band lists of the tester's reference pipeline
  (LCP).
- **Read as data, nothing run:** #51 and #52, the reporter's v1-v7 runs on SARAO block 1680477139.
  - v1-v3: harsh flagging on raw L0 over-flags calibrators (79-87 %) or lets RFI through (v2: flux +3.7 %).
  - v4: a baseline-blind noise scale flagged every baseline to the reference antenna m022, and K lost
    21-23 of 62 antennas.
  - v5: per-antenna noise and an 80 % guard; 0 % of solutions flagged; calibrators 37.3-49.6 % flagged.
  - v7: the known-RFI bands plus residual flags on the calibrators; the best of the series (10.8σ
    against LCP's 13.0σ).
- **Prior in rang:** #51's `flag.residual` stage ([flag-residual.md](flag-residual.md)) was **null** on
  E2-N. It added 0.1-0.4 points of flags and changed nothing measurable. It ran **after** the harsh
  CARACal firstpass, so most RFI was already gone. Its `quartical` kernel matched QuartiCal 0.2.7 exactly
  on 17.9 M cells.
- **The question #51 did not ask:** does mild raw flagging plus residual flags at the solve replace the
  harsh raw strategy? Every arm here except the harsh control starts from the online flags.

## 2. What QuartiCal's `mad_flags` does (read 2026-11-25 from QuartiCal 0.2.7's wheel)

- **When it runs.** `quartical/executor.py` calls `add_mad_graph` once, after `add_calibration_graph`:
  - once per data chunk (`input_ms.time_chunk`, `freq_chunk`), on the final residual
    `_RESIDUAL = data − G M G^H` of the whole chain (`calibration/calibrate.py`), against the input FLAG;
  - **not** per solution interval or per solver iteration: a grep of `gains/` and `calibration/` finds no
    MAD call;
  - its flags are written to FLAG and do **not** change that run's gains. A second QuartiCal run on the
    flagged MS is QuartiCal's re-solve.
- **The rules:** as section 2 of flag-residual.md, with amendment 5's two corrections (complex magnitude
  against real medians). The kernel is already ported (`core/src/flag_residual.rs`, `flags_quartical`).
- **Consequence for the issue's wording.** "Per solution interval and iteration" is not QuartiCal's
  behaviour. The design below flags once per solution interval after each solve, then re-solves, for a
  fixed number of rounds. Round 1 without the re-solve is QuartiCal's `mad_flags`, which is the oracle
  (section 5). The re-solve has QuartiCal's two-run equivalent as its oracle. Anything beyond round 1 has
  no oracle and is judged by the gates only.

## 3. Design (frozen)

### 3.1 Flags at the solve: `calibrate.solver_flags`

```yaml
calibrate:
  solver_flags:
    mode: off          # off | quartical | rang
    terms: [G, B]      # solve types flagged: G (G and Gsec, calmode ap or p) and B
    rounds: 2          # flag passes, each followed by a re-solve of the term
    sigma: 5.0         # cell threshold (QuartiCal threshold_bl)
    global_sigma: 10.0 # quartical only (threshold_global)
    persist: 3.0       # rang only (as flag.residual)
    guard: 0.8         # no baseline is pushed past this flagged fraction within an interval (1: off)
    min_cells: 8       # a (interval, baseline) with fewer unflagged cells gets no new flags
    tripwire: 0.05     # fail when a term's flagged-solution fraction rises by more than this in a re-solve
```

- **Where it runs.** After a G or B term has solved, a flag pass runs on each field of the term:
  - the residual is formed on the unaveraged cells, in the frame of the solve: data with the lower types
    corrected, model with the higher types corrupted, as `rang.cal_gain._Field.prepare` gives them;
  - `r = d − g_p m g_q^H` with the term's diagonal gains for that row's interval and frequency bin;
  - the statistics chunk is one solution time interval times every channel of the window. QuartiCal's
    chunk is a time chunk times the whole band (`freq_chunk: 0`); B's per-channel intervals are pooled;
  - new flags (all correlations) are OR-ed into FLAG through the stage's `WriteBack` session, and the
    term is solved again on the new flags, with averaging if the config averages;
  - after `rounds` passes, or a pass that adds nothing, the last solve's table is the term's table. Later
    terms and `apply` see the flags.
- **Averaging.** E2-N's chain averages in time and frequency (`average_time`, `average_freq`), so the
  kernel sees one cell per baseline and interval, and a MAD inside the kernel's iteration has no sample.
  This is why the flags are found on unaveraged cells between solves and not inside `diag.rs`'s
  iteration.
- **Rules.**
  - `mode: quartical`: `flags_quartical` on the chunk; diagonal correlations, unwhitened,
    `max_deviation` 0 (QuartiCal's defaults).
  - `mode: rang`: `flags_rang`, with per-antenna noise and persistence as in flag-residual.md.
  - Both modes then apply `min_cells` and `guard`. The guard is per (interval, baseline): if the new
    flags would take a baseline's flagged fraction in that interval past `guard`, that baseline gets none
    in that interval. This covers every baseline to every antenna of the refant list (#51's v4 failure).
  - Cells with a flagged gain take no part in the statistics and are not flagged.
  - Autocorrelations are never flagged.
- **Terms.**
  - Not K: its FFT start uses refant baselines only (#60).
  - Not F: the flux bootstrap.
  - Not the polarisation terms: their residual is cross-hand.
  - Not selfcal's target solves in this note (section 7, stage 6).
- **Tripwire and restore.**
  - Relative, as flag-residual.md amendment 4: per term, the flagged fraction of solutions in the last
    re-solve against its first solve.
  - The flags written belong to the calibrate attempt. A rerun's `restore_before` restores the flags
    saved before the stage wrote anything. This is #51 amendment 3's restore point, so a rerun starts
    from the same input.
- **Solve paths.** The flag pass is inline in the parent process after the solve, whatever path solved
  (one call, chunked and replayed, streamed, executor). The pass reads the field in whole intervals
  under the same budget. Its result does not depend on the path, because the gains do not.
- **Off.** `mode: off` (the default) is bit-identical: no code path, receipt or stage hash changes.
  `calibrate.solver_flags` enters calibrate's hash only when it is not off.

### 3.2 The mild raw strategy (frozen, not tuned)

`python/rang/data/mk_rfi_flagging_mild.yaml` is CARACal's
`mk_rfi_flagging_calibrator_fields_firstpass.yaml` cut to its first three steps:

- `flag_nans_zeros`;
- `apply_static_mask` with uvrange "";
- the first `sum_threshold` at 10σ (`background_flags`).

It ends with `flag_autos` and `combine_with_input_flags`, and every parameter is CARACal's. Left out:
both `uvcontsub_flagger` passes (Taylor-polynomial residuals of the uncalibrated band), the second
static mask (uvrange 0~550), and the three final SumThreshold passes.

### 3.3 The MeerKAT L-band known-RFI preset: `flag.known_rfi: meerkat_l`

- **Bands.** Frequency ranges in MHz, mapped by channel frequency, not by channel index. A channel is
  flagged when its centre lies in a range; a single frequency flags the channel that contains it, as
  CASA's `spw='*:1600MHz'`.
  - All baselines: 850-900, 1658-1800, 1419.8-1421.3 (band edges and Galactic HI).
  - Baselines shorter than 600 m (uv distance, as CASA `uvrange='<600'`): 900-915, 925-960,
    1080-1095, 1565-1585, 1217-1237, 1375-1387, 1166-1186, 1592-1610, 1242-1249, 1191-1217,
    1260-1300, 1453-1490, 1616-1626, 1526-1554, and 1600.
- **Source.** oxkat `oxkat/config.py` (`CAL_1GC_BAD_FREQS`, `CAL_1GC_BL_FREQS`,
  `CAL_1GC_BL_FLAG_UVRANGE`), commit `421d14c5`, GPL-3.0. The lists come from SARAO's MeerKAT Cookbook,
  "L-band RFI frequency flagging". They are facts (frequency ranges), cited, not code copied.
- **LCP.** The reporter's summary of LCP ("850-900, 1658-1800, HI on all baselines; 15 satellite and
  transmitter bands with uvrange <600 m") matches this list in count and in every band it names. **That
  LCP uses exactly these values is not verified.** A confirmation question is drafted in
  `outputs/drafts/`, and the owner decides whether to send it.
- **Where it runs.** Behind the telescope boundary, in `python/rang/meerkat.py` (the band table and the
  mask).
  - Called by the `flag` stage before the Tricolour strategy, OR-ed into FLAG, on the stage's fields.
  - Refused (config check and stage) when the MS is not MeerKAT (`OBSERVATION.TELESCOPE_NAME`) or its
    window is not inside 856-1712 MHz (L band).
- **Default** `none`; `meerkat_l` must be named.

## 4. Data

- **E2-N** (capture block 1735268787, raw L0, [e2n-native.md](e2n-native.md)) on nash, run root
  `nash:~/rang-data/outputs/solver-flags-20261125`.
  - One own copy of `e2n.ms` per arm, flags restored to `rang_flag_20261117T015729Z` (the flags before
    E2-N's flag stage: the online flags as converted).
  - Each arm runs the stages `flag`, `calibrate` and `apply` of the frozen E2-N configuration
    (`results/e2n-scripts/e2n.yaml`), changed only as section 5 says per arm. No image or selfcal
    stages.
  - Calibrators: J1939-6342 (flux, bandpass), J1744-5144 (gain), J1331+3030 (polarisation). Target:
    ASKAPJ1745.
- **A1** (`full`, default seeds, [a1-simtruth.md](a1-simtruth.md)): injected RFI with the truth mask
  (`any`, `above_5sigma`) and known gains, run with the same arms.
- **The tester's block 1680477139 is not available.** It is not on nash or D:, and is not in the
  archive link list. It is not fetched for this note.
- **No parameter is tuned.** QuartiCal's defaults, CARACal's strategy parameters, the reporter's guard
  and oxkat's bands are taken as given. There is no development split; every number is a held-out
  reading.

## 5. Arms, oracle, gates (frozen)

**Arms** (E2-N and A1; each from the online flags):

| Arm | flag stage | `known_rfi` | `solver_flags` | `flag.residual` |
| --- | --- | --- | --- | --- |
| R (raw harsh) | CARACal calibrator firstpass (E2-N's frozen strategy) | none | off | off |
| M0 (mild) | mild (3.2) | meerkat_l | off | off |
| M1 (mild + solver) | mild | meerkat_l | `quartical`, terms G B, rounds 2, guard 0.8 | off |
| M2 (mild + stage) | mild | meerkat_l | off | `calibrators`, `rang` (#51's settings) |

Recorded first, from R and M0: the flagged-solution fraction per term, and each antenna's unflagged
cells to each refant per calibrator field. (On E2-N after the harsh chain, 19 antennas already have no
J1939-6342 cell to m022; flag-residual.md G-S.)

**Oracle: QuartiCal 0.2.7** (public PyPI, a uv venv on nash under `~/Build/tmp/20261125-solver-flags`).
Cases are cut from M0's MS after its flag stage:

- **O1 (G, flags).** E2-N J1939-6342 (scan 35):
  - every channel; `diag_complex`, `solint` = the scan (`time_interval: 0`, `time_chunk: 0`,
    `freq_chunk: 0`); no pre-apply; MODEL_DATA from rang's setjy;
  - `mad_flags.enable` with QuartiCal's defaults;
  - against rang's flag pass (`quartical`, guard 1, `min_cells` 0) on rang's `casa_rules=False`
    (QuartiCal rules) G solve of the same cells.
  - **Gate:** flags differing on at most 1e-4 of the scan's cells. The differing cells are listed with
    their deviation over the threshold. Gains differ at about 1e-6 (c2a, dd5), so cells at the threshold
    may flip.
- **O2 (G, re-solve gains).** QuartiCal run again on O1's flagged MS (`mad_flags` off) against rang's
  re-solve.
  - **Gate:** parallel-hand gain products `g_p g_q^*`: max absolute difference ≤ 1e-4 and median ≤ 1e-6.
- **O3 (B).** As O1 with `diag_complex` per channel (`freq_interval: 1`).
  - **Gate:** flags ≤ 1e-4 differing.
- **O4 (A1).** O1 on A1's flux calibrator.
  - **Gate:** flags ≤ 1e-4 differing.

**Gates on E2-N**, M1 against the arm named:

- **G-S (solutions intact), against M0:**
  - per term, flagged-solution fraction at most +1 point;
  - no antenna loses its last unflagged cell to the refant;
  - the tripwire does not fire.
- **G-F (flux and polarisation), against R:**
  - J1744-5144's fluxscale within 0.5 %;
  - 3C 286's p within 0.2 points and χ within 0.5°;
  - J1939-6342's residual polarisation at most R's + 0.05 points.
- **G-K (kept data), against R:** each calibrator field's flagged fraction after `apply` at least 5
  points lower than R's.
- **G-N (noise), against R:**
  - #48's implied natural-weighting noise `sqrt(S_M1 / S_R)` ≤ 0.98 on each calibrator field and ≤ 1.00
    on the target;
  - `S = Σ w² |d|² / (Σ w)²`, with d the Stokes V consecutive-dump differences of CORRECTED_DATA over
    each arm's unflagged cells (fr_score.py's measure);
  - more kept cells lower S only when they carry no RFI, so letting RFI through raises it.
- **G-V (RFI let through), target, against R:** the rms of Stokes V of CORRECTED_DATA over the arm's
  kept cells ≤ 1.02 × R's.
- **G-A (A1), against M0:**
  - recall of the truth's `above_5sigma` cells on the calibrator fields at least M0's + 0.10;
  - false flags on cells clean in `any` at most M0's + 0.02.

**Reported, not gated:**

- M0 against R: the mild strategy and the preset alone.
- M2 against M1: the separate stage against flags at the solve.
- Per-pass flag additions.
- Flagged fraction by baseline length in the reporter's seven bins, per field.
- The preset's own share per field.
- Costs.

## 6. Outcomes

1. **Failure:** O1, O3 or O4 fails. The flag pass is fixed first and nothing else is read. If O2 fails,
   only the re-solve's parity is fixed.
2. **Ship as the native-data recipe:** O, G-S, G-F, G-K, G-N, G-V and G-A pass.
   - `solver_flags: quartical` with the mild strategy and the preset is documented as the recipe for raw
     MeerKAT L-band data (`docs/`, CHANGELOG);
   - the defaults stay off, because changing them changes E2's frozen chains, so the default is an owner
     decision;
   - the tester's external script is then replaceable on calibrators.
3. **Option only:** O and G-S, G-F pass, but G-K, G-N, G-V or G-A fails. Documented as an experimental
   option, with the failing numbers.
4. **Null:** G-S or G-F fails. The option stays experimental and undocumented in the recipes. The preset
   still ships (its unit tests are its gate; it is a fact table).

## 7. Stages and stop rules

1. This note, committed and pushed, before any code.
2. Arm R on E2-N and A1, and the QuartiCal venv (no new code needed); they run while the code is
   written.
3. The Rust flag pass, config, preset, mild strategy and unit tests on the public fixture.
4. O1-O4; then M0, M1 and M2 on E2-N and A1; the scores.
5. The outcome; the archive in `results/solver-flags/`; the README entry.
6. **Not built here:**
   - flags in selfcal's target solves, which need the target model and uv-dependent statistics (#51 v5:
     a uv-blind scale over-flags 100-200 m on diffuse targets);
   - K's fallback (#60);
   - weights (#48).

   Each is named for the coordinator.

## Measured result

Not yet measured.
