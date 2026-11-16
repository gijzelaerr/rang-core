# Rang: a close-to-threshold stop for GeMClean (issue #28)

Status at freeze, 2026-11-16: **proposed; nothing built or run on this branch.** Branch `gemclean-stop28`
from main `d2013ea`. Results go under "Measured result"; nothing above it changes except by dated, labelled
amendment. Route: [docs/agents/propose-and-measure.md](../docs/agents/propose-and-measure.md).

## 1. Gap and hypothesis

GeMClean's default rule (`MeasuredStale { rho: 1, g: 0.95, floor: 0.01 }`) runs until the exact peak after a
major cycle is below the threshold `T`. The last cycles hand back exact peaks just above `T` and hold few
components. On the archived default runs (`D:\rang\outputs\20261103-stale-floor`, the `-f0.01` reports, Linux
build), the last cycles start at, for `T` = 100 µJy:

| sky | cycles | last cycles: components / starting exact peak µJy |
| --- | ---: | --- |
| S1 | 5 | 21,033 / 150.24, 195 / 101.25 |
| S2 | 5 | 15,484 / 137.51, 77 / 100.84 |
| S3 | 4 | 14,932 / 175.35, 91 / 101.34 |
| H1 | 6 | 959 / 111.83, 17 / 100.15 |
| H2 | 6 | 573 / 106.00, 35 / 100.16 |
| H3 | 8 | 19,824 / 138.04, 648 / 102.59, 41 / 100.16, 1 / 100.01 |
| H4 | 5 | 709 / 110.71, 7 / 100.08 |

On the pilot (`cal2`, `cal3`): A at 3 mJy 982 / 3.1927, 8 / 3.0033, 4 / 3.0001 mJy; B at 3 mJy 413 / 3.1784;
A at 1 mJy 8,556 / 1.1777, 511 / 1.0129, 28 / 1.0008, 9 / 1.0002, 1 / 1.0001 mJy.

**Hypothesis.** Accepting an exact post-major peak below `(1 + ε) T` as done saves at least one major cycle
(one degrid and grid pass) per run on average on new skies, at false flux within 1.1 × the default's and
within the earlier WSClean tolerance.

**Not claimed.** No gain over WSClean, no novelty, no speed claim: cycles are the cost measure, and no
exclusive timing hold is asked for. A novelty reading is reported only under the rule of §6.

**Literature and state of the art.** WSClean 3.7 (`-mgain`, `-threshold`, the plain and fast loops) is the
oracle, as in [gemclean-heldout.md](gemclean-heldout.md). WSClean has no tolerance on its threshold: its plain
loop stops when a minor loop reaches the threshold and leaves the revealed peak above it (114.5-121.8 µJy on
H1-H4). A tolerance on the final acceptance is an ordinary engineering rule, not new. Earlier mentions here:
[clean-overview.md](clean-overview.md) decision 4, [opportunities-2026-11-13.md](opportunities-2026-11-13.md)
H; never built or tested.

## 2. The rule (frozen)

- New `Settings` field `stop_tolerance: f64` (`ε ≥ 0`), command line `-stop-tolerance <ε>`, default 0.
- **It applies only to the acceptance of the exact peak at the top of each major cycle** in
  `gemclean::run_masked` (the dirty image, or the exact residual after the previous major cycle). The run
  ends with `StopReason::Threshold` when `|peak| < (1 + ε) · T_eff`, `T_eff` being that cycle's effective
  threshold (the larger of `-abs-threshold` and `-auto-threshold` × σ, as now). The minor cycle's own test
  `|r| < T` and every hand-back rule are unchanged.
- With `ε = 0` the existing comparison runs untouched (the new test is a separate branch), so the output is
  byte-identical to main, `report.json` included: `cycle_stop` keeps its Debug string and the new value is
  written to the report only when nonzero.
- Paths: it applies wherever `run_masked` runs without the automatic mask (Stokes I, separate
  polarisations, separate channels, `-fits-mask`). A nonzero `-stop-tolerance` with `-auto-mask`,
  `-multiscale`, `-join-channels` or `-join-polarizations` is refused with an error: those loops have their
  own stop and are not tested here.
- One arm only. The issue's second clause (a floor on a cycle's predicted component count) is not built: no
  quantity computed before a cycle predicts its count, and a second arm would need its own verdict.

