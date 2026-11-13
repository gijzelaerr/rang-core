"""E2-B's 3C 286 transfer and 1934-638 leakage rows, CASA's arm
(research/e2-acceptance.md 6.5, 7.1), CASA 6.7.6.14 in `rang-o-casa`.

    python e2_casa_xfer.py dev DEV_MS DEV_RUN VERSION RD
        copy DEV_MS (and its flag versions) to RD/casa/; on the copy, rang's
        columns renamed (RANG_*), FLAG from flag version VERSION (rang's
        development FLAG after calibrate, `e2_devtables.py`), RECEPTOR_ANGLE
        -90 (`e2_post.py` PREP_PY); then e2_casa3b.py's calls without the
        secondary and without the applycal steps -> RD/casa/tables/
    python e2_casa_xfer.py rows R RD CASE
        on R/casa/e2b.ms (FLAG restored from rang's flag-stage version first,
        as the rang arm), CASE xfer17, leak18p or leak18ap as e2_transfer.py:
        gaincal of the per-scan G with RD's K, G, B (xfer17, leak18p: p, 60 s,
        parang true; leak18ap: ap, inf, RD's K), then applycal of RD's K, G
        (or the scan's ap G), B, the scan's G, Kcross, Xf, Df with parang true
        to that field and scan -> CORRECTED_DATA, tables in R/casa/xfer/.
"""

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "research" / "results" / "e2-average-time"))

import e2_casa3b as C3
import e2_post as P

LIN, NEAR = "linear", "nearest"


def dev(dev_ms, dev_run, version, rd):
    dev_ms, rd = Path(dev_ms), Path(rd)
    d = rd / "casa"
    d.mkdir(parents=True, exist_ok=True)
    for src in (dev_ms, Path(str(dev_ms) + ".flagversions")):
        dst = d / src.name
        if not dst.exists():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("table.lock"))
    (rd / "e2p_prep.py").write_text(P.PREP_PY, encoding="utf-8")
    rc = P.docker(rd, P.FORMATS_IMAGE, P.prep_mounts(rd),
                  f"{P.QC_PY} -I /p/e2p_prep.py /c/{dev_ms.name} {version} /p/prep.json",
                  "prep")  # fmt: skip
    if rc:
        return rc
    s = json.loads((Path(dev_run) / "calibrate" / "summary.json").read_text())
    refant = ",".join(s["refant_auto"]["names"])
    calls = [c for c in C3.casa_calls(f"/c/{dev_ms.name}", refant)
             if c["task"] != "applycal" and c["args"].get("field") != C3.GCAL
             and not any(str(v).endswith(("/Gsec", "/Gapp", "/F"))
                         for v in c["args"].values())]  # fmt: skip
    P.write(rd / "casa3b-spec.json", calls)
    shutil.rmtree(d / "tables", ignore_errors=True)
    (d / "tables").mkdir()
    rc = P.docker(rd, P.CASA_IMAGE, P.prep_mounts(rd) + [(ROOT / "examples", "/ex")],
                  "/opt/casa/bin/python -I /ex/oracle_pol.py tasks /p/casa3b-spec.json "
                  "/p/casa3b-tasks.json", "casa-dev")  # fmt: skip
    tasks = json.loads((rd / "casa3b-tasks.json").read_text())
    errors = [(t["task"], t["error"]) for t in tasks if t["error"]]
    P.log(rd, f"casa-dev tasks {len(tasks)} errors {errors}")
    return rc or (3 if errors else 0)


def rows(r, rd, case):
    from rang import core_writeback

    r, rd = Path(r), Path(rd)
    ms = r / "casa" / "e2b.ms"
    st = json.loads((r / "rang-run-moved" / "state.json").read_text())
    version = st["stages"]["calibrate"]["flag_version"]
    restored = int(core_writeback.restore_flags(ms, version))
    s = json.loads((r / "rang-run-moved" / "calibrate" / "summary.json").read_text())
    refant = ",".join(s["refant_auto"]["names"])
    t, x = "/d", "/p/casa/xfer"
    (r / "casa" / "xfer").mkdir(parents=True, exist_ok=True)
    shutil.rmtree(r / "casa" / "xfer" / case, ignore_errors=True)
    common = {"vis": "/c/e2b.ms", "refant": refant, "minsnr": 3.0, "minblperant": 4,
              "refantmode": "flex", "uvrange": ">150"}  # fmt: skip
    if case in ("xfer17", "leak18p"):
        field, scan = (C3.XCAL, "17") if case == "xfer17" else (C3.FCAL, "18")
        solve = {"task": "gaincal", "args": {**common, "caltable": f"{x}/{case}",
                 "field": field, "scan": scan, "gaintype": "G", "calmode": "p",
                 "solint": "60s", "combine": "", "parang": True,
                 "gaintable": [f"{t}/K", f"{t}/G", f"{t}/B"], "interp": [LIN] * 3}}  # fmt: skip
        tabs = [
            f"{t}/K",
            f"{t}/G",
            f"{t}/B",
            f"{x}/{case}",
            f"{t}/Kcross",
            f"{t}/Xf",
            f"{t}/Df",
        ]
        interp = [LIN] * 4 + [NEAR] * 3
    else:
        field, scan = C3.FCAL, "18"
        solve = {"task": "gaincal", "args": {**common, "caltable": f"{x}/{case}",
                 "field": field, "scan": scan, "gaintype": "G", "calmode": "ap",
                 "solint": "inf", "combine": "", "parang": False,
                 "gaintable": [f"{t}/K"], "interp": [LIN]}}  # fmt: skip
        tabs = [f"{t}/K", f"{x}/{case}", f"{t}/B", f"{t}/Kcross", f"{t}/Xf", f"{t}/Df"]
        interp = [LIN] * 3 + [NEAR] * 3
    applyc = {"task": "applycal", "args": {"vis": "/c/e2b.ms", "field": field, "scan": scan,
              "gaintable": tabs, "interp": interp, "gainfield": [""] * len(tabs),
              "calwt": [False] * len(tabs), "parang": True, "applymode": "calflag",
              "flagbackup": False}}  # fmt: skip
    spec = r / f"casa-{case}-spec.json"
    P.write(spec, [solve, applyc])
    rc = P.docker(r, P.CASA_IMAGE, P.prep_mounts(r) + [(ROOT / "examples", "/ex"),
                                                      (rd / "casa" / "tables", "/d")],
                  f"/opt/casa/bin/python -I /ex/oracle_pol.py tasks /p/{spec.name} "
                  f"/p/casa-{case}-tasks.json", f"casa-{case}")  # fmt: skip
    tasks = json.loads((r / f"casa-{case}-tasks.json").read_text())
    errors = [(k["task"], k["error"]) for k in tasks if k["error"]]
    P.write(r / f"casa-{case}.json", {"case": case, "flag_version": version,
                                       "restored_rows": restored, "errors": errors,
                                       "exit": rc})  # fmt: skip
    return rc or (3 if errors else 0)


def main(argv):
    mode, *rest = argv
    if mode == "dev":
        return dev(*rest[:4])
    return rows(*rest[:3])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
