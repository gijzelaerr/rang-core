<!-- SPDX-License-Identifier: MIT -->
# Rang: does GeMClean finish its auto-mask one major cycle early? (issue #36)

Status, 2026-11-18 21:00 SAST (amended after the measurement): **measured; outcome rule 4, null**, see "Measured
result". Frozen status, 2026-11-18 18:40 SAST: **proposed; nothing run.** This note was frozen before any reproduction run.
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

Measured 2026-11-18, 18:19-19:45 SAST (frozen runs) and 19:44-21:45 SAST (one post hoc run), host nash, run root `nash:~/rang-data/outputs/automask-cycle-20261118`
(removed after archiving). Archive: [results/automask-cycle/](results/automask-cycle/) (compare outputs `cmp/`,
imager logs, argv and GeMClean reports `small/`, the rebuild's logs `logs/`, `timing.tsv`, the driver scripts
`scripts/`, the post hoc residual probe `probe.json`). State rebuilt with sdm03's chain at `c3d6bf72` (worktree `automask-cycle-state`, extension
`f05fedef…`). Imagers: GeMClean from that worktree; WSClean 3.7 `/usr/bin/wsclean`. Every job 8 threads,
`nice 19`, `ionice -c3`, under the heavy lock.

**Outcome: rule 4, null (H-input-0).** Gate R holds, the rule reads the same (no H-rule difference), and the
lower GeMClean start peak traces to WSClean's iteration-2 first loop, which leaves residual above its own stop
level, not to a GeMClean departure (rule 3 does not hold). No code change.

### Gate R (holds)

| check | frozen value | measured |
| --- | --- | --- |
| fetched objects, SHA-256 against sdm03's manifests | equal | scan 4: 357 of 357 equal, 18,096,402,293 B; scan 14: 378 of 378, 18,121,223,938 B (`gate-r-manifests.json`) |
| WSClean σ, iterations 1 and 2 (scan 4) | 1.19 mJy, 472.9 µJy | 1.19 mJy, 472.9 µJy; start peak 659.06 mJy (`W-MAIN_1-n2`) |
| GeMClean σ and start peak, iteration 1 (scan 4) | 1.187646e-3, 0.659061 Jy (1e-4 rel.) | 1.187646e-3 Jy, 0.6590610902 Jy (n1 and n2) |

Beyond the gate: GeMClean's cycle start peaks and thresholds in the n2 runs are bit-equal to sdm03's archived SDa
reports, on scan 4 (0.6590610902255093, 0.07229122320785566 Jy) and on scan 14 (0.8912910291829735,
0.10047474686181436 Jy). G-MAIN_6-n2 started while scan 14's `state` stage was running; `state` does not write
`P/pilot.ms` (its mtime is from selfcal, 19:00:32), and the bit-equal peaks agree.

### Deviation 1 (2026-11-18 19:40, post hoc): `-nmiter k` does not stop at iteration k+1's start

Section 4 assumed the final residual of `-nmiter 2` is the start of iteration 3. It is not, in either imager:
iteration k's in-mask continuation is skipped when k is the last iteration. In radler (`radler.cc` `Perform`)
the `major_iteration_count` check sets `another_iteration_required` false before the continuation is reached.
GeMClean does the same: n2's cycle 2 is 14,635 components ending on the peak rule, against 17,245 ending on the
threshold in sdm03's full run. WSClean's n2 log has no continuation in iteration 2. So:

- the n2 residual is the residual after iteration 2's **first loop** and a major cycle, the same stage in both;
- the n1 model is the model after iteration 1's first loop. That model is the Högbom mask (radler builds it at
  the first `SetAutoMaskMode(…, true)`, the first continuation), so M3 on n1 is the mask support, as intended;
- no `-nmiter` reaches the iteration-3 start, so M4 is taken from sdm03's archived full runs.

### M1-M4 (no tolerance; T1-T3 apply only to a fix)

Positions are (y, x) array indices; WSClean's log prints x, y.

