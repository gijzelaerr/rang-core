# dask-ms: object columns encoded with `pickle` in older exports

Repository: ratt-ru/dask-ms. Status: **not filed: fixed upstream in 2024.** Checked 2026-10-30.

- Observation (`upstream-notes.md`): the ESO137 public store's string columns use the
  numcodecs `pickle` filter, LUNO's use `json2`.
- Latest release (dask-ms 0.2.32) and `master` (5bc1071): `daskms/experimental/zarr/__init__.py`
  line 75 writes object columns with `numcodecs.JSON()`. The switch is c81ab2d "Use JSON
  encoding for objects when writing zarr (#310)", 2024-03-19; the ESO137 store predates it.
  Reproduced: the scan 9 export above has `json2` object codecs (OBSERVATION `PROJECT`,
  `OBSERVER`, `SCHEDULE`) and no `pickle` anywhere.
- Reader side: decoding an old store's `pickle` filter is done by zarr/numcodecs, not dask-ms,
  so "refuse pickle by default" belongs there (non-RATT; listed in
  [non-ratt-observations.md](../non-ratt-observations.md)). Rang never unpickles remote data
  (`python/rangtoy/flagging_provenance.py` inspects pickle opcodes with `pickletools` only).
