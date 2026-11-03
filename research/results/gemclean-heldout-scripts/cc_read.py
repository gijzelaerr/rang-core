# runs in rang-o-casa with python-casacore; reads cells past 2 GiB of the raw MS
import numpy as np, casacore.tables as t, json, sys
ms, out = sys.argv[1:3]
tb = t.table(ms, readonly=True, ack=False)
rec = {"nrows": tb.nrows()}
rows = [0, 410000, 700000, 849999, 850949]
d = {}
for r in rows:
    d[f"data_{r}"] = tb.getcell("DATA", r)
    d[f"flag_{r}"] = tb.getcell("FLAG", r)
    d[f"wt_{r}"] = tb.getcell("WEIGHT_SPECTRUM", r)
    d[f"uvw_{r}"] = tb.getcell("UVW", r)
np.savez(out, rows=np.array(rows), **d)
rec["columns"] = tb.colnames()
rec["dm"] = {k: v["TYPE"] + "/" + ",".join(v["COLUMNS"][:2]) for k, v in tb.getdminfo().items()}
print(json.dumps(rec))
