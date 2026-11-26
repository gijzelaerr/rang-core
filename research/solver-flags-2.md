# Rang: flags at the gain solve after a mild raw start (issue #58, follow-up)

Status, 2026-11-26: **measured; outcome 4, null (PB and PBG fail G-S, PG fails G-F; all fail G-N and G-A). Defaults unchanged.** Frozen before any arm ran. Branch `solver-flags-2` from origin/main
`9c6b725c`, for v0.5.0. Route: [docs/agents/propose-and-measure.md](../docs/agents/propose-and-measure.md).
This note follows [solver-flags.md](solver-flags.md), which measured outcome 4 (null) because its
"mild" raw strategy was not mild. Its kernel, oracle and gates are reused here unchanged except as
section 4 says. Results go under "Measured result"; nothing above it changes except by a dated,
labelled amendment.

## 1. Question

- **Hypothesis.** On E2-N, a raw start of the online flags plus the MeerKAT L-band known-RFI preset,
  followed by `calibrate.solver_flags: quartical` on the terms solved after the bandpass shape is
  handled (B, and the secondary G with B pre-applied), keeps at least 5 points more of the calibrators'
  data than the harsh raw strategy R, at equal or lower noise and the same flux scale.
- **Not claimed.** Nothing about target flagging. The tester's pipeline flags the target separately
  (LCP: `flagdata`, then Tricolour on corrected data), and solver flags never touch the target. Here
  the target keeps R's flags in every arm, so the target gates read the calibration transfer only.
- **Why these terms.** The first note found that primary G (only K pre-applied) flags on a residual
  that still holds the band's shape, 0.29 of cells at the band edges against 0.09 mid-band, and
  QuartiCal does the same on that residual. B's residual is relative to the per-channel solution, and
  the secondary G (`Gsec`) pre-applies K and B.

## 2. Design inputs, read before freezing (2026-11-26 07:40-07:50 SAST)

Read with `results/solver-flags-2/scripts/sf2_mild.py` from E2-N's online flags (flag version
`rang_flag_20261117T015729Z` of `nash:~/rang-data/outputs/e2n-20261116/e2n.ms`), channel frequencies
and UVW only; no DATA read, no stage run; 90 s on nash. Fraction of cross-correlation (row, channel)
cells flagged, in [results/solver-flags-2/e2n/mild-e2n.json](results/solver-flags-2/e2n/mild-e2n.json):

| Field | Online | + static masks (every baseline) | + preset `meerkat_l` | + both | R after `apply` |
| --- | ---: | ---: | ---: | ---: | ---: |
| J1939-6342 | 33.7 % | 54.0 % | 39.3 % | 57.3 % | 67.4 % |
| J1744-5144 | 33.6 % | 54.1 % | 39.5 % | 57.6 % | 56.9 % |
| J1331+3030 | 32.5 % | 53.8 % | 39.5 % | 57.6 % | 74.4 % |
| ASKAPJ1745 | 32.7 % | 53.8 % | 38.5 % | 57.2 % | 64.9 % |

- Tricolour's two static masks (CARACal's `apply_static_mask` with `uvrange: ""`) mask 446 of the 1,024
  channels on every baseline. The preset masks 119 channels on every baseline and 363 below 600 m.
- **Mildness rule (frozen here).** A start enters the solve arms only if, on J1939-6342 and on
  J1744-5144, it leaves the field at least 10 points below R's flagged fraction after `apply` (G-K
  needs 5 points after the passes and `apply`).
  - Preset: 28.1 and 17.4 points below R. **In.**
  - Static masks: 13.4 and 2.8 points below R. **Out.** On J1744-5144 the static masks alone flag
    within 3 points of the whole harsh chain, so G-K could not pass. The static-mask start is recorded
    by the table above and is not run.
