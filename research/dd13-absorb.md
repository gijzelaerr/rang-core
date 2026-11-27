# DD13: stopping the trusted gains' absorption of the off-axis model gap, on O

Issue #15. Follows [dd12-msclean.md](dd12-msclean.md) (DD12),
[dd11-start.md](dd11-start.md) (DD11) and [dd10-gs.md](dd10-gs.md) (DD10).
Branch `dd13-absorb`. Coordinator brief 2026-11-27. Sections 1-9 are frozen
2026-11-27, before the code that runs them and before any measurement.
Later changes are dated amendments, committed before the reading they
affect, and labelled post hoc where they follow a reading.

Status: **frozen 2026-11-27, not yet measured.**

## 1. Question and hypotheses

On simulation O (truth known), every scored point Rust Gauss-Seidel `ap`,
4 × 8 s, d0 free, cap 500, rule U (untrusted gains set to 1 in the images):

| Earlier arm | e d1, d2, d3 | G d1 |
| --- | --- | --- |
| A0 (M₀ᶜ) | 0.352, 0.544, 1.000 | 0 |
| AX (sky O, exact) | 0.0078, 0.0334, 0.0523 | 1 |
| Q6 (DD11: unit-amplitude images in cycles 0-1, Högbom, 6 cycles) | 0.244, 0.301, 0.365 | 0.313 |
| Q12 (DD12: the same, 12 cycles) | 0.207, 0.343, 0.301 | 0.420 |
| AT6 / AT12 (truth gains in the images) | 0.128 / 0.093 (d1) | 0.649 / 0.753 |
| AT (DD10, 3 cycles) / ATs (DD11, 3 cycles: truth gains only where untrusted) | 0.161 / 0.304 (d1) | |

DD11's confound ATs: with O's truth gains replacing only the untrusted
gains, three cycles reach d1 0.304, the same as solved gains; the trusted
(solved) gains carry the absorbed gap. DD11's diagnostic D: A0's d1
products are 16 % low in amplitude and 0.20 rad off in phase; cycles fix
the phase (0.20 to 0.12 rad), not the amplitude (bias −0.16 before and
after). Q6's unit-amplitude start helped (0.894 × U6).

**DD13's question.** Does stopping the trusted gains' absorption, by
constraining their amplitudes in the images, by excluding the short
baselines (where d1's missing extended flux lives) from the loop's solves,
or by releasing the catalogue pin, close the Q12-to-AT12 gap?

Hypotheses:
- **H-amp.** The absorption that holds d1 sits in the trusted gains'
  amplitudes. Constraining the amplitudes in every cycle's images (not only
  cycles 0-1) lets the residual images show the gap. Arms QA12 (unit
  amplitude, the strongest constraint) and SA12 (amplitude constant in time,
  per antenna, direction and hand, phase free). Split controls ATa3 and
  ATp3 say whether amplitude or phase carries the absorption.
- **H-uv.** d1's missing flux is extended (sky O's d1 holds structure to
  about 64 px, DD12 section 1); unmodelled extended flux is absorbed through
  the short baselines. Solving the loop's gains without the baselines
  shorter than that scale stops the absorption. Arm UV12.
