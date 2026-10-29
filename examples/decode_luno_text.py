"""Offline decode of the bounded LUNO text-metadata probe (run in the pinned container).

String arrays must use the json2 filter (plain JSON, no pickle); numeric arrays no filter.
Only the Blosc compressor is accepted. Prints a JSON summary per store.
"""

import collections
import json
import pathlib
import sys

import numcodecs
import numpy as np

root = pathlib.Path(sys.argv[1])
MAX_BYTES = 1 << 20
TERMS = (
    "quartical",
    "goquartical",
    "applycal",
    "calwt",
    "statwt",
    "initweights",
    "weight",
    "sigma",
    "flag",
    "aoflagger",
    "tricolour",
    "split",
    "mstransform",
    "average",
    "caracal",
    "katdal",
    "mvftoms",
    "model",
    "setjy",
    "crystalball",
)


def load(store, array):
    meta = json.loads((root / store / array / ".zarray").read_text())
    if meta["compressor"]["id"] != "blosc":
        raise ValueError(f"unexpected compressor in {array}")
    chunk = ".".join("0" for _ in meta["shape"])
    if meta["chunks"] != meta["shape"]:
        raise ValueError(f"{array} is not a single chunk")
    raw = numcodecs.Blosc().decode((root / store / array / chunk).read_bytes())
    if len(raw) > MAX_BYTES:
        raise ValueError(f"{array} decodes beyond the cap")
    if meta["dtype"] == "|O":
        if [f["id"] for f in meta["filters"] or []] != ["json2"]:
            raise ValueError(f"refusing {array}: object array without json2 filter")
        items = json.loads(raw.decode("utf-8"))
        if items[-2:] != ["|O", meta["shape"]]:
            raise ValueError(f"{array} json2 trailer mismatch")
        return np.array(items[:-2], dtype=object).reshape(meta["shape"])
    if meta.get("filters") or "O" in meta["dtype"]:
        raise ValueError(f"refusing {array}: filters/object dtype")
    return np.frombuffer(raw, dtype=np.dtype(meta["dtype"])).reshape(meta["shape"])


summary = {}
for store in ("LBAND_LUNO_CALIBRATORS.zarr", "LBAND_LUNO_TARGET.zarr"):
    obs = "OBSERVATION/OBSERVATION_0/"
    hist = {
        c: load(store, f"HISTORY/HISTORY_0/{c}")
        for c in (
            "TIME",
            "APPLICATION",
            "MESSAGE",
            "ORIGIN",
            "PRIORITY",
            "APP_PARAMS",
            "CLI_COMMAND",
        )
    }
    rows = [
        " ".join(str(hist[c][i]) for c in hist if c != "TIME").lower()
        for i in range(hist["TIME"].size)
    ]
    t = hist["TIME"]
    summary[store] = {
        "project": load(store, obs + "PROJECT").tolist(),
        "observer": load(store, obs + "OBSERVER").tolist(),
        "schedule_type": load(store, obs + "SCHEDULE_TYPE").tolist(),
        "telescope": load(store, obs + "TELESCOPE_NAME").tolist(),
        "schedule": load(store, obs + "SCHEDULE").tolist(),
        "log": load(store, obs + "LOG").tolist(),
        "field_name": load(store, "FIELD/FIELD_0/NAME").tolist(),
        "field_code": load(store, "FIELD/FIELD_0/CODE").tolist(),
        "history_rows": int(t.size),
        "history_time_mjd_s": [float(t.min()), float(t.max())],
        "history_application_origin_counts": collections.Counter(
            f"{a} | {o}" for a, o in zip(hist["APPLICATION"], hist["ORIGIN"])
        ).most_common(),
        "history_priority_counts": collections.Counter(
            hist["PRIORITY"].tolist()
        ).most_common(),
        "history_nonempty_app_params": int(
            sum(bool(str(x[0]).strip()) for x in hist["APP_PARAMS"])
        ),
        "history_nonempty_cli_command": int(
            sum(bool(str(x[0]).strip()) for x in hist["CLI_COMMAND"])
        ),
        "history_term_row_counts_not_operation_proof": {
            term: sum(term in r for r in rows) for term in TERMS
        },
        "history_first_messages": [str(m) for m in hist["MESSAGE"][:40]],
        "history_unique_messages": len(set(hist["MESSAGE"].tolist())),
    }
print(json.dumps(summary, indent=1, default=str))
