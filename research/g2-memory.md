# Rang: GeMClean's peak memory (task G2)

Status, 2026-11-06: **measured; the pilot fits 24 GB at 512 channels** (19.7 GB peak RSS in the
default form, 15.7 GB coarse; WSClean 8.35 and 7.77 GB), with images byte-identical to the reference
on all seven skies in both forms and on the pilot-256. Four class-A changes; no default changed; no
novelty claim. GeMClean still holds 2.0-3.6× WSClean's peak. The rule below was written and committed
before the first comparison (`1a97192`).

Goal (finish plan, G2): the pilot fits 24 GB at 512 channels, with images identical, or within a
tolerance written first. If it cannot, say what it needs and whether 256 channels fits (A0's
fallback, `a0-acceptance.md`, E2 resources).

## The pilot

The real MeerKAT data the GeMClean notes call the pilot ([gemclean-heldout.md](gemclean-heldout.md),
sections 4 to 6): ESO 137-006, `ms1_target.zarr` MAIN_0, scan 2, 1 h, 61 antennas, 989.75-1096.54 MHz,
calibrated with the publisher's GKB-net gains (development data under A0).

- 512 channels: `D:\rang\outputs\20261103-gemclean-heldout\real\cal.ms` (823,500 cross-correlation
  rows, 9.7 GB, set A, received flags, 28.1 % flagged). GeMClean `f0ca931` passed 24.5 GB within
  about 50 s and was stopped there; WSClean imaged it.
- 256 channels: `real\cal2.ms` (2× averaged, set A, 4.9 GB); GeMClean needed 18.03 GB on it.

Settings, those of the held-out comparison: `-size 4096 4096 -scale 3asec -weight briggs 0.5 -niter 1000000
-gain 0.1 -nmiter 1000 -abs-threshold 0.003 -data-column DATA -field 0 -j 16`.

## Rule (written 2026-11-06, committed before the first comparison)

**Reference.** The `gemclean` binary at main `66c2967`, profile `gemclean`, built in this task
(`gemclean-66c2967`, sha256 `10e98c60…fb5094c`). Every candidate binary is built from a recorded
commit of `fp-g2-memory`.

**Image sets.** The seven simulated skies S1-S3 (`D:\rang\outputs\20261102-gemclean\bench\data`) and
H1-H4 (`D:\rang\outputs\20261103-gemclean-heldout\sim\data`), at the settings of G1: `-size 2048 2048`
(4096 for H3) `-scale 1.5asec -weight briggs 0.5 -niter 1000000 -gain 0.1 -nmiter 1000
-abs-threshold 0.0001 -data-column DATA -field 0 -j 16`, in two forms: the default (f64,
`-wgridder-accuracy` 1e-6) and the coarse form (`-single -wgridder-accuracy 1e-4`). Plus the pilot at
256 channels at the settings above (default form), where the reference binary fits.

**Class A: changes that do not alter arithmetic** (freeing or reusing buffers, not holding copies,
streaming in the same order, storing values in a narrower type that holds them exactly). The five
FITS files (`dirty`, `psf`, `model`, `residual`, `image`) must be byte-identical (SHA-256) to the
reference's on all seven skies in both forms and on the 256-channel pilot. One differing file
rejects the change, or moves it to class B.

**Class B: changes that alter arithmetic.** The bounds G1 used, against the reference, per sky:
restored-image rms of the difference ≤ 0.1 σ, largest difference ≤ 100 µJy, |ΔQ/Q_truth| ≤ 1e-3,
|Δ false flux| ≤ 1 mJy, scored as G1 scored them (`g1_beam_band_analyse.py`). None is planned; if one
is tried, its scoring is written here before it runs.

**Memory measure.** Peak RSS from GNU `time -v` (maximum resident set size) of the `gemclean`
process, each run under `flock ~/.rang-heavy.lock`. The binary's own allocation accounting
(`-memory-report`, below) gives the breakdown; the decision uses RSS. WSClean's reference: WSClean
3.7 in `rang-wsclean-native:3.7` at matched settings (`-gridder wgridder -no-min-grid-resolution
-wgridder-accuracy 1e-6 -mgain 0.8 -pol I`, the same size, scale, weighting, threshold, `-j 16`),
with `time -v` inside the container, as `examples/gemclean_bench_run.sh` does.

**Swap.** The host has 30 GB, shared with other agents, so a large run can be partly swapped out, and
then its peak RSS under-reports. `-memory-report` records `VmSwap` at every phase. A run counts only if
`VmSwap` is 0 at every phase; otherwise it is repeated, and if that fails the heap peak plus the
non-heap offset measured on the same sky is reported instead, marked so. Runs that may pass 24 GB
are watched every second and stopped at 24 × 10⁹ bytes of RSS, so the host is not pushed into swap.

