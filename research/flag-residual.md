# Rang: a classical residual flagging stage, `flag.residual` (issue #51)

Status at freeze, 2026-11-21: **proposed; nothing built or run.** Branch `flag-residual` from origin/main
`5478c019`, for v0.5.0 (coordinator, 2026-11-21). Route:
[docs/agents/propose-and-measure.md](../docs/agents/propose-and-measure.md). Host: nash for every
measurement (`nice -n 19 ionice -c3`, main checkout's `tools/heavy_lock.py run`, booked by measured
use); glacier for the Rust build and tests. Results go under "Measured result"; nothing above it changes
except by a dated, labelled amendment.

## 1. Origin, and what is taken from it

Issue #51 (owner) and the reporter's comments v1-v5 there and in #52 (Killick, for Prof. O. Smirnov;
SARAO block 1680477139, raw L0, against the lightcurve pipeline LCP). **Read as data, nothing run.** In
short, as the reporter states it:

- Tricolour on raw L0 misses RFI the uncalibrated bandpass hides; it biased a flux scale by +3.7 % (v2)
  and over-flagged calibrators to 79-87 % (v1).
- Mild flagging on residuals then a re-solve helped calibrators (v5: 1934-638 37.5 → 41.8 %, 3C 286
  36.5 → 37.3 %, J0906 48.4 → 49.6 %; fluxes within 0.5 % of v1; no flagged solutions) after a failure
  (v4: a baseline-blind noise scale flagged every baseline to the reference antenna m022, K lost 21-23
  of 62 antennas, the target went 54 → 85 % flagged through `calflag`).
- On a target with diffuse emission, a uv-blind noise scale over-flagged 100-200 m baselines and
  under-flagged < 100 m (v5's flag fraction by baseline length); v6 (LCP's SumThreshold on the
  corrected target) was **not posted at freeze and is unread**.
- The reporter's parameters: z > 5 per cell, a persistence rule at 3 × the median mean z², an 80 %
  per-baseline guard on calibrators, a 5 % flagged-solution tripwire. **They are taken as given, not
  tuned here**, and labelled as the reporter's.
- Provenance: the stage is implemented from this prose and from QuartiCal's source, not by translating
  the reporter's posted script (it carries no licence). The QuartiCal-mode kernel keeps QuartiCal's MIT
  notice, as `core/src/solve.rs` does.

Related: #43's E2-N target cases need posterior masks of 6.5-8.8 % of a 4096² image at 3″
([dl4c-mask.md](dl4c-mask.md), masks R1-R3): the target carries extended Galactic emission, the case
in which the reporter's v5 over-flagged short baselines.

## 2. The oracle and what it does and does not test

QuartiCal 0.2.7 `mad_flags` (`quartical/flagging/flagging.py` `add_mad_graph`,
`flagging_kernels.py` `compute_bl_mad_and_med`, `compute_gbl_mad_and_med`, `compute_mad_flags`; read
2026-11-21 from the PyPI wheel):

- input: the **uncorrected** residual `data − g M g^H` per QuartiCal data chunk (time and frequency),
  whitened by sqrt(weight) or not (`whitening`, default `disabled`), **diagonal correlations only** by
  default (`use_off_diagonals: false`);
- per chunk, per correlation, real and imaginary parts separately: per-baseline median and MAD, and a
  global median and MAD (unflagged cells), MAD × 1.4826;
- a cell is flagged (all correlations) when, for any selected correlation, the baseline deviation
  `((re − med)/mad)² + ((im − med)/mad)²` exceeds `threshold_bl²` (default 5) or the global deviation
  exceeds `threshold_global²` (default 10); a whole baseline row when its MAD deviates from the
  baselines' mean MAD by more than `max_deviation` standard deviations (default 0: off); a baseline
  with no estimate is flagged; autocorrelations are not flagged.

It has no model-free calibrator residual, no antenna-factorised noise, no guard and no tripwire. So it
is the oracle for **one arm**, `method: quartical`: given the same residual array and chunking, rang's
kernel must reproduce QuartiCal's flags cell for cell. The arm with the reporter's rules
(`method: rang`) has no oracle and is judged by the gates of section 5 only.

## 3. The stage (design, frozen)

Configuration, default off (`off` bit-identical: no stage hash, receipt or column changes):

