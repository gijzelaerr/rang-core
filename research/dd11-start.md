# DD11: a start that keeps the solved gains from absorbing the off-axis model gap, on O

Issue #15. Follows [dd10-gs.md](dd10-gs.md) (DD10),
[dd9-solver.md](dd9-solver.md) (DD9) and [dd8-offaxis.md](dd8-offaxis.md)
(DD8). Branch `dd11-start`. Coordinator brief 2026-11-26. Sections 1-9 are
frozen 2026-11-26, before the code that runs them and before any
measurement. Later changes are dated amendments, committed before the
reading they affect.

Status: **measured 2026-11-26.**
- **On O (frozen): partly.** The best start, Q6 (unit-amplitude gains in
  the first two cycles' images), brings d1's truth error from 0.352 to
  0.244 (G_d1 0.31) without harm; the same loop without it reaches 0.273
  (U6), the truth-gain control 0.128 (AT6). L6 (16 × 8 s) has no effect;
  P6 (Jacobi phase-only) hurts, because that solver does not converge with
  four facets.
- **Confounds:** the trusted solved gains absorb the gap (ATs); DD10's
  row-drop weight loss alone wrecks even a truth-gain loop (ATm).
- **Real (frozen):** Q6's loop lifts (min d1-d3 0.080 to 0.961) and tames
  d3 (max 3.8); convergence, not accuracy.

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

Run root `D:/rang/outputs/dd11-20261126/`. Host glacier, shared, under the
main checkout's `heavy_lock.py`; every loop 8 slots, 20 GB booked (about
11.5 GB resident).

**Setup.** O rebuilt (239 s): GO passes, every `build.json` number equals
DD10's, `sky.npy` has DD8's SHA-256 (`setup-gate.json`). PSF peaks equal
DD10's. Reused files and their SHA-256 are in `reuse.json`. AT6's extra
cycle-3 solve (A1) reproduces DD10's AT final solve bitwise.

**Gate F: pass.** On DD10's ALu cycle-0 and cycle-1 residuals the fast
Högbom gives the same 1,203 and 1,489 components in the same order, fluxes
bitwise equal, the same σ and stop (`gatef.json`). It is only 1.4-1.7 ×
faster (262 s and 251 s against 357 s and 424 s, one core, busy host): the
flat gather over most of the image costs about what the slice did. In the
loops a Högbom cycle took 200-310 s.

**Diagnostic D (zero solves; `diag.json`).** Per facet d1, d2, d3, on
unflagged cells against the truth products:

| Gains | e | phase-only e | median \|amp ratio − 1\| | median amp bias |
| --- | --- | --- | --- | --- |
| A0 (M₀ᶜ) | 0.352, 0.544, 1.000 | 0.199, 0.385, 0.903 | 0.231, 0.259, 0.933 | −0.160, −0.090, −0.675 |
| ALu final (M₃) | 0.305, 0.345, 0.536 | 0.125, 0.255, 0.258 | 0.244, 0.133, 0.367 | −0.164, −0.031, +0.056 |
| AT final (M₃) | 0.161, 0.312, 0.500 | 0.071, 0.199, 0.257 | 0.120, 0.155, 0.342 | −0.086, −0.032, −0.091 |
| AX (exact) | 0.008, 0.033, 0.052 | 0.005, 0.019, 0.030 | 0.005, 0.019, 0.030 | 0.000, 0.000, 0.000 |

In d1 the absorbed gap sits in both amplitude and phase: A0's products are
16 % low in amplitude and 0.20 rad off. ALu's three cycles fix most of d1's
phase (0.20 to 0.12 rad), not its amplitude (bias −0.16 before and after).
The truth-gain loop halves both.

### The arms on O (sections 4 and 6)

Every scored point: Rust Gauss-Seidel, 4 × 8 s, d0 free, cap 500, on the
arm's M₆ (M₃ for ATm and ATs). e on converged cells is within 0.001 of e
on all cells in every arm. References (DD10): A0 0.352, 0.544, 1.000; AX
0.0078, 0.0334, 0.0523; AT 0.161, 0.312, 0.500; ALu 0.305, 0.345, 0.536.

