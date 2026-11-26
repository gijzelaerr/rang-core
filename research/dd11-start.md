# DD11: a start that keeps the solved gains from absorbing the off-axis model gap, on O

Issue #15. Follows [dd10-gs.md](dd10-gs.md) (DD10),
[dd9-solver.md](dd9-solver.md) (DD9) and [dd8-offaxis.md](dd8-offaxis.md)
(DD8). Branch `dd11-start`. Coordinator brief 2026-11-26. Sections 1-9 are
frozen 2026-11-26, before the code that runs them and before any
measurement. Later changes are dated amendments, committed before the
reading they affect.

Status: **proposed 2026-11-26.**

## 1. Question and hypotheses

DD10 on simulation O (truth known), all scored solves Gauss-Seidel,
4 × 8 s, d0 free, cap 500:

| DD10 arm | images from | e d1, d2, d3 |
| --- | --- | --- |
| A0 (M₀ᶜ) | - | 0.352, 0.544, 1.000 |
| AX (sky O, exact) | - | 0.0078, 0.0334, 0.0523 |
| AL (frozen, 3 cycles) | solved gains, rows with an untrusted gain dropped (2-27 % of the weight kept) | 0.395, 0.404, 0.478 |
| ALu (A1, post hoc, 3 cycles) | solved gains, untrusted gains set to 1, all rows | 0.305, 0.345, 0.536 |
| AT (control, 3 cycles) | O's truth gains, all rows | 0.161, 0.312, 0.500 |

DD10's frozen reading was "the rule can build the model, but the solved
gains are too wrong to bootstrap it". Its own caveat: AL's failure is not
separated from AL's weight loss.

**DD11's question.** Is there a start that keeps the gains from absorbing
the model gap, so that the loop from solved gains closes on O against the
truth?

Hypotheses (each tested by one arm or control, section 4):
- **H-W (weight loss).** AL's failure is mostly its weight loss (and the
  full-weight PSF it was deconvolved with), not absorption. Control ATm.
- **H-A (absorption).** Where the solved gains are trusted, they have
  absorbed M₀ᶜ's gap, so the residual images miss the missing flux.
  Control ATs.
- **H-amp.** The absorption sits in the gain amplitudes (M₀ᶜ's d1 holds
  2.83 Jy of the truth's 4.43 Jy). Removing amplitude freedom at the start
  lets the residual images show the gap. Arms P6 (phase-only solve) and Q6
  (unit-amplitude gains in the images). The zero-solve diagnostic D says
  where the absorption sits in the existing gains.
- **H-int.** Longer first solution intervals absorb less structure.
  Arm L6.
- **H-cyc.** More cycles alone close the gap: ALu still improved at
  cycle 3 (d1 0.334, 0.315, 0.305). Arm U6, with AT6 as its control.

Precedent: in DD9 an amplitude prior (σ_A 0.2) and a 16 × 8 s interval on
d3, in a single solve with M₀ᶜ, left d1 at 0.35-0.39 and did not tame d3.
They were not tried as the start of a model loop. DD9's prior exists only
in DD9's numpy reference, not in the Rust kernel, so DD11 does not use it.

Not done (brief): the unit-gain deep clean (DEEP) is not a model; d3 is not
merged; the robust held-out score is not a criterion.

## 2. Data, inputs and reuse

DD7's, DD8's, DD9's and DD10's roots under `D:/rang/outputs/` are read
only. DD11's root is `D:/rang/outputs/dd11-20261126/`.

- **O:** rebuilt in DD11's root by `dd8.insert` (DD8's code, unchanged).
  Setup gate: GO passes, every `build.json` number equals DD10's
  `O/build.json` to 1e-9 relative, and `sky.npy` has DD8's SHA-256.
  Truth: `truth.npz`, per 4 integrations, k = 0.5291.
- **Models:** M₀ᶜ = DD7's `b/sky.npy`; sky O = the rebuilt `O/sky.npy`;
  RM = DD7's `models/RM.npy`.
