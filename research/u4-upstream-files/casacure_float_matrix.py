# ruff: noqa
"""Which array columns casacure's putcell accepts. Usage: python -I casacure_float_matrix.py <workdir> casacure|casacore"""

import os
import sys

import numpy as np
import importlib

m = importlib.import_module(sys.argv[2] + ".tables")
makearrcoldesc, maketabdesc, table = m.makearrcoldesc, m.maketabdesc, m.table

os.chdir(sys.argv[1])
cases = [
    ("float variable", 0.0, dict(ndim=1, valuetype="float"), np.float32),
    (
        "float shape=[2] options=0",
        0.0,
        dict(ndim=1, shape=[2], valuetype="float"),
        np.float32,
    ),
    (
        "float shape=[2] options=4",
        0.0,
        dict(ndim=1, shape=[2], options=4, valuetype="float"),
        np.float32,
    ),
    (
        "float shape=[2] options=5",
        0.0,
        dict(ndim=1, shape=[2], options=5, valuetype="float"),
        np.float32,
    ),
    ("double variable", 0.0, dict(ndim=1), np.float64),
    ("double explicit variable", 0.0, dict(ndim=1, valuetype="double"), np.float64),
    ("int variable", 0, dict(ndim=1, valuetype="int"), np.int32),
    ("int64 variable", 0, dict(ndim=1, valuetype="int64"), np.int64),
    ("short variable", 0, dict(ndim=1, valuetype="short"), np.int16),
    ("complex variable", 0j, dict(ndim=1, valuetype="complex"), np.complex64),
    ("dcomplex variable", 0j, dict(ndim=1, valuetype="dcomplex"), np.complex128),
    ("bool variable", False, dict(ndim=1, valuetype="boolean"), np.bool_),
]
for i, (name, val, kw, dt) in enumerate(cases):
    t = table(
        f"{sys.argv[2]}-m{i}.tab",
        maketabdesc([makearrcoldesc("V", val, **kw)]),
        nrow=2,
        ack=False,
    )
    try:
        t.putcell("V", 0, np.ones(2, dtype=dt))
        print(f"{name:30s} putcell ok ", t.getcell("V", 0).dtype)
    except Exception as e:
        print(f"{name:30s} putcell RAISES", e)
    try:
        t.putcol("V", np.ones((2, 2), dtype=dt))
        print(f"{'':30s} putcol ok")
    except Exception as e:
        print(f"{'':30s} putcol RAISES", e)
    t.close()
