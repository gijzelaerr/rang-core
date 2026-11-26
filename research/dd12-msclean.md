# DD12: a multi-scale minor cycle in the DD loop, on O

Issue #15. Follows [dd11-start.md](dd11-start.md) (DD11) and
[dd10-gs.md](dd10-gs.md) (DD10). Branch `dd12-msclean`. Coordinator brief
2026-11-26. Sections 1-9 are frozen 2026-11-26, before the code that runs
them and before any measurement. Later changes are dated amendments,
committed before the reading they affect, and labelled post hoc where they
follow a reading.

Status: **proposed (frozen).**

## 1. Question and hypotheses

DD11 on simulation O (truth known), every scored point Rust Gauss-Seidel,
4 × 8 s, d0 free, cap 500, rule U (untrusted gains set to 1 in the images):

| DD11 arm | e d1, d2, d3 | G d1 | d1 Σ\|M − sky O\| at M₆ |
| --- | --- | --- | --- |
| A0 (M₀ᶜ) | 0.352, 0.544, 1.000 | 0 | 21.2 (M₀ᶜ) |
| AX (sky O, exact) | 0.0078, 0.0334, 0.0523 | 1 | 0 |
| Q6 (unit-amplitude images in cycles 0-1, 6 cycles) | 0.244, 0.301, 0.365 | 0.313 | 33-37 (all arms) |
| AT6 (truth gains, 6 cycles) | 0.128, 0.279, 0.387 | 0.649 | |

DD11's reading: the start is the right lever but not enough; d1 gains about
0.01 per cycle, and the point-component Högbom adds pixel error on d1's
extended emission (Σ|M − sky O| rises from 21 to 33-37 in every arm). Sky O's
d1 (DD8's DEEP; 4.43 Jy net, 15.9 Jy absolute) holds structure up to
about 64 pixels: the flux in the brightest 64 × 64 box is 3.15 Jy, in the
brightest 16 × 16 box 1.00 Jy, in the brightest 4 × 4 box 0.25 Jy.

**DD12's question.** Does a better deconvolver in the loop, GeMClean's
existing multi-scale minor cycle (radler's algorithm, `research/g5-multiscale.md`)
in place of DD3's Högbom, close more of d1's gap on O, with Q6's start and
rule U kept?

Hypotheses:
- **H-ms.** Multi-scale components model d1's extended emission with less
  pixel error, so the residual images feed the solve a better model and the
  solved gains absorb less. Arm MS against Q at the same cycle count.
- **H-ceil.** With the truth gains, multi-scale builds a better model than
  Högbom (it raises the truth-gain ceiling). Control ATM against AT.
- **H-cyc.** Twelve cycles of Q6's loop close more than six (the
  cycles-only reference). Q12 against Q6, with AT12 as its control.

## 2. Data, inputs and reuse

DD7's, DD8's, DD10's and DD11's roots under `D:/rang/outputs/` are read
only. DD12's root is `D:/rang/outputs/dd12-20261126/`.

- **O:** rebuilt in DD12's root by `dd8.insert` (DD8's code, unchanged).
  Setup gate (DD11's): GO passes, every `build.json` number equals DD10's
  `O/build.json` to 1e-9 relative, `sky.npy` has DD8's SHA-256.
- **PSFs:** DD10's `fits_image` PSF of `w_I` (5760², peak 1) on O and, if
  the real arm runs, on the real subset with the 145 bad baselines flagged;
  peaks equal DD10's to 1e-9 relative.
- **Reused from DD11 (copied into DD12's root with their SHA-256 in
  `reuse.json`, never changed there):**
  - Q6's cycles 0-5 (`info.json`, `gains.npz`, `next_model.npy`,
    `residual.npy`) and its cycle-6 scored solve (`gains.npz`, `info.json`).
  - AT6's cycles 0-5 (`info.json`, `next_model.npy`) and its cycle-6 scored
    solve.
  - A0's cycle-0 gains (Q6's `cycle-0/reuse_gains.npz`).
  - R-Q6's cycles 0-6 records and R0 (only if the real arm runs).
  - DD11's `score.json` (references A0, AX, AT, ALu, U6, Q6, AT6).
- The solve is deterministic for fixed inputs (DD10 A1, DD11 A1). Gate R
  (section 5) checks that this worktree's extension and the rebuilt O
  reproduce DD11's files before any reuse is relied on.

## 3. Shared rules (DD11's, unchanged unless stated)

- **Scored point:** DD11's (Rust `diag_dd`, Gauss-Seidel `ap`, 4 × 8 s, all
  channels, d0 free, refant None, stop 1e-7, stop fraction 0.99, cap 500,
  plus the one-longer solve for the per-direction fractions; DD10's
  `scores`).
