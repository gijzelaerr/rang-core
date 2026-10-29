"""Dump Measurement Set columns once with python-casacore (the task E oracle).

Usage: python examples/oracle_ms_columns.py <fresh-output-dir> <ms> [<ms> ...]

Runs where python-casacore is (the pinned `rang-flagging:local` image). For
every Measurement Set it reads the main-table columns the Rang core needs and
every column of the ANTENNA, FIELD, SPECTRAL_WINDOW and POLARIZATION subtables
with `getcol`, and writes one `<label>.npz` per table plus `receipt.json`
with dtypes, shapes, SHA256 of every table file and the wall time of each
`getcol`. String columns are stored as JSON lists next to the arrays. It
never writes the MS (read-only, autonoread locking).
"""

import json
import sys
import time
from hashlib import sha256
from pathlib import Path

import numpy as np
from casacore.tables import table

MAIN_COLUMNS = (
    "TIME",
    "ANTENNA1",
    "ANTENNA2",
    "UVW",
    "DATA",
    "CORRECTED_DATA",
    "MODEL_DATA",
    "FLAG",
    "FLAG_ROW",
    "WEIGHT",
    "WEIGHT_SPECTRUM",
    "SIGMA",
    "DATA_DESC_ID",
    "FIELD_ID",
    "SCAN_NUMBER",
    "INTERVAL",
    "EXPOSURE",
    "OBSERVATION_ID",
    "ARRAY_ID",
    "FEED1",
    "FEED2",
    "PROCESSOR_ID",
    "STATE_ID",
    "TIME_CENTROID",
)
SUBTABLES = ("ANTENNA", "FIELD", "SPECTRAL_WINDOW", "POLARIZATION")


def file_hashes(ms):
    return {
        str(p.relative_to(ms)): sha256(p.read_bytes()).hexdigest()
        for p in sorted(Path(ms).rglob("*"))
        if p.is_file() and p.name != "table.lock"
    }


def dump_table(path, columns, out, label):
    arrays, strings, info = {}, {}, {}
    with table(str(path), readonly=True, ack=False, lockoptions="autonoread") as t:
        names = [c for c in columns if c in t.colnames()] if columns else t.colnames()
        dminfo = {
            v["NAME"]: {
                "TYPE": v["TYPE"],
                "COLUMNS": [str(c) for c in v["COLUMNS"]],
                "SPEC": {
                    k: (x.tolist() if hasattr(x, "tolist") else x)
                    for k, x in v.get("SPEC", {}).items()
                    if k != "HYPERCUBES"
                },
            }
            for v in t.getdminfo().values()
        }
        for name in names:
            started = time.perf_counter()
            try:
                value = t.getcol(name)
            except RuntimeError as error:
                info[name] = {"error": str(error)}
                continue
            seconds = time.perf_counter() - started
            desc = t.getcoldesc(name)
            entry = {
                "seconds": seconds,
                "valueType": desc["valueType"],
                "ndim": int(desc.get("ndim", 0)),
                "dataManagerType": desc.get("dataManagerType"),
                "dataManagerGroup": desc.get("dataManagerGroup"),
            }
            if isinstance(value, np.ndarray):
                if value.dtype.kind in "OU":
                    strings[name] = np.asarray(value).tolist()
                    entry["kind"] = "string"
                    entry["shape"] = list(np.asarray(value).shape)
                else:
                    arrays[name] = np.ascontiguousarray(value)
                    entry["kind"] = "array"
                    entry["shape"] = list(value.shape)
                    entry["dtype"] = str(value.dtype)
            else:
                strings[name] = list(value)
                entry["kind"] = "string"
                entry["shape"] = [len(value)]
            info[name] = entry
        nrows = t.nrows()
    np.savez(out / f"{label}.npz", **arrays)
    (out / f"{label}.strings.json").write_text(json.dumps(strings) + "\n")
    return {"path": str(path), "nrows": nrows, "columns": info, "dminfo": dminfo}


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=False)
    receipt = {"oracle": "python-casacore getcol", "tables": {}}
    try:
        import casacore

        receipt["python_casacore"] = casacore.__version__
    except AttributeError:
        pass
    receipt["numpy"] = np.__version__
    for index, ms in enumerate(sys.argv[2:]):
        ms = Path(ms)
        label = f"ms{index}"
        started = time.perf_counter()
        receipt["tables"][label] = dump_table(ms, MAIN_COLUMNS, out, label)
        receipt["tables"][label]["ms_file_sha256"] = file_hashes(ms)
        for sub in SUBTABLES:
            receipt["tables"][f"{label}.{sub}"] = dump_table(
                ms / sub, None, out, f"{label}.{sub}"
            )
        receipt["tables"][label]["wall_seconds"] = time.perf_counter() - started
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1, default=str) + "\n")
    for label, entry in receipt["tables"].items():
        print(label, entry["nrows"], "rows", len(entry["columns"]), "columns")


if __name__ == "__main__":
    main()
