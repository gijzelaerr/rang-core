Target: https://github.com/casacore/casacore/issues
Status: ready to post
Reproduced on: python-casacore 3.8.1 wheel from PyPI (bundles casacore 3.8.1), Linux x86_64 (WSL2), 2026-11-12; code read at casacore master 9afc669 (unchanged)
Duplicates checked: casacore issues/PRs for "MemoryStMan", "findExt", "terminate called"; python-casacore for "MemoryStMan"; no match (nearest by words: #998 open, MS::requiredTableDesc, unrelated)
Title: Reopened disk table with a FixedShape MemoryStMan array column: reads raise MSMColumn::findExt and closing the table aborts the process
---
casacore 3.8.1 (python-casacore 3.8.1 wheel), read at master 9afc669.

The MemoryStMan.h synopsis says that when a disk-based table is reopened, its MemoryStMan columns are initialised to 0. That holds for scalar columns. For a FixedShape array column (stored as `MSMDirColumn`), reading raises an exception, and even a bare open and close aborts the process.

```python
import numpy as np, casacore.tables as pt
dm = {"*1": {"TYPE": "MemoryStMan", "NAME": "MSM", "SPEC": {}, "COLUMNS": ["D"]}}
d = pt.maketabdesc([pt.makearrcoldesc("D", 0.0, shape=[3]), pt.makescacoldesc("S", 0)])
pt.table("t", d, dminfo=dm, nrow=5).close()
```

Then, in a new process:

```python
t = pt.table("t")
t.getcol("D")   # RuntimeError: MSMColumn::findExt - rownr 0 in column  out of range
t.close()       # terminate called after throwing an instance of 'casacore::indexError<unsigned long long>'
                #   what():  MSMColumn::findExt - rownr 0 in column  out of range   (SIGABRT, exit 134)
```

`pt.table("t").close()` alone aborts the same way. With the same layout:

| MemoryStMan columns | after reopen |
| --- | --- |
| scalar Int only | reads `[0, 0, 0, 0, 0]`, closes cleanly |
| variable-shape array only | cell undefined ("MSM: no array in row 0"), closes cleanly |
| FixedShape Double [3], with or without a scalar | read raises, close aborts |

If rows are added after the reopen (`addrows(1)`), the close does not abort.

Code at 9afc669:
- `~MSMDirColumn` (tables/DataMan/MSMDirColumn.cc:42-47) calls `deleteArray(i)` → `getArrayPtr(i)` → `findExt` for every row. `findExt` throws `indexError` when the column has no extents, and a throw from the destructor terminates the process.
- The column has no extents after the reopen. The column name in the message is empty, which suggests the `MSMDirColumn` is a fresh object. `MSMBase::reallocateColumn` (tables/DataMan/MSMBase.cc:124-141) replaces a fixed-shape `MSMIndColumn` with a new `MSMDirColumn`, and `MSMBase::open64` (MSMBase.cc:212-218) creates the rows by `doCreate` on the columns present at that moment. If `open64` runs before the reallocation on reopen, the new column never gets its rows. We have not traced the call order further.

Suggested fix: create the rows in the reallocated column, for example with `newcol->doCreate(nrrow_p)` in `reallocateColumn` when `nrrow_p > 0`. In addition, `~MSMDirColumn` should not call a throwing lookup (delete the allocated extents directly), so that a destructor cannot abort the process.
