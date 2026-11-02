# casacure: getcol on a ragged variable-shape column silently returns the first row's shape

Repository: tmolteno/casacure. Status: **filed 2026-11-02 (U4), https://github.com/tmolteno/casacure/issues/25 (body edited once, minutes after filing: the first snippet used `valuetype="float"`, which casacure's `putcell` refuses, see `../u4-upstream.md`)**; PR: **https://github.com/tmolteno/casacure/pull/27 (branch gijzelaerr/casacure `getcol-ragged-raises`, 419e7f4)**. Found
by T1, reproduced by U4 on 3.8.36. Unrelated to #8 (defaults for undefined cells, by design: empty
cells stay exempt) and #19 (`getcell` conformance).

<!-- issue-title: getcol of a variable-shape column whose rows differ silently returns every row cut to the first row's shape -->
<!-- issue-body -->
On casacure 3.8.36, `getcol` of a variable-shape array column whose rows differ in shape returns the first row's shape and drops the rest of every longer row, with no error. python-casacore 3.8.1 raises.

```python
import numpy as np
from casacure.tables import table, maketabdesc, makearrcoldesc  # or casacore.tables

t = table("ragged.tab", maketabdesc([makearrcoldesc("V", 0.0, ndim=1)]), nrow=3, ack=False)
for r in range(3):
    t.putcell("V", r, np.arange(1.0, r + 2.0))
t.close()
print(table("ragged.tab").getcol("V"))
# casacure:        [[1.] [1.] [1.]]
# python-casacore: RuntimeError: Table DataManager error: Internal error: StManIndArray::get/put shapes not conforming
```

`getvarcol` and `getcell` return every row correctly. I will open a small PR that raises in this case, and leaves empty (undefined) cells as they are, in line with #8.
<!-- /issue-body -->
