"""E2's post-run steps on a leg's MS (research/e2-acceptance.md 6.5): gates 1,
2a, 2b, 2c and 3a, and the CASA copy that keeps rang's columns for the sealed
scores (6.7). The order is fixed (`ORDER`): every step that needs rang's
columns or post-stage flags runs before `restore`, which writes FLAG back from
`rang_original` and drops rang's columns.

    python e2_post.py STEP MS R [ARGS]     (Windows venv; containers via `wsl docker`)

R is the leg's result directory (D:\\...). Steps, in order:

    gate1     receipt: exit, every stage of run.stages done          -> R/gate1.json
    archive   copy MS.rang-run (tables, images, receipts) to R/rang-run
    wcs       astropy WCS of every FITS rang wrote (gate 2c)          -> R/g2c.json
    casacore  python-casacore opens every table and column (2b)       -> R/g2b-casacore.json
    casa-ro   CASA listobs and flagmanager(mode='list') (2b)          -> R/g2b-casa-ro.json
    wsclean0  WSClean -niter 0 on CORRECTED_DATA and MODEL_DATA (2b)  -> R/g2b-wsclean.json
    daskms    QuartiCal's dask-ms reads every main column (2b)        -> R/g2b-daskms.json
    wsclean3c E2-B 3c's oracle images of rang's CORRECTED_DATA (sealed: run, not read)
    copy      MS and its flag versions to R/casa/ (the one copy)
    prep      on the copy: rang's CORRECTED_DATA, MODEL_DATA, FLAG kept as RANG_*;
              FLAG from rang's `rang_apply_*` (after calibrate); RECEPTOR_ANGLE -90
    applycal  CASA applycal with rang's tables, from rang's apply summary (2b)
    compare   CASA's CORRECTED_DATA and FLAG against rang's, class C  -> R/g2b-applycal.json
    restore   FLAG from rang_original, hashes against INPUT.json (2a) -> R/g2a.json;
              rang's columns dropped; MS.rang-run moved to R/rang-run-moved
    tricolour Tricolour 0.2.1 on the restored MS (3a), then the cell comparison
              with rang's flag stage, then `restore` again              -> R/g3a.json

`restore` takes INPUT.json (e2_flaghash.py of the MS as converted);
`tricolour` takes INPUT.json and the strategy file. Every step runs under
the main checkout's tools/heavy_lock.py (the caller wraps it).
"""

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ORDER = ["gate1", "archive", "wcs", "casacore", "casa-ro", "wsclean0", "daskms",
         "wsclean3c", "copy", "prep", "applycal", "compare", "snapshot", "restore", "tricolour"]  # fmt: skip
CASA_IMAGE = "rang-o-casa:6.7.6.14"
FORMATS_IMAGE = "rang-formats-oracle:20261030"
QC_PY = "/opt/qc/bin/python"
WSCLEAN_IMAGE = "rang-wsclean-native:3.7"
TRICOLOUR_IMAGE = "rang-tricolour:0.2.1-e1"
BLOCK = 4000
EPS32 = float(np.finfo(np.float32).eps)


def wsl(path):
    p = str(Path(path).resolve()).replace("\\", "/")
    return "/mnt/" + p[0].lower() + p[2:]


def log(r, text):
    Path(r).mkdir(parents=True, exist_ok=True)
    with open(Path(r) / "post.log", "a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {text}\n")


def write(path, payload):
    Path(path).write_text(
        json.dumps(payload, indent=1, default=str) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=1, default=str)[:4000])


def docker(r, image, mounts, script, label, threads=8):
    """One network-less container; `script` is a file path inside it or a
    shell command. Output to R/<label>.out."""
    vols = []
    for host, inside in mounts:
        vols += ["-v", f"'{wsl(host)}:{inside}:rw'"]
    inner = " ".join(
        ["docker", "run", "--rm", "--network", "none", "--user", "$(id -u):$(id -g)",
         "--tmpfs", "/tmp", "-e", "HOME=/tmp", "-e", f"OMP_NUM_THREADS={threads}",
         *vols, "-w", "/tmp", image, "sh", "-c", f"'{script}'"]
    )  # fmt: skip
    log(r, f"START {label}: {inner}")
    t0 = time.perf_counter()
    with open(Path(r) / f"{label}.out", "w", encoding="utf-8") as fh:
        rc = subprocess.run(["wsl", "-e", "bash", "-lc", inner], stdout=fh,
                            stderr=subprocess.STDOUT, check=False).returncode  # fmt: skip
    log(r, f"END {label} rc={rc} {time.perf_counter() - t0:.1f}s")
    return rc


def run_dir(ms):
    return Path(str(ms) + ".rang-run")


