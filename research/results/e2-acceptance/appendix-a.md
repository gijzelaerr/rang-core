## Appendix A. A0's gates, verbatim

Copied by `research/results/e2-acceptance-scripts/e2_appendix_a.py` from
[a0-acceptance.md](../../a0-acceptance.md) at `a373a4c`, lines as given; nothing
edited. Section and table references inside are A0's.

<!-- A0 lines 249-294: section 5, common rules -->

## 5. Common rules for every gate (frozen)

1. **Order.** Every tolerance here is fixed now. A later task may tighten a
   gate for its own stage, never loosen one. A note written before a
   comparison may only add measures.
2. **One shot.** Each E2 leg runs once, in full, with the configuration
   committed beforehand. Its result is reported as frozen, pass or fail.
3. **Same inputs for every arm.** Arms are rang, the oracle chain and CARACal:
   - same channel and time selection, averaging, model column and weights;
   - LUNO weights over-state the noise 10–60 times, and ESO137 has zero
     cross-hand weights, so E2 and E3 use **`weights: uniform`** in every arm,
     as CARACal's shipped `prep.specweights: uniform` does;
   - `calwt=False` in every apply;
   - E2-N, when it exists, also runs `weights: as_is`.
4. **Noise-relative measures** use noise measured from adjacent-channel
   differences of the data (`examples/check_luno_noise.py`'s method), never the
   weights.
5. **Gauge.** Gains are compared through gauge-free products: per cell
   `P = DATA / CORRECTED_DATA` on the parallel hands, and the composite applied
   Jones on all four (O-CASA's method). Solutions alone are compared only for
   terms with a fixed reference (K, KCROSS, Xf, Df with refant).
6. **Image comparisons** run through one scorer. Fixed in advance:
   - the off-source mask: the mean of the arms' images above 5σ, dilated by 2
     beams;
   - one common restoring beam;
   - the threshold rule: automatic masking at 5σ, then cleaning to 3σ, σ the
     MAD of the residual. This holds for every imager.

   Nothing is chosen after seeing an arm, unlike `gemclean-heldout.md`'s
   threshold.
7. **Cost.** Wall time is end to end and per stage. Peak memory:
   - processes on the host: `/usr/bin/time -v`;
   - containers: the cgroup's `memory.peak`, read inside the container before
     exit, because `time` around `docker run` measures only the client.

   Every timing run has the host to itself and takes the heavy lock.
8. **Versions pinned:**
   - CASA 6.7.6.14 (`rang-o-casa`) and WSClean 3.7 (`rang-wsclean-native`);
   - QuartiCal 0.2.7 (`rang-formats-oracle:20261030`);
   - Tricolour 0.2.1, CARACal's strategies at `8f7bb363`; a Tricolour image
     must be rebuilt from `history/tools/flagging/`, since
     `rang-flagging:local` is gone;
   - CARACal at `8f7bb363876f5f0daecbf2167c36bb597c7e5160`.

   A newer upstream release is reported beside, never substituted.


<!-- A0 lines 297-305: 6.1, gates 1 to 3c -->

### 6.1 Finish-line gates 1 to 5

| Gate | Measure, and how it is computed | Pass | Reason | A failure means |
| --- | --- | --- | --- | --- |
| **1 One command** | `rang-core run config.yaml my.ms` on the E2-A and E2-B Measurement Sets, from a clean venv with the wheel from public PyPI (or the tagged wheel before upload), config committed before the run | exit 0; every stage ran; no hand edit; receipt complete | the gate's wording | a stage crashed or needed a hand step: fix, then rerun on the reserve (6.5) |
| **2 Written back** | (a) FLAG backup restored, then the FLAG and FLAG_ROW hashes compared with the input's; (b) casacore opens every written column and table; CASA `listobs`, `flagmanager(mode='list')` and `applycal` (with rang's tables, on a copy) run; WSClean images CORRECTED_DATA and MODEL_DATA with `-niter 0`; QuartiCal reads the MS through dask-ms; (c) FITS headers parse with astropy WCS | (a) hashes equal; (b) every call exits 0, and CASA's `applycal` with rang's tables equals rang's own apply within class C; (c) WCS valid | exact round trip is the only meaningful bound for storage | a writer or schema bug: blocks release |
| **3a Flags vs Tricolour** | rang's flagging step against Tricolour 0.2.1 with the same strategy file, input flags and chunking, on the leg's data | 0 cells differ. If W3 must chunk differently from Tricolour, ≥ 1 − 1e-4 of cells agree and every differing cell lies within one window of a chunk edge | the port is flag for flag on four controls (`core-d-tricolour.md`, run `-02`) | a porting error, or a chunking effect if every difference sits at an edge |
| **3b Solutions vs CASA and QuartiCal** | per term, classes A, B, C and T of C1 (restated in 6.2) on the leg's data with matched settings | every term within its class | measured agreements, below | an estimator difference: located by term, not averaged away |
| **3c Images vs WSClean** | dirty images with matched gridder accuracy; cleaned images through the scorer; MODEL_DATA against WSClean `-predict` | dirty L∞ ≤ 1e-6 of the peak. Cleaned: compact-source flux ratio median within 0.5 %, robust scatter ≤ 1 %; Q/Q₀ within 0.5 %; off-source \|model\| ≤ 1.6 × WSClean's better loop; spectral index (sources ≥ 50σ) median \|Δα\| ≤ 0.05; each Stokes Q, U, V image of an unpolarised source no worse than WSClean's by 1.2 ×. MODEL_DATA per cell ≤ 1e-5 of the peak visibility at gridder ε 1e-6 | measured: dirty 6.5e-8 to 2.2e-7 of the peak, compact ratios 0.24–0.31 % scatter, Q/Q₀ differences 0.2–0.4 %, worst false-flux ratio 1.37 (`gemclean-heldout.md`) | an imager difference: G-task bug or a default that needs settling (G7) |

<!-- A0 lines 309-340: 6.2, stage tolerances -->

### 6.2 Stage tolerances (C1's classes, adopted)

From the C1 draft (`research/c1-calibration-chain.md`, branch `fp-c1-chain`),
restated so this note stands alone:

- **A**, same algorithm as QuartiCal 0.2.7: flags exact; complex entries and
  products ≤ 1e-6; iteration counts equal. Measured 1.4e-15 (`core-phase2.md`).
- **B**, CASA's estimator differs: composite products' relative difference has
  median ≤ 7e-4 and p95 ≤ 3e-3. The held-out parallel-hand MSE is within 2e-4
  relative. Measured on matched intervals: 4.9e-4 and 2.0e-3 (fixture),
  7.5e-5 and 2.1e-4 (slice) (`l5c-casa-gaincal`).
- **C**, apply: per cell ≤ 1e-6 relative, or ≤ 11 float32 epsilons of the
  cell's largest correlation; flags exact (measured up to 10.3 ε,
  `dfio-formats.md`).
