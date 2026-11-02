# casacure: cannot read a fixed-shape string array written by casacore

Repository: tmolteno/casacure. Status: **filed 2026-11-02 (U4), https://github.com/tmolteno/casacure/issues/24**. Found by T1, reproduced by U4 on 3.8.36
([../u4-upstream-files/casacure_write.py](../u4-upstream-files/casacure_write.py),
[casacure_read.py](../u4-upstream-files/casacure_read.py)). Broader than T1 said: FixedShape
without Direct (`options=4`) fails the same way. Issue, not PR: `encode_string_array_content`
writes the header for these columns too, so a correct fix touches reading, writing and tables
casacure already wrote. Separate, not approved and not in the issue: python-casacore 3.8.1 raises on the
fixed-shape string tables casacure writes (`outputs/u4-20261102-01/logs/casacure-write2.log`).

<!-- issue-title: Fixed-shape string array columns written by casacore cannot be read: "bad string reference" -->
<!-- issue-body -->
Hi Tim, casacure 3.8.36 cannot read a string array column with a fixed shape when casacore wrote it. python-casacore 3.8.1 reads the table fine. This is not the bucket-chaining case fixed in 3.8.36.

```python
# with python-casacore 3.8.1
import casacore.tables as pt
d = pt.maketabdesc([pt.makearrcoldesc("SD", "", shape=[2], options=1, valuetype="string")])
t = pt.table("sd.tab", d, nrow=3, ack=False)
for r in range(3):
    t.putcell("SD", r, ["p%d" % r, "q" * (r + 1)])
t.close()

# with casacure 3.8.36
from casacure.tables import table
table("sd.tab").getcol("SD")     # RuntimeError: bad string reference: bucket 0, offset 8, length 0
table("sd.tab").getcell("SD", 0) # the same
```

`options=4` (FixedShape, not Direct) gives the same error. A variable-shape string column (`ndim=1`) from casacore reads correctly.

It looks like a layout difference. For a fixed-shape column the string bucket holds only the length-prefixed strings, without a shape header:

```
00000410: 0000 0002 7030 0000 0001 7100 0000 0270  ....p0....q....p
00000420: 3100 0000 0271 7100 0000 0270 3200 0000  1....qq....p2...
```

`decode_string_array_content` in `ssm.rs` expects `[ndim][dims][flag]` first. So it reads the first length as `ndim`, and runs off the end of the content. A table casacure writes itself reads back, because `encode_string_array_content` writes that header.

The shape for these columns would come from the column description. Since the writer is involved too, I am filing this as an issue rather than a PR.
<!-- /issue-body -->
