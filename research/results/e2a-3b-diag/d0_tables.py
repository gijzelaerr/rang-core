"""D0 of research/e2a-3b-diag.md: E2-A's archived 3b tables, no solve.

    python d0_tables.py RUN OUT.json

RUN is E2-A's run directory (D:\\rang\\outputs\\e2a-20261115): rang's tables
in RUN/rang-run/calibrate, CASA's in RUN/casa/tables, the MS RUN/e2a.ms read
for metadata only (TIME, ANTENNA1/2, FIELD_ID, SCAN_NUMBER, CHAN_FREQ). The
composite is `e2avg_common.composite` (every 8th time, pooled), unchanged.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "research" / "results" / "e2-average-time"))

import e2avg_common as C
from rang import cal_apply, core_ms

FCAL = "J1939-6342"
STEP = 8
NAMES = ("K0", "G0", "B0", "K1", "G1", "B1")


def meta(ms, fid, step):
    """The composite's rows (as `C.composite` selects them): time, scan,
    antennas; and the channel frequencies."""
    with core_ms.open_table(ms) as t:
        c = {
            n: np.asarray(t.getcol(n))
            for n in ("TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID", "SCAN_NUMBER")
        }
    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as t:
        freq = np.asarray(t.getcol("CHAN_FREQ")[0], float)
    rows = (c["FIELD_ID"] == fid) & (c["ANTENNA1"] != c["ANTENNA2"])
    times = np.unique(c["TIME"][rows])[::step]
    rows &= np.isin(c["TIME"], times)
    return {k: v[rows] for k, v in c.items()}, freq


def rel(a, fa, b, fb):
    ok = ~fa & ~fb & (np.abs(b) > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.abs(a - b) / np.abs(b)
    return r, ok


def stats_of(r, ok):
    s = C.stats(r[ok])
    s["class_b"] = bool(s.get("n") and s["median"] <= 7e-4 and s["p95"] <= 3e-3)
    return s


def delay_residual(a, fa, b, fb, freq):
    """The ratio a/b per (row, hand) with a weighted (unflagged cells)
    linear fit of its phase against frequency removed; returns the relative
    difference of what is left, the phase-only and amplitude-only parts of
    the raw ratio, and the fitted slopes (ns)."""
    x = (freq - freq.mean()) / 1e9  # GHz
    parts = {k: [] for k in ("lin", "const", "phase", "amp")}
    slopes = []
    for r0 in range(0, len(a), 1000):
        sl = slice(r0, r0 + 1000)
        aa, bb = a[sl], b[sl]
        ok = ~fa[sl] & ~fb[sl] & (np.abs(bb) > 0)
        with np.errstate(divide="ignore", invalid="ignore"):
            q = np.where(ok, aa / np.where(ok, bb, 1), 1)
        phi = np.angle(q)
        w = ok.astype(float)  # (row, chan, hand)
        sw = w.sum(1)
        sx = (w * x[None, :, None]).sum(1)
        sxx = (w * x[None, :, None] ** 2).sum(1)
        sy = (w * phi).sum(1)
        sxy = (w * phi * x[None, :, None]).sum(1)
        den = sw * sxx - sx**2
        with np.errstate(divide="ignore", invalid="ignore"):
            beta = np.where(
                den > 0, (sw * sxy - sx * sy) / np.where(den > 0, den, 1), 0
            )
            alpha = np.where(sw > 0, (sy - beta * sx) / np.where(sw > 0, sw, 1), 0)
        fit = alpha[:, None, :] + beta[:, None, :] * x[None, :, None]
        amp = np.abs(q)
        parts["lin"].append(
            np.abs(amp * np.exp(1j * (phi - fit)) - 1)[ok].astype(np.float32)
        )
        parts["const"].append(
            np.abs(amp * np.exp(1j * (phi - alpha[:, None, :])) - 1)[ok].astype(
                np.float32
            )
        )
        parts["phase"].append(np.abs(np.exp(1j * phi) - 1)[ok].astype(np.float32))
        parts["amp"].append(np.abs(amp - 1)[ok].astype(np.float32))
        slopes.append(np.abs(beta[sw > 2]) / (2 * np.pi))  # rad/GHz -> ns

    def st(k):
        v = np.concatenate(parts[k])
        s = C.stats(v)
        s["class_b"] = bool(s.get("n") and s["median"] <= 7e-4 and s["p95"] <= 3e-3)
        return s

    return {
        "after_linear_phase_removed": st("lin"),
        "after_constant_phase_removed": st("const"),
        "phase_part": st("phase"),
        "amplitude_part": st("amp"),
        "fitted_baseline_delay_ns": C.stats(np.concatenate(slopes)),
    }


def profiles(r, ok, m, freq):
    out = {"scan": {}, "antenna": {}, "channel_block_256": []}
    for s in np.unique(m["SCAN_NUMBER"]):
        sel = (m["SCAN_NUMBER"] == s)[:, None, None] & ok
        out["scan"][int(s)] = C.stats(r[sel])
    for a in np.unique(np.r_[m["ANTENNA1"], m["ANTENNA2"]]):
        rows = (m["ANTENNA1"] == a) | (m["ANTENNA2"] == a)
        x = r[rows][ok[rows]]
        out["antenna"][int(a)] = float(np.median(x)) if x.size else None
    for c0 in range(0, len(freq), 256):
        x = r[:, c0 : c0 + 256][ok[:, c0 : c0 + 256]]
        out["channel_block_256"].append(
            {
                "chan0": c0,
                "mhz": float(freq[c0] / 1e6),
                "n": int(x.size),
                "median": float(np.median(x)) if x.size else None,
            }  # fmt: skip
        )
    return out


def times_compare(r, c):
    tr, tc = (
        np.unique(np.round(r.column("TIME"), 3)),
        np.unique(np.round(c.column("TIME"), 3)),
    )
    out = {"intervals": [len(tr), len(tc)]}
    if len(tr) == len(tc):
        out["max_abs_dt_s"] = float(np.abs(tr - tc).max())
        out["dt_s"] = [round(float(x), 3) for x in tr - tc]
    out["rang_times_rel_s"] = [round(float(x - tr[0]), 3) for x in tr]
    out["casa_times_rel_s"] = [round(float(x - tr[0]), 3) for x in tc]
    return out


def outliers(r, c, kind, limit, names):
    pa, fa, pb, fb, _, _ = C.matched(r, c)
    keys = sorted(set(C.keyed(r)) & set(C.keyed(c)))
    ok = ~fa & ~fb
    if kind == "delay":
        d = np.abs(pa.real - pb.real)
    else:
        with np.errstate(divide="ignore", invalid="ignore"):
            d = np.abs(pa - pb) / np.abs(pb)
    out = []
    for i, ch, p in zip(*np.nonzero(ok & (d > limit))):
        ti, ant = keys[i]
        out.append({"interval": ti, "antenna": names[ant], "chan": int(ch), "pol": int(p),
                    "value": float(d[i, ch, p]), "rang": str(pa[i, ch, p]), "casa": str(pb[i, ch, p])})  # fmt: skip
    return out


def main(run, out_path):
    t0 = time.perf_counter()
    run = Path(run)
    ms = run / "e2a.ms"
    rdir, cdir = run / "rang-run" / "calibrate", run / "casa" / "tables"
    r = {n: C.table(rdir / n) for n in NAMES}
    c = {n: C.table(cdir / n) for n in NAMES}
    with core_ms.open_table(ms / "ANTENNA") as t:
        names = [str(x) for x in t.getcol("NAME")]
    fid = C.field_id(ms, FCAL)
    pooled = [cal_apply.POOLED] * 3
    m, freq = meta(ms, fid, STEP)
    frozen = json.loads((HERE.parent / "e2a-3b-diag" / "g3b-a-frozen.json").read_text())
    out = {"step": STEP, "rows": len(m["TIME"]), "channels": len(freq)}
    for tag, ts in (("1", ("K1", "G1", "B1")), ("0", ("K0", "G0", "B0"))):
        b, fb = C.composite(ms, fid, [c[n] for n in ts], pooled, step=STEP)
        sets = {"rang": [r[n] for n in ts]}
        for i, n in enumerate(ts):
            s = [r[x] for x in ts]
            s[i] = c[n]
            sets[f"swap_{n}"] = s
        for i in range(3):
            s = [c[x] for x in ts]
            s[i] = r[ts[i]]
            sets[f"casa_with_rang_{ts[i]}"] = s
        res = {}
        for label, tabs in sets.items():
            a, fa = C.composite(ms, fid, tabs, pooled, step=STEP)
            rr, ok = rel(a, fa, b, fb)
            res[label] = {"flags_differ": int((fa != fb).sum()), **stats_of(rr, ok)}
            if label == "rang":
                res["delay_share"] = delay_residual(a, fa, b, fb, freq)
                res["profiles"] = profiles(rr, ok, m, freq)
                if tag == "1":
                    want = frozen["composite_fcal_KGB1"]
                    got = res[label]
                    res["control_C0"] = {
                        "cells_equal": got["n"] == want["n"],
                        "median_rel": abs(got["median"] - want["median"])
                        / want["median"],
                        "p95_rel": abs(got["p95"] - want["p95"]) / want["p95"],
                    }
                    res["control_C0"]["met"] = bool(
                        res["control_C0"]["cells_equal"]
                        and res["control_C0"]["median_rel"] <= 1e-6
                        and res["control_C0"]["p95_rel"] <= 1e-6
                    )
            del a, fa, rr, ok
        out[f"KGB{tag}"] = res
        del b, fb
    out["times"] = {n: times_compare(r[n], c[n]) for n in ("K1", "G1", "K0", "G0")}
    out["outliers"] = {
        "K1_gt_0.1ns": outliers(r["K1"], c["K1"], "delay", 0.1, names),
        "G1_rel_gt_0.1": outliers(r["G1"], c["G1"], "complex", 0.1, names),
    }
    out["seconds"] = time.perf_counter() - t0
    C.write(out_path, out)
    print(json.dumps({k: {kk: (vv.get("median") if isinstance(vv, dict) else vv) for kk, vv in v.items()}
                      for k, v in out.items() if k.startswith("KGB")}, indent=1))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
