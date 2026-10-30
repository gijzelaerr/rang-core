import sys
import time
from pathlib import Path

import numpy as np

from rangtoy.flagging import residual_features
from rangtoy.flagging_influence import _npz, _predict
from rangtoy.flagging_structured_proposals import generate_candidates
from rangtoy.flagging_workflow import load_state

mirror = Path(sys.argv[1])
for directory in sorted((mirror / "experiments").iterdir()):
    state = load_state(directory)
    baseline = _npz(directory / "trials/baseline/diagnostics.npz")
    _, _, prediction = _predict(state, baseline["gains"], state["train"])
    residual = np.zeros_like(state["data"], dtype=complex)
    residual[state["train"]] = state["data"][state["train"]] - prediction
    z = residual_features(
        residual * np.sqrt(state["weights"]),
        state["train"],
        state["antenna1"],
        state["antenna2"],
    )
    g = np.ones(state["train"].shape)
    t = time.perf_counter()
    family, stats = generate_candidates(state, z, g, return_stats=True)
    sizes = np.array([c["sample_count"] for c in family])
    print(directory.name, state["train"].shape, f"{time.perf_counter() - t:.2f}s", stats,
          "sizes", sizes.min(), np.median(sizes), sizes.max(), flush=True)
    break
