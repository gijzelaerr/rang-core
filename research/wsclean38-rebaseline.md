# Rang: GeMClean's WSClean comparisons restated against WSClean 3.8

Status, 2026-11-22: **measured (section 7). P passes; H-mask and H-ms hold; T's outcome is changed: in pair B at `-j 1`, S1-S3 move into GeMClean's lead against 3.8, because 3.8's `minres` is 6-23 % slower at one thread. Pair A and every `-j 16` lead set are unchanged; no host change.** Sections 1-6 frozen 2026-11-18 before any WSClean 3.8 run; amendments 1-2 dated.
Results go in section 7; any later change to sections 1-6 is dated and labelled post hoc.

Proposal: [proposals/wsclean-3-8-rebaseline.md](proposals/wsclean-3-8-rebaseline.md), from the
[2026-11-18 digest](digests/2026-11-18.md), approved by the owner on 2026-11-18. A re-measurement
of results stated against WSClean 3.7; **no novelty is claimed**, and no GeMClean code changes.

## 1. Question and hypotheses

WSClean 3.8 (tag `v3.8`, `386ba535`, 2026-11-17;
[changelog](https://wsclean.readthedocs.io/en/latest/changelogs/v3.8.html)) changes multiscale
("far fewer FFTs", a residual update that no longer wraps PSF sidelobes), the wgridder
(recentering, an updated ducc0 wgridder) and per-scale masks. Do the statements rang makes
against 3.7 still hold against 3.8?

- **H-speed** ([gemclean-speed.md](gemclean-speed.md)): at `-j 16` GeMClean is faster than WSClean
  on all seven skies; at `-j 1` WSClean is faster on H1-H3 at its best setting tried.
- **H-mask** ([gemclean-ms-mask.md](gemclean-ms-mask.md)): outcome "multiscale difference, not
  the mask", because WSClean 3.7 diverged on RM and PM. Hypothesis: 3.8 still diverges there
  (its changelog does not name a divergence change).
- **H-ms** ([multiscale-df5o-a1.md](multiscale-df5o-a1.md), [df5o-deconv-oracles.md](df5o-deconv-oracles.md)):
  WSClean multiscale fails A1 on DF5-O's field (p16, p23, p26 in repeat 1), as GeMClean does
  (p23). Hypothesis: 3.8 fails A1 on the same sources.
- **!1068 is in 3.8** (read 2026-11-18, before this freeze): the merge base of `53e25d59` (!1068,
  merged 2026-11-13) and `v3.8` is `53e25d59`. GeMClean on main already follows it (`d2013eae`).
  So 3.7 and 3.8 can choose different theoretic beams and default multiscale scales where `|v|`
  limits differ from `|u|` limits; arm P records the beam each prints.

## 2. Oracle and binaries (pinned)

- **WSClean 3.8**: `rang-wsclean-native:3.8`, built from
  [tools/oracles/wsclean-native/Dockerfile](../tools/oracles/wsclean-native/Dockerfile) with
  `--build-arg WSCLEAN_TAG=v3.8` on glacier (`-DPORTABLE=OFF`, no EveryBeam, no IDG, casacore
  `3.7.1-1kern1`), the image's `/wsclean-commit.txt` and CMake cache recorded. The radler and
  ducc0 commits CMake's FetchContent takes are recorded from the build log.
- **WSClean 3.7**: `rang-wsclean-native:3.7` (`4f395b2`), unchanged, rerun in the same sessions as
  3.8 so that host drift does not enter the 3.7-3.8 comparison.
- **GeMClean**: built in WSL from `6c615524` (main's Rust is unchanged up to `09604d60`),
  `cargo +1.93 build --profile gemclean --bin gemclean`, sha256 recorded.
- Host glacier (16 threads, WSL 2, 44 GB). Data are copied to the WSL disk for timing, as in
  gemclean-speed's native pass.

## 3. Arms

| arm | what | data | settings | host use |
| --- | --- | --- | --- | --- |
| P | parity, `-niter 0` | S1 | 3.7 and 3.8, `minres` and `nominres`, `-j 16`, the bench's common settings (`examples/gemclean_bench_run.sh`) | shared, 8 slots |
| T | speed table | S1-S3, H1-H4 | per repeat (3), sky and thread count (16, 1): WSClean 3.7 and 3.8 `minres` and `nominres` (`BENCH_LOOPS=fast`, `BENCH_MODES=abs`); GeMClean default and coarse (`-single -wgridder-accuracy 1e-4`); order rotated by repeat. One run each of 3.7 and 3.8 `minres -mgain 0.9` and `-mgain 0.95` per sky and thread count | **exclusive**, from 21:00 |
| M | mask arms | H4, the pilot | RM, RH, PM, RM1, PM1 exactly as gemclean-ms-mask section 3 and 7, WSClean 3.8 only; GeMClean's side is the archived run (`D:\rang\outputs\gemclean-ms-mask-20261117`), unchanged | shared, 8 slots |
| D | DF5-O multiscale | DF5-O's field (`D:\rang\outputs\u23-20261113-01\field`) | `ws-multiscale` (DF5-O section 2.1, `-j 4`), one repeat each of native 3.7 and native 3.8 (DF5-O itself ran the packaged 3.7 in `rang-o-casa`, so native 3.7 is the matched control) | shared, 4 slots |

Scoring uses the existing scripts unchanged: `examples/gemclean_bench_compare.py` and
`native_repeats.py` (T), `results/gemclean-ms-mask-scripts/score.py` (M),
`results/multiscale-df5o-a1-scripts/measure.py` (D). Copies of the drivers go in
`results/wsclean38-rebaseline-scripts/`.

## 4. Measures and decision rules (frozen)

**P, parity.** max |Δ| / peak between 3.7 and 3.8 dirty images and PSFs.
- Pass if ≤ 10 × the requested accuracy: 1e-5 for `nominres` (1e-6), 1e-3 for `minres` (1e-4).
- Above that, but ≤ 1e-2: recorded with the changelog item that can explain it; T and M go on
  (each tool is timed at its own requested accuracy).
- Above 1e-2: **stop** (different data or weighting); T is not run.
- The theoretic and fitted beams both versions print are recorded.

**T, speed.** Medians of three repeats; `-mgain` cells one run. Two matched pairs per sky and
thread count: (A) GeMClean default against WSClean `nominres` (both 1e-6); (B) GeMClean coarse
against WSClean's best of `minres`, `minres -mgain 0.9`, `minres -mgain 0.95` (all 1e-4).
- **Lead sets.** For each pair, thread count and WSClean version, the skies where GeMClean's median
  is lower. Outcome **stands** if 3.8's lead sets equal tonight's 3.7 lead sets in all four
  (pair × threads); **changed** otherwise, listing each sky that moved, with its ratios.
- **3.8 against 3.7.** WSClean 3.8 is faster on a sky and setting if its median is lower than
  3.7's by more than the larger relative repeat spread (max−min over median) of the two.
- **Host control.** Tonight's 3.7 medians against gemclean-speed's (2026-11-04): a difference
  over 10 % on two or more skies is reported as host change. It does not void the 3.7-3.8
  comparison, which is within tonight.
- **Accuracy** is not rescored in T. P is its check, and T's FITS are kept for later scoring.

**M, mask.** score.py's M1, C and O, against the archived GeMClean runs.
- **H-mask holds** (3.8 still diverges) if WSClean 3.8 prints a divergence message on RM or PM.
  gemclean-ms-mask's outcome then stands as written.
- **H-mask fails** (3.8 converges on both) if neither run diverges. Then O against GeMClean is
  scored and reported. If O passes on both, the ms-mask outcome against 3.8 reads "no defect";
  if O fails, it still reads "multiscale difference, not the mask". Which applies is reported;
  the note is changed only by a dated line.
- **C on RH must pass with 3.8** (no model pixel outside the mask with Högbom). A failure is a
  3.8 finding, recorded.

**D, DF5-O multiscale.** A1 per DF5-O section 3.
- **H-ms holds** if native 3.8's A1 failure set equals native 3.7's and every ΔS/S on p16, p23 and
  p26 is within 0.01 (absolute) of native 3.7's.
- **Changed** otherwise, listing the sources.
- Native 3.7 against DF5-O's packaged 3.7 (r1) is reported as a control. A difference there is a
  build effect, not a 3.8 effect.

## 5. Cost and stop rules

- Build: shared, 8 slots. P, M, D: shared, in the daytime (no timing claim from them).
- T: one exclusive hold per job under the main checkout's `tools/heavy_lock.py`, started at 21:00
  on glacier (the owner's daytime rule). It must end by 07:00. Repeats not finished by then are
  dropped and recorded; T needs at least two repeats for an outcome, otherwise "incomplete".
- Spoiled runs: load before and after each job is recorded. A job with another process above half
  a core (other than the probe and the VM host) is marked, kept, and repeated once at the end if
  time allows. The rule is applied to the clean runs when every cell has at least two, otherwise
  to all, and both are reported.
- A build failure stops every arm. A WSClean crash in one arm is recorded and the others go on.

## 6. Not claimed, not measured

- No novelty and no change to GeMClean's code or defaults. A changed statement in docs or README
  is an owner decision (proposal, owner decisions).
- Not measured: 3.8's per-scale masks (`-multiscale-fits-mask`), RM synthesis, BDA, IDG,
  EveryBeam; real-data speed; hosts other than glacier.
- G2, G7 and G9's oracle cases (next-session.md: "rerun when !1068 is released") are a follow-up,
  not this task.

## Amendment 1, 2026-11-18 09:40 (before any 3.8 output was seen; not post hoc)

- **Hosts.** M and D run on nash (shared, `nice -n 19 ionice -c3`, nash's heavy lock), not on
  glacier, to keep glacier free in the daytime; neither makes a timing claim. nash has no docker:
  both native images are built there with rootless podman from the same Dockerfile (3.7 and 3.8,
  for nash's CPU, no AVX-512), so D's 3.7 control is nash-native too. M's GeMClean side stays the
  archived glacier run; M compares images, not times. P and T stay on glacier with glacier's images.
- **Dockerfile.** 3.8 links shared libraries from its FetchContent dependencies
  (`libschaapthreading.so`); the first build, which installed only the binary as for 3.7, failed
  at start-up. 3.8 is now installed with `cmake --install` and `ldconfig`. glacier's image
  `rang-wsclean-native:3.8`: WSClean `386ba535`, aocommon `dbee2ed9`, radler `703c1bd7`,
  schaapcommon `35f91f80`, xtensor `f115228a`, xtl `c52350e2` (`/wsclean-deps.txt`); 119 s build.

## Amendment 2, 2026-11-18 12:25 (RH's 3.8 output seen; RM, RM1, PM and PM1 not yet run)

- On nash, M's input directory (`~/rang-data/outputs/stop28-default-20261117`, holding H4 and the
  pilot) was removed by another session's cleanup between RH (finished 11:09) and RM1. RM1, RM,
  PM1 and PM failed at start-up (podman: `statfs ... no such file or directory`, rc 125); no
  WSClean output exists for them.
- RM, RM1, PM and PM1 therefore run on glacier with glacier's `rang-wsclean-native:3.8` on the
  archived inputs gemclean-ms-mask used (`D:\rang\outputs\20261103-gemclean-heldout`), shared
  slots, in the daytime, as the 3.7 runs did (`m_job_glacier.sh`, `M_RUNTIME=docker`). RH stays
  nash's run (nash's H4 copy: the same files as glacier's except glacier's extra MODEL_DATA
  column; every run images DATA). RH is the Högbom control and does not bear on the hypotheses
  RM and PM decide.
- D finished on nash as planned (native 3.7 and 3.8; outputs not yet read).

## 7. Results

Archive: [results/wsclean38-rebaseline/](results/wsclean38-rebaseline/); scripts:
[results/wsclean38-rebaseline-scripts/](results/wsclean38-rebaseline-scripts/). Run root
`D:\rang\outputs\wsclean38-20261118` (glacier) and `nash:~/rang-data/outputs/wsclean38-20261118`.
Images: glacier `rang-wsclean-native:3.8` and nash's podman builds have the same commits (WSClean
`386ba535`; aocommon `dbee2ed9`, radler `703c1bd7`, schaapcommon `35f91f80`); 3.7 is `4f395b28`
on both hosts. GeMClean `6c615524`, sha256 `aa81ad77…dbf1`.

### 7.1 P, parity (glacier, 2026-11-18 09:38): pass

| grid | image | max \|Δ\| / peak | tolerance | verdict |
| --- | --- | ---: | ---: | --- |
| minres | dirty | 1.9e-7 | 1e-3 | pass |
| minres | PSF | 3.0e-7 | 1e-3 | pass |
| nominres | dirty | 3.1e-8 | 1e-5 | pass |
| nominres | PSF | 8.9e-16 | 1e-5 | pass |

Both versions print "Theoretic beam = 5.4''" on S1 and fit 13.88″ × 8.34″, PA 150.19°
(BMAJ equal to 5e-9 relative). On S1, !1068 changes nothing visible.

### 7.2 M, mask (RH on nash; RM, RM1, PM, PM1 on glacier, amendment 2): H-mask holds

| run | WSClean 3.8 | F_in (Jy) | F_out (Jy) | N_out (Jy) | O | 3.7's F_out (Jy) |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| RH | 4 majors, converged | 1.689 | 0 | 0 | (C) pass | 0 |
| RM | **diverged**, 2 majors | 3.286 | 852.714 | −0.409 | fail | 347.411 |
| PM | **diverged**, 3 majors | 104.393 | −61.249 | −108.687 | fail | −62.721 |
| RM1 | 1 major | 1.4042 | 2.9313 | −0.0272 | pass | 2.9294 |
| PM1 | 1 major | 81.1501 | 0.0922 | −0.0000 | pass | 0.0732 |

- **As frozen: H-mask holds.** WSClean 3.8 prints "Multiscale clean diverged" on RM and PM, so
  gemclean-ms-mask's outcome ("multiscale difference, not the mask") stands as written.
- **C passes with 3.8.** On RH no model pixel lies outside the mask.
- M1 (GeMClean's centres) is the archived run's and passes as before.
- **Reported, not gated:** on PM1, 3.8 agrees with GeMClean to 3e-4 Jy in F_in (81.1501 against
  81.1498) and to 6e-7 Jy in F_out. 3.7 differed by 0.41 Jy in F_in (80.744). The level check
  (loop threshold) agrees to 1.7e-5. On RM, 3.8's divergence is larger than 3.7's
  (852.7 against 347.4 Jy outside the mask).
- Wall (shared hosts, no timing claim): RM 83 s (3.7: 181 s), PM 847 s (3.7: 2,346 s), RM1 62 s,
  PM1 346 s, all on glacier at 8 slots; RH 103 s on nash.

### 7.3 D, DF5-O multiscale (nash, native 3.7 and 3.8, one repeat each): H-ms holds

| run | A1 failures | p16 ΔS/S | p23 ΔS/S | p26 ΔS/S | total ratio | inner RMS (µJy) | majors |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DF5-O r1, packaged 3.7 (control) | p16, p23, p26 | +0.0870 | +0.1615 | +0.0898 | 0.99966 | 1.4463 | 7 |
| native 3.7 | p23, p26 | +0.0825 | +0.1574 | +0.0897 | 0.99950 | 1.4451 | 7 |
| native 3.8 | p23, p26 | +0.0830 | +0.1552 | +0.0893 | 0.99939 | 1.4468 | 7 |

- **As frozen: H-ms holds.** Native 3.8 fails A1 on the same sources as native 3.7. The largest
  ΔS/S change is 0.0023, under the 0.01 bound.
- A2 passes in all three.
- The control differs on p16. DF5-O's own r2 also failed only p23 and p26 (df5o-deconv-oracles.md),
  so p16 sits on A1's edge. That is a build or repeat effect, not a 3.8 effect.
- The in-container MS read check reports false for both nash runs, because the native images have
  no python-casacore. Each run imaged a copy of the MS that was deleted afterwards; the field
  itself was mounted read-only.
- Wall (nash, shared, nice 19, no timing claim): 3.7 2,232 s, 3.8 1,875 s.

### 7.4 T, speed table (glacier, exclusive, 2026-11-21 21:04 to 2026-11-22 02:09): outcome **changed**

Driver [t_speed.sh](results/wsclean38-rebaseline-scripts/t_speed.sh), exit 0: three repeats
(83, 84 and 87 min), then the `-mgain 0.9` and `-mgain 0.95` cells (22 and 29 min), ending well
before 07:00. Scored by the frozen [t_score.py](results/wsclean38-rebaseline-scripts/t_score.py).
The compact tables and the clean-runs reading come from
[t_tables.py](results/wsclean38-rebaseline-scripts/t_tables.py), which reports only and decides
nothing. Archive: [t-score.json](results/wsclean38-rebaseline/t-score.json),
[t-notes.txt](results/wsclean38-rebaseline/t-notes.txt),
[t-compact.md](results/wsclean38-rebaseline/t-compact.md),
[t-clean-reading.json](results/wsclean38-rebaseline/t-clean-reading.json). The FITS and logs stay
in `D:\rang\outputs\wsclean38-20261118\t` (308 job records).

**Spoiled runs.** 20 jobs in 18 cells had another process above half a core before or after:

| process | jobs |
| --- | ---: |
| chrome | 11 |
| svchost | 6 |
| MsMpEng | 2 |
| BackgroundDownload | 1 |
| dwm | 1 |

(One job had both MsMpEng and dwm, so the rows sum to 21.)
- Two repeated cells have two spoiled runs each: 3.7 S1 nominres `-j 16`, and GeMClean coarse H1
  `-j 16`. So not every cell keeps two clean runs, and the rule ran on all runs, as section 5 says.
- The driver does not rerun spoiled jobs at the end, although time allowed. None was repeated.
- Both readings:

| set | all runs (the rule) | clean runs only (reported) |
| --- | --- | --- |
| B `-j 16` 3.8 | S1-S3, H1, H3, H4 | S1-S3, H1, **H2**, H3, H4 |

- Every other lead set is the same in both readings.
- H2's change in the clean reading comes from dropping the one spoiled `-mgain 0.9` run, so H2 at
  `-j 16` is on the edge in pair B (gc/WSClean 1.01-1.03 in all runs).

**Lead sets** (skies where GeMClean's median is lower):

| pair | threads | 3.7 | 3.8 |
| --- | --- | --- | --- |
| A, default against `nominres` (1e-6) | 16 | all seven | all seven |
| A | 1 | all seven | all seven |
| B, coarse against WSClean's best `minres` (1e-4) | 16 | S1-S3, H1, H3, H4 | S1-S3, H1, H3, H4 |
| B | 1 | H4 | **S1, S2, S3**, H4 |

- **As frozen: outcome changed.** In B at `-j 1`, S1, S2 and S3 move into GeMClean's lead
  against 3.8.
- Ratios gc / WSClean best, 3.7 then 3.8: S1 1.05 then 0.94, S2 1.04 then 0.95, S3 1.12 then 0.99.
- WSClean's best at `-j 1` is `-mgain 0.9` on every sky for both versions, and those cells are one
  run each. S3's 0.99 is within a single run's noise.
- The other three pair-by-threads sets are unchanged.

**3.8 against 3.7** (3.8's median faster or slower than 3.7's by more than the larger repeat
spread; the full table is in t-compact.md):

| setting | `-j 16` | `-j 1` |
| --- | --- | --- |
| `minres` | slower on S2 (1.060) and S3 (1.044); faster on H3 (0.964); level on S1, H1, H2, H4 | **slower on all seven**, 1.059 (H3) to 1.229 (S1); S1 64.0 s against 52.1 s |
| `nominres` | level on all seven | level, except faster on S2 (0.981) |

- The `-mgain` cells are one run each, with spread 0. Any difference gets a verdict, so they are
  read as indications only:
  - `-j 16`: between 0.979 and 1.077, mixed;
  - `-j 1`: slower on all 14, 1.018 to 1.144.
- In short: at one thread, WSClean 3.8's `minres` (1e-4) path is 6-23 % slower than 3.7's. At
  1e-6, `nominres`, the two versions are level. At 16 threads they are level within a few percent.

**Host control.** Tonight's 3.7 medians against gemclean-speed's 2026-11-04 medians: every ratio
lies between 0.942 and 1.040. No sky differs by more than 10 %, so there is **no host change**.

| | lowest ratio | highest ratio |
| --- | ---: | ---: |
| `-j 16` minres | 0.960 | 1.040 |
| `-j 16` nominres | 0.942 | 1.024 |
| `-j 1` minres | 0.968 | 1.002 |
| `-j 1` nominres | 0.956 | 1.000 |

**What this does to H-speed** (reported; any change to docs wording is the owner's decision,
section 6):
- "At `-j 16` GeMClean is faster on all seven skies" holds against both versions in pair A.
  In pair B it holds on six of seven against both, missing H2 at 1.03 and 1.01.
- "At `-j 1` WSClean is faster on H1-H3 at its best setting" is exactly true against 3.8 tonight.
  Against tonight's 3.7, whose best is the one-run `-mgain 0.9` cell, WSClean is also faster on
  S1-S3.

## For the coordinator

- All four arms measured. T is changed, but only in pair B at `-j 1` (S1-S3). WSClean 3.8 is
  6-23 % slower than 3.7 at one thread with `minres`, and level elsewhere.
- Owner decisions, asked once:
  - docs wording for gemclean-speed's `-j 1` statement. It is exactly true against 3.8; against 3.7
    tonight, WSClean's one-run `-mgain 0.9` cell is also faster on S1-S3;
  - whether 3.8 becomes the speed oracle;
  - whether the 3.8 `-j 1` minres slowdown is worth a WSClean issue (U-style finding; not filed).
- Run roots kept: `D:\rang\outputs\wsclean38-20261118` (T's FITS, 308 job records) and
  `nash:~/rang-data/outputs/wsclean38-20261118`.

