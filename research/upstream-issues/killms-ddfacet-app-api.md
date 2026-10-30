# killMS 3.3.0 cannot run with DDFacet 1.0.0.0 (`AsyncProcessPool` API removed)

Repository: saopicc/killMS (cross-references DDFacet). Status: **filed 2026-10-30,
https://github.com/saopicc/killMS/issues/27. No PR** (a port touches ten modules; fix options left
to the maintainers in the issue). Task U3, [../upstream-saopicc.md](../upstream-saopicc.md).

- **Versions.** killMS 3.3.0 = `master` 350f22c; DDFacet 1.0.0.0 = `master` 2fe05ab4 (also equal to
  cyriltasse/DDFacet `master`, checked with the compare API); Python 3.12.15. killMS requires
  `DDFacet[kms-support] >= 0.7.0` with no upper bound.
- **Reproduction** (`research/upstream-saopicc-files/app_repro.sh`, data-free):
  `AsyncProcessPool._init_default()` -> `AttributeError`; `from DDFacet.Other.AsyncProcessPool
  import APP` -> `ImportError`; `import killMS.Weights.W_DiagBL` (also `W_AntFull`, `InterpSols`)
  -> the same `ImportError`; `inspect.signature(AsyncProcessPool.init)` has
  `requested_worker_cpus`, no `affinity`. The study's `kMS.py` run on the LUNO slice failed at
  `kMS.py:556` with the `AttributeError` (`outputs/ddfacet-feasibility-20261030-01/runs/clean-hmp/kms.log`).
- **Cause (read).** v0.9.1 `AsyncProcessPool.py` 959-971 defines a global `APP`,
  `_init_default()` (called at import) and `init(ncpu, affinity, ...)` on that global. In
  v1.0.0.0 lines 1055-1060 comment them out and `init(Name, ncpu, requested_worker_cpus, ...)`
  returns a new pool; DDFacet classes take it as `APP=` (e.g. `ClassVisServer`). History
  (`git log -S`): de2fc174 (2022-04-21) stopped calling `_init_default()` at import; 11a616f2
  (2026-04-30) commented out the function; `51a1d352` (2026-05-29), cited by the study, only
  re-adds the file after b21b86e5 deleted it, already commented out. All three reach the release
  through the second parent of 34bc8fc5, the merge of cyriltasse/DDFacet#912 (Python 3.12 work),
  so the issue cites #912 rather than one commit.
- **killMS uses of the old API.** Global `APP` imported in 10 modules (`kMS.py`, `AQWeight.py`,
  `InterpSols.py`, `SmoothSols.py`, `Predict/ClassImageSM2.py`, `Weights/W_*.py` x5);
  `init(..., affinity=...)` in 6 places; `_init_default()` at `kMS.py:556`.
- **Expected.** killMS works with current DDFacet, or its metadata excludes 1.0.
- **Impact.** A fresh `pip install killMS` gives a pair that fails at start; a killMS oracle needs
  DDFacet < 1.0 (the study's conclusion stands).
- **Fix options (in the issue).** (1) Port to the returned-pool API and pass `APP=`; (2) meanwhile
  pin `DDFacet[kms-support] >= 0.7.0, < 1.0`.
- **Not verified.** A runtime control on DDFacet 0.9.1: `DDFacet==0.9.1` from PyPI did not install
  on GCC 15 because its dependency `astlib 0.13.2` fails to compile (`wcscon.c`: C23 `void f()`
  prototypes; `-std=gnu17` in `CFLAGS` did not reach it). The 0.9.1 API is read from the tag.
- **Side observation, not filed.** DDFacet 1.0.0.0 itself still has `from
  DDFacet.Other.AsyncProcessPool import APP` at `Imager/MultiFields/ClassImageDeconvMachineMultiFields.py:8`
  (would fail on import; not exercised here).