**Consequence.** A run with `ε` is the default run cut after its first major cycle whose result is below
`(1 + ε) T`: the earlier cycles, picks and model are the default's. The exact inner residual peak at the end is
below `(1 + ε) T` instead of `T`.

**What the Lean results still cover** (`formal/RangFormal/StopRule.lean`, [clean-theory.md](clean-theory.md)).
Every component is placed by the same minor cycle as before, so the per-step results are unchanged, each under
the hypotheses it already has: descent of the true misfit per step (`certified_step`, and the Gram-matrix
descent of clean-theory), the sign and size of the true residual at the pick (`pick_same_sign`,
`pick_fraction`, `pick_level`), and no flux on a pixel whose true residual stays below `(1 − κ) T`
(`no_flux_of_below`, `pixel_flux_le`). These need a valid error bound; the measured rule has none
(`measured_not_a_bound`), as before. What changes is not a Lean result: the run's exit condition becomes
`‖r‖_∞ < (1 + ε) T` on the exact residual. `peak_geometric`'s bound on the cycle count is vacuous after the
first cycle ([stop-rule-theorem.md](stop-rule-theorem.md) §6.5) and nothing here leans on it.

## 3. Choosing ε (development skies only)

Grid: ε ∈ {0.005, 0.01, 0.02, 0.05, 0.10}. **The chosen ε is the smallest value in the grid that removes at
least one major cycle on each of S1, S2 and S3, with false |flux| at most 1.1 × the default's, Q/Q_truth within
0.2 % of the default's and flux-weighted recovery no lower than the default's by more than 0.5 % on each.**
Measured from runs of this branch's binary (§5), scored by `examples/gemclean_bench_compare.py score`. If no
value qualifies, the outcome is null and nothing runs on held-out data.

From the archived traces (seen before this freeze) the expected choice is **ε = 0.02**: S1-S3 need ε above
0.0125, 0.0084 and 0.0134, so 0.01 does not clear S1 and S3. H3's 102.59 µJy does not enter the choice.

## 4. Data

All simulated with `examples/gemclean_bench_simulate.py`: MeerKAT 64 dishes, 2 h, 8 s dumps, 8 × 25 MHz, 20 µJy
natural noise, 2048 × 1.5″ (H3 4096 × 1.5″), Briggs 0.5, gain 0.1, abs threshold 100 µJy, `-niter 1000000`,
`-nmiter 1000`, as [gemclean-heldout.md](gemclean-heldout.md) §2.

1. **Development:** S1, S2, S3 (`D:\rang\outputs\20261102-gemclean\bench\data`).
2. **Seen, not blind (reported; predictions written here):** H1-H4
   (`D:\rang\outputs\20261103-gemclean-heldout\sim\data`), whose traces are published, so the cycle count under
   the rule follows from them; the bright-source cases of [stale-floor.md](stale-floor.md) not used to choose its
   floor (H1 + 30 Jy, H4 + 30 Jy and H3 + 100 Jy at the centre, S2 + 30 Jy 20 px off centre, regenerated with
   `examples/stale_floor_add.py`); the pilot, A at 3 and 1 mJy and B at 3 mJy
   (`D:\rang\outputs\20261103-gemclean-heldout\real\cal2.ms`, `cal3.ms`, 4096 × 3″, as that note §6).
   **Predictions at ε = 0.02 from the archived traces** (default in brackets): H1-H4 5, 5, 6, 4 (6, 6, 8, 5);
   H1 + 30 Jy 6 (7); H4 + 30 Jy 5 (6); S2 + 30 Jy off 20 px 5 (6); H3 + 100 Jy 6 (8); pilot A 3 mJy 3 (5),
   B 3 mJy 3 (3), A 1 mJy 4 (8).
3. **Held out, blind: four new skies drawn now**, H5-H8, 2048 × 1.5″, recipes added to the simulator after this
   commit, sky seeds 20261701-20261704, noise seeds 20261711-20261714:
   - **H5**, dec −30: 200 points, log-uniform 1 mJy - 2 Jy, at least 10 px apart (high dynamic range, crowded).
   - **H6**, dec −60: 800 points, log-uniform 0.05 - 50 mJy, no separation (faint and dense; many sources near `T`).
   - **H7**, dec −10: 40 points, 5 - 500 mJy, and 8 circular Gaussians, FWHM log-uniform 15 - 120″, flux
     log-uniform 0.05 - 1 Jy, inside the inner two-thirds less a 220″ margin (extended).
   - **H8**, dec −20: 80 points, 5 mJy - 1 Jy, at least 10 px apart, plus two 5 Jy points at uniform positions in
     the inner two-thirds (two bright sources off centre).
   No wide field: WSClean's plain loop took 2,749 s on H3's 4096², and H3 is among the seen skies. WSClean 3.7
   (`rang-wsclean-native:3.7`, docker in WSL, `nominres`, `-mgain 0.8`, plain and fast loops, as the held-out
   note) runs on H5-H8 only; H1-H4 reuse the archived WSClean runs and scores.

