# Rang: the default self-calibration run within the default memory limit, the image stage (issue #34)

Status, 2026-11-24: **proposed** (this note is committed before any code). Branch `selfcal-mem-34`.
Host for the measurements: **nash** ([nash-host.md](nash-host.md)), heavy lock, `nice -n 19 ionice -c3`.
Follows [selfcal-memory.md](selfcal-memory.md).

## 1. What is already done, and what is left

The brief for this task names the 37 GB scan-long solve and the planner's "13.6 GiB planned against
11.7 GB measured". **Both were settled on 2026-11-17 and merged in `281a1a79`** (selfcal-memory):

- item 1 of #34: the Sp and Sa `inf` solves stream when one interval does not fit; on the pilot they
  peak at 3.62 GiB under the default 8 GiB, bit-identical to the one-call solves at 96 GiB;
- item 3: `CELL_BYTES["selfcal"]` = 45 (600 s: plan 6.82 GiB against 5.99 GiB measured, 1.138 x). The
  11.7 GB of the issue was another stage's peak.

What keeps #34 open is the GeMClean child. In the default run on the pilot (D's config without
`memory_limit_gb`: 4096² at 3″, Briggs 0.5, `-j 8`) the rang-core process peaked at 6.6 GiB, the whole
run at 9.30 GiB (9,748,364 KiB), which is GeMClean's own `peak_memory_bytes`. GeMClean does not read
`data.memory_limit_gb`. Since then #32's V1 (compacted channel measurements, merged 2026-11-23,
0.944 × on case I) changed GeMClean's Stokes I path, so the 9.30 GiB is out of date. **This task is
about the image stage of the default self-calibration run; the solve is not touched.**

## 2. Steps

**M0, current main on the pilot.** The pilot is rebuilt as on 2026-11-17 (`selfcal_grid.py base`, then
`prepare D`, the 128 held-out channels flagged) from a fresh copy of `cal2.ms` in this task's own run
root, `~/rang-data/outputs/selfcal-mem-34-20261124`. Then `rang-core selfcal` with D's config without
`memory_limit_gb`, 8 slots, `RAYON_NUM_THREADS=8`, `image.extra_args: [-memory-report]` (it only
prints). Recorded separately:

- the whole run's `/usr/bin/time %M` (KiB; the largest process of the tree);
- the rang-core process's own `peak_rss_mb` (receipt);
- GeMClean's `peak_memory_bytes` per image (rounds 1, 2 and the final image) and its buffer report.

M0 is the "before" figure and the reference for equality: its gain stores and FITS hashes, not the
2026-11-17 archive's (GeMClean has changed since).

**Decision after M0.**

1. **Whole run at or below 8 GiB** (8,388,608 KiB): no code. The receipt and a timing row are
   recorded; the coordinator is advised to close #34.
2. **Above 8 GiB, stage A: an identical-output reduction** in the GeMClean path the self-calibration
   images take (Stokes I, one channel out, no joins), guided by M0's buffer report. #32's arms already
   measured and not adopted (beam spectra in the `-reorder` file, visibilities in the `-reorder` file)
   are not retried. Timeboxed to this task.
3. **If A does not reach 8 GiB, stage B: the image stage gets a memory estimate** (option 2 of the
   issue). An `image` figure, from the image size, the threads and the MS's visibility cells, predicts
   GeMClean's peak. Before each GeMClean run of `selfcal` and `image`, the estimate is compared with
   `data.memory_limit_gb`:
   - a limit **set in the configuration** below the estimate refuses the stage, and the message names
     the estimate in GiB and the key to raise;
   - the **default** limit below the estimate does not refuse: a run that completes today keeps
     completing. The stage summary records the estimate and a warning naming the figure. Whether the
     default should refuse instead is an owner decision (section 5).

## 3. Gates (frozen)

- **E, equality.** Every change keeps results: the after-run's gain stores (`np.array_equal`, every
  array), its FITS files (SHA-256) and the stage summaries' solver figures (iterations, converged
  fraction) equal M0's. Any difference is a defect; no tolerance applies. Stage B changes no
  arithmetic by construction, and E still runs on it.
- **P, the default fits** (stage A only): the whole run's `%M` at or below 8,388,608 KiB.
- **Q, the estimate** (stage B only): on the pilot at 4096² and at 2048² (a second run, the same
  config with `size: [2048, 2048]`), the estimate is at least GeMClean's measured
  `peak_memory_bytes` and at most 1.15 times it, for every image of the run.
- Tests: the refusal and the warning paths (synthetic, fixture); for A, the GeMClean identity tests
  that #32 uses (`core/tests/gemclean_memory.rs`, G8's sweep where it applies).

## 4. Decision rule

- M0 at or below 8 GiB: outcome "fits on main", no code.
- A passes E and P: A is kept, #34 can close.
- A fails P (or is not found within the timebox): B, kept if E and Q pass. #34 stays open for the
  GeMClean figure itself (#32's work), with the estimate documented.
- E fails: nothing is merged.
- No novelty or speed claim. This is a resource fix.

## 5. For the coordinator (open decisions)

- Whether the default limit should refuse a GeMClean run whose estimate is above it (stage B makes
  that a one-line change; this note keeps today's behaviour).

## 6. Results

(Filled in after the measurements.)
