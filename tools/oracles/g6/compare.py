# SPDX-License-Identifier: GPL-3.0-or-later
"""G6 criteria 1, 2 and 6 (research/g6-predict.md): gemclean's model column
against WSClean's in the same MS, read with python-casacore, in row chunks.

    python compare.py MS --g MODEL_DATA --w MODEL_WSCLEAN --field 3 \
        [--sentinel 7+7j] [--before before.json] [--out result.json]

Rows "changed" are rows whose cells differ from the sentinel (when the column
was pre-filled) or are not all zero (a column added zero-filled). `--before`
holds SHA-256 of every column before the writes (from `hashes.py`)."""

import argparse
import hashlib
import json
import sys

import numpy as np
import casacore.tables as ct

CHUNK_CELLS = 1 << 24


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("ms")
    p.add_argument("--g", default="MODEL_DATA")
    p.add_argument("--w", default="MODEL_WSCLEAN")
    p.add_argument("--field", type=int, default=None)
    p.add_argument("--sentinel", type=complex, default=None)
    p.add_argument("--before", default=None)
    p.add_argument(
        "--hashes", default=None, help="only write every column's SHA-256 here"
    )
    p.add_argument("--out", default=None)
    a = p.parse_args(argv)
    t = ct.table(a.ms, ack=False)
    if a.hashes:
        hashes = {name: column_hash(t, name) for name in t.colnames()}
        open(a.hashes, "w").write(
            json.dumps({"columns": hashes}, indent=1, sort_keys=True) + "\n"
        )
        return 0
    nrows = t.nrows()
    cell = t.getcell("DATA", 0).shape
    nchan, ncorr = cell
    step = max(1, CHUNK_CELLS // (nchan * ncorr))
    corr = list(ct.table(a.ms + "/POLARIZATION", ack=False).getcol("CORR_TYPE")[0])
    par = [i for i, c in enumerate(corr) if c in (5, 8, 9, 12, 1)]
    cross = [i for i in range(ncorr) if i not in par]
    s = {
        "d2": 0.0,
        "w2": 0.0,
        "dmax": 0.0,
        "wmax": 0.0,
        "rows_g": 0,
        "rows_w": 0,
        "rows_differ": 0,
        "chan_differ": 0,
        "xx_ne_yy": 0,
        "cross_nonzero": 0,
        "unselected_changed": 0,
        "selected_rows": 0,
        "cells": 0,
    }
    hg, hw = hashlib.sha256(), hashlib.sha256()
    for start in range(0, nrows, step):
        n = min(step, nrows - start)
        g = t.getcol(a.g, start, n)
        w = t.getcol(a.w, start, n)
        hg.update(np.ascontiguousarray(g).tobytes())
        hw.update(np.ascontiguousarray(w).tobytes())
        f = t.getcol("FIELD_ID", start, n)
        a1, a2 = t.getcol("ANTENNA1", start, n), t.getcol("ANTENNA2", start, n)
        dd = t.getcol("DATA_DESC_ID", start, n)
        sel = (f == a.field) & (a1 != a2) & (dd == 0)
        base = a.sentinel if a.sentinel is not None else 0
        cg = g != base  # changed cells (rows, chan, corr)
        cw = w != base
        rg, rw = cg.any(axis=(1, 2)), cw.any(axis=(1, 2))
        s["rows_g"] += int(rg.sum())
        s["rows_w"] += int(rw.sum())
        s["rows_differ"] += int((rg != rw).sum())
        # channel sets changed (a channel is changed if any correlation is)
        s["chan_differ"] += int((cg.any(axis=2) != cw.any(axis=2)).sum())
        s["unselected_changed"] += int((rg & ~sel).sum() + (rw & ~sel).sum())
        s["selected_rows"] += int(sel.sum())
        gs, ws = g[rg], w[rg]
        if len(par) == 2:
            s["xx_ne_yy"] += int((gs[..., par[0]] != gs[..., par[1]]).sum())
        if cross:
            s["cross_nonzero"] += int((gs[..., cross] != 0).sum())
        # values over the selected rows' changed channels
        m = sel[:, None] & cg.any(axis=2)
        gv = g[m][:, par].astype(np.complex128)
        wv = w[m][:, par].astype(np.complex128)
        d = gv - wv
        s["d2"] += float(np.sum(np.abs(d) ** 2))
        s["w2"] += float(np.sum(np.abs(wv) ** 2))
        if d.size:
            s["dmax"] = max(s["dmax"], float(np.abs(d).max()))
            s["wmax"] = max(s["wmax"], float(np.abs(wv).max()))
        s["cells"] += int(m.sum())
    rel = (s["d2"] / s["w2"]) ** 0.5 if s["w2"] > 0 else float("nan")
    out = {
        "ms": a.ms,
        "columns": [a.g, a.w],
        "field": a.field,
        "sentinel": None if a.sentinel is None else str(a.sentinel),
        **s,
        "rel_l2": rel,
        "max_abs_over_max_w": s["dmax"] / s["wmax"] if s["wmax"] else float("nan"),
        "sha256_g": hg.hexdigest(),
        "sha256_w": hw.hexdigest(),
        "desc_g": {
            k: v
            for k, v in t.getcoldesc(a.g).items()
            if k
            in (
                "valueType",
                "dataManagerType",
                "dataManagerGroup",
                "ndim",
                "shape",
                "option",
                "comment",
            )
        },
        "dminfo_g": {
            k: v for k, v in t.getdminfo(a.g).items() if k in ("TYPE", "NAME", "SPEC")
        },
        "data_comment": t.getcoldesc("DATA").get("comment", ""),
    }
    c1 = (
        s["rows_differ"] == 0
        and s["chan_differ"] == 0
        and s["xx_ne_yy"] == 0
        and s["cross_nonzero"] == 0
        and s["unselected_changed"] == 0
        and s["rows_g"] > 0
    )
    c2 = rel <= 1e-5 and out["max_abs_over_max_w"] <= 1e-4
    out["criterion_1"] = bool(c1)
    out["criterion_2"] = bool(c2)
    if a.before:
        before = json.load(open(a.before))
        changed = []
        for name in t.colnames():
            if name in (a.g, a.w) or name not in before["columns"]:
                continue
            h = column_hash(t, name)
            if h != before["columns"][name]:
                changed.append(name)
        out["other_columns_changed"] = changed
    text = json.dumps(out, indent=1, sort_keys=True, default=str)
    if a.out:
        open(a.out, "w").write(text + "\n")
    print(text)
    return 0


def column_hash(t, name):
    h = hashlib.sha256()
    nrows = t.nrows()
    step = 4096
    for start in range(0, nrows, step):
        n = min(step, nrows - start)
        try:
            v = t.getcol(name, start, n)
        except Exception as exc:  # undefined cells: hash the error text
            h.update(repr(exc).encode())
            continue
        if isinstance(v, (list, dict)):
            h.update(repr(v).encode())
        else:
            h.update(np.ascontiguousarray(v).tobytes())
    return h.hexdigest()


if __name__ == "__main__":
    sys.exit(main())
