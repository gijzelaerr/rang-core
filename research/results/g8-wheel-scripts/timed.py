"""timed.py OUT CMD...: run CMD, write its wall time (s) and exit status to OUT (task G8);
used inside tools/heavy_lock.py so that waiting for the lock is not counted."""

import subprocess
import sys
import time
from pathlib import Path

t = time.perf_counter()
rc = subprocess.call(sys.argv[2:])
Path(sys.argv[1]).write_text(f"{time.perf_counter() - t:.1f} {rc}\n")
sys.exit(rc)
