"""Oracle side of task C2a (research/c2a-gain.md); imports no `rang`.

QuartiCal 0.2.7 (`rang-formats-oracle:20261030`, run with `/opt/qc/bin/python -I`):

    oracle_gain.py qc-copy <src.ms> <dst.ms> [<column.npz> <NAME>] ...
    oracle_gain.py qc-solve <ms> <out> <key=value> ...

`qc-copy` copies an MS (dropping `table.lock`) and optionally adds columns
`NAME` shaped like DATA holding `column.npz`'s `values` (row, chan, corr);
NAME `FLAG` ORs boolean `values` into FLAG instead (C2b).
`qc-solve` runs `goquartical` with the given options under `/usr/bin/time`,
checks FLAG and FLAG_ROW are unchanged, and saves `gains.npy`
(time, freq, ant, 4), `gain_flags.npy`, for parameterised terms (C2b's
`delay`) `params.npy` and `param_flags.npy`, and `summary.json`
(`conv_iter`, `conv_perc` per chunk, wall, peak RSS) in `<out>`; chunks
(scans) are stacked in time.

CASA 6.7.6.14 (`rang-o-casa:6.7.6.14`, run with `/opt/casa/bin/python -I`):

    oracle_gain.py casa-edit <ms> <edit.json>
    oracle_gain.py casa-gaincal <spec.json> <result.json>
    oracle_gain.py casa-tasks <spec.json> <result.json>

`casa-tasks` (C2c) runs a list of `{"task": "gaincal" | "bandpass",
"args": {...}}` in order (a chain: each call may name tables earlier calls
wrote) and records each as `casa-gaincal` does.

`casa-edit` writes MODEL_DATA (adding it with `clearcal(addmodel=True)` if
absent) from an `.npz` (`rows`, `values`), ORs FLAG with an `.npz`
(`rows`, `flag`), and scales WEIGHT_SPECTRUM and WEIGHT (`weight_scale`)
or SIGMA and SIGMA_SPECTRUM (`sigma_scale`) of listed rows.
`casa-gaincal` runs `gaincal` once per entry of the spec list and records
each call's parameters, return value and wall time.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def qc_copy(src, dst, *pairs):
    """Copy `src` to `dst`, then per (`column.npz`, NAME) pair add a column
    NAME, or with NAME `FLAG` OR the pair's boolean `values` into FLAG
    (C2b's RFI flags)."""
    shutil.copytree(src, dst)
    lock = Path(dst) / "table.lock"
    if lock.exists():
        lock.unlink()
    if not pairs:
        return
    import numpy as np
    from casacore.tables import makearrcoldesc, maketabdesc, table

    for column, name in zip(pairs[::2], pairs[1::2]):
        values = np.load(column)["values"]
        with table(dst, readonly=False, ack=False) as t:
            if name == "FLAG":
                flag = t.getcol("FLAG") | values.astype(bool)
                t.putcol("FLAG", flag)
                assert np.array_equal(t.getcol("FLAG"), flag)
                continue
            desc = makearrcoldesc(
                name,
                0j,
                ndim=2,
                valuetype="complex",
                comment="C2a/C2b: an array written by rang",
            )
            t.addcols(maketabdesc(desc))
            t.putcol(name, values.astype(np.complex64))
            assert np.array_equal(t.getcol(name), values.astype(np.complex64))


def qc_solve(ms, out, options):
    import numpy as np
    from casacore.tables import table
    from daskms.experimental.zarr import xds_from_zarr

    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    command = [
        "/opt/qc/bin/goquartical",
        f"input_ms.path={ms}",
        f"output.gain_directory={out / 'gains.qc'}",
        f"output.log_directory={out / 'logs.qc'}",
        *options,
    ]
    with table(ms, readonly=True, ack=False, lockoptions="autonoread") as t:
        flags, rows = t.getcol("FLAG"), t.getcol("FLAG_ROW")
    started = time.perf_counter()
    with (out / "quartical.log").open("x") as log:
        proc = subprocess.run(
            ["/usr/bin/time", "-f", "TIME %e %M", *command],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    summary = {"command": command, "returncode": proc.returncode}
    summary["seconds"] = time.perf_counter() - started
    for line in (out / "quartical.log").read_text().splitlines():
        if line.startswith("TIME "):
            _, wall, rss = line.split()
            summary["time_wall"], summary["max_rss_mb"] = float(wall), int(rss) / 1024
    with table(ms, readonly=True, ack=False, lockoptions="autonoread") as t:
        summary["flags_unchanged"] = bool(
            np.array_equal(t.getcol("FLAG"), flags)
            and np.array_equal(t.getcol("FLAG_ROW"), rows)
        )
    if proc.returncode == 0:
        term = "G"
        for opt in options:
            if opt.startswith("solver.terms="):
                term = opt.split("=", 1)[1].strip("[]").split(",")[0]
        # One dataset per chunk (scan); C2a's cases had one, C2b's may have
        # several, stacked here along time in the order of their first time.
        dss = [d.compute() for d in xds_from_zarr(f"{out / 'gains.qc'}::{term}")]
        dss.sort(key=lambda d: float(d.gain_time.values[0]))
        gains = np.concatenate([d.gains.transpose(
            "gain_time", "gain_freq", "antenna", "direction", "correlation"
        ).values[..., 0, :] for d in dss])  # fmt: skip
        gflags = np.concatenate([d.gain_flags.transpose(
            "gain_time", "gain_freq", "antenna", "direction"
        ).values[..., 0] for d in dss])  # fmt: skip
        np.save(out / "gains.npy", gains)
        np.save(out / "gain_flags.npy", gflags)
        if "params" in dss[0]:
            axes = ("param_time", "param_freq", "antenna", "direction", "param_name")
            params = np.concatenate(
                [d.params.transpose(*axes).values[..., 0, :] for d in dss]
            )
            pflags = np.concatenate(
                [d.param_flags.transpose(*axes[:-1]).values[..., 0] for d in dss]
            )
            np.save(out / "params.npy", params)
            np.save(out / "param_flags.npy", pflags)
            summary["param_names"] = [str(x) for x in dss[0].param_name.values]
            summary["chunk_param_times"] = [len(d.param_time) for d in dss]
        summary["shape"] = list(gains.shape)
        summary["chunks"] = len(dss)
        summary["chunk_gain_times"] = [len(d.gain_time) for d in dss]
        summary["gain_times"] = np.concatenate(
            [d.gain_time.values for d in dss]
        ).tolist()
        for key in ("conv_iter", "conv_perc"):
            values = []
            for d in dss:
                value = d.attrs.get(key, d.get(key, None))
                values.append(None if value is None else np.asarray(value).tolist())
            summary[key] = values[0] if len(dss) == 1 else values
        summary["type"] = dss[0].attrs.get("TYPE")
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str) + "\n")
    if proc.returncode != 0 or not summary["flags_unchanged"]:
        raise SystemExit(f"QuartiCal failed or altered flags: {out}")


