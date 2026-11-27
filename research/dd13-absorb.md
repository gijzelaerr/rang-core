# DD13: stopping the trusted gains' absorption of the off-axis model gap, on O

Issue #15. Follows [dd12-msclean.md](dd12-msclean.md) (DD12),
[dd11-start.md](dd11-start.md) (DD11) and [dd10-gs.md](dd10-gs.md) (DD10).
Branch `dd13-absorb`. Coordinator brief 2026-11-27. Sections 1-9 are frozen
2026-11-27, before the code that runs them and before any measurement.
Later changes are dated amendments, committed before the reading they
affect, and labelled post hoc where they follow a reading.

Status: **measured on O 2026-11-27; real reading R-QP12 running.**
- **Frozen answer on O: "yes: QP12 stops the absorption and the loop from
  solved gains closes on O".** QP12 (unit-amplitude image gains in every
  cycle, the pin boxes released from cycle 2) brings d1 to 0.116 at 12
  cycles (G_d1 0.686, 0.56 × Q12's 0.207, Γ 0.80 of the Q12-to-AT12 gap),
  0.136 at 6, without harm; d1's amplitude bias falls from −0.116 (Q12) to
  −0.004.
- **The pin limits the loop**, with the truth gains too: ATP12 0.069
  against AT12 0.093. The amplitude constraints alone do not close: QA12
  stopped at 6 (d3 0.459 > 1.2 × Q6's; d1 0.238), SA12 no effect (0.226).
- UV12 not run: gate UV failed as frozen (1.8 % of the solve weight lies
  below 1,074 λ). The split controls read "not mainly in the amplitudes"
  and "not mainly in the phases".

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

Run root `D:/rang/outputs/dd13-20261127/`. Host glacier, shared, under the
main checkout's `heavy_lock.py`; two lanes, every loop 8 slots, 20 GB
booked. Archive `results/dd13-absorb/` (per-cycle records, `score.json`,
`diag.json`, `pinflux.json`, gates, `reuse.json`, `times.log`).

**Setup.** O rebuilt (212 s): DD11's setup gate passes; the PSF peak
equals DD10's. Reused files and their SHA-256 are in `reuse.json`.

**Gate R13: pass.** From DD12's Q12 cycle-11 gains and M₁₁, `hogbom_fast`
gives DD12's M₁₂ bit for bit (2,772 components); the cycle-12 scored solve
on DD12's M₁₂ gives DD12's gains and flags bit for bit (500 iterations).
DD12's Q12 and AT12 records are reused.

**Gate UV: fail (frozen outcome).** The 1,074 λ cut removes 1.8 % of O's
unflagged solve weight (558,479 of 30.8 M cells), below the 5 % bar; no
antenna-interval loses all its data. **UV12 is not run.** With so little
weight below the 64 px scale, an inner cut there cannot move the solve on
O. A cut at a longer scale would be a new, post hoc arm and is not run.

### The arms on O (sections 5 and 6)

Every scored point: Rust Gauss-Seidel `ap`, 4 × 8 s, all baselines, d0
free, cap 500. Q6, Q12, AT6 and AT12 are DD11's and DD12's scored points
(reused, gate R13). References: A0 0.352, 0.544, 1.000; AX 0.0078, 0.0334,
0.0523. b d1 is diagnostic D's signed d1 amplitude bias on the scored
gains.

| Point | e d1, d2, d3 | G d1, d2, d3 | Γ | e/ê d1-d3 | fractions d0-d3 | d3 \|g\| p99 / max | b d1 | Reading | Against Q at N |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Q6 (DD11) | 0.244, 0.301, 0.365 | 0.313, 0.476, 0.670 | 0 | 47, 8.3, 7.0 | 0.983, 0.950, 0.947, 0.948 | 1.83 / 2.5 | −0.107 | partly | - |
| Q12 (DD12) | 0.207, 0.343, 0.301 | 0.420, 0.394, 0.737 | 0 | 42, 9.3, 5.8 | 0.988, 0.958, 0.957, 0.956 | 1.65 / 2.0 | −0.116 | partly | - |
| **QA6** (stopped) | 0.238, 0.347, 0.459 | 0.332, 0.386, 0.571 | 0.055 | 40, 9.8, 9.1 | 0.997, 0.975, 0.974, 0.974 | 2.20 / 2.9 | −0.054 | partly | **hurts** (d1 0.974 ×, d3 1.26 ×) |
| **SA6** | 0.247, 0.307, 0.341 | 0.305, 0.464, 0.695 | −0.023 | - | 0.962, 0.946, 0.931, 0.930 | 1.72 / 2.3 | −0.106 | partly | no effect (1.011 ×) |
| **SA12** | 0.226, 0.335, 0.321 | 0.364, 0.409, 0.716 | −0.168 | 45, 9.2, 6.1 | 0.992, 0.961, 0.957, 0.956 | 1.65 / 2.0 | −0.121 | partly | no effect (1.093 ×) |
| **QP6** | 0.136, 0.317, 0.336 | 0.629, 0.445, 0.701 | 0.939 | - | 0.981, 0.951, 0.947, 0.948 | 1.76 / 2.2 | −0.006 | **closes** | **helps** (0.555 ×) |
| **QP12** | **0.116**, 0.312, 0.317 | **0.686**, 0.455, 0.721 | 0.797 | 17, 9.1, 5.9 | 0.980, 0.945, 0.938, 0.939 | 1.70 / 2.1 | **−0.004** | **closes** | **helps** (0.559 ×) |
| AT6 (control) | 0.128, 0.279, 0.387 | 0.649, 0.520, 0.647 | 1 | 22, 8.0, 7.8 | 0.994, 0.975, 0.974, 0.974 | 1.95 / 2.9 | −0.063 | closes | - |
| AT12 (control) | 0.093, 0.243, 0.300 | 0.753, 0.589, 0.738 | 1 | 15, 7.0, 6.0 | 0.982, 0.933, 0.921, 0.922 | 1.68 / 2.2 | −0.040 | closes | - |
| ATP6 (control) | 0.072, 0.202, 0.283 | 0.813, 0.670, 0.757 | 1.49 | - | 0.991, 0.961, 0.956, 0.956 | 1.78 / 2.4 | −0.017 | closes | helps against AT6 (0.561 ×) |
| ATP12 (control) | 0.069, 0.198, 0.272 | 0.822, 0.678, 0.768 | 1.21 | 11, 5.5, 4.9 | 0.988, 0.946, 0.939, 0.939 | 1.75 / 2.3 | −0.016 | closes | helps against AT12 (0.744 ×) |
| ATa3 (control) | 0.266, 0.377, 0.591 | 0.248, 0.327, 0.431 | - | - | 0.947, 0.919, 0.910, 0.881 | 2.76 / 4.7 | −0.098 | partly | - |
| ATp3 (control) | 0.257, 0.286, 0.475 | 0.274, 0.506, 0.554 | - | - | 0.998, 0.980, 0.959, 0.965 | 2.21 / 3.5 | −0.164 | partly | - |

No arm harms d2 or d3 against A0. e on converged cells is within 0.001 of
e on all cells for every point. Γ above 1 for ATP means that the released
pin also beats the pinned truth-gain control.

**Frozen readings (section 6):**
- **QA12: stopped at N = 6 by the stage rule.** Its d1 (0.238, 0.974 ×
  Q6's) alone is "no effect", but its d3 (0.459) exceeds 1.2 × Q6's 0.365,
  so the effect reads "hurts". Absorption **not reduced**: b d1 −0.054
  against Q6's −0.107, above the half (0.0535) by 0.0005.
- **SA12: no effect** at 6 (1.011 ×) and 12 (1.093 ×); b d1 −0.121
  against −0.116, **not reduced**. A time-constant amplitude keeps the
  bias.
- **QP12: closes** at both N (G_d1 0.629 and 0.686); **helps** against Q at
  6 (0.555 ×) and 12 (0.559 ×); **absorption reduced** (b d1 −0.004
  against −0.116). QP6 also helps against QA6 (0.570 ×).
- **Pin: "the pin limits the loop"** (QP6 helps against QA6; ATP12 helps
  against AT12, 0.744 ×).
- **Split controls:** S_a 0.26, **"not mainly in the amplitudes"**; S_p
  0.32, **"not mainly in the phases"**. With truth amplitudes or truth
  phases alone, three cycles reach d1 0.266 and 0.257 (AT 0.161, ATs
  0.304): neither factor alone carries the absorbed gap, which fits a model
  error that both factors fit (the pin, below).
- **DD13's answer (frozen): "yes: QP12 stops the absorption and the loop
  from solved gains closes on O".** Best arm **QP12** (no harm, lowest
  d1). The frozen rule calls for the real reading (section 7).

**Mechanism (diagnostic D and pin flux; reported, not frozen).**
- d1's amplitude bias by baseline length (< 500 m, 500-2,000 m,
  > 2,000 m): A0 +0.07, −0.16, −0.90; Q12 +0.11, −0.14, −0.61; AT12
  +0.03, −0.04, −0.45; QP12 +0.04, +0.01, −0.17; ATP12 +0.02, −0.01, −0.19.
  The bias sits on the long baselines, the sign of a model too bright in
  compact flux, and releasing the pin removes most of it.
- Pin flux (post hoc A2, `pinflux.json`): in d1's 5 × 5 pin box sky O
  holds 0.24 Jy and the 16 px ring round it 1.20 Jy. M₀ᶜ and every pinned
  arm keep 0.96 Jy in the box at every cycle. QP12 ends with 0.66 Jy in the
  box and 0.87 Jy in the ring; ATP12 0.69 and 0.78. The d1 pin holds M₀ᶜ's
  catalogue point flux where sky O (DD8's DEEP) has the source resolved, so
  on O the pin sets d1's amplitude scale wrong, and the trusted gains
  absorb it. The d2 and d3 pins match the sky (0.10 and 0.08 Jy).
- d1 in QP12's solves per cycle: 0.352, 0.304, 0.289 (cycles 0-2, Q12's),
  then 0.192 after the first released cycle, 0.165, 0.147, 0.135, 0.129,
  0.124, 0.121, 0.119, 0.117, scored 0.116. Högbom components fall from
  3,498 (cycle 4) to 150 (cycle 11), with increments under 0.01 Jy from
  cycle 5. The loop has converged; the remaining 0.116 against ATP12's
  0.069 is the solved gains' share.
- d1 net model flux at M₁₂: QP12 3.82 Jy, ATP12 3.56, Q12 3.38 (sky O
  4.43). e/ê in d1: QP12 17, Q12 42, ATP12 11.

**Caveat for real data (not tested on O).** QP12 holds the facet flux
scale through the unit-amplitude images, not through the catalogue pin.
On O this is right by construction (the truth amplitudes have mean
log-amplitude about 0), and the pin is wrong by construction (M₀ᶜ's
catalogue flux against DEEP's resolved source). On real data the
catalogue flux may be right and the true facet amplitude not 1 (primary
beam; DD3's and DD3c's flux-gain trade-off). The real reading tests
convergence, not this.

**Cost.** Loop walls (8 slots booked, lock waits included): QA12 5,529 s
(stopped at 6); SA12 11,715 s; QP12 10,967 s; ATP12 5,044 s; ATa3 3,400 s;
ATp3 3,365 s. Solve walls summed: QA12 4,408 s, SA12 9,270 s, QP12
9,352 s, ATP12 2,892 s, ATa3 2,523 s, ATp3 2,322 s; a GS solve 520-800 s,
Högbom 200-300 s per cycle. Solves used: gate R13 1, QA12 5, SA12 12,
QP12 12, ATP12 4, ATa3 4, ATp3 4: 42 of the 65 capped (UV12's 16 not run,
QA12 stopped).

REAL_PLACEHOLDER

## Amendments

**A1, 2026-11-27, a correction to `score`'s answer condition (after
QA12's stage stop was read, before any other arm's scored point was read).
It changes no frozen rule.** The code computed DD13's answer only when all
four arms had a final N, so it gave none with UV12 not run. Section 5 says
a failed gate UV means UV12 is not run; the answer is now read over the
arms that run (QA12, SA12, QP12).

**A2, 2026-11-27, post hoc diagnostic (after every O reading). It changes
no frozen rule or reading.** DD12's `pinflux` on DD13's models (Q12,
QA12, QP12, AT12, ATP12, SA12): the flux in each pin box and its 16 px
ring per cycle against sky O (`pinflux.json`, zero solves). Section 10's
mechanism paragraph reads it.
