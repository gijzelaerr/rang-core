# Rang: GeMClean's WSClean comparisons restated against WSClean 3.8

Status, 2026-11-18: **proposed; sections 1-6 frozen in this commit, before any WSClean 3.8 run.**
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