- **H-pin (a hypothesis, not a finding).** The amplitude bias has the sign
  of a model that is too bright, while d1's model is too faint in total
  (M₀ᶜ 2.83 Jy against 4.43). DD12's A3: d1's 5 × 5 pin box holds 0.97 Jy
  in M₀ᶜ against sky O's 0.24 Jy, in every arm, because the pin box is never
  cleaned (DD3c: the pin fixes the facet's amplitude scale). If the pin's
  compact flux sets a wrong amplitude scale, releasing the pin boxes (with
  unit-amplitude images, so the scale stays at the gain convention) helps.
  Arm QP12 against QA12; control ATP12 against AT12.

Not claimed: anything on real data unless section 7's rule calls for it;
any novelty (section 8).

## 2. The brief's candidate arms, and why two of them are not run

The brief named (a) solving the trusted directions' gains against a model
that includes the current DD-corrected d1-d3 prediction, (b) amplitude held
to a smoothness/time constraint, phase free, (c) a joint solve of trusted
and untrusted directions per interval.
- **(c) is the scored solve already.** Every loop solve is one `diag_dd`
  solve of d0-d3 together per 4 × 8 s interval (Gauss-Seidel over the
  directions). DD9 and DD10 showed that Jacobi, Gauss-Seidel and DD9's
  joint update reach the same fixed point wherever their flags agree
  (DD10 K3: 1.8e-14). A different update of the same χ² moves the route,
  not the fixed point, so it cannot change what is absorbed. Not run;
  predicted null from that evidence.
- **(a) is the loop already, as read here.** Each cycle's solve uses
  M_k, which holds the DD-corrected d1-d3 model built so far (the facet
  predicts of M_k, all four directions). Trust in rule U is per gain cell
  (antenna, interval, direction), not per direction, so "trusted
  directions" has no separate model to add. Folding the previous gains into
  the model is a re-parameterisation of the same χ². Not run; the brief's
  wording may mean something else, which the hand-back flags.
- **(b) is run on the image side** (QA12, SA12). A solve-side amplitude
  prior exists only in DD9's NumPy reference (bR, σ_A 0.2, d3 only, which
  left d1 at 0.356 in a single solve); the Rust kernel has none, and
  Gauss-Seidel is `ap` only, while the Jacobi phase-only term does not
  converge with four facets (DD11's P6). A solve-side constraint would
  need a new Rust option with DD10-style gates, an oracle-gated path. DD13
  first asks whether the amplitude is the lever at all (QA12, SA12, ATa3);
  a solve-side prior is the follow-up only if it is.
- What does move the solve's fixed point without a kernel change: its
  weights (UV12). What moves the model built from it: the image gains
  (QA12, SA12) and the clean mask (QP12).

## 3. Data, inputs and reuse

DD7's to DD12's roots under `D:/rang/outputs/` are read only. DD13's root
is `D:/rang/outputs/dd13-20261127/`.

- **O:** rebuilt in DD13's root by `dd8.insert` (DD8's code, unchanged).
  Setup gate (DD11's): GO passes, every `build.json` number equals DD10's
  to 1e-9 relative, `sky.npy` has DD8's SHA-256.
- **PSF:** DD10's `fits_image` PSF of `w_I` on O; peak equal to DD10's to
  1e-9 relative.
- **Reused from DD12** (copied into DD13's root with their SHA-256 in
  `reuse.json`, never changed there):
  - Q12's cycles 0-12 (`info.json`, `gains.npz`, `next_model.npy`; DD12
    kept no residual arrays). Q12's cycles 0-5 and cycle-6 solve are
    DD11's Q6.
  - AT12's cycles 0-12 (`info.json`, `next_model.npy`, the scored
    `gains.npz` at cycles 6 and 12).
  - DD12's `score.json` and its reused DD10/DD11 score files (A0, AX, AT,
    ATs references).
- **Reused from DD11:** ATs's records (`score.json` entry) and A0's gains
  (Q6 `cycle-0/reuse_gains.npz`).
- **Gate R13** (section 5) checks the reproduction before any reuse is
  relied on.
- **Shared prefixes.** QA12, SA12 and QP12 keep Q6's start (cycles 0-1
  unit-amplitude images), so their cycles 0-1 and their cycle-2 solve (on
  M₂) are Q12's, reused; they differ from cycle 2's image on. ATP12's cycles
  0-1 are AT12's (reused); it differs from cycle 2's minor cycle on. ATa3
  and ATp3 reuse A0's cycle-0 solve. UV12 differs from its cycle-0 solve.

## 4. Shared rules

- **Scored point (frozen, every arm and control):** DD11's: Rust `diag_dd`,
  Gauss-Seidel `ap`, 4 × 8 s, all channels, **all baselines and weights**,
  d0 free, refant None, stop 1e-7, stop fraction 0.99, cap 500, plus the
  one-longer solve for the per-direction fractions; DD10's `scores`. Arms
  differ only in how the model was built. For QA12, SA12, QP12 the cycle-6
  loop solve is that solve (the loop solves are the scored solver); for
  UV12 the scored solves are extra solves beside the loop's cut solves.
- **Cycle:** DD12's (solve with M_k; residual at the image gains; flat-gain
  facet images with `w_I`; DD11's `hogbom_fast`, gain 0.1, at most 5,000
  components, stop max(5σ, 1 mJy), σ the MAD rms of the d1-d3 interiors;
  peaks in the d1-d3 interiors minus DD4's 5 × 5 pin boxes unless the arm
  releases them; M_{k+1} = M_k + components; d0 not cleaned). Truth-gain
  arms solve only at their scored points.