**WSClean's memory budget.** WSClean sizes its work by its memory budget. The references here use its
default (no `-mem` or `-abs-mem`), as the simulated-sky benchmark did; the held-out pilot runs used
`-abs-mem 20`, which is stated wherever one of them is quoted.

**Both forms.** Whether the pilot fits 24 GB at 512 channels is reported for the default form and for
the coarse form, since G7 has not chosen the default.

**A change is kept** if its image rule holds and it lowers peak RSS on S1, H3 or the pilot by at least
1 % and 50 MB, and raises none by more than that. **Fits 24 GB** means a peak RSS of at most
24 × 10⁹ bytes. Wall times are recorded with the caveat that a Windows process holds one core; no
speed claim is made either way.

## Allocation accounting (implemented)

`-memory-report` prints, per phase of a run, the heap the process holds at the end of the phase and the
most it held during it, with the RSS beside them, then the sizes of the main buffers. The same is
written to `-report.json` as `memory`. The counts come from the binary's allocator
(`gemclean::host::HugePageAlloc`), two relaxed atomics per allocation
([`gemclean/memory.rs`](../core/src/gemclean/memory.rs)); the Python extension does not count.
Phases: `read`, `weights`, `compact`, `measurement`, `psf 2n`, `beam`, then per major cycle
`residual: predict`, `residual: grid` and `cycle k: minor`, `clean: end`, `write`.

## Where the peak comes from (measured, before any change)

Runs of 2026-11-06, `D:\rang\outputs\20261106-g2-memory\runs\{base,instr}`: `base` is the reference binary
`66c2967`, `instr` the same code with the accounting (`1a97192`, sha256 `ca364c1a…557ead4`). **The accounting
changes no image:** all five FITS files are byte-identical to the reference's on the seven skies in both
forms and on the 256-channel pilot (15 runs, [identity.py](results/g2-memory-scripts/identity.py)), and
peak RSS agrees within 0.13 GB (H3: 6.11 against 5.98 GB; the rest within 0.02 GB). That spread on H3 is
the run-to-run noise of RSS there.

Heap in GB (10⁹ bytes), the most held during each phase; the per-cycle phases give their largest value.
Pilot-256: 792,626 rows × 256 channels = 202.9 M cells, 152.2 M of them active (nonzero weight).

| phase | S1 (2048²) | H3 (4096²) | pilot, 256 channels (4096²) |
| --- | ---: | ---: | ---: |
| read | 0.58 | 0.58 | 8.67 |
| weights | 0.66 | 0.67 | 9.12 |
| compact | 1.10 | 1.10 | 15.81 |
| measurement | 1.11 | 1.17 | 14.34 |
| psf 2n | 3.06 | 4.10 | 14.52 |
| beam | 1.26 | 2.93 | 10.06 |
| major cycles (predict, grid) | **3.44** | **6.09** | **18.44** |
| peak RSS, `time -v` | 3.46 | 5.98 | 18.19 (swap 0.34 at the end: the heap is the better figure here) |
| WSClean `nominres` peak RSS | 0.82 | 1.89 | 4.95 |
| WSClean `minres` peak RSS | 0.58 | 1.13 | – |

Buffers held through the major cycles, GB (the pilot's per-cell share in bytes):

| buffer | S1 | H3 | pilot-256 | bytes per cell (c) or active (a) |
| --- | ---: | ---: | ---: | --- |
| measurement visibilities, `Complex<f64>` | 0.23 | 0.23 | 3.25 | 16 c |
| measurement weights, normalised | 0.12 | 0.12 | 1.62 | 8 c |
| residual visibility buffer | 0.23 | 0.23 | 3.25 | 16 c |
| gridding weights, kept by the binary after the copy | 0.12 | 0.12 | 1.69 | 8 c (a duplicate) |
| gridder sorted index | 0.12 | 0.12 | 1.22 | 8 a |
| gridder stored values | 0.23 | 0.23 | 2.44 | 16 a |
| gridder grids (plane group 4) | 1.45 | 1.66 | 1.66 | fixed |
| beam: exterior, spectrum, resync rows | 0.34 | 1.34 | 1.34 | fixed |
| the 2n PSF, kept to the end for a crop | 0.13 | 0.54 | 0.54 | fixed (a duplicate) |
| n × n images in the loop, about 8 | 0.27 | 1.07 | 1.07 | fixed |

What this says:

- **On the simulated skies the fixed buffers dominate**: the gridder's grids (four planes at once,
  `PLANE_GROUP` 4 within 2 GiB), the beam's three `(2n)²` tables and the images. The visibilities are
  14.5 M cells. GeMClean holds 4.2× WSClean's `nominres` peak on S1 and 3.2× on H3.