def state(ms):
    return json.loads((run_dir(ms) / "state.json").read_text(encoding="utf-8"))


# --- gate 1 and the archive ---------------------------------------------------


def gate1(ms, r):
    st = state(ms)
    cfg = json.loads((run_dir(ms) / "config.resolved.json").read_text(encoding="utf-8"))
    wanted = cfg["run"]["stages"]
    stages = {k: v.get("status") for k, v in st["stages"].items()}
    receipts = sorted((run_dir(ms) / "receipts").glob("*.json"))
    seconds = {k: v.get("seconds") for k, v in st["stages"].items()}
    ok = all(stages.get(s) == "done" for s in wanted) and len(receipts) == 1
    write(Path(r) / "gate1.json", {"stages_wanted": wanted, "stages": stages,
          "seconds": seconds, "attempts": {k: v.get("attempts") for k, v in st["stages"].items()},
          "receipts": [p.name for p in receipts], "met": ok})  # fmt: skip
    return 0


def archive(ms, r):
    dst = Path(r) / "rang-run"
    if not dst.exists():
        shutil.copytree(
            run_dir(ms), dst, ignore=shutil.ignore_patterns("lock", "table.lock")
        )
    fv = Path(str(ms) + ".flagversions")
    shutil.copy(fv / "FLAG_VERSION_LIST", dst / "FLAG_VERSION_LIST")
    if (fv / "rang-writeback.json").exists():
        shutil.copy(fv / "rang-writeback.json", dst / "rang-writeback.json")
    log(r, f"archived {run_dir(ms)} to {dst}")
    return 0


# --- gate 2c --------------------------------------------------------------------


def wcs(ms, r):
    import warnings

    from astropy.io import fits
    from astropy.wcs import WCS

    files = sorted((Path(r) / "rang-run").rglob("*.fits"))
    bad = []
    for p in files:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error")  # a WCS warning counts as a failure
                with fits.open(p) as h:
                    w = WCS(h[0].header)
                    if not w.has_celestial:
                        raise ValueError("no celestial axes")
        except Exception as exc:  # noqa: BLE001 - every failure is reported
            bad.append({"file": str(p.relative_to(r)), "error": repr(exc)})
    write(Path(r) / "g2c.json", {"files": len(files), "failed": bad,
                                 "met": bool(files) and not bad})  # fmt: skip
    return 0


# --- gate 2b: readers -----------------------------------------------------------

CASACORE_PY = r"""
import json, os, sys
from casacore.tables import table
ms = sys.argv[1]
out = {"tables": {}, "errors": []}
def touch(t, label):
    cols = t.colnames()
    n = t.nrows()
    rec = {"rows": n, "columns": {}}
    for c in cols:
        try:
            cells = [r for r in (0, n - 1) if n and t.iscelldefined(c, r)]
            for r in cells:
                t.getcell(c, r)
            rec["columns"][c] = len(cells)
        except Exception as exc:
            out["errors"].append(f"{label}:{c}: {exc!r}")
    out["tables"][label] = rec
t = table(ms, ack=False)
touch(t, "MAIN")
for k in t.getkeywords():
    v = t.getkeyword(k)
    if isinstance(v, str) and v.startswith("Table: "):
        s = table(v[7:], ack=False)
        touch(s, k)
        s.close()
t.close()
fv = ms + ".flagversions"
for name in sorted(os.listdir(fv)):
    if name.startswith("flags."):
        s = table(os.path.join(fv, name), ack=False)
        touch(s, name)
        s.close()
for name in sorted(os.listdir(sys.argv[2])):
    if not os.path.isfile(os.path.join(sys.argv[2], name, "table.dat")):
        continue  # summary.json and other non-tables
    s = table(os.path.join(sys.argv[2], name), ack=False)
    touch(s, "caltable:" + name)
    s.close()
json.dump(out, open(sys.argv[3], "w"), indent=1)
print(len(out["tables"]), "tables", len(out["errors"]), "errors")
"""


def casacore(ms, r):
    ms, r = Path(ms), Path(r)
    (r / "e2p_casacore.py").write_text(CASACORE_PY, encoding="utf-8")
    rc = docker(r, FORMATS_IMAGE, [(ms.parent, "/ms"), (r, "/r")],
                f"{QC_PY} -I /r/e2p_casacore.py /ms/{ms.name} /r/rang-run/calibrate /r/casacore-raw.json",
                "casacore")  # fmt: skip
    raw = json.loads((r / "casacore-raw.json").read_text()) if rc == 0 else {}
    write(r / "g2b-casacore.json", {"exit": rc, "tables": len(raw.get("tables", {})),
          "errors": raw.get("errors"), "met": rc == 0 and not raw.get("errors")})  # fmt: skip
    return 0


