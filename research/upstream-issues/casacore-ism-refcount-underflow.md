Target: https://github.com/casacore/casacore/issues
Status: ready to post
Reproduced on: python-casacore 3.8.1 wheel from PyPI (bundles casacore 3.8.1), Linux x86_64 (WSL2), 2026-11-12; code read at casacore master 9afc669 (unchanged)
Duplicates checked: casacore issues/PRs for "IncrementalStMan", "ISM", "IncrementalStMan array", "ISM grows", "refcount", "reference count", "StIndArray", "decrementRefCount", "handleRemove"; nearest: #767 (closed 2018; StandardStMan ScalarRecordColumn file grows when identical data are rewritten, traced to StIndArray puts; same symptom class, different manager and code path), #899 (closed; ISM slicing)
Title: IncrementalStMan: re-putting an indirect array in a single-row interval decrements its reference count below zero; the array file then grows
---
casacore 3.8.1 (python-casacore 3.8.1 wheel), read at master 9afc669.

Each time a variable-shape IncrementalStMan array is re-put in place with the same shape, the stored reference count of that array goes down by one: 1, 0, -1, -2 (as `unsigned int`, 4294967294). Once the count has wrapped, `refCount() <= 1` is false, so later puts reserve a new array. The old one is never freed. 20 puts to a single row leave 6 extra arrays in `table.f0i`. This looks related in symptom to #767 (StandardStMan), but the code path here is IncrementalStMan-specific.

```python
import numpy as np, casacore.tables as pt
cd = pt.makearrcoldesc("V", 0.0, ndim=1)
dm = {"*1": {"TYPE": "IncrementalStMan", "NAME": "ISM", "SPEC": {}, "COLUMNS": ["V"]}}
t = pt.table("t", pt.maketabdesc([cd]), dminfo=dm, nrow=10)
for r in range(10):
    t.putcell("V", r, np.full(4, float(r)))
for k in range(N):
    t.putcell("V", 5, np.full(4, 100.0 + k))
t.close()
```

Walking `t/table.f0i` (version 1: refcount, ndim, shape, data, records 8-byte aligned) after close. Values always read back correctly:

| N | file size | records | reference counts (signed) |
| --- | --- | --- | --- |
| 0 | 492 | 10 | 1 x 10 |
| 1 | 492 | 10 | row 5: 0 |
| 2 | 492 | 10 | row 5: -1 |
| 3 | 540 | 11 | -2, new 1 |
| 4 | 540 | 11 | -2, new 0 |
| 10 | 636 | 13 | -2 x 3, 0 |
| 20 | 780 | 16 | -2 x 6, -1 |

Cause (line numbers at 9afc669): `ISMIndColumn::putArrayPtr` (tables/DataMan/ISMIndColumn.cc:191-197) handles a single-row interval whose array is not shared by keeping the array. `setShape` returns early when the shape is known and equal. It then calls `putValue(rownr, &offset)` with the same offset. `putValue` ends in `ISMColumn::replaceData` (tables/DataMan/ISMColumn.cc:638-648), which calls `handleRemove` for the old value. `ISMIndColumn::handleRemove` (ISMIndColumn.cc:267-274) decrements the reference count of that offset, which is the array still in use. `StIndArray::decrementRefCount` (tables/DataMan/StIndArray.cc:73-76) does not guard against 0.

Suggested fix: in the single-row branch, skip `putValue` when the offset did not change. Otherwise, increment the new offset's count before `replaceData` removes the old one, as `handleCopy` does for copies. A guard against decrementing a zero count would make any similar mismatch visible.

Side effect: an array whose count has reached 0 while a row still references it looks unused to anything that inspects the counts.
