"""Host side of task C6 (research/c6-polterms.md): the polarisation terms
Gpol, KCROSS, Xf, Df and P against CASA 6.7.6.14 (class B, the chain on the
composite, class C) and the simulated truths `poldx` / `polholdout` (class T).

    python examples/check_pol.py casa <run> --version V [--cases B-poldx,...]
    python examples/check_pol.py compare <run> --casa <casa-run> --version V [--cases ...]
    python examples/check_pol.py truth <run> --casa <casa-run> --version V --set twin|noisy
    python examples/check_pol.py chain-truth <run> --casa <casa-run> --version V
    python examples/check_pol.py readback <run> --compare <compare-run> --casa <casa-run> --version V
    python examples/check_pol.py parang <run> --casa <casa-run> --version V

`casa` makes the shared MS copies (MODEL_DATA from A1's calibrator Stokes,
the RFI mask in FLAG on the noisy copy) and runs CASA's chain per case, the
O2 variant and `applycal(parang=True)` without tables. The other commands
read those copies and tables. Each writes `<run>/<command>.json`; exit 0 only
when every gated item passes.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_formats as cf
import check_gain as cg
from rang import cal_apply, cal_gain, cal_pol, core_ms, simtruth
from rang.formats import caltable

CASA = "/opt/casa/bin/python"
SETS = Path("/mnt/d/rang/outputs/c6-20261106-sets")
TRUTH_TABLES = ("K", "B", "G", "Kcross", "Xf", "Df")
REFANT = "m000"
CLASS_B = {"median": 7e-4, "p95": 3e-3}
KCROSS_TOL = 0.02  # ns
XF_TOL = {"median": 0.5, "p95": 2.0}  # degrees
DF_TOL = {"median": 1e-3, "p95": 5e-3}
P_TOL = 1e-3  # rad
T_TOL = {"products": 1e-5, "kcross": 1e-3, "xf": 1e-5, "df": 1e-5, "angle": 1e-9}

CASES = {
    "B-poldx": {"ms": "noisy", "gpol_solint": "60s", "kc_combine": "",
                "xf_combine": "scan", "uvrange": ""},
    "B-poldx-uv": {"ms": "noisy", "gpol_solint": "int", "kc_combine": "scan",
                   "xf_combine": "", "uvrange": ">150"},
    "B-twin": {"ms": "twin", "gpol_solint": "60s", "kc_combine": "",
               "xf_combine": "scan", "uvrange": ""},
}  # fmt: skip


def arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def paths(version):
    v = SETS / version
    return {
        "noisy": v / f"a1-{version}.ms",
        "twin": v / f"a1-{version}-twin.ms",
        "truth": v / "truth.npz",
        "rfi": v / f"a1-{version}.rfi_mask.npz",
        "tables": {k: SETS / f"casa-{version}" / f"truth.{k}" for k in TRUTH_TABLES},
    }


def write(path, payload):
    Path(path).write_text(json.dumps(payload, indent=1, default=float) + "\n")


def stats(x):
    x = np.asarray(x, float)
    if not x.size:
        return {"n": 0}
    return {
        "n": int(x.size),
        "median": float(np.median(x)),
        "p95": float(np.percentile(x, 95)),
        "max": float(x.max()),
    }


# -- the CASA side ------------------------------------------------------------


def casa_chain(name, cfg, ms, tt):
    """CARACal's polcal calls (C1 section 2.2) for one case, CASA's own
    earlier tables in each solve."""
    t = f"/run/casa/{name}"
    uv = cfg["uvrange"]
    common = {"vis": ms, "refant": REFANT, "minsnr": 3.0, "minblperant": 4}
    cc, cci = [tt["K"], tt["B"]], ["linear", "linear"]
    ccl, ccli = [tt["K"], tt["B"], tt["G"]], ["linear", "linear", "nearest"]
    return [
        {"task": "gaincal", "args": {**common, "caltable": f"{t}.Gpol", "field": "1",
            "gaintype": "G", "calmode": "p", "solint": cfg["gpol_solint"], "combine": "",
            "parang": True, "uvrange": uv, "gaintable": cc, "interp": cci}},
        {"task": "gaincal", "args": {**common, "caltable": f"{t}.Kcross", "field": "1",
            "gaintype": "KCROSS", "solint": "inf", "combine": cfg["kc_combine"],
            "parang": True, "uvrange": uv, "gaintable": cc + [f"{t}.Gpol"],
            "interp": cci + ["linear"]}},
        {"task": "polcal", "args": {**common, "caltable": f"{t}.Xf", "field": "1",
            "poltype": "Xf", "solint": "inf", "combine": cfg["xf_combine"], "uvrange": uv,
            "gaintable": cc + [f"{t}.Gpol", f"{t}.Kcross"],
            "interp": cci + ["linear", "nearest"]}},
        {"task": "polcal", "args": {**common, "caltable": f"{t}.Df", "field": "0",
            "poltype": "Df", "solint": "inf", "combine": "scan", "uvrange": uv,
            "gaintable": ccl + [f"{t}.Kcross", f"{t}.Xf"],
            "interp": ccli + ["nearest", "nearest"]}},
        {"task": "copytree", "args": {"src": f"{t}.Df", "dst": f"{t}.Df.clip"}},
        {"task": "flagdata", "args": {"vis": f"{t}.Df.clip", "mode": "clip",
            "clipminmax": [-0.6, 0.6], "datacolumn": "CPARAM", "flagbackup": False}},
    ]  # fmt: skip


def casa(run, argv):
    version = arg(argv, "--version")
    cases = arg(argv, "--cases", ",".join(CASES)).split(",")
    p = paths(version)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    truth = dict(np.load(p["truth"]))
    edits = run / "edits"
    edits.mkdir()
    rows, values = cg.a1_model(p["noisy"], truth, [0, 1], parang=False)
    np.savez(edits / "model.npz", rows=rows, values=values)
    nchan = len(truth["freq_hz"])
    rfi = cg.rfi_flags(p["noisy"], p["rfi"], nchan)
    np.savez(edits / "rfi.npz", rows=np.arange(len(rfi)), flag=rfi)
    write(
        edits / "noisy.json",
        {"model": "/run/edits/model.npz", "flag": "/run/edits/rfi.npz"},
    )
    write(edits / "twin.json", {"model": "/run/edits/model.npz"})
    tt = {k: f"/sets/casa-{version}/truth.{k}" for k in TRUTH_TABLES}
    steps = []
    for which, src in (("noisy", f"/sets/{version}/a1-{version}.ms"),
                       ("twin", f"/sets/{version}/a1-{version}-twin.ms")):  # fmt: skip
        steps += [
            f"cp -r {src} /run/casa/{which}.ms",
            f"{CASA} -I /ex/oracle_pol.py edit /run/casa/{which}.ms /run/edits/{which}.json",
        ]
    calls = []
    for name in cases:
        cfg = CASES[name]
        calls += casa_chain(name, cfg, f"/run/casa/{cfg['ms']}.ms", tt)
    # O2 (C1 section 5): CASA's chain of B-poldx with and without tfcrop on Xf,
    # applied to the polarised calibrator with parang=True.
    if "B-poldx" in cases:
        t = "/run/casa/B-poldx"
        calls += [
            {"task": "copytree", "args": {"src": f"{t}.Xf", "dst": f"{t}.Xf.tfcrop"}},
            {"task": "flagdata", "args": {"vis": f"{t}.Xf.tfcrop", "mode": "tfcrop",
                "ntime": "60s", "combinescans": True, "datacolumn": "CPARAM",
                "usewindowstats": "both", "flagbackup": False}},
        ]  # fmt: skip
        for tag, xf in (("o2-plain", f"{t}.Xf"), ("o2-tfcrop", f"{t}.Xf.tfcrop")):
            calls += [
                {"task": "copytree", "args": {"src": "/run/casa/noisy.ms",
                                              "dst": f"/run/casa/{tag}.ms"}},
                {"task": "applycal", "args": {"vis": f"/run/casa/{tag}.ms", "field": "1",
                    "gaintable": [tt["K"], tt["B"], f"{t}.Gpol", f"{t}.Kcross", xf],
                    "interp": ["linear", "linear", "linear", "nearest", "nearest"],
                    "calwt": [False] * 5, "parang": True, "applymode": "calflag",
                    "flagbackup": False}},
            ]  # fmt: skip
    # P: applycal(parang=True) without tables on the twin.
    calls += [
        {"task": "copytree", "args": {"src": "/run/casa/twin.ms", "dst": "/run/casa/p.ms"}},
        {"task": "applycal", "args": {"vis": "/run/casa/p.ms", "field": "1", "gaintable": [],
            "parang": True, "applymode": "calflag", "flagbackup": False}},
    ]  # fmt: skip
    write(run / "casa-spec.json", calls)
    steps.append(
        f"{CASA} -I /ex/oracle_pol.py tasks /run/casa-spec.json /run/casa-tasks.json"
    )
    exports = ["p"] + (["o2-plain", "o2-tfcrop"] if "B-poldx" in cases else [])
    for tag in exports:
        steps.append(
            f"{CASA} -I /ex/oracle_pol.py export /run/casa/{tag}.ms /run/casa/{tag}.npz "
            "CORRECTED_DATA FLAG FIELD_ID"
        )
    (run / "casa").mkdir()
    cf.TIMINGS.clear()
    cf.docker(
        cf.CASA_IMAGE,
        ["sh", "-c", " && ".join(steps)],
        [(run, "/run", "rw"), (HERE, "/ex", "ro"), (SETS, "/sets", "ro")],
        "casa polarisation chain",
    )
    for tag in exports:
        if tag != "p":
            import shutil

            shutil.rmtree(run / "casa" / f"{tag}.ms")
    results = json.loads((run / "casa-tasks.json").read_text())
    errors = [r for r in results if r["error"]]
    out = {
        "version": version,
        "cases": cases,
        "errors": errors,
        "timings": cf.TIMINGS,
        "seconds": time.perf_counter() - started,
        "task_seconds": [
            (r["task"], r["call"].get("caltable"), r["seconds"]) for r in results
        ],
    }
    write(run / "casa.json", out)
    return 0 if not errors else 1


# -- reading tables -------------------------------------------------------------


def cube(table, nant):
    """`(times, values (time, ant, chan, par), flags, antenna2 per time)` of
    a table, rows sorted by time."""
    tm = table.column("TIME")
    times = np.unique(tm)
    p, f = table.params, table.flags
    a1, a2 = table.column("ANTENNA1"), table.column("ANTENNA2")
    vals = np.zeros((len(times), nant) + p.shape[1:], p.dtype)
    fl = np.ones((len(times), nant) + p.shape[1:], bool)
    ref = np.full(len(times), -9)
    for r in range(table.nrows):
        t = int(np.searchsorted(times, tm[r]))
        vals[t, a1[r]] = p[r]
        fl[t, a1[r]] = f[r]
        ref[t] = a2[r]
    return times, vals, fl, ref


def gpol_compare(rt, ct, nant):
    rtimes, rv, rf, rref = cube(rt, nant)
    ctimes, cv, cfl, cref = cube(ct, nant)
    out = {"intervals": [len(rtimes), len(ctimes)]}
    if len(rtimes) != len(ctimes):
        out["pass"] = False
        return out
    g1, f1 = rv[:, :, 0, :][:, None], rf[:, :, 0, :][:, None]
    g2, f2 = cv[:, :, 0, :][:, None], cfl[:, :, 0, :][:, None]
    prod = cg.product_compare(g1, f1, g2, f2, absolute=False)
    p1, ok1, _ = cal_gain.baseline_products(g1, f1)
    p2, ok2, _ = cal_gain.baseline_products(g2, f2)
    ph = np.degrees(np.abs(np.angle(p1 / np.where(p2 == 0, 1, p2))))[ok1 & ok2]
    out.update(
        products=prod,
        phase_deg=stats(ph),
        flags_differ=int((rf != cfl).sum()),
        refant_equal=bool(np.array_equal(rref, cref)),
        max_time_diff_s=float(np.max(np.abs(rtimes - ctimes))),
    )
    out["pass"] = bool(
        prod["products"] > 0
        and prod["median_rel"] <= CLASS_B["median"]
        and prod["p95_rel"] <= CLASS_B["p95"]
        and out["flags_differ"] == 0
        and out["refant_equal"]
    )
    return out


def kcross_compare(rt, ct, nant):
    rtimes, rv, rf, rref = cube(rt, nant)
    ctimes, cv, cfl, cref = cube(ct, nant)
    out = {"intervals": [len(rtimes), len(ctimes)]}
    if len(rtimes) != len(ctimes):
        out["pass"] = False
        return out
    d = np.abs(rv[:, 0, 0, 0].astype(float) - cv[:, 0, 0, 0].astype(float))
    out.update(
        rang_ns=rv[:, 0, 0, 0].tolist(),
        casa_ns=cv[:, 0, 0, 0].tolist(),
        abs_diff_ns=d.tolist(),
        second_param_casa=float(np.abs(cv[..., 1]).max()),
        flags_differ=int((rf != cfl).sum()),
        antenna2=[sorted(set(rref.tolist())), sorted(set(cref.tolist()))],
        max_time_diff_s=float(np.max(np.abs(rtimes - ctimes))),
    )
    out["pass"] = bool(d.max() <= KCROSS_TOL and out["flags_differ"] == 0)
    return out


def xf_compare(rt, ct, nant):
    rtimes, rv, rf, rref = cube(rt, nant)
    ctimes, cv, cfl, cref = cube(ct, nant)
    out = {"intervals": [len(rtimes), len(ctimes)]}
    if len(rtimes) != len(ctimes):
        out["pass"] = False
        return out
    x1, x2 = rv[:, 0, :, 0], cv[:, 0, :, 0]
    ok = ~rf[:, 0, :, 0] & ~cfl[:, 0, :, 0]
    dphi = np.degrees(np.abs(np.angle(x1 / np.where(x2 == 0, 1, x2))))[ok]
    s = stats(dphi)
    out.update(
        phase_deg=s,
        flags_differ=int((rf != cfl).sum()),
        all_antennas_equal_rang=bool(np.all(rv == rv[:, :1])),
        all_antennas_equal_casa=bool(np.all(cv == cv[:, :1])),
        antenna2=[sorted(set(rref.tolist())), sorted(set(cref.tolist()))],
    )
    out["pass"] = bool(
        s["n"] > 0
        and s["median"] <= XF_TOL["median"]
        and s["p95"] <= XF_TOL["p95"]
        and out["flags_differ"] == 0
    )
    return out


def gauge_free(d, f):
    """`d_x,p + conj(d_y,q)` and `d_y,p + conj(d_x,q)` over ordered pairs
    p != q: `d`, `f` (ant, chan, 2)."""
    nant = d.shape[0]
    p, q = np.array([(a, b) for a in range(nant) for b in range(nant) if a != b]).T
    g1 = d[p, :, 0] + np.conj(d[q, :, 1])
    g2 = d[p, :, 1] + np.conj(d[q, :, 0])
    ok1 = ~f[p, :, 0] & ~f[q, :, 1]
    ok2 = ~f[p, :, 1] & ~f[q, :, 0]
    return np.concatenate([g1, g2]), np.concatenate([ok1, ok2])


def df_compare(rt, ct, nant, rclip=None, cclip=None):
    _, rv, rf, rref = cube(rt, nant)
    _, cv, cfl, cref = cube(ct, nant)
    rv, rf, cv, cfl = rv[0], rf[0], cv[0], cfl[0]
    g1, ok1 = gauge_free(rv, rf)
    g2, ok2 = gauge_free(cv, cfl)
    ok = ok1 & ok2
    gs = stats(np.abs(g1 - g2)[ok])
    okt = ~rf & ~cfl
    ts = stats(np.abs(rv - cv)[okt])
    out = {
        "gauge_free": gs,
        "referenced": ts,
        "flags_differ": int((rf != cfl).sum()),
        "antenna2": [sorted(set(rref.tolist())), sorted(set(cref.tolist()))],
        "leakage_amplitude_casa": stats(np.abs(cv)[~cfl]),
    }
    passed = all(
        s["n"] > 0 and s["median"] <= DF_TOL["median"] and s["p95"] <= DF_TOL["p95"]
        for s in (gs, ts)
    )
    passed &= out["flags_differ"] == 0
    if rclip is not None:
        out["clip_flags_differ"] = int((rclip.flags != cclip.flags).sum())
        out["clip_flags"] = [int(rclip.flags.sum()), int(cclip.flags.sum())]
        passed &= out["clip_flags_differ"] == 0
    out["pass"] = bool(passed)
    return out


# -- rang solves ----------------------------------------------------------------


def rang_terms(ms, cfg, tt, earlier, field_x=1, field_d=0):
    """Rang's four terms. `earlier(term)` gives the earlier pol tables to
    pre-apply: CASA's (B-cases) or rang's own (the chain)."""
    uv = cfg["uvrange"]
    cc = [tt["K"], tt["B"]]
    ccl = [tt["K"], tt["B"], tt["G"]]
    out, seconds = {}, {}
    t0 = time.perf_counter()
    out["Gpol"], _, _ = cal_pol.gpol(
        ms, field_id=field_x, solint=cfg["gpol_solint"], refant=0, uvrange=uv,
        gaintable=cc, interp=["linear", "linear"],
    )  # fmt: skip
    seconds["Gpol"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    g = earlier("Gpol", out)
    out["Kcross"], ks, _ = cal_pol.kcross(
        ms, field_id=field_x, solint="inf", combine=cfg["kc_combine"], uvrange=uv,
        gaintable=cc + [g], interp=["linear", "linear", "linear"], refant=REFANT,
    )  # fmt: skip
    seconds["Kcross"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    k = earlier("Kcross", out)
    out["Xf"], _, _ = cal_pol.xf(
        ms, field_id=field_x, solint="inf", combine=cfg["xf_combine"], uvrange=uv,
        gaintable=cc + [g, k], interp=["linear", "linear", "linear", "nearest"],
    )  # fmt: skip
    seconds["Xf"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    x = earlier("Xf", out)
    out["Df"], dsol, _ = cal_pol.df(
        ms, field_id=field_d, solint="inf", combine="scan", refant=0, uvrange=uv,
        gaintable=ccl + [k, x],
        interp=["linear", "linear", "nearest", "nearest", "nearest"],
    )  # fmt: skip
    seconds["Df"] = time.perf_counter() - t0
    out["Df.clip"], _nclip = cal_pol.clip_df(out["Df"])
    return (
        out,
        seconds,
        {"kcross_err_ns": ks.err_ns.tolist(), "df_gauge_fixed": dsol.gauge_fixed},
    )


def probes(nrow, nchan):
    unpol = simtruth.stokes_coherency(np.array([1.0, 0, 0, 0]))
    pol = simtruth.stokes_coherency(np.array([1.0, 0.06, 0.08, 0]))
    return [
        np.broadcast_to(m, (nrow, nchan, 4)).astype(np.complex64) for m in (unpol, pol)
    ]


def composite(ms, rtabs, ctabs):
    """C-gate: both sides' pol tables corrupting the probe models, fields 0
    and 1 (Gpol on field 1 only)."""
    c = cal_gain._ms_columns(ms, ["TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID"])
    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as t:
        freq = np.asarray(t.getcol("CHAN_FREQ")[0], float)
    errs, flags_equal, cells = [], True, 0
    for fid in (0, 1):
        rows = np.flatnonzero((c["FIELD_ID"] == fid) & (c["ANTENNA1"] != c["ANTENNA2"]))
        names = (["Gpol"] if fid == 1 else []) + ["Kcross", "Xf", "Df"]
        interp = (["linear"] if fid == 1 else []) + ["nearest"] * 3
        for m in probes(len(rows), len(freq)):
            v = []
            for tabs in (rtabs, ctabs):
                vv, ff = cal_pol.apply(
                    m, False, c["TIME"][rows], c["ANTENNA1"][rows], c["ANTENNA2"][rows],
                    freq, [tabs[n] for n in names], direction="corrupt", interp=interp,
                    field_id=fid,
                )  # fmt: skip
                v.append((vv.astype(np.complex128), ff))
            (vr, fr), (vc, fc) = v
            flags_equal &= bool(np.array_equal(fr, fc))
            ok = ~fr & ~fc
            scale = np.max(np.abs(vc), axis=-1, keepdims=True)
            e = np.abs(vr - vc) / np.where(scale > 0, scale, 1)
            errs.append(e[ok])
            cells += int(ok.sum())
    s = stats(np.concatenate(errs))
    return {
        "relative_to_cell_max": s,
        "flags_exact": flags_equal,
        "pass": bool(
            s["n"] > 0
            and s["median"] <= CLASS_B["median"]
            and s["p95"] <= CLASS_B["p95"]
            and flags_equal
        ),
    }


def compare(run, argv):
    version = arg(argv, "--version")
    crun = Path(arg(argv, "--casa"))
    cases = arg(argv, "--cases", ",".join(CASES)).split(",")
    p = paths(version)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    (run / "rang").mkdir()
    started = time.perf_counter()
    tt = {k: caltable.read(v) for k, v in p["tables"].items()}
    results = {}
    ok_all = True
    for name in cases:
        cfg = CASES[name]
        ms = crun / "casa" / f"{cfg['ms']}.ms"
        base = crun / "casa" / name
        ctabs = {
            k: caltable.read(f"{base}.{k}") for k in ("Gpol", "Kcross", "Xf", "Df")
        }
        ctabs["Df.clip"] = caltable.read(f"{base}.Df.clip")
        nant = len(cal_pol.receptor_angles(ms))
        res = {}
        for mode in ("B", "C"):
            if mode == "B":

                def earlier(term, out, ct=ctabs):
                    return ct[term]
            else:

                def earlier(term, out):
                    return out[term]

            rtabs, secs, extra = rang_terms(ms, cfg, tt, earlier)
            tag = name if mode == "B" else "C" + name[1:]
            for k, t in rtabs.items():
                caltable.write(t, run / "rang" / f"{tag}.{k}")
            terms = {
                "Gpol": gpol_compare(rtabs["Gpol"], ctabs["Gpol"], nant),
                "Kcross": kcross_compare(rtabs["Kcross"], ctabs["Kcross"], nant),
                "Xf": xf_compare(rtabs["Xf"], ctabs["Xf"], nant),
                "Df": df_compare(
                    rtabs["Df"], ctabs["Df"], nant, rtabs["Df.clip"], ctabs["Df.clip"]
                ),
            }
            entry = {"terms": terms, "rang_seconds": secs, **extra}
            if mode == "B":
                entry["pass"] = all(v["pass"] for v in terms.values())
            else:
                entry["composite"] = composite(ms, rtabs, ctabs)
                entry["pass"] = bool(
                    entry["composite"]["pass"] and terms["Kcross"]["pass"]
                )
            ok_all &= entry["pass"]
            res[tag] = entry
            print(tag, "PASS" if entry["pass"] else "FAIL",
                  json.dumps(entry, default=float)[:3000], flush=True)  # fmt: skip
        results[name] = res
    # O2 and the table layouts against CASA's own (reported).
    extra = {}
    o2p, o2t = crun / "casa" / "o2-plain.npz", crun / "casa" / "o2-tfcrop.npz"
    if o2p.exists():
        a, b = np.load(o2p), np.load(o2t)
        sel = a["FIELD_ID"] == 1
        va, vb = a["CORRECTED_DATA"][sel], b["CORRECTED_DATA"][sel]
        fa, fb = a["FLAG"][sel], b["FLAG"][sel]
        ok = ~fa.any(-1) & ~fb.any(-1)
        qa = (va[..., 0] - va[..., 3]) / 2 + 1j * (va[..., 1] + va[..., 2]) / 2
        qb = (vb[..., 0] - vb[..., 3]) / 2 + 1j * (vb[..., 1] + vb[..., 2]) / 2
        extra["O2"] = {
            "cells_both_unflagged": int(ok.sum()),
            "flags_added_by_tfcrop": int(fb.sum() - fa.sum()),
            "chi_change_deg": stats(np.degrees(np.abs(np.angle(qb[ok] / qa[ok]))) / 2),
            "relative_qu_change": stats(np.abs(qb[ok] - qa[ok]) / np.abs(qa[ok])),
        }
    layouts = {}
    for name in cases:
        for k in ("Gpol", "Kcross", "Xf", "Df"):
            r = caltable.read(run / "rang" / f"{name}.{k}")
            c = caltable.read(crun / "casa" / f"{name}.{k}")
            layouts[f"{name}.{k}"] = {
                "vis_cal": [r.vis_cal, c.vis_cal],
                "par_type": [r.keywords.get("ParType"), c.keywords.get("ParType")],
                "param_shape": [list(r.params.shape[1:]), list(c.params.shape[1:])],
                "window_channels": [
                    len(r.solution_frequencies(0)),
                    len(c.solution_frequencies(0)),
                ],
                "antenna2": [r.reference_antenna, c.reference_antenna],
                "time_casa_minus_rang_s": float(
                    np.max(
                        np.abs(
                            np.unique(c.column("TIME")) - np.unique(r.column("TIME"))
                        )
                    )
                )
                if len(np.unique(c.column("TIME"))) == len(np.unique(r.column("TIME")))
                else None,
                "interval": [
                    float(r.column("INTERVAL")[0]),
                    float(c.column("INTERVAL")[0]),
                ],
                "equal": bool(
                    r.vis_cal == c.vis_cal
                    and r.keywords.get("ParType") == c.keywords.get("ParType")
                    and r.params.shape[1:] == c.params.shape[1:]
                    and r.reference_antenna == c.reference_antenna
                ),
            }
    extra["layouts"] = layouts
    out = {"version": version, "casa_run": str(crun), "results": results, **extra,
           "seconds": time.perf_counter() - started, "pass": bool(ok_all)}  # fmt: skip
    write(run / "compare.json", out)
    return 0 if ok_all else 1


# -- class T --------------------------------------------------------------------


def truth_index(truth, time):
    ti = np.searchsorted(truth["time"], time)
    if not np.array_equal(truth["time"][ti], time):
        raise SystemExit("truth times do not match the MS")
    return ti


def z_gate(z):
    z = np.asarray(z, float)
    n = len(z)
    lim = 3 * 1.2533 / np.sqrt(n) if n else 0.0
    med = float(np.median(z)) if n else None
    return {"n": n, "median": med, "limit": lim, "std": float(np.std(z)) if n else None,
            "pass": bool(n and abs(med) <= lim)}  # fmt: skip


def truth(run, argv):
    version = arg(argv, "--version")
    crun = Path(arg(argv, "--casa"))
    which = arg(argv, "--set")
    twin = which == "twin"
    p = paths(version)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    t = dict(np.load(p["truth"]))
    tt = {k: caltable.read(v) for k, v in p["tables"].items()}
    ms = crun / "casa" / f"{which}.ms"
    len(t["antenna_index"])
    res = {}
    near = lambda n: ["nearest"] * n
    # P.
    c = cal_gain._ms_columns(ms, ["TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID"])
    rows = np.flatnonzero(c["FIELD_ID"] == 1)
    ap, aq = cal_pol.row_angles(
        ms, c["TIME"][rows], c["ANTENNA1"][rows], c["ANTENNA2"][rows], 1
    )
    ti = truth_index(t, c["TIME"][rows])
    want = t["parallactic_angle"] + t["receptor_angle"][0]
    dp = np.abs(np.angle(np.exp(1j * (ap - want[ti, c["ANTENNA1"][rows]]))))
    dq = np.abs(np.angle(np.exp(1j * (aq - want[ti, c["ANTENNA2"][rows]]))))
    m = float(max(dp.max(), dq.max()))
    res["P"] = {"max_abs_rad": m, "pass": m <= T_TOL["angle"]}
    # Gpol.
    _tab, sol, info = cal_pol.gpol(
        ms, field_id=1, solint="60s", refant=0,
        gaintable=[tt["K"], tt["B"], tt["Kcross"], tt["Df"], tt["Xf"]], interp=near(5),
    )  # fmt: skip
    tb = info["time_bin"]
    rowt = cal_gain._ms_columns(ms, ["TIME"], info["row_index"])["TIME"]
    ntime = sol.gains.shape[0]
    g = t["raw_gain"] * t["raw_selfcal"][..., None]
    gt = np.stack([g[truth_index(t, rowt[tb == k][:1])[0]] for k in range(ntime)])
    gt = (gt / np.abs(gt))[:, None]
    ft = np.zeros(gt.shape, bool)
    p1, ok1, pairs = cal_gain.baseline_products(sol.gains, sol.flags)
    p2, _, _ = cal_gain.baseline_products(gt, ft)
    pi, qi = np.array(pairs).T
    if twin:
        e = float(np.abs(p1 - p2)[ok1].max())
        res["Gpol"] = {"max_abs": e, "pass": e <= T_TOL["products"]}
    else:
        s = np.sqrt(sol.err[:, :, pi, :] ** 2 + sol.err[:, :, qi, :] ** 2)
        z = ((p1 - p2) / np.where(s > 0, s, 1))[ok1 & (s > 0)]
        zr, zi = z_gate(z.real), z_gate(z.imag)
        res["Gpol"] = {"re": zr, "im": zi, "pass": zr["pass"] and zi["pass"]}
    # KCROSS.
    _tab, ks, _ld = cal_pol.kcross(
        ms, field_id=1, solint="inf", combine="",
        gaintable=[tt["K"], tt["B"], tt["G"], tt["Df"], tt["Xf"]], interp=near(5),
    )  # fmt: skip
    tau_true = float(
        json.loads((SETS / version / "truth.json").read_text())["design"]["tau_c_ns"]
    )
    d = ks.delay_ns - tau_true
    if twin:
        res["Kcross"] = {"delays": ks.delay_ns.tolist(), "max_abs_ns": float(np.abs(d).max()),
                         "pass": bool(np.abs(d).max() <= T_TOL["kcross"])}  # fmt: skip
    else:
        zg = z_gate(d / ks.err_ns)
        res["Kcross"] = {
            "delays": ks.delay_ns.tolist(),
            "err": ks.err_ns.tolist(),
            **zg,
        }
    # Xf.
    _tab, xs, _ld = cal_pol.xf(
        ms, field_id=1, solint="inf", combine="scan",
        gaintable=[tt["K"], tt["B"], tt["G"], tt["Kcross"], tt["Df"]], interp=near(5),
    )  # fmt: skip
    dphi = np.angle(xs.x / t["raw_xf"][None])[xs.ok]
    if twin:
        res["Xf"] = {"max_abs_rad": float(np.abs(dphi).max()),
                     "pass": bool(np.abs(dphi).max() <= T_TOL["xf"])}  # fmt: skip
    else:
        res["Xf"] = z_gate(dphi / xs.err[xs.ok])
    # Df.
    _tab, ds, _ld = cal_pol.df(
        ms, field_id=0, solint="inf", combine="scan", refant=0,
        gaintable=[tt["K"], tt["B"], tt["G"], tt["Kcross"], tt["Xf"]], interp=near(5),
    )  # fmt: skip
    leak = t["raw_leakage"].copy()
    zx = leak[0, :, 0].copy()
    leak[..., 0] -= zx[None]
    leak[..., 1] += np.conj(zx)[None]
    got = ds.d[0].transpose(1, 0, 2)  # (ant, chan, 2)
    okd = ~ds.flags[0].transpose(1, 0, 2)
    fixed = np.zeros_like(okd)
    fixed[0, :, 0] = True
    if twin:
        e = float(np.abs(got - leak)[okd].max())
        res["Df"] = {"max_abs": e, "pass": e <= T_TOL["df"]}
    else:
        sel = okd & ~fixed
        vr = ds.var_re[0].transpose(1, 0, 2)[sel]
        vi = ds.var_im[0].transpose(1, 0, 2)[sel]
        dd = (got - leak)[sel]
        zr, zi = z_gate(dd.real / np.sqrt(vr)), z_gate(dd.imag / np.sqrt(vi))
        res["Df"] = {"re": zr, "im": zi, "pass": zr["pass"] and zi["pass"],
                     "chi2_reduced_median": float(np.median(ds.chi2 / np.maximum(ds.neq - ds.npar, 1)))}  # fmt: skip
    ok_all = all(v["pass"] for v in res.values())
    for k, v in res.items():
        print(
            k,
            "PASS" if v["pass"] else "FAIL",
            json.dumps(v, default=float)[:1500],
            flush=True,
        )
    write(run / "truth.json", {"version": version, "set": which, "results": res,
                               "seconds": time.perf_counter() - started, "pass": ok_all})  # fmt: skip
    return 0 if ok_all else 1


def chain_truth(run, argv):
    """Reported: rang's chain on the twin in CARACal's order, the corrected
    calibrators against the truth's sky model."""
    version = arg(argv, "--version")
    crun = Path(arg(argv, "--casa"))
    p = paths(version)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    t = dict(np.load(p["truth"]))
    tt = {k: caltable.read(v) for k, v in p["tables"].items()}
    ms = crun / "casa" / "twin.ms"
    ccx = [tt["K"], tt["B"], tt["G"]]
    li = ["linear", "linear", "nearest"]
    gp, _, _ = cal_pol.gpol(
        ms, field_id=1, solint="60s", refant=0, gaintable=ccx, interp=li
    )
    kc, _, _ = cal_pol.kcross(
        ms, field_id=1, gaintable=ccx + [gp], interp=li + ["linear"]
    )
    xf, _, _ = cal_pol.xf(ms, field_id=1, combine="scan", gaintable=ccx + [gp, kc],
                          interp=li + ["linear", "nearest"])  # fmt: skip
    df, _, _ = cal_pol.df(ms, field_id=0, refant=0, gaintable=ccx + [kc, xf],
                          interp=li + ["nearest", "nearest"])  # fmt: skip
    c = cal_gain._ms_columns(
        ms, ["TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID", "DATA", "FLAG"]
    )
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as tb:
        freq = np.asarray(tb.getcol("CHAN_FREQ")[0], float)
    res = {}
    kc_true = float(
        json.loads((SETS / version / "truth.json").read_text())["design"]["tau_c_ns"]
    )
    res["kcross_ns"] = [float(kc.params[0, 0, 0]), kc_true]
    for fid in (0, 1):
        rows = np.flatnonzero(c["FIELD_ID"] == fid)
        ang = cal_pol.row_angles(
            ms, c["TIME"][rows], c["ANTENNA1"][rows], c["ANTENNA2"][rows], fid
        )
        tabs = ccx + ([gp] if fid == 1 else []) + [kc, xf, df]
        it = li + (["linear"] if fid == 1 else []) + ["nearest"] * 3
        v, f = cal_pol.apply(c["DATA"][rows], c["FLAG"][rows], c["TIME"][rows],
                             c["ANTENNA1"][rows], c["ANTENNA2"][rows], freq, tabs,
                             angles=ang, interp=it, field_id=fid)  # fmt: skip
        s = t["calibrator_stokes"][fid]
        ok = ~f.any(-1)
        if fid == 1:
            qu = (v[..., 0] - v[..., 3]) / 2 + 1j * (v[..., 1] + v[..., 2]) / 2
            want = s[:, 1] + 1j * s[:, 2]
            rel = np.abs(qu - want[None]) / np.abs(want[None])
            chi = np.degrees(np.abs(np.angle(qu / want[None]))) / 2
            pfrac = np.abs(qu) / np.abs((v[..., 0] + v[..., 3]) / 2)
            res["xcal"] = {"relative_qu_error": stats(rel[ok]), "chi_error_deg": stats(chi[ok]),
                           "p_fraction": stats(pfrac[ok]),
                           "p_true": float(np.median(np.abs(want) / s[:, 0]))}  # fmt: skip
        else:
            i = (v[..., 0] + v[..., 3]) / 2
            cross = np.abs(np.stack([v[..., 1], v[..., 2]], -1)) / np.abs(i)[..., None]
            res["fcal"] = {"cross_over_i": stats(cross[ok])}
    d_ref = float(np.median(np.abs(t["raw_leakage"][0, :, 0])))
    res["refant_dx_median"] = d_ref
    write(run / "chain-truth.json", {"version": version, "results": res})
    print(json.dumps(res, indent=1, default=float))
    return 0


