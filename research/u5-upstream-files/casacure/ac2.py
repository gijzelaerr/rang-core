# ruff: noqa
import os, sys, numpy as np

if sys.argv[1] == "cc":
    from casacure import tables as T
else:
    import casacore.tables as T
path = sys.argv[2]
t = T.table(path, readonly=False, ack=False)
t.addcols(T.makearrcoldesc("CORRECTED_DATA", 0j, ndim=2, valuetype="complex"))
t.flush()
t.close()
