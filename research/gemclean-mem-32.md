# GeMClean memory, phase 4 (issues #32 and #34): E2-N profile, beam spectra

Branch `gemclean-mem-32` from origin/main `73fe1111`. **Frozen 2026-11-21 before any code**, after
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

## Measured

(none yet)
