"""Oracle side of task C2d (research/c2d-fluxscale.md); imports no `rang`.
CASA 6.7.6.14 (`rang-o-casa:6.7.6.14`, run with `/opt/casa/bin/python -I`):

    oracle_fluxscale.py slice2 <src.ms> <dst.ms> <first_int> <factor>
    oracle_fluxscale.py edit <ms> <edit.json>
    oracle_fluxscale.py multispw <src.ms> <dst.ms> <nspw> <tables.json> <check.json>
    oracle_fluxscale.py steps <spec.json> <result.json>

`slice2` copies an MS and turns integrations `first_int` onward into a new
field `SLICE-SEC` (a FIELD row copied from the slice's one field, the last id) whose DATA
is multiplied by `factor`. `edit` is `oracle_gain.py casa-edit` (MODEL_DATA,
FLAG, weights). `multispw` corrects a copy by the tables in `tables.json`
(`applycal`, `calwt=False`, `parang=False`), splits it into `nspw` windows
with `mstransform(datacolumn='all', regridms=True, mode='channel')`, writes
CORRECTED_DATA into DATA and checks per window that DATA, MODEL_DATA, FLAG
and WEIGHT_SPECTRUM equal the source's corrected data, model, flags and
weights. `steps` runs a list of CASA calls and table edits in order and
records each one's parameters, return value (made JSON-safe) and wall time:
`gaincal`, `bandpass` (C2e), `fluxscale`, `applycal`, `copytree`, `rmtree` and `edit_caltable`
(flag or scale rows of a calibration table copy: see `edit_caltable`).
"""

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def jsonable(x):
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, np.ndarray):
        return jsonable(x.tolist())
    if isinstance(x, (np.floating,)):
        return float(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, complex):
        return [x.real, x.imag]
    return x


def slice2(src, dst, first_int, factor):
    from casatools import table

    shutil.copytree(src, dst)
    lock = Path(dst) / "table.lock"
    if lock.exists():
        lock.unlink()
    tb = table()
    tb.open(dst)
    (old,) = np.unique(tb.getcol("FIELD_ID"))  # the slice holds one field
    old = int(old)
    tb.close()
    tb.open(dst + "/FIELD", nomodify=False)
    tb.addrows(1)
    new = tb.nrows() - 1
    for col in tb.colnames():
        if tb.iscelldefined(col, old):
            tb.putcell(col, new, tb.getcell(col, old))
    tb.putcell("NAME", new, "SLICE-SEC")
    tb.close()
    tb.open(dst, nomodify=False)
    t = tb.getcol("TIME")
    times = np.unique(t)
    rows = np.flatnonzero(t >= times[int(first_int)])
    fid = tb.getcol("FIELD_ID")
    fid[rows] = new
    tb.putcol("FIELD_ID", fid)
    data = tb.getcol("DATA")
    data[:, :, rows] *= np.float32(factor)
    tb.putcol("DATA", data)
    tb.close()
    return {
        "rows_moved": len(rows),
        "times": len(times),
        "factor": float(factor),
        "primary_field": old,
        "secondary_field": int(new),
    }


def multispw(src, dst, nspw, tables_json, check_json):
    from casatasks import applycal, mstransform
    from casatools import table

    work = dst + ".corrected.ms"
    shutil.copytree(src, work)
    spec = json.loads(Path(tables_json).read_text())
    applycal(
        vis=work,
        gaintable=spec["gaintable"],
        interp=spec.get("interp", ["linear"] * len(spec["gaintable"])),
        calwt=[False],
        parang=False,
        flagbackup=False,
    )
    mstransform(
        vis=work,
        outputvis=dst,
        datacolumn="all",
        regridms=True,
        nspw=int(nspw),
        mode="channel",
    )
    tb = table()
    tb.open(work)
    ref = {
        "CORRECTED_DATA": tb.getcol("CORRECTED_DATA"),
        "MODEL_DATA": tb.getcol("MODEL_DATA"),
        "FLAG": tb.getcol("FLAG"),
        "WEIGHT_SPECTRUM": tb.getcol("WEIGHT_SPECTRUM"),
    }
    tb.close()
    tb.open(work + "/SPECTRAL_WINDOW")
    fin = tb.getcell("CHAN_FREQ", 0)
    tb.close()
    tb.open(dst, nomodify=False)
    tb.putcol("DATA", tb.getcol("CORRECTED_DATA"))
    tb.close()
    tb.open(dst + "/SPECTRAL_WINDOW")
    freqs = [tb.getcell("CHAN_FREQ", i) for i in range(tb.nrows())]
    tb.close()
    tb.open(dst)
    out = {"rows": tb.nrows(), "columns": tb.colnames(), "spws": []}
    ok = True
    for s in range(len(freqs)):
        sub = tb.query(f"DATA_DESC_ID=={s}")
        lo = int(np.argmin(np.abs(fin - freqs[s][0])))
        n = len(freqs[s])
        r = {"spw": s, "first_channel": lo, "nchan": n}
        r["freq_equal"] = bool(np.array_equal(fin[lo : lo + n], freqs[s]))
        for col, src_col in (
            ("DATA", "CORRECTED_DATA"),
            ("MODEL_DATA", "MODEL_DATA"),
            ("FLAG", "FLAG"),
            ("WEIGHT_SPECTRUM", "WEIGHT_SPECTRUM"),
        ):
            got = sub.getcol(col)
            want = ref[src_col][:, lo : lo + n, :]
            r[col + "_equal"] = bool(
                got.shape == want.shape and np.array_equal(got, want)
            )
            ok &= r[col + "_equal"]
        ok &= r["freq_equal"]
        out["spws"].append(r)
        sub.close()
    tb.close()
    shutil.rmtree(work)
    out["all_equal"] = bool(ok)
    Path(check_json).write_text(json.dumps(out, indent=1) + "\n")
    if not ok:
        raise SystemExit(f"mstransform changed the data: {check_json}")


