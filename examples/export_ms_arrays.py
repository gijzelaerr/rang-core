"""Export Measurement Set MAIN columns to one NumPy archive (run where casacore is).

Usage: python examples/export_ms_arrays.py <ms> <fresh-output-dir> [COLUMN ...]

This is the Rang core's MS edge for validation: it reads columns once with
python-casacore and writes `arrays.npz` plus `receipt.json` (column shapes,
dtypes and the table's file hashes) into a new directory. It never writes the
MS. Default columns are the ones the gain solver needs.
"""

import json
import sys
from hashlib import sha256
from pathlib import Path

import numpy as np
from casacore.tables import table

DEFAULT = (
    "DATA",
    "MODEL_DATA",
    "FLAG",
    "FLAG_ROW",
    "WEIGHT_SPECTRUM",
    "ANTENNA1",
    "ANTENNA2",
    "TIME",
)


def main():
    ms, out = Path(sys.argv[1]), Path(sys.argv[2])
    columns = tuple(sys.argv[3:]) or DEFAULT
    out.mkdir(parents=True, exist_ok=False)
    files = {
        str(p.relative_to(ms)): sha256(p.read_bytes()).hexdigest()
        for p in sorted(ms.rglob("*"))
        if p.is_file() and p.name != "table.lock"
    }
    arrays = {}
    with table(str(ms), readonly=True, ack=False, lockoptions="autonoread") as t:
        for name in columns:
            arrays[name] = np.ascontiguousarray(t.getcol(name))
    np.savez(out / "arrays.npz", **arrays)
    receipt = {
        "ms": str(ms),
        "columns": {k: [list(v.shape), str(v.dtype)] for k, v in arrays.items()},
        "ms_file_sha256": files,
        "arrays_sha256": sha256((out / "arrays.npz").read_bytes()).hexdigest(),
    }
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1) + "\n")
    print(json.dumps({k: v for k, v in receipt.items() if k != "ms_file_sha256"}))


if __name__ == "__main__":
    main()
