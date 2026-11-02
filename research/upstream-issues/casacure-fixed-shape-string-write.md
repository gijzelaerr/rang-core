# casacure: casacore cannot read fixed-shape string columns that casacure wrote

Repository: tmolteno/casacure. Status: **filed 2026-11-02 (U4), https://github.com/tmolteno/casacure/issues/28**. Reproduced by U4 on 3.8.36 with python-casacore
3.8.1 ([../u4-upstream-files/casacure_write_side.py](../u4-upstream-files/casacure_write_side.py)). The other direction is #24.

<!-- issue-title: Fixed-shape string columns written by casacure cannot be read by casacore (the other direction of #24) -->
<!-- issue-body -->
This is the other direction of #24. On casacure 3.8.36, python-casacore 3.8.1 cannot read a fixed-shape string array column that casacure wrote:

```python
# with casacure 3.8.36
from casacure.tables import table, maketabdesc, makearrcoldesc
t = table("sd.tab", maketabdesc([makearrcoldesc("S", "", shape=[2], options=1, valuetype="string")]), nrow=3, ack=False)
for r in range(3):
    t.putcell("S", r, ["p%d" % r, "q" * (r + 1)])
t.close()

# with python-casacore 3.8.1
import casacore.tables as pt
pt.table("sd.tab", ack=False).getcol("S")
# RuntimeError: ArrayIterator<T>::ArrayIterator<T> -  at the moment cannot iterate by scalars
```

`options=4` also raises, a `RuntimeError` with an empty message. casacure reads both tables back itself.

`encode_string_array_content` writes the `[ndim][dims][flag]` header for these columns too (`table.rs`, around line 706), and casacore stores those cells without it (#24), which looks like the cause, though I have not confirmed it by changing the writer. A fix would probably cover #24 and this together, and would need to decide what to do with fixed-shape string tables casacure has already written.
<!-- /issue-body -->
