"""Arm A1b's CASA side (research/e2b-misses.md 9.5); imports no `rang`.

    a1b_casa.py MINI_MS WORK OUT_DIR

For each field of the mini MS: a fresh copy, DATA = XX 1, XY = YX = YY 0,
FLAG false, CASA `applycal` with no tables and `parang=True`; CORRECTED_DATA
saved to OUT_DIR/probe_<field id>.npz. Also UT1 - UTC (s) from
`casatools.measures` at every distinct TIME, and the measures data's
IERSeop2000 VS_DATE, in OUT_DIR/casa-ut1.json.
"""

import json
import shutil
import sys
from pathlib import Path


def main(mini, work, out):
    import casatasks
    import numpy as np
    from casatools import ctsys, measures, quanta, table

    work, out = Path(work), Path(out)
    work.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    casatasks.casalog.setlogfile(str(work / "casa-a1b.log"))
    tb = table()
    errors = {}
    for fid, name in ((1, "J1939-6342"), (2, "J1833-2103")):
        ms = work / "p.ms"
        if ms.exists():
            shutil.rmtree(ms)
        shutil.copytree(mini, ms)
        tb.open(str(ms), nomodify=False)
        d = tb.getcol("DATA")
        e = np.zeros_like(d)
        e[0] = 1.0
        tb.putcol("DATA", e)
        tb.putcol("FLAG", np.zeros(d.shape, bool))
        tb.putcol("FLAG_ROW", np.zeros(d.shape[-1], bool))
        tb.close()
        try:
            casatasks.applycal(vis=str(ms), field=name, gaintable=[], parang=True,
                               applymode="calflag", flagbackup=False)  # fmt: skip
            errors[name] = None
        except Exception as exc:  # noqa: BLE001 (recorded)
            errors[name] = repr(exc)
        tb.open(str(ms))
        np.savez(out / f"probe_{fid}.npz",
                 CORRECTED_DATA=np.transpose(tb.getcol("CORRECTED_DATA"), (2, 1, 0)),
                 FIELD_ID=tb.getcol("FIELD_ID"), TIME=tb.getcol("TIME"))  # fmt: skip
        times = np.unique(tb.getcol("TIME"))
        tb.close()
    shutil.rmtree(work / "p.ms", ignore_errors=True)
    me, qa = measures(), quanta()
    ut1 = []
    for t in times:
        ep = me.epoch("utc", qa.quantity(float(t), "s"))
        u = me.measure(ep, "ut1")
        ut1.append((u["m0"]["value"] - ep["m0"]["value"]) * 86400.0)
    path = Path(ctsys.measurespath()) / "geodetic" / "IERSeop2000"
    vs = None
    try:
        tb.open(str(path))
        vs = {
            k: str(tb.getkeyword(k))
            for k in ("VS_DATE", "VS_VERSION")
            if k in tb.keywordnames()
        }
        tb.close()
    except Exception as exc:  # noqa: BLE001
        vs = repr(exc)
    res = {"errors": errors, "times": times.tolist(), "ut1_minus_utc_s": ut1,
           "measurespath": str(ctsys.measurespath()), "IERSeop2000": vs}  # fmt: skip
    (out / "casa-ut1.json").write_text(json.dumps(res, indent=1) + "\n")
    return 0 if not any(errors.values()) else 3


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
