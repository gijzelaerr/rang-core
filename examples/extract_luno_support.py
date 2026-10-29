"""Offline extraction for the LUNO processed-support survey (run in the pinned container).

Decodes the bounded slice from tools/flagging/fetch-luno-support.sh and writes the
four-station cross rows plus whole-array counts as .npy/.json into a fresh directory.
Numeric arrays must have no filter; ANTENNA NAME must be json2 (plain JSON, no pickle).
"""

import json
import pathlib
import sys

import numcodecs
import numpy as np

root, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
STATIONS = (0, 1, 2, 3)
TILES = range(8, 24)
out.mkdir(parents=False, exist_ok=False)


def chunk(array_dir, key):
    meta = json.loads((root / array_dir / ".zarray").read_text())
    if meta["compressor"]["id"] != "blosc":
        raise ValueError(f"unexpected compressor in {array_dir}")
    raw = numcodecs.Blosc().decode((root / array_dir / key).read_bytes())
    if meta["dtype"] == "|O":
        if [f["id"] for f in meta["filters"] or []] != ["json2"]:
            raise ValueError(f"refusing {array_dir}: object array without json2")
        items = json.loads(raw.decode("utf-8"))
        if items[-2] != "|O":
            raise ValueError(f"{array_dir} json2 trailer mismatch")
        return items[:-2]
    if meta.get("filters") or "O" in meta["dtype"]:
        raise ValueError(f"refusing {array_dir}: filters/object dtype")
    shape = [
        min(c, s - int(i) * c)
        for c, s, i in zip(meta["chunks"], meta["shape"], key.split("."))
    ]
    full = np.frombuffer(raw, dtype=np.dtype(meta["dtype"])).reshape(meta["chunks"])
    return full[tuple(slice(0, n) for n in shape)]


names = chunk("ANTENNA/ANTENNA_0/NAME", "0")
summary = {"antenna_names": names, "stations": list(STATIONS), "groups": {}}
for group in (1, 2):
    main = f"MAIN/MAIN_{group}"
    attrs = json.loads((root / main / ".zattrs").read_text())
    a1, a2 = chunk(f"{main}/ANTENNA1", "0"), chunk(f"{main}/ANTENNA2", "0")
    time, frow = chunk(f"{main}/TIME", "0"), chunk(f"{main}/FLAG_ROW", "0")
    cross = a1 != a2
    keep = cross & np.isin(a1, STATIONS) & np.isin(a2, STATIONS) & ~frow
    flags, weights, models = [], [], []
    per_antenna = np.zeros(len(names), dtype=np.int64)
    model_nonzero, train_total = np.zeros(4, dtype=np.int64), 0
    for tile in TILES:
        f = chunk(f"{main}/FLAG", f"0.{tile}.0")
        w = chunk(f"{main}/WEIGHT_SPECTRUM", f"0.{tile}.0")
        m = chunk(f"{main}/MODEL_DATA", f"0.{tile}.0")
        train = (
            (cross & ~frow)[:, None]
            & ~f.any(-1)
            & (w > 0).all(-1)
            & np.isfinite(m).all(-1)
        )
        cells = train.sum(1)
        np.add.at(per_antenna, a1, cells)
        np.add.at(per_antenna, a2, cells)
        model_nonzero += (np.abs(m[train]) > 0).sum(0)
        train_total += int(train.sum())
        flags.append(f[keep])
        weights.append(w[keep])
        models.append(m[keep])
    directory = out / f"group{group}"
    directory.mkdir()
    for name, value in (
        ("antenna1", a1[keep]),
        ("antenna2", a2[keep]),
        ("time", time[keep]),
        ("flag", np.concatenate(flags, 1)),
        ("weight", np.concatenate(weights, 1)),
        ("model", np.concatenate(models, 1)),
    ):
        np.save(directory / f"{name}.npy", np.ascontiguousarray(value))
    summary["groups"][group] = {
        "field": attrs.get("FIELD_ID"),
        "scan": attrs.get("SCAN_NUMBER"),
        "chunk_rows": int(a1.size),
        "chunk_integrations": int(np.unique(time).size),
        "flag_row_fraction": float(frow.mean()),
        "four_station_rows": int(keep.sum()),
        "whole_array_train_cells": train_total,
        "whole_array_model_nonzero_fraction_per_corr": (
            model_nonzero / max(train_total, 1)
        ).tolist(),
        "per_antenna_train_cells": {
            f"{i}:{n}": int(c) for i, (n, c) in enumerate(zip(names, per_antenna))
        },
    }
(out / "extract.json").write_text(json.dumps(summary, indent=1) + "\n")
print(json.dumps({g: v["four_station_rows"] for g, v in summary["groups"].items()}))
