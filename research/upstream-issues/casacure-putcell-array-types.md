# casacure: putcell refuses arrays for float and several other column types

Repository: tmolteno/casacure. Status: **filed 2026-11-02 (U4), https://github.com/tmolteno/casacure/issues/29**. Reproduced by U4 on 3.8.36
([../u4-upstream-files/casacure_float_matrix.py](../u4-upstream-files/casacure_float_matrix.py),
`casacure-float-matrix.log`). Broader than the first U4 note, which named only variable-shape float
columns: the shape does not matter, and int64, short, complex and dcomplex fail too. python-casacore: no refusal in the same matrix.

<!-- issue-title: putcell refuses arrays for float, int64, short, complex and dcomplex columns; putcol accepts them -->
<!-- issue-body -->
On casacure 3.8.36, `putcell` with an array raises for several column types, while `putcol` on the same column works. python-casacore 3.8.1 accepts every case below.

```python
import numpy as np
from casacure.tables import table, maketabdesc, makearrcoldesc

t = table("v.tab", maketabdesc([makearrcoldesc("V", 0.0, ndim=1, valuetype="float")]), nrow=2, ack=False)
t.putcol("V", np.ones((2, 2), dtype=np.float32))   # works
t.putcell("V", 0, np.ones(2, dtype=np.float32))
# TypeError: putcol/putcell: array cannot be stored in column V (valueType float)
```

Each column was tried with an array of its own dtype:

| valueType | Column | `putcell` | `putcol` |
| --- | --- | --- | --- |
| float | variable; `shape=[2]` with `options` 0, 4 or 5 | `array cannot be stored` | ok |
| int64 | variable | `array cannot be stored` | ok |
| short | variable | `string cannot be stored` | ok |
| complex, dcomplex | variable | `string cannot be stored` | ok |
| double, int, boolean | variable | ok | ok |

The message is raised near `crates/casacure-python/src/table.rs:3113` and `:3177`; I have not traced the cause. "string" in the second message also looks wrong for an array input.
<!-- /issue-body -->
