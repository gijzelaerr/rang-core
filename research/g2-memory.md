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
