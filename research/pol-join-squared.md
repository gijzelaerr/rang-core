# Rang: joined polarisations on the squared sum (issue #22)

Status, 2026-11-13: **upstream checked; proposal frozen; nothing implemented or measured.**
Implementation waits for v0.2.0's E6 (`research/roadmap.md`, branch `roadmap-v030`). Issue
[gijzelaerr/rang-core#22](https://github.com/gijzelaerr/rang-core/issues/22). Gap measured in
[g9-stokes.md](g9-stokes.md) (section 5, P1-Q6; section 8, decision 1).

## 1. Upstream status (read 2026-11-13, about 10:00-12:00 UTC)

**Upstream has not moved to the sum of squares. It moved the other way: the linear sum is kept
and documented, and squares stay behind `-squared-channel-joining`.**

- **WSClean issue #207** ([work item](https://gitlab.com/aroffringa/wsclean/-/work_items/207),
  filed 2026-11-12 by the owner from G9's finding, closed 2026-11-13 by A. Offringa through !1070).
  Its discussion was not readable without a login (API 401); the reasoning below is from the
  merge requests only.
- **WSClean !1070** ("Fix some inaccuracies in the RM documentation", merged 2026-11-13, squash
  `11975412`): `doc/source/rm_synthesis.rst` now says that `-pol QU -join-polarizations
  -channels-out 100` finds peaks in "Q + U ... This is not ideal, because Q and U might cancel when
  they have opposite sign", and drops the example that claimed `√(Q² + U²)` for `-join-channels`
  without `-squared-channel-joining`. The squared route it documents is `-join-polarizations
  -join-channels -squared-channel-joining` (peaks in `Σ_ch Q_ch² + U_ch²`).
- **WSClean !1068** ("Fix an issue in CalculateMsLimits", merged 2026-11-13, master `53e25d59`)
  is not about the join. It fixes #208 (also the owner's): `CalculateMsLimits` tested the second
  image axis with `u` instead of `v` (`const double y = v * ...`). That is the rule G5 copied
  into GeMClean's theoretic beam and scale selection ([g5-multiscale.md](g5-multiscale.md),
  section 1). A finding for the coordinator, not for this note (section 6).
- **`wsclean --help` on master** (`main/commandline.cpp:467-470`) still says `-join-polarizations`
  searches "in the sum of squares of the polarizations". The help text was not changed by !1070.
- **radler `main`** (the default branch; `master` is empty), head `109057de` (2026-11-12, "Improve
  the speed of the RM transformation"); WSClean master pins radler `703c1bd7`
  (`CMakeLists.txt:11`, after !1055), its parent. At `109057de`: `generic_clean.cc:70` (first peak
  of a major iteration) and `subminor_loop.cc:49, 179` (the fast sub-minor loop) read
  `GetLinearIntegrated`; `generic_clean.cc:197` (`-no-fast-subminor`, after the first pick) and
  `multiscale_algorithm.cc:820, 832` (`FindSquaredScaleConvolvedMaxima`) read
  `GetSquareIntegrated`; `image_set.h:161-166`: `GetLinearIntegrated` returns the squared form
  when `square_joined_channels_` (the `-squared-channel-joining` flag) is set. The same as 3.7.
- **radler !238** ("Make peak finding consistently use linear or squared values", opened
  2026-11-12 by A. Offringa, **open, not merged**, two notes, not approved): renames
  `GetLinearIntegrated` to `GetIntegrated` (linear unless `-squared-channel-joining`) and makes
  every peak search use it, including `generic_clean.cc:197`. Its description: "Multiscale and the
  subminor loop use linear integration. Hence, in this MR GenericClean is changed so it also always
  uses linear integration." It also changes `GetSquareIntegrated`'s normalisation to the square
  root of the weighted mean of squares over every entry (tests in `test_image_set.cc`: for two
  channels of I, `√(½(12² + 13²))` in place of 12.5). After !238 the only squared peak search is
  `-squared-channel-joining`.
- **WSClean's settings** (`main/settings.cpp:617`) pass `squaredJoins` to radler without checking
  `-join-channels`; the help says "Use with -join-channels". Whether WSClean 3.7 accepts
  `-squared-channel-joining` with one output channel, and whether radler then squares over the
  polarisations of that channel, was **not run** (stage 0 below).
- GeMClean refuses `-squared-channel-joining` (`core/src/gemclean/cli.rs:562`, G3 owner
  decision 4).

**Consequence for #22.** #22's plan step 1: "If the join is already changed upstream, the task
becomes match upstream and measure, with no novelty claim." Upstream did not change the join; it
documented the linear sum as the default and named `-squared-channel-joining` as the squared
route. So the change proposed here is **to match upstream's squared route** (GeMClean's
`-squared-channel-joining` as WSClean 3.7 computes it, oracle WSClean 3.7 with the same flag) and
measure what it buys on Q/U-cancelling components. A squared polarisation join is standard in
RM-CLEAN practice (peaks in |P|, Heald, Braun and Edmonds 2009) and in WSClean itself: **no
novelty claim.** GeMClean's default stays linear, byte-identical to main.

