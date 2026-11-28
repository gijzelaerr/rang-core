# The Galactic Centre mosaic tutorial (2026-11-28)

Status: **proposed recipe, not measured.** Owner's request of 2026-11-28: a
tutorial from the SARAO archive to a picture like the MeerKAT Galactic Centre
mosaic (Heywood et al. 2022, ApJ 925, 165; arXiv:2201.10541; products at
doi:10.48479/fyst-hj47, CC BY-NC 4.0; visibilities under SSV-20180505-FC-01).

## What was added

- `docs/tutorials/galactic-centre.md`: archive to MS (katdal 0.24
  `mvftoms.py`, options read from its wheel), `rang-core run` per pointing,
  primary-beam correction, mosaic, rendering, and a check against the
  released mosaic. Each step is labelled measured, implemented or proposed.
- `examples/gc-mosaic/config.yaml`: E2-N's Stokes I chain with the paper's
  imaging and self-cal settings where rang-core has them (Briggs -1.5,
  multiscale, 8 joined channels, 4th-order polynomial, Sp 64 s then Sa per
  scan, no spacings under 300 m in self-cal). It passes
  `rang-core config check --all`; it has not been checked against an MS.
- `examples/gc-mosaic/gc_mosaic.py`: `pbcor` (katbeam MKAT-AA-L-JIM-2020 or
  Mauch et al. 2020 eq. 3, azimuthally averaged, cut at B = 0.5), `mosaic`
  (sum B I / sum B^2) and `render` (the paper's Figure 1 scheme). At
  1,284 MHz katbeam's half-power radius is 0.555 deg and Mauch's 0.560 deg.
- `tests/test_gc_mosaic.py`: synthetic two-pointing images. pbcor and the
  mosaic recover a 10 mJy source to 1.5 % and 2 %, and the mosaic weight
  equals sum B^2 at the source.

## Estimates, not measurements

These are scaled from E2-N (102 GiB per 2.20 M rows at 1,024 channels):

- about 8.9 M rows per block;
- an MS of about 410 GiB, about 900 GiB with the chain's columns;
- about 1.5 TB read from the archive per pointing at 4,096 channels.

Not checked: whether the 2018 blocks are online or on tape.

## For the coordinator

- Next, a measured run on one pointing: GC23, 7' from Sgr A*. Run the
  `config.yaml` chain on nash, then compare with the released Stokes I mosaic
  at 4": compact-source fluxes, rms, filament brightness. Freeze a note
  before the run (AGENTS.md claims).
- rang has no primary-beam correction or mosaicking. Both are candidates for
  `rang-core` (a `pbcor` stage and a `mosaic` command), and the beam could be
  the katbeam path in `rang.beams`.
- The paper's 4" homogenisation (model convolved, residual homogenised with
  pypher) has no counterpart in rang.

## Progress, 2026-11-28 (nash)

- **GC23 (1528480450): restage requested.** The archive showed the
  visibilities and flags ARCHIVED (tape only) and the RDB SPOOLED. The
  restage request was made through the archive UI and the archive confirmed
  it ("A restage request for this dataset has been captured"); its banner
  warns of significant delays. The archive gives the selection as 1.14 TB and
  10:48:39. The stored E2-N token does not open this block (tokens are per
  block): "only to '1735268787*'". A GC23 link exists in the browser session;
  it goes to nash once the block is online.
- **Reference products fetched** to `~/rang-data/gc-mosaic/reference/` on
  nash (curl, nice 19):
  - Stokes I, 852,356,160 B, 10.6 s;
  - alpha, 1,196,611,200 B, 13.5 s;
  - alpha-error, the same size, 13.3 s.

  `SHA256SUMS` is beside them. The Stokes I mosaic is 10,121 × 10,527
  pixels at 1.1″, RA---TAN, reference 266.3668 −29.2214.
