"""Task A1: the CASA side of the simulated-truth checks (research/a1-simtruth.md).

Runs inside `rang-o-casa:6.7.6.14` (CASA venv `/opt/casa/bin/python`) and
imports no `rang`; driven by `examples/a1_simtruth_check.py`.

    listobs MS OUT.txt
    tables  MS TRUTH.npz TRUTH.json WORKDIR   # copy MS, make template tables, overwrite with truth
    apply   WORKDIR PARANG EXPORT.npz          # applycal the truth tables, export CORRECTED_DATA

`tables` copies the noiseless twin to WORKDIR/work.ms, sets the calibrator
models (the polarised one with `setjy` manual, the truth's values), runs
one template solve per type to obtain a table CASA itself made (K on the
flux calibrator, G per integration on every field, B, KCROSS and Xf on the
polarised calibrator, Df on the flux calibrator), then overwrites every
parameter with the raw truth (FLAG false, SNR 1e3) through casatools'
`table`. `apply` runs `applycal` with all six tables (`calwt=False`,
`interp` nearest, `parang` as given) and exports CORRECTED_DATA, FLAG and
the row columns.
"""

import json
import shutil
import sys
from pathlib import Path

import numpy as np

TYPES = ("K", "B", "G", "Kcross", "Xf", "Df")


def _tools():
    import casatasks
    import casatools

    return casatasks, casatools


def listobs(ms, out):
    casatasks, _ = _tools()
    casatasks.listobs(vis=ms, listfile=out, overwrite=True, verbose=True)
    print(Path(out).read_text()[:2000])


def _fields(ms):
    _, ct = _tools()
    tb = ct.table()
    tb.open(f"{ms}/FIELD")
    names = list(tb.getcol("NAME"))
    tb.close()
    return names


