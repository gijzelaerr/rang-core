# DD10: a Gauss-Seidel direction update in the Rust DD kernel, and an off-axis model from DD-corrected facet images on O

Issue #15. Follows [dd9-solver.md](dd9-solver.md) (DD9),
[dd8-offaxis.md](dd8-offaxis.md) (DD8) and [dd7-cause.md](dd7-cause.md)
(DD7). Branch `dd10-gs`. Coordinator brief 2026-11-26. Sections 1-9 are
frozen 2026-11-26, before the code that runs them and before any
measurement. Later changes are dated amendments, committed before the
reading they affect.

Status: **proposed 2026-11-26.**

## 1. Questions

DD9 found, with a numpy reference of the Rust kernel that reproduces DD6 and
DD8 to every digit:
- the default (Jacobi, halved) DD update is linearly unstable at the solution
  in 56 of 113 O-X intervals (ρ up to 1.17), only with all four facets;
- Gauss-Seidel over directions (I2) and a joint direction block (I3) close
  O-X's gap at cap 500 (min d1-d3 0.974 and 0.991, against 0.449) and stay
  accurate, but fail DD9's frozen same-fixed-point check;
- where flag arrays agree, all updates agree to 3e-14 (A4, post hoc);
- d1's error stays at e/ê about 72 in every arm with M₀ᶜ: the off-axis model
  gap sets the error, and Gauss-Seidel does not help with the wrong model.

DD10 asks:

- **(1) The option.** Does a Gauss-Seidel direction update in the Rust
  kernel (`core/src/cal/diag_dd.rs`) equal DD9's reference I2, while the
  default path stays bit-identical?
- **(2) The fixed point.** Is DD9's same-fixed-point failure only the flag
  ladder, or a real difference in the fixed point? Settled in the reference
  (section 4) before any claim about the option.