- **T**, against simulated truth: noise-free products within 1e-5. With noise,
  each term's median error is at most 3 standard errors of the expected thermal
  error.

Term limits against CASA:

- **K:** |Δτ| median ≤ 0.01 ns, p95 ≤ 0.03 ns.
- **KCROSS:** |Δτ| ≤ 0.02 ns.
- **Gpol phase:** median ≤ 0.1°.
- **Xf:** median ≤ 0.5°, p95 ≤ 2° per channel.
- **Df, gauge-free combinations:** median ≤ 1e-3, p95 ≤ 5e-3.
- **F (`fluxscale`):** per-field flux and scale factors within 1e-3.
- **`setjy` and `manual` models:** 0 ulps (FS1).
- **Polarised model rows:** ≤ 1e-6 of |I|.

**On E2-B real data the class B limits apply only to the half's own solve.**
Transfers are judged by 6.3.


<!-- A0 lines 355-398: 6.3, E2-A and E2-B -->

**E2-A: ESO137 ms1, Stokes I, raw phases.**

- **Data:** primary scans 9 and 11 bracket target scan 10. All 4,096 channels
  for flagging and calibration, then averaged by 8 to 512 channels for imaging,
  identically for every arm.
- **Image:** 4,096 × 3″, Briggs 0.5, Stokes I, `-channels-out` 8 with a
  2-term spectral fit, the threshold rule of section 5 (item 6), no hand
  mask. This matches
  the pilot geometry.
