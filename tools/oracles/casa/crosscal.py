"""CARACal's crosscal sequence for one calibrator, issued by hand in CASA 6.7.6.

Runs in the O-CASA image's CASA venv (/opt/casa/bin/python). The calls and
parameters follow caracal-pipeline/caracal 8f7bb363 `crosscal_worker.py` with
its schema defaults for a set whose only calibrator is PKS 1934-638 (the
`no_secondary` branch); see research/o-casa.md for the line-by-line mapping.

Usage (inside the container, cwd /run):
  crosscal.py solve <arm> <ms>     setjy (unless the arm keeps the stored model), K, G, B
  crosscal.py apply <arm> <ms>     applycal with CARACal's apply settings
  crosscal.py flagdata <mode> <ms> tfcrop with CARACal's flag-worker defaults, or rflag (CASA defaults)
  crosscal.py setjy <standard> <ms> a named CASA flux standard (FS1 side output)
Each call writes /run/casa/<name>.json with the parameters, return values and seconds.
"""

import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from casatasks import applycal, bandpass, flagdata, gaincal, setjy
from casatools import table

OUT = Path("/run/casa")
CARACAL_COMMIT = "8f7bb363876f5f0daecbf2167c36bb597c7e5160"
# caracal/data/southern_calibrators.txt: "name=PKS1934-63 epoch=1994 ... a=-30.7667
# b=26.4908 c=-7.0977 d=0.605334" (log10 S [Jy] against log10 nu [MHz]).
REYNOLDS_1994_MHZ = (-30.7667, 26.4908, -7.0977, 0.605334)
# obsconf schema defaults: refant auto, maxdist 1000 m, minbase 150 m.
MAXDIST, MINBASE = 1000.0, 150.0
# MeerKAT array reference position (geodetic WGS84), the centre for maxdist.
CENTRE_DEG = (-30.71106, 21.44389, 1086.6)
ARMS = {
    # name: (minblperant or None for CASA's default, run setjy, G/B uvrange,
    #        refant or None for CARACal's auto rule)
    "a": (None, True, ">50", None),  # CARACal's defaults (frozen)
    "b": (3, True, ">50", None),  # frozen deviation: minblperant=3
    # Post-hoc after the smoke (research/o-casa.md, amendment): the auto rule
    # returns no antenna (all baselines < 150 m) and K needs a refant; the four
    # core stations have baselines of 29-74 m, so uvrange '>50' leaves three.
    "d": (None, True, ">50", "m000"),  # CARACal's defaults with refant set by hand
    "c": (3, True, "", "m000"),  # the baseline arm
    "ch": (3, True, "", "m000"),
    "sh": (3, False, "", "m000"),
}


def dump(name, payload):
    OUT.mkdir(exist_ok=True)

    def default(value):
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        return str(value)

    (OUT / f"{name}.json").write_text(
        json.dumps(payload, indent=1, sort_keys=True, default=default) + "\n"
    )


def timed(log, label, task, **params):
    started = time.perf_counter()
    entry = {"task": type(task).__name__.lstrip("_"), "params": params}
    try:
        entry["returned"] = task(**params)
        entry["ok"] = True
    except Exception as error:  # noqa: BLE001 - every CASA failure is recorded
        entry["ok"] = False
        entry["error"] = f"{type(error).__name__}: {error}"
    entry["seconds"] = time.perf_counter() - started
    log[label] = entry
    return entry


def caracal_manual_model():
    """catalog_parser.convert_pb_to_casaspi, reimplemented from its docstring."""
    from scipy.optimize import curve_fit

    a, b, c, d = REYNOLDS_1994_MHZ
    k = math.log10(1000.0)
    ag = a + b * k + c * k**2 + d * k**3
    bg = b + 2 * c * k + 3 * d * k**2
    cg = c + 3 * d * k
    dg = d

    def pb(v):
        lv = np.log10(v)
        return 10 ** (ag + bg * lv + cg * lv**2 + dg * lv**3)

    v0 = 1.4
    flux = float(pb(v0))

    def casaspi(v, a1, b1, c1, d1):
        x = np.log10(v / v0)
        return flux * (v / v0) ** (a1 + b1 * x + c1 * x**2 + d1 * x**3)

    v = np.linspace(0.8, 1.8, 10000)
    popt, pcov = curve_fit(casaspi, v, pb(v))
    perr = np.sqrt(np.diag(pcov))
    return {
        "ghz_coefficients": [ag, bg, cg, dg],
        "fluxdensity": flux,
        "spix": [float(x) for x in popt],
        "spix_stderr": [float(x) for x in perr],
        "fit_ok": bool(np.all(perr < 1e-6)),
        "reffreq": f"{v0:f}GHz",
    }