- **(3) The model.** On O, where the truth is known, does an off-axis model
  built from DD-corrected facet images (DD3's loop, with the option) reduce
  d1's truth error from M₀ᶜ's towards the exact model's, without harming
  d2 and d3?
- **(4) Real data.** One reading of the same loop on the real subset with
  the 145 bad baselines flagged, against a frozen convergence rule.

Not done (brief): the unit-gain deep clean (DEEP) is not a model on real
data; d3 is not merged; the robust held-out score is not a criterion. On O,
sky O (DEEP in d1-d3) is the truth, used only as the exact-model reference.

**Choice of update.** Gauss-Seidel (DD9's I2), not the joint block (I3): it
reuses the kernel's per-direction update unchanged, needs no 4 × 4 solve or
condition-number fallback, and DD9 measured it on O-X, B-X, O (bGS) and real
data (real-bGS). On B-X its min d1-d3 at cap 500 is 0.956 against the
default's 0.974, inside DD9's 0.02 admissibility margin.

## 2. Data and inputs

DD7's, DD8's and DD9's roots under `D:/rang/outputs/` are read only. DD10's
root is `D:/rang/outputs/dd10-20261126/`.

- **O:** rebuilt in DD10's root by `dd8.insert` (DD8's code, unchanged).
  Setup gate: GO passes as DD8 froze it; every `build.json` number equals
  DD8's `O/build.json` to 1e-9 relative; `sky.npy` has DD8's SHA-256.
  Truth: `truth.npz` (B's, per 4 integrations, d0 exactly 1), k = 0.5291.
- **Models:** M₀ᶜ = DD7's `b/sky.npy`; sky O = DD8's `O/sky.npy` (M₀ᶜ in
  d0, DEEP in d1-d3); RM = DD7's `models/RM.npy` (deep clean in d0, M₀ᶜ in
  d1-d3).
- **Real:** DD7's `real/sub.ms`. The 145 bad baselines
  (`dd7.bad_pairs()`, gemclean-heldout's `badbaselines.json`) are flagged in
  memory (FLAG set on their rows, no MS copy); setup gate: 65,250 rows, as
  DD7's `builds/R1.json`.
- **DD9's reference and kept solves:** `tools/oracles/dd9/dd9.py`;
  `sums/O-skyO.npz`; `solve/O-X-default.npz`, `solve/O-X-I2.npz` (cap 500
  and 2000, no global stop, each with its one-longer solve).
- **DD8's Rust O-X:** `grid/O-X.npz` (cap 500, stop fraction 0.99, 500
  iterations; gains, flags, converged mask), from the kernel unchanged since
  2026-11-23.

## 3. Part 1: the option and its gates

**The option (frozen).** `diag_dd::Settings` gains `direction_update`:
`Jacobi` (the default, QuartiCal 0.2.7's DD update, unchanged) or
`GaussSeidel`. Gauss-Seidel, per iteration `loop_idx`:
1. for d = 0, 1, ..., ndir − 1 in order, skipping pinned directions: the
   residual of every kept cell at the current gains (directions before d
   already updated in this iteration); direction d's `J^H J` and `J^H r`
   only, as the kernel forms them; its update exactly as the default
   (non-generalised invert, no update if det < 1e-6); unflagged gains
   `g ← g + u/2`, flagged gains held at 1;
2. then the flag ladder (`update_gain_flags`) on every gain, as the
   default, and `km1 ← g`.
The global stop test, `finalize_gain_flags`, referencing and the solution
layout are the default's. `diag_complex` only; `phase` with Gauss-Seidel is
a settings error. This is DD9's `iterate(..., "I2")`.

The Jacobi path's functions (`accumulate`, `step_gain`, `run_interval`'s
loop) are left textually unchanged; Gauss-Seidel is a separate function
behind one branch. Exposure: `rang.cal_gain.solve_dd(...,
direction_update="jacobi" | "gauss-seidel")` and the extension's
`cal_gain_solve_dd(..., direction_update=0 | 1)`. The DD solve has no
configuration key, CLI command or `RANG_*` variable, so none is added;
`python docs/gen_cli.py` is run to confirm `docs/cli.md` does not change.

**Gates (frozen; a miss stops DD10 at a setup outcome, reported):**

- **K1, the default is bit-identical.**
  - (a) The Rust DD unit tests and `tests/test_cal_gain_dd.py`,
    `tests/test_dd6.py`, `tests/test_dd9.py` pass unchanged.
  - (b) Synthetic A/B: the problems of `tests/test_cal_gain_dd.py` and
    `tests/test_dd9.py` solved with the default settings through the main
    checkout's extension and the branch's (refant 0 and None, d0 pinned and
    free, `ap` and `p`, caps 1, 5, 50, 300): SHA-256 of gains and flags,
    iterations and fraction equal in every case.
  - (c) Real-size: the default on O with sky O (DD8's O-X settings: 4 × 8 s,
    d0 free, refant None, stop 1e-7, fraction 0.99, cap 500) through the
    branch's extension: gains and flags bitwise equal to DD8's
    `grid/O-X.npz`. If not bitwise equal, the same run through the main
    checkout's extension decides: branch equal to main is a pass (DD8's
    archive then differs for a reason outside the kernel, recorded).
  - The gain-hash gate (`tools/gain_hash_gate.py`) replays DI solves only
    (`core.solve_complex`) and is blind to `diag_dd`. It is run by the
    quick check as usual; it is not the DD proof.
  - Consequence: the default path keeps DD6's QuartiCal 0.2.7 parity status
    (flags, fraction and iterations identical; gain products 5.4e-5 against
    a 1e-5 bar, not met). It cannot get worse.
- **K2, the option equals DD9's reference I2.**
  - (a) Synthetic (`tests/test_dd9.py`): Rust Gauss-Seidel against the
    reference's I2 at 1-40 iterations, pinned and free: flags identical,
    gains to 1e-9.
  - (b) O-X, cap 500, no global stop (stop fraction 2), and the one-longer
    solve (501), against `O-X-I2.npz`'s cap-500 pair, with GR's tolerances:
    per-direction converged fraction within 0.005 in d0-d3; flagged gains per
    direction within 1 %; on cells converged in both, max |Δ(g_p conj g_q)|
    ≤ 1e-6. Iterations exactly 500.
