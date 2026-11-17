"""U5 CASA reproductions (casatools/casatasks 6.7.6.14, public PyPI).

Run with the CASA venv's python from an empty working directory:
    python -I repro_casa.py OUTDIR [TABLES_DIR]
TABLES_DIR holds PerleyButler2017Coeffs / PerleyButler2013Coeffs (casarundata);
without it the table-backed setjy arm runs with the tables missing only.
Writes OUTDIR/result.json and per-call CASA logs. Items: gaincal minblperant K vs G,
tasks that write no table, solint frequency part and seconds binning, setjy
empty returns, unknown names, table keywords.
"""

import contextlib
import io
import json
import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np
from casatasks import bandpass, casalog, ft, gaincal, setjy
from casatools import componentlist, measures, simulator, table

ANT = ["m000", "m001", "m002", "m003"]
# local east/north/up offsets (m) from the MeerKAT array centre
ENU = [(0.0, 0.0, 0.0), (300.0, 120.0, 0.0), (-150.0, 420.0, 0.0), (80.0, -510.0, 0.0)]
F1934 = ("19h39m25.026s", "-63d42m45.63s")
F3C286 = ("13h31m08.288s", "+30d30m32.96s")
FFOO = ("02h00m00s", "-30d00m00s")
FFORNAXA = ("03h22m41.7s", "-37d12m30s")
DUMP = 8.0
NDUMP = 32
OUT = None


def log(tag):
    path = OUT / f"{tag}.log"
    casalog.setlogfile(str(path))
    return path


def severe(path):
    if not path.exists():
        return []
    keep = []
    for line in path.read_text(errors="replace").splitlines():
        parts = line.split("\t")
        if len(parts) >= 4 and parts[1] in ("SEVERE", "WARN"):
            msg = parts[3].strip()
            if msg and not any(
                s in msg
                for s in (
                    "contents of measurespath",
                    "not being maintained",
                    "external-data",
                    "TAI_UTC",
                    "times and coordinates",
                    "Until the table",
                )
            ):
                keep.append(f"{parts[1]}: {msg}")
    return keep[:12]


def call(tag, fn, **kw):
    path = log(tag)
    out = io.StringIO()
    err = None
    t0 = time.time()
    # capture the process-level stdout too: C++ `cout` bypasses sys.stdout
    fd_path = OUT / f"{tag}.stdout"
    sys.stdout.flush()
    saved = os.dup(1)
    with open(fd_path, "w") as fh:
        os.dup2(fh.fileno(), 1)
        try:
            with contextlib.redirect_stdout(out):
                ret = fn(**kw)
        except Exception as exc:  # noqa: BLE001 -- the point is whether CASA raises
            ret, err = None, repr(exc)
        finally:
            sys.stdout.flush()
            os.dup2(saved, 1)
            os.close(saved)
    text = (out.getvalue() + fd_path.read_text(errors="replace")).strip()
    return {
        "tag": tag,
        "return": repr(ret)[:300],
        "raised": err,
        "wall_s": round(time.time() - t0, 2),
        "log": severe(path),
        "stdout": text.splitlines()[-5:],
    }, ret


def build(ms, fields, spws, nant=4, ndump=NDUMP, noise="0.05Jy", flux=10.0):
    sm, me = simulator(), measures()
    sm.open(ms)
    sm.setconfig(
        telescopename="MeerKAT",
        x=[e[0] for e in ENU[:nant]],
        y=[e[1] for e in ENU[:nant]],
        z=[e[2] for e in ENU[:nant]],
        dishdiameter=[13.5] * nant,
        mount=["alt-az"] * nant,
        antname=ANT[:nant],
        coordsystem="local",
        referencelocation=me.observatory("MeerKAT"),
    )
    for name, f0, df, n in spws:
        sm.setspwindow(
            spwname=name,
            freq=f"{f0}Hz",
            deltafreq=f"{df}Hz",
            freqresolution=f"{df}Hz",
            nchannels=n,
            stokes="XX YY",
        )
    sm.setfeed(mode="perfect X Y")
    for name, (ra, dec) in fields.items():
        sm.setfield(sourcename=name, sourcedirection=me.direction("J2000", ra, dec))
    sm.setlimits(shadowlimit=0.0, elevationlimit="-90deg")
    sm.setauto(autocorrwt=0.0)
    sm.settimes(
        integrationtime=f"{DUMP}s",
        usehourangle=False,
        referencetime=me.epoch("UTC", "2026/01/01/20:00:00"),
    )
    t = 0.0
    for name in fields:
        for spw in spws:
            sm.observe(
                sourcename=name,
                spwname=spw[0],
                starttime=f"{t}s",
                stoptime=f"{t + ndump * DUMP}s",
            )
            t += ndump * DUMP
    if flux:
        cl = componentlist()
        ra, dec = next(iter(fields.values()))
        clpath = f"{ms}.cl"
        cl.addcomponent(
            dir=f"J2000 {ra} {dec}", flux=flux, fluxunit="Jy", shape="point"
        )
        cl.rename(clpath)
        cl.close()
        sm.predict(complist=clpath)
        if noise:
            sm.setseed(42)
            sm.setnoise(mode="simplenoise", simplenoise=noise)
            sm.corrupt()
        sm.close()
        ft(vis=ms, complist=clpath, usescratch=True)
    else:
        sm.close()