# -- class C and P ----------------------------------------------------------------


def readback(run, argv):
    version = arg(argv, "--version")
    crun, brun = Path(arg(argv, "--casa")), Path(arg(argv, "--compare"))
    case = arg(argv, "--case", "B-poldx")
    paths(version)
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    (run / "casa").mkdir()
    started = time.perf_counter()
    tt = {k: f"/sets/casa-{version}/truth.{k}" for k in TRUTH_TABLES}
    r = f"/rang/{case}"
    specs = {
        1: ([tt["K"], tt["B"], f"{r}.Gpol", f"{r}.Kcross", f"{r}.Xf", f"{r}.Df"],
            ["linear", "linear", "linear", "nearest", "nearest", "nearest"]),
        0: ([tt["K"], tt["B"], tt["G"], f"{r}.Kcross", f"{r}.Xf", f"{r}.Df"],
            ["linear", "linear", "nearest", "nearest", "nearest", "nearest"]),
    }  # fmt: skip
    calls = [{"task": "copytree", "args": {"src": f"/casa/{CASES[case]['ms']}.ms",
                                           "dst": "/run/casa/rb.ms"}}]  # fmt: skip
    for fid, (tabs, it) in specs.items():
        calls.append({"task": "applycal", "args": {"vis": "/run/casa/rb.ms", "field": str(fid),
            "gaintable": tabs, "interp": it, "calwt": [False] * len(tabs), "parang": False,
            "applymode": "calflag", "flagbackup": False}})  # fmt: skip
    write(run / "spec.json", calls)
    steps = [
        f"{CASA} -I /ex/oracle_pol.py tasks /run/spec.json /run/tasks.json",
        f"{CASA} -I /ex/oracle_pol.py export /run/casa/rb.ms /run/casa/rb.npz CORRECTED_DATA FLAG FIELD_ID",
    ]
    cf.TIMINGS.clear()
    cf.docker(
        cf.CASA_IMAGE,
        ["sh", "-c", " && ".join(steps)],
        [
            (run, "/run", "rw"),
            (HERE, "/ex", "ro"),
            (SETS, "/sets", "ro"),
            (brun / "rang", "/rang", "ro"),
            (crun / "casa", "/casa", "ro"),
        ],
        "casa applycal of rang's tables",
    )
    import shutil

    shutil.rmtree(run / "casa" / "rb.ms")
    z = np.load(run / "casa" / "rb.npz")
    ms = crun / "casa" / f"{CASES[case]['ms']}.ms"
    c = cal_gain._ms_columns(
        ms, ["TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID", "DATA", "FLAG"]
    )
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as tb:
        freq = np.asarray(tb.getcol("CHAN_FREQ")[0], float)
    res = {}
    for fid, (tabs, it) in specs.items():
        rows = np.flatnonzero(c["FIELD_ID"] == fid)
        hosts = {"/sets/": f"{SETS}/", "/rang/": f"{brun / 'rang'}/"}
        local = [
            caltable.read(
                next(h + tp[len(g) :] for g, h in hosts.items() if tp.startswith(g))
            )
            for tp in tabs
        ]
        v, f = cal_pol.apply(c["DATA"][rows], c["FLAG"][rows], c["TIME"][rows],
                             c["ANTENNA1"][rows], c["ANTENNA2"][rows], freq, local,
                             interp=it, field_id=fid)  # fmt: skip
        cv, cfl = z["CORRECTED_DATA"][rows], z["FLAG"][rows]
        cc = cal_apply.class_c(v, cv, ~cfl)
        cc["flags_exact"] = bool(np.array_equal(f, cfl))
        cc["pass"] = bool(cc["pass"] and cc["flags_exact"])
        res[f"field{fid}"] = cc
    ok = all(v["pass"] for v in res.values())
    print(json.dumps(res, indent=1, default=float))
    write(run / "readback.json", {"case": case, "results": res, "timings": cf.TIMINGS,
                                  "seconds": time.perf_counter() - started, "pass": ok})  # fmt: skip
    return 0 if ok else 1


