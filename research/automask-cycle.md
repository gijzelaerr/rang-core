<!-- SPDX-License-Identifier: MIT -->
# Rang: does GeMClean finish its auto-mask one major cycle early? (issue #36)

Status, 2026-11-18 18:40 SAST: **proposed; nothing run.** This note was frozen before any reproduction run.
Only the inputs were copied and the build was made before the freeze; no image was made. Branch `automask-cycle`
from main `175bf323`. Results go under "Measured result". Nothing above it changes except by a dated, labelled
amendment. Route: [docs/agents/propose-and-measure.md](../docs/agents/propose-and-measure.md). Previous note:
[sdm03-default.md](sdm03-default.md), section "O1 on scan 4" and the coordinator's decision. Host: **nash**. Every
job runs `nice -n 19 ionice -c3` through the main checkout's `tools/heavy_lock.py run --slots N --mem G`. Run root:
`nash:~/rang-data/outputs/automask-cycle-20261118`.

## 1. The finding

With `-auto-mask 6 -auto-threshold 0.5 -mgain 0.9 -channels-out 8 -join-channels -fit-spectral-pol 2` (sdm03's
SDa) on ESO137 scan 4, GeMClean declares the auto-mask threshold reached in major iteration 3, at a mask level of
1.05 mJy. WSClean 3.7 declares it in iteration 4, at 0.51 mJy. GeMClean's residual excess then comes out at
1.36 × WSClean's (sdm03's O1 fails). On scan 14 both finish in iteration 4 and agree (P ratio 0.976). The seen
pilot finishes in iteration 3 under GeMClean; WSClean was not run there.

## 2. Code reading (done before the freeze; no run)

GeMClean (`core/src/gemclean/mask.rs` `AutoState::begin` / `end_stage`; `joined.rs` `joined`, the stage loop) was
compared with radler 76fe4474, the radler inside WSClean 3.7 (`radler.cc` `Radler::Perform`, `SetAutoMaskMode`;
`algorithms/generic_clean.cc` `ExecuteMajorIteration`; `math/gain_calculations.h` `CalculateContinuedLoopGain`;
`image_set.cc` `GetLinearIntegrated`). The source read is `~/Build/tmp/20261109-g4-wsclean-src` in WSL, at
WSClean `4f395b2` ("3.7 release"):

| step | radler 3.7 | GeMClean | same? |
| --- | --- | --- | --- |
| σ | `MedianAndStdDevFromMAD` of the weighted linear integrated residual, every major iteration, before the minor loop | `radler_stddev(residual_int)` at `begin`, where `residual_int` is the channel-weight-share sum | yes |
| phase-1 threshold | `max(σ·auto_mask (+ bias if squared joins), abs_auto_mask, abs_threshold)` | the same (no squared joins) | yes |
| final threshold | `max(σ·auto_threshold, abs_threshold)` | the same | yes |
| first-loop stop | while \|peak\| > max(threshold, (1 − mgain)·\|initial peak\|) | the threshold test first, then the peak rule `(1 − g)·first_peak` with `g` = mgain (`auto_mask_mgain`: `PeakFraction` only) | yes |
| "another iteration" | `mgainReached && didWork && !negative && !finalThresholdReached` | `stage_stop == PeakRule && did_work` | yes (≤ against <) |
| the switch | `!another && !finished` finishes the mask, and the same iteration continues at `1 − (1 − mgain)/(1 − achieved)` to the final threshold | `end_stage`, the same | yes |
| phase-1 continuation | at mgain inside the mask, at the phase-1 threshold; its result does not set "another" | the same | yes |
| Högbom mask | the nonzero model pixels at the first `SetAutoMaskMode(…, true)`, never rebuilt | `models.mask()` at the first use, never rebuilt | yes |
| the stop threshold in phase 1 | not used: the minor loop's threshold is the 6σ mask level | the same | yes |

So the rule reads the same. The archived reports differ in its **input**, the first-loop start peak of
iteration 3 (GeMClean `image-report.json` `peak_start`; WSClean's "Next major iteration at", which is 0.1 × the
start peak):

| case | GeMClean start peak / 10 × 6σ | WSClean start peak / 10 × 6σ | finishing iteration G / W |
| --- | --- | --- | --- |
| scan 4, iteration 2 | 72.29 / 28.23 mJy | 76.2 / 28.4 mJy | – |
| scan 4, iteration 3 | **10.24 / 10.51 mJy** (finishes) | **15.4 / 10.9 mJy** (continues) | 3 / 4 |
| scan 14, iteration 3 | 13.90 / 11.40 mJy | 15.3 / 11.6 mJy | 4 / 4 |
| pilot, iteration 3 | 11.51 / 12.50 mJy (finishes) | not run | 3 / – |

