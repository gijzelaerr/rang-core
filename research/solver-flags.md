# Rang: residual flags inside the gain solve, a mild raw strategy and a MeerKAT known-RFI preset (issues #58, #59)

Status, 2026-11-26: **measured; outcome 4, null (G-F fails; G-K, G-N and G-A fail too). The oracle passes: QuartiCal 0.2.7 `mad_flags` is reproduced cell for cell. Defaults stay off.** Frozen 2026-11-25 before any code or run. Branch `solver-flags` from origin/main
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

## Amendments

**Amendment 1, 2026-11-25 07:00 SAST (implementation choices, written with the code, before any M
arm or oracle case ran; arm R had started and needs none of this code).**

- **3.2, location.** The mild strategy is `research/results/solver-flags/mk_rfi_flagging_mild.yaml`, not
  package data. It is a cut of a CARACal file, and CARACal's strategy copies have an open licence-notice
  item (STATE, MIT audit), so it stays with the other copies outside the wheel. The content is as
  frozen; a check against the e2n-scripts copy shows its first three steps byte-identical, trailing
  spaces aside.
- **3.3, single frequency.** Channels are selected by `rang.flagdata`'s CASA `spw` rule
  (research/v8b-flagdata.md): a range takes the channels whose centre lies inside it. A range between
  two centres, which includes `1600MHz` unless a centre is exactly 1600 MHz, takes both neighbouring
  channels, as CASA does. The note's "the channel that contains it" was wrong for CASA.
- **3.3, refusal.** The refusal runs at the `flag` stage only, because `config check` does not open the
  MS's OBSERVATION table.
  - The check: TELESCOPE_NAME is MeerKAT or MKAT, and the window is inside 856-1712 MHz with 1 MHz of
    slack.
  - The preset is OR-ed into FLAG before the strategy, and again after it, because `write: replace`
    would otherwise drop it.
- **3.1, executor.** With `data.processes` > 1, `solver_flags` is refused. The flag pass writes FLAG
  from the calibrate process, and a multi-field term on the pool solves its fields in workers.
  Chunked, replayed and streamed solves in one process are unaffected.
- **3.1, where flags can land.** Cells the solve excludes get no flags: rows outside the term's
  `uvrange` (`>150` on E2-N), and cells flagged by a pre-applied table's `calflag`. Each pass reads the
  whole field, then writes its flags, so a second table object never opens while the writer holds the
  lock.

**Amendment 2, 2026-11-26 03:30 SAST (post hoc: deviations found while reading, before the gates
were scored).**

- **A1 ran on glacier, not nash.** On the coordinator's word, A1 ran on glacier (Git Bash, glacier's
  lock, 4 slots and 16 GB, `memory_limit_gb` 12), because nash's queue was blocked on memory. Same
  code, 99a4e04a.
- **O1 and O3 were cut from the wrong flag version, and their reading stands.**
  - The cut took the first `rang_calibrate_*` version in `e2n-M0.ms.flagversions`. That is the copied
    E2-N run's `rang_calibrate_20261117T022650Z`, the flags after E2-N's harsh flag stage of 17
    November, not M0's own.
  - O1 and O3 test the kernel on identical arrays, so the reading holds. The input is the harsh chain's
    flag state, 61.7 % flagged.
  - O4 used M0's own version.
- **Arm R ran from a frozen worktree.** It used `solver-flags-base` at 669eeab1: main plus the note,
  before any branch code. `mode: off` is bit-identical by test, so R is the branch's `off`.

**Order of reading, stated plainly (2026-11-26 06:50 SAST).**

- Amendment 2 was written after the E2-N scores were read (about 04:05), not before. It is stamped
  03:30, the time its first item was found.
- A1's G-A numbers (25 November, afternoon) and M1's E2-N pass records (22:30) were read before any
  oracle case had passed (O4 at about 16:00 on the 25th; O1 at 23:16). Section 6 rule 1 says nothing
  else is read while the oracle is unread.
- No number or setting was changed after any of these readings.

**Amendment 3, 2026-11-26 06:50 SAST (post hoc diagnostics, after the outcome was read; they change
no gate).**

- **P0 on A1.** A flag-only run of the mild strategy without the preset (`a1-P0`, glacier, 411 s of
  flag stage). It tests whether the preset causes the over-flagging. It does not (Measured result).
- **Two cheap reads on E2-N's archived products:**
  - the per-block share of the oracle passes' flags (`oracle-e2n/*/rang-new.npy`);
  - the gain amplitudes of M1 against M0 (G, B, Gsec tables).
- **Numbers corrected from the first reading:**
  - "0.5-2.4 % per term" was wrong; it is 2.9 / 1.0 / 1.7 % of cells;
  - "1.4-1.8×" was M1 against R; against M0 it is 1.25 / 1.04.

## Measured result

Run 2026-11-25/26.