def ecef(lat_deg, lon_deg, height):
    a, f = 6378137.0, 1 / 298.257223563
    e2 = f * (2 - f)
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    n = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)
    return np.array(
        [
            (n + height) * math.cos(lat) * math.cos(lon),
            (n + height) * math.cos(lat) * math.sin(lon),
            (n * (1 - e2) + height) * math.sin(lat),
        ]
    )


def ms_info(ms):
    tb = table()
    tb.open(f"{ms}/FIELD")
    all_fields = list(tb.getcol("NAME"))
    tb.close()
    tb.open(f"{ms}/ANTENNA")
    names = list(tb.getcol("NAME"))
    positions = tb.getcol("POSITION").T
    tb.close()
    tb.open(ms)
    # The FIELD subtable is copied whole; the observed field is MAIN's FIELD_ID.
    fields = [all_fields[i] for i in np.unique(tb.getcol("FIELD_ID"))]
    flag = tb.getcol("FLAG")  # (corr, chan, row)
    a1, a2 = tb.getcol("ANTENNA1"), tb.getcol("ANTENNA2")
    uvw = tb.getcol("UVW").T
    tb.close()
    return fields, names, positions, flag, a1, a2, uvw


def caracal_refant(names, positions, flag, a1, a2):
    """manage_antennas.get_refant: core antennas, all baselines >= minbase, by flags."""
    centre = ecef(*CENTRE_DEG)
    rows = flag.all(axis=(0, 1))
    stats = {}
    for i, name in enumerate(names):
        mine = (a1 == i) | (a2 == i)
        frac = float(flag[..., mine].mean()) if mine.any() else 1.0
        dist = float(np.linalg.norm(positions[i] - centre))
        bases = [
            float(np.linalg.norm(positions[i] - positions[j]))
            for j in range(len(names))
            if j != i
        ]
        stats[name] = {
            "flagged_fraction": frac,
            "array_centre_dist_m": dist,
            "baselines_m": bases,
            "rows_fully_flagged": int(rows[mine].sum()),
        }
    core = {
        n: s
        for n, s in stats.items()
        if s["array_centre_dist_m"] <= MAXDIST
        and all(b >= MINBASE for b in s["baselines_m"])
    }
    ranked = sorted(core.items(), key=lambda item: item[1]["flagged_fraction"])
    refant = ",".join(n for n, _ in ranked[:3])
    return refant, stats


def solve(arm, ms):
    minblperant, run_setjy, uvrange, refant_override = ARMS[arm]
    fields, names, positions, flag, a1, a2, uvw = ms_info(ms)
    field = fields[0]
    auto_refant, antenna_stats = caracal_refant(names, positions, flag, a1, a2)
    refant = auto_refant if refant_override is None else refant_override
    extra = {} if minblperant is None else {"minblperant": minblperant}
    log = {
        "arm": arm,
        "ms": ms,
        "field": field,
        "caracal_commit": CARACAL_COMMIT,
        "refant": refant,
        "refant_auto": auto_refant,
        "refant_rule": {
            "maxdist_m": MAXDIST,
            "minbase_m": MINBASE,
            "centre": CENTRE_DEG,
        },
        "antennas": antenna_stats,
        "baseline_lengths_m": sorted(
            {
                f"{names[p]}-{names[q]}": float(
                    np.linalg.norm(uvw[(a1 == p) & (a2 == q)], axis=1).mean()
                )
                for p, q in zip(a1, a2)
            }.items()
        ),
        "minblperant": minblperant,
        "uvrange": uvrange,
        "tasks": {},
    }
    tasks = log["tasks"]
    prefix = f"/run/{arm}"
    k, g, b = f"{prefix}.K0", f"{prefix}.G0", f"{prefix}.B0"
    try:
        if run_setjy:
            model = caracal_manual_model()
            log["manual_model"] = model
            entry = timed(
                tasks,
                "setjy",
                setjy,
                vis=ms,
                field=field,
                standard="manual",
                fluxdensity=model["fluxdensity"],
                reffreq=model["reffreq"],
                spix=model["spix"],
                scalebychan=True,
                usescratch=True,
            )
            if not entry["ok"]:
                return log
        entry = timed(
            tasks,
            "gaincal_K",
            gaincal,
            vis=ms,
            caltable=k,
            field=field,
            refant=refant,
            solint="120s",
            combine="",
            spw="",
            scan="",
            gaintype="K",
            **extra,
        )
        if not entry["ok"]:
            return log
        entry = timed(
            tasks,
            "gaincal_G",
            gaincal,
            vis=ms,
            caltable=g,
            field=field,
            refant=refant,
            solint="120s",
            combine="",
            spw="",
            scan="",
            gaintype="G",
            uvrange=uvrange,
            calmode="ap",
            gaintable=[k],
            interp=["linear"],
            gainfield=[field],
            **extra,
        )
        if not entry["ok"]:
            return log
        timed(
            tasks,
            "bandpass_B",
            bandpass,
            vis=ms,
            caltable=b,
            field=field,
            refant=refant,
            solint="inf",
            combine="scan",
            bandtype="B",
            solnorm=False,
            fillgaps=70,
            uvrange=uvrange,
            scan="",
            gaintable=[k, g],
            interp=["linear", "linear"],
            gainfield=[field, field],
            **extra,
        )
    finally:
        dump(f"{arm}-solve", log)
    return log


