# DD15: releasing the pins only where the nominal beam is high

Issue #15. Follows [dd14-flux-scale.md](dd14-flux-scale.md) (DD14) and
[dd13-absorb.md](dd13-absorb.md) (DD13). Branch `dd15-beam-gate`.
Coordinator brief 2026-11-28. Sections 1-9 are frozen 2026-11-28, before
the code that runs them, before OB is rebuilt and before any measurement or
real-data read. Later changes are dated amendments, committed before the
reading they affect, and labelled post hoc where they follow a reading.

Status: **measured 2026-11-28.**
- **Frozen answer: "out: the pinned rule stays in the recipe".** Rows
  [2, 0]: QPG12 reads "in for d1-d2" at M₆ and "out" at M₁₂, so section 7's
  real check does not run.
- **d3 decides it again, now as a loss.** Kept pinned, d3's pin aperture
  falls: κ^pin_3 is −0.350 at M₆ and −0.411 at M₁₂. The allowance,
  |κ^pin_3(Q12)| + 0.05, is 0.386 and 0.328.
- **d1 and d2 pass everything at both N.** e^sr_d1 is 0.150 and 0.139
  (0.42 × and 0.39 × Q's); s is 0.995/0.979 and 0.997/0.978; κ^pin is
  −0.024/−0.016 and −0.026/−0.011.

## 1. Question

DD14's frozen answer on OB (O with a realistic MeerKAT L-band beam in the
truth gains; B_nom 0.918, 0.813, 0.361 in d1-d3) was **out**: no arm met
its gain and flux criteria at 12 cycles, because no arm calibrates d3, the
truth controls included. Post hoc (DD14 A3):
- with the nominal beam in the image gains and the pins released (QPN12),
  the d1 and d2 facet scale holds within 1-3 % (gain scale s 0.994, 0.983)
  and d1 keeps the gain win (e^sr 0.141 against Q12's 0.356);
- QPN12's released d3 pin grows a 3 × excess (pin aperture 0.262 Jy at
  M₁₂ against the sky's 0.088 Jy);
- DD14's flux metric φ mixes deconvolution completeness with scale.

**DD15's question.** Does a rule that releases the pins (with the nominal
beam in the image gains) only in facets where the nominal beam is high, and
keeps the pinned rule elsewhere, keep QPN12's d1-d2 gain win and flux scale
without QPN12's d3 excess?

No novelty is claimed. Beam-weighted sky models and per-direction flux
anchoring are standard DD practice (DD14 section 7). DD15 is a recipe and
safety step for rang's own DD loop.

## 2. The gate and the threshold (frozen)

- **Rule.** A facet f is **high** if B_nom,f ≥ 0.5 and **low** otherwise.
  B_nom,f is DD14's nominal beam at the facet centre (the circular Mauch
  beam, catalogue.py's ρ; DD14 section 2 and A1). On this field d1 and d2
  are high, d3 is low.
- **Why 0.5.** It is the nominal beam's half-power point, the usual edge of
  the primary beam. Below it:
  - the apparent signal is under half the intrinsic one, so the facet's
    solve has under half the signal-to-noise. On OB, AX's d3 error rises
    from 0.052 on O to 0.145 (DD14);
  - the true beam's departure from the nominal one grows as a fraction.
    On OB the p5-p95 spread of B_true/B_nom per antenna and block is
    ±1 % in d1 and −3 % to +4 % in d3 (DD14 `beam.json`);
  - DD14's one released low facet, d3, grew a spurious compact excess
    while d1 and d2 held.
- **Scope limit.** OB partitions the facets the same way for any threshold
  in (0.361, 0.813]. DD15 therefore tests the partition {d1, d2 high; d3
  low}, not the value 0.5. No other threshold is run.

## 3. Data, reuse and gates

DD7's, DD8's and DD11-DD14's roots are read only. DD15's root is
`D:/rang/outputs/dd15-20261128/`. Every reused file is copied into DD15's
root with its SHA-256 in `reuse.json`, never changed there.

**Rebuild.** DD14 deleted OB's MS, `gate/O` and the PSF array. DD15
rebuilds them with DD14's code, unchanged (`tools/oracles/dd14/dd14.py`
`beam`, `gateo`, `insert`, `psf`), into DD15's root. `gate/O` (DD8's O) is
kept until the O-twin arm (section 4) has run.