def make_tables(ms, truth_npz, truth_json, workdir):
    casatasks, ct = _tools()
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    vis = str(work / "work.ms")
    if Path(vis).exists():
        shutil.rmtree(vis)
    shutil.copytree(ms, vis)
    truth = np.load(truth_npz)
    meta = json.loads(Path(truth_json).read_text())
    names = _fields(vis)
    fcal, xcal = names[0], names[1]
    x = meta["calibrators"]["xcal"]
    casatasks.setjy(
        vis=vis,
        field=fcal,
        standard="Stevens-Reynolds 2016",
        scalebychan=True,
        usescratch=True,
    )
    casatasks.setjy(
        vis=vis,
        field=xcal,
        standard="manual",
        fluxdensity=[x["fluxdensity"], 0, 0, 0],
        spix=list(x["spix"]),
        reffreq=f"{x['reffreq_hz'] / 1e9}GHz",
        polindex=[x["p"]],
        polangle=[np.radians(x["chi_deg"])],
        rotmeas=x["rm"],
        scalebychan=True,
        usescratch=True,
    )
    refant = meta["antenna_names"][meta["gauge"]["refant"]]
    t = {k: str(work / f"truth.{k}") for k in TYPES}
    for p in t.values():
        if Path(p).exists():
            shutil.rmtree(p)
    common = {"vis": vis, "refant": refant, "minsnr": 0.0, "minblperant": 1}
    casatasks.gaincal(
        caltable=t["K"],
        field=fcal,
        gaintype="K",
        solint="inf",
        combine="scan",
        **common,
    )
    casatasks.gaincal(
        caltable=t["G"],
        field="",
        gaintype="G",
        calmode="ap",
        solint="int",
        combine="",
        **common,
    )
    casatasks.bandpass(
        caltable=t["B"],
        field=fcal,
        bandtype="B",
        solint="inf",
        combine="scan",
        solnorm=False,
        fillgaps=0,
        **common,
    )
    casatasks.gaincal(
        caltable=t["Kcross"],
        field=xcal,
        gaintype="KCROSS",
        solint="inf",
        combine="scan",
        parang=True,
        **common,
    )
    casatasks.polcal(
        vis=vis,
        caltable=t["Xf"],
        field=xcal,
        poltype="Xf",
        solint="inf",
        combine="scan",
        refant=refant,
        minsnr=0.0,
        minblperant=1,
    )
    casatasks.polcal(
        vis=vis,
        caltable=t["Df"],
        field=fcal,
        poltype="Df",
        solint="inf",
        combine="scan",
        refant=refant,
        minsnr=0.0,
        minblperant=1,
    )
    report = {"tables": t, "shapes": {}, "rows": {}}
    tb = ct.table()
    gain = truth["raw_gain"] * truth["raw_selfcal"][..., None]
    times = truth["time"]
    for kind, path in t.items():
        tb.open(path, nomodify=False)
        col = "FPARAM" if kind in ("K", "Kcross") else "CPARAM"
        par = tb.getcol(col)  # casacore order (npar, nchan, nrow)
        ant = tb.getcol("ANTENNA1")
        report["shapes"][kind] = list(par.shape)
        report["rows"][kind] = len(ant)
        report.setdefault("viscal", {})[kind] = tb.getkeyword("VisCal")
        new = np.zeros_like(par)
        if kind == "K":
            new[:, 0, :] = truth["raw_tau_ns"][ant].T
        elif kind == "Kcross":
            new[:, 0, :] = 0.0
            new[0, 0, :] = meta["design"]["tau_c_ns"]
        elif kind == "B":
            new[:] = np.transpose(truth["raw_bandpass"][ant], (2, 1, 0))
        elif kind == "Df":
            new[:] = np.transpose(truth["raw_leakage"][ant], (2, 1, 0))
        elif kind == "Xf":
            new[:] = truth["raw_xf"][None, :, None]
        elif kind == "G":
            tt = tb.getcol("TIME")
            idx = np.searchsorted(times, tt)
            idx = np.clip(idx, 0, len(times) - 1)
            lo = np.clip(idx - 1, 0, len(times) - 1)
            idx = np.where(np.abs(times[lo] - tt) < np.abs(times[idx] - tt), lo, idx)
            report["g_time_max_offset_s"] = float(np.abs(times[idx] - tt).max())
            new[:, 0, :] = gain[idx, ant].T
        tb.putcol(col, new)
        tb.putcol("FLAG", np.zeros(par.shape, bool))
        tb.putcol("SNR", np.full(par.shape, 1e3, np.float32))
        tb.close()
    (work / "tables.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))


def apply(workdir, parang, export):
    casatasks, ct = _tools()
    work = Path(workdir)
    vis = str(work / "work.ms")
    t = json.loads((work / "tables.json").read_text())["tables"]
    order = ["K", "B", "G", "Kcross", "Xf", "Df"]
    casatasks.applycal(
        vis=vis,
        field="",
        gaintable=[t[k] for k in order],
        interp=["nearest"] * len(order),
        gainfield=[""] * len(order),
        calwt=[False] * len(order),
        parang=parang == "True",
        applymode="calflag",
        flagbackup=False,
    )
    tb = ct.table()
    tb.open(vis)
    out = {
        c: tb.getcol(c)
        for c in (
            "CORRECTED_DATA",
            "FLAG",
            "DATA",
            "TIME",
            "ANTENNA1",
            "ANTENNA2",
            "FIELD_ID",
        )
    }
    tb.close()
    # casacore order (corr, chan, row) to (row, chan, corr)
    for c in ("CORRECTED_DATA", "FLAG", "DATA"):
        out[c] = np.ascontiguousarray(np.transpose(out[c], (2, 1, 0)))
    np.savez(export, **out)
    print("exported", export, out["CORRECTED_DATA"].shape)


def main(argv):
    cmd = argv[0]
    if cmd == "listobs":
        listobs(argv[1], argv[2])
    elif cmd == "tables":
        make_tables(argv[1], argv[2], argv[3], argv[4])
    elif cmd == "apply":
        apply(argv[1], argv[2], argv[3])
    else:
        raise SystemExit(f"unknown command {cmd}")


if __name__ == "__main__":
    main(sys.argv[1:])
