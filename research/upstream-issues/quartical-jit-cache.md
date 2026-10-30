# QuartiCal: JIT cost of small solves and the Numba cache location

Repository: ratt-ru/QuartiCal. Status: **not filed: QuartiCal already caches; the cold cost
came from rang's containers.** Checked 2026-10-30.

Paths (2026-10-30, task P8): the frozen `tv-flagging*` recipes,
`tools/flagging/` and the recipe-only modules named here now live under
[`history/`](../../history/README.md); this text keeps the paths it was
written with.

- Upstream behaviour: `quartical/utils/numba.py` sets `cache: True` in `JIT_OPTIONS`
  (0.2.7 = `main` 942f77f). Without `NUMBA_CACHE_DIR`, Numba writes the cache beside the
  installed sources (`__pycache__` in site-packages) or in its user-wide fallback, so a normal
  install compiles once and keeps the result.
- Reproduction on the latest release (QuartiCal 0.2.7, Numba 0.68.1, Python 3.13), scan 9 of
  the public fixture with a unit MODEL_DATA, `G.type=complex`, 2 × 32 intervals, 50 iterations,
  `dask.threads=1`, fresh `NUMBA_CACHE_DIR`:
  cold run 29.3 s wall (25.49 s "execute graph"); warm run 4.0 s (1.65 s graph); cache 4.3 MB.
  This matches rang's earlier LUNO numbers (28.3 s against 3.6 s).
- The `/tmp` cache that made every rang solve cold is rang's own `NUMBA_CACHE_DIR=/tmp/numba`
  in `tools/flagging/Dockerfile`; the rang-side fix (bind-mounted cache) is already in
  `run-next.sh` and `run-luno-solve.sh`.
- Remaining upstream angle (about 2.4 s to import `quartical.executor` on a warm cache) is
  small and not a defect. Related open issue: #278 "Suggestion: Use github actions to cache
  numba kernels" (CI-side), which covers the documentation angle well enough.
