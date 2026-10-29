"""QuartiCal full-2x2 solve on the four-station LUNO MS (run in the pinned container).

Uses the frozen pipeline command from rangtoy.flagging_workflow.solve (G.type=complex,
2 x 32 intervals, 50 iterations, reference antenna 0, no robust/MAD, output.flags=false,
single-threaded). Checks FLAG/FLAG_ROW are unchanged and saves gains and convergence.
"""

import json
import pathlib
import subprocess
import sys
import time

import numpy as np
from casacore.tables import table
from daskms.experimental.zarr import xds_from_zarr

ms, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
out.mkdir(parents=False, exist_ok=False)
with table(str(ms), ack=False) as t:
    flags, rows = t.getcol("FLAG"), t.getcol("FLAG_ROW")
command = [
    "goquartical",
    f"input_ms.path={ms}",
    "input_ms.data_column=DATA",
    "input_ms.weight_column=WEIGHT_SPECTRUM",
    "input_model.recipe=MODEL_DATA",
    "solver.terms=[G]",
    "G.type=complex",
    "G.time_interval=2",
    "G.freq_interval=32",
    "solver.iter_recipe=[50]",
    "solver.convergence_criteria=1e-7",
    "solver.reference_antenna=0",
    "solver.robust=false",
    "mad_flags.enable=false",
    "output.flags=false",
    "output.overwrite=false",
    f"output.gain_directory={out / 'gains.qc'}",
    f"output.log_directory={out / 'logs.qc'}",
    "dask.threads=1",
    "solver.threads=1",
    "dask.scheduler=single-threaded",
]
(out / "command.json").write_text(json.dumps(command, indent=1) + "\n")
started = time.perf_counter()
with (out / "quartical.log").open("x") as log:
    code = subprocess.run(
        command, stdout=log, stderr=subprocess.STDOUT, check=False
    ).returncode
seconds = time.perf_counter() - started
with table(str(ms), ack=False) as t:
    unchanged = np.array_equal(t.getcol("FLAG"), flags) and np.array_equal(
        t.getcol("FLAG_ROW"), rows
    )
summary = {"returncode": code, "seconds": seconds, "flags_unchanged": bool(unchanged)}
if code == 0:
    (ds,) = xds_from_zarr(f"{out / 'gains.qc'}::G")
    ds = ds.compute()
    gains = ds.gains.transpose(
        "gain_time", "gain_freq", "antenna", "direction", "correlation"
    ).values[..., 0, :]
    gflags = ds.gain_flags.transpose("gain_time", "gain_freq", "antenna", "direction")
    np.save(out / "gains.npy", gains.reshape(*gains.shape[:3], 2, 2))
    np.save(out / "gain_flags.npy", gflags.values[..., 0])
    summary.update(
        {
            "type": ds.attrs.get("TYPE"),
            "shape": list(gains.shape),
            "conv_iter": np.asarray(
                ds.attrs.get("conv_iter", ds.get("conv_iter", -1))
            ).tolist(),
            "conv_perc": np.asarray(
                ds.attrs.get("conv_perc", ds.get("conv_perc", -1))
            ).tolist(),
            "flagged_gain_fraction": float(np.mean(gflags.values != 0)),
        }
    )
(out / "summary.json").write_text(json.dumps(summary, indent=1, default=str) + "\n")
print(
    json.dumps(
        {k: v for k, v in summary.items() if k not in ("conv_iter",)}, default=str
    )
)
if code or not unchanged:
    raise SystemExit("QuartiCal failed or altered flags")