CASA_RO_PY = """\
import json, sys
import casatasks
ms = sys.argv[1]
out = {}
for name, call in (
    ("listobs", lambda: casatasks.listobs(vis=ms, listfile=sys.argv[2] + "/listobs.txt",
                                          overwrite=True)),
    ("flagmanager", lambda: casatasks.flagmanager(vis=ms, mode="list")),
):
    try:
        res = call()
        out[name] = {"error": None, "result": res if name == "flagmanager" else bool(res)}
    except Exception as exc:
        out[name] = {"error": repr(exc)}
json.dump(out, open(sys.argv[2] + "/casa-ro.json", "w"), indent=1, default=str)
"""


def casa_ro(ms, r):
    ms, r = Path(ms), Path(r)
    (r / "e2p_casa_ro.py").write_text(CASA_RO_PY, encoding="utf-8")
    rc = docker(r, CASA_IMAGE, [(ms.parent, "/ms"), (r, "/r")],
                f"/opt/casa/bin/python -I /r/e2p_casa_ro.py /ms/{ms.name} /r", "casa-ro")  # fmt: skip
    raw = json.loads((r / "casa-ro.json").read_text()) if rc == 0 else {}
    versions = (raw.get("flagmanager") or {}).get("result")
    ok = rc == 0 and all(v.get("error") is None for v in raw.values()) and len(raw) == 2
    write(r / "g2b-casa-ro.json", {"exit": rc, "calls": {k: v.get("error") for k, v in raw.items()},
          "flag_versions_listed": versions, "met": ok})  # fmt: skip
    return 0


def wsclean0(ms, r, field="0"):
    ms, r = Path(ms), Path(r)
    d = r / "wsclean0"
    (d / "tmp").mkdir(parents=True, exist_ok=True)
    rcs = {}
    for col in ("CORRECTED_DATA", "MODEL_DATA"):
        cmd = (f"wsclean -name /r/wsclean0/{col} -size 1024 1024 -scale 2asec -niter 0 "
               f"-data-column {col} -field {field} -no-update-model-required -j 8 "
               f"-temp-dir /r/wsclean0/tmp /ms/{ms.name}")  # fmt: skip
        rcs[col] = docker(r, WSCLEAN_IMAGE, [(ms.parent, "/ms"), (r, "/r")], cmd,
                          f"wsclean0-{col}")  # fmt: skip
    fits_out = sorted(p.name for p in d.glob("*.fits"))
    shutil.rmtree(d / "tmp", ignore_errors=True)
    write(r / "g2b-wsclean.json", {"field": field, "exit": rcs, "fits": fits_out,
          "met": all(v == 0 for v in rcs.values()) and len(fits_out) >= 2})  # fmt: skip
    return 0


def wsclean3c(ms, r):
    """Gate 3c's oracle images (E2-B, 6.5): WSClean 3.7 dirty and cleaned
    images of rang's CORRECTED_DATA with rang's FLAG after apply, at the
    image stage's settings (from the resolved configuration), per imaged
    field. Run here, before `restore`; read only after the 6.7 amendment."""
    from rang import core_ms

    ms, r = Path(ms), Path(r)
    cfg = json.loads((run_dir(ms) / "config.resolved.json").read_text())
    im = cfg["image"]
    fields = list(
        dict.fromkeys(n for role in im["fields"] for n in cfg["fields"][role])
    )
    with core_ms.open_table(ms / "FIELD") as t:
        names = [str(n) for n in t.getcol("NAME")]
    d = r / "wsclean3c"
    (d / "tmp").mkdir(parents=True, exist_ok=True)
    size = " ".join(str(x) for x in im["size"])
    common = (f"-size {size} -scale {im['scale']} -weight briggs {im['robust']} "
              f"-channels-out {im['channels_out']} -join-channels -pol {im['pol']} "
              "-join-polarizations -data-column CORRECTED_DATA -no-update-model-required "
              "-j 8 -temp-dir /r/wsclean3c/tmp")  # fmt: skip
    rcs = {}
    for f in fields:
        fid = names.index(f)
        tag = f.replace("+", "p").replace("-", "m")
        for kind, extra in (("dirty", "-niter 0"),
                            ("clean", (f"-niter {int(im['niter'])} -mgain {im['mgain']} "
                                      f"-auto-threshold {im['auto_threshold']}"))):  # fmt: skip
            cmd = (f"wsclean -name /r/wsclean3c/{tag}-{kind} {common} {extra} -field {fid} "
                   f"/ms/{ms.name}")  # fmt: skip
            rcs[f"{f}:{kind}"] = docker(r, WSCLEAN_IMAGE, [(ms.parent, "/ms"), (r, "/r")], cmd,
                                        f"wsclean3c-{tag}-{kind}", 16)  # fmt: skip
    shutil.rmtree(d / "tmp", ignore_errors=True)
    write(r / "wsclean3c-run.json", {"exit": rcs, "settings": common})  # names only
    return 0


