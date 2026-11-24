# SPDX-License-Identifier: MIT
"""Identity sweep of research/selfcal-mem-34.md (gate E for stage A): gemclean-mem-32's
sweep.py (G8's tiny MS, main's binary against this branch's, without and with -reorder),
its 21 cases plus single-image Stokes I cases that reach the compacted path of
`deconvolve`: double precision, the pilot's accuracy, multiscale, the misfit floor, the
certified stop rule, the gram operator and no plan reuse.

    sweep.py BASE_BINARY BRANCH_BINARY OUTDIR   -> OUTDIR/sweep.json
"""

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "sweep32", HERE.parent / "gemclean-mem-32" / "sweep.py"
)
sweep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sweep)

sweep.CASES.update(
    {
        "stokes-i-double": ["-double"],
        "stokes-i-accuracy-1e-6": ["-wgridder-accuracy", "1e-6"],
        "stokes-i-multiscale": ["-multiscale"],
        "stokes-i-multiscale-masked": ["-multiscale", "-auto-mask", "5"],
        "stokes-i-floor": ["-floor-iterations", "5"],
        "stokes-i-certified": ["-stop-rule", "certified"],
        "stokes-i-gram": ["-gram-operator", "4,0.5"],
        "stokes-i-no-plan-reuse": ["-no-plan-reuse"],
    }
)

if __name__ == "__main__":
    sweep.main()
