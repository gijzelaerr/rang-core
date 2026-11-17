Target: https://github.com/tmolteno/casacure/issues
Status: ready to post
Reproduced on: casacure 3.8.41 (PyPI, Linux x86_64, CPython 3.12), python-casacore 3.8.1 as reference, 2026-11-12
Duplicates checked: open and closed issues and PRs, searches "unset", "empty table", "zero rows", "nrow", "addcols", "iscelldefined"; nearest #8 (closed; its 2026-09 status comment says reads now return defaults, ad0b510), #32 (iscelldefined, added 3.8.38), #22 (addcols in place, closed); none covers the shapes and dtypes below
Title: Shapes and dtypes of never-written cells: a 3-D column reads as (nrow,), 0-row columns read as int32, addcols stores empty 1-D arrays

---

DIFFERENCES.md says a read of a cell that is not on disk returns the column's default, "a zeroed array of the declared shape" (the #8 follow-up, ad0b510). The three cases below give a shape or dtype that disagrees with the column description. casacure 3.8.41, python-casacore 3.8.1.

```python
import numpy as np
from casacure.tables import table, maketabdesc, makearrcoldesc, makescacoldesc  # or casacore.tables

d = maketabdesc([makescacoldesc("D", 0.0), makescacoldesc("B", False),
                 makearrcoldesc("A", 0.0, ndim=1), makearrcoldesc("FLAG_CATEGORY", False, ndim=3)])
# 1. a never-written 3-D column
t = table("u.tab", d, nrow=3, ack=False)
t.putcol("D", np.arange(3.0))
t.close()
t = table("u.tab", ack=False)
try:
    v = t.getcol("FLAG_CATEGORY")
    print("getcol FLAG_CATEGORY:", v.shape, v.dtype)
except Exception as err:
    print("getcol FLAG_CATEGORY raises:", err)
t.close()
# 2. a 0-row table
table("z.tab", d, nrow=0, ack=False).close()
t = table("z.tab", ack=False)
print("0 rows:", {c: np.asarray(t.getcol(c)).dtype.str for c in ("D", "B", "A", "FLAG_CATEGORY")})
t.close()
```

**1. Never-written `ndim=3` column.** casacure's `getcol` returns a `(3,)` bool array of `False`, and `getcell` returns a 0-d `array(False)`. `iscelldefined` is `False`. python-casacore raises `SSMIndColumn::getShape: no array in row 0 in column FLAG_CATEGORY`. It is the same when python-casacore wrote the table, which is the usual case for FLAG_CATEGORY in an MS. A default is what DIFFERENCES.md promises, but a `(nrow,)` result for a 3-D column has neither the declared rank nor a shape, and code that indexes `[:, :, :, k]` breaks. An empty `(nrow, 0, 0, 0)` array, or the raise, would keep the declared rank.

**2. 0-row table.** Every column comes back as an empty `int32` array: `{'D': '<i4', 'B': '<i4', 'A': '<i4', 'FLAG_CATEGORY': '<i4'}`. It is the same for a 0-row table python-casacore wrote. python-casacore gives `float64` for D and A, `bool` for B and FLAG_CATEGORY, and an empty `list` for a string column. An empty `query()` result on a non-empty table has the right dtypes in casacure, so only the 0-row table is affected. Expected: the column's dtype.

**3. `addcols` of a variable-shape array column stores defined, empty 1-D cells.** casacore then sees them as written cells that contradict the column's `ndim`:

```python
# casacure
import numpy as np
from casacure.tables import table, maketabdesc, makearrcoldesc, makescacoldesc
t = table("ac.tab", maketabdesc([makescacoldesc("TIME", 0.0)]), nrow=3, ack=False)
t.putcol("TIME", np.arange(3.0))
t.addcols(makearrcoldesc("CORRECTED_DATA", 0j, ndim=2, valuetype="complex"))
t.close()

# python-casacore
import casacore.tables as pt
t = pt.table("ac.tab", ack=False)
t.iscelldefined("CORRECTED_DATA", 0)   # True
t.getcell("CORRECTED_DATA", 0).shape   # (0,)
t.getcol("CORRECTED_DATA")             # RuntimeError: ArrayIterator<T>::ArrayIterator<T> -  at the moment cannot iterate by scalars
```

When python-casacore itself adds the column, the cells are undefined (`iscelldefined` False, `getcell` raises `no array in row 0`). The same happens on a 20000-row table with the column joining the existing StandardStMan. A column created with the table, as opposed to added later, is left undefined by casacure, which is right.