| Arm | e d1, d2, d3 | G d1, d2, d3 | S_AT d1 (S_AT6 d1) | e/ê d1-d3 | fractions d0-d3 | d3 \|g\| p99 / max | Reading | Against U6 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **U6** | 0.273, 0.301, 0.397 | 0.227, 0.476, 0.636 | 0.41 (0.35) | 57, 8.3, 7.1 | 0.992, 0.991, 0.991, 0.988 | 1.86 / 2.6 | **partly** | - |
| **Q6** | **0.244**, 0.301, 0.365 | **0.313**, 0.476, 0.670 | 0.56 (0.48) | 47, 8.3, 7.0 | 0.983, 0.950, 0.947, 0.948 | 1.83 / 2.5 | **partly** | **helps** (0.894 ×) |
| **L6** | 0.277, 0.301, 0.396 | 0.218, 0.476, 0.637 | 0.39 (0.34) | 57, 8.3, 7.2 | 0.994, 0.983, 0.982, 0.983 | 1.86 / 2.6 | **partly** | **no effect** (1.01 ×) |
| **P6** | 0.314, 0.391, 0.412 | 0.109, 0.300, 0.620 | 0.20 (0.17) | 55, 9.8, 7.9 | 0.978, 0.924, 0.912, 0.913 | 1.87 / 2.6 | **no** | **hurts** (1.15 ×) |
| AT6 (control) | 0.128, 0.279, 0.387 | 0.649, 0.520, 0.647 | 1.17 (1) | 22, 8.0, 7.8 | 0.994, 0.975, 0.974, 0.974 | 1.95 / 2.9 | closes | - |
| ATs (control) | 0.304, 0.344, 0.503 | 0.139, 0.392, 0.524 | 0.25 | 61, 9.6, 9.5 | 0.999, 0.989, 0.984, 0.983 | 2.27 / 3.2 | no | - |
| ATm (control) | 0.911, 1.039, 1.201 | −1.627, −0.970, −0.212 | −2.93 | 368, 40, 24 | 0.004, 0.000, 0.000, 0.000 | 5.69 / 9.7 | no (with harm) | - |

No eligible arm harms d2 or d3 (only the control ATm does). e in d1 per cycle (cycles 0-5, then the scored
point; "nc" marks a start solve whose e is not comparable, section 3):
- U6: 0.352, 0.334, 0.315, 0.305, 0.295, 0.284, **0.273**.
- Q6: 0.352, 0.304, 0.289, 0.285, 0.269, 0.254, **0.244**.
- L6: nc 0.351, nc 0.335, 0.317, 0.307, 0.298, 0.286, **0.277**.
- P6: nc 0.669, nc 0.571, 0.330, 0.317, 0.317, 0.316, **0.314**.
- AT6 (from the A1 solves): -, -, -, 0.161, 0.148, 0.137, **0.128**.
- ATs: 0.352, 0.337, 0.316, **0.304**.

Per arm:
- **Q6 (unit amplitude in the start images)** is the only start that
  helps.
  - Its first Högbom adds 0.53 Jy (U6 and AT 0.41), its second 0.29 Jy
    (U6 0.12): with amplitudes set to 1, the residual images show more of
    the missing flux.
  - Its lead over U6 holds to the scored point (d1 0.244 against 0.273, d3
    0.365 against 0.397).
  - Its solves converge less (min d1-d3 0.947 against 0.988), which does
    not change its truth error (0.244 on converged cells too).
- **L6 (16 × 8 s start)** stays within 0.004 of U6 in d1 from cycle 2 on.
  A longer interval does not stop the absorption, as DD9 found for d3.
- **P6 (Jacobi phase-only start)** fails at the start.
  - The Jacobi `phase` term converges nowhere at cap 500 with four facets
    (global fraction 0.000 in both start cycles) and flags 2,232, 560,
    3,849 and 3,733 gains in d0-d3 (cycle 0).
  - Its d1 phase-only error is 0.650 and 0.547 in the two start cycles,
    against 0.199 for A0's `ap` solve.
  - Its start images build a worse model (first Högbom −0.11 Jy), from
    which the Gauss-Seidel cycles recover only to 0.314.
  - This tests the phase-only solver available, not phase-only starts in
    general.