def parang(run, argv):
    version = arg(argv, "--version")
    crun = Path(arg(argv, "--casa"))
    run = Path(run)
    run.mkdir(parents=True, exist_ok=False)
    ms = crun / "casa" / "twin.ms"
    z = np.load(crun / "casa" / "p.npz")
    c = cal_gain._ms_columns(
        ms, ["TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID", "DATA", "FLAG"]
    )
    rows = np.flatnonzero(c["FIELD_ID"] == 1)
    res = {}
    for frame in ("casa", "rang"):
        ang = cal_pol.row_angles(ms, c["TIME"][rows], c["ANTENNA1"][rows], c["ANTENNA2"][rows], 1,
                                 frame)  # fmt: skip
        v = cal_pol.rotate(c["DATA"][rows], *ang, inverse=True).astype(np.complex128)
        cv = z["CORRECTED_DATA"][rows].astype(np.complex128)
        qu = (v[..., 0] - v[..., 3]) / 2 + 1j * (v[..., 1] + v[..., 2]) / 2
        cqu = (cv[..., 0] - cv[..., 3]) / 2 + 1j * (cv[..., 1] + cv[..., 2]) / 2
        delta = np.abs(np.angle(qu / cqu)) / 2
        s = stats(delta.ravel())
        res[frame] = {"delta_rad": s, "flags_casa": int(z["FLAG"][rows].sum()),
                      "pass": bool(s["median"] <= P_TOL and s["p95"] <= P_TOL)}  # fmt: skip
    print(json.dumps(res, indent=1, default=float))
    # Gated: the default (CASA) frame; rang's earlier frame reported.
    write(
        run / "parang.json",
        {"version": version, "results": res, "pass": res["casa"]["pass"]},
    )
    return 0 if res["casa"]["pass"] else 1


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    cmd, run = argv[1], argv[2]
    fn = {"casa": casa, "compare": compare, "truth": truth, "chain-truth": chain_truth,
          "readback": readback, "parang": parang}[cmd]  # fmt: skip
    return fn(run, argv[3:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