**Gate GB15 (build, blocking).**
1. DD14's GB 1-4 pass in DD15's root, with DD14's tolerances.
2. `beam.npz`: every array equals DD14's kept `beam.npz` bitwise.
3. OB's `truth.npz` gains equal DD14's kept `O/truth.npz` bitwise, and
   `sky.npy` has DD14's SHA-256.

**Gate R15 (reproduction against DD14 and DD13, blocking).** DD15's loop
code, one image and one Högbom each, no solve:
- **(a)** On OB with the gate degenerate (threshold 0, so every facet is
  high and DD15's rule is QN everywhere): from DD14's QPN12 cycle-11 gains
  and M₁₁ (`QPN12/cycle-10/next_model.npy`), DD14's QPN12 M₁₂
  (`cycle-11/next_model.npy`) bitwise. This one check covers the rebuilt
  DATA and PSF, this worktree's extension, the QN rule and the released
  Högbom.
- **(b)** On OB with threshold 0.5: from DD14's QPN12 cycle-1 gains and M₁,
  DD14's QPN12 M₂ bitwise. It shows that QPG12's cycles 0-1 are QPN12's
  (section 4).
- **(c)** On `gate/O` with threshold 0.5 and unit amplitudes: from DD13's
  QP12 cycle-1 gains and M₁, DD13's QP12 M₂ bitwise. It shows that
  QPG12-O's cycles 0-1 are DD13's QP12's.
- **(d)** Before the real arm, and only if it runs (section 7): on the real
  subset with the real form of the rule, from DD13's R-QP12 cycle-1 gains
  and M₁, DD13's R-QP12 M₂ bitwise. The real PSF is rebuilt first
  (`dd10.psf`), with its peak equal to DD13's `psf-real.json` to 1e-9
  relative.
- Also unit-tested: the gated rule with every facet high is QN bitwise;
  with every facet low it is section 4's low-facet rule; the gated search
  mask is the released mask with all facets high and the pinned mask with
  all low.
- Fail: no loop runs and the miss is reported.

**PSF of the O twin.** The PSF depends only on UVW, weights and flags,
which O and OB share (DD14 GB 4: equal peaks), so the O twin uses OB's PSF.

## 4. Arms

Cycle, Högbom, rule U (trusted amplitudes in [1/3, 3]), scored solve
(Rust Gauss-Seidel `ap`, 4 × 8 s, all baselines, d0 free, cap 500, plus the
one-longer solve) and scored points M₆ and M₁₂ are DD13's and DD14's,
unchanged.

**The gated rule QG (frozen).** Per facet, for trusted cells:

| Facet | Cycles 0-1 image gains | From cycle 2 image gains | Untrusted cells | Pin box |
| --- | --- | --- | --- | --- |
| high (d1, d2) | √B_nom,f · g/\|g\| | √B_nom,f · g/\|g\| | √B_nom,f | excluded in cycles 0-1, released from cycle 2 |
| low (d3) | √B_nom,f · g/\|g\| | g | √B_nom,f | excluded in every cycle |
| d0 | 1 · g/\|g\| | 1 · g/\|g\| | 1 | not cleaned |

- **Why this low-facet rule.** It is the pinned recipe (DD11's Q rule:
  unit amplitude in cycles 0-1, the solved gains after, untrusted → 1,
  pins kept) mapped onto OB's units by DD14 section 2: on real data the
  catalogue model already holds B_nom, so on OB the unit amplitude becomes
  √B_nom,f. With the pin kept, the pin's catalogue flux sets the facet's
  scale, and the solved amplitudes carry the beam. Unit amplitude with a
  kept pin (DD13's QA12) is not used: it harmed d3 on O.
- **The real form** (real data, the O twin): B_nom,f ≡ 1 in the amplitudes,
  the partition unchanged (it is the field's geometry). In d1-d2 this is
  QP12's rule, in d3 Q12's rule.
- DD14's Q12 on OB used unit amplitude in cycles 0-1 (no √B_nom). It stays
  DD14's reference as run; it is not the mapped pinned recipe in cycles
  0-1.

| Arm | Data | Image gains | Clean mask | Prefix reused | Role |
| --- | --- | --- | --- | --- | --- |
| **QPG12** | OB | QG | QG's | DD14 QPN12 cycles 0-1 and the cycle-2 solve (R15 b) | the arm |
| **ATG12** | OB | OB's truth | QG's | DD14 AT12 cycles 0-1 | matched truth control |
| **QPG12-O** | O (`gate/O`) | QG, real form | QG's | DD13 QP12 cycles 0-1 and the cycle-2 solve (R15 c) | O twin: κ's reference (section 5) |
| **R-QPG12** | real subset | QG, real form | QG's | DD13 R-QP12 cycles 0-1 and the cycle-2 solve (R15 d) | section 7, only if called |
| Q12 | OB | DD14's | DD14's | DD14's kept records, zero solves | reference |
| QPN12 | OB | DD14's | DD14's | DD14's kept records, zero solves | reference |
| AT12, ATP12, AX, A0 | OB | DD14's | DD14's | DD14's kept records, zero solves | truth controls and references |

- **Why ATG12.** Högbom cleans d1-d3 in one residual image with one stop
  threshold, and the solve is joint, so neither AT12 (all pinned) nor ATP12
  (all released) is QPG12's matched control.
- **Why QPG12-O.** DD14 found that the pin aperture against the same arm on
  O (κ_pin) is the clean scale measure: it cancels each rule's own
  completeness and pin bias. For the gated rule no O run exists, so DD15
  runs one. QPG12-O is scored at M₆ and M₁₂ like the other loop arms;
  its e_d is reported, not read.
- **Stage stop (frozen, QPG12 only).** After M₆, QPG12 stops if section 6's
  answer at N = 6 cannot be "in" or "in for d1-d2" (the rows of section 6
  read at M₆). It waits for ATG12's and QPG12-O's M₆ first. The controls,
  the O twin and the references never stop. A stopped QPG12 is read "out".

## 5. Metrics

At M₆ and M₁₂, for QPG12, ATG12, QPG12-O and re-scored from DD14's kept
records for Q12, QPN12, AT12 and ATP12:
- **DD14's set,** unchanged: e_d (raw), s_d, e^sr_d, G^sr, the per-arm
  reading, untrusted shares, Högbom components per cycle, diagnostic D,
  and φ (all and non-pin apertures, against DD14's references). **φ is
  reported only** and decides nothing.
- **Gain scale s_f** (DD14 section 4; truth = 1) in d1 and d2. s_d3 is
  reported, not read: on OB no loop calibrates d3 (truth controls s_d3
  0.31-0.39), so s_d3 measures the failed solve, not the scale.
- **Pin-aperture response** `κ^pin_f(X) = F^pin_f(M_X on OB) /
  F^pin_f(M_X' on O) − 1` at the same N, with DD14's frozen pin apertures
  (`apertures.json`, the 16 px disc that holds the pin pixel). X' is X's O
  twin: QPG12-O for QPG12; DD14's O references for the others (Q12 → DD12's
  Q12; QPN12 → DD13's QP12; AT12 → DD12's AT12; ATP12 → DD13's ATP12).
  ATG12 has no O twin, so for it the pin aperture against sky O,
  `F^pin_f(M) / F^pin_f(sky O) − 1`, and against ATP12 and AT12 on OB, are
  reported only.
- **Readability (DD14's, on the pin aperture):** a facet is readable if
  ATG12's pin aperture holds more than 0.2 of sky O's.

## 6. Readings (frozen)

**Criterion G (gains) at N.** Both:
1. the per-arm reading on e^sr (DD14 section 5, with A0 and AX on OB,
   unchanged) is "closes" or "partly";
2. **helps against Q12 at N**, with **a d3 clause changed from DD14 after
   DD14's outcome:**
   - d1: e^sr_d1 ≤ 0.9 × Q's (helps; within 0.02 of the bar is marginal,
     and marginal counts);
   - d2: e^sr_d2 ≤ 1.2 × Q's (DD12's clause, unchanged);
   - **d3, a low facet (changed):** raw e_d3 ≤ 1.2 × max(raw e_d3 of Q at
     N, raw e_d3 of the matched truth control at N). The matched control is
     ATG12 for QPG12, ATP12 for QPN12 and AT12 for Q12.
   - **Why it changed.** On OB no loop calibrates d3: AX with the exact sky
     reaches 0.145, every loop and truth control 0.89 or more (raw), so
     d3's gain accuracy is out of scope. The clause keeps only a non-harm
     guard against both the recipe and the truth gains. It reads raw e,
     not e^sr: where the solve fails, s is far from 1 and dividing by it
     amplifies the error (DD14 A3); in a pinned facet the pin holds the
     scale, so raw e is the whole error.

**Criterion F (flux scale) at N.**
- **d1 and d2:** |s_f − 1| ≤ 0.05 and |κ^pin_f| ≤ 0.05.
- **d3:** |κ^pin_3| ≤ 0.05. This is the excess guard: the kept pin masks
  only the 5 × 5 box, so excess can still grow in the 16 px disc around
  it.
- **Tolerance:** 0.05, as in DD14 (about RACS's own flux-scale
  uncertainty). A facet that is not readable fails.

**Checked on already-read OB numbers (DD14's `score.json`, before this
freeze).** The truth controls pass every clause above:
- κ^pin, d1-d3: AT6 −0.002, −0.001, +0.020; AT12 +0.012, −0.022, 0.000;
  ATP6 −0.004, −0.010, +0.010; ATP12 −0.004, −0.013, +0.007.
- s in d1 and d2: ATP12 0.980 and 1.031. AT12's is 0.952 and 0.990.
  AT6's d1 s is 0.943, outside the bar, but AT6 is not a matched control
  for any arm read here.
- The d3 clause: AT12 and ATP12 pass by construction (ratio ≤ 1).

The same numbers give the expected readings of the references:
- QPN12 passes G at 12 under the new clause (raw e_d3 1.136 against
  1.2 × max(1.318, 1.001)). It fails F on d3: κ^pin_3 is +1.47.
- Q12, the pinned rule as DD14 ran it, fails F: κ^pin d1 −0.128, d3 −0.278.
- These are recorded as expectations. The references cannot change the
  answer.

**Both N.** QPN6 met DD14's criteria and QPN12 did not, so every criterion
is read at M₆ and at M₁₂, and the answer needs both.

**DD15's answer (frozen), read on QPG12:**

| Condition, at both M₆ and M₁₂ | Reading |
| --- | --- |
| QPG12 meets G and F | **in: the beam-gated rule (pins released with the nominal beam in the image gains where B_nom ≥ 0.5, pinned below) goes into the real DD recipe, subject to section 7's real check** |
| QPG12 meets G and F's d1-d2 terms. It fails F's d3 term, but \|κ^pin_3(QPG12)\| ≤ \|κ^pin_3(Q)\| + 0.05 | **in for d1-d2, d3 a known limitation: the gate holds the high facets, and d3 moves no more than the pinned rule moves it; subject to section 7 for d1-d2** |
| otherwise (a stopped QPG12 included) | **out: the pinned rule stays in the recipe**, with the criteria and facets that failed |

- **Stop rules.**
  - No other threshold, seed, tolerance or arm is run on OB.
  - A failed gate stops everything before any loop.
  - "out" ends DD15: section 7 does not run.
  - The solve cap (section 9) is not exceeded; a crash is resumed from the
    last kept cycle, not rerun.
- **What each reading recommends for #15's convention question.**
  - **in, real check passes:** close it with the beam in the model, pins
    released where B_nom ≥ 0.5 and pinned below.
  - **out:** close it with the beam in the model required and the pins
    kept. Stating that is the coordinator's or the owner's choice.

## 7. Real-data check (frozen before any real data is read)

Runs only on an "in" or "in for d1-d2" reading.
- **Data.** DD7's real subset (ESO 137-006), the field DD11-DD14 used, with
  the 145 bad baselines flagged (setup gate 65,250 rows).
- **The arm.** R-QPG12: QG's real form from RM, 12 cycles, then the scored
  point (DD13 section 7's loop and records). Cycles 0-1 and the cycle-2
  solve are DD13's R-QP12's (gate R15 d). R0 is DD10's.
- **Flux statistic.** DD14 section 6 with its A1, unchanged:
  - the apertures: 16 px discs at catalogue components with S_app ≥ 20 mJy
    inside the facet interiors, merged within 33 px; each disc's catalogue
    flux is the sum of S_app of every component in it;
  - `ε^real_f(M) = Σ M over the non-pin apertures / Σ S_app − 1`;
  - the same for the pin aperture alone.
- **Models scored** (zero solves):
  - R-QPG12's M₁₂, which is read;
  - DD11's R-Q6 M₆ (pinned) and DD13's R-QP12 M₁₂ (all released), both
    reported;
  - RM, as the code check (ε = 0 to 1e-9).
- **Matched resolution:** integrated flux in 48″ discs, coarser than the
  RACS beam (DD14 section 6). No residual is added.
- **Not blind:** d1's pin box was read in DD13. The pin apertures are
  reported and not read; the reading uses the non-pin apertures only.
- **Reading (frozen).**
  - Per readable facet (at least one non-pin aperture), **agrees with the
    catalogue** if |ε^real_f(R-QPG12)| ≤ 0.10.
  - The facets read are d1-d3 on an "in" reading, and d1-d2 on an "in for
    d1-d2" reading (d3 is then reported).
  - **Agrees with the pinned loop** if |ε^real_f(R-QPG12) −
    ε^real_f(R-Q6)| ≤ 0.05. This is reported.
  - **The real check passes** if every facet read is readable and agrees
    with the catalogue.
  - Otherwise: **the real facet flux scale differs from the catalogue** in
    the facets named, and the gated rule waits for the cause (catalogue,
    beam or loop).
- Also reported: DD13 section 7's convergence reading for R-QPG12 (lifts,
  tames d3), beside R-Q6 and R-QP12.

## 8. Literature and novelty

Unchanged from DD14 section 7: the per-direction flux-gain degeneracy and
holding the scale with a beam-weighted model are standard DD practice
(killMS/DDFacet, Tasse et al. 2018, A&A 611, A87; from recall). The beam is
from Mauch et al. 2020 and de Villiers & Cotton 2022 (DD14). Restricting
direction-dependent freedom to directions with enough apparent flux is
common practice in facet calibration, where facets are chosen by apparent
flux (van Weeren et al. 2016, ApJS 223, 2; from recall). No novelty is
claimed.

## 9. Implementation, host and cost

- `tools/oracles/dd15/dd15.py` (new, MIT): `build` (the rebuild and gate
  GB15), `gater` (R15 a-c), `loop` (QPG12, ATG12, QPG12-O, R-QPG12),
  `score`, `real` (with R15 d). It imports DD14's driver for the beam, the
  build, the apertures and the scores. No solver or library change.
- `tests/test_dd15.py`: the gated rule and mask on small synthetic inputs
  (section 3's unit checks), the d3 clause, and the answer table.
- Python: this worktree's own `.venv` with its extension.
- glacier, shared, under the main checkout's `tools/heavy_lock.py`:
  - loops 6 slots, 20 GB each, at most two at once, so about 4 slots
    stay free for the coordinator's checks;
  - the rebuild 2 slots, 16 GB; PSF 4 slots, 10 GB; R15 4 slots, 16 GB;
  - no exclusive or timing runs.
- **Run cap (Rust solves, the one-longer solves counted):**
  - QPG12 12: cycles 3-12, plus 2;
  - ATG12 4;
  - QPG12-O 12;
  - R-QPG12 12, if run.
  - That is 40, plus one spare per class (arm, control, O twin, real):
    44. A stopped arm uses fewer.
- Lanes: A runs ATG12, then QPG12; B runs QPG12-O, then R-QPG12 if
  section 6 calls for it. Expected about 4,500 s for ATG12 and 9,000-
  12,000 s per solved loop at 6 slots.
- Wall times go into [tool-timings.md](tool-timings.md). At the end OB's
  MS, `gate/O` and the PSF arrays are deleted. Records stay in the run
  root, and a compact archive goes in `results/dd15-beam-gate/`.

## 10. Measured result

Run root `D:/rang/outputs/dd15-20261128/`. Host glacier, shared, under the
main checkout's `heavy_lock.py`. Two lanes, every loop 6 slots and 20 GB
booked. Archive `results/dd15-beam-gate/`: `score.json`, the gates,
`reuse.json`, per-cycle `info.json` for ATG12, QPG12 and QPG12-O,
`times.log`, the scripts and `posthoc-d3-pin.json`.

**Gates, all pass.**
- **GB15:** DD14's GB 1-4 pass (GB 2 7.6e-6 Jy, GB 3 2.7e-6 Jy). `beam.npz`
  arrays, OB's truth gains and the apertures equal DD14's bitwise, and the
  sky SHA-256 is DD14's.
- **R15 a:** QN everywhere, from DD14's QPN12 cycle 11, gives DD14's M₁₂
  bitwise (563 components).
- **R15 b:** cycle 1 gives QPN12's M₂ bitwise.
- **R15 c:** the real form on O, from DD13's QP12 cycle 1, gives DD13's M₂
  bitwise.
- R15 d did not run (section 7 not called).
- QPG12 did not stop at M₆: row 2 there.

**Points on OB** (d1, d2, d3; truth s = 1; κ^pin against the O twin;
references re-scored from DD14's records):

| Point | e^sr d1-d3 | raw e d3 | s d1-d3 | G^sr d1 | Against Q (DD15's d3 clause) | κ^pin d1-d3 | G | F d1-d2 | F d3 | Row |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **QPG6** | 0.150, 0.322, 1.314 | 1.100 | 0.995, 0.979, 0.591 | 0.681 | helps (0.42 ×) | −0.024, −0.016, **−0.350** | yes | yes | no | **2** |
| **QPG12** | 0.139, 0.315, 1.303 | 1.109 | 0.997, 0.978, 0.626 | 0.705 | helps (0.39 ×) | −0.026, −0.011, **−0.411** | yes | yes | no | **0** |
| QPN6 (ref.) | 0.149, 0.322, 1.288 | 1.048 | 0.996, 0.982, 0.496 | 0.683 | helps (0.42 ×) | −0.019, −0.036, +0.073 | yes | yes | no | 2 |
| QPN12 (ref.) | 0.141, 0.312, 1.249 | 1.136 | 0.994, 0.983, 0.806 | 0.700 | helps (0.40 ×) | −0.014, −0.035, +1.472 | yes | yes | no | 0 |
| Q6 (ref.) | 0.359, 0.307, 1.091 | 1.312 | 0.977, 1.003, 1.382 | 0.209 | - | −0.145, −0.010, −0.336 | no | no | no | 0 |
| Q12 (ref.) | 0.356, 0.282, 0.886 | 1.318 | 0.959, 1.082, 1.787 | 0.215 | - | −0.128, −0.007, −0.278 | no | no | no | 0 |
| ATG6 (control) | 0.091, 0.214, 1.225 | 1.001 | 0.980, 1.030, 0.295 | 0.813 | - | (pin vs sky −0.069, −0.068, −0.015) | - | - | - | - |
| ATG12 (control) | 0.090, 0.211, 1.216 | 1.000 | 0.981, 1.031, 0.305 | 0.816 | - | (pin vs sky −0.069, −0.068, −0.015) | - | - | - | - |

- **O twin QPG12-O:** raw e 0.150, 0.322, 0.539 at M₆ and 0.134, 0.319,
  0.537 at M₁₂; s 0.99-1.04. Reported, not read.
- Every facet is readable: ATG12's pin apertures hold 0.93-0.99 of sky O's.

**Frozen readings.**
- **G holds at both N.** QPG12 reads "closes" and helps against Q.
  - d1 ratio 0.42 and 0.39.
  - d2 0.322 and 0.315 against Q's 0.307 and 0.282, under the 1.2 × bar.
  - d3 raw 1.100 and 1.109 against bars of 1.57 and 1.58.
- **F's d1-d2 terms hold at both N.**
- **F's d3 term fails at both N.**
  - At M₆ it is inside row 2's allowance: 0.350 ≤ 0.336 + 0.05.
  - At M₁₂ it is not: 0.411 > 0.278 + 0.05.
- **Answer (frozen table): "out: the pinned rule stays in the recipe".** The
  failing term is F's d3 at M₁₂, alone. Section 7 does not run.
- **References under DD15's rules (recorded, not deciding):**
  - QPN12: rows [2, 0], out by its d3 excess (+1.47).
  - Q12: rows [0, 0]. The pinned rule itself fails F in d1 (κ^pin −0.13)
    and d3 (−0.28).

### Reading the result (post hoc, A1; changes no frozen reading)

- **Pinned d3 on OB loses flux round the pin.**
  - QPG12's d3 pin disc goes 0.087 → 0.057 Jy from M₂ to M₁₂, while the
    5 × 5 box stays at the catalogue's 0.0825 Jy. Högbom builds negative
    flux in the ring.
  - The O twin holds 0.096 Jy from M₃ on.
  - QPG12's d3 cells stay 70 % untrusted throughout (O twin 3 % from
    cycle 4). So most of d3's image gains are the nominal √B_nom, and the
    trusted remainder carries s_d3 0.59-0.63.
  - Released (QPN12), the same facet builds a +147 % excess instead.
  - Neither rule holds d3's flux on OB; the truth gains do (ATG12 −1.5 %
    against the sky).
- **The gate does its job in d1 and d2.** QPG12's d1-d2 numbers equal
  QPN12's within 0.01 in e^sr, s and κ^pin. Pinning d3 does not disturb
  the high facets.
- **The d3 loss grows with cycles.** −0.35 at M₆, −0.41 at M₁₂, with no
  sign of levelling at 12. That is the same "M₆ passes, M₁₂ fails" pattern
  as QPN in DD14, with the opposite sign.

**Cost.**
- Walls (lock waits included; QPG12's includes waiting for the M₆ inputs):
  ATG12 4,874 s, QPG12 12,000 s, QPG12-O 12,266 s.
- Prep: build and GB15 398 s, R15 702 s. Score 4 s.
- Solves: ATG12 4, QPG12 12, QPG12-O 12. That is 28 against a cap of 44.
- A GS solve took 720-900 s at 6 slots.

## 11. For the coordinator

- **Frozen answer: "out"; the pinned rule stays.** QPG12 meets G and F's
  d1-d2 terms at M₆ and M₁₂ (d1 e^sr 0.139, s within 2.2 %, κ^pin within
  2.6 %). It fails only F's d3 term: the pinned d3's pin aperture is
  −35 % at M₆ and −41 % at M₁₂, past the allowance at 12 (0.328).
- **What it settles for #15's convention question.**
  - In high-beam facets, the nominal beam in the image gains plus released
    pins holds the scale and keeps the gain win: QPN12 and QPG12 agree.
  - In a facet at B 0.36, neither the released rule (+147 %) nor the pinned
    rule (Q12 −28 %, QPG12 −41 %) holds the flux on OB. Only the truth
    gains do.
  - The low-beam facet's flux is therefore outside what rang's DD loop
    calibrates on this field.
- **Recommended:** close the convention question as "beam in the model
  required; pins released only where B_nom ≥ 0.5 is safe for d1-d2 but not
  adopted, because no rule holds a facet at B 0.36". Facets below half
  power should be flagged as uncalibrated flux, or left out of DD
  solutions. Choosing that is the owner's or the coordinator's call.
- **Not run:** section 7, so there is no real-data flux reading for any
  rule.

## 12. Owner decision

**2026-11-28, owner: option A.** The convention question of #15 is closed as
"beam in the model required; pins kept". Releasing pins where B_nom >= 0.5
is not adopted: no real-data check has read it. Facets below half power
(B_nom < 0.5) are a known limitation: their flux is reported as uncalibrated,
or the facet is left out of the DD solutions. #15 itself stays open for the
rest of the direction-dependent work.

## Amendments

**A1, 2026-11-28, post hoc diagnostics, after the frozen reading. They
change no frozen reading.** The d3 pin disc and box flux per cycle for
QPG12 and QPG12-O, and their d3 untrusted shares, were read from the kept
models and records, with zero solves (`posthoc-d3-pin.json`). Section 10's
"Reading the result" reports them.