- **Cycle:** DD11's: solve with M_k; residual at the image gains (rule U;
  Q6's unit-amplitude trusted gains in cycles 0 and 1); flat-gain facet
  images with `w_I`; a minor cycle; M_{k+1} = M_k + its increment. d0 is not
  cleaned.
- **Truth-gain arms solve only at their scored points** (DD11's A1
  deviation is not repeated).
- **N is fixed per arm** (6 or 12). No stop rule reads the truth. A
  12-cycle arm is also scored at M₆: its cycle-6 solve gets the one-longer
  solve as well, so its first solve is the same solve as the 6-cycle scored
  point.

**Minor cycle H (Högbom, the control's):** DD11's `hogbom_fast` (gain 0.1,
at most 5,000 components, stop max(5σ, 1 mJy), σ the MAD rms of the d1-d3
interiors, peaks in the d1-d3 interiors minus DD4's 5 × 5 pin boxes),
unchanged.

**Minor cycle S (multi-scale, frozen).** GeMClean's
`multiscale::run_multiscale_masked`, called on the cycle's residual image
through a new binding `rang._core.multiscale_image` (section 9) with an
image-domain measurement: `residual(m) = dirty − B m`, `B` the convolution
with the 2n PSF (`gemclean::Beam`, exact over the whole image). Settings:
- WSClean 3.7's multi-scale defaults: component gain 0.1, `-multiscale-gain`
  0.2, `-multiscale-scale-bias` 0.6, tapered-quadratic shapes, scale bias
  referenced to the theoretic beam, negative components allowed, radler's
  divergence limit 4.
- **Scales:** radler's automatic list for O's theoretic beam b
  (`multiscale::theoretic_beam` on O's UVW, frequencies and `w_I`, 2880 px of
  3″), **at most 5 scales** (`-multiscale-max-scales 5`: 0, 4b, 8b, 16b,
  32b). The automatic list without a cap runs to 1,440 px, wider than a
  facet; five scales reach about 64 px for b ≈ 2 px, sky O's largest
  structure (section 1). b and the scales are recorded.
- **Stop:** the same absolute threshold as H, max(5σ, 1 mJy) with σ the MAD
  rms of the cycle's residual over the d1-d3 interiors, computed in Python;
  no hand-back (`CycleStop::Threshold`), at most 50 image-domain major
  cycles, at most 5,000 sub-minor components. The threshold acts on the
  biased scale-convolved peak (scale 0: the plain peak, H's stop).
- **Mask:** H's search pixels (d1-d3 interiors minus the pin boxes) as the
  FITS mask: they confine the component centres at every scale.
- **Spill (frozen rule: clip).** A scale component's shape can reach outside
  the search pixels (d0, a pin box, a facet edge). The increment added to
  the model is the shape-convolved model set to zero outside the search
  pixels, the same support H's increments have. The clipped flux (net and
  absolute, per facet) is reported per cycle. The next cycle's residual is
  computed afresh from the visibilities, so the clip leaves no stale
  residual behind.
- Reported per cycle: components and flux per scale, sub-minor loops,
  image-domain cycles, the end reason (normal, stalled, diverged), seconds.

## 4. Arms

All arms start from M₀ᶜ (O), with Q6's start (cycles 0-1 images with
unit-amplitude trusted gains) and rule U, unless stated.

| Arm | Minor cycle | Cycles | Scored at | Eligible as best | Solves (new) |
| --- | --- | --- | --- | --- | --- |
| **Q6** (control, DD11's, reproduced by gate R) | H | 6 | M₆ | yes | reused |
| **Q12** (cycles-only reference) | H | 12 | M₆ (= Q6), M₁₂ | yes | 5 + 2 |
| **MS12** | S | 12 | M₆ (MS6), M₁₂ | yes (MS6 and MS12) | 11 + 1 + 2 |
| **AT12** (control) | H, truth gains | 12 | M₆ (= AT6), M₁₂ | no | 2 |
| **ATM12** (control) | S, truth gains | 12 | M₆ (ATM6), M₁₂ | no | 2 + 2 |

- Q12 continues Q6: cycles 0-5 and the cycle-6 solve are DD11's Q6
  (reused); cycle 6 builds M₇ from that solve's gains.
- AT12 continues AT6 the same way (DD11's AT6 cycles 0-5 and its cycle-6
  scored point).
- MS12's cycle-0 solve is A0 (reused, as in Q6). MS6 is MS12 scored at M₆.
- ATM12: O's truth gains in every cycle's images, no solve in the cycles.
- Real arm: section 7.

## 5. Gates

- **Gate R (reproduction, blocking; frozen).** With this worktree's
  extension and the rebuilt O: (1) Q6's cycle-0 residual image from A0's
  gains, rule U and unit amplitudes, equal to DD11's `cycle-0/residual.npy`
  (float32) bitwise, or within 1e-6 × its max |value| with `hogbom_fast`
  on it still giving DD11's `cycle-0/next_model.npy` bitwise; (2) the cycle-1 solve with DD11's M₁
  giving DD11's Q6 `cycle-1/gains.npz` gains and flags bitwise. Pass: DD11's
  Q6 and AT6 files are reused as section 2 says. Fail: no reuse; Q6 is rerun
  in full (7 solves) as Q12's first half, AT6 likewise, and the miss is
  reported.
- **Gate M (the binding; frozen, no truth read).**
  - M1 (exactness): on DD11's Q6 `cycle-0/residual.npy` with O's PSF and
    masks, the binding's returned residual equals dirty − B m (B m computed
    independently in NumPy/SciPy by a direct FFT convolution of the returned
    model with the 2n PSF) to max |difference| ≤ 1e-8 × max |dirty| over the
    image.
  - M2 (synthetic, `tests/test_dd12.py`): on a 128² image, a Gaussian of
    1 Jy (σ 6 px) and a 0.5 Jy point convolved with a Gaussian PSF (σ 1.5 px,
    peak 1): scales (0, 4, 8, 16) recover the total flux within 2 % and end
    with a residual peak below the threshold; M1's identity holds to 1e-10.
  - Pass: minor cycle S is used as section 3 says. Fail: the MS arms are not
    run; the miss is reported.
- **Pilot T (timing only; frozen, reads no truth quantity).** The same run
  as M1 (8 threads). It also fixes the scale count by cost:
  - ≤ 1,800 s: five scales as frozen.
  - > 1,800 s: four scales (0, 4b, 8b, 16b), timed again; then three. If
    three scales take more than 1,800 s, the MS arms are not run.
  - The scale count used is recorded; the ladder does not look at any
    model, image quality or truth number.

## 6. Scores and frozen readings

For every scored point: e_d (all unflagged cells) in d1-d3,
- `G_d = (e_A0,d − e_d) / (e_A0,d − e_AX,d)` (DD10's);
- `S_d = (e_A0,d − e_d) / (e_A0,d − e_AT·,d)` against the truth-gain
  control at the same N and minor cycle (AT6 or ATM6 at 6, AT12 or ATM12 at
  12), and against AT6 or AT12 (Högbom) for every arm;
- e on converged cells, e/ê, per-direction fractions, d3 |g| p99 and max,
  d1-d3 Σ|M − sky O| and net flux per facet, components and stop per cycle,
  untrusted shares, clipped flux (S).

**Per-arm reading (DD10's, unchanged):** harm: e_d > 1.2 e_A0,d in d2 or
d3; **closes:** G_d1 ≥ 0.5 and no harm; **partly:** 0.2 ≤ G_d1 < 0.5 and no
harm; **moves the error:** G_d1 ≥ 0.2 with harm; **no:** G_d1 < 0.2.

**Deconvolver effect (frozen), MS6 against Q6 and MS12 against Q12
(matched N):**
- **helps:** e_d1 ≤ 0.9 × the Högbom arm's, and e_d2, e_d3 ≤ 1.2 × its;
- **hurts:** e_d1 ≥ 1.1 × the Högbom arm's, or e_d2 or e_d3 > 1.2 × its;
- else **no effect**.
- A "helps" or "hurts" with the d1 ratio within 0.02 of its bar (0.88-0.90,
  1.10-1.12) is labelled **marginal** (DD11's readings were 0.894 and 0.895).

**The same rule on the controls (H-ceil):** ATM6 against AT6 and ATM12
against AT12: **multi-scale raises the ceiling** (helps), **lowers it**
(hurts), or **no effect**.

**Mechanism (frozen, reported beside the deconvolver reading):** at matched
N, MS's d1 Σ|M − sky O| ≤ 0.9 × the Högbom arm's: **less pixel error**;
≥ 1.1 ×: **more pixel error**; else **similar**. Sky O's d1 is itself a
pixel model, so this measures pixel agreement, not visibility agreement;
the truth error decides.

**More cycles (H-cyc):** Q12 against Q6: **help** if e_Q12,d1 ≤ 0.9 ×
0.244 without harm, else **do not help**; AT12 against AT6 is reported
beside it. MS6 against Q12 (multi-scale at half the cycles) is reported:
the ratio of e_d1 and of wall time.

**DD12's answer (frozen):**

| Condition | Reading |
| --- | --- |
| MS6 or MS12 closes (G_d1 ≥ 0.5, no harm) | **yes: the multi-scale minor cycle closes the loop on O** |
| no MS closes; MS helps against Q at a matched N | **partly: multi-scale helps (d1 x × Högbom's at N) but does not close** |
| MS no effect at both N; Q12 helps | **the cycle count, not the deconvolver, is the lever** |
| MS no effect or hurts at both N; Q12 does not help | **no: neither the deconvolver nor more cycles moves d1** |
| MS hurts at both N | **no: multi-scale hurts in this loop** (overrides the rows above it except "yes") |

The control readings say why: with "multi-scale raises the ceiling" a
"no" on the solved gains means absorption still limits; with "no effect" on
the controls the deconvolver is not the limit at this depth.

**Best arm (frozen):** among Q6, Q12, MS6, MS12 without harm, the lowest
e_d1; within 0.005 of each other, the lower mean of e_d2 and e_d3, then the
fewer cycles. With harm everywhere, the lowest e_d1, labelled "with harm".
Controls cannot be chosen.

## 7. One real reading

Only if the best arm is MS6 or MS12 and its deconvolver reading against
the matched Högbom arm is "helps" (marginal or not) without harm: that arm's
loop on DD7's real subset with the 145 bad baselines flagged (setup gate
65,250 rows), from RM, Q6's start, rule U, minor cycle S with the real
PSF's own scales (b from the real subset), N of the arm; R0 (DD10's RL
cycle-0 solve) reused. Read by DD11's section-7 rule (lifts: min d1-d3
fraction ≥ R0's + 0.20; tames d3: p99 ≤ 3 and max ≤ 10; supported by O if
the arm reads closes or partly), reported beside DD11's R-Q6 (min 0.961, d3
max 3.8) and its residual rms against the thermal σ. Convergence, not
accuracy. Otherwise no real arm runs, and the note says why.

## 8. What the outcomes mean for the DD plan

| Outcome | Next DD step |
| --- | --- |
| yes | carry Q6's start, rule U and minor cycle S into the real DD recipe; image-domain checks on real data |
| partly | keep S; the remaining gap is the gains' absorption (read with ATM): a constrained solve (amplitude prior in the Rust kernel) or a joint model-gain step on O |
| the cycle count | the loop with H and N ≥ 12; cost, not method, is the knob |
| no, with "raises the ceiling" | absorption limits: constrain the solve, not the images |
| no, with "no effect" on the controls | neither deconvolver nor cycles: a deeper d1 model from another route (catalogue, external image) |
| hurts | S as configured does not suit facet residuals; per-facet multi-scale or other settings, as a new note |

## 9. Implementation, host and cost

- **Binding:** `core/py/src/multiscale_image.rs` (new, MIT, own code): an
  image-domain `Measurement` over `gemclean::Beam`, `multiscale_image(...)`
  calling `multiscale::run_multiscale_masked` with one channel, and
  `multiscale_theoretic_beam(...)` calling `multiscale::theoretic_beam`.
  No change to `core/src`. Gate M (section 5).
- **Driver:** `tools/oracles/dd12/dd12.py` (`reuse`, `psf`, `setup`, `gater`,
  `gatem`, `loop` for Q12, MS12, AT12, ATM12 and the real arm, `score`). It
  imports DD11's `dd11.py` (and through it DD10's) for the context, solves,
  images, scores and `hogbom_fast`; no solver or library change.
- Python: this worktree's own `.venv` with its extension.
- glacier, shared, under the main checkout's `tools/heavy_lock.py`: a loop
  with solves 8 slots and 20 GB (DD11's figure; minor cycle S adds about
  4 GB of shape convolvers and twice-convolved PSFs); truth-gain loops the
  same (their scored solves need 8); O rebuild 2 slots, 10 GB; PSF 4 slots,
  10 GB; gates 8 slots, 20 GB. At most two loops at once. No exclusive or
  timing runs (pilot T is a shared run and is labelled so).
- **Run cap (Rust solves, second solves counted):** gate R 1; Q12 7; MS12
  14; AT12 2; ATM12 4; real 7 (N 6) or 14 (N 12). 28 on O plus the real
  arm, one spare per class (gate, O arms, controls, real).
- Expected: a GS solve 690-810 s at 8 slots, an image set 30-60 s, H 200-310
  s per cycle, S as pilot T measures. Wall times go into
  [tool-timings.md](tool-timings.md). The rebuilt O MS and the PSF arrays
  are deleted at the end; records stay in the run root, a compact archive
  in `results/dd12-msclean/`. D: stays above 150 GB free.