- R's later SumThreshold and `uvcontsub_flagger` passes replace the first pass's flags (`write:
  replace`, the first note's amendment 3 reading), so R ends below online plus the static masks on
  J1744-5144. Not tested further here.

## 3. Code change: terms by name

`calibrate.solver_flags.terms` now accepts, besides the types `G` (every G term) and `B`, the name of
a G or B term of the calibrate chains, such as `Gsec`. A term is flagged when its type or its name is
in the list.

- The config check refuses an entry that is neither a type (G, B) nor the name of a G or B term.
- `mode: off` and the type list `[G, B]` behave exactly as before: no code path, receipt or stage hash
  changes (unit tests).
- The flag kernel and re-solve are unchanged, so the first note's oracle (O1-O4 against QuartiCal
  0.2.7) still covers them and is not rerun. Rule 1 below reads the unit tests and the pass records
  instead.

## 4. Data and arms (frozen)

- **E2-N** on nash, run root `nash:~/rang-data/outputs/solver-flags-2-20261126`, one own copy of
  `e2n.ms` per arm (from `~/rang-data/outputs/e2n-20261116`).
  - Every field starts from the online flags (`rang_flag_20261117T015729Z`).
  - Then J1331+3030, ASKAPJ1745 and J0408-6545 take R's flags after its flag stage: flag version
    `rang_calibrate_20261125T180010Z` of the first note's `e2n-R.ms`, chosen by R's own run date
    (25 November). The version list's first `rang_calibrate_*` is the copied 17 November run, which
    is the first note's amendment 2 trap.
  - Check before any arm runs: per field, those rows' flagged fraction equals R's flag-stage summary
    for those fields.
  - Each arm runs `flag`, `calibrate` and `apply` of the frozen E2-N configuration
    (`results/e2n-scripts/e2n.yaml`), changed only as the table says, with `flag.fields: [fcal, gcal]`
    (J1939-6342, J1744-5144).
- **A1** (`full`, default seeds) on glacier, run root `D:\rang\outputs\solver-flags-2-20261126`, the same
  arms.
  - The first note's generated `a1-full.ms` is the start.
  - 3C286-SIM and SIM-TARGET take A1's R flags after its flag stage (`rang_calibrate_20261125T100613Z`
    of `a1-R.ms`).
  - `flag.fields: [fcal, gcal]` (J1939-6342, SIM-GCAL).
- **R is not rerun.** The first note's R (E2-N and A1, code 669eeab1) is the control. Its MSs move into
  this run root and are scored again with this note's scorer. `mode: off` is bit-identical by test,
  so R is the branch's `off` with the harsh strategy.

| Arm | Flag stage on J1939-6342, J1744-5144 | `known_rfi` | `solver_flags` (`quartical`, rounds 2, guard 0.8, the rest default) |
| --- | --- | --- | --- |
| R (control, reused) | CARACal calibrator firstpass, on every field | none | off |
| P0 (start control) | `sf2_preset_only.yaml`: `flag_nans_zeros`, `flag_autos`, `combine_with_input_flags` | meerkat_l | off |
| PB | as P0 | meerkat_l | `terms: [B]` |
| PG | as P0 | meerkat_l | `terms: [Gsec]` |
| PBG | as P0 | meerkat_l | `terms: [B, Gsec]` |

- `sf2_preset_only.yaml` has no SumThreshold, no static mask and no `uvcontsub_flagger`; every step is a
  CARACal step without parameters.
- PB flags only J1939-6342 (B), PG only J1744-5144 (Gsec), PBG both. PBG is the recipe candidate. PB
  and PG separate the two terms' effects. A gate on a field its terms do not flag is expected to fail;
  it is still scored and still counts.
- No parameter is tuned. The `solver_flags` settings are the first note's M1 settings, apart from
  `terms`.

## 5. Gates (frozen)

The first note's gates, with the fields restricted to the fields the arms flag differently from R.
For each candidate C in {PB, PG, PBG}:

- **G-S (solutions intact), against P0:**
  - per term, flagged-solution fraction at most +1 point;
  - on J1939-6342 and J1744-5144, no antenna loses its last unflagged cell to the refant;
  - the tripwire does not fire.
- **G-F (flux and polarisation), against R:**
  - J1744-5144's fluxscale within 0.5 %;
  - 3C 286's p within 0.2 points and χ within 0.5°;
  - J1939-6342's residual polarisation at most R's + 0.05 points.