- **More cycles help.** U6 reaches 0.273, against ALu's 0.305 at 3 cycles
  (0.895 ×, bar 0.9).
  - d1 improves by about 0.01 per cycle; U6 reads "partly" (G_d1 0.227).
  - AT6 also improves per cycle (0.161 at 3, 0.128 at 6). The truth-gain
    control's gain from cycles 3-5 is 0.033, U6's 0.032.
- Model net flux in d1 at M₆ (truth 4.43 Jy, M₀ᶜ 2.83): U6 3.31, Q6 3.56,
  L6 3.30, P6 3.07, AT6 3.60. Σ|M − sky O| in d1 rises in every arm (33-37
  against 21.2), as in DD10 (point components on extended emission).
- Untrusted d3 gains under rule U fall to 2 % by cycle 5 in every solved
  arm, from 76 % at cycle 0 (P6: 54 %, its phase-only flags); Q6 has 39 %
  at cycle 1 (U6 21 %).

**Confounds (frozen):**
- **Absorption: "the trusted solved gains absorb the gap"** (S_ATs,d1 0.25,
  bar 0.5). With O's truth gains replacing only the untrusted gains and all
  weight kept, three cycles reach d1 0.304. ALu, with those gains set to 1,
  reaches the same 0.305, against AT's 0.161. The untrusted gains and their
  substitute do not matter; the trusted gains carry the absorbed gap.
- **Weight loss: "weight loss alone stops it"** (G_ATm,d1 −1.63, bar 0.2).
  - With O's truth gains but AL's row masks (2.1 %, 5.1 % and 26.6 % of
    the weight kept) and the full-weight PSF, the loop wrecks the model:
    d1 0.911, d2 1.039, d3 1.201, and the scored solve converges nowhere
    (min 0.000).
  - Its Högbom cycles stop at 41, 63 and 51 mJy (σ of the masked images)
    and add +1.7, −7.7 and +10.5 Jy: the deconvolution diverges with a PSF
    that does not match the images' weights.
  - AL itself, with the same masks, stayed at 0.395 because its solved
    gains had absorbed most of the gap, so its residual images held
    little to clean (stop 13 mJy, net 0.008 Jy). DD10's AL therefore did
    not isolate absorption; ATs, with all weight, shows it.

**Frozen answer: "partly: the best start (Q6) closes G_d1 0.313 of the
gap".**
- Best arm Q6 (no harm, lowest d1).
- No start closes. Q6 helps against U6, L6 has no effect, P6 hurts, and
  more cycles help.
- Both "helps" readings are narrow: Q6 is 0.894 × U6 and U6 is 0.895 ×
  ALu, against a 0.9 bar. The solves are deterministic, so a rerun gives
  the same numbers, but a slightly different rule or sky could move either
  reading.
- Q6 closes 31 % of d1's gap to the exact sky, 56 % of DD10's truth-gain
  control's gain and 48 % of AT6's.

### One real reading (section 7)

R-Q6: DD7's real subset with the 145 bad baselines flagged (65,250 rows),
RM, Q6's start (unit-amplitude images in cycles 0-1), rule U, six cycles,
then the scored point. R0 is DD10's RL cycle-0 solve, reused.

| Point | fractions d0-d3 | d3 \|g\| p99 / max (cells > 10) | flagged d0-d3 | residual rms d1-d3 / thermal σ | weight in images |
| --- | --- | --- | --- | --- | --- |
| R0 (RM) | 0.231, 0.137, 0.124, **0.080** | 10.8 / 33 (169) | 113, 113, 117, 249 | 1.48 / 0.092 mJy (16.1 ×), DD10's row drop | 11.9 % |
| DD10 RL (row drop, 3 cycles) | 0.970, 0.937, 0.922, **0.914** | 2.34 / 11.6 (2) | 113, 116, 114, 119 | 0.61 / 0.045 mJy (13.7 ×) | 50.3 % |
| **R-Q6** | 0.999, 0.988, 0.970, **0.961** | 1.83 / **3.8** (0) | 113, 113, 114, 116 | 0.31 / 0.032 mJy (9.7 ×) | 100 % (rule U) |