## 2. Hypothesis and what is not claimed

Hypothesis: with polarisations joined, peak finding on WSClean's squared form
(`-squared-channel-joining`) recovers the linear-polarised components whose Q and U cancel in the
linear sum, so their polarised truth error drops to at most half the linear join's, with Stokes I
unchanged and at most one extra major cycle.

Not claimed: anything about RM synthesis (`-fit-rm`), circular feeds, XY/YX, `-link-polarizations`,
multiscale with several polarisations (refused, [g9-stokes.md](g9-stokes.md) section 12), real data,
timing.

## 3. Data (registered now)

- **P1** (development): G9's P1 MS, read in place, `D:\rang\outputs\g9-20261107-02\data\P1.ms`
  (seeds 20261181 sky, 20261182 noise; 36 points, 27 polarised, dec −30).
- **H1p** (held out for this hypothesis): G9's H1p MS, `D:\rang\outputs\g9-20261107-03\data\H1p.ms`
  (sky `0x210f9de0`, noise `0xb0eaa431`, dec −45). G9 read H1p once for Q0-Q5; it never ran a
  QU-joined configuration (Q6, Q7) on it, so H1p is unseen for this hypothesis. Its IQUV run (Q2)
  is a second read and is labelled as such.
- **H2p** (held out, new, drawn after the freeze): P1's recipe (`examples/g9_stokes_simulate.py`)
  at dec −60 with every polarised component's χ0 kept, except that a third of the linearly
  polarised components (every third in catalogue order) get RM = 0 and χ0 = 67.5° or −22.5°
  (alternating) plus a uniform offset in [−5°, 5°], so that `Q_T + U_T` nearly cancels. The recipe
  is added to the simulator as `--sky H2p` with the implementation, before the freeze; its seeds
  are the first 8 and the next 8 hex digits of `sha256("<full freeze commit> <binary sha256> H2p")`;
  if either equals a value of `rang.simtruth.SEEDS`, of G9's (20261181-84) or G3's (20261161-72),
  or E0's (20261191-93), the next 8 digits are taken. Drawn once; not redrawn.
- **Cancelling subset** of a sky: the (component, output channel) pairs scored for linear
  polarisation by G9's D with `|Q_T + U_T| / (2 P_T) ≤ 0.25` (truth only; on P1-Q6 the 33 failing
  pairs had a median of 0.12 and the 37 passing 0.54).

## 4. Arms and settings