- **G-K (kept data), against R:** J1939-6342's and J1744-5144's flagged fraction after `apply` each at
  least 5 points lower than R's.
- **G-N (noise), against R:** `sqrt(S_C / S_R)` ≤ 0.98 on J1939-6342 and on J1744-5144, and ≤ 1.00 on
  ASKAPJ1745 (S as the first note, sf_score.py's measure).
- **G-V (RFI let through), ASKAPJ1745, against R:** Stokes V rms of CORRECTED_DATA over kept cells
  ≤ 1.02 × R's.
- **G-A (A1), against P0, on J1939-6342 and SIM-GCAL** (the first note used all three calibrator
  fields; 3C286-SIM carries R's flags in every arm here):
  - recall of the truth's `above_5sigma` cells at least P0's + 0.10;
  - false flags on cells clean in `any` at most P0's + 0.02.

J1331+3030's flags are R's in every arm, so its G-K and G-N are reported and not gated.

**Reported, not gated:**

- P0 against R on G-F, G-K, G-N, G-V: the preset start alone.
- Each candidate against the first note's archived M0 (the cut strategy plus preset).
- Gsec and B amplitude ratios C / P0 (median, p5-p95), and J1744-5144's flux C / P0. This is the
  first note's −1.07 % reading; the CASA fluxscale check it names is not done here.
- Per-pass flag additions, and the flagged fraction by baseline length in the reporter's seven bins.
- Costs.

## 6. Outcomes (frozen)

Each candidate gets an outcome by the first note's section 6 rules 2-4. The note's outcome:

1. **Failure:** a unit test of section 3 fails, or a candidate's pass records show flags on a term it
   does not name. The selection is fixed first and nothing else is read.
2. **Recipe:** at least one candidate passes G-S, G-F, G-K, G-N, G-V and G-A.
   - The recipe is the passing candidate with the lowest target G-N, then the fewest terms.
   - It is documented as the calibrator recipe for raw MeerKAT L-band data (`docs/howto/flag.md`,
     CHANGELOG): the preset start on the calibrators, `solver_flags` on the recipe's terms, and the
     target flagged as before.
   - Defaults stay off. Changing them changes E2's frozen chains, so that is an owner decision.
3. **Option only:** no candidate is a recipe, but at least one passes G-S and G-F. Documented as an
   experimental option, with the failing numbers.
4. **Null:** every candidate fails G-S or G-F. The option stays experimental. #58's mechanism is then
   closed as null for both starts the first note named.

The reported P0 against R reading has no outcome of its own. If P0 passes every R-relative gate on its
own, the note says that the preset start needs no solver flags on E2-N.

## 7. Stages and stop rules

1. This note, committed and pushed, before any code or arm.
2. The section 3 change with its unit tests; `python docs/gen_cli.py`; `tools/check_all.py --quick`.
3. Inputs: the E2-N and A1 copies with the section 4 flags, and the check against R's summary.
   - **Stop** if a field's copied flags differ from R's flag stage.
   - **Stop** if P0's flagged fraction after its flag stage on J1939-6342 or J1744-5144 differs from
     section 2's preset column by more than 1 point.
4. P0, PB, PG and PBG on E2-N (nash, 3 slots and 32 GB each, `nice -n 19 ionice -c3`) and on A1
   (glacier, 4 slots and 16 GB). All from one commit.
5. Score (`sf2_score.py`), the outcome, the archive in `results/solver-flags-2/`, the README and STATE
   entries.
6. **Not built here:** target-field solver flags, K's fallback (#60), weights (#48), the CASA fluxscale
   check.

## Measured result

Run 2026-11-26, code 9b61c9ce (branch; the arms' rang is the section 3 change on main 9c6b725c).

- **E2-N:** nash (shared; `nice -n 19 ionice -c3`; nash's lock, 3 slots and 32 GB per arm, four at
  once), run root `nash:~/rang-data/outputs/solver-flags-2-20261126`. R is the first note's MS, moved
  there.
- **A1:** glacier (4 slots, 16 GB, two at a time), run root `D:\rang\outputs\solver-flags-2-20261126`.
- **Archive:** [results/solver-flags-2](results/solver-flags-2): `gates.json` (the outcome),
  `e2n/records.json` and `a1/records.json` (`sf2_score.py`), the flag-stage summaries, the copied-row
  checks (`rows-*.json`), and the time files.

**Stop rules: none fired.**

- The copied rows (J1331+3030, ASKAPJ1745, J0408-6545 on E2-N; 3C286-SIM and SIM-TARGET on A1) equal
  R's flag stage exactly: 0.686270, 0.649307 and 0.609670 of elements on E2-N, against R's summary
  0.68627, 0.649307 and 0.60967.
- P0's flag stage leaves J1939-6342 at 39.33 % and J1744-5144 at 39.52 % flagged (section 2: 39.3 and
  39.5 %). The preset adds everything; the strategy adds nothing.
- **Rule 1:** the pass records name only each arm's terms (PB: B on J1939-6342; PG: Gsec on
  J1744-5144; PBG: both).

**E2-N, after `apply`** (R and the first note's M0 for reference):

| Arm | J1939-6342 flagged | J1744-5144 flagged | √(S/S_R) J1939 | √(S/S_R) J1744 | √(S/S_R) target | J1744 flux (Jy) | 3C 286 p, χ | Target V rms / R |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| R | 67.4 % | 56.9 % | 1 | 1 | 1 | 7.1793 | 9.964 %, 39.56° | 1 |
| M0 (first note) | 85.8 % | 77.7 % | 1.47 | 1.32 | 1.04 | 7.1828 | 9.753 %, 39.42° | – |
| P0 | 44.4 % | 39.5 % | 3.09 | 9.28 | 1.001 | 7.1854 | 9.913 %, 40.16° | 1.002 |
| PB | 61.6 % | 39.5 % | 1.04 | 9.06 | 0.999 | 7.1762 | 9.812 %, 39.89° | 0.999 |
| PG | 44.4 % | 44.1 % | 3.09 | 1.07 | 1.000 | 7.1514 | 9.913 %, 40.16° | 1.001 |
| PBG | 61.6 % | 44.0 % | 1.04 | 1.07 | 0.998 | 7.1482 | 9.812 %, 39.89° | 0.998 |

- **Passes (E2-N, both rounds):**
  - B on J1939-6342: 13.5 M then 4.1 M cells. The flagged B solutions go from 15.8 % to 17.1 %.
  - Gsec on J1744-5144: 8.2 M then 1.7 M cells (PBG 8.1 M, 1.7 M). Its solutions stay at 0 % flagged.
- **A1, G-A on J1939-6342 and SIM-GCAL** (R: recall 0.946, false flags 0.459):

  | Arm | Recall `above_5sigma` | False flags on clean cells |
  | --- | ---: | ---: |
  | P0 | 0.665 | 0.253 |
  | PB | 0.760 | 0.329 |
  | PG | 0.838 | 0.385 |
  | PBG | 0.933 | 0.462 |

**Gates.**

| Gate | PB | PG | PBG |
| --- | --- | --- | --- |
| G-S (against P0) | **fail**: Df +2.24 points of solutions, B +1.26 (bound +1) | pass | **fail**: as PB |
| G-F (against R) | pass: flux −0.04 %, p −0.15 points, χ +0.33° | **fail**: χ +0.61° (bound 0.5°); flux −0.39 % | pass: flux −0.43 %, p −0.15, χ +0.33° |
| G-K (against R) | pass (−5.7, −17.4 points) | pass (−23.0, −12.8) | pass (−5.7, −12.9) |
| G-N (against R) | fail (1.04, 9.06; target 0.999) | fail (3.09, 1.07; target 1.000) | fail (1.04, 1.07; target 0.998) |
| G-V (against R) | pass (0.999) | pass (1.001) | pass (0.998) |
| G-A (against P0) | fail: recall +0.095, false +0.077 | fail: false +0.132 | fail: false +0.209 (recall +0.268) |
| Outcome (section 6) | 4 | 4 | 4 |

- PG's χ is P0's. PG flags nothing on 3C 286's chain (B and primary G are P0's), so its G-F failure is
  the preset start, not Gsec's flags. The frozen rule still counts it.
- PB's and PBG's G-S failure is two downstream solution fractions: B's own (+1.26 points) and Df's
  (+2.24 points, the leakage term solved on J1939-6342 after B). No antenna lost its refant cells,
  and the tripwire (+5 points) did not fire.

**Reported, not gated.**

- **P0 against R (the preset start alone):** G-K and G-V pass; G-F fails on χ (+0.61°); G-N fails
  badly (3.09 and 9.28). The preset alone leaves most of the calibrators' RFI in.
- **What the flags at the solve do on this start (PBG against P0):**
  - implied noise 0.34× on J1939-6342 and 0.12× on J1744-5144;
  - 17.2 and 4.5 more points of flags;
  - A1 recall +0.27, at +0.21 false flags.
  - They remove most of the RFI the start leaves, but not down to R's noise: 1.04× and 1.07×, against
    a bound of 0.98×.
- **Against the first note's M0:** PBG keeps 24 and 34 points more data, at 0.71× and 0.81× of M0's
  noise on J1939-6342 and J1744-5144 and 0.96× on the target. So the preset start fixes the first
  note's confound.
- **Gsec amplitude bias, again.** Gsec's amplitudes are 0.9978 (PG) and 0.9974 (PBG) of P0's (median;
  p5-p95 0.995-1.002), and J1744-5144's flux drops 0.47 % and 0.52 % against P0. This is the first
  note's −1.07 % reading at half the size, in the same direction. Here it stays inside G-F's 0.5 %
  bound against R only because P0's flux is 0.09 % above R's. B's amplitudes are 1.0003 (p5-p95
  0.999-1.008) and primary G's 1.0000.