- **E2-N:** on nash (shared; `nice -n 19 ionice -c3`; nash's lock, 3 slots and 32 GB per arm), run
  root `nash:~/rang-data/outputs/solver-flags-20261125`.
- **A1:** on glacier, run root `D:\rang\outputs\solver-flags-20261125`.
- **Code:** 99a4e04a; arm R at 669eeab1.
- **Archive:** [results/solver-flags](results/solver-flags):
  - `e2n/score.json` (sf_score.py) and `e2n/flag-*.json`;
  - `a1/score.json` and `a1/flag-*.json`;
  - `oracle-*/compare-*.json`;
  - the time files.

**Oracle: pass.**

| Case | Cells | QuartiCal new | rang new | Differ | Bound | Re-solve products (max, median) |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| O1, E2-N J1939-6342 G | 143,292,416 | 9,078,219 | 9,078,219 | 0 | ≤ 1e-4 | 1.1e-15, 1.4e-16 (O2: pass) |
| O3, E2-N J1939-6342 B | 143,292,416 | 9,948,796 | 9,948,796 | 60 (4.2e-7) | ≤ 1e-4 | 3.6e-4, 2.1e-8 (not gated) |
| O4, A1 J1939-6342 G (2 scans) | 46,448,640 | 1,582,526 | 1,582,526 | 0 | ≤ 1e-4 | 1.6e-15, 3.0e-17 |

O3's 60 differing cells split 30 and 30. They sit at the threshold: the per-channel gains behind them
differ by at most 7.9e-8 before the pass. Its re-solves then differ by those 60 cells.

**The flag stage on E2-N (all cells, after the stage).**

- R: 31.5 → 63.8 %.
- M0-M2:
  - the preset adds 557.0 M cells (6.1 %; 119 channels on all baselines, 363 below 600 m), so the
    online 31.5 % becomes 37.6 %;
  - the mild strategy then takes it to **71.2 %**.
- **The "mild" arms start more flagged than the harsh one.**
  - By baseline length, M0 is flagged at 0.68-0.88 on every bin. R is at 0.36-0.49 beyond 1 km.
  - A1 shows the same: R 29.1 %, M0 66.3 %.
  - On A1 the preset alone flags 12.1 % of a sample of baselines longer than 2 km, and 48 % below
    600 m.
  - After the strategy, about 60 % of A1's channels are flagged whole on every baseline, in the preset's
    short-baseline bands.
- **The preset is not the cause (post hoc P0, amendment 3).** On A1, CARACal's first three steps
  alone, without the preset, flag 53.2 % of cells against the full harsh strategy's 29.1 %, and 0.888 of
  the short-list channels on baselines longer than 2 km. With the preset OR-ed in after them, the total
  is 65.6 %; with the preset before them (M0), 66.4 %. So the "mild" cut is the over-flagger, not the
  preset. One reading, not tested: in the full strategy the later `uvcontsub_flagger` passes do not
  OR with their input from cycle 0, so they replace the first SumThreshold's flags rather than add to
  them. Not checked on E2-N, where the preset alone adds 6.1 %.

**Flags at the solve (M1's passes, E2-N):**

| Term, field | Pass 1 added | Pass 2 added | Cells | Solutions flagged, first → last |
| --- | ---: | ---: | ---: | --- |
| G, J1939-6342 | 3,465,483 | 739,628 | 143,292,416 | 0 → 0 |
| B, J1939-6342 | 1,096,489 | 277,904 | 143,292,416 | 0.679 → 0.679 |
| Gsec, J1744-5144 | 2,492,578 | 1,128,016 | 218,811,392 | 0 → 0 |

**Gates for M1.**

- **G-S (against M0): pass.**
  - No term's flagged-solution fraction rose.
  - No antenna lost its last cell to m022.
  - The tripwire did not fire.
  - Every M arm has B at 67.9 % of solutions flagged (R 29.7 %) and Xf at 66.8 % (R 18.0 %). This
    comes from the flag stage, not the passes: M0 shows it too.
- **G-F (against R): fails.**
  - J1744-5144's fluxscale: 7.1058 against 7.1793 Jy (−1.02 %; bound 0.5 %). M0 and M2 both give
    7.1828, so the drop is M1's.
  - 3C 286: p 9.753 % against 9.964 % (−0.21 points; bound 0.2), χ 39.42° against 39.56°. M0 shows
    the same p and χ, so this is the flag stage's.
  - J1939-6342's residual polarisation: 0.066 % against 0.079 %.
  - Under the M arms' flags many channels are empty, so `stokes()`'s Stokes I median is diluted. p and
    χ are ratios within a block and are not affected.
- **G-K (against R): fails.** J1939-6342 67.4 → 90.4 %; J1744-5144 56.9 → 79.8 %; J1331+3030
  74.4 → 73.9 %.
- **G-N (against R): fails.** sqrt(S_M1 / S_R): J1939-6342 1.84, J1744-5144 1.37, J1331+3030 0.976,
  target 1.04.
- **G-V (target): pass.** Stokes V rms of kept cells 0.1439 against 0.1491 (0.965).
- **G-A (A1, against M0): fails.**

  | Arm | Recall | False flags |
  | --- | ---: | ---: |
  | R | 0.920 | 0.423 |
  | M0 | 0.9934 | 0.784 |
  | M1 | 0.9955 | 0.809 |
  | M2 | 0.995 | 0.795 |

  M1 against M0: recall +0.002 (bound +0.10, which M0's own 0.993 leaves no room for); false flags
  +0.025 (bound +0.02).

**Reported, not gated.**

- **M2 against M1:** the separate `flag.residual` stage changes almost nothing over M0 (J1939-6342
  85.8 against 85.8 %; S 1.720e-9 against 1.718e-9). M1 adds 4.6 points on J1939-6342 and its S is
  1.56× M0's.
- **M0 against R:** the preset plus the mild strategy is worse on every calibrator except 3C 286
  (S 0.954× R's).

### Verdict by section 6: **outcome 4, null**

- **Kernel.** rang's flags at the solve reproduce QuartiCal 0.2.7's `mad_flags` exactly on E2-N and A1
  (O1, O4). The re-solve's gains match QuartiCal's second run to 1e-15 (O2).
- **The arms do not test the hypothesis.** The "mild" raw strategy is not mild. With the preset it
  leaves E2-N 71 % flagged, against the harsh strategy's 64 %. On A1 the cut flags 53 % on its own
  (P0), against the full strategy's 29 %.
- **What the flags at the solve did on that start (M1 against M0, its own share):**
  - they added 2.9 %, 1.0 % and 1.7 % of all cells for G, B and Gsec, which is 11 %, 4 % and 6 % of
    the cells left unflagged before the passes;
  - J1744-5144's flux changed by −1.07 % (7.1058 against 7.1828 Jy), past the frozen bound. The change
    follows Gsec: its amplitudes are 0.996 of M0's (median; p5-p95 0.994-0.999), while primary G's are
    1.0002 and B's 1.0000. One reading, not tested: clipping on |d − g m g*| against a unit point model
    removes upward excursions first, and lowers the gain;
  - implied noise sqrt(S_M1 / S_M0): 1.25 on J1939-6342, 1.04 on J1744-5144, 1.00 on J1331+3030 and
    the target. Against R it is 1.84 and 1.37, and most of that is the flag stage;
  - on A1 they found 0.2 points more of the injected RFI and flagged 2.5 points more clean cells.
- **Primary G flags on a residual that still holds the band.** Primary G pre-applies only K; B is
  solved after it. On the oracle scan, G's pass flags 6-29 % of unflagged cells per 64-channel block,
  most at the band's edges (0.29 and 0.25 against 0.09 mid-band). B's pass flags 3-23 %. QuartiCal's
  own pass, on the same G residual, does the same (O1). It is the rule on this residual, not a port
  difference.
- **What ships.**
  - Defaults stay off.
  - `solver_flags` stays an experimental option, documented but not in the recipes.
  - The preset ships off by default; its unit tests are its gate (section 6, outcome 4).
- **Not answered:** whether flags at the solve replace a harsh raw strategy when the raw strategy is
  really mild, with no preset before it or the preset after it.

Costs (nash shared, 3 threads, `/usr/bin/time`):

- **E2-N `run` (flag, calibrate, apply):**

  | Arm | Wall | Flag | Calibrate | Apply |
  | --- | --- | ---: | ---: | ---: |
  | R | 4 h 21 min | 6,976 s | 5,858 s | 2,820 s |
  | M0 | 4 h 17 min | 6,125 s | 5,439 s | 3,824 s |
  | M1 | 5 h 00 min | 5,775 s | **8,297 s** | 3,890 s |
  | M2 | 5 h 11 min | – | 10,014 s | – |

  The passes and two re-solves of G, B and Gsec cost M1 2,858 s of calibrate over M0.
- **QuartiCal:** O1 241 s and 27.2 GB; O3 959 s and 26.9 GB.
- **rang's oracle side:** G 365 s; B 957 s.
- **A1 on glacier (4 threads):** R 4,709 s, M0 1,616 s, M1 1,946 s, M2 3,549 s; generation 2,023 s.

## For the coordinator

- **#58: null as frozen.**
  - The mechanism is exact against QuartiCal.
  - The arms were confounded by the "mild" strategy, which over-flags on its own (P0 on A1).
  - What would answer it:
    - a mild raw start that is mild: online flags plus the static mask, or the preset alone;
    - `solver_flags` with `terms: [B]`, or G only after B, so that primary G does not flag on the band's
      shape;
    - an explicit check of the Gsec amplitude bias on J1744-5144 against CASA's fluxscale.

    About 9 h on nash per E2-N arm.
- **#59: ships off by default.**
  - On A1, before or after the cut strategy it adds the same (66.4 against 65.6 %). On E2-N it adds
    6.1 % on its own.
  - Untested: LCP's order (`flagdata`, then Tricolour on corrected data).
  - The LCP band-list question is drafted in `outputs/drafts/solver-flags-lcp-bands.md`, not posted.
- **K's fallback (#60): no change.** In R, 19 antennas still have no J1939-6342 cell to m022; in the
  M arms, 14.
