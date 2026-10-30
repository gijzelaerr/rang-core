"""A-FLAG post-hoc: stage measures of the S1 variants (worktree venv; reads outputs/aflag-20261030-15-s1-variants)."""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[4]
spec = importlib.util.spec_from_file_location("compare_aoflagger", W / "examples/compare_aoflagger.py")
compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)
S = W / "outputs/aflag-20261030-15-s1-variants"
O = W / "outputs/core-d-oracle-20261029-01/run"
S1 = W / "outputs/aflag-20261030-14-dump"
result = {}
for label in compare.CONTROLS:
    st = np.load(O / label / "stages.npz")
    names = list(st.files)
    ubl = np.load(O / label / "arrays.npz")["ubl"]
    v = np.load(S / f"s1v-{label}.npz")
    s1 = np.load(S1 / f"s1-{label}.npz")
    result[label] = {}
    for key in s1.files:
        k = int(key[1:])
        before = np.asarray(st[names[k - 1]][:, 0], bool)
        ref = np.asarray(st[names[k]][:, 0], bool)
        autos = np.broadcast_to((ubl[:, 1] == ubl[:, 2])[:, None, None], before.shape)
        row = {"tricolour_new": int((ref & ~before).sum())}
        for name, arr in (("s1", s1[key]), ("values", v[f"values_{key}"]), ("tric_missing", v[f"tric_missing_{key}"])):
            m, _ = compare.stage_measures(np.asarray(arr[:, 0], bool), ref, before, autos)
            row[name] = {x: m["all"][x] for x in ("agree_fraction", "a_new", "a_only", "b_only")}
        result[label][names[k]] = row
        print(label[:22], names[k][:2], row["tricolour_new"],
              {n: (round(row[n]["agree_fraction"], 4), row[n]["a_new"]) for n in ("s1", "values", "tric_missing")})
(S / "measures.json").write_text(json.dumps(result, indent=1) + "\n")
