"""Build a four-station CASA MS from the bounded LUNO slices (run in the pinned container).

Inputs: the support slice (tools/flagging/fetch-luno-support.sh) for ANTENNA1/2, TIME,
FLAG_ROW, FLAG, WEIGHT_SPECTRUM and MODEL_DATA, and the solve inputs
(tools/flagging/fetch-luno-solve.sh) for subtables, other row columns and DATA.
With --dry-run, DATA is set to MODEL_DATA. Every array must be unfiltered numeric
or json2 (plain JSON); anything else is refused. Writes only the new MS.
"""

import json
import pathlib
import sys

import numcodecs
import numpy as np
from casacore.tables import default_ms, makearrcoldesc, maketabdesc, table

slice_dir, inputs, ms = (pathlib.Path(x) for x in sys.argv[1:4])
dry_run = sys.argv[4:] == ["--dry-run"]
STATIONS = (0, 1, 2, 3)
TILES = range(8, 24)
GROUP = "MAIN/MAIN_1"
if ms.exists():
    raise SystemExit(f"{ms} exists; choose a fresh path")


def decode(root, array_dir, key=None):
    meta = json.loads((root / array_dir / ".zarray").read_text())
    if meta["compressor"]["id"] != "blosc":
        raise ValueError(f"unexpected compressor in {array_dir}")
    key = key or ".".join("0" for _ in meta["shape"])
    raw = numcodecs.Blosc().decode((root / array_dir / key).read_bytes())
    if meta["dtype"] == "|O":
        if [f["id"] for f in meta["filters"] or []] != ["json2"]:
            raise ValueError(f"refusing {array_dir}: object array without json2")
        items = json.loads(raw.decode("utf-8"))
        return np.array(items[:-2], dtype=object).reshape(items[-1])
    if meta.get("filters") or "O" in meta["dtype"]:
        raise ValueError(f"refusing {array_dir}: filters/object dtype")
    index = [int(i) for i in key.split(".")]
    full = np.frombuffer(raw, dtype=np.dtype(meta["dtype"])).reshape(meta["chunks"])
    return full[
        tuple(
            slice(0, min(c, s - i * c))
            for c, s, i in zip(meta["chunks"], meta["shape"], index)
        )
    ]


a1, a2 = decode(slice_dir, f"{GROUP}/ANTENNA1"), decode(slice_dir, f"{GROUP}/ANTENNA2")
frow = decode(slice_dir, f"{GROUP}/FLAG_ROW")
keep = (a1 != a2) & np.isin(a1, STATIONS) & np.isin(a2, STATIONS) & ~frow
attrs = json.loads((slice_dir / GROUP / ".zattrs").read_text())


def tiles(root, column):
    return np.concatenate(
        [decode(root, f"{GROUP}/{column}", f"0.{t}.0")[keep] for t in TILES], axis=1
    )


main = {
    "ANTENNA1": a1[keep].astype(np.int32),
    "ANTENNA2": a2[keep].astype(np.int32),
    "TIME": decode(slice_dir, f"{GROUP}/TIME")[keep],
    "FLAG_ROW": frow[keep],
    "FLAG": tiles(slice_dir, "FLAG"),
    "WEIGHT_SPECTRUM": tiles(slice_dir, "WEIGHT_SPECTRUM"),
    "MODEL_DATA": tiles(slice_dir, "MODEL_DATA"),
}
for column in (
    "UVW",
    "INTERVAL",
    "EXPOSURE",
    "TIME_CENTROID",
    "FEED1",
    "FEED2",
    "ARRAY_ID",
    "OBSERVATION_ID",
    "PROCESSOR_ID",
    "STATE_ID",
    "SIGMA",
    "WEIGHT",
):
    main[column] = decode(inputs, f"{GROUP}/{column}")[keep]
