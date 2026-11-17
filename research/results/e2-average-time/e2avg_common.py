"""Shared helpers of the `calibrate.average_time` validation (task E2): run
rang-core, read tables, compare terms and composites.

Composites are `J_p J_q^*` of the parallel hands over the field's
cross-correlation rows (`examples/check_c2e.py` `composite`), here at a
subset of the field's times (every `step`-th unique TIME) so that a
4096-channel field fits in memory; the relative difference statistics are
class B's (research/a0-acceptance.md 6.2)."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "python"))

from rang import cal_apply, core_ms
from rang.formats import caltable

PY = Path(sys.executable)


def stats(x):
    x = np.asarray(x, float).ravel()
    x = x[np.isfinite(x)]
    if not x.size:
        return {"n": 0}
    return {"n": int(x.size), "median": float(np.median(x)),
            "p95": float(np.percentile(x, 95)), "max": float(x.max())}  # fmt: skip


def rang_core(*argv, log, env=None):
    """`rang-core` from this checkout; returns (exit code, wall seconds)."""
    e = dict(os.environ)
    e["PYTHONPATH"] = str(ROOT / "python")
    e.update(env or {})
    t0 = time.perf_counter()
    with open(log, "w", encoding="utf-8") as fh:
        rc = subprocess.run([str(PY), "-m", "rang.core_cli", *map(str, argv)],
                            stdout=fh, stderr=subprocess.STDOUT, env=e, check=False).returncode  # fmt: skip
    return rc, time.perf_counter() - t0


def field_id(ms, name):
    with core_ms.open_table(Path(ms) / "FIELD") as t:
        return [str(n) for n in t.getcol("NAME")].index(name)


def composite(ms, fid, tables, table_fields, step=1, nmax=None):
    """`J_p J_q^*` (complex128) and flags `(row, chan, hand)` of the field's
    cross rows at every `step`-th unique time (at most `nmax` times)."""
    with core_ms.open_table(ms) as t:
        c = {n: t.getcol(n) for n in ("TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID")}
    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as t:
        freq = t.getcol("CHAN_FREQ")[0]
    rows = (c["FIELD_ID"] == fid) & (c["ANTENNA1"] != c["ANTENNA2"])
    times = np.unique(c["TIME"][rows])[::step]
    if nmax:
        times = times[:nmax]
    rows &= np.isin(c["TIME"], times)
    ones = np.zeros((rows.sum(), len(freq), 4), np.complex64)
    ones[..., 0] = ones[..., 3] = 1
    v, f = cal_apply.apply(ones, np.zeros(ones.shape, bool), c["TIME"][rows],
                           c["ANTENNA1"][rows], c["ANTENNA2"][rows], freq, tables,
                           interp="linear", direction="corrupt",
                           table_fields=table_fields)  # fmt: skip
    return v[..., (0, 3)].astype(np.complex128), f[..., (0, 3)]


def rel_stats(a, fa, b, fb, median=7e-4, p95=3e-3):
    ok = ~fa & ~fb & (np.abs(b) > 0)
    rel = (np.abs(a - b) / np.abs(b))[ok]
    out = {"cells": int(ok.sum()), "flags_differ": int((fa != fb).sum()), **stats(rel)}
    out["class_b"] = bool(rel.size and out["median"] <= median and out["p95"] <= p95)
    return out


def table(path):
    return caltable.read(path)


def keyed(t):
    """{(time index, antenna): row} of a table, times ranked."""
    times = np.unique(np.round(t.column("TIME"), 3))
    ti = np.searchsorted(times, np.round(t.column("TIME"), 3))
    return {
        (int(i), int(a)): r for r, (i, a) in enumerate(zip(ti, t.column("ANTENNA1")))
    }


def matched(a, b):
    """The params and flags of tables `a` and `b` on their common (time
    rank, antenna) rows."""
    ka, kb = keyed(a), keyed(b)
    common = sorted(set(ka) & set(kb))
    ia = [ka[k] for k in common]
    ib = [kb[k] for k in common]
    return a.params[ia], a.flags[ia], b.params[ib], b.flags[ib], len(ka), len(kb)


def term_diff(a, b, kind):
    pa, fa, pb, fb, na, nb = matched(a, b)
    ok = ~fa & ~fb
    out = {"rows": [na, nb], "flags_differ": int((fa != fb).sum())}
    if kind == "delay":
        out["abs_ns"] = stats(np.abs(pa.real - pb.real)[ok])
    elif kind == "phase":
        out["abs_deg"] = stats(np.degrees(np.abs(np.angle(pa[ok] / pb[ok]))))
    else:
        with np.errstate(divide="ignore", invalid="ignore"):
            out["rel"] = stats((np.abs(pa - pb) / np.abs(pb))[ok])
        out["abs_deg"] = stats(np.degrees(np.abs(np.angle(pa[ok] / pb[ok]))))
    return out


def write(path, payload):
    Path(path).write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