G9's settings (section 3 of [g9-stokes.md](g9-stokes.md)) for both imagers: `-size 2048 2048
-scale 1.5asec -weight briggs 0.5 -niter 1000000 -gain 0.1 -nmiter 1000 -data-column DATA
-field 0 -abs-threshold 0.00015 -j 16`; GeMClean default form; WSClean 3.7
`rang-wsclean-native:3.7` with `-gridder wgridder -no-min-grid-resolution -wgridder-accuracy 1e-6
-mgain 0.8 -nmiter 0 -no-update-model-required`, its default (fast sub-minor) loop.

| config | options |
| --- | --- |
| Q6 | `-pol QU -join-polarizations -channels-out 4 -join-channels` (G9's Q6) |
| Q7 | `-pol QU -join-polarizations` (one output channel) |
| Q2 | `-pol IQUV -join-polarizations` (carries the Stokes I check) |

Arms per configuration: **WL** WSClean linear (default), **WS** WSClean `-squared-channel-joining`,
**GL** GeMClean linear (main's binary), **GS** GeMClean `-squared-channel-joining`. On Q7 and Q2
the WS and GS arms exist only if stage 0 shows that WSClean 3.7 accepts the flag with one output
channel and squares over polarisations there; otherwise Q7 and Q2 drop their squared arms, the
note records it, and the I check moves to Q2 with `-channels-out 4 -join-channels` (Q2′).

## 5. Measures, tolerances and the decision rule (frozen)

Scorer: G9's `score.py` ([results/g9-stokes-scripts](results/g9-stokes-scripts/score.py)), its
criteria D (polarised truth), D′ (parity), C′ (leakage, common beam) and E (cleaned images against
WSClean, relative to Q0), unchanged. `err` of a scored (component, channel) pair is D's
`|(F_Q − Q_T, F_U − U_T)| / P_T`. Major cycles from each log.

**Parity (numerical correctness first, before any quality number counts).** GS against WS on P1
and on both held-out skies: G9's B (dirty images, PSFs, headers), E and D′ with GS in GeMClean's
place and WS in WSClean's. A failed parity check stops the measurement; the implementation is
fixed (post-hoc label if after the freeze) or the outcome is recorded as **failure (no parity)**.
GL against main: byte-identical on G9's identity set (criterion A, 100 FITS files) and on H1p-Q2
(17 files against the frozen G9 binary's).

**Quality, per held-out run (H1p-Q6, H1p-Q7, H2p-Q6, H2p-Q7).** `R` = median `err` of GS over the
cancelling subset divided by GL's median over the same pairs. Clauses:

- (a) `R ≤ 0.5`;
- (b) median `err` of GS over the non-cancelling scored pairs at most GL's + 0.005;
- (c) Stokes I (Q2 or Q2′ on H1p and H2p): GS against WL within G9's E bounds for I (`d_rms ≤
  max(1.5 X_rms, X_rms + 0.1)`, `d_max ≤ max(1.5 X_max, X_max + 100 µJy)` relative to Q0), and the
  paired median of GS's I `err` minus GL's at most 0.005;
- (d) GS's major cycles at most GL's + 1 on every run.

Outcomes, read from the held-out runs only (a sky with an empty cancelling subset is reported and
does not count):

| outcome | rule |
| --- | --- |
| **gain** | (a)-(d) on every counted run |
| **partial** | (b)-(d) hold, `R ≤ 0.9` on every counted run, (a) fails on at least one |
| **null** | (b)-(d) hold and `0.9 < R ≤ 1.1` on any counted run |
| **failure** | `R > 1.1` on any counted run, or (b), (c) or (d) fails, or no parity |

With a gain the result is reported upstream on WSClean (the `-join-polarizations` help text, and
the measured benefit of squares for QU joining); with any other outcome it is recorded here. No
GeMClean default changes in any case; the owner decides.

**Cost.** Wall time and peak RSS of every run, at `-j 16` on a shared host under the heavy lock
(shared slots); reported, not gated (no timing claim). Major cycles are gated by (d).

## 6. Stages and stop rules

0. **Probe** (WSClean only, no rang code): G9's two-source probe MS
   (`D:\rang\outputs\g9-20261107-01-probe`), `-pol IQ -join-polarizations -niter 1` with
   `-squared-channel-joining`, at one output channel and at `-channels-out 4 -join-channels`.
   Record whether WSClean 3.7 accepts the flag and whether the first component lands on A
   (squares) or B (linear). This fixes section 4's Q7/Q2 arms. Not scored.
1. **Implement** (after E6) `-squared-channel-joining` in gemclean as radler 3.7's
   `GetSquareIntegratedWithSquaredChannels` and its use in the first peak and the sub-minor loop
   (`image_set.h:161`), with joined polarisations and joined channels; component values stay per
   entry. `rang-core image` passes `image.squared_channel_joining`. Unit test: the probe's two
   sources pick A.
2. **Identity**: GL byte-identical (section 5).
3. **Development** on P1 (Q6, Q7, Q2): parity, then the quality clauses, reported. No tuning: the
   rule has no free parameter. A development failure is recorded; it does not stop the held-out
   run unless parity fails.
4. **Freeze**: commit and binary sha256 recorded here before H2p is drawn; H2p drawn; then the
   held-out runs once.
5. **Report**: the outcome under section 5, every arm, both skies; if gain, the upstream report.

## 7. For the coordinator

- !1068 fixes the `u`-for-both-axes rule in WSClean's `CalculateMsLimits` that G5 ported into
  GeMClean's theoretic beam (`g5-multiscale.md`, section 1). WSClean 3.8 will compute a different
  theoretic beam (and so different default multiscale scales) from 3.7 where `|v|` limits differ
  from `|u|` limits; GeMClean matches 3.7. A follow-up issue, not part of #22 or #23.
- The `-join-polarizations` help text on WSClean master still says squares; #207 is closed by a
  docs change only. Whether to ask for the help text too is the owner's call.
