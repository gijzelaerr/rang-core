"""E2-A gate 3b's CASA arm (research/e2-acceptance.md 6.5, 9.11): CARACal's
KGB, KGB sequence in CASA 6.7.6.14 on the primaries (no A step: it has no CASA
counterpart), on the leg's MS itself after `restore` (no copy, 9.6), with
FLAG and FLAG_ROW set from rang's FLAG after calibrate (the flag version
rang's apply saved before its first write, after the A step), RECEPTOR_ANGLE
-90 as stored, rang's refant list (refantmode flex) and the same model
(setjy Stevens-Reynolds 2016). The calls are E2-B's (e2_casa3b.py: K without
uvrange, uvrange >150 on G and B, minsnr 3, minblperant 4) with e2a.yaml's
terms: K0 inf; G0 ap inf (K0); B0 inf, combine scan, fillgaps 70, solnorm
false (K0, G0); K1 60s (G0, B0); G1 ap 60s (K1, B0); B1 as B0 (K1, G1).
setjy runs with usescratch false (a virtual model: no 128 GiB MODEL_DATA
written over 9p, 9.20 of e2b-misses).

    python e2_casa3b_a.py spec MS R     the task list            -> R/casa3b-a-spec.json
    python e2_casa3b_a.py prep MS R     FLAG from rang's after-calibrate version (native)
    python e2_casa3b_a.py run MS R      the tasks                 -> R/casa/tables/
"""

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

import e2_post as P

FCAL = "J1939-6342"
UVRANGE = ">150"
LIN = "linear"
TERMS = ("K0", "G0", "B0", "K1", "G1", "B1")


def casa_calls(ms, refant):
    t = "/p/casa/tables"
    common = {"vis": ms, "field": FCAL, "refant": refant, "minsnr": 3.0, "minblperant": 4,
              "parang": False}  # fmt: skip
    flex = {"refantmode": "flex"}

    def gk(name, solint, pre):
        return {"task": "gaincal", "args": {**common, **flex, "caltable": f"{t}/{name}",
                "gaintype": "K", "solint": solint, "combine": "",
                "gaintable": [f"{t}/{p}" for p in pre], "interp": [LIN] * len(pre)}}  # fmt: skip

    def gg(name, solint, pre):
        return {"task": "gaincal", "args": {**common, **flex, "caltable": f"{t}/{name}",
                "gaintype": "G", "calmode": "ap", "solint": solint, "combine": "",
                "uvrange": UVRANGE, "gaintable": [f"{t}/{p}" for p in pre],
                "interp": [LIN] * len(pre)}}  # fmt: skip

    def bb(name, pre):
        return {"task": "bandpass", "args": {**common, "caltable": f"{t}/{name}",
                "bandtype": "B", "solint": "inf", "combine": "scan", "solnorm": False,
                "fillgaps": 70, "uvrange": UVRANGE, "gaintable": [f"{t}/{p}" for p in pre],
                "interp": [LIN] * len(pre)}}  # fmt: skip

    return [
        {"task": "setjy", "args": {"vis": ms, "field": FCAL, "standard": "Stevens-Reynolds 2016",
         "scalebychan": True, "usescratch": False}},
        gk("K0", "inf", []), gg("G0", "inf", ["K0"]), bb("B0", ["K0", "G0"]),
        gk("K1", "60s", ["G0", "B0"]), gg("G1", "60s", ["K1", "B0"]), bb("B1", ["K1", "G1"]),
    ]  # fmt: skip


def refant_names(r):
    s = json.loads((Path(r) / "rang-run" / "calibrate" / "summary.json").read_text())
    return ",".join(s["refant_auto"]["names"])


def after_calibrate_version(r):
    """The flag version rang's apply saved before writing: FLAG after calibrate."""
    return json.loads((Path(r) / "rang-run" / "apply" / "summary.json").read_text())["flag_version"]


def spec(ms, r):
    calls = casa_calls(f"/c/{Path(ms).name}", refant_names(r))
    P.write(Path(r) / "casa3b-a-spec.json", calls)
    return 0


def prep(ms, r):
    from rang import core_writeback

    ms, r = Path(ms), Path(r)
    held = [c for c in P.ms_columns(ms) if c.startswith(("RANG_", "E2_"))]
    if held or P.run_dir(ms).exists():
        raise SystemExit(f"restore has not run on {ms}: {held}")
    version = after_calibrate_version(r)
    rows = core_writeback.restore_flags(ms, version)
    P.write(r / "casa3b-a-prep.json", {"flag_version": version, "rows": rows,
                                       "hash": P.flag_hash(ms)})  # fmt: skip
    return 0


def run(ms, r):
    ms, r = Path(ms), Path(r)
    if not (r / "casa3b-a-prep.json").is_file():
        raise SystemExit("prep has not run")
    spec(ms, r)
    shutil.rmtree(r / "casa" / "tables", ignore_errors=True)
    (r / "casa" / "tables").mkdir(parents=True)
    rc = P.docker(r, P.CASA_IMAGE, [*P.inplace_mounts(ms, r), (ROOT / "examples", "/ex")],
                  "/opt/casa/bin/python -I /ex/oracle_pol.py tasks /p/casa3b-a-spec.json "
                  "/p/casa3b-a-tasks.json", "casa3b-a", 4)  # fmt: skip
    tasks = json.loads((r / "casa3b-a-tasks.json").read_text())
    errors = [(t["task"], t["error"]) for t in tasks if t["error"]]
    P.log(r, f"casa3b-a tasks {len(tasks)} errors {errors}")
    return rc or (3 if errors else 0)


if __name__ == "__main__":
    step, ms, r = sys.argv[1:4]
    sys.exit({"spec": spec, "prep": prep, "run": run}[step](ms, r))