def casa_edit(ms, spec_path):
    import numpy as np
    from casatasks import clearcal
    from casatools import table

    spec = json.loads(Path(spec_path).read_text())
    tb = table()
    tb.open(ms)
    has_model = "MODEL_DATA" in tb.colnames()
    tb.close()
    if spec.get("model") and not has_model:
        clearcal(vis=ms, addmodel=True)
    tb.open(ms, nomodify=False)
    if spec.get("model"):
        z = np.load(spec["model"])
        model = tb.getcol("MODEL_DATA")  # (corr, chan, row)
        model[:, :, z["rows"]] = np.transpose(z["values"], (2, 1, 0))
        tb.putcol("MODEL_DATA", model)
    if spec.get("flag"):
        z = np.load(spec["flag"])
        flag = tb.getcol("FLAG")
        flag[:, :, z["rows"]] |= np.transpose(z["flag"], (2, 1, 0))
        tb.putcol("FLAG", flag)
    for rows, factor in spec.get("weight_scale", []):
        ws = tb.getcol("WEIGHT_SPECTRUM")
        ws[:, :, rows] *= factor
        tb.putcol("WEIGHT_SPECTRUM", ws)
        w = tb.getcol("WEIGHT")
        w[:, rows] *= factor
        tb.putcol("WEIGHT", w)
    for rows, factor in spec.get("sigma_scale", []):
        for name in ("SIGMA_SPECTRUM", "SIGMA"):
            if name in tb.colnames():
                s = tb.getcol(name)
                s[..., rows] *= factor
                tb.putcol(name, s)
    tb.close()


def casa_gaincal(spec_path, result_path):
    from casatasks import gaincal

    calls = json.loads(Path(spec_path).read_text())
    results = []
    for call in calls:
        started = time.perf_counter()
        try:
            out = gaincal(**call)
            error = None
        except Exception as exc:  # noqa: BLE001 (recorded, not hidden)
            out, error = None, repr(exc)
        results.append(
            {
                "call": call,
                "seconds": time.perf_counter() - started,
                "error": error,
                "written": os.path.isdir(call["caltable"]),
                "return": json.loads(json.dumps(out, default=str)) if out else None,
            }
        )
    Path(result_path).write_text(json.dumps(results, indent=1) + "\n")


def casa_tasks(spec_path, result_path):
    import casatasks

    calls = json.loads(Path(spec_path).read_text())
    results = []
    for entry in calls:
        task = {"gaincal": casatasks.gaincal, "bandpass": casatasks.bandpass}[
            entry["task"]
        ]
        call = entry["args"]
        started = time.perf_counter()
        try:
            out = task(**call)
            error = None
        except Exception as exc:  # noqa: BLE001 (recorded, not hidden)
            out, error = None, repr(exc)
        results.append(
            {
                "task": entry["task"],
                "call": call,
                "seconds": time.perf_counter() - started,
                "error": error,
                "written": os.path.isdir(call["caltable"]),
                "return": json.loads(json.dumps(out, default=str)) if out else None,
            }
        )
    Path(result_path).write_text(json.dumps(results, indent=1) + "\n")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "qc-copy" and len(argv) >= 4 and len(argv) % 2 == 0:
        qc_copy(*argv[2:])
    elif cmd == "qc-solve" and len(argv) >= 4:
        qc_solve(argv[2], argv[3], argv[4:])
    elif cmd == "casa-edit" and len(argv) == 4:
        casa_edit(argv[2], argv[3])
    elif cmd == "casa-gaincal" and len(argv) == 4:
        casa_gaincal(argv[2], argv[3])
    elif cmd == "casa-tasks" and len(argv) == 4:
        casa_tasks(argv[2], argv[3])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