- **On the pilot the per-visibility buffers dominate**: 48 bytes per cell (16 + 8 + 16 + 8) and 24 per
  active visibility in the major cycles. 3.7× WSClean's peak.
- **The early phases waste**: `read_ms` grows its arrays by doubling, so the Stokes I visibilities
  hold 5.24 GB of capacity for 3.25 GB of values (and pass through up to three times their size while
  growing); the compaction copies the visibilities and weights into new vectors, again grown by
  doubling, while the originals and the gridding weights are still held (15.8 GB);
  `GridMeasurement::new` copies them once more, even where the conversion is to the same type.
- **The 2n PSF** pass builds its own sorted index and stored values (24 bytes per active visibility)
  and a grid on the 2n side: 6.1 GB above what is held, on the pilot-256.
- **Pilot at 512 channels, the reference binary** (`base/p512-def`, stopped at 20 × 10⁹ bytes so the
  shared host would not swap): read finished at 24 s at about 12.8 GB RSS, the weights at 30 s, and
  the compaction passed 19.7 GB at 40 s, when the watchdog stopped it. Scaling the pilot-256 buffers
  to 405.8 M cells and 303 M active visibilities: about 31.6 GB in the major cycles (48 × 405.8 M +
  24 × 303 M + 4.8 GB fixed), and the compaction about as much. The held-out note's "about 33 GB" is
  this.
- **WSClean at 512 channels** (default memory budget): 8.35 GB `nominres`, 7.77 GB `minres`.

So 512 channels cannot fit by trimming the fixed buffers; it needs the per-cell bytes down. Planned
class-A changes, each byte-identical by construction (the rule above decides):

1. read at the exact size (count the rows first), Stokes I held in `f32` as formed (exact to widen);
2. compact in place, drop the gridding weights after the copy, shrink large blocks in place;
3. hold the measurement's visibilities in `f32` where they came in `f32` (widened where used);
4. form the residual in the gridder's sorted stored values instead of a visibility-sized buffer,
   with the misfit still summed serially in visibility order through a permutation (4 bytes per active
   visibility), where the zero-weight visibilities add exactly zero to it;
5. drop the 2n PSF after the beam is built, keeping its n × n crop.

Expected at 512 channels, default form: 16 bytes per cell + 28 per active visibility + about 4.3 GB,
about 19.3 GB in the major cycles. An estimate, to be measured.

## Changes and what each saved (measured)

Each change is class A. Each was built from its commit on `fp-g2-memory` (or from a tree checked to be
identical to it), run on the full identity set (seven skies in both forms and the 256-channel pilot,
15 runs), and compared file by file with the reference. **All five FITS files were byte-identical in
all 15 runs after every change**, and the pilot-512 images after changes 2 and 3-4 were byte-identical
to each other. Binaries under `D:\rang\outputs\20261106-g2-memory\bin`; runs under `runs/<tag>`.

| change | commit, binary sha256 | what |
| --- | --- | --- |
| 0 | `1a97192`, `ca364c1a…557ead4` | the accounting only |
| 1 | `ae1f64f`, `0fc6f91d…7c63fa` | read at the exact size (rows counted first), Stokes I held in `f32` as formed; compact in place; do not keep the gridding weights beside the copy; the measurement holds `f32` visibilities as read and widens them where used; large blocks shrink in place (the allocator unmaps the tail) |
| 2 | `cf549d6`, `db646826…acbf407` | the residual is formed in the gridder's sorted stored values (`Prepared::residual`): prediction written in sorted order, subtracted there, turned into the data values there and gridded; the misfit is still summed serially in visibility order, through a permutation (4 bytes per active visibility), and only where every zero-weight visibility adds exactly zero to it (checked once; otherwise the old path) |
| 3, 4 | `83baf9f`, `647bc32a…620a0bfe` | 3: the 2n PSF is cropped to the n × n image written at the end and freed before the run; 4: the 2n PSF is formed before the plan of the image grid (`from_single_unprepared`, then `prepare`) |

A unit test checks change 2 bit for bit against the dense path in both precisions, with single- and
double-precision data, zero weights, the w-term and a shifted centre, over repeated calls
(`sorted_residual_has_the_bits_of_the_dense_one`).

Peak RSS, GB (`time -v`), default form, with the largest heap and its phase:

