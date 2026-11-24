# Rang: the default self-calibration run within the default memory limit, the image stage (issue #34)

Status, 2026-11-24: **measured (section 6): stage A passes E and P; the default self-calibration on the
pilot peaks at 7.53 GiB (was 9.30) under the default 8 GiB, images and gain stores identical.** Frozen in
`68be3fa9` before any code; sections 1-5 unchanged since. Branch `selfcal-mem-34`.
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

Measured 2026-11-24 on **nash** (heavy lock, shared, `nice -n 19 ionice -c3`; each pipeline 8 slots, 16
GB, `RAYON_NUM_THREADS=8`). `cal2.ms` copied from the workstation (`D:\rang\outputs\
20261103-gemclean-heldout\real`, 8.1 GB, 27 min) to `~/rang-data/outputs/selfcal-mem-34-20261124/
inputs/real/`; `selfcal_grid.py base` 88 s, `prepare D` 32 s (and again for M1's own copy, from the same
base). M0 ran main `6f438bc9` (receipt `commit.head`, not dirty) in the worktree; M1 ran the branch at
`bd4d6105` (stage A; receipt `commit.head`, not dirty) in a scratch checkout with its own venv and
extension, on its own copy of the pilot. They overlapped from 07:56 to 08:27 UTC. Scripts, logs, run
comparison, both selfcal summaries and the round-1 GeMClean reports:
[results/selfcal-mem-34/](results/selfcal-mem-34/).

**M0 (main), the "before".** Whole run `%M` 9,748,640 KiB (9.30 GiB, the 2026-11-17 figure was 9,748,364),
2,533 s. The rang-core process peaked at 6,722 MiB (`peak_rss_mb`). GeMClean's `peak_memory_bytes`:
9,982,607,360 (round 1), 9,974,079,488 (round 2), 9,971,126,272 (final). So #32's V1 did not touch this
path: the single-image `deconvolve` kept the dense visibilities (1.623 GB, complex f32) and weights (1.623
GB, f64) of all 203 M cells through the clean, although 76,089,333 (37 %) are weighted. Its heap peaked at
10.06 GB in the major cycles (dense arrays 3.25 GB, gridder grids 1.66, the plan's sorted values 1.22, 11
images 1.48, beam 1.07).

**Stage A.** After the beam and the misfit floor, the single-image path calls `compacted()`, as the
channel and polarisation paths do: only the active visibilities and weights are kept, sorted in the
plan's order, and residuals read the same values from the same places. One change in
`core/src/gemclean/cli.rs`. `-no-plan-reuse` (no plan) and the misfit floor (which needs the dense
`gram_apply`, so compaction comes after it) are unchanged.

| gate | measured | verdict |
| --- | --- | --- |
| E, identity on the pilot | `compare_runs.py M0/run M1/run`: 98 files identical, all 15 FITS (3 images x 5) and every file of both gain stores (`gains.qc`, Sp and Sa) included; the 8 that differ are the 3 `gemclean.log`, the 3 `image-report.json` (argv paths, timings, memory), `summary.json` and `state.json` (paths, timings, flag-version name, the binary's hash). Solver records (iterations, converged fraction, flags) equal | **pass** |
| E, identity sweep | gemclean-mem-32's 21 cases plus 8 single-image Stokes I cases (`-double`, accuracy 1e-6, multiscale, multiscale masked, `-floor-iterations`, `-stop-rule certified`, `-gram-operator`, `-no-plan-reuse`): main's binary against the branch's, without and with `-reorder`, exit code, every FITS SHA-256, report entries and mask equal, 29/29, nothing left behind ([sweep.json](results/selfcal-mem-34/sweep.json)) | **pass** |
| P, the default fits | M1 whole run `%M` 7,890,824 KiB (7.53 GiB) against 8,388,608 KiB (0.941 of the limit); GeMClean 8,079,613,952 / 8,080,203,776 / 8,079,118,336 bytes; rang-core 6,726 MiB | **pass** |

Where the peak is now: GeMClean's heap peaks at 8.04 GB in the 2n PSF pass (dense arrays held while the
2n grid is gridded); the clean peaks at 8.03 GB. The measurement's arrays fell from 3.25 to 1.22 GB.

**Reported, not gated.** M1 took 2,087 s against M0's 2,533 s, but the two overlapped only partly on a
shared host, so this is no speed figure. M0's FITS differ from the 2026-11-17 run's (GeMClean changed
between, as section 1 expected); its gain stores were not archived then, so that comparison is not made.

**Outcome.** Stage A passes E and P: it is kept. The default self-calibration on the pilot runs within the
default `data.memory_limit_gb: 8`, whole run included. Stage B and gate Q were not needed. Item 1 of #34
(solve) and item 3 (planner) were done in `281a1a79`; this closes the remaining part. The margin is 6 %
of the limit on this pilot at 4096²; GeMClean still does not read `data.memory_limit_gb`, so a larger
image or MS can exceed it (section 7). No novelty or speed claim.

## 7. For the coordinator

- **Branch `selfcal-mem-34`, not merged.** `tools/check_all.py --quick` on glacier; CI on the branch; the
  full check (oracles, archive) is left to the merge check.
- **#34 can close** after the merge: the default run fits at 8 GiB (7.53 GiB whole run). The brief's 37 GB
  and "13.6 against 11.7" figures were from before `281a1a79`.
- **Open, not done here:** GeMClean has no memory limit of its own, and no estimate of its peak is
  checked against `data.memory_limit_gb` (stage B of section 2 was not needed). Whether to add one is an
  owner decision; the next peak to cut is the 2n PSF pass (8.04 GB here).
- **Left on nash:** `~/rang-data/outputs/selfcal-mem-34-20261124/` (the `cal2.ms` copy 8.1 GB, base and
  two pilot copies, both runs, binaries) and the scratch checkout `~/Build/tmp/20261124-selfcal-mem-34/arm`.
  Deleted when this task ends (see the hand-back).
