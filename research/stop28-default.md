<!-- SPDX-License-Identifier: MIT -->
# Rang: `-stop-tolerance 0.02` as GeMClean's default? (issue #28, at the shipping accuracy)

Status at freeze, 2026-11-17: **proposed; nothing run.** Branch `stop28-default` from main `02f1d39`. Results go
under "Measured result"; nothing above it changes except by dated, labelled amendment. Route:
[docs/agents/propose-and-measure.md](../docs/agents/propose-and-measure.md). Previous note:
[gemclean-stop28.md](gemclean-stop28.md).

## 1. Question

[gemclean-stop28.md](gemclean-stop28.md) measured `-stop-tolerance 0.02` (end the run when the exact peak after a
major cycle is below 1.02 T) at `-wgridder-accuracy 1e-6`: blind H5-H8 8, 5, 5, 6 → 5, 4, 5, 5 cycles, a gain under
its rule. GeMClean ships at 1e-4 in single precision ([g7-defaults.md](g7-defaults.md)). The coordinator kept the
default at 0: H5's cut cycle started 0.04 µJy under the cut-off, and 1e-4 was measured only post hoc on H5-H8
(7, 5, 6, 7 → 6, 4, 5, 5). A switch needs a fresh frozen run at the shipping accuracy on skies not yet seen.

**Hypothesis.** At GeMClean's default accuracy, ε = 0.02 saves at least one major cycle per run on average on new
skies at the default's quality and within the WSClean tolerance of the held-out note.

**Not claimed.** No gain over WSClean, no novelty, no speed claim: nash is shared, so wall times are reported only.
ε is not re-chosen: 0.02 is fixed by [gemclean-stop28.md](gemclean-stop28.md) §3.

## 2. Settings (frozen)

- **GeMClean**: this branch's binary built on nash (`cargo +1.93 build --release --bin gemclean`, AVX2 tier; nash
  has no AVX-512). Every run as [gemclean-stop28.md](gemclean-stop28.md) §4 except the accuracy: **no
  `-wgridder-accuracy`** (1e-4, single precision), `-size N N -scale 1.5asec -weight briggs 0.5 -niter 1000000
  -gain 0.1 -nmiter 1000 -abs-threshold 100e-6 -data-column DATA -field 0 -j 4`. Two arms per case: **D** (no
  flag) and **R** (`-stop-tolerance 0.02`). Pilot: `-size 4096 4096 -scale 3asec`, abs threshold 3 mJy (A, B) and
  1 mJy (A), as there.
- **WSClean 3.7** (`rang-wsclean-native_3.7.sif`, the oracle of the earlier notes, apptainer on nash): on the new
  skies only, settings of `examples/gemclean_bench_run.sh` abs/nominres (`-wgridder-accuracy 1e-6
  -no-min-grid-resolution -mgain 0.8 -nmiter 0`), fast and plain (`-no-fast-subminor`) loops, `-j 8`. H1-H8 reuse
  the archived WSClean scores.
- **Host and lock**: nash, every command `nice -n 19 ionice -c3` through `~/Github/rang/tools/heavy_lock.py run
  --slots N --mem G`: GeMClean 4 slots (6 GB at 2048², 12 GB at 4096², 20 GB pilot), WSClean fast 8 slots and plain
  3 slots (8 GB). Outputs `~/rang-data/outputs/stop28-default-20261117/`.
