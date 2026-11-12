Target: https://github.com/tmolteno/casacure/issues
Status: ready to post
Reproduced on: casacure 3.8.41 (PyPI, Linux x86_64, CPython 3.12), python-casacore 3.8.1 as reference, 2026-11-12
Duplicates checked: open and closed issues and PRs, searches "taql", "BETWEEN", "ORDERBY", "rownumbers"; nearest #5 (TaQL subset, closed), #16 (query row order, closed), neither covers these; ARE_WE_CURED.md lists Tier A (query language) as done and Tier C (units, cones, masked arrays, UDFs) as out of scope, and these four are in neither
Title: TaQL: BETWEEN, SELECT without a column list and ORDERBY DESC col are parse errors; rownumbers(table) is missing

---

Four TaQL and selection forms that python-casacore 3.8.1 accepts fail on casacure 3.8.41:

```python
import numpy as np
from casacure.tables import table, maketabdesc, makescacoldesc, taql  # or casacore.tables

t = table("tq.tab", maketabdesc([makescacoldesc("TIME", 0.0), makescacoldesc("ANT", 0)]), nrow=6, ack=False)
t.putcol("TIME", np.arange(6.0))
t.putcol("ANT", np.array([3, 1, 2, 3, 1, 2]))
t.flush()
for q in ("SELECT TIME FROM tq.tab WHERE TIME BETWEEN 1 AND 3",
          "SELECT FROM tq.tab WHERE ANT == 3",
          "SELECT TIME FROM tq.tab ORDERBY DESC TIME"):
    try:
        print(q, "->", taql(q).getcol("TIME").tolist())
    except Exception as err:
        print(q, "-> raises", err)
sel = t.query("ANT == 3")
for label, f in (("sel.rownumbers(t)", lambda: list(sel.rownumbers(t))),
                 ("t.rownumbers(sel)", lambda: list(t.rownumbers(sel)))):
    try:
        print(label, "->", [int(x) for x in f()])
    except Exception as err:
        print(label, "-> raises", err)
```

| | casacure 3.8.41 | python-casacore 3.8.1 |
| --- | --- | --- |
| `WHERE TIME BETWEEN 1 AND 3` | `TaQL parse error: trailing tokens after query: [Ident("BETWEEN"), Int(1), Ident("AND"), Int(3)]` | `[1.0, 2.0, 3.0]` |
| `SELECT FROM tq.tab WHERE ANT == 3` (no column list, all columns) | `TaQL parse error: expected FROM, found tq.tab` | `[0.0, 3.0]` |
| `ORDERBY DESC TIME` | `TaQL parse error: trailing tokens after query: [Ident("TIME")]` | `[5.0, 4.0, 3.0, 2.0, 1.0, 0.0]` |
| `sel.rownumbers(t)` | `table.rownumbers() takes no arguments (1 given)` | `[0, 3]` |
| `t.rownumbers(sel)` | the same | `[0, -1, -1, 1, -1, -1]` |

`ORDERBY TIME DESC` and `TIME >= 1 AND TIME <= 3` work, so the first and third have workarounds. `sel.rownumbers()` with no argument works too. ARE_WE_CURED.md lists the query-language tier (A) as done, so these look like gaps rather than scope. `rownumbers(table)` is python-casacore's way to map a selection's rows to another table's row numbers (`-1` where a row is absent).