- **Step 6 measured on the released mosaic.** `render --downsample 4` took
  16 s at 2.0 GB peak (venv `~/Build/tmp/20261128-gc-mosaic/venv`). The robust
  σ is 61 µJy/beam. After a first look, the scheme was changed: the grey now
  rises to 0.7 (was 0.5) and the default faint limit is 10σ (was 30σ). The
  faint filaments were too dark before.

## A quicker field, 2026-11-28 (nash)

The owner's request: a test on data that is online, with fewer steps. The
field is SARAO **1658556374**, an MMGPS-L block (SCI-20200703-MK-01, public,
AVAILABLE, QA good):

- 3 h 24 min, 63 antennas, 4,096 channels, 404 GB;
- 16 ten-minute target snapshots at l = 269.2-273.4 deg, b = -0.2 to +2.4
  deg, around RCW 41;
- calibrators 0408-658 (flux, bandpass, delay), J0825-5010 (gain) and 3C138
  (not used).

Steps:

- **Conversion done.** `mvftoms -f -a --chanbin 8` streamed from the archive
  link, outside the lock (owner's word). It took 13:42-14:33 UTC, rc 0, and
  wrote `~/rang-data/gc-mosaic/rcw41/rcw41.ms` (88 GB).
- **Config.** `examples/gc-mosaic/rcw41.yaml`: 1GC with setjy standard
  `caracal` (CARACal's 0408-65 cubic), one 4,096² × 1.5″ image per pointing,
  Briggs −0.5, 4 joined channels with a 2-term fit, multiscale, auto-mask 5,
  threshold 1.5σ, no self-cal. `data.memory_limit_gb` is 90 since #34, under
  the run's 96 GB booking.
- **Running.** `chain2.sh` is in the run directory and its status log is
  `status.md` there. Its steps:
  1. rebuild the branch at bcca80f5 (main with #34) under the lock, 8 slots;
  2. `listobs` and `config check` against the MS;
  3. `rang-core run` under the lock, 16 slots, 96 GB, `RAYON_NUM_THREADS=16`;
  4. `gc_mosaic.py mosaic --frame galactic`, then `render` to
     `rcw41-mosaic.png`.

  At 16:16 UTC it was queued: the UHF gate and CARACal retry 3 held all 44
  slots.
- **Links.** The archive links live in `~/rang-data/gc-mosaic/links/`
  (mode 600). The owner allowed tokens in session logs (public archive). A
  link comes from the archive row's right-click "RDB" item, which writes it to
  the page's clipboard; in the built-in browser that clipboard is isolated, so
  the item was read from the page.

### Open items for the coordinator

1. When `chain2.sh` finishes:
   - check `status.md`, `run.log` and `post.log`;
   - inspect the 16 images and the mosaic: noise against the radiometer
     figure, calibrator flux, artefacts;
   - send the PNG to the owner;
   - add timings for the run, mosaic and render;
   - copy a compact archive to `research/results/gc-mosaic/` (PNG, summaries,
     receipts, no MS).
2. If the image looks right, add a "quicker field" section to
   `docs/tutorials/galactic-centre.md` with the measured times, then merge
   `gc-mosaic-tutorial`. CI was green at 4560b079; recheck at the merge.
3. GC23 (1528480450): the restage was requested at about 13:15 UTC and the
   archive warns of delays. When the observation page shows the visibilities
   no longer ARCHIVED:
   - make its link the same way;
   - put it in `links/`;
   - run the GC pointing (`examples/gc-mosaic/config.yaml`);
   - score it against the released mosaic in `~/rang-data/gc-mosaic/reference/`,
     with a note frozen before the run (AGENTS.md claims).
4. Cleanup when done:
   - `~/Build/tmp/20261128-gc-mosaic` (venvs, target, wheel) on nash;
   - the scratch nash worktree `~/Worktrees/rang/gc-mosaic-tutorial` (detached
     at bcca80f5);
   - the 88 GB MS once the images are archived.
