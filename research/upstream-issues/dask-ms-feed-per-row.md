# dask-ms: Zarr export writes FEED as one group per row

Repository: ratt-ru/dask-ms. Status: **not filed: deliberate design.** Checked 2026-10-30.

- Observation ([stack-consolidation-feasibility.md](../stack-consolidation-feasibility.md),
  `tool-timings.md`): the public LUNO store splits FEED into 56 per-antenna groups of
  single-row chunks; fetching the needed subtables meant 2,608 objects for 2.3 MB (432 s with
  rang's sequential `curl`).
- Reproduction on the latest release (dask-ms 0.2.32, Python 3.13): `dask-ms convert
  scan9.ms -o scan9.zarr --format zarr` on scan 9 of the public fixture (2.2 s) writes
  `FEED/FEED_0` … `FEED/FEED_3` for its 4 FEED rows (169 objects for FEED, 560 in all), while
  ANTENNA, SPECTRAL_WINDOW and POLARIZATION are one group each. Every group has its own
  `.zmetadata` (16 in all); there is none at the store root, which is how dask-ms reads it.
- Source: `daskms/apps/convert.py` reads the `NONUNIFORM_SUBTABLES` (SPECTRAL_WINDOW,
  POLARIZATION, FEED, SOURCE) with `group_cols="__row__"`, introduced in f64df55 / #191
  (2022-03-30) because rows of these subtables may have different shapes. That is a
  correctness choice; QuartiCal's v0.2.8-dev PR #451 "read the FEED subtable whatever its
  partitioning" shows readers adapting to it.
- What an issue would have said: group only when the row shapes actually differ. The cost is
  latency of many small objects over HTTP, which rang avoids with parallel or range fetches;
  dask-ms 0.3.0 is in alpha with breaking changes (#444), so a layout request now would be
  noise.
