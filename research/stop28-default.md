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