- **By baseline length (PBG against R), J1939-6342:** fewer flags below 1 km (0.59-0.69 against
  0.72-0.89), more beyond 1 km (0.50-0.62 against 0.47-0.54). The B pass flags long baselines that R
  keeps. J1744-5144 is below R's fraction in every bin.
- **Costs (E2-N, 3 threads):** calibrate P0 4,328 s, PB 4,786 s, PG 5,708 s, PBG 6,457 s, so the
  passes and re-solves cost +11 %, +32 % and +49 % of P0's calibrate. R's first-note calibrate was
  5,858 s, with its flag stage 6,976 s against P0's 593 s. Whole runs: P0 1 h 54 min, PBG 2 h 27 min,
  R 4 h 21 min.

### Verdict by section 6: **outcome 4, null**

- Every candidate fails G-S or G-F (PB and PBG G-S, PG G-F), and each also fails G-N and G-A.
- **#58's question is answered, negatively, for both starts the first note named.**
  - The static-mask start is too harsh to test (section 2).
  - On the preset start, QuartiCal-rule flags at B and Gsec cut the calibrators' implied noise by
    3-9×, but leave it 4-7 % above the harsh CARACal strategy's, while keeping 6-13 points more data.
  - On A1 they find RFI at roughly 1:1 with clean cells (+0.27 recall, +0.21 false flags).
  - Their Gsec flags lower J1744-5144's flux by about 0.5 %.
- **Defaults:** no change. `solver_flags` stays experimental (documented, with this result).
  `terms` by name ships with it, off by default.

## For the coordinator

- **#58 closes as null** on two frozen tests. Recommend closing the issue with this note. The tester's
  external residual script is not replaced by rang's flags at the solve on E2-N.
- **Next, if anyone wants it:**
  - one arm with the harsh strategy's SumThreshold passes on the preset start and no `uvcontsub_flagger`;
  - the CASA fluxscale check of the Gsec bias;
  - flags at the solve after a re-solve with B applied to primary G.

  None is planned here.
- **Run roots deleted** on both hosts (the archive holds the records). The first task's inputs are
  deleted too: nash run root, worktrees `solver-flags` and `solver-flags-base`, QuartiCal venv;
  glacier root and WSL venv.
