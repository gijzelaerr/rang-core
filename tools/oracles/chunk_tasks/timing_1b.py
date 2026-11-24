# SPDX-License-Identifier: MIT
"""The timing runs of research/chunk-task-api-1b.md section 5 on nash.

    python timing_1b.py point RUN CONFIG REPEAT
    python timing_1b.py matrix RUN
    python timing_1b.py report RUN

Stage 1's driver (`timing.py`: exclusive holds queued only on an idle lock,
the load record and void rule of chunk-task-api 5.1, hashes after each
stage) with section 5's case: flag (CARACal's first pass), the K, G, B chain
of case W, apply. B is main e071bdab (`RANG_CTA_ORACLE`), N1-N8 this branch
(`RANG_CTA_CODE`), `memory_limit_gb: 32`, T = 16. One repeat per point
unless `RANG_CTA_REPEATS` says more. Environment as `timing.py`.
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import run_1b  # stage 1b's cases
import timing

timing.SCRIPT = HERE
timing.REPEATS = int(os.environ.get("RANG_CTA_REPEATS") or 1)


def config_text(config, ms):
    strategy = Path(os.environ["RANG_CTA_STRATEGY"]).as_posix()
    lines = timing._data_lines(config)
    block = "data:\n" + "".join(f"  {d}\n" for d in lines)
    return run_1b.WHOLE % {"data": block + f"flag: {{strategy: {strategy}}}\n"}


timing.config_text = config_text

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "point":
        sys.exit(timing.point(sys.argv[2], sys.argv[3], int(sys.argv[4])))
    elif cmd == "matrix":
        timing.matrix(sys.argv[2])
    elif cmd == "report":
        timing.report(sys.argv[2])
    else:
        raise SystemExit(__doc__)
