import hashlib, json, sys
import numpy as np
from casatools import table
tb = table(); tb.open(sys.argv[1]); n = tb.nrows()
hf, hr = hashlib.sha256(), hashlib.sha256()
for r0 in range(0, n, 4000):
    k = min(4000, n - r0)
    f = np.ascontiguousarray(np.transpose(tb.getcol("FLAG", r0, k), (2, 1, 0)).astype(bool))
    hf.update(f.tobytes())
    hr.update(np.ascontiguousarray(tb.getcol("FLAG_ROW", r0, k).astype(bool)).tobytes())
tb.close()
json.dump({"rows": n, "flag_sha256": hf.hexdigest(), "flag_row_sha256": hr.hexdigest()}, open(sys.argv[2], "w"), indent=1)