def apply(arm, ms):
    fields = ms_info(ms)[0]
    prefix = f"/run/{arm}"
    tables = [f"{prefix}.K0", f"{prefix}.G0", f"{prefix}.B0"]
    log = {"arm": arm, "ms": ms, "tasks": {}}
    missing = [t for t in tables if not Path(t).exists()]
    if missing:
        log["skipped"] = f"missing tables {missing}"
    else:
        timed(
            log["tasks"],
            "applycal",
            applycal,
            vis=ms,
            field=fields[0],
            applymode="calflag",
            gaintable=tables,
            interp=["linear", "linear", "linear"],
            calwt=[False],
            gainfield=["nearest", "nearest", "nearest"],
            parang=False,
            flagbackup=False,
        )
    dump(f"{arm}-apply", log)
    return log


def run_flagdata(mode, ms):
    log = {"mode": mode, "ms": ms, "tasks": {}}
    if mode == "tfcrop":
        params = {
            "mode": "tfcrop",
            "datacolumn": "data",
            "field": ms_info(ms)[0][0],
            "usewindowstats": "std",
            "combinescans": False,
            "flagdimension": "freqtime",
            "flagbackup": False,
            "timecutoff": 4.0,
            "freqcutoff": 3.0,
            "correlation": "",
        }
    elif mode == "rflag":
        params = {"mode": "rflag", "datacolumn": "data", "flagbackup": False}
    else:
        raise SystemExit(f"unknown flagdata mode {mode}")
    timed(log["tasks"], f"flagdata_{mode}", flagdata, vis=ms, **params)
    dump(f"flagdata-{mode}", log)
    return log


def run_setjy_standard(standard, ms):
    field = ms_info(ms)[0][0]
    log = {"standard": standard, "ms": ms, "tasks": {}}
    timed(
        log["tasks"],
        "setjy",
        setjy,
        vis=ms,
        field=field,
        standard=standard,
        scalebychan=True,
        usescratch=True,
    )
    dump(f"setjy-{standard.replace(' ', '_')}", log)
    return log


def main(argv):
    command, what, ms = argv[1:4]
    if command == "solve":
        log = solve(what, ms)
        failed = [k for k, v in log["tasks"].items() if not v["ok"]]
    elif command == "apply":
        log = apply(what, ms)
        failed = [k for k, v in log["tasks"].items() if not v["ok"]]
    elif command == "flagdata":
        log = run_flagdata(what, ms)
        failed = [k for k, v in log["tasks"].items() if not v["ok"]]
    elif command == "setjy":
        log = run_setjy_standard(what, ms)
        failed = [k for k, v in log["tasks"].items() if not v["ok"]]
    else:
        raise SystemExit(__doc__)
    print(json.dumps({"command": command, "what": what, "failed": failed}))
    # Arms A, B (frozen) and D (diagnostic) may fail; that is their outcome.
    return 1 if failed and what not in ("a", "b", "d") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
