"""DL4s stage 3 probe (research/dl4s-screen.md 2.3, readings 2.4): the outlier
screen per term on one block's two calibrate arms, and its catches.

    python dl4s_screen.py OFF_DIR ON_DIR OUT.json [--block CBID]
        [--terms K,G,B,Gsec,F] [--ref K=G,G=G,B=G,Gsec=Gsec,F=Gsec]

OFF_DIR and ON_DIR hold the CASA tables of the `k_zero_start` off and on arms
(a run directory's `calibrate/`). Reads the tables only.

Screen (2.3, 2.4): per (field, antenna, hand[, channel]) the median over the
field's intervals (one per scan at solint inf) of the unflagged solutions;
K outlier |tau - median| > 0.1 ns; G-type and B outlier, amplitude reading
| |g| - median|g| | / median|g| > 0.1, and complex reading |g - m| / |m|
with m = median(Re) + i median(Im). Catches: (a) the solution flagged in
rang's table; (b) the G-type solution (`--ref`) of the same field, antenna,
hand and interval flagged; (c) key-off outliers absent in the key-on arm.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from rang.formats import caltable

LIMIT = {"K": 0.1, "G": 0.1, "B": 0.1}
ORDER = ("K", "G", "B", "Gsec", "F")


def load(path):
    t = caltable.read(path)
    time = t.column("TIME")
    field = t.column("FIELD_ID").astype(int)
    ant = t.column("ANTENNA1").astype(int)
    scan = t.column("SCAN_NUMBER").astype(int) if "SCAN_NUMBER" in t.main else None
    p = t.params
    f = t.flags
    err = (
        np.stack([np.asarray(c) for c in t.main["PARAMERR"]])
        if "PARAMERR" in t.main
        else np.full(p.shape, np.nan)
    )
    # interval index per field: time rank within the field
    iv = np.zeros(len(time), int)
    for fid in np.unique(field):
        s = field == fid
        tu = np.unique(np.round(time[s], 1))
        iv[s] = np.searchsorted(tu, np.round(time[s], 1))
    return {
        "kind": t.kind, "time": time, "field": field, "ant": ant, "scan": scan,
        "iv": iv, "p": p, "f": f, "err": err,
    }  # fmt: skip


def deviations(tab, reading):
    """(dev, ok_median) arrays shaped like params: the deviation of every
    solution from its (field, antenna, chan, hand) median over intervals of
    the unflagged solutions; NaN where fewer than two unflagged intervals."""
    p, f = tab["p"], tab["f"]
    dev = np.full(p.shape, np.nan)
    nmed = np.zeros(p.shape, int)
    for fid in np.unique(tab["field"]):
        for a in np.unique(tab["ant"]):
            rows = np.nonzero((tab["field"] == fid) & (tab["ant"] == a))[0]
            if len(rows) == 0:
                continue
            x = p[rows]
            ok = ~f[rows]
            n = ok.sum(0)
            nmed[rows] = n[None]
            with np.errstate(invalid="ignore", divide="ignore"):
                if tab["kind"] == "K":
                    v = np.where(ok, x.real, np.nan)
                    med = np.nanmedian(v, 0) if v.size else v
                    d = np.abs(x.real - med[None])
                elif reading == "amplitude":
                    v = np.where(ok, np.abs(x), np.nan)
                    med = np.nanmedian(v, 0)
                    d = np.abs(np.abs(x) - med[None]) / med[None]
                else:
                    re = np.nanmedian(np.where(ok, x.real, np.nan), 0)
                    im = np.nanmedian(np.where(ok, x.imag, np.nan), 0)
                    m = re + 1j * im
                    d = np.abs(x - m[None]) / np.abs(m)[None]
            d = np.where((n >= 2)[None], d, np.nan)
            dev[rows] = d
    return dev, nmed


def ref_flag(tab, ref, i, pol):
    """Catch (b): the G-type solution of the same field, antenna, hand and
    interval (nearest time within the field) flagged; None: no such row."""
    s = np.nonzero((ref["field"] == tab["field"][i]) & (ref["ant"] == tab["ant"][i]))[0]
    if len(s) == 0:
        return None
    j = s[np.argmin(np.abs(ref["time"][s] - tab["time"][i]))]
    if abs(ref["time"][j] - tab["time"][i]) > 900:
        return None
    pp = min(pol, ref["f"].shape[2] - 1)
    return bool(ref["f"][j, :, pp].all())


def screen(tabs, names, refmap, reading):
    out = {}
    for name in names:
        tab = tabs.get(name)
        if tab is None:
            continue
        kind = "K" if tab["kind"] == "K" else ("B" if tab["kind"] == "B" else "G")
        dev, nmed = deviations(tab, reading)
        ref = tabs.get(refmap.get(name, ""))
        lim = LIMIT[kind]
        hit = np.nan_to_num(dev, nan=0.0) > lim
        rows = []
        # one record per (row, hand): channels aggregated (B)
        for i, pol in sorted({(int(i), int(q)) for i, _, q in zip(*np.nonzero(hit))}):
            ch = np.nonzero(hit[i, :, pol])[0]
            flagged = tab["f"][i, ch, pol]
            caught_a = bool(flagged.all())
            uncaught_ch = ch[~flagged]
            rep = uncaught_ch if len(uncaught_ch) else ch
            rb = (
                ref_flag(tab, ref, i, pol)
                if ref is not None and ref is not tab
                else None
            )
            if ref is tab:
                rb = bool(tab["f"][i, :, pol].all())
            with np.errstate(invalid="ignore", divide="ignore"):
                err = tab["err"][i, uncaught_ch, pol]
                if kind == "K":
                    sig = dev[i, uncaught_ch, pol] / err
                else:
                    sig = (
                        dev[i, uncaught_ch, pol]
                        * np.abs(tab["p"][i, uncaught_ch, pol])
                        / err
                    )
            sig_ok = (
                bool(np.any(np.nan_to_num(sig, nan=np.inf) > 5))
                if len(uncaught_ch)
                else False
            )
            rows.append({
                "row": i, "field": int(tab["field"][i]), "antenna": int(tab["ant"][i]),
                "interval": int(tab["iv"][i]),
                "scan": None if tab["scan"] is None else int(tab["scan"][i]),
                "time": float(tab["time"][i]), "pol": pol, "channels": len(ch),
                "uncaught_channels": len(uncaught_ch),
                # over the uncaught channels when there are any (B), else all
                "max_dev": float(np.nanmax(dev[i, rep, pol])),
                "value": str(tab["p"][i, rep[np.nanargmax(dev[i, rep, pol])], pol]),
                "caught_a": caught_a or len(uncaught_ch) == 0, "caught_b": rb,
                "significant_5sigma": sig_ok,
            })  # fmt: skip
        n_med = nmed[..., :]
        out[name] = {
            "kind": kind, "rows": int(tab["p"].shape[0]),
            "solutions": int(np.prod(tab["p"].shape)),
            "flagged": int(tab["f"].sum()),
            "no_median": int((n_med < 2).sum()),
            "fields": sorted(int(x) for x in np.unique(tab["field"])),
            "intervals_per_field": {
                int(fid): int(tab["iv"][tab["field"] == fid].max() + 1)
                for fid in np.unique(tab["field"])
            },
            "outliers": rows,
        }  # fmt: skip
    return out


def uncaught(o):
    return not o["caught_a"] and not o["caught_b"]


def events(scr, block, order=ORDER):
    """2.4: (block, field, antenna, interval) events of uncaught outliers,
    attributed to the most upstream term; and the (block, term) pairs."""
    ev = {}
    for sig in (False, True):
        e = {}
        for name in order:
            for o in scr.get(name, {}).get("outliers", []):
                if not uncaught(o) or (sig and not o["significant_5sigma"]):
                    continue
                key = (o["field"], o["antenna"], round(o["time"] / 60.0))
                # the same scan is matched by time to the minute
                hit = [
                    k
                    for k in e
                    if k[0] == key[0] and k[1] == key[1] and abs(k[2] - key[2]) <= 15
                ]
                if hit:
                    continue
                e[key] = name
        ev["significant" if sig else "literal"] = {
            "events": [{"field": k[0], "antenna": k[1], "minute": k[2], "term": v} for k, v in e.items()],
            "block_terms": sorted({f"{block}:{v}" for v in e.values()}),
        }  # fmt: skip
    return ev


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("off")
    ap.add_argument("on")
    ap.add_argument("out")
    ap.add_argument("--block", default="")
    ap.add_argument("--terms", default="K,G,B,Gsec,F")
    ap.add_argument("--ref", default="K=G,G=G,B=G,Gsec=Gsec,F=Gsec")
    a = ap.parse_args(argv)
    names = a.terms.split(",")
    refmap = dict(x.split("=") for x in a.ref.split(","))
    res = {"block": a.block, "off": a.off, "on": a.on}
    for arm, d in (("off", a.off), ("on", a.on)):
        tabs = {n: load(Path(d) / n) for n in names if (Path(d) / n).is_dir()}
        res[arm] = {}
        for reading in ("amplitude", "complex"):
            scr = screen(tabs, names, refmap, reading)
            res[arm][reading] = {"terms": scr, "instances": events(scr, a.block, names)}
    # catch (c): key-off K outliers that the key-on arm does not have
    off_k = {
        (o["row"], o["pol"])
        for o in res["off"]["amplitude"]["terms"].get("K", {}).get("outliers", [])
    }
    on_k = {
        (o["row"], o["pol"])
        for o in res["on"]["amplitude"]["terms"].get("K", {}).get("outliers", [])
    }
    res["k_zero_start_removed"] = sorted(off_k - on_k)
    res["k_zero_start_added"] = sorted(on_k - off_k)
    Path(a.out).write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    for arm in ("off", "on"):
        for reading in ("amplitude", "complex"):
            r = res[arm][reading]
            print(arm, reading, {n: (len(v["outliers"]), sum(uncaught(o) for o in v["outliers"]))
                                 for n, v in r["terms"].items()},
                  r["instances"]["literal"]["block_terms"], r["instances"]["significant"]["block_terms"])  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