def caltable(path):
    if not os.path.isdir(path):
        return {"exists": False}
    tb = table()
    tb.open(path)
    col = "FPARAM" if tb.getkeyword("ParType") == "Float" else "CPARAM"
    times = tb.getcol("TIME")
    flag = tb.getcol("FLAG")
    shape = list(tb.getcell(col, 0).shape) if tb.nrows() else []
    out = {
        "exists": True,
        "rows": int(tb.nrows()),
        "cell_shape_pol_chan": shape,
        "flagged_frac": float(flag.mean()) if flag.size else None,
        "unique_times": int(np.unique(times).size),
        "times": np.unique(times).tolist(),
    }
    tb.close()
    return out


def ms_times(ms):
    tb = table()
    tb.open(ms)
    t = np.unique(tb.getcol("TIME"))
    tb.close()
    return t


def model_col(ms):
    tb = table()
    tb.open(ms)
    m = tb.getcol("MODEL_DATA") if "MODEL_DATA" in tb.colnames() else None
    tb.close()
    return m


def gaincal_arms(res):
    ms = "g.ms"
    t0 = time.time()
    build(ms, {"J1939-6342": F1934}, [("L", 1.4e9, 0.5e6, 64)])
    res["build_gaincal_ms_s"] = round(time.time() - t0, 2)
    common = {"vis": ms, "refant": "m000", "minsnr": 0.0}
    r = {}
    for tag, kw in [
        (
            "K_mbl4",
            {"caltable": "K4.tb", "gaintype": "K", "solint": "inf", "minblperant": 4},
        ),
        (
            "G_mbl4",
            {
                "caltable": "G4.tb",
                "gaintype": "G",
                "calmode": "ap",
                "solint": "inf",
                "minblperant": 4,
            },
        ),
        (
            "G_mbl3",
            {
                "caltable": "G3.tb",
                "gaintype": "G",
                "calmode": "ap",
                "solint": "inf",
                "minblperant": 3,
            },
        ),
        (
            "G_inf_32ch",
            {
                "caltable": "Gf.tb",
                "gaintype": "G",
                "solint": "inf,32ch",
                "minblperant": 3,
            },
        ),
        (
            "G_16s_32ch",
            {
                "caltable": "Gf16.tb",
                "gaintype": "G",
                "solint": "16s,32ch",
                "minblperant": 3,
            },
        ),
        (
            "T_inf_32ch",
            {
                "caltable": "Tf.tb",
                "gaintype": "T",
                "solint": "inf,32ch",
                "minblperant": 3,
            },
        ),
        (
            "B_inf_32ch",
            {
                "caltable": "Bf.tb",
                "gaintype": "G",
                "solint": "inf,32ch",
                "minblperant": 3,
                "_task": "bandpass",
            },
        ),
        (
            "G_16s",
            {"caltable": "G16.tb", "gaintype": "G", "solint": "16s", "minblperant": 3},
        ),
        (
            "G_12s",
            {"caltable": "G12.tb", "gaintype": "G", "solint": "12s", "minblperant": 3},
        ),
        (
            "G_8s",
            {"caltable": "G8.tb", "gaintype": "G", "solint": "8s", "minblperant": 3},
        ),
    ]:
        kw = dict(kw)
        task = kw.pop("_task", "gaincal")
        if task == "bandpass":
            kw.pop("gaintype")
            entry, _ = call(tag, bandpass, solnorm=False, bandtype="B", **common, **kw)
        else:
            entry, _ = call(tag, gaincal, **common, **kw)
        entry["table"] = caltable(kw["caltable"])
        r[tag] = entry
    # a task that pre-applies a table that was never written
    entry, _ = call(
        "B_missing_gaintable",
        bandpass,
        vis=ms,
        caltable="Bm.tb",
        refant="m000",
        solint="inf",
        gaintable=["G4.tb"],
        minblperant=3,
    )
    entry["table"] = caltable("Bm.tb")
    r["B_missing_gaintable"] = entry
    # seconds-solint bins against the integration pairs
    dumps = ms_times(ms)
    pairs = dumps[: dumps.size // 2 * 2].reshape(-1, 2).mean(axis=1)
    for tag in ("G_16s", "G_12s", "G_8s"):
        times = np.asarray(r[tag]["table"].get("times", []))
        if times.size:
            d = np.abs(times[:, None] - pairs[None, :]).min(axis=1)
            r[tag]["vs_pairs"] = {
                "n_dumps": int(dumps.size),
                "n_pairs": int(pairs.size),
                "n_solutions": int(times.size),
                "max_offset_from_pair_centre_s": float(d.max()),
                "offsets_s": np.round(times - dumps[0], 3).tolist(),
            }
    res["gaincal"] = r


def setjy_arms(res, tables):
    ms = "s.ms"
    fields = {"3C286": F3C286, "J1939-6342": F1934, "FOO": FFOO, "FORNAXA": FFORNAXA}
    spws = [
        ("L", 1.4e9, 1e6, 4),
        ("X1", 11.0e9, 1e6, 1),
        ("X2", 11.1e9, 1e6, 1),
        ("X3", 11.2e9, 1e6, 1),
    ]
    build(ms, fields, spws, nant=2, ndump=1, flux=0)
    r = {}

    def fluxd(ret):
        out = {}
        if isinstance(ret, dict):
            for fid, per in ret.items():
                if isinstance(per, dict):
                    for spw, v in per.items():
                        if isinstance(v, dict) and "fluxd" in v:
                            out[f"{fid}/{spw}"] = [
                                float(x) for x in np.asarray(v["fluxd"])
                            ][:1]
        return out

    common = {"vis": ms, "scalebychan": True, "usescratch": True}
    e, ret = call(
        "pb2010_3c286", setjy, field="3C286", standard="Perley-Butler 2010", **common
    )
    e["fluxd"] = fluxd(ret)
    r["pb2010_3c286"] = e
    before = model_col(ms)
    # tables absent from the working directory and from measurespath
    e, ret = call(
        "pb2017_3c286_no_tables",
        setjy,
        field="3C286",
        standard="Perley-Butler 2017",
        **common,
    )
    e["fluxd"] = fluxd(ret)
    after = model_col(ms)
    e["model_unchanged"] = bool(np.array_equal(before, after))
    e["model_nonzero_frac"] = float((np.abs(after) > 0).mean())
    r["pb2017_3c286_no_tables"] = e
    for field in ("FOO", "FORNAXA"):
        tag = f"pb2010_{field}"
        e, ret = call(tag, setjy, field=field, standard="Perley-Butler 2010", **common)
        e["fluxd"] = fluxd(ret)
        r[tag] = e
    e, ret = call(
        "sr2016_1934",
        setjy,
        field="J1939-6342",
        standard="Stevens-Reynolds 2016",
        **common,
    )
    e["fluxd"] = fluxd(ret)
    r["sr2016_1934"] = e
    if tables:
        for name in ("PerleyButler2017Coeffs", "PerleyButler2013Coeffs"):
            shutil.copytree(Path(tables) / name, name)
        for field in ("FOO", "FORNAXA", "3C286", "J1939-6342"):
            tag = f"pb2017_{field}_tables"
            before = model_col(ms)
            e, ret = call(
                tag, setjy, field=field, standard="Perley-Butler 2017", **common
            )
            e["fluxd"] = fluxd(ret)
            e["model_unchanged"] = bool(np.array_equal(before, model_col(ms)))
            r[tag] = e
        kw = {}
        tb = table()
        for name in ("PerleyButler2017Coeffs", "PerleyButler2013Coeffs"):
            tb.open(name, nomodify=True)
            kw[name] = {k: str(v)[:120] for k, v in tb.getkeywords().items()}
            tb.close()
        r["table_keywords"] = kw
    res["setjy"] = r


def main():
    global OUT
    OUT = Path(sys.argv[1]).resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    tables = sys.argv[2] if len(sys.argv) > 2 else None
    import casatasks
    import casatools

    res = {
        "casatools": casatools.version_string(),
        "casatasks": casatasks.version_string(),
    }
    t0 = time.time()
    gaincal_arms(res)
    setjy_arms(res, tables)
    res["wall_s"] = round(time.time() - t0, 1)
    (OUT / "result.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1)[:200])


if __name__ == "__main__":
    main()