- **Field limit:** at 512 channels bandwidth smearing reaches β ≈ 1 at the
  field edge, so the scorer uses the inner 0.7° radius.
- **Oracle chain:** CASA K, G, B by CARACal's sequence (6.4), then WSClean 3.7.
- **Second reference:** the publisher's `GKB-net` gains, compared only after
  the frozen run.

| Measure | How | Pass | Reason |
| --- | --- | --- | --- |
| Flags | 3a | 3a | – |
| Solutions | K, G, B against CASA on these scans | class B on composite products; K by its limit | – |
| Flux scale | solve on scan 9 only, apply to scan 11; 1934−638's Stokes I per 100 MHz against SR2016 | median within 2 % in every bin with ≥ 10 % unflagged | O-CASA: corrected I = 1.0003 × model; models differ by up to 1 % across the band |
| Target, compact sources | ≥ 10σ isolated sources: flux ratio rang/oracle | median within 1 %, robust scatter ≤ 1.5 % | 3c's imager bound plus calibration differences |
| Target, noise and dynamic range | off-source rms; peak/rms | rms ≤ 1.2 × the oracle's; dynamic range ≥ 0.8 × | parity, not thermal: the pilot's floor is 40–60 × thermal in every imager |
| Self-calibration | rms before and after; gains | after ≤ 1.02 × before; class B against QuartiCal on the same model | self-calibration must not degrade |

**E2-B: LUNO scans 17 to 20, full polarisation, calibrators.**

- **Stages:** flag, then the CARACal full-Stokes chain. That is K, G, B on
  1934−638 (scan 18); G and F on 1830−211 (scans 19–20); then Gpol, KCROSS
  and Xf on 3C 286 (scan 17), and Df on 1934−638.
- **Images:** 2,048 × 2″, robust 0, 8 joined channels, joined polarisations,
  for each field.
- **Feed angle:** `feed_angle_rotation: -90`. The store's RECEPTOR_ANGLE is 0,
  and CARACal's shipped config rewrites it to −90°, so rang uses the same frame.
- **Not imaged:** the Moon target.

| Measure | How | Pass | Reason |
| --- | --- | --- | --- |
| Flags | 3a | 3a | – |
| Own-half solutions | every term against CASA on scans 17–20 | 6.2 | – |
| 3C 286 parity | p and χ per 100 MHz bin (1.0–1.65 GHz, ≥ 10 % unflagged) from rang's and CASA's calibrated scan 17, sky frame | \|Δp\| ≤ 0.1 point, \|Δχ\| ≤ 0.5° | matched solves on the same data |
| **3C 286 transfer** | apply the development half's B, KCROSS, Xf and Df (scans 1–2) with per-scan G to scan 17, which sits 43° away in parallactic angle | at 1.3–1.5 GHz: p ∈ [9.0, 10.1] % and \|χ − 33.1°\| ≤ 7°; both arms reported | p spans 9.30 (MeerKAT), 9.5 (VLA), 9.8 (CARACal model) and 9.8–9.9 in the publisher's data; for χ, a 2 rad m⁻² change in ionospheric RM is 5.3° at 1.4 GHz, plus 1.7° for calibration. A sign error would move χ by about 87°. **Not circular:** Xf was solved on another scan |
| **1934−638 leakage** | dev-half Df applied to scan 18 (43° further in parallactic angle than scan 2); the peak of the Q, U and V MFS images over I | ≤ 0.3 % | the publisher reaches ≤ 0.08 % in sampled tiles; the transfer allows four times that |
| 1830−211 | I, p, χ against CASA after the full chain | flux within 1 %; \|Δp\| ≤ 0.1 point; \|Δχ\| ≤ 1° | parity only: the source is variable and its own polarisation is not a standard |