- **Real:** DD7's `real/sub.ms` with the 145 bad baselines flagged in
  memory (DD10's `base_ctx`; setup gate 65,250 rows).
- **PSFs:** `fits_image` PSFs of `w_I` on O and on the flagged real subset,
  rebuilt as DD10 built them (DD10 deleted its arrays). PSF peaks must equal
  DD10's `psf/*.json` peaks to 1e-9 relative.
- **Reused from DD10 (copied into DD11's root, never changed there):**
  - A0's cycle-0 gains (`loop/AL/cycle-0/gains.npz`; ALu's cycle 0 is the
    same solve).
  - ALu's cycles 0-2 (gains, records, `next_model.npy`) and ALu's
    cycle-3 gains (the solve with M₃, which in U6 is a non-final cycle).
  - AT's cycles 0-2 `next_model.npy` and records.
  - AL's cycle 0-2 gains (the row masks of control ATm).
  - RL's cycle-0 gains (R0, the solve with RM).
  - The solve is deterministic for fixed inputs (DD10 A1 reused A0's gains
    the same way). Every reused file is listed with its SHA-256 in
    `reuse.json`.
- **Scores of the references:** A0, AX, AT and ALu from DD10's `score.json`
  and point records.

## 3. Shared rules

**Scored point (frozen, every arm and control).** DD10's: Rust `diag_dd`,
Gauss-Seidel, 4 × 8 s, all channels, d0 free, refant None, stop criterion
1e-7, stop fraction 0.99, cap 500, plus the one-longer solve (stop fraction
1.0) for the per-direction fractions; scored on the arm's final model with
DD10's `scores` (e_d on all unflagged cells and on converged cells, ê,
e/ê, fractions, d3 |g| tails). Arms therefore differ only in how the model
was built. Intermediate cycles get e_d without a second solve; e_d of a
phase-only or 16 × 8 s solve is not comparable with the scored points and
is reported only (for P6's start cycles the phase-only truth error,
`dd5.truth_error(..., phase_only=True)`).