UNIT_PY = r"""
import json, sys
import numpy as np
from casacore.tables import table, makecoldesc
ms, mode, out = sys.argv[1:4]
t = table(ms, readonly=False, ack=False)
cols = t.colnames()
rec = {"mode": mode}
if mode == "on":
    assert "RANG_FLAG" in cols and "E2_CASA_FLAG" not in cols
    n = t.nrows()
    rows_extra = 0
    for r0 in range(0, n, 4000):
        k = min(4000, n - r0)
        fr = t.getcol("FLAG_ROW", r0, k)
        rf = t.getcol("RANG_FLAG", r0, k)
        rows_extra += int((fr & ~rf.all(axis=(1, 2))).sum())
    rec["flag_row_not_all_rang_flag"] = rows_extra
    t.renamecol("FLAG", "E2_CASA_FLAG")
    t.renamecol("RANG_FLAG", "FLAG")
    t.renamecol("WEIGHT_SPECTRUM", "E2_WEIGHT_SPECTRUM")
    t.renamecol("WEIGHT", "E2_WEIGHT")
    desc = t.getcoldesc("E2_WEIGHT")
    # its own storage manager, so removecols drops it whole: rang's reader
    # rejects a StandardStMan that casacore added a column to and removed
    t.addcols(makecoldesc("WEIGHT", desc),
              {"TYPE": "StandardStMan", "NAME": "E2UnitWeight", "SPEC": {}})
    w = np.ones((n, t.getcell("E2_WEIGHT", 0).shape[0]), np.float32)
    t.putcol("WEIGHT", w)
else:
    assert "E2_CASA_FLAG" in cols
    t.removecols(["WEIGHT"])
    t.renamecol("E2_WEIGHT", "WEIGHT")
    t.renamecol("E2_WEIGHT_SPECTRUM", "WEIGHT_SPECTRUM")
    t.renamecol("FLAG", "RANG_FLAG")
    t.renamecol("E2_CASA_FLAG", "FLAG")
rec["columns"] = t.colnames()
t.close()
json.dump(rec, open(out, "w"), indent=1)
print(json.dumps(rec))
"""


def wsclean3c_unit(ms, r):
    """Gate 3c's matched oracle (added 2026-11-12, research/e2-acceptance.md
    results): `wsclean3c` as committed images with the MS's WEIGHT_SPECTRUM,
    where rang's image stage passes `-unit-weights` (data.weights: uniform);
    the gridder matches (WSClean 3.7's default wgridder at 1e-4, rang's
    image.wgridder_accuracy 1e-4). Run on the CASA copy R/casa/<ms> as the
    last step that reads it: by column renames only (undone after), FLAG is
    rang's FLAG after apply (RANG_FLAG), WEIGHT_SPECTRUM is absent and WEIGHT
    is 1, so WSClean falls back to WEIGHT (W6), and WSClean images
    RANG_CORRECTED_DATA at wsclean3c's settings -> R/wsclean3c-unit/."""
    from rang import core_ms

    ms, r = Path(ms), Path(r)
    cms = r / "casa" / ms.name
    cfg = json.loads((r / "rang-run-moved" / "config.resolved.json").read_text())
    im = cfg["image"]
    fields = list(
        dict.fromkeys(n for role in im["fields"] for n in cfg["fields"][role])
    )
    with core_ms.open_table(cms / "FIELD") as t:
        names = [str(n) for n in t.getcol("NAME")]
    (r / "e2p_unit.py").write_text(UNIT_PY, encoding="utf-8")
    mounts = prep_mounts(r)
    rc = docker(r, FORMATS_IMAGE, mounts,
                f"{QC_PY} -I /p/e2p_unit.py /c/{cms.name} on /p/unit-on.json", "unit-on")  # fmt: skip
    if rc != 0:
        return rc
    d = r / "wsclean3c-unit"
    (d / "tmp").mkdir(parents=True, exist_ok=True)
    size = " ".join(str(x) for x in im["size"])
    common = (f"-size {size} -scale {im['scale']} -weight briggs {im['robust']} "
              f"-channels-out {im['channels_out']} -join-channels -pol {im['pol']} "
              "-join-polarizations -data-column RANG_CORRECTED_DATA "
              f"-gridder wgridder -wgridder-accuracy {float(im['wgridder_accuracy'])!r} "
              "-no-update-model-required -j 8 -temp-dir /p/wsclean3c-unit/tmp")  # fmt: skip
    rcs = {}
    for f in fields:
        fid = names.index(f)
        tag = f.replace("+", "p").replace("-", "m")
        for kind, extra in (("dirty", "-niter 0"),
                            ("clean", (f"-niter {int(im['niter'])} -mgain {im['mgain']} "
                                      f"-auto-threshold {im['auto_threshold']}"))):  # fmt: skip
            cmd = (f"wsclean -name /p/wsclean3c-unit/{tag}-{kind} {common} {extra} "
                   f"-field {fid} /c/{cms.name}")  # fmt: skip
            rcs[f"{f}:{kind}"] = docker(r, WSCLEAN_IMAGE, mounts, cmd,
                                        f"wsclean3c-unit-{tag}-{kind}", 16)  # fmt: skip
    shutil.rmtree(d / "tmp", ignore_errors=True)
    off = docker(r, FORMATS_IMAGE, mounts,
                 f"{QC_PY} -I /p/e2p_unit.py /c/{cms.name} off /p/unit-off.json", "unit-off")  # fmt: skip
    write(
        r / "wsclean3c-unit-run.json",
        {"exit": rcs, "unit_off_exit": off, "settings": common},
    )
    return off or max(rcs.values(), default=0)


