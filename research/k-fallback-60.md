# K without the reference antenna's baselines, through the chain and on real flags (issue #60)

Status at freeze, 2026-11-25: **proposed; nothing in this note is built or measured.** Branch `weights-k`
from origin/main `de22d05e`, committed before any code or run that tests it. Later changes are dated
amendments in section 8, labelled post hoc when they could have seen a result. Procedure:
`docs/agents/propose-and-measure.md`. The weights item of the same branch (#48) has its own note,
[weights-48.md](weights-48.md), and its own gate.

## 0. Starting point (read)

- **#60** (filed 2026-11-25 from the testers' list, priority 5 of 5) asks for a K solve that does not
  depend on the single baseline to the reference antenna, flagging only where an antenna truly has no
  data, with CASA gaincal `gaintype=K` on the same flags as the oracle. Its evidence is #51's v4 run
  (2026-11-20, **rang-core 0.3.0**): residual flags removed every baseline to the auto refant m022 on
  1934's scans, K was flagged for 21-23 of 62 antennas, G, Gsec and F followed (35-39 % of solutions
  flagged), and calflag apply took the target from 54 % to 85 % flagged.
- **#53** ([k-refant-53.md](k-refant-53.md), merged before v0.4.0, released 2026-11-23) already
  implements what #60 asks: under `refantmode: flex`, the default, each K interval takes its reference
  from the refant list (then the best-connected antenna), an antenna is solved when it is connected to
  the reference through any unflagged baselines (the joint solve uses every baseline), and the FFT start
  hops through a well-linked started antenna. `strict` keeps CASA's rule. Its gates passed on a
  12-antenna simulation, at the solver (`rang.cal_delay`): bit identity with the refant present,
  truth, and CASA at an alternative refant composed (0.0019 ns max).
- **What #53 did not check** (its section 7): the tester's block; the pipeline path (`rang-core run`
  calibrate with `refant: auto`, the chain and chunked code); the downstream G, B, Gsec and F after a
  flex K; the target's flags after calflag apply. **#60 is therefore a verification on the pipeline and
  on real flags, and a fix only where that verification fails.**
- **A real flag state with the v4 pattern exists** ([e2n-followup.md](e2n-followup.md) 1.1, 2.2): on
  E2-N's J1939−6342, the flags after rang's calibrate (`rang_apply_20261117T034709Z`, after
  `extendflags`) leave 351 of 1,891 baselines wholly flagged, and **19 antennas** (0, 1, 2, 3, 6, 7, 9,
  11, 12, 15, 16, 18, 21, 23, 26, 29, 30, 41, 45) with no unflagged cell to the refant m022, which
  itself has data. CASA's K on those flags at m022 flags exactly those 19; at m058 it flags 0. Rang
  solved its own K on the flag stage's flags (before `extendflags`), so rang's K has never been run on
  this state.

## 1. Hypothesis

On real native data, with the flags that cut 19 antennas off the refant m022 on the bandpass
calibrator, `rang-core run` calibrate at E2-N's configuration (`refant: auto`, `refantmode` default):

- **K** flags no antenna that has unflagged data in the interval, and its delays agree with CASA's K
  at a refant that reaches every antenna directly;
- **downstream** G, B, Gsec and F are flagged no more than in the unperturbed run plus the bound of
  section 4, and calflag apply leaves the target's flag fraction within the bound of the unperturbed run;