- **Frozen reading: lifts** (min d1-d3 0.080 to 0.961, bar 0.280); **tames
  d3** (p99 1.83 ≤ 3, max 3.8 ≤ 10); **supported by O** in the frozen
  rule's sense (Q6 reads "partly" on O).
- **What the real run compares.** R-Q6 differs from DD10's RL in three
  ways at once: rule U instead of the row drop, six cycles instead of
  three, and the unit-amplitude start. No real U6 was run, so the lift
  over RL and the tamer d3 cannot be credited to the start.
- **Convergence alone is not evidence.**
  - On O every solved arm converged (min d1-d3 0.91-0.99), while d1's
    truth error stayed at 0.24-0.31, 47-57 × the noise prediction.
  - DD10's AL converged while d1 got worse.
  - On O, Q6 closes 31 % of d1's gap. The real run says only that the same
    loop converges and stays tame there, not how accurate its gains are.
- Cycles (Högbom components and stop): 1,032 (3.2 mJy), 1,282 (2.4), 1,218
  (2.2), 2,119 (2.1), 2,849 (1.9), 3,139 (1.7).
  - Global fraction 0.143, 0.661, 0.791, 0.853, 0.931, 0.985, 0.979.
  - Untrusted d3 gains 55 %, 18 %, 9.1 %, 6.7 %, 3.6 %, 2.6 %, 2.0 %.
- The residual rms over the d1-d3 interiors falls from 0.64 mJy (cycle 0)
  to 0.31 mJy, 9.7 × the thermal σ of all the weight. RL's 13.7 × is
  against the thermal σ of its kept 50 %. On O a model the gains can fit
  also lowers the residual, so this is not an accuracy claim.

**Cost.** Loop walls (8 slots booked; lock waits included):

| Loop | Wall |
| --- | --- |
| U6 (three new cycles) | 2,989 s |
| Q6 | 6,433 s |
| P6 | 11,330 s |
| L6 | 9,446 s |
| AT6 | 6,508 s |
| ATs | 8,440 s |
| R-Q6 | 9,579 s |
| ATm | 2,189 s |

- Per step: a Gauss-Seidel solve took 690-810 s at 8 slots on a busy host
  (16 × 8 s: 803-809 s), a Jacobi phase solve 593-595 s, a facet image set
  32-58 s, a Högbom cycle 200-310 s (one core).
- Solves: U6 4, Q6 7, P6 8, L6 8, AT6 2 + 3 (A1), ATm 2 + 1 (A1), ATs 4,
  R-Q6 7. That is 46, the run cap with its spares; no solve failed.

## 11. For the coordinator

- **Frozen answer: partly.**
  - The best start is **Q6**: Gauss-Seidel `ap` solves, gains set to unit
    amplitude (phase kept) in the first two cycles' images, untrusted gains
    set to 1 (rule U), six cycles.
  - It brings d1's truth error from 0.352 to **0.244** (G_d1 0.31; 56 % of
    DD10's truth-gain control's gain, 48 % of AT6's) without harm, against
    0.273 for the same loop without the start (U6) and 0.128 for the
    truth-gain control at six cycles (AT6).
  - No start closes half of d1's gap.
  - The margin is narrow: Q6 is 0.894 × U6 (bar 0.9), and more cycles are
    0.895 × ALu (bar 0.9). Keeping Q6's start rests on a 1 % margin.