Iteration 1 agrees to four figures: start peak 659.06 against 659.1 mJy, σ 1.1876 against 1.19 mJy. On scan 4
GeMClean's iteration-3 start is 2.6 % below the switch's edge. What WSClean's extra phase-1 iteration buys is one
more **unmasked** minor loop to 6σ ≈ 0.51 mJy (73,547 iterations). It is not a different mask: both build the mask
once, from iteration 1's model. sdm03's reading "WSClean builds a larger mask" is checked here (section 4, M3).

## 3. Hypotheses

- **H-rule**: GeMClean's switch predicate, σ or threshold differs from radler's in a way the reading missed
  (single against double precision, the peak's sign, the border, the mask in force at the start peak).
- **H-input**: the rule is the same. After a major cycle, GeMClean's exact residual has a lower peak than
  WSClean's. On scan 4 that puts iteration 3's start below 10 × 6σ. The cause is either:
  - **H-input-G**: a GeMClean inexactness upstream (spectral fit, model per channel, prediction); or
  - **H-input-0**: neither is wrong. radler's rule is a knife edge on the ratio start peak / threshold against
    1/(1 − mgain) = 10, and the two imagers' residuals differ by more than that margin.

## 4. Smallest case and measurements (frozen)

Data: ESO137 scans 4 (MAIN_1) and 14 (MAIN_6), sdm03's Sp state (`P/pilot.ms`, CORRECTED_DATA). sdm03's run root
was deleted on 2026-11-18 at about 17:10, during the first copy, so the state is **rebuilt** in this run root. It
uses sdm03's own chain (fetch, build, copy, `rang-core selfcal` with p1.yaml, state) at sdm03's driver commit
`c3d6bf72`, whose Rust is `aef6c48c`'s. Its extension was built on nash as
`f05fedef3e0bfc969…`; sdm03's was `959aae39…`, from the same source in another path. floor-5's pilot folder
(`--held`: cal2.ms, set A's mask, the pilot model) is copied into `inputs/held` first.

**Gate R (reproduction), before any new reading.**
- Every fetched object's SHA-256 equals sdm03's archived manifest (`manifest-MAIN_k-data.json`).
- With WSClean at SDa's settings, iteration 1's σ is 1.19 mJy and iteration 2's is 472.9 µJy (scan 4), to the
  log's three figures.
- With GeMClean at SDa's settings, iteration 1's σ is 1.187646e-3 Jy and its start peak 0.659061 Jy, within 1e-4
  relative.

A miss voids the reproduction (reported, not read as a result).

**Smallest case.** On scan 4, both imagers at SDa's settings with `-nmiter 2` (GeMClean also with `-nmiter 1`):
the final residual is then the start of iteration 3. The readings, on the MFS (weighted linear integrated)
residual images:

- **M1**: each residual's peak \|value\|, sign and position. Each residual's value at the other's peak position.
  σ by radler's MAD.
- **M2**: the integrated model flux and the 20 brightest model pixels per output channel, against each other.
- **M3**: the number of nonzero model pixels after iteration 1 (the mask's support), for both.
- **M4**: GeMClean's iteration-3 start peak and 6σ, reported against 10 × 6σ.

## 5. Oracle and tolerance (frozen)

Oracle: WSClean 3.7, nash's `/usr/bin/wsclean` ("WSClean version 3.7 (2026-02-16)"). It runs with sdm03's W-SDa
argv, plus `-nmiter` for the smallest case.

**T1 (the switch)**: the same finishing iteration as WSClean on scans 4 and 14.
**T2 (the closing check, sdm03's O1)**: P_gem ≤ 1.25 × P_wsc on scans 4 and 14, by sdm03's scorer (`floor6_tests`
`score`) against the same A0.
**T3 (no movement)**: the existing GeMClean gates pass (`python tools/check_all.py`, full, under the lock).

## 6. Decision rule (frozen)

Precedence: the first that holds.

1. **Incomplete**: gate R fails, or the smallest case does not run on scan 4 before 22:00 SAST. Report what ran.
2. **Defect in the rule (H-rule)**: a difference in σ, a threshold or the predicate is found that alone moves
   GeMClean's scan-4 finishing iteration to WSClean's. Fix it in Rust with a unit test that reproduces radler's
   behaviour on the triggering input. Accept the fix only with T1, T2 and T3.
3. **Defect upstream (H-input-G)**: M1/M2 trace the lower peak to a GeMClean departure from WSClean's documented
   semantics (the spectral fit, the per-channel model or its prediction). Fix it there under the same T1-T3, or
   record it as a follow-up if it cannot be fixed and verified before the hand-back.
4. **Null (H-input-0)**: the rule is the same, and no GeMClean departure is found that explains the peak. The
   finishing iteration follows the residual, and sdm03's O1 failure is a property of radler's rule at a 2.6 %
   margin, not a GeMClean defect.

**Not a fix**: changing GeMClean's comparison, σ or margin so that it reproduces WSClean's cycle count on these
scans. That would leave radler's semantics and tune to two scans.

## 7. Not claimed

No novelty and no performance claim. Not tested: other fields, multiscale (its own per-scale masks), squared
joins, and `-local-rms`.

## Measured result

(Not yet run.)