```yaml
flag:
  residual:
    mode: off            # off | calibrators | all
    method: rang         # rang | quartical
    sigma: 5.0           # cell threshold (QuartiCal: threshold_bl)
    global_sigma: 10.0   # quartical only (threshold_global)
    persist: 3.0         # rang only: baseline-channel / baseline-dump mean z^2 over the field median
    guard: 0.8           # rang only, calibrators: never push a baseline past this flagged fraction
    tripwire: 0.05       # stop the run if more than this fraction of K/G/B/Gsec/F solutions are flagged after the re-solve
    min_uv_m: 0.0        # targets: cells on shorter baselines are not flagged by this stage
```

**Where it runs.** Inside the `calibrate` stage, after the chain has solved: the calibrator fields'
residuals are formed in memory (the solved tables applied by the existing kernel,
`rang.cal_apply`), flags are added in the stage's own write session, and the chain solves again on the
new flags. The flags belong to the `calibrate` attempt, so a rerun's `restore_before` (which restores the
flags saved before that stage's last attempt) gives the same input; a separate forced stage would not.
Targets (`mode: all`) are flagged inside `selfcal`, per round, after the round's model is predicted and
before its solve, against `CORRECTED_1GC − MODEL_DATA`.

**Residual.** Calibrators: the corrected data minus the field's per-channel, per-correlation complex
median over unflagged rows (model-free; parallactic angle applied, so a polarised calibrator is constant
in the sky frame); `method: quartical` uses QuartiCal's definition instead (`data − g M g^H` with the
setjy model). Targets: corrected minus model.