- under `refantmode: strict`, K flags the 19 (the v4 failure reproduced in rang, as CASA's rule).

**Not claimed:** anything about 1680477139 (not on hand), or about rang's G/B with a missing refant
beyond what the arms measure.

## 2. Data and arms

**Real data: E2-N** (capture block 1735268787, [e2n-native.md](e2n-native.md)), copies of
`nash:~/rang-data/outputs/e2n-20261116/e2n.ms` in this task's run root (the original is only read).

| Arm | J1939−6342 flags before calibrate | Other fields | `refantmode` | Stages |
| --- | --- | --- | --- | --- |
| A, unperturbed | flag stage (`rang_calibrate_20261117T022650Z`) | flag stage | flex (default) | calibrate, apply |
| B, cut off | after calibrate (`rang_apply_20261117T034709Z`): 19 antennas without a cell to m022 | flag stage | flex (default) | calibrate, apply |
| C, strict | as B | flag stage | strict (`calibrate.refantmode`) | calibrate |

Arm A is the same run as #48's E2-N chain ([weights-48.md](weights-48.md) section 3). The refant is
CARACal's auto choice in every arm; the arms record which antenna it picked. If auto does not pick m022
on arm B's flags, the cut-off set is recomputed for the picked refant before any solution is read, and
the arm stands as long as at least 10 antennas lose every baseline to it; otherwise `refant: m022` is set
in B and C (as E2-N's CASA calls used m022), and this is reported.

**Synthetic, through the pipeline path (unit tests on the public fixture):** a simulated MS with the k53
generator (12 antennas, 64 channels, ±8 ns, refant list [0, 1]) run through `rang.cal_chain` (the code
`rang-core run` calibrate calls), K then G then B, with (i) every baseline of antenna 0 flagged in one
interval and (ii) one antenna's baseline to antenna 0 flagged in another; checked: K, G and B flag no
antenna with data, K delays within 1e-6 ns of truth in the noise-free twin, `refant_used` as #53's.
The same through `rang.cal_chunks` if the chain's chunked path solves K.

## 3. Oracle

CASA 6.7.6.14 (`rang-o-casa_6.7.6.14.sif`, WSL or nash apptainer) `gaincal(gaintype='K', solint='inf',
refantmode='flex', minsnr=3, minblperant=4)`, uvrange and model as E2-N's `e2n_casa3b.casa_calls`, on
a copy of the J1939−6342 rows with arm B's flags:

- **O1, the failure:** refant m022 (or the arm's auto refant). Expected: the cut-off antennas flagged, as
  in e2n-followup. Recorded as CASA's behaviour, not a parity bar.
- **O2, the parity bar:** refant m058 (e2n-followup's probe, an antenna with no wholly flagged baseline
  in this flag state; if auto picks another refant, the probe is redone for it before any solution is
  read). Rang's arm-B K delays, re-referenced to m058 per interval and hand (τ_p − τ_m058), against CASA
  at m058, over antennas both solve.

## 4. Tolerances and decision rule (frozen)

- **K1:** arm B flags K only for antenna-intervals without any unflagged cross cell (expected 0 of 62).
- **K2 (O2):** |Δτ| median ≤ 0.01 ns and p95 ≤ 0.03 ns (E2-N's 3b K row, C2b's), over antennas both solve,
  including the 19.
- **K3, against arm A:** arm B's delays re-referenced to A's reference: median |Δτ| ≤ 0.01 ns and p95 ≤
  0.03 ns over the 19 (reported for the rest). B's flags remove 18 % of J1939's baselines, so this is a
  consistency check, not truth.
- **D1, downstream:** for each of G, B, Gsec and F, the fraction of flagged solutions in B is at most A's
  plus 1 percentage point.
- **D2, target:** the target's flagged fraction after calflag apply in B is at most A's plus 1
  percentage point.
- **C:** arm C flags at least the 19 antennas (strict reproduces CASA's rule on the chain path).
  Reported; it fails only as a sign that the plumbing does not reach K.

**Rule.**
1. K1, K2, K3, D1, D2 pass and the synthetic pipeline tests pass: #60 is **met by #53's flex fallback**
   as shipped in 0.4.0; the branch adds the pipeline tests, the measured record and a `docs/limits.md`
   line; no solver change.
2. A K gate or a synthetic test fails: the fault is traced and fixed in this branch (one dated revision,
   bit-identical where the refant's baselines are present, #53's G1 gate re-run), then re-measured on the
   same arms; the outcome stands after that.
3. K passes but D1 or D2 fails: the downstream term that flags is named and traced. A fix of that term
   (for example G or B with the refant cut off) follows the same one-revision rule; if it needs more than
   that, it is recorded as a known limitation with its own issue, and #60's K part is met.

## 5. Hosts and runs

nash (`nice -n 19 ionice -c3`, nash's main-checkout `tools/heavy_lock.py run --slots N --mem G`, more
than 100 GB free at start), run root `nash:~/rang-data/outputs/weights-k-20261125/`; CASA in the nash
apptainer image or WSL. Arms A and B run calibrate and apply (each about 3 h at E2-N's size on nash,
apply-calwt's timing); C calibrate only. Timing rows in [tool-timings.md](tool-timings.md); archive
`research/results/k60/` (JSON records and K tables' per-antenna values, no MS).

## 6. Measured

Nothing yet.

## 7. Outcome

Not yet.

## 8. Amendments

None yet.