- **Per arm, against the frozen table:**
  - U6 partly (0.273; more cycles help: 0.895 × ALu's 3-cycle 0.305).
  - Q6 partly, helps (0.894 × U6).
  - L6 partly, no effect (16 × 8 s does not stop absorption).
  - P6 no, hurts: the Jacobi `phase` term does not converge with four
    facets (fraction 0.000), so the phase-only start is untestable with the
    solver available.
- **Confounds:**
  - ATs: the trusted solved gains absorb the gap (truth in place of the
    untrusted gains gives 0.304, the same as ALu's 0.305).
  - ATm: AL's weight loss alone, with the full-weight PSF, wrecks even a
    truth-gain loop (d1 0.911). So DD10's "the solved gains absorb the
    gap" reading came from a confounded arm; ATs now shows it directly.
  - Diagnostic D: d1's absorbed gap is 16 % in amplitude and 0.2 rad in
    phase. Rule U's cycles fix the phase, not the amplitude, which is why a
    unit-amplitude start helps.
- **Real (frozen): lifts and tames d3; "supported by O" only in the frozen
  rule's sense.**
  - Min d1-d3 0.080 to 0.961; d3 |g| max 3.8 against DD10's RL 11.6.
  - The residual is 9.7 × thermal against RL's 13.7 ×.
  - R-Q6 changes the image rule, the cycle count and the start together
    against RL; none of the difference is attributable to the start alone.
  - This is convergence, not accuracy. On O the same loop leaves d1 at
    47 × the noise prediction.
- **Recommended next step (section 8, row "partly"):** DD12 on O, frozen
  before code, keeping Q6's start and rule U. The deconvolver is the
  remaining lever: point-component Högbom adds pixel error on extended d1
  emission (Σ|M − sky| 21 to 34) and d1 gains about 0.01 per cycle.
  - Arms: a multi-scale or per-facet clean in the loop, using an existing
    minor cycle (GeMClean's multi-scale) rather than a new one.
  - Also a longer run of the Q6 loop (12 cycles) as the cycles-only
    reference, scored against AT at the same N.
  - The unit-amplitude rule could also be tried for more than two cycles.
- **Not adopted:** the unit-gain deep clean, merging d3, the robust
  held-out score.
- **Infrastructure:** the fast Högbom is bitwise equal but only 1.5 ×
  faster in NumPy. A real speed-up needs compiled code: exposing
  `core/src/clean.rs::hogbom` with a search mask would be a small binding.
- **Checks:** `python tools/check_all.py --quick` PASS (1,157 s, from the worktree's own .venv). CI on the
  branch: CI_RESULT. No Rust or library change, so the oracle gates are
  unchanged; the full check is left to the coordinator's merge check.
- **Disk:** the rebuilt O MS and the PSF arrays are deleted. The run root
  keeps 4.1 GB (models, residual images, gains, records). Archive:
  `results/dd11-start/`.
- **Procedure:** ATm ran from the worktree's `python/` with a copy of
  main's `_core.pyd`; the other loops used the main venv, which locked main's
  `_core.pyd` during the coordinator's merge check (DD11 only, now stopped).

## Amendments

**A1, 2026-11-26, a record of two procedure deviations (after the U6, Q6,
L6, P6, AT6 and R-Q6 readings; before any ATm or ATs record was read). It
changes no frozen rule or reading.**
- **Unneeded solves in the truth-gain controls.** The code applied the start
  rule to cycles 0-1 only, so AT6's cycles 3-5 and ATm's cycle 2 also ran a
  Gauss-Seidel solve (3 + 1 solves over the run cap). Their images used O's
  truth gains as frozen, so their models are unaffected; the solves are
  reported only. One use: AT6's cycle-3 solve on DD10's AT M₃ gives gains
  and flags **bitwise equal** to DD10's AT final solve (e d1 0.16078 in
  both), which confirms section 2's reuse of DD10's solves.
- **R-Q6 started early.** The real reading of Q6 was queued at 12:11, when
  U6, Q6 and P6 were near their ends and L6 was at cycle 4, to use the
  queue. The frozen best-arm choice, made after L6's scored point, picked Q6,
  so R-Q6 is the section-7 run; had it picked another arm, that arm's real
  run would have followed and R-Q6 would have been reported only.

**A2, 2026-11-26, a correction to A1 (after every reading; it changes no
reading).** A1 says R-Q6 was queued when U6, Q6 and P6 were "near their
ends". At 12:11 U6 and Q6 had finished and their scored d1 (0.273 and
0.244) had been read; P6 was at its final solve and L6 at cycle 4. So the
early queue was chosen with knowledge of O's results for two of the four
eligible arms. The frozen best-arm rule, applied after L6 and P6 were
scored, gives Q6 as well.
