Target: https://github.com/casacore/casacore/issues
Status: ready to post
Reproduced on: python-casacore 3.8.1 wheel from PyPI (bundles casacore 3.8.1), Linux x86_64 (WSL2), 2026-11-12; code read at casacore master 9afc669 (unchanged)
Latest release: casacore v3.8.2 (2026-09-29) was not run (no python-casacore wheel for it); master 9afc669 is after v3.8.2, and the cited code is the same there.
Duplicates checked: casacore issues/PRs for "TiledCellStMan", "shapes do not conform", "conform", "putColumnRange", "getColumnRange tiled"; python-casacore for "TiledCellStMan", "getcol startrow"; nearest: #543 (open; tTempImage on 32-bit x86, unrelated)
Title: TiledCellStMan: getColumnRange/putColumnRange raise "TSMShape::offset - shapes do not conform" (reads rowpos past the IPosition end)
---
casacore 3.8.1 (python-casacore 3.8.1 wheel), read at master 9afc669.

On a TiledCellStMan column, whole-column get/put and get/put of single cells work. A row-range get or put fails.

```python
import numpy as np, casacore.tables as pt
cd = pt.makearrcoldesc("A", 0.0, shape=[4, 2])
dm = {"*1": {"TYPE": "TiledCellStMan", "NAME": "TCS", "SPEC": {"DEFAULTTILESHAPE": [4, 2]}, "COLUMNS": ["A"]}}
t = pt.table("t", pt.maketabdesc([cd]), dminfo=dm, nrow=6)
t.putcol("A", np.zeros((6, 4, 2)))                         # ok
t.putcell("A", 1, np.ones((4, 2)))                         # ok
t.putcol("A", np.full((2, 4, 2), 7.0), startrow=2, nrow=2) # RuntimeError: TSMShape::offset - shapes do not conform
t.getcol("A", startrow=2, nrow=2)                          # same error
```

Cause (line numbers at 9afc669):
- `TSMDataColumn::getArrayColumnCellsV` and `putArrayColumnCellsV` (tables/DataMan/TSMDataColumn.cc:540-564) take the optimised `accessColumnCells` path when `dataPtr.ndim() == nrCoordVector() + 1`. That holds for TiledCellStMan too: `setup(0)` gives `nrCoordVector_p = nrdim_p` = cell ndim (tables/DataMan/TiledStMan.cc:590-591).
- A TiledCellStMan hypercube has no row axis. `TiledCellStMan::getHypercube(rownr, position)` (tables/DataMan/TiledCellStMan.cc:177-186) returns the cell shape as `position`.
- `accessColumnCells` then reads `rowpos(lastAxis)` (TSMDataColumn.cc:295) with `lastAxis` = cell ndim, one element past the end of `rowpos`. This is not caught in builds without `AIPS_ARRAY_INDEX_CHECK`, and the mismatch surfaces later as the conformance error.
- `accessColumnSliceCells` (TSMDataColumn.cc:374) has the same pattern.

- The sliced variants (TSMDataColumn.cc:570, 584) use the same guard.

Suggested fix: use the optimised path only when the hypercube has a row axis, i.e. `nrdim_p == nrCoordVector_p + 1` (TiledStMan has no public `nrdim()` accessor yet). Otherwise fall back to the `...Base` implementations, as for multi-axis row mappings.
