"""Validation 2 of `calibrate.average_time` (task E2, research/e2-average-time.md
section 2): LUNO development scans 1 (3C286, MAIN_0) and 2 (PKS 1934-638,
MAIN_1), rang with the key against CASA 6.7.6.14 with CARACal's calls.

    python e2avg_luno.py build RUN        convert and verify (Windows venv)
    python e2avg_luno.py readable RUN     listobs, casacore tables, numcodecs chunks
    python e2avg_luno.py rang RUN         copy for CASA, then rang-core run (calibrate)
    python e2avg_luno.py casa RUN         receptor angle -90 on the copy, CARACal's calls
    python e2avg_luno.py score RUN        class B comparison, RUN/luno-score.json

RUN is a Windows path (D:\\...); containers run through `wsl docker`, every
heavy step under tools/heavy_lock.py (the caller wraps the command).
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import e2avg_common as C
from rang import cal_apply, core_ms

ROOT = C.ROOT
STORE = Path(r"D:\rang\data\e2-d\LBAND_LUNO_CALIBRATORS.zarr")
GROUPS = [f"{STORE}:MAIN_0", f"{STORE}:MAIN_1"]
CONVERT = ROOT / "research" / "results" / "e2-acceptance-scripts" / "e2_convert.py"
STRATEGY = "mk_rfi_flagging_calibrator_fields_firstpass.yaml"
FCAL, XCAL = "J1939-6342", "J1331+3030"
UVRANGE = ">150"
LIN, NEAR = "linear", "nearest"
X286 = {"fluxdensity": [14.7172, 0.0, 0.0, 0.0], "spix": [-0.4507, -0.1798, 0.0357],
        "reffreq": "1.47GHz", "polindex": [0.098], "polangle": [0.575959],
        "rotmeas": 0.0}  # fmt: skip
CONFIG = f"""\
version: 1
fields: {{fcal: [{FCAL}], bpcal: [{FCAL}], xcal: [{XCAL}]}}
data: {{weights: uniform, memory_limit_gb: 8}}
flag: {{strategy: {STRATEGY}}}
calibrate:
  model: {{source: setjy, standard: Stevens-Reynolds 2016}}
  refant: auto
  uvrange: "{UVRANGE}"
  average_time: true
  primary:
    field: [fcal]
    terms:
      - {{type: K, name: K, solint: inf}}
      - {{type: G, name: G, solint: inf, calmode: ap, preapply: [K], interp: [linear]}}
      - {{type: B, name: B, solint: inf, combine: scan, preapply: [K, G],
         interp: [linear, linear]}}
  secondary:
    field: [fcal]
    terms: []
  polcal:
    field: [xcal]
    model: {{source: nrao, name: 3C286}}
    feed_angle_rotation: -90
    extendflags: false
    terms:
      - {{type: Gpol, name: Gpol, solint: 60s, calmode: p, parang: true,
         preapply: [K, G, B], interp: [linear, linear, linear]}}
      - {{type: KCROSS, name: Kcross, solint: inf, parang: true,
         preapply: [K, G, B, Gpol], interp: [linear, linear, linear, linear]}}
      - {{type: Xf, name: Xf, solint: inf, combine: scan, parang: true,
         preapply: [K, G, B, Gpol, Kcross],
         interp: [linear, linear, linear, linear, nearest]}}
      - {{type: Df, name: Df, field: [fcal], solint: inf, combine: scan, parang: true,
         clip: [-0.6, 0.6], preapply: [K, G, B, Kcross, Xf],
         interp: [linear, linear, linear, nearest, nearest]}}