<!-- A0 lines 498-560: 6.5 and 6.6, failure rules and amendment 1 -->

### 6.5 Failure, retry and reporting

- **E1 failure:** a bug, located with truth. It is fixed, and E1 reruns; E1 is
  not held out.
- **E2-A failure:** recorded as frozen. After a fix, E2-A runs once on the
  reserve (scans 12, 11 and 13), reported as the second attempt beside the
  first.
- **E2-B failure:** recorded. There is no reserve, because both 3C 286 scans
  are used. A rerun after a fix is labelled "seen". The polarisation claim of
  v0.2.0 then rests on E1 plus the labelled rerun.
- **E3:** any outcome is reported; a "worse" reading goes into the release
  notes.
- **E2-N (native):** the same gates when the data exist; v0.2.0 states it is
  open.

### 6.6 Amendment 1 (2026-11-05, after review, before any run)

Added after the first commit of this note (`8285010`) and before any E run.
The text above is unchanged; where it conflicts, this section wins.

1. **3C 286 transfer, gain mode.** In E2-B's "3C 286 transfer" row and its
   parity row, the per-scan gain on scan 17 is **phase-only**
   (`calmode='p'`, `parang=True`), as CARACal's own `Gpol1`. Amplitudes come
   from the 1934−638 solve (scan 18; for the transfer, scan 2), interpolated
   as CARACal's crosscal applies them to xcal.
   - Reason: an amplitude-and-phase G solved against the polarised model forces
     XX/YY to (I+Q′)/(I−Q′). That would impose the model's Q and make p and χ
     partly circular.
   - The CASA arm uses the same modes. If CARACal's shipped chain solves an
     amplitude on 3C 286 anywhere (crosscal applies to xcal only), the E3-B
     report states which step.
2. **Calibrator models, frozen per leg.** MODEL_DATA is written once per leg by
   the core (C3) and copied to the rang and oracle arms.
   - **1934−638:** the SR2016 point model (`setjy`-equal, FS1) for E2-A and
     E2-B and for the flux-scale check.
   - **3C 286:** CARACal's NRAO `manual` model (`nrao_xcal.yml`: 14.7172 Jy at
     1.47 GHz, spix [−0.4507, −0.1798, 0.0357], p 9.8 %, χ 0.575959 rad,
     RM 0).
   - **1830−211:** no model; it is solved as the secondary with
     `smodel=[1,0,0,0]` and `fluxscale`, as CARACal does.
   - CARACal's E3 arm keeps its own `set_model` (`meerkat_skymodel: true`, the
     1934−638 lsm). That difference is reported, since O-CASA measured that the
     model choice alone moves the parallel-hand MSE by about 12 %. A second
     rang E3 arm using the same lsm through `predict_components` is run and
     reported beside it, so that model and method can be separated.
3. **Resources.**
   - **Disk:** arms run one after another. Each arm's MS copy is deleted once
     its numbers, tables and images are archived. At most one 480 GB E2-A copy
     and the input exist at a time.
   - **Memory:** E2-A runs after G2. If G2's measured GeMClean peak at 512
     channels exceeds 24 GB, every arm of E2-A and E3-A images at 256
     channels (×16), and the scorer radius shrinks to 0.5°. The choice is made
     on G2's number, before E2-A's data are opened.
4. **Rule 6 (thresholds) scope:** rule 6 binds rang and the oracle chain in E2.
   In E3, CARACal runs its shipped imaging (`cleanmask_thr 10, 6`,
   `clean_cutoff 0.5, 0.5`). Rang's E3 arm uses rule 6 (its default), and the
   difference is reported.
5. **Estimated sizes:** section 8 measured ms1 primary MAIN_4 and target
   MAIN_4. MAIN_5 and MAIN_6 (primary) and MAIN_5 (target) are **estimated**
   equal; the LUNO sizes are measured per group.
6. **The ms1 primary held-out check** is done (section 4, prior touches): only
   MAIN_0 and MAIN_1 were read before. E2-A keeps scans 9, 10 and 11.