DASKMS_PY = r"""
import json, sys
import numpy as np
import dask
import daskms
ms = sys.argv[1]
cols = ["DATA", "CORRECTED_DATA", "MODEL_DATA", "FLAG", "FLAG_ROW", "WEIGHT_SPECTRUM",
        "WEIGHT", "UVW", "TIME", "ANTENNA1", "ANTENNA2"]
# QuartiCal's grouping (quartical.data_handling.ms_handler).
xds = daskms.xds_from_ms(ms, columns=cols, group_cols=["FIELD_ID", "DATA_DESC_ID", "SCAN_NUMBER"],
                         chunks={"row": 20000})
out = {"datasets": len(xds), "rows": 0, "finite": {}, "flagged": 0}
for ds in xds:
    out["rows"] += ds.sizes["row"]
    sums = {}
    for c in ("DATA", "CORRECTED_DATA", "MODEL_DATA", "WEIGHT_SPECTRUM"):
        sums[c] = np.isfinite(ds[c].data).sum()
    sums["FLAG"] = ds["FLAG"].data.sum()
    got = dask.compute(sums, scheduler="threads", num_workers=8)[0]
    for c in ("DATA", "CORRECTED_DATA", "MODEL_DATA", "WEIGHT_SPECTRUM"):
        out["finite"][c] = out["finite"].get(c, 0) + int(got[c])
    out["flagged"] += int(got["FLAG"])
json.dump(out, open(sys.argv[2], "w"), indent=1)
print(json.dumps(out))
"""


def daskms(ms, r):
    ms, r = Path(ms), Path(r)
    (r / "e2p_daskms.py").write_text(DASKMS_PY, encoding="utf-8")
    rc = docker(r, FORMATS_IMAGE, [(ms.parent, "/ms"), (r, "/r")],
                f"{QC_PY} -I /r/e2p_daskms.py /ms/{ms.name} /r/daskms-raw.json", "daskms")  # fmt: skip
    raw = json.loads((r / "daskms-raw.json").read_text()) if rc == 0 else {}
    write(
        r / "g2b-daskms.json",
        {"exit": rc, **raw, "met": rc == 0 and raw.get("rows", 0) > 0},
    )
    return 0


# --- gate 2b: CASA applycal with rang's tables, on the copy -------------------


def copy(ms, r):
    ms, d = Path(ms), Path(r) / "casa"
    d.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    for src in (ms, Path(str(ms) + ".flagversions")):
        dst = d / src.name
        if not dst.exists():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("table.lock"))
    log(r, f"copied {ms} to {d} {time.perf_counter() - t0:.1f}s")
    return 0


PREP_PY = r"""
import json, sys
import numpy as np
from casacore.tables import table, makecoldesc
ms, version, out = sys.argv[1:4]
B = 4000
t = table(ms, readonly=False, ack=False)
done = {}
for c in ("CORRECTED_DATA", "MODEL_DATA"):
    if c in t.colnames() and "RANG_" + c not in t.colnames():
        t.renamecol(c, "RANG_" + c)
        done[c] = "RANG_" + c
n = t.nrows()
if "RANG_FLAG" not in t.colnames():
    dm = t.getdminfo("FLAG")
    dm["NAME"] = "RangFlagTSM"
    if "SPEC" in dm and "HYPERCUBES" in dm["SPEC"]:
        dm["SPEC"].pop("HYPERCUBES", None)
    t.addcols(makecoldesc("RANG_FLAG", t.getcoldesc("FLAG")), dm)
    for r0 in range(0, n, B):
        k = min(B, n - r0)
        t.putcol("RANG_FLAG", t.getcol("FLAG", r0, k), r0, k)
    done["RANG_FLAG"] = "FLAG after rang's apply"
fv = table(ms + ".flagversions/flags." + version, ack=False)
assert fv.nrows() == n
for r0 in range(0, n, B):
    k = min(B, n - r0)
    t.putcol("FLAG", fv.getcol("FLAG", r0, k), r0, k)
    t.putcol("FLAG_ROW", fv.getcol("FLAG_ROW", r0, k), r0, k)
fv.close()
t.close()
f = table(ms + "/FEED", readonly=False, ack=False)
a = f.getcol("RECEPTOR_ANGLE")
before = a[:, :].tolist()[:1]
a[:] = np.deg2rad(-90.0)
f.putcol("RECEPTOR_ANGLE", a)
f.close()
json.dump({"renamed": done, "flag_from": version, "rows": n,
           "receptor_angle_before": before}, open(out, "w"), indent=1)
"""


