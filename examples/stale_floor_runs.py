"""The stale-floor test (research/stale-floor.md). Each group of runs takes the heavy lock on its own.

Paths come from the environment, with this host's defaults: B (a gemclean built on this branch), PY, BENCH,
HELD, W (scratch for Measurement Set copies), O (outputs), LOCK.
"""

import os
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
BIN = os.environ.get("B", str(HERE.parent / "core/target/release/gemclean"))
PY = os.environ.get("PY", "/home/gijsm/Github/rang/.venv/bin/python")
BENCH = Path(os.environ.get("BENCH", "/mnt/d/rang/outputs/20261102-gemclean/bench/data"))
HELD = Path(os.environ.get("HELD", "/mnt/d/rang/outputs/20261103-gemclean-heldout/sim/data"))
W = Path(os.environ.get("W", "/home/gijsm/Build/tmp/20261103-stale-floor"))
O = Path(os.environ.get("O", "/mnt/d/rang/outputs/20261103-stale-floor"))
LOCK = os.environ.get("LOCK", "/home/gijsm/.rang-heavy.lock")
SCALE = 1.5


def locked(*argv):
    return subprocess.run(["flock", LOCK, *map(str, argv)], check=False).returncode


def one(name, size, ms, added, floor):
    """A run and its row; the lock is held for the run and released for the score."""
    argv = [BIN, "-name", O / name, "-size", size, size, "-scale", f"{SCALE}asec", "-weight", "briggs", "0.5"]
    argv += ["-niter", "1000000", "-gain", "0.1", "-nmiter", "1000", "-abs-threshold", "100e-6"]
    argv += ["-data-column", "DATA", "-field", "0", "-j", "8", "-stale-floor", floor, ms]
    with open(O / f"{name}.log", "w") as log:
        code = subprocess.run(["flock", LOCK, *map(str, argv)], stdout=log, stderr=log, check=False).returncode
    print(name, "exit", code, flush=True)
    subprocess.run([PY, "-I", str(HERE / "stale_floor_score.py"), str(O / name), str(added), str(O / "rows.jsonl")], check=False)


def sky(name, size, source, jy, offset, floors):
    """A copy of the sky with the source added, then one run per floor."""
    ms = W / f"{name}.ms"
    shutil.rmtree(ms, ignore_errors=True)
    shutil.copytree(source, ms)
    add = subprocess.run([PY, "-I", str(HERE / "stale_floor_add.py"), str(ms), str(jy), str(offset), str(SCALE)], check=False)
    if add.returncode != 0:
        raise SystemExit(f"{name}: no source added")
    for f in floors:
        one(f"{name}-f{f}", size, ms, jy, f)
    shutil.rmtree(ms)


def main():
    W.mkdir(parents=True, exist_ok=True)
    O.mkdir(parents=True, exist_ok=True)
    # 1. No change at 0.01 on the ordinary skies; S1 at 0.05 to see what a binding floor does.
    for s in ("s1", "s2", "s3"):
        one(f"{s}-f0.01", 2048, BENCH / f"{s}.ms", 0, 0.01)
    one("s1-f0.05", 2048, BENCH / "s1.ms", 0, 0.05)
    for s, size in (("h1", 2048), ("h2", 2048), ("h3", 4096), ("h4", 2048)):
        one(f"{s}-f0.01", size, HELD / f"{s}.ms", 0, 0.01)
    # 2. The failure cases the floor was chosen against.
    sky("s1-plus10", 2048, BENCH / "s1.ms", 10, 0, [0.01])
    sky("s1-plus30", 2048, BENCH / "s1.ms", 30, 0, [0.01, 0.02, 0.05])
    sky("s1-plus100", 2048, BENCH / "s1.ms", 100, 0, [0.01, 0.02, 0.05])
    sky("s1-plus1000", 2048, BENCH / "s1.ms", 1000, 0, [0, 0.01])
    # 3. Failure cases not used to choose it.
    sky("h1-plus30", 2048, HELD / "h1.ms", 30, 0, [0, 0.01])
    sky("h4-plus30", 2048, HELD / "h4.ms", 30, 0, [0, 0.01])
    sky("s2-plus30-off20", 2048, BENCH / "s2.ms", 30, 20, [0, 0.01])
    sky("h3-plus100", 4096, HELD / "h3.ms", 100, 0, [0, 0.01])
    shutil.rmtree(W, ignore_errors=True)
    print("finished", flush=True)


if __name__ == "__main__":
    main()