- **Scorers**: `examples/gemclean_bench_compare.py prepare/score` (simulated skies; beams as
  [gemclean-stop28.md](gemclean-stop28.md) amendment 3: archived value for H1-H4, WSClean's fitted beam on its
  nominres fast image for H5-H16, the archived WSClean fast image for H5-H8; S1-S3 the scorer's own);
  `examples/gemclean_heldout_real.py prep/score/compare` (pilot; beam 12.7″, mask 5 σ, compact 10 σ, source mask the
  mean of D's and R's images, as there).

## 3. Data

1. **Seen** (reported, not in the verdict): S1-S3, H1-H8, and the pilot (`cal2.ms` A, `cal3.ms` B). Simulated sets
   are regenerated on nash from their recipes and seeds and must match the archived catalogues'
   `main_table_sha256` (except `table.lock`) and `noise_out_sha256`; a mismatch is copied from glacier instead and
   reported. The pilot is copied. H3 is 4096² as before.
   **Predictions** from the post hoc 1e-4 pairs on glacier ([gemclean-stop28.md](gemclean-stop28.md), last
   bullet): H5-H8 D 7, 5, 6, 7; R 6, 4, 5, 5. None for the others. A different count on nash (other CPU, AVX2) is
   reported, not a failure: nash's own D is the baseline for every ratio.
2. **New, blind: H9-H16**, eight 2048² × 1.5″ skies, recipes of earlier skies at new declinations, recipes added to
   `examples/gemclean_bench_simulate.py` after this commit, sky seeds 20261801-20261808, noise seeds
   20261811-20261818:

   | sky | recipe (as) | dec |
   | --- | --- | ---: |
   | H9 | H5: 200 points, 1 mJy - 2 Jy, min-sep 10 px | −45 |
   | H10 | H6: 800 points, 0.05 - 50 mJy, no separation | −30 |
   | H11 | H7: 40 points 5 - 500 mJy (10 px) and 8 Gaussians | −60 |
   | H12 | H8: 80 points 5 mJy - 1 Jy (10 px) and two 5 Jy points | −40 |
   | H13 | H1: 60 points, 5 mJy - 1 Jy, min-sep 10 px | −5 |
   | H14 | H2: 300 points, 0.2 - 200 mJy, blended | −70 |
   | H15 | H4: 30 points, 6 Gaussians and a 25-Gaussian tail | −25 |
   | H16 | S3: 500 points, 0.1 - 100 mJy, no separation | −50 |

   No wide field and no bright-source additions (the stale-floor cases need python-casacore, and the rule only
   truncates the default's run; [gemclean-stop28.md](gemclean-stop28.md) found nothing there at 1e-6).

## 4. Measures

Per case and arm: major cycles; components; wall time (`report.json` `seconds.total` and `seconds.major`,
provisional, nash shared); GeMClean's own final residual peak (`run.residual_peak_abs`) / T; the scorer's exact
inner residual peak; false |flux|; Q/Q_truth; flux-weighted recovery; compact flux (pilot). Also, descriptive: the
start peak (`peak_start`) / T of R's last cycle and of D's cycles, to show the margin to 1.02.

**Integrity checks** (frozen):
- I1: `-stop-tolerance 0` byte-identical to D in model, residual, image, PSF and dirty FITS on S1-S3.
- I2: on every case, R is D cut: R's cycle count equals the index of D's first cycle (from 1) whose `peak_start` is
  below 1.02 T (D's count if none), and R's per-cycle component counts equal D's over those cycles.

## 5. Decision rule (frozen, on H9-H16)

Per sky, R against D and WSClean (W):

- **Q-D**: false |flux| ≤ 1.1 × D's; Q/Q_truth within 0.2 % of D's; recovery ≥ D's − 0.5 %; R's own final residual
  peak < 1.02 T; R's exact inner peak ≤ max(D's exact inner peak, T) + 0.02 T. (At 1e-4 the exact inner peak is
  set by the gridder's error, 100-207 µJy for both arms on H5-H8, so it is compared with D's, not with T.)
- **Q-W**: false |flux| ≤ 1.6 × the lower of W's two loops; Q/Q_truth within 0.2 % of W plain's; recovery ≥ W
  plain's − 0.5 %. Where D itself misses Q-W, R only has to pass Q-D there, and D's miss is reported.
- **Saving** s = D's cycles − R's cycles.
- **Seen sets** at 1e-4 (S1-S3, H1-H8, pilot): Q-D on every simulated case (Q-W reported for H1-H8); pilot
  off-source |model| ≤ 1.1 × D's and compact-flux median ratio R/D within 0.5 % of 1; no component budget and no
  ascending major cycle on any case.

Outcomes:

1. **Switch the default** to 0.02: Q-D on all eight new skies, Q-W on all eight beyond D's own misses, mean s ≥ 1
   over H9-H16, s ≥ 1 on at least four of the eight, every seen-set condition met, I1 and I2 pass.
2. **Keep opt-in** (default 0, `-stop-tolerance 0.02` stays an option): every quality, seen-set and integrity
   condition of 1 met, but mean s < 1 or fewer than four skies with s ≥ 1.
3. **Not yet** (default 0, the failure reported in the flag's help and here): any Q-D failure on any case, a Q-W
   failure beyond D's own on a new sky, a seen-set condition missed, I1 or I2 failed, or a new sky without both
   arms scored.

Also reported, not gating: at most 5 cycles on every new sky (the issue's example bar), pooled mean s over all 19
simulated skies, and the novelty reading of [gemclean-stop28.md](gemclean-stop28.md) §6.

**If the outcome is "switch"**, the default changes only where the flag is supported now (Stokes I, separate
polarisations or channels, `-fits-mask`): with `-auto-mask`, `-multiscale`, `-join-channels` or
`-join-polarizations` the default stays 0 silently, and only an explicit nonzero `-stop-tolerance` is refused, as
now. `-stop-tolerance 0` restores the exact stop. Tests, `docs/cli.md`, CHANGELOG.

## 6. Stages

1. This note, committed. 2. Simulator recipes H9-H16 and the nash driver `examples/stop28_default.py`.
3. Build on nash; regenerate and hash-check the seen skies; copy the pilot. 4. I1 on S1-S3. 5. H9-H16 simulated
once, run once (D, R, WSClean fast and plain), scored. 6. Seen sets. 7. Pilot. 8. Verdict by §5. A failed build,
simulation or hash check stops its stage and is reported.

**How to read a run.** The driver runs unattended (`setsid nohup`); its log
`~/rang-data/outputs/stop28-default-20261117/logs/driver-<stage>.log` ends with a line `DRIVER-END <stage> rc=N`.
`timing.tsv` there lists every locked job (name, wall including lock wait, exit code).

## Amendments

**1, 2026-11-17, before any run.** I2's "index of D's first cycle (from 1)" means the report's own 0-based cycle
`index`, searched over all cycles: R's cycle count equals the `index` of D's first cycle whose `peak_start` is below
1.02 T. On the pilot T is that run's threshold (3 or 1 mJy). Driver: `examples/stop28_default.py`.

**2, 2026-11-17, before any WSClean run, after the GeMClean runs on H9-H16 had started (none scored).**
`rang-wsclean-native_3.7.sif` was built for glacier's CPU and stops with an illegal instruction on nash (no
AVX-512); every WSClean job exited at once and wrote nothing. WSClean on H9-H16 is nash's system build
(`/usr/bin/wsclean`, "WSClean version 3.7 (2026-02-16)"), same settings. The oracle stays WSClean 3.7; the build
differs from the archived H1-H8 runs'. Also, stage 3's hash check: S1, H3 and H4 regenerated on nash equal the
archive; S2, S3, H1, H2 and H5-H8 differ in the DATA column file (`table.f0_TSM0`; H5-H8 also `table.f3`), so those
eight are copied from glacier as §3 says, their noise files equal on every sky.

**3, 2026-11-18, post hoc: after every run had finished and after the H9-H16 savings and checks were seen.** The
driver's as-run table (`summary-asrun.json`) gave "not yet" only because S1-S3 were never scored:
`score-seen-s{1,2,3}` exited 1 ("no beam"). §2's "S1-S3 the scorer's own" beam is the one the scorer read from a
prep made with `--wsclean-dirty`; nash's prepare had no WSClean dirty image, so no such beam existed. Fix: the
driver passes S1-S3 that beam explicitly, 10.761531523459142″, the `beam_arcsec` of the archived
`D:/rang/outputs/stop28-20261116/scores/dev-s{1,2,3}.json`, which is √(bmaj × bmin) of the PSF fit in
`D:/rang/outputs/20261102-gemclean/bench/prep/s1/meta.json` (13.8785″ × 8.3448″). No imaging is re-run, no
threshold or rule changes; only the three missing S1-S3 scores and the table are produced.

## Measured result

Run 2026-11-17 20:13 to 2026-11-18 02:44 NST on nash (36 cores, shared; every job `nice -n 19 ionice -c3` under
the heavy lock), S1-S3 scores and the table 02:49-02:50 under amendment 3. GeMClean built from `7621d575` on nash
(AVX2; `bin/commit.txt`, `bin/gemclean.sha256`), `-j 4`, default accuracy 1e-4. WSClean: nash's `/usr/bin/wsclean`
3.7 (amendment 2). Seeds: H9-H16 sky 20261801-20261808, noise 20261811-20261818; seen skies from their archived
recipes and seeds (S1, H3, H4 regenerated equal; the other eight copied from glacier, `regen-check.json`). Run root
`nash:~/rang-data/outputs/stop28-default-20261117/` (`summary.json`, `summary-asrun.json`, `timing.tsv`,
`logs/run-all.log`, `logs/run-all2.log`, `logs/run-a3.log`). Compact copies:
[results/stop28-default/](results/stop28-default/) (`summary.json`, `table.txt`; as-run `summary-asrun.json`,
`table-asrun.txt`; `timing.tsv`, `regen-check.json`).

**Verdict by §5: switch the default** (outcome 1), exactly on the bar: mean saving over H9-H16 **1.0** (8/8; the
rule is mean s ≥ 1), **6 of 8** skies save a cycle (rule ≥ 4), Q-D on all eight, Q-W on all eight beyond D's own
misses, every seen-set condition met, I1 and I2 pass. The verdict rests on amendment 3 (post hoc): the driver's
as-run table said "not yet", only because S1-S3 had no scores (`score-seen-s{1,2,3}` exit 1, no beam). With
S1-S3 scored they pass every check, and no other number changed between the two tables.

### Blind H9-H16 (the verdict)

D default, R `-stop-tolerance 0.02`, W WSClean fast / plain. Seconds: GeMClean's `seconds.total`, provisional
(shared host).

| sky | majors D → R (W f/p) | s | comps D / R | false \|flux\| mJy D / R (W f/p) | Q/Q_truth D / R (W p) | recovery D / R (W p) | inner peak µJy D / R | R own peak / T | s D / R |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| H9 | 8 → 6 (10/7) | 2 | 332,481 / 332,456 | 45.976 / 45.966 (30.08/44.83) | 1.04900 / 1.04900 (1.04929) | 0.9978 / 0.9978 (0.9979) | 130.93 / 130.93 | 1.0005 | 71.3 / 62.6 |
| H10 | 4 → 3 (5/4) | 1 | 36,833 / 36,822 | 1.702 / 1.702 (0.666/1.014) | 1.00613 / 1.00613 (1.00626) | 0.9961 / 0.9961 (0.9960) | 100.62 / 100.58 | 1.0004 | 23.0 / 21.6 |
| H11 | 5 → 4 (7/6) | 1 | 36,830 / 36,828 | 1.319 / 1.319 (0.629/0.567) | 1.00567 / 1.00567 (1.00527) | 0.8557 / 0.8557 (0.8557) | 104.90 / 104.90 | 1.0011 | 28.2 / 24.1 |
| H12 | 6 → 5 (10/7) | 1 | 173,849 / 173,834 | 122.060 / 122.060 (96.25/118.99) | 1.02262 / 1.02262 (1.02310) | 0.9954 / 0.9954 (0.9954) | 224.16 / 224.17 | 1.0012 | 47.0 / 43.6 |
| H13 | 6 → 6 (9/6) | 0 | 100,212 / 100,212 | 91.195 / 91.195 (91.37/118.91) | 1.01285 / 1.01285 (1.01266) | 1.0003 / 1.0003 (1.0005) | 103.90 / 103.90 | 0.9999 | 60.8 / 60.2 |
| H14 | 6 → 4 (6/5) | 2 | 50,769 / 50,741 | 1.561 / 1.561 (0.898/1.150) | 1.00979 / 1.00979 (1.00987) | 0.9986 / 0.9986 (0.9986) | 100.15 / 100.35 | 1.0030 | 36.0 / 27.6 |
| H15 | 4 → 4 (5/5) | 0 | 44,204 / 44,204 | 3.427 / 3.427 (26.40/13.62) | 1.00384 / 1.00384 (1.00345) | 0.8292 / 0.8292 (0.8293) | 104.71 / 104.71 | 0.9999 | 24.3 / 26.1 |
| H16 | 5 → 4 (6/5) | 1 | 39,958 / 39,957 | 1.102 / 1.102 (1.077/1.104) | 1.00812 / 1.00812 (1.00813) | 0.9978 / 0.9978 (0.9978) | 100.40 / 100.40 | 1.0004 | 28.2 / 24.8 |

- **Savings 2, 1, 1, 1, 0, 2, 0, 1: mean 1.0, 6 of 8.** Equal to the bar, not above it. H13 and H15 save nothing:
  D's last cycle started at 1.0597 T and 1.0213 T, above 1.02.
- **Q-D passes on every sky**: false |flux| R/D 0.9998-1.0000, Q/Q_truth equal to five decimals, recovery equal to
  four, R's own final peak 0.9999-1.0030 T (bar < 1.02), exact inner peak within 0.20 µJy of D's.
- **Q-W: D itself misses the false-flux bar on H10, H11 and H14** (D / lower W loop 2.55, 2.33, 1.74; bar 1.6),
  and R has the same ratios, so R passes there only by the clause "where D itself misses Q-W". This is against
  nash's system WSClean build (amendment 2). On the other five skies the ratio is 0.25-1.53 for both arms;
  Q/Q_truth within 0.04 % of W plain's and recovery within 0.0002 on all eight.
- **I2 passes on all 19 simulated cases and the pilot**: R's cycles are D's, cut where D's next cycle starts
  below 1.02 T, with equal per-cycle component counts.
- Not gating: **the issue's bar of at most 5 cycles is missed** on H9 (6) and H13 (6); pooled mean saving over all
  19 simulated skies 1.105 (21/19); median R/D `seconds.total` on H9-H16 0.90; **novelty reading not met**
  (R below W plain's cycles at no more false flux on H15 and H16 only).

### Seen sets at 1e-4 (all pass)

| sky | D → R | s | false mJy D / R | Q/Q_truth D / R | inner peak µJy D / R | R own peak / T |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| S1 | 5 → 4 | 1 | 4.319 / 4.279 | 1.01359 / 1.01362 | 125.29 / 125.20 | 1.0114 |
| S2 | 5 → 4 | 1 | 4.908 / 4.848 | 1.01517 / 1.01520 | 122.36 / 122.24 | 1.0136 |
| S3 | 4 → 3 | 1 | 1.556 / 1.516 | 1.00987 / 1.00988 | 101.94 / 102.13 | 1.0125 |
| H1 | 6 → 5 | 1 | 1.428 / 1.428 | 1.01417 / 1.01418 | 107.94 / 107.93 | 1.0004 |
| H2 | 7 → 5 | 2 | 6.093 / 6.083 | 1.00999 / 1.01000 | 101.23 / 101.21 | 1.0007 |
| H3 | 7 → 6 | 1 | 11.769 / 11.769 | 1.02541 / 1.02541 | 107.16 / 107.14 | 1.0002 |
| H4 | 5 → 4 | 1 | 5.231 / 5.231 | 1.00336 / 1.00336 | 100.44 / 100.42 | 1.0013 |
| H5 | 8 → 6 | 2 | 162.280 / 162.270 | 1.06867 / 1.06868 | 153.51 / 153.58 | 1.0003 |
| H6 | 4 → 4 | 0 | 0.527 / 0.527 | 1.00490 / 1.00490 | 100.17 / 100.17 | 1.0000 |
| H7 | 5 → 4 | 1 | 5.720 / 5.700 | 1.00515 / 1.00517 | 101.37 / 102.63 | 1.0194 |
| H8 | 7 → 5 | 2 | 111.023 / 110.351 | 1.01982 / 1.01990 | 206.97 / 206.80 | 1.0180 |

- Q-D on all eleven; Q-W on H1-H8 for both arms; no budget stop, no ascending cycle. S1-S3 agree with the 1e-6
  development scores of [gemclean-stop28.md](gemclean-stop28.md) (S1 D 4.319 against 4.335 mJy, Q 1.01359
  against 1.01358), so amendment 3's beam reproduces that scoring.
- **H7 and H8 end close to the own-peak bar**: 1.0194 T and 1.0180 T against < 1.02.
- **Predictions missed on nash** (reported, not a failure): H5-H8 D 8, 4, 5, 7 and R 6, 4, 4, 5 against the
  glacier 1e-4 prediction D 7, 5, 6, 7 and R 6, 4, 5, 5.
- **I1**: `-stop-tolerance 0` byte-identical to the default in model, residual, image, PSF and dirty FITS on S1-S3.
- **Pilot** (4096² × 3″): A 3 mJy 5 → 3 cycles, B 3 mJy 4 → 3, A 1 mJy 7 → 4; off-source |model| R/D 0.9994,
  0.9997, 0.9992; compact-flux median R/D 0.99998, 1.000004, 1.00005 (n 42, 72, 60); no budget stop or ascending
  cycle; `seconds.total` D/R 310/224, 240/195, 784/628.

### Wall times (nash, shared)

Simulate 22.8 min (20:13-20:36), regen and hash check 26 min, H9-H16 GeMClean pairs 17 min (20:39-20:56), seen
pairs 31.7 min (21:22-21:54), pilot 56.8 min, scoring 3 h 36 min (23:08-02:44, almost all lock wait: one queue of
11,879 s before `score-new-h15`), S1-S3 scores and table 1 min. WSClean per sky (`timing.tsv`, lock wait
included): fast 70-130 s, plain 386-3,210 s.

### Code change (outcome 1)

`gemclean` now defaults to `-stop-tolerance 0.02` where the flag is supported (Stokes I, separate polarisations
or channels, `-fits-mask`). With `-auto-mask`, `-multiscale`, `-join-channels` or `-join-polarizations` the default
is 0 silently and an explicit nonzero value is still refused; `-stop-tolerance 0` restores the exact stop. The core
`Settings::default()` keeps 0 (library callers unchanged). Tests in `core/src/gemclean/cli.rs`; `docs/cli.md`;
CHANGELOG.

## For the coordinator

- **Outcome 1, switch, exactly on the bar**: mean saving 8/8 = 1.0 against "≥ 1", 6 of 8 against "≥ 4". One sky
  fewer saving a cycle would have meant keep opt-in.
- **It rests on post hoc amendment 3.** The driver's as-run table (`summary-asrun.json`, `table-asrun.txt`) said
  "not yet" because S1-S3 were never scored (no beam). With the archived scorer beam they pass and reproduce the
  1e-6 development scores; nothing else moved. If you do not accept amendment 3, the as-run outcome is "not yet"
  (incomplete) and the code commit should be left out: the research commits stand alone.
- **Q-W passes on H10, H11 and H14 only through D's own miss** (D / lower WSClean false flux 2.55, 2.33, 1.74
  against 1.6), against nash's system WSClean 3.7, not the archived image (amendment 2). Worth a look before
  claiming parity with WSClean on faint-source skies; it is a default-GeMClean property, not the rule's.
- Close calls: H7 and H8 R's own final peak 1.0194 T and 1.0180 T against < 1.02. Not met, not gating: at most
  5 cycles (H9, H13 at 6); novelty (only H15, H16 below WSClean plain's cycles at no more false flux).
- **Code** (separate commit): CLI default 0.02 on the supported paths, 0 with `-auto-mask`, `-multiscale` and
  the joins (explicit nonzero still refused there), `-stop-tolerance 0` the exact stop; `Settings::default()` in
  the core stays 0. Default GeMClean runs now end up to two cycles earlier and their `report.json` carries
  `stop_tolerance` 0.02. `--quick` and CI do not run the archive and oracle gates: the full check
  (`python tools/check_all.py`) is left to the merge check; gates that pin a default GeMClean run's cycle count or
  output (the gemclean benchmark and E2/E5 image gates) may shift and should be re-read, not re-frozen silently.
- Raw outputs stay on nash (`~/rang-data/outputs/stop28-default-20261117`, about the size of 19 MS copies);
  delete when merged. The nash worktree is at `47ab64ef`, clean.
