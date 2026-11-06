# Rang: GeMClean's peak memory (task G2)

Status, 2026-11-06: **in progress.** The rule below was written and committed before the first
comparison. Breakdown, changes and results follow as they are measured.

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