- **K3, agreement with the default where flags agree.** Rust Gauss-Seidel
  (K2b) against the Rust default (K1c; it ran all 500 iterations, its global
  fraction stays below 0.99), on intervals whose flag arrays (all
  directions) are identical in both, on cells converged in both:
  - **operational bound (cap 500):** products median ≤ 1e-6 and
    p99 ≤ 1e-4 (DD9's thresholds). At cap 500 a "converged" gain is only
    within about step/(1 − ρ) of the fixed point, so no tighter bound is
    frozen here.
  - **strict bound:** the reference at cap 2000 (DD9 A4 measured 3e-14 on
    identical-flag intervals) is the strict statement; it is reported, not
    re-run.

**Oracle.** For the kernel: DD9's numpy reference (I2 for the option, the
default for the default path), which DD9's gate GR tied to the Rust kernel.
For accuracy: O's truth gains. QuartiCal 0.2.7 has no Gauss-Seidel DD update,
so the option has no QuartiCal oracle; the default path's parity is kept by
K1.

## 4. Part 1: the fixed point (reference, before any Rust reading)

**Statement.** For the same set of flagged, pinned and det-suppressed gains,
both maps leave g unchanged exactly when every free direction's `J^H r` is
zero at g (a stationary point of χ² over the free gains). So Jacobi and
Gauss-Seidel have the same fixed points; they can only end in different
places through different flags, or by one not converging. Two tests, on
DD9's `sums/O-skyO.npz` and kept solves, in DD9's reference:

- **T1, GS's answer is a fixed point of the default.** At I2's cap-2000
  gains and flags on O-X, one default iteration's relative step
  `|Δg| / |g|` over the free gains, per interval. Frozen: on intervals where
  I2 has converged at cap 2000 (every unflagged gain converged), max
  relative step ≤ 1e-6: **a fixed point of the default update**; else
  **not**.