## 5. Measurement

- **Baseline from this branch:** the default (no flag, and `-stop-tolerance 0`) runs natively on Windows from
  this branch's binary on S1-S3 and H1-H4. Expected 5, 5, 4 and 6, 6, 8, 5 cycles, and the two runs
  byte-identical in their FITS. A different count is reported, and then the branch's own default is the
  baseline for every ratio.
- Every run under `python C:\Users\gijsm\Github\rang\tools\heavy_lock.py run --slots N --mem G --` with honest
  figures (about 4 GB at 2048², 10 GB at 4096², 20 GB on the pilot; `-j 8`). Cycle counts do not depend on
  threads. Wall times are recorded in [tool-timings.md](tool-timings.md) and are not a result.
- Outputs: `D:\rang\outputs\stop28-20261116`; compact archive `research/results/gemclean-stop28.json`.
- Scorers: `examples/gemclean_bench_compare.py prepare` and `score` (truth-based false |flux|, Q/Q_truth,
  flux-weighted recovery, inner residual peak); the bright-source cases by `examples/stale_floor_score.py` (the
  model's own measures: cycles, model pixels, off-source Σ|flux|); the pilot by
  `examples/gemclean_heldout_real.py score` and `compare` (off-source |model| in the shared mask, compact fluxes).

## 6. Decision rule (frozen, on H5-H8 at the chosen ε)

Per sky, against GeMClean's default on the same sky (D) and WSClean's two loops (W):

- **Q-D, against the default:** false |flux| ≤ 1.1 × D's; Q/Q_truth within 0.2 % of D's; flux-weighted
  recovery ≥ D's − 0.5 %; exact inner residual peak below (1 + ε) T.
- **Q-W, against WSClean (the held-out note's tolerance):** false |flux| ≤ 1.6 × the lower of W's two loops;
  Q/Q_truth within 0.2 % of WSClean plain's; recovery no lower than WSClean plain's by more than 0.5 %. Where D
  itself misses Q-W on a sky, the rule there only has to pass Q-D, and D's miss is reported.
- **Saving** s = D's cycles − the rule's cycles.

Outcomes:

1. **Gain:** Q-D and Q-W on every new sky, mean s ≥ 1, and at most 5 cycles on every new sky.
2. **Partial gain:** Q-D and Q-W on every new sky and mean s ≥ 1, but more than 5 cycles on some sky: a gain
   over GeMClean's own rule, with the issue's bar of 5 missed and reported.
3. **Null:** Q-D and Q-W hold, mean s < 1.
4. **Failure:** Q-D, or Q-W beyond D's own misses, missed on any new sky.

**Novelty reading**, not a claim unless met: the rule's cycles below WSClean plain's on every new sky at false
|flux| no higher than plain's.

**Default.** This branch does not change it. On a gain, with the pilot (seen) at off-source |model| ≤ 1.1 × D's
and compact-flux median ratios within 0.5 % of 1, the note recommends `-stop-tolerance ε` as the default to the
coordinator, stating the residual peak left above `T`; on a partial gain it lists the flag as an option; otherwise
it stays off. The seen sets do not change the outcome, except that a component budget or an ascending cycle on
any of them counts as a failure.

## 7. Stages and stop rules

1. This note, committed. 2. The flag, with tests: ε = 0 byte-identical; a nonzero ε ends a run exactly at the
first cycle below `(1 + ε) T`; the refusals. 3. Baseline and ε choice on S1-S3. 4. H5-H8 registered in the
simulator, simulated once, run once (default, rule, WSClean plain and fast). 5. Seen sets. 6. Pilot. 7. Verdict
by §6. A failed build or a baseline mismatch stops its stage and is reported.

## Amendments

**1, 2026-11-16, before any run.** (a) Every GeMClean run passes `-wgridder-accuracy 1e-6` (double precision):
the archived runs (`f0ca931`, the stale-floor reports) used 1e-6, and WSClean's runs here use 1e-6, but GeMClean's
default has been 1e-4 in single precision since G7 ([g7-defaults.md](g7-defaults.md)). Without the flag the
baseline would not be the archived one. The rule's effect at the 1e-4 default is not measured here. (b) H7's 40
points keep the 10 px separation of H1, H3 and H4 (the freeze did not say).

**2, 2026-11-16, after the development stage, before any held-out GeMClean run.** Threads only, for the shared
host: the held-out GeMClean runs use `-j 4` (4 slots) instead of `-j 8`, and WSClean on H5-H8 runs at `-j 8`
(the archived H1-H4 WSClean runs were `-j 16`). Cycle counts and images do not depend on the thread count
(identical at 1 and 16 threads on S1, [x1-crossplatform.md](x1-crossplatform.md)); no wall time here is a result.

**3, 2026-11-16, after the held-out runs, before any held-out score.** The scorer needs a beam for its "within one
beam" and "two beams" regions, which the held-out note took from WSClean's `-niter 0` PSF fit. The re-prepared
H1-H4 and the new H5-H8 have no such comparison, so the beam is passed explicitly: for H1-H4 the archived scores'
value (12.33″ on H1, as before), for H5-H8 the geometric mean of WSClean's fitted restoring beam on its nominres
fast image (the same PSF fit). The same beam applies to all four imagers on a sky.

## Measured result

### Development (S1-S3), branch binary `0775c4f`, native Windows, `-j 8`

Baseline: the default reproduces the archived Linux runs exactly (S1 5 cycles, 85,337 components, starting peaks
equal to the archive's to 0.01 µJy; S2 5, S3 4). `-stop-tolerance 0` is byte-identical to the default in model,
residual, image, PSF and dirty FITS on all three.

| sky | ε | majors | comps | false \|flux\| mJy | Q/Q_truth | recovery (fw) | inner peak µJy |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| S1 | default, 0, 0.005, 0.01 | 5 | 85,337 | 4.335 | 1.01358 | 0.9994 | 100.01 |
| S1 | 0.02, 0.05, 0.10 | 4 | 85,142 | 4.305 | 1.01361 | 0.9994 | 101.26 |
| S2 | default, 0, 0.005 | 5 | 90,905 | 4.878 | 1.01507 | 0.9993 | 100.02 |
| S2 | 0.01 - 0.10 | 4 | 90,828 | 4.838 | 1.01508 | 0.9993 | 100.52 |
| S3 | default, 0, 0.005, 0.01 | 4 | 45,803 | 1.575 | 1.00986 | 0.9978 | 100.00 |
| S3 | 0.02, 0.05, 0.10 | 3 | 45,712 | 1.525 | 1.00988 | 0.9978 | 101.33 |

**Chosen by the frozen rule (§3): ε = 0.02**, the smallest grid value saving a cycle on all three; every quality
check passes on each. As predicted from the traces. Scores: `scores/dev-s{1,2,3}.json`; table
`summary-dev.json` (`examples/stop28_table.py dev`).

### Held out, blind: H5-H8 at ε = 0.02 (the verdict)

GeMClean `-j 4`; WSClean 3.7 `rang-wsclean-native:3.7`, nominres, `-mgain 0.8`, `-j 8`; one scorer and one beam
per sky (10.76″, 11.28″, 11.44″, 10.99″). WSClean's plain loop reports no component total.

| sky | imager | majors | comps | false \|flux\| mJy | Q/Q_truth | recovery (fw) | inner peak µJy |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| H5 | GeMClean default | 8 | 517,615 | 162.25 | 1.06868 | 0.9984 | 100.02 |
| H5 | **ε = 0.02** | **5** | 516,345 | 160.98 | 1.06889 | 0.9984 | 101.96 |
| H5 | WSClean fast | 10 | 505,075 | 115.92 | 1.07016 | 0.9983 | 238.54 |
| H5 | WSClean plain | 7 | – | 164.35 | 1.06932 | 0.9984 | 108.47 |
| H6 | GeMClean default | 5 | 32,242 | 0.517 | 1.00490 | 0.9961 | 99.99 |
| H6 | **ε = 0.02** | **4** | 32,237 | 0.517 | 1.00490 | 0.9961 | 100.04 |
| H6 | WSClean fast | 5 | 31,808 | 0.496 | 1.00497 | 0.9960 | 177.81 |
| H6 | WSClean plain | 4 | – | 0.631 | 1.00490 | 0.9961 | 110.79 |
| H7 | GeMClean default | 5 | 31,218 | 5.721 | 1.00519 | 0.9348 | 99.97 |
| H7 | **ε = 0.02** | **5** | 31,218 | 5.721 | 1.00519 | 0.9348 | 99.97 |
| H7 | WSClean fast | 7 | 30,412 | 6.186 | 1.00496 | 0.9353 | 228.94 |
| H7 | WSClean plain | 6 | – | 5.689 | 1.00483 | 0.9348 | 104.26 |
| H8 | GeMClean default | 6 | 145,825 | 111.36 | 1.01983 | 0.9941 | 99.97 |
| H8 | **ε = 0.02** | **5** | 145,584 | 110.85 | 1.01987 | 0.9941 | 101.33 |
| H8 | WSClean fast | 10 | 143,745 | 91.56 | 1.02023 | 0.9941 | 263.63 |
| H8 | WSClean plain | 7 | – | 116.16 | 1.01969 | 0.9941 | 118.85 |

- **Savings 3, 1, 0, 1: mean 1.25 cycles.** The cut cycles started at 101.96, 100.04 and 101.40 µJy (H5 then
  cycles of 120 and 2 components; H6 5; H8 241). H7's last cycle started at 102.82 µJy, above 102, so nothing changed.
- **Q-D passes on every sky:** false |flux| 0.992-1.000 × the default's, Q/Q_truth within 0.02 %, recovery equal to
  four decimals, inner peak below 102 µJy (largest 101.96 on H5).
- **Q-W passes on every sky:** false |flux| / lower WSClean loop 1.39, 1.04, 1.01, 1.21 (bar 1.6); Q/Q_truth within
  0.05 % of plain's; recovery equal to plain's to 0.0001.
- **At most 5 cycles on every sky:** 5, 4, 5, 5.
- **Outcome under §6: gain.** Over GeMClean's own rule only.
- **Novelty reading: not met.** Below WSClean plain's cycles at no more false flux on H5 (5 against 7) and H8 (5 against
  7). Not on H6 (4 against 4) or H7 (5 against 6, but 5.721 against 5.689 mJy false flux).
- **H5 is the one sky where the default missed the issue's bar badly** (8 cycles). The rule brings it to 5. Its false
  flux is high for every imager (116-164 mJy, 200 sources up to 2 Jy). WSClean's fast loop is lowest there.

### Seen: H1-H4 (not blind; predictions in §4)

Default reproduced exactly: 6, 6, 8, 5 cycles, false |flux| 1.427, 6.156, 11.842, 5.328 mJy, as the archive.
At ε = 0.02: **5, 5, 6, 4, as predicted**; false |flux| 1.427, 6.135, 11.832, 5.328 mJy; Q/Q_truth unchanged at
five decimals; inner peaks 100.15, 100.16, 100.18, 100.07 µJy. Q-D and Q-W pass on all four. H3 still has 6 cycles
(its sixth cycle starts at 102.59 µJy). By §6's wording this set would read "partial gain"; it does not enter the
verdict.

### Seen: bright-source cases (the model's own measures; predictions in §4)

| case | default: cycles, comps, model px, off-source Σ\|flux\| Jy | ε = 0.02: same | inner peak µJy |
| --- | --- | --- | ---: |
| H1 + 30 Jy | 7, 88,682, 2,522, 16.4481 | 6, 88,665, 2,522, 16.4479 | 100.13 |
| H4 + 30 Jy | 6, 55,509, 30,688, 7.8450 | 5, 55,502, 30,683, 7.8450 | 100.06 |
| S2 + 30 Jy off 20 px | 6, 94,678, 4,558, 16.0164 | 5, 94,654, 4,558, 16.0161 | 100.08 |
| H3 + 100 Jy | 8, 166,396, 6,263, 27.6342 | 6, 166,166, 6,254, 27.6320 | 100.82 |

All stop at the threshold, as predicted (6, 5, 5, 6); the defaults equal [stale-floor.md](stale-floor.md)'s rows. No
budget, no ascending cycle.