| run | reference `66c2967` | 0 | 1 | 2 | 3, 4 | WSClean `nominres` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| S1 | 3.46 | 3.46 | 3.23 | 3.09 | **2.99** (cycles) | 0.82 |
| H3 | 6.11 | 5.98 | 5.81 | 5.84 | **5.43** (cycles) | 1.89 |
| pilot, 256 channels | 18.44 | 18.19 (heap 18.44) | 15.13 | 12.57 | **12.23** (cycles) | 4.95 |
| pilot, 512 channels | stopped at 20.2 | – | stopped at 23.9 | 20.82 (PSF phase) | **19.72** (cycles) | 8.35 |

Coarse form (`-single -wgridder-accuracy 1e-4`):

| run | reference | 0 | 1 | 2 | 3, 4 | WSClean `minres` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| S1 | 2.50 | 2.50 | 2.38 | 2.38 | **2.20** (PSF phase) | 0.58 |
| H3 | 5.39 | 5.38 | 5.26 | 5.25 | **4.84** (cycles) | 1.13 |
| pilot, 512 channels | – | – | – | – | **15.66** (cycles) | 7.77 |

Per change (default form; the pilot from the heap, which the swap rule prefers there):

- **Change 1** saves 8 + 8 bytes per cell in the major cycles (the kept gridding weights, and half of
  the visibilities), and removes the growth slack and the copies of the early phases: pilot-256
  18.44 → 15.12 GB, S1 −0.23 GB, H3 −0.29 GB. The early phases on the pilot-512 now peak at 10.1 GB
  (the weights), from about 32 GB. Not yet enough at 512 channels: stopped at 23.9 GB in the first
  residual.
- **Change 2** removes the 16-byte-per-cell residual buffer for 4 bytes per active visibility:
  pilot-256 15.12 → 12.61 GB of heap, S1 −0.14 GB; H3 unchanged within noise (+0.02 GB RSS, −0.04 GB
  heap). With it the pilot-512 runs to the end: 20.78 GB of heap at its peak, now in the 2n PSF phase.
- **Change 3** frees the 2n PSF (0.54 GB at 4096², 0.13 GB at 2048²) for its crop: −0.40 GB in the
  major cycles at 4096².
- **Change 4** takes the plan's sorted index (2.4 GB at 512 channels) out of the PSF phase: on the
  pilot-512 the PSF phase falls from 20.78 to 18.27 GB of heap, below the major cycles (19.69 GB).

## The pilot at 512 channels (measured)

**It fits 24 GB in both forms**: 19.72 GB peak RSS in the default form (19.69 GB of heap), 15.66 GB
in the coarse form, with binary `83baf9f`, against 8.35 and 7.77 GB for WSClean (2.4× and 2.0×). The
256-channel fallback of A0 is not needed on GeMClean's account.

- Default form: 58,356 components, 4 major cycles, Q/Q0 2.6500e-2, 4 min 23 s on a busy host
  (`runs/c34/log/p512-def.log`); change 2's run gave the same images and the same line.
- Swap: in the default run another agent's work pushed 1.28 GB of the process to swap during the PSF
  phase (no swap at the peak, 0.002 GB). Under the rule the run was repeated (`runs/c34r`):
  19.69 GB peak RSS, no swap at any phase, the same five files. The heap
  peak, which swap does not touch, is 19.69 GB, so the decision does not rest on RSS.
- No reference image exists at 512 channels (the reference binary does not fit), so identity there
  rests on the 15-run set and the pilot-256, plus the agreement of changes 2 and 3-4 with each other.
- Headroom: 24 − 19.7 = 4.3 GB. The heap in the major cycles is about 16 bytes per cell (6.5 GB),
  28 per active visibility (8.5 GB) and 4.7 GB fixed (grids 1.66, beam 1.34, images and crop about
  1.2, tables and baselines). A 7-hour track at 512 channels would need about 7 × 15 GB + 4.7 GB,
  some 110 GB; this task does not change that conclusion of `gemclean-heldout.md`.

## Not changed: the plane group (measured, an option for G7)

The gridder holds `PLANE_GROUP` = 4 w-planes at once in the binary (within 2 GiB), 1.45-1.66 GB of
grids, the largest fixed buffer on the simulated skies. `RANG_WGRIDDER_PLANE_GROUP=1` with `83baf9f`:

| run | group 4 (default) | group 1 | group 2 (env, which also lifts the 2 GiB cap) |
| --- | ---: | ---: | ---: |
| S1, peak RSS GB | 2.99 | 1.89 | 2.65 |
| H3, peak RSS GB | 5.43 | 4.59 | 5.46 (the 2n PSF pass then takes two 2n planes) |
| pilot-512, peak RSS GB | 19.69 (repeat, no swap) | 18.89 | 21.62 |
| S1 / H3 / pilot-512 major-cycle seconds, busy host | 6.4 / 22.7 / 107 | 8.1 / 27.4 / 118 | – |

**The plane group is not bit-neutral, against what the code's comment and its test say.** Group 1 gave
byte-identical files on S1 and H3, but on the pilot-512 its `residual` and `image` differ from group 4's
(`dirty`, `psf` and `model` identical). Group 2 changes H3's `residual` and `image` in the same way, and
does so with the reference binary `66c2967` too (bisected: `66c2967`, `ae1f64f`, `cf549d6` and `83baf9f`
give the same residual hash under group 2, `5e1c8dfa…`, against the reference's `1ea26cf7…`). So the
prediction of a nonzero model depends on the grouping in some layouts, which this task did not cause and
did not chase; the models agree, so the loop's decisions did not change in these runs. Under the rule a
group change is therefore class B, and it is left alone: 1.1 GB on S1 and 0.8 GB on the pilot for, as
far as a busy host shows, about 10-25 % more major-cycle time. For G7 and for whoever owns the gridder.

## Timings (busy host; no speed claim)

A Windows process held one core and other agents' check-all and imaging ran at times, so wall times
moved by up to 3× between identical runs (H2: 22 s and 78 s, same binary class, same images). None
are read as speed changes. The sorted residual adds a serial pass through a permutation per major
cycle; on the pilot-512 the major cycles took 101-107 s against no reference (the reference does not
fit), and on S1 and H3 they were within the spread of the reference's.

## What was not checked

- Pilot-512 images have no reference to compare with (the reference binary does not fit); the class-A
  claim there rests on the 15-run set, the pilot-256 and changes 2 and 3-4 agreeing with each other.
- Only the default stop rule and options of the identity set were run: not `-stop-rule certified`,
  `-gram-operator`, `-no-plan-reuse`, `-floor-iterations`, `-beam-band` or `-beam-no-w` (the code paths
  for them still take the old route where they differ, and the unit tests pass).
- Pilot set B (extra flags) and the coarse form on the pilot-256 were not run; the coarse pilot-512
  has no reference.
- The Python extension and `rang-core image` use the library, not the binary: changes 2 and 4 apply
  to any `GridMeasurement`, changes 1 and 3 only to the `gemclean` binary.
- Not on an idle host; no timing claim.

## For the coordinator

- `research/README.md` index line: `[g2-memory.md](g2-memory.md) — G2: GeMClean's peak memory; the pilot
  fits 24 GB at 512 channels (19.7 GB default, 15.7 GB coarse), images byte-identical.`
- `research/STATE.md`: "GeMClean memory, 2026-11-06 (task G2; measured; [g2-memory.md](g2-memory.md)).
  Four class-A changes, byte-identical on S1-S3, H1-H4 in both forms and the pilot-256 under a rule
  written first: exact-size read with Stokes I in f32, in-place compaction, no kept weights, f32
  visibilities held as read; the residual formed in the gridder's sorted values (no visibility-sized
  buffer); the 2n PSF before the plan and freed after the beam. Peak RSS: pilot-512 from over 24 GB
  (about 32 estimated) to 19.7 GB (WSClean 8.35), coarse 15.7 (WSClean 7.77); pilot-256 18.4 to 12.2;
  S1 3.46 to 2.99 (WSClean 0.82); H3 6.11 to 5.43 (1.89). Still 2.4-3.6× WSClean. The pilot fits
  24 GB at 512 channels in both forms, so A0's 256-channel fallback is not triggered. Finding: the
  gridder's plane group changes predicted residual bits (group 2 on H3, group 1 on the pilot-512),
  in the reference binary too. No default changed; no novelty claim."
- `research/finish-plan.md`: G2 done; A0 E2 resources: "G2 measured 19.7 GB at 512 channels: E2-A and
  E3-A image at 512 channels." G3 unblocked. G7: the plane-group trade (1.1 GB on S1) needs a rule of
  its own, since it is not bit-neutral.
- New `CHANGELOG.md` lines under Unreleased (the memory change and `-memory-report`).
- Branch `fp-g2-memory`; data copies in `~/Build/tmp/20261106-g2-memory` were removed; outputs in
  `D:\rang\outputs\20261106-g2-memory`. The side worktree `~/Worktrees/rang/g2-base` (detached, scratch)
  was removed.