- **T2, the default's answer is GS's answer under the default's flags.**
  I2 run from unit gains with the default's cap-2000 final flags imposed
  (those gains held at 1 from the start; the ladder may add flags, which are
  counted, and intervals whose final flags then differ from the default's
  are excluded and counted), to cap 2000, no global stop. Against the
  default's cap-2000 gains, on cells converged in both:
  - on the 41 intervals that the default converges between 500 and 2000
    (DD9's slow intervals, where its ladder flagged 60 gains I2 keeps), and
    separately on all intervals converged in the default at cap 2000;
  - frozen: products median ≤ 1e-6 and p99 ≤ 1e-4 (DD9's same-fixed-point
    thresholds) on the slow intervals: **only the flag ladder**; else **a
    real difference in the fixed point**.
  - The 25 intervals the default never converges have no default answer
    and are reported only.

**Admissibility (DD9 section 4's rule, completed).** Gauss-Seidel is
**admissible** as an option if K2 and K3 pass and T1 and T2 read "a fixed
point of the default update" and "only the flag ladder". DD9 already
measured the other clauses (closes O-X's gap; B-X not worse by more than
0.02; accurate on O-X).

## 5. Part 2: an off-axis model on O

**Solver for every scored arm (frozen):** Rust `diag_dd`, Gauss-Seidel,
4 × 8 s, all channels, d0 free, refant None, stop criterion 1e-7, stop
fraction 0.99, cap 500; the one-longer solve (stop fraction 1.0) on every
scored point for the per-direction fractions (DD4c).

**Arms:**

| Arm | Model of the scored solve |
| --- | --- |
| **A0** | M₀ᶜ (the loop's start, the model-gap reference; DD9's bGS in Rust) |
| **AX** | sky O (exact; DEEP in d1-d3, the ceiling) |
| **AL** | the loop's M₃ (below) |
| **AT** | the truth-gain control's M₃ (below) |

**The loop AL (frozen).** M₀ = M₀ᶜ. For k = 0, 1, 2:
1. solve with M_k (k = 0 is A0);
2. residual `R = DATA − Σ_f G_p,f M_f G_q,f^H` at the solved gains, and its
   flat-gain facet image (DD4's `facet_image`: per facet f,
   `½ Σ_hands conj(g_p,f) R g_q,f`, imaged with the Stokes I weights `w_I`,
   divided by the facet's c);
3. Högbom (DD3's `hogbom`): loop gain 0.1, at most 5,000 components per
   cycle, stop at max(5σ, 1 mJy) with σ the MAD-based rms of the d1-d3
   facet interiors; peaks searched in the **d1-d3 interiors only**, minus
   DD4's 5 × 5 pin boxes at the d1-d3 facet-centre pixels (so the facet
   centre fluxes stay fixed, against DD3's gain-flux degeneracy); M_{k+1} =
   M_k + components. d0 is not cleaned (its model is exact on O).

Then the final solve with M₃ is AL's scored point. Three minor cycles, no
early stop.

**Gains entering the images (frozen).** A gain (interval, antenna,
direction) is **trusted** if unflagged and both hands' amplitudes lie in
[1/3, 3] (the truth amplitudes are within ±20 %). Rows (baseline and
interval) with an untrusted gain in any direction on either antenna get zero
weight in every facet image of that cycle and in its c; their weight share
is reported. Unconverged trusted gains are used as solved.

**The truth-gain control AT (frozen).** The same three minor cycles from
M₀ᶜ with O's truth gains (per 4-integration block, all trusted) in steps 2-3
and no solve inside the cycles; then the final Gauss-Seidel solve with its
M₃, scored. It separates "the rule cannot build the model" from "the solved
gains are too wrong to bootstrap it".

**PSF.** rang's `fits_image` PSF of O's `w_I` (2 NX × 2 NY, DD4's grid
2880² at 3″), built in DD10's root and fixed for every cycle of O.

**Scores per scored point:** `e_d` in d1, d2, d3 (DD5: median
|P − P̄| / |P̄| over unflagged cells, pairs and hands, all cells; and on cells
converged in both antennas), ê and e/ê, per-direction converged fraction,
iterations, d3 |g| p99, maximum and cells > 10. Per model: Σ|M − sky O| and
net flux per facet d1-d3 (`dd6.facet_abs_error`), components and stop level
per cycle, and the excluded weight share. AL's cycle-1 and cycle-2 solves
get `e_d` (no second solve).

**Rule per arm a ∈ {AL, AT} (frozen):** with
`G_d = (e_A0,d − e_a,d) / (e_A0,d − e_AX,d)` (the share of the model gap's
error closed, all cells):
- **harm:** `e_a,d > 1.2 e_A0,d` in d2 or d3;
- **closes:** G_d1 ≥ 0.5 and no harm;
- **partly:** 0.2 ≤ G_d1 < 0.5 and no harm;
- **moves the error:** G_d1 ≥ 0.2 with harm;
- **no:** G_d1 < 0.2.

| AL | AT | Reading |
| --- | --- | --- |
| closes or partly | any | **the loop builds a better off-axis model from DD-corrected facet images on O** (in the measured share) |
| no or moves | closes or partly | **the rule can build the model, but the solved gains are too wrong to bootstrap it**: M₀ᶜ's gains absorb the gap and the corrected images inherit it |
| no or moves | no or moves | **a point-component Högbom with the unit-gain PSF cannot build d1's model at this depth**, even from correctly calibrated images |

G_d2 and G_d3 are reported beside G_d1.

## 6. Part 2: one real-data reading

Base: DD7's `real/sub.ms` with the 145 bad baselines flagged (setup gate,
section 2). PSF: `fits_image` PSF of `w_I` with those rows at zero weight.

- **R0:** RM, the section-5 solver (Gauss-Seidel, cap 500, d0 free).
- **RL:** AL's loop from RM, every rule as section 5 (d1-d3 cleaned, pins
  kept, trusted gains, three minor cycles), final solve with M₃.

**Rule (frozen), convergence only:**
- **lifts:** min over d1-d3 of RL's per-direction fraction ≥ R0's + 0.20;
  else **no lift**;
- **tames d3:** RL's d3 |g| p99 ≤ 3 and maximum ≤ 10 (DD9's rule);
- the reading is about convergence, not accuracy. It is **supported by O**
  only if AL reads "closes" or "partly" on O; otherwise **O does not support
  reading it as better gains**.

Reported beside it: per-direction fractions per cycle, components per cycle,
the residual-image rms over the d1-d3 interiors for R0 and RL against the
thermal image σ, and the excluded weight share.

## 7. What the outcomes mean for the DD plan

| Outcome | Next DD step |
| --- | --- |
| K1-K3 pass, T1-T2 "only the flag ladder" | Gauss-Seidel is an admissible option: same answer, converges where the default is unstable; candidate for the DD recipe's update once a real-data case needs it |
| T2 "a real difference" | The option changes the answer; it stays an experimental option, and the difference is the next diagnostic |
| AL closes or partly, real lifts and supported | Carry the loop into the real DD recipe (145 flagged); image-domain checks on real data next |
| AL closes or partly, real no lift | The real data need more than the model (DD7's other properties); combined insertion into O |
| AT closes, AL not | A bootstrap that keeps the gains from absorbing the gap (phase-only first cycles, longer first intervals, or an amplitude constraint), tested on O |
| AT and AL not | A better deconvolver in the loop (GeMClean, multi-scale, per facet), tested on O |

## 8. Not claimed

Image quality; real gain accuracy; a speed claim for the option (cost is
reported, not gated); anything about QuartiCal beyond K1's consequence.

## 9. Implementation, host and cost

- `core/src/cal/diag_dd.rs` (the option, unit tests), `core/py/src/cal_gain.rs`
  and `python/rang/cal_gain.py` (exposure), `tests/test_cal_gain_dd.py` and
  `tests/test_dd9.py` (K1a, K2a).
- `tools/oracles/dd10/dd10.py`: `abtest` (K1b, run under each extension),
  `point` (a Rust solve with the second solve and section 5's scores),
  `k2`/`k3` (gates against DD9's and DD8's files), `fixedpoint` (T1, T2 in
  DD9's reference), `loop` (AL, AT, RL), `score`.
- glacier, shared, under the main checkout's `tools/heavy_lock.py`: a Rust
  solve point 8 slots and 20 GB (the data, four f32 model columns and the
  solver's state); the reference tests 2 slots and 6 GB; builds through
  `tools/check_all.py --quick` (which takes the lock itself). No exclusive
  or timing runs. At most two solve jobs at once.
- **Point cap (Rust solves, each second solve counted):** K1c 1 (+1
  contingent); K2b 2; A0 2; AX 2 (or K2b's pair, if it ran 500 iterations
  and its stop would not have fired: then the two settings are the same
  solve); AL cycles 1, 2: 2, final 2; AT final 2; R0 2; RL cycles 1, 2: 2,
  final 2. 19-21 solves, plus one spare per class.
- Expected: the default's cap-500 solve took 371-464 s in DD8 (4 slots);
  Gauss-Seidel forms the full residual once per direction, so about 3-4 ×
  per iteration. Predict about 50 s, a facet image set about 60 s, a Högbom
  cycle up to about 150 s. Wall times go into
  [tool-timings.md](tool-timings.md). The rebuilt O MS is deleted at the
  end; records stay in the run root and a compact archive in
  `results/dd10-gs/`.

## 10. Measured result

Run root `D:/rang/outputs/dd10-20261126/`. Host glacier, shared, under the
main checkout's `heavy_lock.py`.

**Setup.** O rebuilt (230 s): GO passes; every `build.json` number equals
DD8's; `sky.npy` has DD8's SHA-256.

**K1b: pass.** 64 default-settings solves (two synthetic problems; refant 0
and None; d0 pinned and free; `ap` and `p`; caps 1, 5, 50, 300): gains and
flags SHA-256, iterations and fraction identical between the main checkout's
extension and the branch's (`k1b/compare.json`).

**Section 4 (reference, read before any Rust reading of the option):**
- **T1: a fixed point of the default update.** At I2's cap-2000 solution,
  on the 110 intervals where I2 has converged, one default iteration moves
  no free gain by more than 1.6e-15 relative (median of the per-interval
  maxima 7.8e-16).
- **T2: only the flag ladder.** I2 started with the default's cap-2000 flags
  imposed reproduces the default's answer on the slow intervals: products
  median 2.5e-10, p99 1.4e-7 (max 1.5e-6) on 38 of the 41 (531,846 cells),
  against median 3.9e-4, p99 0.026 (max 0.40) for I2 without them (DD9's
  failing comparison). The other 3 slow intervals are excluded: the imposed
  run flagged 3 more d3 gains there. On all 85 intervals the default
  converges with equal flags: median 1.7e-15, p99 7.2e-8. On the 25
  intervals the default never converges (no default answer): median 5.6e-9,
  p99 2.0e-6. Wall 843 s (2 slots), T2's 2001 iterations 841 s.
- So DD9's same-fixed-point failure is the flag ladder only: both updates
  have the same fixed points, and the default reaches a different answer
  only where its ladder has flagged gains it cannot converge.

**K1a: pass.** The Rust DD unit tests (8, 3 new), `tests/test_cal_gain_dd.py`,
`tests/test_dd6.py` and `tests/test_dd9.py` pass.

**K1c: pass, bitwise.** The default on O-X through the branch's extension
(8 slots; predict 44 s, solve 246 s, 500 iterations, global fraction 0.522)
gives gains and flags bitwise equal to DD8's `grid/O-X.npz`. The contingent
main-extension run was not needed.

**K2a: pass.** Rust Gauss-Seidel against the reference's I2 on synthetic data
(1-40 iterations, free, d0 pinned, d2 pinned): flags identical, gains within
1e-9 (3e-16 at up to 20 iterations). The first draft of the test ran the Rust
side with stop fraction 1.0 against the reference's 2.0; the sweep reached
fraction 1.0 at iteration 39 and stopped there, a test-setup difference,
fixed by running both sides without the global stop (commit 69da36c0).

**K2b: pass.** Rust Gauss-Seidel on O-X, cap 500 and 501, no global stop:
500 iterations; per-direction fractions 0.9969, 0.9795, 0.9739, 0.9739,
equal to the reference's to every digit; flagged gains 113, 113, 113, 116 in
both, flag arrays identical; products on cells converged in both within
6.0e-14 (median 1.2e-16 to 2.2e-15 per direction). e/ê 1.20, 1.08, 1.08 in
d1-d3; d3 |g| max 1.38. Solve 672 s and 742 s (8 slots): 2.7 × the default's
246 s per iteration.

**K3: pass.** Against the Rust default (K1c, equal to DD8's), on the 63 O-X
intervals whose flag arrays are identical in both, on 637,200 products of
cells converged in both: median 2.5e-16, p99 3.6e-15, max 1.8e-14 (frozen
bounds 1e-6 and 1e-4).

**Admissibility (section 4): admissible.** K2 and K3 pass, T1 reads "a fixed
point of the default update" and T2 "only the flag ladder". With DD9's
clauses (closes O-X's gap, B-X within 0.02, accurate on O-X), Gauss-Seidel is
an admissible option: the default's answer where the default converges
without extra flags, and a converged answer where the default is unstable.

## Amendments

**A1, 2026-11-26, post hoc (after AL's cycle-0 record was read: A0's
fractions and e_d, its excluded weight share and its Högbom summary; before
AL's cycle-1 solve finished and before any AX, AT or RL record).**
- What was seen: under section 5's frozen image rule, A0's gains leave
  **2.1 % of the weight** in the cycle-0 images (excluded share 0.979). d3's
  gains run away on most antennas (|g| p99 13.6, max 59; DD9's bGS), and a
  row is dropped if any direction's gain on either antenna is untrusted. The
  cycle-0 Högbom then stops at 13 mJy (5σ of a 2.6 mJy residual) with 4,770
  components of net flux 0.008 Jy. AL continues unchanged and is read by the
  frozen rule.
- Added, reported only (no frozen reading changes, and it cannot be chosen
  by section 5's table): **ALu**, the same loop with one change in step 2:
  an untrusted gain (flagged, or an amplitude outside [1/3, 3]) is set to 1
  in the residual and the facet images, and no row is dropped. ALu's cycle 0
  is A0 (the same deterministic solve; its gains are reused, not re-solved).
  Its final solve is scored as section 5's arms, and G_d1 is reported with
  the reading section 5's rule would give.
- RLu (the same change on real data) runs only if ALu would read "closes"
  or "partly"; otherwise it is not run, and that is reported.