def apply_summary(r):
    return json.loads((Path(r) / "rang-run" / "apply" / "summary.json").read_text())


def flag_version(ms_or_state, stage):
    return state(ms_or_state)["stages"][stage]["flag_version"]


def prep_mounts(r):
    return [(Path(r) / "casa", "/c"), (Path(r), "/p")]


def prep(ms, r):
    ms, r = Path(ms), Path(r)
    version = apply_summary(r)["flag_version"]  # FLAG before apply = after calibrate
    (r / "e2p_prep.py").write_text(PREP_PY, encoding="utf-8")
    return docker(r, FORMATS_IMAGE, prep_mounts(r),
                  f"{QC_PY} -I /p/e2p_prep.py /c/{ms.name} {version} /p/prep.json", "prep")  # fmt: skip


APPLY_PY = """\
import json, sys
import casatasks
spec = json.load(open(sys.argv[1]))
out = []
for call in spec:
    try:
        casatasks.applycal(**call)
        out.append({"field": call["field"], "error": None})
    except Exception as exc:
        out.append({"field": call["field"], "error": repr(exc)})
json.dump(out, open(sys.argv[2], "w"), indent=1)
"""


def applycal_spec(r, ms_inside):
    """CASA applycal calls rebuilt from rang's apply summary: one call per
    field of each applied entry; tables, gainfield and interp as rang
    recorded them; calwt, parang and applymode as rang's."""
    s = apply_summary(r)
    calls = []
    for entry in s["applied"]:
        names, tabs = entry["tables_applied"], entry["tables"]
        assert len(names) == len(tabs)
        for f in entry["fields"]:
            calls.append({
                "vis": ms_inside, "field": f, "scan": ",".join(str(x) for x in entry["scans"]),
                "gaintable": [f"/p/rang-run/calibrate/{n}" for n in names],
                "gainfield": [t["gainfield"] for t in tabs],
                "interp": [t["interp"] for t in tabs],
                "calwt": [bool(t["calwt_effective"]) for t in tabs],
                "parang": bool(entry["parang"]), "applymode": entry["applymode"],
                "flagbackup": False,
            })  # fmt: skip
    return calls


def applycal(ms, r):
    ms, r = Path(ms), Path(r)
    calls = applycal_spec(r, f"/c/{ms.name}")
    write(r / "applycal-spec.json", calls)
    (r / "e2p_applycal.py").write_text(APPLY_PY, encoding="utf-8")
    return docker(r, CASA_IMAGE, prep_mounts(r),
                  "/opt/casa/bin/python -I /p/e2p_applycal.py /p/applycal-spec.json /p/applycal-result.json",
                  "applycal")  # fmt: skip


COMPARE_PY = r"""
import json, sys
import numpy as np
from casacore.tables import table
ms, out = sys.argv[1:3]
B = 4000
eps = float(np.finfo(np.float32).eps)
t = table(ms, ack=False)
n = t.nrows()
res = {"rows": n, "cells": 0, "compared_cells": 0, "flag_elements_differ": 0,
       "cells_over_class_c": 0, "max_eps_of_cell_max": 0.0, "max_rel": 0.0,
       "nonfinite_compared": 0}
for r0 in range(0, n, B):
    k = min(B, n - r0)
    c = t.getcol("CORRECTED_DATA", r0, k)
    g = t.getcol("RANG_CORRECTED_DATA", r0, k)
    fc = t.getcol("FLAG", r0, k)
    fg = t.getcol("RANG_FLAG", r0, k)
    res["flag_elements_differ"] += int((fc != fg).sum())
    res["cells"] += int(fc.shape[0] * fc.shape[1])
    use = ~(fc | fg)                      # (row, chan, corr)
    ag = np.abs(g)
    cellmax = ag.max(-1, keepdims=True)
    d = np.abs(c.astype(np.complex128) - g.astype(np.complex128))
    tol = np.maximum(1e-6 * ag, 11 * eps * cellmax)
    bad = use & ~(d <= tol)
    res["nonfinite_compared"] += int((use & ~np.isfinite(d)).sum())
    res["cells_over_class_c"] += int(bad.any(-1).sum())
    res["compared_cells"] += int(use.any(-1).sum())
    with np.errstate(divide="ignore", invalid="ignore"):
        e = np.where(use & (cellmax > 0), d / (eps * cellmax), 0.0)
        rel = np.where(use & (ag > 0), d / ag, 0.0)
    res["max_eps_of_cell_max"] = max(res["max_eps_of_cell_max"], float(np.nanmax(e)))
    res["max_rel"] = max(res["max_rel"], float(np.nanmax(rel)))
json.dump(res, open(out, "w"), indent=1)
print(json.dumps(res))
"""