**Noise and flags, `method: rang`.** Per field and channel block (16 channels), per correlation, a noise
level per antenna fitted so that a baseline's expected |r| level is the product of its two antennas'
(least squares on the log of each baseline's median |r|, over unflagged cells); z = |r| / expected,
Rayleigh-scaled; a cell is flagged (all correlations) when any correlation has z > `sigma`; a baseline's
channel over time, or a dump over the band, when its mean z² exceeds `persist` × the field median of
z². Guard: on calibrator fields, flags that would take a baseline past `guard` flagged are not added for
that baseline. Targets: the antenna factorisation per uv bin (baseline length in 8 logarithmic bins
from the shortest to the longest baseline) instead of per baseline, and no flag on baselines shorter
than `min_uv_m`.

**Tripwire.** After the re-solve, if more than `tripwire` of the K, G, B, Gsec and F solutions are
flagged, the stage fails with the numbers; nothing downstream runs.

Rust: `core/src/flag_residual.rs` (the median, the factorisation, both methods' flag rules), called from
Python with the existing chunk plan; tests: `off` bit-identical (gain-hash gate, stage hashes), a
synthetic RFI injection per method, the QuartiCal-mode kernel against the oracle's numbers.

## 4. Data

- **E2-N** (capture block 1735268787, raw L0, [e2n-native.md](e2n-native.md)): its frozen
  configuration through `calibrate` and `apply`, the stage off and on (`mode: calibrators`, then
  `all`). Calibrators J1939-6342 (flux, bandpass), J1744-5144 (gain), J1331+3030 (polarisation). Target
  ASKAPJ1745 (diffuse Galactic emission), for `mode: all`, with the DL0 profile's selfcal settings.
- **A1** (`full`, default seeds, [a1-simtruth.md](a1-simtruth.md)): injected RFI with the truth mask
  (`any`, `above_5sigma`) and known gains, run with Tricolour off (online flags only), the stage off and
  on.
- **ESO137** is not used: its calibrated pilot is gone from nash and its raw form was not checked
  (planned in the coordinator's brief; dropped at freeze, reason stated).
- No parameter is tuned (section 1), so there is no development split; every number is a held-out reading
  under the reporter's values.

## 5. Gates (frozen)

Recorded first, with the stage off: E2-N's flagged-solution fraction per term and each antenna's count
of unflagged baselines to the reference antenna (CASA's own K solve flagged 19 of 62 antennas on this
block, e2n-native.md, so K is fragile here).

- **G-Q (oracle).** `method: quartical` against QuartiCal's three kernels called on the same residual
  array, chunk and flags (the oracle container `rang-formats-oracle:20261030`, which ships QuartiCal
  0.2.7): flags identical on E2-N's J1939-6342 first scan and on A1's flux calibrator; a difference of at
  most 1e-6 of cells is allowed for floating-point medians and reported cell by cell.
- **G-S (solutions intact).** With the stage on, per term, flagged-solution fraction at most the off
  value + 1 percentage point; no antenna loses its last unflagged baseline to the reference antenna; the
  tripwire does not fire.
- **G-F (flux and polarisation).** E2-N: J1744-5144's fluxscale within 0.5 % of the off run; 3C 286's
  fractional polarisation within 0.2 percentage points and χ within 0.5° of the off run, per E2-N's
  polarisation rows; J1939-6342's residual polarisation not higher.
- **G-D (downstream).**
  - A1: on the calibrator fields, recall of `above_5sigma` cells ≥ 0.9 and false flags ≤ 2 % of clean
    cells; gain error against truth (G amplitude and phase, B amplitude, median over antennas) on ≤ off.
  - E2-N: the natural-weighting image noise implied on each field, from #48's scorer
    ([apply-calwt.md](apply-calwt.md) section 5: Stokes V consecutive-dump differences, held-out σ²,
    weights 0 where flagged): on ≤ 0.98 × off on the calibrators; for `mode: all`, on ≤ 0.98 × off on the
    target and the flagged fraction below 200 m rising by at most 5 points.
  - Not used as a gate: "V rms of removed against kept cells" (flagging on |r| makes the removed cells
    noisier by selection).

## 6. Outcomes

1. **Failure:** G-Q fails; the kernel is fixed first, nothing else is read.
2. **Ship calibrators:** G-Q, G-S, G-F and A1's and E2-N's calibrator parts of G-D pass for
   `mode: calibrators`; documented as an option, default stays `off`.
3. **Ship all:** 2 plus `mode: all`'s target parts of G-D.
4. **Calibrators pass, targets fail:** 2 holds and 3 does not; ship `calibrators` only, and the target
   result and its uv profile are recorded.
5. **Null:** G-S or G-F fails, or G-D's calibrator parts fail; the stage stays experimental (not in
   `docs/cli.md`'s recipes).

The rang-specific rules (guard, tripwire, factorisation) are reported for the reporter's values only;
no ablation is gated.

## 7. Stages and stop rules

1. This note, committed and pushed. 2. Baselines with the stage off (section 5). 3. The Rust kernel
   and its tests; G-Q. 4. `mode: calibrators` on A1 and E2-N; G-S, G-F, G-D. 5. `mode: all` on E2-N.
   6. Outcome. Implementation starts after #43's outcome is recorded (coordinator's order).

## Amendments

**Amendment 1, 2026-11-21 12:10 SAST (the reporter's v6 and v7 read after the freeze; before any
code or run).** As the reporter states them, read as data:

- v6: v5's residual flags on the calibrators, then LCP's final SumThreshold on the corrected target;
  calibration clean (0 % of K/G/Gsec/F solutions flagged); target 9.0σ (LCP 13.0σ).
- v6 also names what the earlier runs missed: LCP's "basic flagging" before Tricolour, `flagdata
  manual` on 850-900 MHz, 1658-1800 MHz and 1419.8-1421.3 MHz (all baselines), on 15 satellite and
  transmitter bands with `uvrange <600 m`, and zero clipping. The satellite step is what flags 77 % of
  LCP's 0-100 m baselines.
- v7: those manual steps (done with `rang-core flagdata`), 1GC, residual flags **on the calibrators
  only**, re-solve (tripwire 0 %), LCP's narrow+broad SumThreshold on the corrected target: 10.8σ, the
  best of the reporter's series (LCP 13.0σ); fluxes and 3C 286's p and χ unchanged; the remaining
  target excess on long baselines is attributed to L0's default online flags (about 37 % against L1's
  29 %), not tested.

Consequences for this note, decided before any code:

- The calibrator arm (`mode: calibrators`) is the primary deliverable; its gates are unchanged.
- The target arm (`mode: all`, uv-binned) stays frozen as written but runs only after the calibrator
  outcome, and the reporter's evidence that residual flagging on a diffuse target does not reach the
  sensitivity of known-band flagging is recorded as its prior.
- A MeerKAT L-band "known RFI" preset (the reporter's band lists, with the satellite bands below 600 m)
  is **not** part of #51: it is a separate, cheap first-stage item (`rang-core flagdata` already parses
  CASA's keywords), named for the coordinator, with LCP's lists to be checked against their source
  before use.
- Not checked: which online flag categories katdal applies to L0 by default against SDP's L1 (the
  reporter's last point); named for the coordinator.

**Amendment 2, 2026-11-21 (implementation choices; written with the code, before any run on data).**

- **Statistics unit: one (field, scan) block**, not the whole field: the calibrator median model, the
  antenna noise levels, the median z² and the persistence sums are per scan. A calibrator field's
  residual at E2-N's size is several GB per field; per scan it fits the booked memory. A scan holds one
  field, so the median model is still "the field's".
- **`method: quartical` in the pipeline uses the same residual as `rang`** (corrected minus the scan's
  median), not QuartiCal's uncorrected `data − g M g^H`; one chunk per scan; diagonal correlations,
  unwhitened, `max_deviation` 0 (QuartiCal's defaults). G-Q tests the kernel on identical arrays, as
  section 2 says; the residual's definition is not part of the oracle.
- **Flags around the calibrator apply:** the residuals are formed by `applycal` into CORRECTED_DATA on
  the calibrator fields (calflag adds solution flags), so the flags are saved as the CASA flag version
  `<calibrate version>_residual_pre` first and restored after the apply; only the residual flags are
  then added. The chain's own flag-writing steps (A term, extendflags) run again in the re-solve.
- **Tripwire input:** the flagged fraction of each K, G (G, Gsec), B and F table's solutions, read from
  the CASA tables' FLAG column after the re-solve (the step summaries carry no such number); written
  with the first pass's fractions to `calibrate/residual.json`.
- **Targets (`mode: all`) are not implemented in this commit**; the config accepts `off` and
  `calibrators` only until the calibrator outcome (amendment 1).
- Rust: `core/src/flag_residual.rs` (MIT, QuartiCal's notice), bindings `rang._core.flag_residual_*`,
  orchestration `python/rang/flag_residual.py` and `core_pipeline.residual_flag_pass`; with `mode: off`
  no code path changes and no stage hash changes (`flag.residual` is left out of the flag stage's hash
  and enters calibrate's only when not off; tests in `tests/test_flag_residual.py`).

**Amendment 3, 2026-11-22 01:00 SAST, post hoc (the first E2-N `on` run was read: its tripwire
fired).** The first E2-N `on` run stopped at the tripwire: after the re-solve, K, G, Gsec and F had
30.6 % of their solutions flagged (19 of 62 antennas: m000-m003, m006, m007, m009, m011, m012, m015,
m016, m018, m021, m023, m026, m030, m031, m043, m047) and B 53.9 %, against K, G, Gsec, F 0 % and B
29.7 % in the first pass. The residual flags themselves added only 0.1-0.4 percentage points per
calibrator scan. Diagnosis: those 19 antennas have no unflagged J1939-6342 cell to the reference
antenna m022 in the flags the chain leaves behind (in the `off` run too); the first pass's K solved
before the chain's later flag-writing steps, but amendment 2's restore point was the flags after the
whole chain, so the re-solve's K started from them. That is a defect of this note's design (amendment
2's restore point), not evidence about residual flagging. Fix, before any further run: the residual
flags are found on the cells still valid after the first pass's chain and calflag apply, the flags
are then put back to the calibrate stage's own starting version (`rang_calibrate_<time>`, the flags
before the stage wrote anything), and the residual flags are OR-ed into those, so the re-solve differs
from the first pass by the residual flags alone. The E2-N `on` and A1 `on` arms run again under the
fix; the first runs' records are archived. Side finding for the coordinator, not acted on here: on
E2-N the stage-off chain flags B for about 30 % of solutions and leaves 19 antennas without a J1939
baseline to m022 after its own flag steps, close to the 19 antennas CASA's K solve flagged on this
block ([e2n-native.md](e2n-native.md)).

**Amendment 4, 2026-11-22 03:10 SAST, post hoc (the second E2-N `on` run was read: its tripwire fired
on B alone).** Under amendment 3's fix the re-solve keeps every antenna: K, G, Gsec and F 0.0 % of
solutions flagged, as in the first pass; B 29.71 % against 29.69 % in the first pass. The tripwire still
stopped the run, because section 3 froze it as an absolute 5 % ceiling and E2-N's stage-off chain
already flags 29.7 % of B (amendment 3's side finding). An absolute ceiling therefore stops every run
on this block whatever the residual flags do. The reporter's 5 % was measured on a block where the
stage-off fractions were near zero. Change, before any score: the tripwire fires when a table's
flagged fraction **rises** by more than `tripwire` between the first pass and the re-solve (the same
comparison as gate G-S, whose +1 percentage point bound is unchanged). The E2-N `on` arm runs a third
time; the second run's record is archived with the first.

## Measured result

_Nothing yet._