| reading | scan 4, n1 | scan 4, n2 | scan 14, n2 |
| --- | --- | --- | --- |
| GeMClean MFS residual peak | +65.97 mJy at (2048, 2045); WSClean there 63.78 | +7.340 mJy at (2358, 2043); WSClean there 7.366 | +10.30 mJy at (2025, 1940); WSClean there 10.05 |
| WSClean MFS residual peak | +70.00 mJy at (2047, 2060); GeMClean there 60.72 | **+22.89 mJy at (2045, 1970); GeMClean there 6.92** | **+24.50 mJy at (1980, 2158); GeMClean there 9.10** |
| radler σ (MAD), G / W | 820.7 / 821.3 µJy | 191.5 / 206.9 µJy | 212.6 / 224.8 µJy |
| rms of G − W | 36.3 µJy | 63.3 µJy | 73.0 µJy |
| model flux per channel, G / W (M2) | 29.756…16.547 / 29.709…16.512 Jy (+0.16 to +0.21 %) | 81.32…62.77 / 80.36…61.08 Jy (+1.2 to +2.8 %) | 79.90…58.10 / 79.29…56.95 Jy (+0.8 to +2.0 %) |
| nonzero model pixels, G / W / both (M3) | **1,527 / 1,520 / 1,068** | 5,940 / 5,670 / 4,120 | 4,655 / 4,596 / 2,822 |

- **The first loop's stop.** Each imager's iteration-2 first loop stops at 0.1 × its start peak: GeMClean
  7.23 mJy (scan 4) and 10.05 mJy (scan 14), WSClean 7.62 and 10.22 mJy. After the major cycle, GeMClean's
  residual is at that level. On scan 4: 0 pixels above 7.62 mJy and 63 above its own 7.23 mJy stop, peak 7.34
  (1.5 % over). On scan 14: 78 pixels above 10 mJy, peak 10.30 (2.5 % over). WSClean's is not: **1,096 pixels above its own 7.62 mJy stop on scan 4 (112 above
  15 mJy), 1,837 above 10 mJy on scan 14 (249 above 15 mJy)**. The scan-14 counts and the 63 come from an inline probe,
  not archived; `probe.json` re-reads scan 4's n2 residuals. Its log still says "Stopped on peak 7.61 mJy"
  and "10.22 mJy".
- **The sources.** On scan 4 the excess sits at four compact sources, (y, x) = (2046, 1970), (1980, 2109),
  (1973, 2159), (2033, 1969). After iteration 1's first loop the imagers agree there. Three of them have 61-65 mJy
  residual and 7×7 model sums within 5 %. (1980, 2109) has −6.4 / −6.6 mJy and no model in either. After iteration 2, WSClean's residual there is 15.2-22.8 mJy and GeMClean's
  6.4-6.7 mJy. GeMClean has added 17-108 mJy more model per 7×7 box: 571 against 464 mJy at (2046, 1970),
  28.7 against 11.7 mJy at (1980, 2109). The model sums come from an inline probe on nash, run outside the
  lock and not archived. The residuals are re-read by `scripts/probe.py` (`probe.json`).
- **The iteration-3 start.** WSClean's iteration-3 start peak in sdm03's full run is 15.42 mJy at x 2109,
  y 1980, the second of those sources. No model there after iteration 1, so it lies outside the Högbom mask and
  iteration 2's in-mask continuation does not touch it. Its n2 residual there is 15.16 mJy (WSClean) and
  6.50 mJy (GeMClean). WSClean's 15.4 mJy start peak is that source, left by iteration 2's first loop.
