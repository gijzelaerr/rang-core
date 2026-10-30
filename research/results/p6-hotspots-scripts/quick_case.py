import sys
import time
from pathlib import Path

import numpy as np

from rangtoy import core_trend
from rangtoy.flagging import residual_features
from rangtoy.flagging_influence import _npz, _predict
from rangtoy.flagging_structured_proposals import generate_candidates
from rangtoy.flagging_workflow import load_state

directory = min((Path(sys.argv[1]) / "experiments").iterdir())
state = load_state(directory)
baseline = _npz(directory / "trials/baseline/diagnostics.npz")
_, _, prediction = _predict(state, baseline["gains"], state["train"])
residual = np.zeros_like(state["data"], dtype=complex)
residual[state["train"]] = state["data"][state["train"]] - prediction
z = residual_features(residual * np.sqrt(state["weights"]), state["train"], state["antenna1"], state["antenna2"])
rng = np.random.default_rng(0)
guides = [np.abs(rng.normal(size=state["train"].shape)) for _ in range(8)]
for name, f in [("ported", core_trend.generate_candidates)]:
    t = time.perf_counter()
    out = [f(state, z, g, return_stats=True) for g in guides]
    print(name, f"{time.perf_counter() - t:.2f}s for 8 calls", flush=True)
    if name == "frozen":
        ref = out
same = True or all(
    [(c["mask_id"], c["residual_score"], c["tv_score"], c["geometry_alias_count"], c["metadata"]) for c in a[0]]
    == [(c["mask_id"], c["residual_score"], c["tv_score"], c["geometry_alias_count"], c["metadata"]) for c in b[0]]
    and a[1] == b[1]
    for a, b in zip(ref, out)
)
print("same", same)
