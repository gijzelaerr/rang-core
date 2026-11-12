"""E2-B gate 3b's CASA arm (research/e2-acceptance.md 6.5): CARACal's
full-Stokes sequence in CASA 6.7.6.14 on the copy `e2_post.py copy` made
(R/casa/), carrying rang's FLAG after its calibrate stage (`e2_post.py prep`
restores it after gate 2b's applycal), RECEPTOR_ANGLE -90, rang's refant
list (refantmode flex) and the same models.

    python e2_casa3b.py spec MSNAME R     the task list           -> R/casa3b-spec.json
    python e2_casa3b.py run MSNAME R      prep again, then the tasks -> R/casa/tables/

The calls are e2avg_luno.py's (the averaging validation's, run against the
same e2b.yaml shape on LUNO scans 1-2) plus the secondary as e1b_casa.py
(Gsec; G copied and appended on the secondary with smodel [1,0,0,0]; then
fluxscale to F) and e2b.yaml's apply targets. Not run, as the input already
holds rang's flags after calibrate: CASA's own `flagdata(mode='extend')`
(rang's extend flags are in FLAG, so K, G and B see them too, which rang's
own K, G and B did not) and the A step (no CASA counterpart; its flags are
in FLAG, so F solves on rang's cells). CASA pre-averages in time and
frequency itself; `average_time` and `average_freq` do not apply.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "research" / "results" / "e2-average-time"))

import e2_post as P

FCAL, XCAL, GCAL = "J1939-6342", "J1331+3030", "J1833-2103"
UVRANGE = ">150"
LIN, NEAR = "linear", "nearest"
# CARACal's nrao_xcal.yml 3C286 (rang.calmodels.NRAO_XCAL), setjy manual.
X286 = {"fluxdensity": [14.7172, 0.0, 0.0, 0.0], "spix": [-0.4507, -0.1798, 0.0357],
        "reffreq": "1.47GHz", "polindex": [0.098], "polangle": [0.575959],
        "rotmeas": 0.0}  # fmt: skip
# e2b.yaml apply targets: field, tables, interp, gainfield.
APPLY = [
    (GCAL, ["K", "F", "B", "Kcross", "Xf", "Df"], [LIN] * 3 + [NEAR] * 3,
     [FCAL, GCAL, FCAL, "", "", ""]),
    (FCAL, ["K", "G", "B", "Gpol", "Kcross", "Xf", "Df"], [LIN] * 4 + [NEAR] * 3, [""] * 7),
    (XCAL, ["K", "G", "B", "Gpol", "Kcross", "Xf", "Df"], [LIN] * 4 + [NEAR] * 3, [""] * 7),
]  # fmt: skip


def casa_calls(ms, refant):
    t = "/p/casa/tables"
    common = {"vis": ms, "refant": refant, "minsnr": 3.0, "minblperant": 4}
    mode = {"refantmode": "flex"}
    cc = [f"{t}/K", f"{t}/G", f"{t}/B"]
    calls = [
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
    for field, names, interp, gainfield in APPLY:
        calls.append({"task": "applycal", "args": {
            "vis": ms, "field": field, "gaintable": [f"{t}/{n}" for n in names],
            "interp": interp, "gainfield": gainfield, "calwt": [False] * len(names),
            "parang": True, "applymode": "calflag", "flagbackup": False}})  # fmt: skip
    return calls


def refant_names(r):
    s = json.loads((Path(r) / "rang-run" / "calibrate" / "summary.json").read_text())
    return ",".join(s["refant_auto"]["names"])


def spec(msname, r, fields=None):
    calls = casa_calls(f"/c/{msname}", refant_names(r))
    if fields is not None and GCAL not in fields:  # development: no secondary in the MS
        sec = ("/Gsec", "/Gapp", "/F")
        calls = [c for c in calls if c["args"].get("field") != GCAL
                 and not any(str(v).endswith(sec) for v in c["args"].values())]  # fmt: skip
    P.write(Path(r) / "casa3b-spec.json", calls)
    return 0


def run(msname, r):
    r = Path(r)
    rc = P.prep(
        r / "casa" / msname, r
    )  # FLAG after calibrate again, idempotent renames
    if rc:
        return rc
    (r / "casa" / "tables").mkdir(exist_ok=True)
    rc = P.docker(r, P.CASA_IMAGE, P.prep_mounts(r) + [(ROOT / "examples", "/ex")],
                  "/opt/casa/bin/python -I /ex/oracle_pol.py tasks /p/casa3b-spec.json "
                  "/p/casa3b-tasks.json", "casa3b")  # fmt: skip
    tasks = json.loads((r / "casa3b-tasks.json").read_text())
    errors = [(t["task"], t["error"]) for t in tasks if t["error"]]
    P.log(r, f"casa3b tasks {len(tasks)} errors {errors}")
    return rc or (3 if errors else 0)


def main(argv):
    step, msname, r, *rest = argv
    if step == "spec":
        return spec(msname, r, json.loads(rest[0]) if rest else None)
    return run(msname, r)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