- **M2.** Of the 20 brightest model pixels (by GeMClean's channel mean), 12 agree within 0.1 % after
  iteration 1 (largest difference 13 %) and 8 after iteration 2 (largest 18 %). Channel-mean model flux:
  23.151 against 23.111 Jy after iteration 1, 72.043 against 70.717 Jy after iteration 2. Of that 1.33 Jy,
  0.25 Jy is in the four sources' 7×7 boxes. The rest is spread over GeMClean's 1,526 extra components
  (26,437 against 24,911) and was not localised.
- **M3, the mask.** The two Högbom masks are the same size (1,527 against 1,520 pixels) and share 1,068 (70 %).
  sdm03's reading "WSClean builds a larger mask" is not supported. The masks differ in where 30 % of the
  components fell, not in size.
- **M4** (from sdm03's archive, since no run here reaches the iteration-3 start). GeMClean's start peak is
  10.236 mJy against 10 × 6 × 175.19 µJy = 10.511 mJy (ratio 0.974). WSClean's is 15.42 mJy against
  10 × 6 × 182.19 µJy = 10.93 mJy (ratio 1.41). With WSClean's σ, GeMClean's edge rises to 10.93 mJy and it
  still finishes, so σ does not decide it (rule 2). Here, before iteration 2's continuation: GeMClean 7.340 mJy
  against 10 × 6 × 191.5 µJy = 11.49 mJy.

### Rule by rule

1. Incomplete: no. Gate R holds, and the smallest case ran on scan 4 by 19:35.
2. H-rule: no. σ agrees to WSClean's three printed figures in iteration 1 and to 0.5 % in iteration 2
   (470.46 against 472.9 µJy).
   The iteration-3 σ difference (175.19 against 182.19 µJy) moves GeMClean's edge the wrong way to change the
   outcome. The predicate and thresholds read the same (section 2).
3. H-input-G: no. M1/M2 trace the 50 % gap in iteration-3 start peaks (10.24 against 15.42 mJy) to iteration 2's
   first loop. GeMClean's ends at its stop level, as radler's documented rule (`-mgain`) says it should.
   WSClean's ends with 2-3 × its stop level left at sources it never saw. That is a WSClean inexactness, not a
   GeMClean departure from WSClean's documented semantics in the spectral fit, the per-channel model or the
   prediction.
4. **Null: holds.** The finishing iteration follows the residual. sdm03's scan-4 O1 failure is radler's rule
   at a 2.6 % margin (10.24 against 10.51 mJy), fed by a residual that differs because WSClean's first loop is
   inexact. It is not a GeMClean defect.

### Mechanism (post hoc: a source read, then one run)

Radler's first loop uses the sub-minor optimisation by default (`-no-fast-subminor` turns it off).
`SubMinorLoop::findPeakPositions` takes, at the loop's start, the pixels whose integrated residual is at least
the loop threshold (here 7.62 mJy). `Run` cleans and tracks only those pixels, and the stop peak it returns is
theirs. `CorrectResidualDirty` then updates the full image by FFT. `GenericClean::ExecuteMajorIteration`
rescans the full image only when the subset returned no peak (`generic_clean.cc`, after the sub-minor call).
So a pixel outside the starting subset that is above the stop at the end is seen only in the next iteration.
Inside the subset, the tracked values are the PSF subtraction that `CorrectResidualDirty` then applies, so a
pixel that ends above the stop must have been outside the starting subset (an inference from the source).
On scan 4 that is 1,096 pixels. GeMClean's minor loop searches the whole working map (per-tile maxima), and
its resyncs restore the exact residual, so after the major cycle its residual is within 1.5 % of its stop. How the four sources fell
below 7.62 mJy at iteration 2's start and rose above it was not traced.

Post hoc test (not in section 4): WSClean n2 on scan 4 with `-no-fast-subminor` (`W-MAIN_1-n2-nofs`).
It ran 19:44-21:45 (7,229 s against 384 s with the optimisation). The arms are on scan 4's
iteration 2, after the first loop and a major cycle:

| | WSClean default | WSClean `-no-fast-subminor` | GeMClean |
| --- | --- | --- | --- |
| iteration-2 σ | 472.9 µJy | 471.42 µJy | 470.46 µJy |
| iteration-2 start peak | 76.17 mJy | 73.33 mJy | 72.29 mJy |
| first-loop stop | 7.62 mJy | 7.33 mJy | 7.23 mJy |
| MFS residual peak | +22.89 mJy | −7.45 mJy | +7.34 mJy |
| pixels above 7.62 / 10 / 15 mJy | 1,096 / 467 / 112 | 0 / 0 / 0 | 0 / 0 / 0 |
| residual at the four sources | 15.2-22.8 mJy | 6.2-7.1 mJy | 6.4-6.7 mJy |
| radler σ of the MFS residual | 206.9 µJy | 193.8 µJy | 191.5 µJy |
| rms of G − W | 63.3 µJy | 34.3 µJy | – |

Without the sub-minor optimisation, WSClean's iteration-2 residual matches GeMClean's: nothing above 7.62 mJy
(peak |7.45| mJy, 1.6 % over its own 7.33 mJy stop), the four sources at 6.2-7.1 mJy, and the G − W rms halved. Iteration 1 is unchanged (σ 1.19 mJy, start
peak 659.06 mJy). The excess is radler's default sub-minor loop, not a property of WSClean's clean as
documented. How WSClean `-no-fast-subminor` would switch on scan 4 was not run: its full run is about 2 h at
this cost, and E3-A held nash from 21:45. Whether it would then finish in iteration 3, as GeMClean does, is
not known. The probe ran on glacier under its lock, on the three MFS residuals copied from nash at
`nice 19` / `ionice -c3`. nash was held exclusively by E3-A from 21:45.

### Not done

T1-T3 were not run: they gate a fix, and there is none. Scan 14's n1 was not run; its M3 is after iteration 2.
The first three WSClean launches exited with rc 255 within 3 s at 19:06-19:21. They were relaunched and ran;
the first logs were overwritten, so the cause is not diagnosed. The likeliest cause is a table lock taken by
the `state` stage then starting, but that was not checked. scan 14's first `fetchmeta` exited 1 (a
`FileExistsError` on a linked subtable when both scans were fetched at once) and passed on retry. Both are kept
in `timing.tsv`.

What touched nash after E3-A took it exclusively (21:45:02 SAST, 8 s after the post hoc run ended at 21:44:54;
E3-A's exclusive ticket may have waited on that run): a 201 MB tar read of three FITS files at 21:53 (`nice 19`,
`ionice -c3`, outside the lock); then, about 22:05, removing the worktree `automask-cycle-state`,
`~/Build/tmp/20261118-automask-cycle` and the 179 GB run root (`rm` at `nice 19` / `ionice -c3`, 27 s wall,
14.7 s system). A 1-slot probe queued at 21:47 was cancelled before it ran. Three `tail -F` watchers of the
removed `driver.log` from the earlier session (pids 1630895, 1649882, 1662781) are still running; they were not
this session's and were left.

## For the coordinator

- **Verdict: rule 4, null; no code change.** GeMClean's auto-mask switch is radler 3.7's. Gate R holds.
- **Rule or upstream departure?** The switch is radler's knife edge (start peak / 6σ against 1/(1 − mgain) = 10).
  GeMClean lands 2.6 % under it (10.24 against 10.51 mJy). WSClean's start peak is 50 % higher (15.42 mJy), and
  M1/M2 put that gap on WSClean's side: its default sub-minor first loop in iteration 2 stops at 7.62 mJy but
  leaves 1,096 pixels above it (peak 22.9 mJy at four sources). The edge picks GeMClean's side; the gap is not a
  GeMClean departure.
- **M1** (scan 4, after iteration 2's first loop): WSClean peak 22.89 mJy, GeMClean 6.92 there; GeMClean peak
  7.34. **M2**: GeMClean model +1.2 to +2.8 % per channel, 0.25 of the 1.33 Jy at the four sources. **M3**: masks
  of 1,527 and 1,520 pixels, 1,068 shared, so "WSClean builds a larger mask" does not hold. No tolerance applies
  (T1-T3 gate a fix only).
- **Post hoc:** WSClean `-no-fast-subminor` leaves 0 pixels above 7.62 mJy, the sources at 6.2-7.1 mJy (GeMClean
  6.4-6.7), G − W rms 63 → 34 µJy, at 19 × the wall. Its full-depth switch was not run.
- **Deviation:** `-nmiter k` skips iteration k's continuation in both imagers; M4 is from sdm03's archive.
- **Decide:** (1) whether WSClean oracle runs that compare cycle counts or residual excess use
  `-no-fast-subminor`; (2) copying radler's subset loop into GeMClean (recommended no; section 6 calls it not a
  fix); (3) close #36 as null and decide whether to re-read #13: its O1 failure rests on the oracle's excess,
  and sdm03 records the outcome as null without O1.
- nash during E3-A (from 21:45:02): one 201 MB read and the cleanup, at `ionice -c3`. Three earlier-session
  `tail -F` watchers (1630895, 1649882, 1662781) were left running.

## Coordinator decision (2026-11-18)

- **Outcome stands as frozen: rule 4, null; no code change.** #36 closes as null.
- **(1) Oracle setting, from now on:** WSClean oracle runs whose measure compares major-cycle counts, or residual
  excess above a stop, add `-no-fast-subminor`; timing runs keep WSClean's default. Archived oracle runs are not
  rerun for this. Post hoc for every earlier comparison.
- **(2) No:** GeMClean does not copy radler's subset loop. It would reproduce an oracle artefact, not fix a defect.
- **(3) #13 stays closed** with SDm03 "not yet". Its O1 failure on scan 4 rests on the default oracle's residual
  excess, so O1 as run there is not evidence against SDa. The coordinator re-reads #13 as "not yet, O1 not
  informative", not as a pass. Any second look at SDa as default is a new frozen note that uses setting (1) and
  the unspent reserve scan 12.
