# SPDX-License-Identifier: GPL-3.0-or-later
"""G6 case preparation (python-casacore, rang-ms-reader:local).

python prep.py MS --flags FIELD          # the probe's flag edit on FIELD's rows
python prep.py MS --sentinel COL [COL...] # add COLs (StandardStMan) = 7+7j
python prep.py MS --drop COL [COL...]     # remove columns
"""

import argparse

import numpy as np
import casacore.tables as ct

SENTINEL = 7 + 7j


def main():
    p = argparse.ArgumentParser()
    p.add_argument("ms")
    p.add_argument("--flags", type=int, default=None)
    p.add_argument("--sentinel", nargs="*", default=[])
    p.add_argument("--drop", nargs="*", default=[])
    a = p.parse_args()
    t = ct.table(a.ms, readonly=False, ack=False)
    if a.flags is not None:
        rows = np.flatnonzero(t.getcol("FIELD_ID") == a.flags)
        f, fr = t.getcol("FLAG"), t.getcol("FLAG_ROW")
        f[rows[:50]] = True
        f[rows[100:110], 5:9, :] = True
        fr[rows[200:220]] = True
        t.putcol("FLAG", f)
        t.putcol("FLAG_ROW", fr)
        print("flags edited on", len(rows), "rows of field", a.flags)
    for name in a.drop:
        if name in t.colnames():
            t.removecols(name)
            print("removed", name)
    for name in a.sentinel:
        shape = t.getcell("DATA", 0).shape
        if name not in t.colnames():
            t.addcols(ct.makearrcoldesc(name, 0j, ndim=2, valuetype="complex"))
        step = 4096
        for start in range(0, t.nrows(), step):
            n = min(step, t.nrows() - start)
            t.putcol(name, np.full((n, *shape), SENTINEL, np.complex64), start, n)
        print("sentinel", name)
    t.close()


if __name__ == "__main__":
    main()