def compare(ms, r):
    ms, r = Path(ms), Path(r)
    tasks = json.loads((r / "applycal-result.json").read_text())
    errors = [t for t in tasks if t["error"]]
    (r / "e2p_compare.py").write_text(COMPARE_PY, encoding="utf-8")
    rc = docker(r, FORMATS_IMAGE, prep_mounts(r),
                f"{QC_PY} -I /p/e2p_compare.py /c/{ms.name} /p/compare-raw.json", "compare")  # fmt: skip
    raw = json.loads((r / "compare-raw.json").read_text()) if rc == 0 else {}
    ok = (rc == 0 and not errors and raw.get("compared_cells", 0) > 0
          and raw["cells_over_class_c"] == 0 and raw["flag_elements_differ"] == 0
          and raw["nonfinite_compared"] == 0)  # fmt: skip
    write(r / "g2b-applycal.json", {"applycal_calls": len(tasks), "applycal_errors": errors,
          "compare_exit": rc, **raw, "class_c": "per cell <= 1e-6 relative or <= 11 float32 "
          "epsilons of the cell's largest correlation; flags exact", "met": ok})  # fmt: skip
    return 0


SNAP_PY = r"""
import sys
import numpy as np
from casacore.tables import table
t = table(sys.argv[1], ack=False)
cols = {c: t.getcol(c) for c in ("ANTENNA1", "ANTENNA2", "FIELD_ID", "SCAN_NUMBER", "TIME")}
for c in ("FLAG", "RANG_FLAG"):
    cols[c] = np.packbits(t.getcol(c), axis=-1)  # 4 correlations packed, MSB first
np.savez(sys.argv[2], **cols)
print({k: v.shape for k, v in cols.items()})
"""


def snapshot(ms, r):
    """CASA's FLAG after applycal and rang's applied FLAG (RANG_FLAG) on the copy,
    kept before the 3b arm's prep resets FLAG (the Df flag-rule follow-up)."""
    ms, r = Path(ms), Path(r)
    (r / "df-flag-snapshot").mkdir(exist_ok=True)
    (r / "e2p_snap.py").write_text(SNAP_PY, encoding="utf-8")
    return docker(r, FORMATS_IMAGE, prep_mounts(r),
                  f"{QC_PY} -I /p/e2p_snap.py /c/{ms.name} "
                  "/p/df-flag-snapshot/flags-after-applycal.npz", "snapshot")  # fmt: skip


# --- gate 2a and the restore -------------------------------------------------------


def flag_hash(ms):
    from rang import core_ms

    hf, hr = hashlib.sha256(), hashlib.sha256()
    with core_ms.open_table(ms) as t:
        n = t.nrows
        for r0 in range(0, n, BLOCK):
            k = min(BLOCK, n - r0)
            hf.update(
                np.ascontiguousarray(
                    np.asarray(t.getcol("FLAG", r0, k), bool)
                ).tobytes()
            )
            hr.update(
                np.ascontiguousarray(
                    np.asarray(t.getcol("FLAG_ROW", r0, k), bool)
                ).tobytes()
            )
    return {
        "rows": int(n),
        "flag_sha256": hf.hexdigest(),
        "flag_row_sha256": hr.hexdigest(),
    }


DROP_PY = r"""
import json, sys
from casacore.tables import table
ms, keep, out = sys.argv[1], json.load(open(sys.argv[2])), sys.argv[3]
t = table(ms, readonly=False, ack=False)
extra = [c for c in t.colnames() if c not in keep]
if extra:
    t.removecols(extra)
json.dump({"dropped": extra, "columns": t.colnames()}, open(out, "w"), indent=1)
t.close()
"""


