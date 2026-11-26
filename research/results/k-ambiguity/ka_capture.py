# SPDX-License-Identifier: MIT
"""research/k-ambiguity.md section 4 step 1: run `rang-core` in this process
with `rang.cal_delay.solve` wrapped, saving the arrays and settings of every
non-trace call (one per K solve and chunk) to `OUT-<n>.npz`, and the result's
settings beside them.

    python ka_capture.py OUT -- calibrate CONFIG MS --run-dir DIR
"""

import json
import sys

import numpy as np
from rang import cal_delay, core_cli

_solve = cal_delay.solve
NAMES = (
    "data",
    "model",
    "weights",
    "flag",
    "flag_row",
    "antenna1",
    "antenna2",
    "time_bin",
)
CALLS = []


def main(out, argv):
    def capture(*args, **kwargs):
        sol = _solve(*args, **kwargs)
        if kwargs.get("trace"):
            return sol
        n = len(CALLS)
        arrays = {k: np.asarray(v) for k, v in zip(NAMES, args)}
        arrays["chan_freq"] = np.asarray(kwargs["chan_freq"], float)
        kw = {k: v for k, v in kwargs.items() if k != "chan_freq"}
        np.savez(f"{out}-{n}.npz", **arrays)
        rec = {
            "kwargs": {k: (v if isinstance(v, (int, float, str, bool, list, type(None)))
                           else str(v)) for k, v in kw.items()},
            "settings": sol.settings,
            "delays_ns": np.asarray(sol.delays).tolist(),
            "flags": np.asarray(sol.flags).tolist(),
            "refant_used": np.asarray(sol.refant_used).tolist(),
            "iterations": sol.iterations,
        }  # fmt: skip
        with open(f"{out}-{n}.json", "w") as f:
            json.dump(rec, f, default=str)
        CALLS.append(n)
        return sol

    cal_delay.solve = capture
    try:
        rc = core_cli.main(argv)
    finally:
        cal_delay.solve = _solve
    print(json.dumps({"calls": len(CALLS), "rc": rc}))
    return rc or 0


if __name__ == "__main__":
    i = sys.argv.index("--")
    sys.exit(main(sys.argv[1], sys.argv[i + 1 :]))