- **N:** 12 for the loop arms, scored at M₆ and M₁₂ (the 12-cycle arms'
  cycle-6 solve gets the one-longer solve as well). 3 for the split
  controls (scored at M₃, against DD10's AT and DD11's ATs at 3 cycles).
- **Stage stop (frozen).** After an arm's M₆ scored point, the arm
  continues to 12 cycles unless its effect against Q6 (section 6) reads
  "hurts" (marginal or not). A stopped arm is read at N = 6 only and
  reported as stopped. ATP12 always runs to 12 (no solves inside).
- No stop rule reads the truth.

## 5. Arms and gates

| Arm | Solve in cycles | Image gains (trusted cells; untrusted → 1 unless stated) | Clean mask | Cycles | Eligible as best |
| --- | --- | --- | --- | --- | --- |
| **Q12** (control, DD12's) | GS `ap` | g/\|g\| in cycles 0-1, g after | pins excluded | 12 | yes |
| **QA12** | GS `ap` | g/\|g\| in every cycle | pins excluded | 12 | yes |
| **SA12** | GS `ap` | g/\|g\| in cycles 0-1; from cycle 2, Ā·g/\|g\| | pins excluded | 12 | yes |
| **UV12** | GS `ap`, cells with uv < 1,074 λ flagged in the solve only | Q12's rule | pins excluded | 12 | yes |
| **QP12** | GS `ap` | QA12's | cycles 0-1 pins excluded; from cycle 2 pins released | 12 | yes |
| **AT12** (control, DD12's) | none | truth | pins excluded | 12 | no |
| **ATP12** (control) | none | truth | cycles 0-1 pins excluded; from cycle 2 released | 12 | no |
| **ATa3** (control) | GS `ap` | \|g_truth\|·g/\|g\|; untrusted → truth | pins excluded | 3 | no |
| **ATp3** (control) | GS `ap` | \|g\|·g_truth/\|g_truth\|; untrusted → truth | pins excluded | 3 | no |

- **SA12's Ā (frozen):** per antenna, direction and hand, the median of the
  cycle's own trusted |g| over all intervals: an amplitude constant over the
  observation, the strongest time constraint, chosen without reference to
  O's gain periods. Untrusted cells (rule U) take part in neither the
  median nor the image (set to 1). Where an antenna-direction-hand has no
  trusted interval, Ā = 1.
- **UV12's cut (frozen):** u_min = 1 / (64 px × 3″) = 1 / 9.309e-4 rad =
  **1,074 λ**, per row and channel (|uv| × ν / c). 64 px is sky O's
  largest d1 structure scale from DD12 section 1, fixed before any UV12
  record. The cut cells are flagged (all four correlations) in the loop's
  solves only; the images and the scored points use every cell. The share
  of `WEIGHT_SPECTRUM` removed is recorded. The cut's own truth error per
  cycle is reported (it is a 4 × 8 s `ap` solve on the same gains, so it is
  comparable, but it is not the scored point).
- **QP12 and ATP12's release:** the Högbom search pixels are the d1-d3
  interiors with the pin boxes included, from cycle 2 on (both signs, as
  Högbom already searches |r|). d0 stays uncleaned. QP12 pairs the release
  with unit-amplitude images, so the facet's amplitude scale is held at the
  gain convention (O's truth amplitudes have mean log-amplitude about 0)
  instead of by the pin.
- **ATa3 and ATp3** follow DD11's ATs (truth gains where untrusted, all
  weight) and replace one factor of the trusted gains by the truth's.

**Gate R13 (reproduction, blocking; frozen).** With this worktree's
extension and the rebuilt O: (1) Q12's cycle-11 image from DD12's Q12
cycle-11 gains and M₁₁ (DD12's `cycle-10/next_model.npy`), rule U: the
float64 residual (DD12 kept no residual arrays) through `hogbom_fast`
giving DD12's `cycle-11/next_model.npy` (M₁₂) bitwise; (2) the cycle-12
scored solve on DD12's M₁₂ giving DD12's Q12 `cycle-12/gains.npz` gains and
flags bitwise. Pass: DD12's Q12 and AT12 files are reused as section 3 says, and
Q12 counts as "reproduced (bitwise)" in this sense: one late cycle and the
final scored solve reproduce bit for bit; the full Q12 is not rerun. Fail:
no reuse; the miss is reported, Q12 is rerun in full (13 solves) and the
other arms wait for it. No loop starts before gate R13 passes.

**Gate UV (frozen, no truth read).** On O: the cut removes at least 5 % and
at most 60 % of the solve weight, and every antenna keeps unflagged cells
in every interval after the cut. Fail: UV12 is not run; the miss is
reported.

## 6. Scores and frozen readings

For every scored point: e_d (all unflagged cells) in d1-d3,
`G_d = (e_A0,d − e_d) / (e_A0,d − e_AX,d)`, e on converged cells, e/ê,
per-direction fractions, d3 |g| p99 and max, d1-d3 Σ|M − sky O| and net
flux, components and stop per cycle, untrusted shares, and:
- **Gap share** `Γ_N = (e_Q,d1 − e_d1) / (e_Q,d1 − e_AT,d1)` at matched N
  (Q6 0.244 and AT6 0.128 at 6; Q12 0.207 and AT12 0.093 at 12).
- **Absorption measure (diagnostic D, zero solves):** on the scored gains,
  per facet d1-d3 on unflagged cells against the truth products (DD11's
  section 5): the signed amplitude bias b_d (median of |P|/|P̄| − 1), the
  amplitude error, the phase-only e_d. Also, reported only, d1's bias per
  baseline length bin (< 500 m, 500-2,000 m, > 2,000 m), for H-pin. D is
  computed also for A0, Q6, Q12, AT6 and AT12's scored gains.

**Per-arm reading (DD10's, unchanged):** harm: e_d > 1.2 e_A0,d in d2 or
d3; **closes:** G_d1 ≥ 0.5 and no harm; **partly:** 0.2 ≤ G_d1 < 0.5 and no
harm; **moves the error:** G_d1 ≥ 0.2 with harm; **no:** G_d1 < 0.2.

**Effect against the matched control (DD12's rule, frozen):** an arm at N
against Q at N (QP12 also against QA12 at N; ATP12 against AT12 at N):
- **helps:** e_d1 ≤ 0.9 × the control's and e_d2, e_d3 ≤ 1.2 × its;
- **hurts:** e_d1 ≥ 1.1 × the control's, or e_d2 or e_d3 > 1.2 × its;
- else **no effect**; "helps" or "hurts" with the d1 ratio within 0.02 of
  its bar (0.88-0.90, 1.10-1.12) is **marginal**.

**Absorption reduced (frozen):** |b_d1| at the arm's final N ≤ 0.5 × |b_d1|
of Q at the same N.

**Split controls (frozen), at 3 cycles against AT (0.161) and ATs
(0.304):** `S_a = (e_ATs,d1 − e_ATa3,d1) / (e_ATs,d1 − e_AT,d1)`:
≥ 0.8: **the absorption sits in the trusted amplitudes**; < 0.5: **not
mainly in the amplitudes**; else **partly in the amplitudes**. The same
for S_p and ATp3 (**phases**).

**Pin (frozen):** **the pin limits the loop** if QP12 helps against QA12 at
its final N or ATP12 helps against AT12 at 12; **releasing the pin hurts**
if either hurts and neither helps; else **the pin does not limit**.

**DD13's answer (frozen),** over QA12, SA12, UV12 and QP12 at each one's
final N:

| Condition | Reading |
| --- | --- |
| some arm closes | **yes: X stops the absorption and the loop from solved gains closes on O** |
| none closes; some arm helps against Q (marginal or not) | **partly: X closes Γ of the Q-to-AT gap** (with "absorption reduced" or "not reduced" for X) |
| no arm helps; some arm reduces absorption | **absorption reduced, gap not closed: the amplitude bias is not what holds d1** |
| no arm helps; none reduces absorption | **no: none of the tested constraints stops the absorption** |

With several arms in a row, X is the best arm. **Best arm (frozen):**
among Q12 and the four arms without harm at their final N, the lowest
e_d1 at 12 (a stopped arm competes with its N = 6 value against Q6's
0.244, and cannot be best over a 12-cycle arm with lower e_d1); within
0.005, the lower mean of e_d2 and e_d3, then the fewer constraints (Q12
first). Controls cannot be chosen.

## 7. One real reading

Only if the best arm is QA12, SA12, UV12 or QP12 and reads "helps"
(marginal or not) against Q12 without harm: that arm's loop on DD7's real
subset with the 145 bad baselines flagged (setup gate 65,250 rows), from
RM, its rules (UV12's cut in real λ, the same 1,074 λ), 12 cycles, read by
DD11's section-7 rule (lifts: min d1-d3 fraction ≥ R0's + 0.20; tames d3:
p99 ≤ 3 and max ≤ 10; supported by O if the arm reads closes or partly on
O), beside DD11's R-Q6. Convergence, not accuracy. Otherwise no real arm
runs, and the note says why.

## 8. Literature and novelty

Verified by search on 2026-11-27 unless marked "from recall".
- **Absorption of unmodelled flux by calibration is established.**
  Grobler et al. 2014, MNRAS 439, 4030 (Calibration artefacts I, ghost
  sources from incomplete sky models; arXiv 1402.1373) and Wijnholds,
  Grobler & Smirnov 2016 (Calibration artefacts III, arXiv 1606.06320): a
  suppression ghost on unmodelled sources; phase-only calibration
  behaves differently. Mevius et al. 2022 (arXiv 2111.02537): in LOFAR
  DD calibration, excluding short baselines avoids suppression on them
  but adds excess variance from overfitting. Patil et al. 2016, MNRAS 463,
  4317: suppression of diffuse emission and excess noise from calibrating
  on incomplete models; long-baseline-only calibration as a remedy, with
  its costs.
- **uv cuts in DD solves are standard practice** (LOFAR EoR's 250 λ cut;
  ddf-pipeline's killMS solves with a uv range, from recall; van Weeren
  et al. 2016, ApJS 223, 2, facet calibration, arXiv 1601.05422).
- **Joint DD solves** (CohJones: Tasse 2014, arXiv 1410.8706; Smirnov &
  Tasse 2015, MNRAS 449, 2668, arXiv 1502.06974) and killMS's Kalman filter
  (cited as Tasse 2016 elsewhere; the brief's "Tasse 2014 killMS" is the
  CohJones paper) are what rang's `diag_dd` already is in kind.
- **Amplitude smoothness/regularisation** (SAGECal consensus over
  frequency, Yatawatta 2015; DDFacet/killMS with smoothed solutions,
  Tasse et al. 2018, A&A 611, A87): from recall, not re-verified. The
  brief's "Albert 2020 DDFacet/SPAM-like" was not found; Albert et al.
  2020 (A&A, probabilistic DD ionospheric calibration for LOFAR-HBA) is a
  phase-screen method, from recall.
- **Reading:** every arm is an established remedy, tested in rang's loop
  on a simulation with a known gap. DD13 is a parity/understanding step: it
  says which established lever, if any, moves rang's d1 gap. It claims no
  novelty; a win would be a recipe choice against Q12, not against
  killMS/DDFacet, which were not run.

## 9. Implementation, host and cost

- `tools/oracles/dd13/dd13.py` (new, MIT): `reuse`, `gater13`, `gateuv`,
  `loop` (QA12, SA12, UV12, QP12, ATP12, ATa3, ATp3 and the real arm),
  `diag`, `score`. It imports DD12's and DD11's drivers for the context,
  solves, images, `hogbom_fast` and scores; no solver or library change.
  `tests/test_dd13.py`: SA's Ā and the uv-cut mask on small synthetic
  inputs.
- Python: this worktree's own `.venv` with its extension.
- glacier, shared, under the main checkout's `tools/heavy_lock.py`: a loop
  with solves 8 slots, 20 GB (DD11/DD12's figure, about 11.5-16 GB
  resident); truth-gain loops the same (their scored solves need 8); O
  rebuild 2 slots, 10 GB; PSF 4 slots, 10 GB; gate R13 8 slots, 20 GB. At
  most two loops at once. No exclusive or timing runs. nash is not used.
- **Run cap (Rust solves, one-longer solves counted):** gate R13 1; QA12 12
  (9 loop solves in cycles 3-11, the cycle-6 one-longer, 2 at M₁₂); SA12
  12; QP12 12; UV12 16 (12 cut loop solves, 2 scored at M₆, 2 at M₁₂);
  ATP12 4; ATa3 4; ATp3 4. That is 65, plus one spare per class (gate,
  arms, controls): 68. A stopped arm uses fewer. Real arm, if run: 14 + 1.
- Expected: a GS solve 600-800 s at 8 slots, an image set 30-60 s, Högbom
  185-310 s per cycle; about 50,000 s of jobs, 7-9 h with two at once.
  Wall times go into [tool-timings.md](tool-timings.md). The rebuilt O MS
  and the PSF array are deleted at the end; records stay in the run root, a
  compact archive in `results/dd13-absorb/`. D: stays above 150 GB free.

## 10. Measured result

Not yet measured.

## Amendments

None.