def restore(ms, r, input_json, label="g2a"):
    from rang import core_writeback

    ms, r = Path(ms), Path(r)
    t0 = time.perf_counter()
    rows = core_writeback.restore_flags(ms, "rang_original")
    got = flag_hash(ms)
    want = json.loads(Path(input_json).read_text())
    keep = r / "columns-before.json"
    if not keep.exists():
        raise SystemExit(f"{keep} missing: the MS's columns before the run")
    (r / "e2p_drop.py").write_text(DROP_PY, encoding="utf-8")
    rc = docker(r, FORMATS_IMAGE, [(ms.parent, "/ms"), (r, "/p")],
                f"{QC_PY} -I /p/e2p_drop.py /ms/{ms.name} /p/columns-before.json /p/{label}-drop.json",
                f"{label}-drop")  # fmt: skip
    moved = None
    if run_dir(ms).exists() and label == "g2a":
        moved = r / "rang-run-moved"
        shutil.move(str(run_dir(ms)), str(moved))
    ok = (got["flag_sha256"] == want["flag_sha256"]
          and got["flag_row_sha256"] == want["flag_row_sha256"] and got["rows"] == want["rows"])  # fmt: skip
    write(r / f"{label}.json", {"restored_rows": rows, "hash": got, "input": want,
          "drop_exit": rc, "rang_run_moved_to": moved, "seconds": time.perf_counter() - t0,
          "met": ok and rc == 0})  # fmt: skip
    return 0


def columns_before(ms, r):
    from rang import core_ms

    with core_ms.open_table(ms) as t:
        cols = list(t.colnames())
    write(Path(r) / "columns-before.json", cols)
    return 0


# --- gate 3a ------------------------------------------------------------------------


def tricolour(ms, r, input_json, strategy):
    from rang.formats import flagversions

    ms, r = Path(ms), Path(r)
    g2a = json.loads((r / "g2a.json").read_text())
    if not g2a["met"]:
        raise SystemExit(
            "gate 2a not met: the MS is not as converted, Tricolour not run"
        )
    shutil.copy(strategy, r / "tricolour-strategy.yaml")
    cmd = (f"tricolour -c /p/tricolour-strategy.yaml -fs polarisation -dc DATA -dpm "
           f"/ms/{ms.name}")  # fmt: skip
    rc = docker(
        r, TRICOLOUR_IMAGE, [(ms.parent, "/ms"), (r, "/p")], cmd, "tricolour", 16
    )
    out = {"tricolour_exit": rc}
    if rc == 0:
        from rang import core_ms

        moved = r / "rang-run-moved"
        name = json.loads((moved / "state.json").read_text())["stages"]["calibrate"][
            "flag_version"
        ]
        out["rang_version"] = name  # FLAG before calibrate = after rang's flag stage
        acc = {"elements_differ": 0, "cells_differ": 0, "rang_only": 0, "tricolour_only": 0,
               "corr_partial": 0, "cells": 0}  # fmt: skip
        scans = {}
        with core_ms.open_table(ms) as t:
            n = t.nrows
            for r0 in range(0, n, BLOCK):
                k = min(BLOCK, n - r0)
                a = np.asarray(flagversions.load(ms, name, r0, k)[0], bool)
                b = np.asarray(t.getcol("FLAG", r0, k), bool)
                s = np.asarray(t.getcol("SCAN_NUMBER", r0, k))
                d = (a != b).any(-1)
                acc["elements_differ"] += int((a != b).sum())
                acc["cells_differ"] += int(d.sum())
                acc["rang_only"] += int((a.any(-1) & ~b.any(-1)).sum())
                acc["tricolour_only"] += int((~a.any(-1) & b.any(-1)).sum())
                acc["corr_partial"] += int((d & ~(a != b).all(-1)).sum())
                acc["cells"] += int(d.size)
                for sc in np.unique(s):
                    scans[int(sc)] = scans.get(int(sc), 0) + int(d[s == sc].sum())
        out.update(acc, cells_differ_by_scan=scans, exact=acc["elements_differ"] == 0)
    write(r / "g3a.json", out)
    restore(ms, r, input_json, label="g3a-restore")
    return 0


STEPS = {"gate1": gate1, "archive": archive, "wcs": wcs, "casacore": casacore,
         "casa-ro": casa_ro, "wsclean0": wsclean0, "daskms": daskms, "wsclean3c": wsclean3c,
         "wsclean3c-unit": wsclean3c_unit, "copy": copy,
         "prep": prep, "applycal": applycal, "compare": compare, "snapshot": snapshot, "restore": restore,
         "tricolour": tricolour, "columns-before": columns_before}  # fmt: skip


def main(argv):
    step, ms, r, *rest = argv
    Path(r).mkdir(parents=True, exist_ok=True)
    log(r, f"step {step} {ms} {rest}")
    return STEPS[step](ms, r, *rest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
