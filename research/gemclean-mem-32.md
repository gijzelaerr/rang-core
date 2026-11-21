# GeMClean memory, phase 4 (issues #32 and #34): E2-N profile, beam spectra

Branch `gemclean-mem-32` from origin/main `73fe1111`. **Frozen 2026-11-21 before any code**; measured the same day: arm A not adopted (time), arm 0 kept, after
the profile in section 2 (a measurement of main, no change). Phases 1-3 are
[gemclean-memory.md](gemclean-memory.md), [gemclean-memory2.md](gemclean-memory2.md) and
[gemclean-memory3.md](gemclean-memory3.md). Bug-fix and resource work: no scientific claim. Results go
under "Measured"; anything later is a dated amendment.

## 1. The problem

Phase 3 left J1833−2103 (E2-B, joined IQUV, 2048²) at 5.73 GiB, 4.3 × WSClean 3.7's 1.34. #34 left
GeMClean's 9.3 GiB in E2-N's selfcal image. Both issues ask for peak memory within a stated factor
of WSClean's at identical images.

## 2. Profile of main on E2-N (nash, shared, 2026-11-21; before any change)

Inputs are own deep copies of `e2n-20261116/e2n.ms` (2,229,489 rows, 1,024 channels, DATA only):
`q.ms` (field 1, J1331+3030, scan 2, 139,934 rows) and `i.ms` (field 3, the target, scans 6, 8 and
10, 1,596,004 rows). Main's `gemclean` binary at `73fe1111` (`--profile gemclean`, counting
allocator) and WSClean 3.7 (`/usr/bin/wsclean`), `/usr/bin/time -v`, `-j 4`, sequential in one lock
hold (4 slots). Script: [results/gemclean-mem-32/profile.sh](results/gemclean-mem-32/profile.sh).

| Case | Settings | GeMClean peak RSS | WSClean peak RSS | Ratio | GeMClean wall | WSClean wall |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| **Q** | A5's argv (2048², 2″, Briggs 0, `-pol IQUV -join-polarizations -channels-out 8 -join-channels -auto-mask 5 -auto-threshold 3`, `-mgain 0.9`, niter 1e6) | 10.43 GB | 1.41 GB | **7.4 ×** | 2,051 s | 1,343 s |
| **I** | E2-N's image settings (4096², 3″, Briggs 0.5, 8 joined channels, `-fit-spectral-pol 2`, multiscale, auto-mask 5, `-average-channels 2` for GeMClean), **`-niter 20000`** on both to bound the run on uncalibrated DATA | 40.17 GB | 11.02 GB | **3.6 ×** | 6,208 s | 7,566 s |

**Case Q, traced at the minor cycle's peak (heap 10.61 GB):**

| Block | GB |
| --- | ---: |
| beams: 16 (two PSFs per channel: the parallel and cross hands carry different weights), exterior `(2n−1)²` f64 each | 2.146 |
| beams: resync spectrum (half spectrum `(n+1) × 2n` complex) each | 2.149 |
| 78 images `n²` f64 (32 residuals, 32 working maps, PSF crops, single maps) | 2.617 |
| measurement weights (32 entries) | 0.781 |
| gridder plans and sorted tables (many blocks of 0.07-0.14) | about 2.3 |
| uvw | 0.100 |

Q ran 3 major cycles and **352 resyncs (856 s of the 2,051 s)**, each over the 32 entries.

**Case I:** the joined-channel multiscale path writes no `memory` section (its report writer does not
call the memory report), so its 40 GB is not attributed. By the buffer sizes it holds 8 beams of
2 × 537 MB at 4096² (8.6 GB), the in-memory visibilities and weights of 1.6 M rows × 512 channels
(about 10 GB), the multiscale caches (up to `CACHE_BYTES` = 2 GB each) and the images. This is an
estimate, not a trace.

## 3. Arms (bit-identical by construction)

- **Arm 0 (no arithmetic):** the joined multiscale path's report gets the memory section, so case I
  can be traced.
- **Arm A, beam spectra in a spill file.** A beam's resync spectrum is a cache: computed once from the
  PSF, then read in every resync. With arm A the spectra of a joined run are written to one file
  beside the run's other temporary files (`-temp-dir`, `<name>-beams-<n>.spill`). Each resync reads
  a beam's spectrum back into one buffer shared by all beams. The bytes are equal, so the arithmetic
  is equal. Scope: the paths that already write temporary files, that is joined polarisations with
  `-reorder` (the default since phase 3); everything else is unchanged. Expected: −2.1 GB on Q
  (16 × 134 MB, less one buffer), +2.1 GB of reads per resync from the page cache (about 750 GB over
  Q's 352 resyncs).
- Not in this phase: the exteriors (every step gathers from them), the working maps and residuals
  (each resync and each step reads them), `f32` storage (changes bits). They are named as the floor.

## 4. Decision rule (frozen)

- **Identity (gate):** every FITS file and `image-mask.json` byte-identical to main on case Q, on
  G8's tiny-MS sweep (phase 3's `sweep.py`, all cases) and on the regression MS. The `gemclean_memory`
  tests pass. A failed identity rejects the arm.
