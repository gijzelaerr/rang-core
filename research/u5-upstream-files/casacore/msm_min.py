# ruff: noqa  (one-off upstream reproduction probe)
"""MemoryStMan in a disk table: create, close, reopen in a fresh process, close. Usage: msm_min.py <dir> <create|open> <scalar|array|both|var>"""

import subprocess
import sys

import casacore.tables as pt
import numpy as np

d, mode, kind = sys.argv[1:4]
if mode == "create":
    cols = {"scalar": ["I"], "array": ["D"], "both": ["I", "D"], "var": ["V"]}[kind]
    descs = [
        pt.makescacoldesc("I", 0),
        pt.makearrcoldesc("D", 0.0, shape=[3]),
        pt.makearrcoldesc("V", 0.0, ndim=1),
    ]
    descs = [c for c in descs if c["name"] in cols] + [pt.makescacoldesc("S", 0)]
    dm = {"*1": {"TYPE": "MemoryStMan", "NAME": "MSM", "SPEC": {}, "COLUMNS": cols}}
    t = pt.table(d, pt.maketabdesc(descs), dminfo=dm, nrow=5, ack=False)
    if kind == "var":
        t.putcell("V", 0, np.arange(3.0))
    t.close()
    r = subprocess.run(
        [sys.executable, "-u", __file__, d, "open", kind],
        capture_output=True,
        text=True,
    )
    print(
        kind,
        "reopen rc",
        r.returncode,
        "|",
        (r.stdout + r.stderr).strip().replace("\n", " | "),
    )
else:
    t = pt.table(d, ack=False)
    for c in t.colnames():
        try:
            print(c, t.getcol(c).tolist())
        except Exception as e:
            print(c, "raised", e)
    t.close()
    print("closed")
