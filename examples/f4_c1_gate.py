# SPDX-License-Identifier: MIT
"""F4 C1(U4) attempt gate (research/f4-flagger.md, "Rerun rule", 2026-11-17).

Usage: python examples/f4_c1_gate.py [f4_cost.py arguments ...]

Inside the exclusive hold, samples system CPU for 10 s; if processes other
than this one use more than one logical CPU, writes $RUN_DIR/skipped.json
and exits 3 without timing (a skipped attempt). Otherwise runs
examples/f4_cost.py with the given arguments in this process's environment.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import psutil

HERE = Path(__file__).resolve().parent


def main():
    me = psutil.Process()
    me.cpu_percent(None)
    total = psutil.cpu_percent(interval=10.0)
    other = max(total * psutil.cpu_count() / 100 - me.cpu_percent(None) / 100, 0.0)
    rec = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "other_cpus_10s": other}
    print(json.dumps(rec), flush=True)
    if other > 1.0:
        Path(os.environ["RUN_DIR"], "skipped.json").write_text(json.dumps(rec) + "\n")
        sys.exit(3)
    sys.exit(subprocess.call([sys.executable, str(HERE / "f4_cost.py"), *sys.argv[1:]]))


if __name__ == "__main__":
    main()