**Cycle (DD10's section 5, unchanged except the image rule).** M₀ = the
start model. For k = 0, ..., N − 1: solve with M_k (per the arm's start
rule); residual at the image gains; flat-gain facet images with weights
`w_I`; Högbom (gain 0.1, at most 5,000 components, stop max(5σ, 1 mJy),
σ the MAD rms of the d1-d3 interiors, peaks in the d1-d3 interiors minus
DD4's 5 × 5 pin boxes); M_{k+1} = M_k + components. d0 is not cleaned.
Then the scored point with M_N.

**Image rule U (frozen; DD10's ALu rule, now frozen).** A gain is
untrusted if flagged or if either hand's amplitude lies outside [1/3, 3];
untrusted gains are set to 1 in the residual and in the facet images, and
no row is dropped. The untrusted share per facet per cycle is reported. In
d3 at A0 it is 76 %, so U's first d3 images are close to unit-gain images
there; this is reported as a caveat, it is not the excluded unit-gain
deep clean (the model is built only from residual images of the loop).

**N = 6 cycles for every arm** (cycles 0-5, the scored point on M₆).
N is fixed; no stop rule uses the truth.

**Minor cycle (infrastructure, gated).** A faster implementation of DD3's
Högbom with the same arithmetic: the residual is kept only on the search
pixels (the only pixels the peak search reads), and each component
subtracts the PSF there by a flat index gather. The peak is the first
maximum in the same row-major order, and each subtraction is the same
`r − f·b` per pixel, so the components should be bitwise equal.
- **Gate F (frozen):** on DD10's ALu `cycle-0/residual.npy` and
  `cycle-1/residual.npy` (float32, read as float64; both implementations
  get the same input; DD10's archived components are not the reference,
  because DD10 cleaned the float64 image), with O's PSF and masks: the
  same component pixels, fluxes bitwise equal, the same σ and stop. Pass:
  the fast Högbom is used everywhere. Fail: DD3's Högbom is used everywhere
  (at about 400 s per cycle), and the miss is reported.
- GeMClean's or another minor cycle with different arithmetic would be an
  arm of its own; none is run.

## 4. Arms

All arms start from M₀ᶜ (O) and use rule U unless stated.

| Arm | Cycles 0-1 (the start) | Cycles 2-5 | Eligible as best |
| --- | --- | --- | --- |
| **U6** | Gauss-Seidel `ap`, 4 × 8 s (as ALu) | the same | yes |
| **P6** | Jacobi phase-only (`calmode="p"`, `phase_last_direction_gain=False`, cap 500, d0 free, refant None) | GS `ap` | yes |
| **Q6** | GS `ap`; images with g/\|g\| (amplitude 1, phase kept) for trusted gains | GS `ap` | yes |
| **L6** | GS `ap` at 16 × 8 s (gains mapped to rows by their 16-integration block) | GS `ap`, 4 × 8 s | yes |
| **AT6** | O's truth gains in the images, no solve in the cycles | the same | no (control) |
| **ATm** | 3 cycles: truth gains, rows weighted as AL's cycle k (AL's trusted-row mask from DD10's AL cycle-k gains), the full-weight PSF as in AL | - | no (control) |
| **ATs** | 3 cycles: GS `ap` solve each cycle; trusted gains as solved, untrusted gains replaced by the truth gain; all rows | - | no (control) |

- Gauss-Seidel is `ap` only (DD10), so a phase-only solve is the Jacobi
  `phase` term, which DD9 did not test with four facets; its convergence is
  reported. P6 removes amplitude freedom from the solve, Q6 only from the
  images.
- U6 cycles 0-2 and the cycle-3 solve are DD10's ALu (reused); AT6 cycles
  0-2 are DD10's AT (reused). Q6's cycle-0 solve is A0 (reused).
- ATm and ATs have 3 cycles, matching AT, AL and ALu, which they are read
  against.
- ATm reproduces AL's weight loss together with its PSF mismatch (AL's
  images used masked weights, its Högbom the full-weight PSF); it does not
  separate the two.

## 5. Diagnostic D (zero solves, reported only)

On the saved gains of A0, ALu's final (M₃) solve, AT's final solve and AX,
per facet d1-d3, on unflagged cells (pairs and hands, DD5's products
against the truth): e_d; the phase-only e_d; the amplitude error, median
| |P|/|P̄| − 1 |; and the signed amplitude bias, median of |P|/|P̄| − 1. It
shows whether the absorbed gap sits in amplitude or phase. It steers no
arm: every arm in section 4 runs whatever D shows.

## 6. Scores and frozen readings

For every scored point: e_d (all unflagged cells) in d1-d3, with
- `G_d = (e_A0,d − e_d) / (e_A0,d − e_AX,d)`, the share of the gap to the
  exact sky (DEEP in d1-d3) closed (DD10's);
- `S_d = (e_A0,d − e_d) / (e_A0,d − e_AT,d)`, the share of DD10's
  truth-gain control's gain; and the same against AT6.
- Also: e on converged cells, e/ê, per-direction fractions, d3 |g| p99,
  max and cells > 10, model Σ|M − sky O| and net flux per facet, components
  and stop per cycle, untrusted shares per cycle.

**Per-arm reading (DD10's rule, unchanged):**
- harm: e_d > 1.2 e_A0,d in d2 or d3;
- **closes:** G_d1 ≥ 0.5 and no harm; **partly:** 0.2 ≤ G_d1 < 0.5 and no
  harm; **moves the error:** G_d1 ≥ 0.2 with harm; **no:** G_d1 < 0.2.

**Start effect, P6, Q6, L6 against U6 (frozen):**
- **helps:** e_d1 ≤ 0.9 e_U6,d1, and e_d2, e_d3 ≤ 1.2 × U6's;
- **hurts:** e_d1 ≥ 1.1 e_U6,d1, or e_d2 or e_d3 > 1.2 × U6's;
- else **no effect**.

**More cycles (U6 against ALu at 3 cycles):** **help** if e_U6,d1 ≤
0.9 × 0.305 without harm; else **do not help**. AT6 against AT is reported
beside it (the control's own gain from more cycles).

**Confounds (frozen):**
- **Weight loss, ATm against AT:** G_ATm,d1 ≥ 0.5: **weight loss alone does
  not stop the loop** (AL's failure then needs absorption); G_ATm,d1 < 0.2:
  **weight loss alone stops it** (AL's failure is not evidence of
  absorption); else **both contribute**.
- **Absorption, ATs against AT:** S_ATs,d1 ≥ 0.8: **the trusted solved gains
  do not absorb the gap** (DD10's failure is in the untrusted gains or the
  weight); S_ATs,d1 < 0.5: **the trusted solved gains absorb the gap**;
  else **partly**. ATs against ALu (truth against 1 for the untrusted
  gains) is reported beside it.

**DD11's answer (frozen):**

| Condition | Reading |
| --- | --- |
| some start arm (P6, Q6, L6) closes | **yes: start X keeps the gains from absorbing the gap, and the loop from solved gains closes on O** |
| no start arm closes, U6 closes | **more cycles close the loop; the start is not needed** |
| none closes; the best eligible arm reads partly | **partly: the best start closes G_d1 of the gap, not half** |
| every eligible arm reads no or moves | **no: no start tested keeps the gains from absorbing the gap** |

**Best arm (frozen choice):** among U6, P6, Q6, L6 without harm, the lowest
e_d1; within 0.005 of each other, the lower mean of e_d2 and e_d3. If every
eligible arm has harm, the lowest e_d1 regardless, labelled "with harm".
Controls cannot be chosen.

## 7. One real reading

The best arm's loop on DD7's real subset with the 145 bad baselines flagged
(setup gate 65,250 rows), from RM, N = 6, its start rule, rule U, the
real-data PSF. R0 = RM with the scored-point solver: DD10's RL cycle-0
solve, reused if the best arm's cycle-0 solve is GS `ap` 4 × 8 s (U6, Q6);
for P6 or L6 R0 is still that solve, and the arm's own cycle 0 is solved.

**Rule (DD10's section 6, verbatim), convergence only:**
- **lifts:** min over d1-d3 of RX's per-direction fraction ≥ R0's + 0.20;
  else **no lift**;
- **tames d3:** RX's d3 |g| p99 ≤ 3 and maximum ≤ 10;
- **supported by O** only if the best arm reads closes or partly on O;
  otherwise **O does not support reading it as better gains**.

Convergence alone is not evidence of better gains: on O, AL converged
(min 0.922) while d1's truth error rose. The reading is framed against
DD10's RL (the frozen row-drop rule, 3 cycles: min 0.914, d3 max 11.6),
reported beside it: fractions per cycle, components per cycle, residual rms
over the d1-d3 interiors against the thermal σ of the weight used, the
untrusted share per facet.

## 8. What the outcomes mean for the DD plan

| Outcome | Next DD step |
| --- | --- |
| yes (start X closes) and real lifts, supported | carry start X and rule U into the real DD recipe (145 flagged); image-domain checks on real data next |
| yes, real no lift | the real data need more than the model loop (DD7's other properties); combined insertion into O |
| more cycles close | the loop with rule U and N cycles; the cycle count, not the start, is the knob |
| partly | the start is the right lever but not enough: a better deconvolver in the loop (multi-scale, per facet) on O, keeping the best start |
| no | the bootstrap is not the lever at this depth; a better deconvolver or a deeper d1 model from another route, on O |
| ATm: weight loss alone stops it | DD10's AL reading does not show absorption; drop row-drop rules for good |
| ATs: trusted gains absorb | the start must constrain the solve, not only the images |

## 9. Implementation, host and cost

- `tools/oracles/dd11/dd11.py`: `hogbom_fast`, `gatef`, `diag`, `reuse`,
  `loop` (U6, P6, Q6, L6, AT6, ATm, ATs, and the real arm), `score`. It
  imports DD10's `dd10.py` for `base_ctx`, `solve`, `scores`, the images and
  the PSF; no solver or library code changes. `tests/test_dd11.py`: the fast
  Högbom against DD3's on a small synthetic image (bitwise).
- Python: the main checkout's venv (its extension has DD10's Gauss-Seidel
  option; DD11 changes no Rust).
- glacier, shared, under the main checkout's `tools/heavy_lock.py`: a loop
  with solves 8 slots and 20 GB (DD10's figure); the truth-gain loops
  without inner solves 4 slots and 16 GB, 8 slots for their final solve
  (run as one job at 8 slots, 20 GB); gate F 1 slot, 6 GB; O rebuild 2 slots,
  10 GB. At most two solve jobs at once. No exclusive or timing runs.
- **Run cap (Rust solves, second solves counted):** U6 4 (cycles 4, 5,
  scored 2); P6 8; Q6 7; L6 8; AT6 2; ATm 2; ATs 4; real 8. 43, plus one
  spare per class (O arms, controls, real): 46. Gate F: two Högbom pairs.
- Expected: a GS solve 600-740 s at 8 slots, a facet image set 22-45 s,
  the fast Högbom under 100 s per cycle (DD3's 400 s), a Jacobi phase solve
  under half a GS solve. About 30,000 s of jobs, about 5 h at two at once.
- Wall times go into [tool-timings.md](tool-timings.md). The rebuilt O MS
  and the PSF arrays are deleted at the end; records stay in the run root,
  a compact archive in `results/dd11-start/`. D: stays above 150 GB free.

## 10. Measured result

(not yet measured)

## 11. For the coordinator

(after the measurement)

## Amendments

(none)
