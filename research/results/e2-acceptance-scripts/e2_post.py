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

E2-A runs the in-place order instead (`ORDER_INPLACE`, research/e2-acceptance.md
9.9): no `copy`; `prep-inplace`, `applycal-inplace`, `compare-inplace` and
`snapshot-inplace` act on the leg's MS itself, then (9.10) E2-A's own reads of
rang's columns, then `restore` and `tricolour`:

    drop-corrected-inplace  CASA's CORRECTED_DATA dropped after 2b (-128 GiB)
    qc-avg            native: CORRECTED_1GC and each round's model averaged in
                      time within selfcal's intervals (unit weights, FLAG after
                      apply and each round's own flags)  -> R/qc-selfcal/
    qc-selfcal        QuartiCal 0.2.7 on an ext4 MS of those averages, per
                      round; class B against rang's stores -> R/qc-selfcal.json
    unit-on-a         gate 3c's matched state (E2-B's UNIT_PY) on the MS
    wsclean3c-a-dirty WSClean 3.7 dirty image of RANG_CORRECTED_DATA (Stokes I,
                      the image stage's argv)       -> R/wsclean3c-a/
    wsclean3c-a-clean the same, cleaned as the image stage
    score3c-a         gate 3c's primary reading (e2_score3c_a.py) -> R/g3c-a.json
    wsclean3c-a-nosi-dirty, score3c-a-nosi
                      optional (the launcher's NOSI=0 skips them): after the
                      primary is scored, one -no-small-inversion dirty run and
                      its dirty-only reading, seen -> R/g3c-a-nosi.json
    unit-off-a        the matched state undone (restore refuses while it is on)

`restore` takes INPUT.json (e2_flaghash.py of the MS as converted);
`tricolour` takes INPUT.json and the strategy file. Every step runs under
the main checkout's tools/heavy_lock.py (the caller wraps it).
"""

import hashlib
import importlib.util
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
    vols, made = [], []
    for host, inside in mounts:
        if isinstance(host, str) and host.startswith("$HOME/"):  # WSL ext4, not /mnt
            # unquoted: bash expands $HOME, and no double quote crosses wsl.exe
            vols += ["-v", f"{host}:{inside}:rw"]
            made += ["mkdir", "-p", host, "&&"]
        else:
            vols += ["-v", f"'{wsl(host)}:{inside}:rw'"]
    inner = " ".join(
        [*made, "docker", "run", "--rm", "--network", "none", "--user", "$(id -u):$(id -g)",
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


# --- gate 2b in place (E2-A; research/e2-acceptance.md 9.9) ----------------------
#
# E2-A's MS after the chain is about 608 GiB, so `copy` cannot run (9.6). In
# place, on the leg's MS itself and after every read of rang's columns:
#   prep-inplace      rang's apply output (CORRECTED_1GC when selfcal copied it,
#                     else CORRECTED_DATA) -> RANG_CORRECTED_DATA, MODEL_DATA ->
#                     RANG_MODEL_DATA, RANG_FLAG = FLAG after rang's apply (the
#                     flag version selfcal saved, else FLAG as it is), FLAG from
#                     the version before apply; RECEPTOR_ANGLE must already be
#                     -90 deg (ESO137 stores it so) and is not written
#   applycal-inplace  CASA applycal with rang's tables into CORRECTED_DATA (with
#                     selfcal, the existing column holding rang's selfcal output
#                     is overwritten: no new 128 GiB column)
#   compare-inplace, snapshot-inplace   as compare and snapshot, on the MS
# then `restore` (FLAG from rang_original, every column not in
# columns-before.json dropped, RANG_* included) and `tricolour`.
ORDER_INPLACE = ["gate1", "archive", "wcs", "casacore", "casa-ro", "wsclean0", "daskms",
                 "prep-inplace", "applycal-inplace", "compare-inplace", "snapshot-inplace",
                 "drop-corrected-inplace", "qc-avg", "qc-selfcal",
                 "unit-on-a", "wsclean3c-a-dirty", "wsclean3c-a-clean", "score3c-a",
                 "wsclean3c-a-nosi-dirty", "score3c-a-nosi", "unit-off-a",
                 "restore", "tricolour"]  # fmt: skip


def inplace_plan(ms):
    """What prep-inplace renames and which flag versions it uses, from the run
    directory alone (state.json, selfcal-input.json, apply/summary.json)."""
    rd = run_dir(ms)
    st = state(ms)["stages"]
    apply = st.get("apply") or {}
    if apply.get("status") != "done":
        raise SystemExit("apply is not done: nothing to compare")
    summary = json.loads((rd / "apply" / "summary.json").read_text(encoding="utf-8"))
    column = summary.get("column", "CORRECTED_DATA")
    marker = rd / "selfcal-input.json"
    selfcal = st.get("selfcal") or {}
    if marker.is_file() and "flag_version" in selfcal:
        copied = json.loads(marker.read_text(encoding="utf-8"))
        if copied.get("copied_from") != column or copied.get("apply_finished") != apply.get("finished"):
            raise SystemExit(f"{marker} does not record a copy of this run's apply output")  # fmt: skip
        rang_column, rang_flag = copied["column"], selfcal["flag_version"]
    else:
        rang_column, rang_flag = column, None  # FLAG as it is is FLAG after apply
    return {"rang_column": rang_column, "rang_flag_version": rang_flag,
            "flag_before_apply": summary["flag_version"], "applycal_writes": column}  # fmt: skip


PREP_INPLACE_PY = r"""
import json, sys
import numpy as np
from casacore.tables import table, makecoldesc
ms, plan_path, out = sys.argv[1:4]
plan = json.load(open(plan_path))
B = 4000
f = table(ms + "/FEED", ack=False)
angle = f.getcol("RECEPTOR_ANGLE")
f.close()
if not np.allclose(angle, np.deg2rad(-90.0)):
    raise SystemExit("RECEPTOR_ANGLE is not -90 deg; the in-place order does not write FEED")
t = table(ms, readonly=False, ack=False)
cols = t.colnames()
done = {}
src = plan["rang_column"]
if "RANG_CORRECTED_DATA" not in cols:
    t.renamecol(src, "RANG_CORRECTED_DATA")
    done[src] = "RANG_CORRECTED_DATA"
if "MODEL_DATA" in cols and "RANG_MODEL_DATA" not in cols:
    t.renamecol("MODEL_DATA", "RANG_MODEL_DATA")
    done["MODEL_DATA"] = "RANG_MODEL_DATA"
n = t.nrows()
if "RANG_FLAG" not in t.colnames():
    dm = t.getdminfo("FLAG")
    dm["NAME"] = "RangFlagTSM"
    if "SPEC" in dm and "HYPERCUBES" in dm["SPEC"]:
        dm["SPEC"].pop("HYPERCUBES", None)
    t.addcols(makecoldesc("RANG_FLAG", t.getcoldesc("FLAG")), dm)
    v = plan["rang_flag_version"]
    fa = table(ms + ".flagversions/flags." + v, ack=False) if v else None
    for r0 in range(0, n, B):
        k = min(B, n - r0)
        t.putcol("RANG_FLAG", (fa if fa is not None else t).getcol("FLAG", r0, k), r0, k)
    if fa is not None:
        fa.close()
    done["RANG_FLAG"] = "FLAG after rang's apply" + (" (" + v + ")" if v else "")
fv = table(ms + ".flagversions/flags." + plan["flag_before_apply"], ack=False)
assert fv.nrows() == n
for r0 in range(0, n, B):
    k = min(B, n - r0)
    t.putcol("FLAG", fv.getcol("FLAG", r0, k), r0, k)
    t.putcol("FLAG_ROW", fv.getcol("FLAG_ROW", r0, k), r0, k)
fv.close()
t.close()
json.dump({"renamed": done, "plan": plan, "rows": n, "receptor_angle": "-90 deg, unchanged"},
          open(out, "w"), indent=1)
"""


def inplace_mounts(ms, r):
    return [(Path(ms).parent, "/c"), (Path(r), "/p")]


def prep_inplace(ms, r):
    ms, r = Path(ms), Path(r)
    plan = inplace_plan(ms)
    write(r / "prep-inplace-plan.json", plan)
    (r / "e2p_prep_inplace.py").write_text(PREP_INPLACE_PY, encoding="utf-8")
    return docker(r, FORMATS_IMAGE, inplace_mounts(ms, r),
                  f"{QC_PY} -I /p/e2p_prep_inplace.py /c/{ms.name} /p/prep-inplace-plan.json "
                  "/p/prep-inplace.json", "prep-inplace")  # fmt: skip


def applycal_inplace(ms, r):
    return applycal(ms, r, mounts=inplace_mounts(ms, r))


def compare_inplace(ms, r):
    return compare(ms, r, mounts=inplace_mounts(ms, r))


def snapshot_inplace(ms, r):
    return snapshot(ms, r, mounts=inplace_mounts(ms, r))


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


def applycal(ms, r, mounts=None):
    ms, r = Path(ms), Path(r)
    calls = applycal_spec(r, f"/c/{ms.name}")
    write(r / "applycal-spec.json", calls)
    (r / "e2p_applycal.py").write_text(APPLY_PY, encoding="utf-8")
    return docker(r, CASA_IMAGE, mounts or prep_mounts(r),
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


def compare(ms, r, mounts=None):
    ms, r = Path(ms), Path(r)
    tasks = json.loads((r / "applycal-result.json").read_text())
    errors = [t for t in tasks if t["error"]]
    (r / "e2p_compare.py").write_text(COMPARE_PY, encoding="utf-8")
    rc = docker(r, FORMATS_IMAGE, mounts or prep_mounts(r),
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
n = t.nrows()
for c in ("FLAG", "RANG_FLAG"):
    # 4 correlations packed, MSB first; read in blocks (E2-A: a whole FLAG is 69 GB)
    first = np.packbits(t.getcol(c, 0, 1), axis=-1)
    out = np.empty((n, *first.shape[1:]), np.uint8)
    for r0 in range(0, n, 4000):
        k = min(4000, n - r0)
        out[r0 : r0 + k] = np.packbits(t.getcol(c, r0, k), axis=-1)
    cols[c] = out
np.savez(sys.argv[2], **cols)
print({k: v.shape for k, v in cols.items()})
"""


def snapshot(ms, r, mounts=None):
    """CASA's FLAG after applycal and rang's applied FLAG (RANG_FLAG) on the copy,
    kept before the 3b arm's prep resets FLAG (the Df flag-rule follow-up)."""
    ms, r = Path(ms), Path(r)
    (r / "df-flag-snapshot").mkdir(exist_ok=True)
    (r / "e2p_snap.py").write_text(SNAP_PY, encoding="utf-8")
    return docker(r, FORMATS_IMAGE, mounts or prep_mounts(r),
                  f"{QC_PY} -I /p/e2p_snap.py /c/{ms.name} "
                  "/p/df-flag-snapshot/flags-after-applycal.npz", "snapshot")  # fmt: skip


# --- E2-A's reads of rang's columns after gate 2b (research/e2-acceptance.md 9.10) ----
#
# 9.9 left two reads to write: gate 3c's WSClean images and the self-calibration
# row's QuartiCal gains. Both run after compare-inplace and snapshot-inplace and
# read the renamed columns: RANG_CORRECTED_DATA is rang's apply output
# (CORRECTED_1GC), RANG_MODEL_DATA selfcal's last model, and FLAG after rang's
# apply is the flag version selfcal saved (RANG_FLAG holds the same).

DROP_ONE_PY = r"""
import json, sys
from casacore.tables import table
ms, out = sys.argv[1:3]
t = table(ms, readonly=False, ack=False)
cols = t.colnames()
assert "RANG_CORRECTED_DATA" in cols and "CORRECTED_DATA" in cols, cols
t.removecols(["CORRECTED_DATA"])
json.dump({"dropped": ["CORRECTED_DATA"], "columns": t.colnames()}, open(out, "w"), indent=1)
t.close()
"""


def free_gib(path):
    return shutil.disk_usage(Path(path).resolve().anchor).free / 2**30


def drop_corrected_inplace(ms, r):
    """CASA's CORRECTED_DATA (gate 2b's applycal output; compare and snapshot
    have read it) dropped, which returns the 128 GiB that WSClean's reordered
    files need (9.10). `restore` would drop it in any case."""
    ms, r = Path(ms), Path(r)
    snap = r / "df-flag-snapshot" / "flags-after-applycal.npz"
    g = r / "g2b-applycal.json"
    if not g.is_file() or not snap.is_file():
        raise SystemExit(
            "compare-inplace and snapshot-inplace have not run: CORRECTED_DATA kept"
        )
    # compare writes its record even when its container failed; a second 2b
    # reading after the drop would need CASA to write a new 128 GiB column (9.20)
    got = json.loads(g.read_text(encoding="utf-8"))
    if got.get("compare_exit") != 0 or not got.get("compared_cells") or got.get("applycal_errors"):
        raise SystemExit(f"2b's compare did not complete ({g}): CORRECTED_DATA kept")
    before = free_gib(ms)
    (r / "e2p_drop_one.py").write_text(DROP_ONE_PY, encoding="utf-8")
    rc = docker(r, FORMATS_IMAGE, inplace_mounts(ms, r),
                f"{QC_PY} -I /p/e2p_drop_one.py /c/{ms.name} /p/drop-corrected.json",
                "drop-corrected", 1)  # fmt: skip
    write(r / "drop-corrected-run.json",
          {"exit": rc, "free_gib_before": before, "free_gib_after": free_gib(ms)})  # fmt: skip
    return rc


# --- the self-calibration row: QuartiCal 0.2.7 on rang's averaged inputs -----------
#
# The frozen row (6.5) says "unaveraged (stated)". At selfcal's solint (120
# integrations) one QuartiCal chunk of E2-A's target holds 120 x 1,830
# baselines x 4,096 channels x 4 correlations: 28.8 GB of complex64 data and
# as much model, beyond WSL's 44 GB, so that form cannot run here (6.5's rule:
# the reason is recorded, `unaveraged_form` in qc-selfcal.json). 9.10's form:
# the averages rang's `selfcal.average_time` solves (CASA's estimator,
# cal_chunks.load_averaged) are recomputed here without rang's averaging code,
# written to a small MS on WSL ext4, and QuartiCal solves one interval per
# averaged time.

QC_B = {"median": 7e-4, "p95": 3e-3}  # C5's G2 (C2a's class B), products, gauge-free
QC_SUB = 2048  # rows read per block
QC_EXT4 = "$HOME/e2a-qc"  # the small MSs (about 3 GiB each), deleted after each round
WSL_MEMORY_GB = 44  # ~/.wslconfig, 2026-11-13
QUARTICAL_TYPES = {"Sp": "phase", "Sa": "diag_complex"}  # cal_selfcal.QUARTICAL


def solint_n(solint):
    """N integrations of a selfcal `solint` (an int; 'int' 1; 'inf' 0, the
    scan); None for seconds bins (no QuartiCal form)."""
    if isinstance(solint, bool):
        raise TypeError(f"solint {solint!r}")
    if isinstance(solint, (int, np.integer)):
        return int(solint)
    text = str(solint).strip().lower()
    if text == "inf":
        return 0
    if text == "int":
        return 1
    return int(text) if text.isdigit() else None


def qc_layout(time, scan, a1, a2, n):
    """Selfcal's intervals and the averaged rows from row metadata alone
    (written from cal_selfcal.time_bins' rule, not calling it): per scan in
    time order, N of its unique times per interval from the scan start (0:
    the scan); one averaged row per (interval, ANTENNA1, ANTENNA2) of the
    cross-correlations, ordered by its first source row. Returns `bin` and
    `out` (averaged row, -1 for autocorrelations) per source row; per
    averaged row `template` (its first source row), `a1`, `a2`, `out_bin`;
    per interval `bin_time` (mean of its unique times) and `bin_scan`."""
    time = np.asarray(time, np.float64)
    scan = np.asarray(scan)
    a1 = np.asarray(a1, np.int64)
    a2 = np.asarray(a2, np.int64)
    tb = np.empty(len(time), np.int64)
    bin_time, bin_scan, offset = [], [], 0
    for s in sorted(np.unique(scan), key=lambda s: time[scan == s].min()):
        m = scan == s
        u, inv = np.unique(time[m], return_inverse=True)
        step = len(u) if n == 0 else n
        local = inv.reshape(-1) // step
        tb[m] = local + offset
        for b in range(int(local.max()) + 1):
            bin_time.append(u[b * step : (b + 1) * step].mean())
            bin_scan.append(int(s))
        offset += int(local.max()) + 1
    nant = int(max(a1.max(), a2.max())) + 1
    cross = np.flatnonzero(a1 != a2)
    key = (tb[cross] * nant + a1[cross]) * nant + a2[cross]
    uniq, first, inv = np.unique(key, return_index=True, return_inverse=True)
    template = cross[first]
    order = np.argsort(template, kind="stable")
    rank = np.empty_like(order)
    rank[order] = np.arange(len(order))
    out = np.full(len(time), -1, np.int64)
    out[cross] = rank[inv.reshape(-1)]
    ukey = uniq[order]
    return {"bin": tb, "out": out, "template": template[order],
            "a1": (ukey // nant) % nant, "a2": ukey % nant, "out_bin": ukey // (nant * nant),
            "bin_time": np.asarray(bin_time), "bin_scan": np.asarray(bin_scan)}  # fmt: skip


class QcSums:
    """Per averaged row, channel and correlation, over the unflagged samples
    of rows without FLAG_ROW (unit weights, E2-A's `data.weights: uniform`):
    the count and the complex128 sums of data and model. `means` gives the
    averaged arrays as rang's `load_averaged` defines them: data and model
    the means (complex64, 0 where nothing was summed), the weight the count,
    flagged where it is 0; an averaged row with no live source row is
    flagged as a row."""

    def __init__(self, nout, nchan, ncorr):
        shape = (nout, nchan, ncorr)
        self.n = np.zeros(shape, np.int32)
        self.d = np.zeros(shape, np.complex128)
        self.m = np.zeros(shape, np.complex128)
        self.live = np.zeros(nout, bool)

    def add(self, out, data, model, flag, flag_row):
        keep = (np.asarray(out) >= 0) & ~np.asarray(flag_row, bool)
        idx = np.asarray(out)[keep]
        used = ~np.asarray(flag, bool)[keep]
        d = np.where(used, data[keep], 0).astype(np.complex128)
        m = np.where(used, model[keep], 0).astype(np.complex128)
        u = used.astype(np.int32)
        self.live[idx] = True
        rest = np.arange(len(idx))
        while len(rest):  # one source row per averaged row per pass: fancy += is exact
            _, first = np.unique(idx[rest], return_index=True)
            take = rest[first]
            self.n[idx[take]] += u[take]
            self.d[idx[take]] += d[take]
            self.m[idx[take]] += m[take]
            rest = np.delete(rest, first)

    def means(self):
        good = self.n > 0
        div = np.where(good, self.n, 1)
        return {"data": np.where(good, self.d / div, 0).astype(np.complex64),
                "model": np.where(good, self.m / div, 0).astype(np.complex64),
                "weight": self.n.astype(np.float32), "flag": ~good,
                "flag_row": ~self.live}  # fmt: skip


def apply_flags(valid, tb, fb, a1, a2):
    """(row, channel): where rang's selfcal apply flags a row (all four
    correlations, cal_selfcal.apply), that is where either antenna's gain is
    invalid on the row's interval and the channel's frequency bin. `valid`
    is (interval, frequency bin, antenna)."""
    v = np.asarray(valid, bool)[np.asarray(tb)]
    rows = np.arange(len(tb))
    bad = ~v[rows, :, np.asarray(a1)] | ~v[rows, :, np.asarray(a2)]
    return bad[:, np.asarray(fb)]


def qc_freq_bins(nchan, freqint):
    if freqint in ("inf", None, 0):
        return np.zeros(nchan, np.int64)
    return np.arange(nchan) // (1 if freqint == "int" else int(freqint))


def qc_avg(ms, r):
    """Step qc-avg (native, from the frozen wheel's venv, whose predictor
    wrote selfcal's MODEL_DATA). For every selfcal round: rang's solve input
    (CORRECTED_1GC, RANG_CORRECTED_DATA after prep-inplace) and that round's
    model, averaged as `selfcal.average_time` averages them, with the flags
    that round's solve saw (selfcal's flag version, ORed with the earlier
    rounds' apply flags recomputed from their stores). The MS holds only the
    last round's model, so every round's model is predicted again from its
    model images by rang's predictor, block for block as
    `core_model.write_model_data` predicted it; control: the last round's
    prediction equals the MS's model column in every element. The last
    round sums the column itself, so a failed control voids only the
    earlier rounds (qc-selfcal marks them). Writes R/qc-selfcal/ (about
    2.5 GiB per round) and R/qc-avg.json."""
    from rang import _core, cal_selfcal, core_model, core_ms, core_pipeline
    from rang.formats import flagversions

    ms, r = Path(ms), Path(r)
    rd = run_dir(ms)
    started = time.perf_counter()
    cfg = json.loads((rd / "config.resolved.json").read_text(encoding="utf-8"))
    sc = json.loads((rd / "selfcal" / "summary.json").read_text(encoding="utf-8"))
    plan = inplace_plan(ms)
    if plan["rang_flag_version"] is None:
        raise SystemExit("this run has no selfcal copy: nothing to compare")
    if cfg["data"]["weights"] != "uniform":
        raise SystemExit("qc-avg sums unit weights only (E2-A: data.weights uniform)")
    (field,) = sc["fields"]
    fid = int(field["field_id"])
    rounds = field["rounds"]
    ns = {solint_n(x["term"]["solint"]) for x in rounds}
    if len(ns) != 1 or None in ns:
        raise SystemExit(f"qc-avg needs one integration-count solint for all rounds: {ns}")
    (n,) = ns
    scans = list(cfg["data"]["scans"] or [])
    img = cfg["image"]
    extra = [str(a) for a in img["extra_args"]]
    rng = core_pipeline._extra_flag(extra, "-channel-range", 2)
    channel_range = None if rng is None else (int(rng[0]), int(rng[1]))
    single = core_pipeline._gridder_single(img, extra)
    wgridding = core_pipeline._extra_flag(extra, "-no-wgridding") is None
    freq, corr, phase_dir = core_model.band(ms, fid, 0)
    a, b = core_model._hands(corr)
    nchan, ncorr = len(freq), len(corr)
    cmap = np.asarray(_core.gemclean_channel_map(
        freq, int(img["channels_out"]), channel_range, int(img["average_channels"])))  # fmt: skip
    mapped = np.flatnonzero(cmap >= 0)

    def predict(name, uvw):  # core_model.write_model_data's predict, unchanged
        out = np.zeros((uvw.shape[0], nchan), np.complex64)
        _core.gemclean_predict(str(name), int(img["channels_out"]), channel_range,
                               int(img["average_channels"]), float(img["wgridder_accuracy"]),
                               bool(wgridding), bool(single), phase_dir, uvw, freq, out)  # fmt: skip
        return out

    with core_ms.open_table(ms) as t:
        cols = set(t.colnames())
        data_col = (
            "RANG_CORRECTED_DATA" if "RANG_CORRECTED_DATA" in cols else plan["rang_column"]
        )
        model_col = "RANG_MODEL_DATA" if "RANG_MODEL_DATA" in cols else sc["model_column"]
        nrow = t.nrows
        meta = {c: np.asarray(t.getcol(c, 0, nrow))
                for c in ("FIELD_ID", "SCAN_NUMBER", "TIME", "ANTENNA1", "ANTENNA2")}  # fmt: skip
    keep = meta["FIELD_ID"] == fid
    if scans:
        keep &= np.isin(meta["SCAN_NUMBER"], scans)
    rows = np.flatnonzero(keep)  # the solve's rows (core_pipeline._selected_rows)
    lay = qc_layout(meta["TIME"][rows], meta["SCAN_NUMBER"][rows],
                    meta["ANTENNA1"][rows], meta["ANTENNA2"][rows], n)  # fmt: skip
    sel = core_model.selected_rows(ms, fid, 0, scans or None)  # the predictor's rows
    if not np.array_equal(sel, rows[lay["out"] >= 0]):
        raise SystemExit("the predictor's rows are not the solve's cross-correlations")
    pos = np.full(nrow, -1, np.int64)
    pos[rows] = np.arange(len(rows))
    stores, valid = [], []
    for x in rounds:
        g, f, gt, _gf, _gs = cal_selfcal.read_store(x["store"], x["solve"]["name"])
        stores.append(gt)
        valid.append(~f & np.isfinite(g).all(-1))
    times_equal = [bool(len(gt) == len(lay["bin_time"])
                        and np.max(np.abs(gt - lay["bin_time"])) <= 1e-6)
                   for gt in stores]  # fmt: skip
    if not all(times_equal):
        raise SystemExit(f"rang's intervals differ from qc-avg's: {times_equal}")
    fbs = [qc_freq_bins(nchan, x["term"].get("freqint", "inf")) for x in rounds]
    nout = len(lay["template"])
    sums = [QcSums(nout, nchan, ncorr) for _ in rounds]
    newly = [0] * len(rounds)
    ctrl = {"cells": 0, "elements_differ": 0, "max_abs": 0.0}
    block = int(_core.gemclean_block_rows(nchan))
    last = len(rounds) - 1
    with core_ms.open_table(ms) as t:
        for b0 in range(0, len(sel), block):
            blk = sel[b0 : b0 + block]
            lo, hi = int(blk[0]), int(blk[-1]) + 1
            uvw = np.ascontiguousarray(t.getcol("UVW", lo, hi - lo)[blk - lo], np.float64)
            vis = [predict(x["model"]["name"], uvw) for x in rounds]
            del uvw
            # every solve row from this block's first row to the next block's
            r_lo = int(rows[0]) if b0 == 0 else lo
            r_hi = int(sel[b0 + block]) if b0 + block < len(sel) else int(rows[-1]) + 1
            for s0 in range(r_lo, r_hi, QC_SUB):
                s1 = min(r_hi, s0 + QC_SUB)
                here = np.flatnonzero(keep[s0:s1]) + s0
                if not len(here):
                    continue
                pick = here - s0
                data = np.asarray(t.getcol(data_col, s0, s1 - s0))[pick]
                mcol = np.asarray(t.getcol(model_col, s0, s1 - s0))[pick]
                fv, frow = flagversions.load(ms, plan["rang_flag_version"], s0, s1 - s0)
                flag = np.asarray(fv, bool)[pick].copy()
                frow = np.asarray(frow, bool)[pick]
                p = pos[here]
                out = lay["out"][p]
                c = np.flatnonzero(out >= 0)
                at = np.searchsorted(blk, here[c])
                for k, x in enumerate(rounds):
                    model = mcol.copy()
                    v = vis[k][at]
                    cells = model[c[:, None], mapped[None, :], :]
                    cells[...] = 0
                    cells[..., a] = v[:, mapped]
                    cells[..., b] = v[:, mapped]
                    model[c[:, None], mapped[None, :], :] = cells
                    if k == last:  # the control; the MS's own model is summed
                        diff = model[c] != mcol[c]
                        ctrl["cells"] += int(diff[..., 0].size)
                        ctrl["elements_differ"] += int(diff.sum())
                        if diff.any():
                            gap = np.abs(model[c].astype(np.complex128) - mcol[c]).max()
                            ctrl["max_abs"] = max(ctrl["max_abs"], float(gap))
                        model = mcol
                    sums[k].add(out, data, model, flag, frow)
                    bad = apply_flags(valid[k], lay["bin"][p], fbs[k],
                                      meta["ANTENNA1"][here], meta["ANTENNA2"][here])  # fmt: skip
                    bad = np.broadcast_to(bad[..., None], flag.shape)
                    newly[k] += int((bad & ~flag).sum())
                    flag |= bad  # the next round's solve sees this round's apply
            del vis
    d = r / "qc-selfcal"
    d.mkdir(exist_ok=True)
    np.save(d / "template_rows.npy", rows[lay["template"]])
    np.savez(d / "layout.npz", a1=lay["a1"], a2=lay["a2"], bin=lay["out_bin"],
             time=lay["bin_time"][lay["out_bin"]], bin_time=lay["bin_time"],
             bin_scan=lay["bin_scan"])  # fmt: skip
    met = ctrl["cells"] > 0 and ctrl["elements_differ"] == 0
    rec = {"ms": str(ms), "data_column": data_col, "model_column": model_col,
           "flag_version": plan["rang_flag_version"], "solint_integrations": n,
           "rows": len(rows), "cross_rows": len(sel), "averaged_rows": nout,
           "baselines": len(set(zip(lay["a1"].tolist(), lay["a2"].tolist()))),
           "intervals": len(lay["bin_time"]), "channels": nchan,
           "channels_predicted": len(mapped), "predict_block_rows": block,
           "rang_intervals_equal": times_equal, "model_control": {**ctrl, "met": met},
           "rounds": []}  # fmt: skip
    for k, x in enumerate(rounds):
        sub = d / f"round-{x['round']}"
        sub.mkdir(exist_ok=True)
        for name, arr in sums[k].means().items():
            np.save(sub / f"{name}.npy", arr)
        sums[k] = None
        want = x["apply"]["cells_flagged_after"] - x["apply"]["cells_flagged_before"]
        rec["rounds"].append({"round": x["round"], "term": x["term"], "store": x["store"],
                              "solve_name": x["solve"]["name"],
                              "model_images": x["model"]["name"],
                              "apply_flags_recomputed": newly[k], "apply_flags_rang": want,
                              "apply_flags_equal": newly[k] == want})  # fmt: skip
    rec["seconds"] = time.perf_counter() - started
    write(r / "qc-avg.json", rec)
    return 0


QC_MS_PY = r"""
import json, sys
import numpy as np
from casacore.tables import table, taql, makecoldesc
src, d, dst, out = sys.argv[1:5]
COLS = ("UVW, ANTENNA1, ANTENNA2, TIME, TIME_CENTROID, INTERVAL, EXPOSURE, FIELD_ID, "
        "DATA_DESC_ID, SCAN_NUMBER, FLAG_ROW, ARRAY_ID, OBSERVATION_ID, PROCESSOR_ID, "
        "STATE_ID, FEED1, FEED2, SIGMA, WEIGHT, DATA, FLAG, WEIGHT_SPECTRUM")
rows = np.load(d + "/../template_rows.npy")
lay = np.load(d + "/../layout.npz")
t = table(src, ack=False)
cols = t.colnames()
assert "WEIGHT_SPECTRUM" in cols and not [c for c in cols if c.startswith("E2_")], cols
subs = [k for k in t.getkeywords()
        if isinstance(t.getkeyword(k), str) and t.getkeyword(k).startswith("Table: ")]
ref = t.selectrows([int(x) for x in rows])
taql(f"SELECT {COLS} FROM $ref GIVING '{dst}' AS PLAIN")
c = table(dst, readonly=False, ack=False)
copied = []
for k in subs:
    if k not in c.getkeywords():
        s = table(src + "/" + k, ack=False)
        s.copy(dst + "/" + k, deep=True)
        s.close()
        c.putkeyword(k, table(dst + "/" + k, ack=False))
        copied.append(k)
t.close()
n = c.nrows()
assert n == len(rows), (n, len(rows))
assert (c.getcol("ANTENNA1") == lay["a1"]).all() and (c.getcol("ANTENNA2") == lay["a2"]).all()
c.putcol("TIME", lay["time"])
c.putcol("TIME_CENTROID", lay["time"])
c.putcol("FLAG_ROW", np.load(d + "/flag_row.npy"))
desc = c.getcoldesc("DATA")
desc["dataManagerType"], desc["dataManagerGroup"] = "StandardStMan", "E2QcModel"
c.addcols(makecoldesc("MODEL_DATA", desc),
          {"TYPE": "StandardStMan", "NAME": "E2QcModel", "SPEC": {}})
arrays = {"DATA": "data", "MODEL_DATA": "model", "WEIGHT_SPECTRUM": "weight", "FLAG": "flag"}
arrays = {k: np.load(d + "/" + v + ".npy", mmap_mode="r") for k, v in arrays.items()}
for r0 in range(0, n, 256):
    k = min(256, n - r0)
    for name, a in arrays.items():
        c.putcol(name, np.ascontiguousarray(a[r0 : r0 + k]), r0, k)
rec = {"rows": n, "columns": c.colnames(), "subtables": subs, "subtables_copied": copied,
       "times": int(len(np.unique(lay["time"])))}
c.close()
json.dump(rec, open(out, "w"), indent=1, default=str)
print(json.dumps(rec, default=str))
"""


def qc_options(term, refant):
    """C5's QuartiCal options (examples/check_c5.py QC_OPTIONS) with the
    reference antenna, the round's type and stop rule (rang's term keys,
    cal_selfcal.solve's defaults); one interval per averaged time and one
    time per chunk (`G.time_interval=1`, `input_ms.time_chunk=1`: about
    0.25 GB of data per chunk), the round's frequency interval (0: the
    band). Keys checked against the container's argument_schema.yaml."""
    fi = term.get("freqint", "inf")
    fint = 0 if fi in ("inf", None) else (1 if fi == "int" else int(fi))
    return ["input_ms.data_column=DATA", "input_model.recipe=MODEL_DATA",
            "input_ms.weight_column=WEIGHT_SPECTRUM", "solver.terms=[G]",
            f"solver.iter_recipe=[{int(term.get('max_iterations', 50))}]",
            f"solver.convergence_criteria={float(term.get('stop_criterion', 1e-7))!r}",
            f"solver.convergence_fraction={float(term.get('stop_fraction', 0.99))!r}",
            f"solver.reference_antenna={int(refant)}", "solver.robust=false",
            "input_ms.time_chunk=1",
            "mad_flags.enable=false", "output.flags=false", "output.overwrite=false",
            "dask.threads=1", "solver.threads=1", "dask.scheduler=single-threaded",
            f"G.type={QUARTICAL_TYPES[term['type']]}", "G.time_interval=1",
            f"G.freq_interval={fint}"]  # fmt: skip


def qc_products(g, f, qg, qf):
    """C5's G2 measure (check_c5.qc_compare): relative differences of the
    gauge-free products g_p conj(g_q), p < q, per hand, where both arms hold
    a valid gain. g, qg (time, freq, ant, 2); f, qf (time, freq, ant)."""
    p, q = np.triu_indices(g.shape[2], 1)
    ok = ~f[:, :, p] & ~f[:, :, q] & ~qf[:, :, p] & ~qf[:, :, q]
    ok = np.broadcast_to(ok[..., None], (*ok.shape, 2))
    p1 = g[:, :, p] * np.conj(g[:, :, q])
    p2 = qg[:, :, p] * np.conj(qg[:, :, q])
    ok = ok & np.isfinite(p1) & np.isfinite(p2) & (np.abs(p2) > 0)
    rel = (np.abs(p1 - p2) / np.where(ok, np.abs(p2), 1.0))[ok]
    if not len(rel):
        return {"products": 0, "median": None, "p95": None, "max": None, "pass": False}
    res = {"products": len(rel), "median": float(np.median(rel)),
           "p95": float(np.percentile(rel, 95)), "max": float(rel.max())}  # fmt: skip
    res["pass"] = res["median"] <= QC_B["median"] and res["p95"] <= QC_B["p95"]
    return res


def qc_selfcal(ms, r):
    """Step qc-selfcal: per round, a small MS of qc-avg's averages on WSL
    ext4 (`QC_MS_PY`, template rows read from the MS), QuartiCal 0.2.7 on it
    (examples/oracle_gain.py qc-solve), the small MS deleted; then class B
    against rang's stored gains. -> R/qc-selfcal.json"""
    from rang import cal_selfcal

    ms, r = Path(ms), Path(r)
    avg = json.loads((r / "qc-avg.json").read_text(encoding="utf-8"))
    oracle = Path(__file__).resolve().parents[3] / "examples" / "oracle_gain.py"
    shutil.copy(oracle, r / "e2p_oracle_gain.py")
    (r / "e2p_qc_ms.py").write_text(QC_MS_PY, encoding="utf-8")
    refant = json.loads((run_dir(ms) / "selfcal" / "summary.json").read_text())["refant"]
    d = r / "qc-selfcal"
    per = avg["solint_integrations"] * avg["baselines"] * avg["channels"] * 4
    res = {"oracle": "QuartiCal 0.2.7 (rang-formats-oracle:20261030) on averaged inputs (9.10)",
           "class_b": QC_B, "refant": refant, "model_control_met": avg["model_control"]["met"],
           "unaveraged_form": {"run": False, "samples_per_interval": per,
                               "gb_per_interval_data_model_weights": per * (8 + 8 + 4) / 1e9,
                               "wsl_memory_gb": WSL_MEMORY_GB,
                               "reason": "one interval of unaveraged data, model and weights "
                                         "exceeds WSL's memory (6.5: not checked)"},
           "rounds": []}  # fmt: skip
    rc_all = 0
    last = max(x["round"] for x in avg["rounds"])
    for x in avg["rounds"]:
        k, term = x["round"], x["term"]
        if k != last and not avg["model_control"]["met"]:
            res["rounds"].append({"round": k, "quartical": "void: model control not met"})
            continue
        if term["type"] not in QUARTICAL_TYPES:
            res["rounds"].append({"round": k, "quartical": "not run: no averaged form"})
            continue
        out = d / f"qc-round-{k}"
        if not (out / "summary.json").is_file():
            shutil.rmtree(out, ignore_errors=True)
            small = f"/q/round-{k}.ms"
            script = (f"rm -rf {small} && {QC_PY} -I /p/e2p_qc_ms.py /c/{ms.name} "
                      f"/p/qc-selfcal/round-{k} {small} /p/qc-selfcal/round-{k}-ms.json && "
                      f"NUMBA_CACHE_DIR=/tmp/numba {QC_PY} -I /p/e2p_oracle_gain.py qc-solve "
                      f"{small} /p/qc-selfcal/qc-round-{k} " + " ".join(qc_options(term, refant))
                      + f"; rc=$?; rm -rf {small}; exit $rc")  # fmt: skip
            rc = docker(r, FORMATS_IMAGE, [*inplace_mounts(ms, r), (QC_EXT4, "/q")], script,
                        f"qc-selfcal-round-{k}", 1)  # fmt: skip
            if rc != 0:
                res["rounds"].append({"round": k, "exit": rc, "pass": False})
                rc_all = rc
                continue
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        qg = np.load(out / "gains.npy")
        qg = np.stack([qg[..., 0], qg[..., 3]], -1)
        qf = np.load(out / "gain_flags.npy") != 0
        g, f, gt, _gf, _gs = cal_selfcal.read_store(x["store"], x["solve_name"])
        entry = {"round": k, "term": term, "shape_rang": list(g.shape),
                 "shape_qc": list(qg.shape), "qc_wall_s": summary.get("time_wall"),
                 "qc_max_rss_mb": summary.get("max_rss_mb"),
                 "conv_iter": summary.get("conv_iter"), "rang_flagged": int(f.sum()),
                 "qc_flagged": int(qf.sum()), "apply_flags_equal": x["apply_flags_equal"]}  # fmt: skip
        if g.shape != qg.shape:
            entry["pass"] = False
        else:
            entry.update(qc_products(g, f, qg, qf))
            qt = np.asarray(summary["gain_times"], float)
            same = len(qt) == len(gt) and np.max(np.abs(qt - gt)) <= 1e-6
            entry["gain_times_equal"] = bool(same)
            entry["pass"] = bool(entry["pass"] and same)
        res["rounds"].append(entry)
    write(r / "qc-selfcal.json", res)
    return rc_all


# --- gate 3c: WSClean 3.7 at the image stage's settings (E2-A, Stokes I) -------------

# gemclean arguments WSClean does not take, or that wsclean_argv sets itself
WS_FROM_GEMCLEAN = {"-name": 1, "-average-channels": 1, "-scans": 1, "-unit-weights": 0,
                    "-data-column": 1, "-j": 1}  # fmt: skip


def wsclean_argv(gem, *, name, column, threads, temp, ms_inside, dirty, nosi=False):
    """WSClean 3.7's command for the image stage's gemclean argv `gem` (the
    binary, its arguments, the MS): every argument WSClean shares is passed
    as it was; -name, -data-column, -j and the MS are this step's;
    -unit-weights is the matched state (unit-on-a); -average-channels has no
    WSClean counterpart (WSClean grids every channel); -scans is checked by
    the caller to select every row of the field. -gridder wgridder as E2-B's
    matched oracle; `dirty` sets -niter 0. Returns (argv, what was dropped)."""
    args = list(gem[gem.index("-name") : -1])
    kept, dropped = [], {}
    i = 0
    while i < len(args):
        n = WS_FROM_GEMCLEAN.get(args[i])
        if n is None:
            kept.append(args[i])
            i += 1
            continue
        dropped[args[i]] = args[i + 1 : i + 1 + n] if n else True
        i += 1 + n
    if dirty:
        j = kept.index("-niter")
        kept[j + 1] = "0"
    if "-gridder" not in kept:
        kept += ["-gridder", "wgridder"]
    out = ["wsclean", "-name", name, *kept, "-data-column", column, "-j", str(int(threads)),
           "-temp-dir", temp, *(["-no-small-inversion"] if nosi else []), ms_inside]  # fmt: skip
    return out, dropped


def ms_columns(ms):
    from rang import core_ms

    with core_ms.open_table(ms) as t:
        return list(t.colnames())


def unit_on_a(ms, r):
    """Gate 3c's matched state on the MS itself (E2-B's UNIT_PY: renames and
    a unit WEIGHT only): FLAG is rang's FLAG after apply (RANG_FLAG),
    WEIGHT_SPECTRUM renamed away and WEIGHT 1, as the image stage's
    -unit-weights (data.weights: uniform)."""
    return _unit_a(ms, r, "on")


def unit_off_a(ms, r):
    return _unit_a(ms, r, "off")


def _unit_a(ms, r, mode):
    ms, r = Path(ms), Path(r)
    if mode == "on" and "RANG_CORRECTED_DATA" not in ms_columns(ms):
        raise SystemExit("prep-inplace has not run")
    (r / "e2p_unit.py").write_text(UNIT_PY, encoding="utf-8")
    return docker(r, FORMATS_IMAGE, inplace_mounts(ms, r),
                  f"{QC_PY} -I /p/e2p_unit.py /c/{ms.name} {mode} /p/unit-{mode}-a.json",
                  f"unit-{mode}-a", 1)  # fmt: skip


def wsclean3c_a(ms, r, kind, threads, nosi=False):
    """Gate 3c's oracle image of rang's apply output (E2-A, 6.5): WSClean
    3.7 on RANG_CORRECTED_DATA in the matched state, with the image stage's
    own gemclean argv (R/rang-run/image/summary.json) translated by
    `wsclean_argv`; `kind` dirty (-niter 0) or clean. Without `nosi` as
    frozen; `nosi` (-no-small-inversion, E2-B's A4b) only under a later
    amendment, into its own directory. -> R/wsclean3c-a[-nosi]/"""
    from rang import core_ms

    ms, r = Path(ms), Path(r)
    if "E2_CASA_FLAG" not in ms_columns(ms):
        raise SystemExit("run unit-on-a first: WSClean reads FLAG and WEIGHT")
    s = json.loads((r / "rang-run" / "image" / "summary.json").read_text(encoding="utf-8"))
    (entry,) = s["images"]
    gem = entry["argv"]
    if "-scans" in gem:
        with core_ms.open_table(ms) as t:
            fids = np.asarray(t.getcol("FIELD_ID", 0, t.nrows))
            scan_ids = np.asarray(t.getcol("SCAN_NUMBER", 0, t.nrows))
        listed = {int(x) for x in gem[gem.index("-scans") + 1].split(",")}
        have = {int(x) for x in np.unique(scan_ids[fids == int(entry["field_id"])])}
        if not have <= listed:
            raise SystemExit(f"-scans {sorted(listed)} selects part of the field: {sorted(have)}")
    sub = "wsclean3c-a" + ("-nosi" if nosi else "")
    d = r / sub
    (d / "tmp").mkdir(parents=True, exist_ok=True)
    tag = entry["field"].replace("+", "p").replace("-", "m")
    argv, dropped = wsclean_argv(gem, name=f"/p/{sub}/{tag}-{kind}", column="RANG_CORRECTED_DATA",
                                 threads=threads, temp=f"/p/{sub}/tmp", ms_inside=f"/c/{ms.name}",
                                 dirty=kind == "dirty", nosi=nosi)  # fmt: skip
    t0 = time.perf_counter()
    rc = docker(r, WSCLEAN_IMAGE, inplace_mounts(ms, r), " ".join(argv),
                f"{sub}-{tag}-{kind}", int(threads))  # fmt: skip
    shutil.rmtree(d / "tmp", ignore_errors=True)
    fits_out = sorted(p.name for p in d.glob(f"{tag}-{kind}*.fits"))
    write(r / f"{sub}-{kind}-run.json",
          {"exit": rc, "argv": argv, "gemclean_argv": gem, "dropped": dropped,
           "seconds": time.perf_counter() - t0, "fits": fits_out})  # fmt: skip
    return rc


def wsclean3c_a_dirty(ms, r, threads="2", nosi=""):
    return wsclean3c_a(ms, r, "dirty", threads, nosi == "nosi")


def wsclean3c_a_clean(ms, r, threads="4", nosi=""):
    return wsclean3c_a(ms, r, "clean", threads, nosi == "nosi")


def wsclean3c_a_nosi_dirty(ms, r, threads="2"):
    """The coordinator's decision on 9.10: one -no-small-inversion dirty run,
    a second, seen reading, only after the primary reading is scored."""
    if not (Path(r) / "g3c-a.json").is_file():
        raise SystemExit("score3c-a has not run: the nosi reading follows the primary")
    return wsclean3c_a(ms, r, "dirty", threads, True)


def _score3c_a():
    spec = importlib.util.spec_from_file_location(
        "e2_score3c_a", Path(__file__).resolve().parent / "e2_score3c_a.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def score3c_a(ms, r):
    r = Path(r)
    return _score3c_a().main(r, r / "wsclean3c-a", r / "g3c-a.json")


def score3c_a_nosi(ms, r):
    r = Path(r)
    return _score3c_a().main(r, r / "wsclean3c-a-nosi", r / "g3c-a-nosi.json", "--dirty-only")


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
    from rang import core_ms, core_writeback

    ms, r = Path(ms), Path(r)
    with core_ms.open_table(ms) as t:
        held = [c for c in t.colnames() if c.startswith("E2_")]
    if held:  # gate 3c's matched state: WEIGHT is the unit column, FLAG is rang's
        raise SystemExit(f"{ms} holds {held}: run unit-off-a before restore")
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


def tricolour(ms, r, input_json, strategy, scans=None):
    """Gate 3a. `scans` (a comma list) runs Tricolour once per scan
    (`-sn`) and compares only those scans' rows -> R/g3a-scans.json: E2-A's
    target scan does not fit Tricolour's per-scan packing in WSL's memory
    (research/e2-acceptance.md 9.12)."""
    from rang.formats import flagversions

    ms, r = Path(ms), Path(r)
    only = [int(x) for x in scans.split(",")] if scans else None
    tag = "g3a-scans" if only else "g3a"
    g2a = json.loads((r / "g2a.json").read_text())
    if not g2a["met"]:
        raise SystemExit(
            "gate 2a not met: the MS is not as converted, Tricolour not run"
        )
    shutil.copy(strategy, r / "tricolour-strategy.yaml")
    base = "tricolour -c /p/tricolour-strategy.yaml -fs polarisation -dc DATA -dpm"
    if only is None:
        rc = docker(r, TRICOLOUR_IMAGE, [(ms.parent, "/ms"), (r, "/p")],
                    f"{base} /ms/{ms.name}", "tricolour", 16)  # fmt: skip
    else:
        rc = 0
        for sc in only:
            rc = rc or docker(r, TRICOLOUR_IMAGE, [(ms.parent, "/ms"), (r, "/p")],
                              f"{base} -nw 8 -sn {sc} /ms/{ms.name}", f"tricolour-scan{sc}", 8)  # fmt: skip
    out = {"tricolour_exit": rc, "scans": only}
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
                if only is not None:
                    keep = np.isin(s, only)
                    a, b, s = a[keep], b[keep], s[keep]
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
    write(r / f"{tag}.json", out)
    restore(ms, r, input_json, label=f"{tag}-restore")
    return 0


def tricolour_scans(ms, r, input_json, strategy, scans="9,11"):
    return tricolour(ms, r, input_json, strategy, scans)


STEPS = {"gate1": gate1, "archive": archive, "wcs": wcs, "casacore": casacore,
         "casa-ro": casa_ro, "wsclean0": wsclean0, "daskms": daskms, "wsclean3c": wsclean3c,
         "wsclean3c-unit": wsclean3c_unit, "copy": copy,
         "prep": prep, "applycal": applycal, "compare": compare, "snapshot": snapshot, "restore": restore,
         "tricolour": tricolour, "tricolour-scans": tricolour_scans,
         "columns-before": columns_before,
         "prep-inplace": prep_inplace, "applycal-inplace": applycal_inplace,
         "compare-inplace": compare_inplace, "snapshot-inplace": snapshot_inplace,
         "drop-corrected-inplace": drop_corrected_inplace, "qc-avg": qc_avg,
         "qc-selfcal": qc_selfcal, "unit-on-a": unit_on_a, "unit-off-a": unit_off_a,
         "wsclean3c-a-dirty": wsclean3c_a_dirty, "wsclean3c-a-clean": wsclean3c_a_clean,
         "score3c-a": score3c_a, "wsclean3c-a-nosi-dirty": wsclean3c_a_nosi_dirty,
         "score3c-a-nosi": score3c_a_nosi}  # fmt: skip


def main(argv):
    step, ms, r, *rest = argv
    Path(r).mkdir(parents=True, exist_ok=True)
    log(r, f"step {step} {ms} {rest}")
    return STEPS[step](ms, r, *rest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
