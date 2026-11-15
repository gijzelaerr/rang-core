"""Arm A3's CASA side (research/e2b-misses.md 9.21); imports no `rang`.

CASA 6.7.6.14 (`rang-o-casa:6.7.6.14`, `/opt/casa/bin/python -I`):

    a3_casa.py base SRC_MS OUT_MS OUT.json   deep copy of the FIELD_ID 0 rows
    a3_casa.py tasks SPEC.json RESULT.json   the calls, in order

`tasks` runs CASA tasks and these steps (`a2_casa.py`'s `copytree` and
`putflags`, plus):
- `receptor` (`vis`, `deg`): FEED RECEPTOR_ANGLE set on both receptors;
- `reset` (`vis`): FLAG and FLAG_ROW false, WEIGHT, SIGMA and
  WEIGHT_SPECTRUM 1;
- `simulate` (`vis`, `seed`, `sigma`, `flux`, `freq0`, `index`, `lm_arcsec`,
  `drift_rad`, `drift_period_s`): the simulation of 9.21. MODEL_DATA must hold
  the point model (`setjy` first). DATA = g_p (M + C) g_q* on the parallel
  hands, 0 on the cross hands, plus noise; CORRECTED_DATA the same with
  C = 0 and the same noise. The gains are written to `truth` (an .npz);
- `swap` (`vis`): DATA from CORRECTED_DATA;
- `model_rows` (`vis`, `rows`, `out`): MODEL_DATA of those rows to an .npy.
The result records each call's seconds and the process's peak RSS.
A step's error stops the run.
"""

import json
import os
import resource
import shutil
import sys
import time
from pathlib import Path

B = 2000
C_LIGHT = 299792458.0


def base(src, out, out_json):
    import numpy as np
    from casatools import table

    tb = table()
    tb.open(src)
    fid = tb.getcol("FIELD_ID")
    rows = np.flatnonzero(fid == 0)
    sel = tb.query("FIELD_ID == 0")
    sel.copy(out, deep=True, valuecopy=True, returnobject=False)
    sel.close()
    t_src = tb.getcol("TIME")[rows]
    a_src = tb.getcol("ANTENNA1")[rows], tb.getcol("ANTENNA2")[rows]
    tb.close()
    tb.open(out)
    same = bool(
        tb.nrows() == len(rows)
        and (tb.getcol("TIME") == t_src).all()
        and (tb.getcol("ANTENNA1") == a_src[0]).all()
        and (tb.getcol("ANTENNA2") == a_src[1]).all()
    )
    cols = tb.colnames()
    tb.close()
    info = {"rows": len(rows), "first": int(rows[0]), "last": int(rows[-1]),
            "contiguous": bool((np.diff(rows) == 1).all()), "rows_match_source": same,
            "columns": cols}  # fmt: skip
    Path(out_json).write_text(json.dumps(info, indent=1) + "\n")
    return 0 if (same and info["contiguous"]) else 3


def receptor(vis, deg):
    import numpy as np
    from casatools import table

    tb = table()
    tb.open(vis + "/FEED", nomodify=False)
    a = tb.getcol("RECEPTOR_ANGLE")
    a[:] = np.deg2rad(float(deg))
    tb.putcol("RECEPTOR_ANGLE", a)
    tb.close()
    return {"receptor_angle_rad": float(np.deg2rad(float(deg)))}


def reset(vis):
    import numpy as np
    from casatools import table

    tb = table()
    tb.open(vis, nomodify=False)
    n = tb.nrows()
    for r0 in range(0, n, B):
        k = min(B, n - r0)
        f = tb.getcol("FLAG", r0, k)
        tb.putcol("FLAG", np.zeros_like(f), r0, k)
        tb.putcol("FLAG_ROW", np.zeros(k, bool), r0, k)
        for c in ("WEIGHT", "SIGMA", "WEIGHT_SPECTRUM"):
            if c in tb.colnames():
                x = tb.getcol(c, r0, k)
                tb.putcol(c, np.ones_like(x), r0, k)
    tb.close()
    return {"rows": n}