run: {{stages: [calibrate]}}
"""


def wsl(path):
    p = str(Path(path).resolve()).replace("\\", "/")
    return "/mnt/" + p[0].lower() + p[2:]


def log(run, text):
    with open(Path(run) / "luno.log", "a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {text}\n")


def docker(run, image, mounts, script, label):
    vols = []
    for host, inside, mode in mounts:
        vols += ["-v", f"{wsl(host)}:{inside}:{mode}"]
    inner = " ".join(
        ["docker", "run", "--rm", "--network", "none", "--user", "$(id -u):$(id -g)",
         "--tmpfs", "/tmp", "-e", "HOME=/tmp", "-e", "OMP_NUM_THREADS=8",
         *[f"'{v}'" for v in vols], "-w", "/tmp", image, "sh", "-c", f"'{script}'"]
    )  # fmt: skip
    log(run, f"START {label}: {inner}")
    t0 = time.perf_counter()
    with open(Path(run) / f"{label}.out", "w", encoding="utf-8") as fh:
        rc = subprocess.run(["wsl", "-e", "bash", "-lc", inner], stdout=fh,
                            stderr=subprocess.STDOUT, check=False).returncode  # fmt: skip
    log(run, f"END {label} rc={rc} {time.perf_counter() - t0:.1f}s")
    return rc


def ms_paths(run):
    run = Path(run)
    return run / "luno" / "luno-dev.ms", run / "casa" / "luno-dev.ms"


def build(run):
    ms, _ = ms_paths(run)
    ms.parent.mkdir(parents=True, exist_ok=True)
    py = str(C.PY)
    for mode, extra in (
        ("build", []),
        ("verify", ["--json", str(ms.parent / "verify.json")]),
    ):
        t0 = time.perf_counter()
        dry = os.environ.get(
            "E2AVG_DRY", ""
        ).split()  # development: --rows N --chan A:B
        rc = subprocess.run([py, str(CONVERT), mode, str(ms), *GROUPS, *dry, *extra],
                            check=False).returncode  # fmt: skip
        log(run, f"{mode} rc={rc} {time.perf_counter() - t0:.1f}s")
        if rc:
            raise SystemExit(f"{mode} exit {rc}")


READABLE = r"""
import json, sys, os
import numpy as np, numcodecs
from casacore.tables import table
ms = "/ms/luno-dev.ms"
out = {"tables": {}}
t = table(ms, ack=False)
out["tables"]["MAIN"] = t.nrows()
for k in t.getkeywords():
    v = t.getkeyword(k)
    if isinstance(v, str) and v.startswith("Table: "):
        s = table(v[7:], ack=False)
        out["tables"][k] = s.nrows()
        for c in s.colnames():
            if s.nrows() and s.iscelldefined(c, 0):
                s.getcell(c, 0)
        s.close()
for c in t.colnames():
    if t.iscelldefined(c, 0):
        t.getcell(c, 0)
# Two DATA chunks of the zarr decoded with numcodecs (blosc), against the MS.
checks = []
row0 = {"MAIN_0": 0, "MAIN_1": int(json.load(open("/out/n0.json"))["n0"])}
for group, (ri, ci) in (("MAIN_0", (0, 0)), ("MAIN_1", (1, 17))):
    meta = json.load(open(f"/zarr/MAIN/{group}/DATA/.zarray"))
    codec = numcodecs.get_codec(meta["compressor"])
    raw = codec.decode(open(f"/zarr/MAIN/{group}/DATA/{ri}.{ci}.0", "rb").read())
    rch, cch, _ = meta["chunks"]
    nrow = min(rch, meta["shape"][0] - ri * rch)
    z = np.frombuffer(raw, "<c8").reshape(rch, cch, 4)[:nrow]
    r = row0[group] + ri * rch
    m = t.getcolslice("DATA", [ci * cch, 0], [ci * cch + cch - 1, 3], startrow=r, nrow=nrow)
    checks.append({"group": group, "chunk": f"{ri}.{ci}.0", "rows": nrow,
                   "equal_bytes": bool(z.tobytes() == np.ascontiguousarray(m, "<c8").tobytes())})