def edit_caltable(src, dst, ops):
    """Copy calibration table `src` to `dst` and apply `ops` in order:
    `{"flag": {...selector}}` sets FLAG on the selected rows (all
    parameters, or `par`); `{"flag_except": {...selector, "antenna": a,
    "par": p}}` flags every parameter of the selected rows except
    parameter `p` of antenna `a`; `{"scale": {...selector, "factor": x}}`
    multiplies CPARAM. A selector holds any of `field`, `spw`, `antenna`,
    `scan` (lists of ints)."""
    from casatools import table

    shutil.copytree(src, dst)
    tb = table()
    tb.open(dst, nomodify=False)
    cols = {
        c: tb.getcol(c)
        for c in ("FIELD_ID", "SPECTRAL_WINDOW_ID", "ANTENNA1", "SCAN_NUMBER")
    }
    flag = tb.getcol("FLAG")  # (par, chan, row)
    cparam = tb.getcol("CPARAM")
    counts = []

    def select(sel, skip=()):
        keep = np.ones(len(cols["FIELD_ID"]), bool)
        for key, col in (("field", "FIELD_ID"), ("spw", "SPECTRAL_WINDOW_ID"),
                         ("antenna", "ANTENNA1"), ("scan", "SCAN_NUMBER")):  # fmt: skip
            if key in sel and key not in skip:
                keep &= np.isin(cols[col], sel[key])
        return keep

    for op in ops:
        ((kind, sel),) = op.items()
        if kind == "flag":
            rows = select(sel)
            pars = sel.get("par", list(range(flag.shape[0])))
            for p in pars:
                flag[p, :, rows] = True
        elif kind == "flag_except":
            rows = select(sel, skip=("antenna",))
            flag[:, :, rows] = True
            keep = rows & (cols["ANTENNA1"] == sel["antenna"])
            flag[sel["par"], :, keep] = False
        elif kind == "scale":
            rows = select(sel)
            cparam[:, :, rows] *= np.complex64(sel["factor"])
        else:
            raise SystemExit(f"unknown edit {kind}")
        counts.append({kind: int(rows.sum())})
    tb.putcol("FLAG", flag)
    tb.putcol("CPARAM", cparam)
    tb.close()
    return {"rows": counts}


def steps(spec_path, result_path):
    from casatasks import applycal, bandpass, fluxscale, gaincal

    # bandpass: task C2e (research/c2e-calibrate.md), the whole chain.
    tasks = {"gaincal": gaincal, "bandpass": bandpass, "fluxscale": fluxscale,
             "applycal": applycal}  # fmt: skip
    results = []
    for step in json.loads(Path(spec_path).read_text()):
        name, args = step["task"], step.get("args", {})
        started = time.perf_counter()
        out, error = None, None
        try:
            if name in tasks:
                out = tasks[name](**args)
            elif name == "copytree":
                shutil.copytree(args["src"], args["dst"])
            elif name == "rmtree":
                shutil.rmtree(args["path"], ignore_errors=True)
            elif name == "edit_caltable":
                out = edit_caltable(args["src"], args["dst"], args["ops"])
            else:
                raise SystemExit(f"unknown step {name}")
        except Exception as exc:  # noqa: BLE001 (recorded, not hidden)
            error = repr(exc)
        results.append(
            {
                "label": step.get("label", name),
                "task": name,
                "args": args,
                "seconds": time.perf_counter() - started,
                "error": error,
                "return": jsonable(out) if out is not None else None,
            }
        )
        Path(result_path).write_text(json.dumps(results, indent=1) + "\n")
        if error and step.get("required", True):
            raise SystemExit(f"step {step.get('label', name)} failed: {error}")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "slice2" and len(argv) == 6:
        print(json.dumps(slice2(argv[2], argv[3], int(argv[4]), float(argv[5]))))
    elif cmd == "edit" and len(argv) == 4:
        import oracle_gain

        oracle_gain.casa_edit(argv[2], argv[3])
    elif cmd == "multispw" and len(argv) == 7:
        multispw(argv[2], argv[3], int(argv[4]), argv[5], argv[6])
    elif cmd == "steps" and len(argv) == 4:
        steps(argv[2], argv[3])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
