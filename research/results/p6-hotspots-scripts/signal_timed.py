"""Diagnostic: wall and CPU inside selected functions during one signal run."""
import json
import sys
import time
from collections import defaultdict

import numpy as np

from rangtoy import core_signal, core_trend, flagging_influence, flagging_prospective

totals = defaultdict(lambda: [0, 0.0, 0.0])


def wrap(owner, name, label):
    original = getattr(owner, name)

    def timed(*args, **kwargs):
        w, c = time.perf_counter(), time.process_time()
        try:
            return original(*args, **kwargs)
        finally:
            entry = totals[label]
            entry[0] += 1
            entry[1] += time.perf_counter() - w
            entry[2] += time.process_time() - c

    setattr(owner, name, timed)


wrap(np.linalg, "cond", "np.linalg.cond")
wrap(np.linalg, "inv", "np.linalg.inv")
wrap(flagging_influence, "anchored_response", "anchored_response")
wrap(flagging_influence, "training_normals", "training_normals")
wrap(core_signal, "core_solve", "core_solve")
wrap(flagging_prospective, "generate_candidates", "generate_candidates")
run_dir, arm = sys.argv[1:3]
w, c = time.perf_counter(), time.process_time()
core_signal.run(run_dir, "outputs/tv-next-wsl-20261029-01/inputs",
                "outputs/core-phase3c-b-uvw-20261029-01", ported=arm == "new")
report = {"arm": arm, "wall": time.perf_counter() - w, "cpu": time.process_time() - c,
          "functions": {k: {"calls": v[0], "wall": round(v[1], 3), "cpu": round(v[2], 3)} for k, v in totals.items()}}
print(json.dumps(report))