out["chunks"] = checks
out["casacore_ok"] = True
json.dump(out, open("/out/readable.json", "w"), indent=1)
print(json.dumps(out))
"""
LISTOBS_PY = """\
import casatasks
casatasks.listobs(vis="/ms/luno-dev.ms", listfile="/out/listobs.txt", overwrite=True)
"""
LISTOBS = "/opt/casa/bin/python /out/listobs.py"


def readable(run):
    run = Path(run)
    ms, _ = ms_paths(run)
    out = run / "readable"
    out.mkdir(exist_ok=True)
    with core_ms.open_table(ms) as t:
        fid = t.getcol("FIELD_ID")
        scan = t.getcol("SCAN_NUMBER")
    n0 = int((scan == scan[0]).sum())
    C.write(
        out / "n0.json",
        {"n0": n0, "first_scan": int(scan[0]), "fields": np.unique(fid).tolist()},
    )
    (out / "readable.py").write_text(READABLE, encoding="utf-8")
    (out / "listobs.py").write_text(LISTOBS_PY, encoding="utf-8")
    rc1 = docker(run, "rang-o-casa:6.7.6.14", [(ms.parent, "/ms", "rw"), (out, "/out", "rw")],
                 LISTOBS, "listobs")  # fmt: skip
    rc2 = docker(run, "rang-tricolour:0.2.1-e1",
                 [(ms.parent, "/ms", "rw"), (out, "/out", "rw"), (STORE, "/zarr", "ro")],
                 "python3 /out/readable.py", "readable")  # fmt: skip
    rec = json.loads((out / "readable.json").read_text()) if rc2 == 0 else {}
    rec["listobs_exit"] = rc1
    rec["casacore_exit"] = rc2
    C.write(out / "result.json", rec)
    print(json.dumps(rec, indent=1))
    ok = (
        rc1 == 0 and rc2 == 0 and all(c["equal_bytes"] for c in rec.get("chunks", [{}]))
    )
    return 0 if ok else 3


def rang(run):
    run = Path(run)
    ms, casa_ms = ms_paths(run)
    if not casa_ms.exists():  # the CASA copy is taken before rang writes anything
        t0 = time.perf_counter()
        shutil.copytree(ms, casa_ms)
        log(run, f"copied for CASA {time.perf_counter() - t0:.1f}s")
    d = ms.parent
    shutil.copy(run / STRATEGY, d / STRATEGY)
    (d / "config.yaml").write_text(CONFIG, encoding="utf-8")
    rc, wall = C.rang_core("run", d / "config.yaml", ms, log=d / "rang-core.log")
    log(run, f"rang-core run rc={rc} {wall:.1f}s")
    receipts = sorted(Path(str(ms) + ".rang-run").rglob("*receipt*.json"))
    rec = {"exit": rc, "wall_s": wall, "receipts": [str(p) for p in receipts]}
    for p in receipts:
        r = json.loads(p.read_text(encoding="utf-8"))
        rec.setdefault("timings", []).append(
            {"stage": r.get("stage"), **r.get("timings", {})}
        )
    C.write(d / "rang-run.json", rec)
    return rc


def casa_calls(ms, refant):
    """CARACal's calls as rang runs them (core_pipeline.chain_terms,
    polcal_terms; e1b_casa.py casa_calls without the secondary and extend):
    K without uvrange, uvrange on the other solves, minsnr 3, minblperant
    4, flex."""
    t = "/run/casa"
    common = {"vis": ms, "refant": refant, "minsnr": 3.0, "minblperant": 4}
    mode = {"refantmode": "flex"}
    cc = [f"{t}/K", f"{t}/G", f"{t}/B"]
    return [
        {"task": "setjy", "args": {"vis": ms, "field": FCAL, "standard": "Stevens-Reynolds 2016",
         "scalebychan": True, "usescratch": True}},
        {"task": "setjy", "args": {"vis": ms, "field": XCAL, "standard": "manual", **X286,
         "scalebychan": True, "usescratch": True}},
        {"task": "gaincal", "args": {**common, **mode, "caltable": f"{t}/K", "field": FCAL,
         "gaintype": "K", "solint": "inf", "combine": "", "parang": False}},
        {"task": "gaincal", "args": {**common, **mode, "caltable": f"{t}/G", "field": FCAL,
         "gaintype": "G", "calmode": "ap", "solint": "inf", "combine": "", "parang": False,
         "uvrange": UVRANGE, "gaintable": [f"{t}/K"], "interp": [LIN]}},
        {"task": "bandpass", "args": {**common, "caltable": f"{t}/B", "field": FCAL,
         "bandtype": "B", "solint": "inf", "combine": "scan", "solnorm": False,
         "fillgaps": 0, "parang": False, "uvrange": UVRANGE,
         "gaintable": [f"{t}/K", f"{t}/G"], "interp": [LIN, LIN]}},
        {"task": "gaincal", "args": {**common, **mode, "caltable": f"{t}/Gpol", "field": XCAL,
         "gaintype": "G", "calmode": "p", "solint": "60s", "combine": "", "parang": True,
         "uvrange": UVRANGE, "gaintable": cc, "interp": [LIN] * 3}},
        {"task": "gaincal", "args": {**common, **mode, "caltable": f"{t}/Kcross", "field": XCAL,
         "gaintype": "KCROSS", "solint": "inf", "combine": "", "parang": True,
         "uvrange": UVRANGE, "gaintable": cc + [f"{t}/Gpol"], "interp": [LIN] * 4}},
        {"task": "polcal", "args": {**common, "caltable": f"{t}/Xf", "field": XCAL,
         "poltype": "Xf", "solint": "inf", "combine": "scan", "uvrange": UVRANGE,
         "gaintable": cc + [f"{t}/Gpol", f"{t}/Kcross"], "interp": [LIN] * 4 + [NEAR]}},
        {"task": "polcal", "args": {**common, "caltable": f"{t}/Df.raw", "field": FCAL,
         "poltype": "Df", "solint": "inf", "combine": "scan", "uvrange": UVRANGE,
         "gaintable": cc + [f"{t}/Kcross", f"{t}/Xf"], "interp": [LIN] * 3 + [NEAR] * 2}},
        {"task": "copytree", "args": {"src": f"{t}/Df.raw", "dst": f"{t}/Df"}},
        {"task": "flagdata", "args": {"vis": f"{t}/Df", "mode": "clip",
         "clipminmax": [-0.6, 0.6], "datacolumn": "CPARAM", "flagbackup": False}},
    ]  # fmt: skip


RECEPTOR = r"""
import numpy as np
from casatools import table
tb = table()
tb.open("/run/casa/luno-dev.ms/FEED", nomodify=False)
a = tb.getcol("RECEPTOR_ANGLE")
before = a.copy()
a[:] = np.deg2rad(-90.0)
tb.putcol("RECEPTOR_ANGLE", a)
tb.close()
print("RECEPTOR_ANGLE", before[:, :2].tolist(), "->", a[:, :2].tolist())
"""


def refant_of(run):
    ms, _ = ms_paths(run)
    s = json.loads(
        (Path(str(ms) + ".rang-run") / "calibrate" / "summary.json").read_text()
    )
    auto = s.get("refant_auto") or {}
    names = auto.get("names") or auto.get("refant") or auto.get("chosen")
    return names, auto


def casa(run):
    run = Path(run)
    _, casa_ms = ms_paths(run)
    names, auto = refant_of(run)
    refant = ",".join(names) if isinstance(names, list) else str(names)
    d = casa_ms.parent
    # E2AVG_CASA_FROM=N resumes at call N (the receptor step is idempotent).
    start = int(os.environ.get("E2AVG_CASA_FROM", "0"))
    tag = "" if start == 0 else f"-from-{start}"
    (d / "receptor.py").write_text(RECEPTOR, encoding="utf-8")
    calls = casa_calls("/run/casa/luno-dev.ms", refant)[start:]
    C.write(d / f"casa-spec{tag}.json", calls)
    C.write(d / "refant.json", {"refant": refant, "rang_auto": auto})
    script = ("/opt/casa/bin/python /run/casa/receptor.py && /opt/casa/bin/python -I "
              f"/ex/oracle_pol.py tasks /run/casa/casa-spec{tag}.json "
              f"/run/casa/casa-tasks{tag}.json")  # fmt: skip
    rc = docker(run, "rang-o-casa:6.7.6.14",
                [(run, "/run", "rw"), (ROOT / "examples", "/ex", "ro")], script,
                f"casa{tag}")  # fmt: skip
    tasks = json.loads((d / f"casa-tasks{tag}.json").read_text())
    errors = [(r["task"], r["error"]) for r in tasks if r["error"]]
    log(run, f"casa tasks {len(tasks)} errors {errors}")
    return rc or (3 if errors else 0)


def _first_unflagged(t):
    v, f = t.params[:, :, 0].astype(complex), t.flags[:, :, 0]
    return np.array([v[~f[:, j], j][0] if (~f[:, j]).any() else np.nan
                     for j in range(v.shape[1])])  # fmt: skip


def score(run, ms=None, cdir=None, name="luno-score.json"):
    """Class B scores of rang's tables (of `ms`, default the run's) against
    CASA's (`cdir`, default the run's), into `run/name`."""
    run = Path(run)
    own, casa_ms = ms_paths(run)
    ms = Path(ms or own)
    rdir = Path(str(ms) + ".rang-run") / "calibrate"
    cdir = Path(cdir or casa_ms.parent)
    names = ("K", "G", "B", "Gpol", "Kcross", "Xf", "Df")
    r = {n: C.table(rdir / n) for n in names}
    c = {n: C.table(cdir / n) for n in names}
    out = {"terms": {}}
    out["terms"]["K"] = k = C.term_diff(r["K"], c["K"], "delay")
    k["class_b"] = bool(k["abs_ns"]["median"] <= 0.01 and k["abs_ns"]["p95"] <= 0.03)
    for n in ("G", "B"):
        out["terms"][n] = C.term_diff(r[n], c[n], "complex")
    g = out["terms"]["Gpol"] = C.term_diff(r["Gpol"], c["Gpol"], "phase")
    g["class_b"] = bool(g["abs_deg"]["median"] <= 0.1)
    kr = r["Kcross"].params[:, 0, 0].real
    kc = c["Kcross"].params[:, 0, 0].real
    kx = {
        "rang_ns": np.unique(np.round(kr, 6)).tolist(),
        "casa_ns": np.unique(np.round(kc, 6)).tolist(),
    }
    pa, fa, pb, fb, _, _ = C.matched(r["Kcross"], c["Kcross"])
    ok = ~fa[:, 0, 0] & ~fb[:, 0, 0]
    kx["abs_ns"] = C.stats(np.abs(pa[ok, 0, 0].real - pb[ok, 0, 0].real))
    kx["class_b"] = bool(kx["abs_ns"].get("max", 1.0) <= 0.02)
    out["terms"]["Kcross"] = kx
    xr, xc = _first_unflagged(r["Xf"]), _first_unflagged(c["Xf"])
    xd = np.degrees(np.abs(np.angle(xr / xc)))
    xf = {"abs_deg": C.stats(xd), "channels_flagged": [int(np.isnan(xr).sum()),
          int(np.isnan(xc).sum())]}  # fmt: skip
    xf["class_b"] = bool(xf["abs_deg"]["median"] <= 0.5 and xf["abs_deg"]["p95"] <= 2.0)
    out["terms"]["Xf"] = xf
    # Df gauge-free: d_x,p + conj(d_y,q) and d_y,p + conj(d_x,q), p != q.
    pa, fa, pb, fb, _, _ = C.matched(r["Df"], c["Df"])
    nant = pa.shape[0]
    diffs = []
    for p in range(nant):
        for q in range(nant):
            if p == q:
                continue
            for i, j in ((0, 1), (1, 0)):
                ok = ~fa[p, :, i] & ~fa[q, :, j] & ~fb[p, :, i] & ~fb[q, :, j]
                ga = pa[p, :, i] + np.conj(pa[q, :, j])
                gb = pb[p, :, i] + np.conj(pb[q, :, j])
                diffs.append(np.abs(ga - gb)[ok])
    df = {"abs": C.stats(np.concatenate(diffs)), "flags": [int(fa.sum()), int(fb.sum())],
          "flags_differ": int((fa != fb).sum())}  # fmt: skip
    df["class_b"] = bool(df["abs"]["median"] <= 1e-3 and df["abs"]["p95"] <= 5e-3)
    out["terms"]["Df"] = df
    fcal = C.field_id(ms, FCAL)
    pooled = [cal_apply.POOLED] * 3
    a, fa = C.composite(ms, fcal, [r[n] for n in ("K", "G", "B")], pooled, step=8)
    b, fb = C.composite(ms, fcal, [c[n] for n in ("K", "G", "B")], pooled, step=8)
    out["composite_fcal_KGB"] = C.rel_stats(a, fa, b, fb)
    del a, b, fa, fb
    out["class_b_all"] = bool(
        out["composite_fcal_KGB"]["class_b"]
        and all(v.get("class_b", True) for v in out["terms"].values())
    )
    C.write(run / name, out)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    cmd, run = sys.argv[1:3]
    sys.exit({"build": build, "readable": readable, "rang": rang, "casa": casa,
              "score": score}[cmd](run) or 0)  # fmt: skip