main["DATA"] = main["MODEL_DATA"].copy() if dry_run else tiles(inputs, "DATA")
nrow, nchan = main["FLAG"].shape[:2]
main["SIGMA_SPECTRUM"] = np.where(
    main["WEIGHT_SPECTRUM"] > 0,
    1 / np.sqrt(np.maximum(main["WEIGHT_SPECTRUM"], 1e-30)),
    0,
).astype(np.float32)
for name in ("FIELD_ID", "DATA_DESC_ID", "SCAN_NUMBER"):
    main[name] = np.full(nrow, attrs[name], dtype=np.int32)

extra = maketabdesc(
    [
        makearrcoldesc(n, 0j, ndim=2, shape=[nchan, 4], valuetype="complex")
        for n in ("DATA", "MODEL_DATA")
    ]
    + [
        makearrcoldesc(n, 0.0, ndim=2, shape=[nchan, 4], valuetype="float")
        for n in ("WEIGHT_SPECTRUM", "SIGMA_SPECTRUM")
    ]
)
skipped = []
with default_ms(str(ms)) as t:
    t.addcols(extra)
    t.addrows(nrow)
    for name, value in main.items():
        t.putcol(name, np.ascontiguousarray(value))


def fill(name, rows=None, override=None):
    """Copy every decodable subtable column the MS descriptor knows."""
    # dask-ms may partition a subtable into NAME_0, NAME_1, ...; rows concatenate in order.
    groups = sorted(
        (p for p in (inputs / name).iterdir() if p.is_dir()),
        key=lambda p: int(p.name.rsplit("_", 1)[1]),
    )
    override = override or {}
    with table(f"{ms}::{name}", readonly=False, ack=False) as sub:
        parts = {}
        for root in groups:
            for directory in sorted(p for p in root.iterdir() if p.is_dir()):
                if directory.name not in sub.colnames():
                    continue
                try:
                    value = decode(root, directory.name)
                except (ValueError, FileNotFoundError) as error:
                    skipped.append(f"{name}.{directory.name}: {error}")
                    continue
                parts.setdefault(directory.name, []).append(value)
        columns = {k: np.concatenate(v) for k, v in parts.items()}
        columns.update(override)
        if not columns:
            skipped.append(f"{name}: no decodable columns")
            return
        n = len(next(iter(columns.values())))
        index = np.arange(n) if rows is None else rows(columns)
        sub.addrows(len(index))
        for column, value in columns.items():
            value = value[index]
            if value.dtype == object:
                value = np.array(value, dtype=str)
                value = list(value) if value.ndim == 1 else value
            try:
                sub.putcol(column, value)
            except RuntimeError as error:
                skipped.append(f"{name}.{column}: {error}")


fill("ANTENNA", rows=lambda c: np.array(STATIONS))
fill("FEED", rows=lambda c: np.flatnonzero(np.isin(c["ANTENNA_ID"], STATIONS)))
spw = inputs / "SPECTRAL_WINDOW" / "SPECTRAL_WINDOW_0"
channels = slice(TILES[0] * 128, (TILES[-1] + 1) * 128)
freq = decode(spw, "CHAN_FREQ")[:, channels]
width = decode(spw, "CHAN_WIDTH")[:, channels]
fill(
    "SPECTRAL_WINDOW",
    override={
        "NUM_CHAN": np.array([nchan], dtype=np.int32),
        "CHAN_FREQ": freq,
        "CHAN_WIDTH": width,
        "EFFECTIVE_BW": decode(spw, "EFFECTIVE_BW")[:, channels],
        "RESOLUTION": decode(spw, "RESOLUTION")[:, channels],
        "TOTAL_BANDWIDTH": np.array([np.abs(width).sum()]),
        "REF_FREQUENCY": freq[:, nchan // 2],
    },
)
for name in (
    "POLARIZATION",
    "DATA_DESCRIPTION",
    "FIELD",
    "OBSERVATION",
    "STATE",
    "PROCESSOR",
):
    fill(name)
print(
    json.dumps(
        {"rows": nrow, "channels": nchan, "dry_run": dry_run, "skipped": skipped}
    )
)