- **Arm A is adopted** if, on case Q (nash, shared, the same lock booking, main and arm A in the same
  hour): tree peak RSS ≤ **0.85 ×** main's, and wall ≤ **1.10 ×** main's. If the wall ratio falls in
  1.05-1.15, a second pair is run and the means are used. Otherwise arm A is recorded and not merged.
- **Stated factor:** the result is reported as GeMClean / WSClean peak RSS on Q and I, whatever it is.
  No factor is claimed beforehand; the frozen target is the 0.85 above.
- Arm 0 is merged if its identity passes; case I's attribution is then recorded.

## 5. Not claimed

No speed or quality claim. WSClean's runs are the reference for memory only. Case I's `-niter 20000`
departs from E2-N's settings, so its peak may differ from the selfcal image's 9.3 GiB, which used
fewer rows per image.

## Measured (2026-11-21, nash, shared)

Code: arm A and arm 0 as [results/gemclean-mem-32/arm-a.patch](results/gemclean-mem-32/arm-a.patch)
on `73fe1111`. It was built as `gemclean-arm` in a nash worktree; main's `gemclean-main` was built
from the same commit without the patch. The four case-Q runs were in two lock holds of 4 slots,
in the order main, arm A (hold 1, 09:56-11:14 UTC) and arm A, main (hold 2, 12:52-14:07 UTC).
Receipts: [results/gemclean-mem-32/](results/gemclean-mem-32/).

**Identity (gate): met.**

| Check | Result |
| --- | --- |
| Case Q: main (three runs: `gq`, `mq`, `mq2`) against arm A (`aq`, `aq2`) | all 153 FITS and `image-mask.json` byte-identical |
| G8's tiny-MS sweep (phase 3's `sweep.py`, 21 cases): main's binary against arm A, without and with `-reorder -temp-dir` | all identical in both legs, no file left; the two refusal cases exit 2 with the same message in every leg ([sweep-armA.json](results/gemclean-mem-32/sweep-armA.json)) |
| `core/tests/gemclean_memory.rs` (three cases); new unit tests: a spilled spectrum gives the same bits (own buffers, and a work space shared with another convolver); `TempFile` complex f64 round trip | pass (glacier) |

**Arm A on case Q, against main:**

| Pair | Main peak RSS | Arm A peak RSS | Main wall | Arm A wall | Resync, main → arm A |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 10.433 GB | 8.466 GB | 2,184 s | 2,472 s | 955 → 1,276 s |
| 2 | 10.431 GB | 8.469 GB | 2,040 s | 2,343 s | 793 → 1,172 s |

- Memory 0.811 × main (limit 0.85): **met**. The heap at the minor cycle goes from 10.61 to 8.60 GB.
  The beam spectra go from 2.149 GB to 0, and nothing else moves.
- Time: pair 1 reads 1.132, inside 1.05-1.15, so pair 2 was run as frozen. The means are 2,407.5
  against 2,111.5 s: **1.140, above 1.10. Not met.** All of the extra time is in the resyncs (+321 and
  +379 s). Each of Q's 352 resyncs reads 16 spectra of 134 MB back from the page cache, about 750 GB
  over the run, and the read decodes them value by value.
- **Outcome under the frozen rule: arm A is recorded, not merged.** The branch keeps arm 0 only.
  Main and arm A give the same images; the cost of arm A is time.

**Arm 0: met** (identity as above). The joined-channel path's report now has the `memory` section.
Its trace of **case I** at the heap peak (41.05 GB, during a major cycle's predict):

| Blocks | GB |
| --- | ---: |
| 65 images of 4096² f64 (residuals, models, dirty images, working maps, multiscale scale images) | 8.72 |
| 10 half spectra of 537 MB (the 8 beams' resync spectra and 2 multiscale convolvers) | 5.37 |
| 8 beam exteriors of `(2n−1)²` f64 | 4.29 |
| measurement arrays of 0.37-0.82 GB (visibilities and weights of 1.6 M rows × 512 channels) | about 14 |
| 10 multiscale buffers of 268 MB | 2.69 |

The read alone peaks at 29.5 GB, held 9.8 GB at its end. Arm A does not apply to case I, which has
one polarisation and no `-reorder`.

**Stated factor against WSClean 3.7** (peak RSS, same settings, section 2): case Q 7.4 × with
main, 6.0 × with arm A (not merged); case I 3.6 ×.

**Not done, for a later proposal:**
- arm A with a direct copy instead of decoding value by value: about 750 GB through memcpy is
  roughly 1-2 min at page-cache speed, against the measured +5-6 min;
- arm A on the one-polarisation path (case I's 4.3 GB of spectra), which would write temporary
  files by default;
- case I's read peak of 29.5 GB.

## For the coordinator

- #32 phase 4: **arm A not adopted** under the frozen rule. Memory 0.811 × (met), wall 1.140 × (limit
  1.10), images byte-identical. Kept as a patch.
- Arm 0 (the memory report on the joined-channel path) is on the branch; quick check below.
- E2-N factors against WSClean 3.7: joined IQUV 7.4 ×, Stokes I multiscale 3.6 × (40 against 11 GB).
- nash keeps `~/rang-data/outputs/gemclean-mem-32-20261121/` (q.ms 6.6 GB, i.ms 75 GB) and worktrees
  `~/Worktrees/rang/gemclean-mem-32{,-arm}` for a follow-up; delete on your word.
