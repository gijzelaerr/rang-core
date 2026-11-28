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