def simulate(vis, seed, sigma, flux, freq0, index, lm_arcsec, drift_rad, drift_period_s,
             truth):  # fmt: skip
    import numpy as np
    from casatools import table

    tb = table()
    tb.open(vis + "/SPECTRAL_WINDOW")
    freq = tb.getcol("CHAN_FREQ")[:, 0]
    tb.close()
    tb.open(vis + "/ANTENNA")
    nant = tb.nrows()
    tb.close()
    rng = np.random.default_rng(int(seed))
    phi0 = rng.uniform(-np.pi, np.pi, (nant, 2))
    phi0[:, :] = np.where(phi0 == -np.pi, np.pi, phi0)
    theta = rng.uniform(-np.pi, np.pi, (nant, 2))
    l, m = (np.deg2rad(float(x) / 3600.0) for x in lm_arcsec)
    comp = float(flux) * (freq / float(freq0)) ** float(index)
    tb.open(vis, nomodify=False)
    n = tb.nrows()
    t0 = float(tb.getcol("TIME", 0, 1)[0])
    rms = []
    for blk, r0 in enumerate(range(0, n, B)):
        k = min(B, n - r0)
        time_ = tb.getcol("TIME", r0, k) - t0
        a1, a2 = tb.getcol("ANTENNA1", r0, k), tb.getcol("ANTENNA2", r0, k)
        uvw = tb.getcol("UVW", r0, k)  # (3, row)
        model = tb.getcol("MODEL_DATA", r0, k)  # (corr, chan, row)
        ph = phi0[None] + float(drift_rad) * np.sin(
            2 * np.pi * time_[:, None, None] / float(drift_period_s) + theta[None]
        )  # (row, ant, hand)
        rows_ = np.arange(k)
        gp = np.exp(1j * ph[rows_, a1])  # (row, hand)
        gq = np.exp(1j * ph[rows_, a2])
        delay = (
            (uvw[0] * l + uvw[1] * m)[None, :] * freq[:, None] / C_LIGHT
        )  # (chan, row)
        cvis = comp[:, None] * np.exp(-2j * np.pi * delay)
        noise = rng.normal(0, float(sigma), (2,) + model.shape)
        noise = noise[0] + 1j * noise[1]
        res = np.zeros(model.shape, np.complex128)
        pt = np.zeros(model.shape, np.complex128)
        for c, h in ((0, 0), (3, 1)):
            g = (gp[:, h] * np.conj(gq[:, h]))[None, :]
            pt[c] = g * model[c]
            res[c] = g * (model[c] + cvis)
        rms.append(float(np.sqrt(np.mean(np.abs(res - pt) ** 2))))
        tb.putcol("DATA", (res + noise).astype(np.complex64), r0, k)
        tb.putcol("CORRECTED_DATA", (pt + noise).astype(np.complex64), r0, k)
    tb.close()
    np.savez(truth, phase0=phi0, theta=theta, drift_rad=float(drift_rad),
             drift_period_s=float(drift_period_s), t0=t0, nant=nant)  # fmt: skip
    return {"rows": n, "nant": nant, "component_rms_jy": float(np.mean(rms)),
            "component_jy_first_last_chan": [float(comp[0]), float(comp[-1])]}  # fmt: skip


def swap(vis):
    from casatools import table

    tb = table()
    tb.open(vis, nomodify=False)
    n = tb.nrows()
    for r0 in range(0, n, B):
        k = min(B, n - r0)
        tb.putcol("DATA", tb.getcol("CORRECTED_DATA", r0, k), r0, k)
    tb.close()
    return {"rows": n}


def model_rows(vis, rows, out):
    import numpy as np
    from casatools import table

    tb = table()
    tb.open(vis)
    m = np.stack([tb.getcol("MODEL_DATA", int(r), 1)[..., 0].T for r in rows])
    tb.close()
    np.save(out, m)  # (row, chan, corr), as python-casacore's getcol
    return {"rows": [int(r) for r in rows], "shape": list(m.shape)}


def tasks(spec_path, result_path):
    import casatasks

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from a2_casa import putflags

    calls = json.loads(Path(spec_path).read_text())
    if calls and "logfile" in calls[0]:
        casatasks.casalog.setlogfile(calls[0]["logfile"])
        calls = calls[1:]
    local = {"receptor": receptor, "reset": reset, "simulate": simulate, "swap": swap,
             "model_rows": model_rows}  # fmt: skip
    results = []
    for entry in calls:
        name, call = entry["task"], entry["args"]
        started = time.perf_counter()
        out, error = None, None
        try:
            if name == "copytree":
                if os.path.isdir(call["dst"]):
                    shutil.rmtree(call["dst"])
                shutil.copytree(call["src"], call["dst"])
            elif name == "putflags":
                out = putflags(call["vis"], call["version"], int(call["first"]),
                               call.get("field"))  # fmt: skip
            elif name in local:
                out = local[name](**call)
            else:
                out = getattr(casatasks, name)(**call)
        except Exception as exc:  # noqa: BLE001 (recorded, not hidden)
            error = repr(exc)
        target = call.get("caltable") or call.get("dst")
        results.append({
            "task": name, "call": call, "seconds": time.perf_counter() - started,
            "error": error, "written": bool(target) and os.path.isdir(str(target)),
            "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
            "return": json.loads(json.dumps(out, default=str)) if out else None,
        })  # fmt: skip
        Path(result_path).write_text(json.dumps(results, indent=1) + "\n")
        if error:
            break
    return 3 if any(r["error"] for r in results) else 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "base" and len(argv) == 5:
        return base(*argv[2:5])
    if cmd == "tasks" and len(argv) == 4:
        return tasks(argv[2], argv[3])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
