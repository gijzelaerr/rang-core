"""Arm A3's CASA task lists (research/e2b-misses.md 9.23); imports no `rang`.

    python a3_spec.py OUT_DIR     writes OUT_DIR/{L,S,Xprep,X}/spec.json

Container paths: /w the WSL ext4 work directory, /p the result directory on
D:, /d D:\\rang read only."""

import json
import sys
from pathlib import Path

XCAL = "J1331+3030"
REFANT = "m022,m023,m024"
# CARACal's nrao_xcal.yml 3C286, as e2_casa3b.X286.
X286 = {"fluxdensity": [14.7172, 0.0, 0.0, 0.0], "spix": [-0.4507, -0.1798, 0.0357],
        "reffreq": "1.47GHz", "polindex": [0.098], "polangle": [0.575959],
        "rotmeas": 0.0}  # fmt: skip
# The simulation's point: X286 without its polarisation.
POINT = {"fluxdensity": [14.7172, 0.0, 0.0, 0.0], "spix": [-0.4507, -0.1798, 0.0357],
         "reffreq": "1.47GHz"}  # fmt: skip
SIM = {"seed": 20261115, "sigma": 0.3, "flux": 1.5, "freq0": 1.284e9, "index": -1.0,
       "lm_arcsec": [-1.6, -2.0], "drift_rad": 0.2, "drift_period_s": 600.0}  # fmt: skip
VERSION = "/d/outputs/e2-20261111-20-e2b/casa/e2b.ms.flagversions/flags.rang_apply_20261112T013707Z"


def setjy(vis, model):
    return {"task": "setjy", "args": {"vis": vis, "field": XCAL, "standard": "manual",
            **model, "scalebychan": True, "usescratch": True}}  # fmt: skip


def gpol(vis, caltable, tables):
    args = {"vis": vis, "refant": REFANT, "minsnr": 3.0, "minblperant": 4,
            "refantmode": "flex", "caltable": caltable, "field": XCAL, "gaintype": "G",
            "calmode": "p", "solint": "60s", "combine": "", "parang": True,
            "uvrange": ">150"}  # fmt: skip
    if tables:
        args.update(gaintable=tables, interp=["linear"] * len(tables))
    return {"task": "gaincal", "args": args}


def kgb(d):
    return [f"/w/tabs/{d}/{n}" for n in ("K", "G", "B")]


def specs():
    lv, sv, spv, xv = "/w/L/luno.ms", "/w/S/sim.ms", "/w/S/simpt.ms", "/w/x17.ms"
    return {
        "L": [
            {"logfile": "/w/L/casa.log"},
            {"task": "copytree", "args": {"src": "/w/luno0.ms", "dst": lv}},
            {"task": "receptor", "args": {"vis": lv, "deg": -90.0}},
            setjy(lv, X286),
            {
                "task": "model_rows",
                "args": {
                    "vis": lv,
                    "rows": [0, 7777, 19999],
                    "out": "/p/L/casa-model.npy",
                },
            },
            gpol(lv, "/w/L/Gpol", kgb("luno")),
        ],
        "S": [
            {"logfile": "/w/S/casa.log"},
            {"task": "copytree", "args": {"src": "/w/luno0.ms", "dst": sv}},
            {"task": "reset", "args": {"vis": sv}},
            {"task": "receptor", "args": {"vis": sv, "deg": -90.0}},
            setjy(sv, POINT),
            {"task": "simulate", "args": {"vis": sv, **SIM, "truth": "/p/S/truth.npz"}},
            gpol(sv, "/w/S/Gpol-res", []),
            {"task": "copytree", "args": {"src": sv, "dst": spv}},
            {"task": "swap", "args": {"vis": spv}},
            gpol(spv, "/w/S/Gpol-pt", []),
        ],
        "Xprep": [
            {"logfile": "/w/X/casa-prep.log"},
            {"task": "putflags", "args": {"vis": xv, "version": VERSION, "first": 0}},
        ],
        "X": [
            {"logfile": "/w/X/casa.log"},
            {"task": "receptor", "args": {"vis": xv, "deg": -90.0}},
            setjy(xv, X286),
            {
                "task": "model_rows",
                "args": {
                    "vis": xv,
                    "rows": [0, 60000, 118103],
                    "out": "/p/X/casa-model.npy",
                },
            },
            gpol(xv, "/w/X/Gpol-CC", kgb("cc")),
            gpol(xv, "/w/X/Gpol-CM", kgb("cm")),
            gpol(xv, "/w/X/Gpol-CR", kgb("cr")),
        ],
    }


def main(out):
    out = Path(out)
    for name, calls in specs().items():
        (out / name).mkdir(parents=True, exist_ok=True)
        (out / name / "spec.json").write_text(json.dumps(calls, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
