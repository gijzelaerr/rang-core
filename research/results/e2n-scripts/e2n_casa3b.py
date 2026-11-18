"""E2-N gate 3b's CASA arm and the oracle's corrected data (research/e2n-native.md
section 6): CARACal's full-Stokes sequence in CASA 6.7.6.14, E2-B's calls
(`e2_casa3b.py`) with E2-N's fields, run in place on the leg's MS after
`restore` as E2-A's (`e2_casa3b_a.py`): FLAG from rang's FLAG after calibrate,
RECEPTOR_ANGLE -90 as mvftoms wrote it, rang's refant list (refantmode flex),
setjy with usescratch true (E2-B's calls: MODEL_DATA written; nash has no 9p, amendment 3).
Then CASA applycal of CASA's tables with e2n.yaml's apply entries into a
CORRECTED_DATA that `corr-prep` creates natively (a copy of DATA), for the
rows (3C 286 parity, J1744-5144, J0408-6545 leakage) and the target oracle.

    python e2n_casa3b.py spec MS R        the solve list            -> R/casa3b-n-spec.json
    python e2n_casa3b.py prep MS R        FLAG from rang's after-calibrate version (native)
    python e2n_casa3b.py run MS R         the solves                -> R/casa/tables/
    python e2n_casa3b.py corr-prep MS R   CORRECTED_DATA = DATA, natively
    python e2n_casa3b.py applycal MS R    CASA applycal, every entry -> R/casa-applycal-*.json
"""

import json
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "research" / "results" / "e2-acceptance-scripts"))

import e2_post as P

# E2-N's fields; the E2N_* variables map them for the development dry run only.
FCAL = os.environ.get("E2N_FCAL", "J1939-6342")
XCAL = os.environ.get("E2N_XCAL", "J1331+3030")
GCAL = os.environ.get("E2N_GCAL", "J1744-5144")
TARGET = os.environ.get("E2N_TARGET", "ASKAPJ1745")
LEAK = os.environ.get("E2N_LEAK", "J0408-6545")
UVRANGE = ">150"
LIN, NEAR = "linear", "nearest"
X286 = {"fluxdensity": [14.7172, 0.0, 0.0, 0.0], "spix": [-0.4507, -0.1798, 0.0357],
        "reffreq": "1.47GHz", "polindex": [0.098], "polangle": [0.575959],
        "rotmeas": 0.0}  # fmt: skip
# e2n.yaml's apply entries: field, tables, interp, gainfield.
APPLY = [
    (",".join(f for f in (GCAL, TARGET, LEAK) if f not in (FCAL, XCAL)), ["K", "F", "B", "Kcross", "Xf", "Df"],
     [LIN] * 3 + [NEAR] * 3, [FCAL, GCAL, FCAL, "", "", ""]),
    (f"{FCAL},{XCAL}", ["K", "G", "B", "Gpol", "Kcross", "Xf", "Df"],
     [LIN] * 4 + [NEAR] * 3, [""] * 7),
]  # fmt: skip


def casa_calls(ms, refant):
    t = "/p/casa/tables"
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
        {"task": "gaincal", "args": {**common, **mode, "caltable": f"{t}/Gsec", "field": GCAL,
         "gaintype": "G", "calmode": "ap", "solint": "inf", "combine": "", "parang": False,
         "uvrange": UVRANGE, "gaintable": [f"{t}/K", f"{t}/B"], "interp": [LIN, LIN],
         "gainfield": [FCAL, FCAL]}},
        {"task": "copytree", "args": {"src": f"{t}/G", "dst": f"{t}/Gapp"}},
        {"task": "gaincal", "args": {**common, **mode, "caltable": f"{t}/Gapp", "field": GCAL,
         "gaintype": "G", "calmode": "ap", "solint": "inf", "combine": "", "parang": False,
         "uvrange": UVRANGE, "append": True, "smodel": [1.0, 0.0, 0.0, 0.0],
         "gaintable": [f"{t}/K", f"{t}/B"], "interp": [LIN, LIN], "gainfield": [FCAL, FCAL]}},
        {"task": "fluxscale", "args": {"vis": ms, "caltable": f"{t}/Gapp",
         "fluxtable": f"{t}/F", "reference": FCAL, "transfer": ""}},
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


def applycal_calls(ms):
    t = "/p/casa/tables"
    return [{"vis": ms, "field": field, "gaintable": [f"{t}/{n}" for n in names],
             "interp": interp, "gainfield": gainfield, "calwt": [False] * len(names),
             "parang": True, "applymode": "calflag", "flagbackup": False}
            for field, names, interp, gainfield in APPLY]  # fmt: skip


def refant_names(r):
    s = json.loads((Path(r) / "rang-run" / "calibrate" / "summary.json").read_text())
    return ",".join(s["refant_auto"]["names"])


def after_calibrate_version(r):
    """The flag version rang's apply saved before writing: FLAG after calibrate."""
    return json.loads((Path(r) / "rang-run" / "apply" / "summary.json").read_text())[
        "flag_version"
    ]


def spec(ms, r):
    P.write(
        Path(r) / "casa3b-n-spec.json",
        casa_calls(f"/c/{Path(ms).name}", refant_names(r)),
    )
    return 0


def restored_only(ms):
    held = [c for c in P.ms_columns(ms) if c.startswith(("RANG_", "E2_"))]
    if held or P.run_dir(ms).exists():
        raise SystemExit(f"restore has not run on {ms}: {held}")


def prep(ms, r):
    from rang import core_writeback

    ms, r = Path(ms), Path(r)
    restored_only(ms)
    version = after_calibrate_version(r)
    rows = core_writeback.restore_flags(ms, version)
    P.write(r / "casa3b-n-prep.json", {"flag_version": version, "rows": rows,
                                       "hash": P.flag_hash(ms)})  # fmt: skip
    return 0


def run(ms, r):
    ms, r = Path(ms), Path(r)
    if not (r / "casa3b-n-prep.json").is_file():
        raise SystemExit("prep has not run")
    spec(ms, r)
    shutil.rmtree(r / "casa" / "tables", ignore_errors=True)
    (r / "casa" / "tables").mkdir(parents=True)
    rc = P.docker(r, P.CASA_IMAGE, [*P.inplace_mounts(ms, r), (ROOT / "examples", "/ex")],
                  "/opt/casa/bin/python -I /ex/oracle_pol.py tasks /p/casa3b-n-spec.json "
                  "/p/casa3b-n-tasks.json", "casa3b-n", 4)  # fmt: skip
    tasks = json.loads((r / "casa3b-n-tasks.json").read_text())
    errors = [(t["task"], t["error"]) for t in tasks if t["error"]]
    P.log(r, f"casa3b-n tasks {len(tasks)} errors {errors}")
    return rc or (3 if errors else 0)


def corr_prep(ms, r):
    from rang import core_writeback

    ms, r = Path(ms), Path(r)
    if not (r / "casa" / "tables" / "Df").is_dir():
        raise SystemExit("run has not written CASA's tables")
    t0 = time.perf_counter()
    with core_writeback.WriteBack(ms, stage="e2n-oracle") as w:
        added = w.ensure_column("CORRECTED_DATA", init="data")
    P.write(r / "casa-corr-prep.json", {"column_added": added,
                                        "seconds": time.perf_counter() - t0})  # fmt: skip
    return 0


def applycal(ms, r):
    ms, r = Path(ms), Path(r)
    if not (r / "casa-corr-prep.json").is_file():
        raise SystemExit("corr-prep has not run")
    P.write(r / "casa-applycal-spec.json", applycal_calls(f"/c/{ms.name}"))
    (r / "e2p_applycal.py").write_text(P.APPLY_PY, encoding="utf-8")
    rc = P.docker(r, P.CASA_IMAGE, P.inplace_mounts(ms, r),
                    "/opt/casa/bin/python -I /p/e2p_applycal.py /p/casa-applycal-spec.json "
                    "/p/casa-applycal-result.json", "casa-applycal", 2)  # fmt: skip
    # e2_rows_a.py's target-unit-on reads its applycal record under this name;
    # the target is one of this call's fields.
    res = r / "casa-applycal-result.json"
    if res.is_file():
        shutil.copy(res, r / "target-applycal-result.json")
    return rc


if __name__ == "__main__":
    step, ms, r = sys.argv[1:4]
    sys.exit({"spec": spec, "prep": prep, "run": run, "corr-prep": corr_prep,
              "applycal": applycal}[step](ms, r))  # fmt: skip
