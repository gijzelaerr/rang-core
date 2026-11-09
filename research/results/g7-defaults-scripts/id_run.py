"""id_run.py BIN TAG RUN FORM [extra...]: gate A of research/g7-defaults.md (section 2), natively on Windows.

Adapted from G4's id_run.py: -no-update-model-required on every run (G6 writes MODEL_DATA by
default), and the FITS files are kept when G7_KEEP=1 (for the restored-image check).

One GeMClean run without the G4 options at the settings of G5's id_run.sh (G2's identity set
s1 s2 s3 h1 h2 h3 h4 p256 in FORM def | coarse, G3's D1-C1 and D1-C3 in def), the SHA-256 of
every FITS file into <out>/identity/TAG/img/<name>.sha256, then the FITS files are deleted.
Run it under tools/heavy_lock.py. Output root: G7_ID_OUT (default D:/rang/outputs/g7-20261109-01).
"""

import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

O = Path(os.environ.get("G7_ID_OUT", "D:/rang/outputs/g7-20261109-01"))
B = "D:/rang/outputs/20261102-gemclean/bench/data"
H = "D:/rang/outputs/20261103-gemclean-heldout"
G3 = "D:/rang/outputs/20261106-g3-spectral/data"

RUNS = {
    "s1": (2048, 1.5, 0.0001, f"{B}/s1.ms", []),
    "s2": (2048, 1.5, 0.0001, f"{B}/s2.ms", []),
    "s3": (2048, 1.5, 0.0001, f"{B}/s3.ms", []),
    "h1": (2048, 1.5, 0.0001, f"{H}/sim/data/h1.ms", []),
    "h2": (2048, 1.5, 0.0001, f"{H}/sim/data/h2.ms", []),
    "h3": (4096, 1.5, 0.0001, f"{H}/sim/data/h3.ms", []),
    "h4": (2048, 1.5, 0.0001, f"{H}/sim/data/h4.ms", []),
    "p256": (4096, 3, 0.003, f"{H}/real/cal2.ms", []),
    "D1-C1": (
        2048,
        1.5,
        0.00015,
        f"{G3}/D1.ms",
        ["-channels-out", "8", "-join-channels", "-fit-spectral-pol", "4"],
    ),
    "D1-C3": (2048, 1.5, 0.0003, f"{G3}/D1.ms", ["-channels-out", "4"]),
}


def main():
    binary, tag, run, form, *extra = sys.argv[1:]
    size, scale, thr, ms, more = RUNS[run]
    name = f"{run}-{form}"
    d = O / "identity" / tag
    for sub in ("img", "log"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    f = ["-single", "-wgridder-accuracy", "1e-4"] if form == "coarse" else []
    cmd = [
        binary,
        "-name",
        str(d / "img" / name),
        "-size",
        str(size),
        str(size),
        "-scale",
        f"{scale}asec",
        "-weight",
        "briggs",
        "0.5",
        "-niter",
        "1000000",
        "-gain",
        "0.1",
        "-nmiter",
        "1000",
        "-abs-threshold",
        str(thr),
        "-data-column",
        "DATA",
        "-field",
        "0",
        "-j",
        "16",
        *more,
        *f,
        *extra,
        "-no-update-model-required",
        ms,
    ]
    t = time.time()
    with open(d / "log" / f"{name}.log", "w") as log:
        rc = subprocess.call(cmd, stdout=log, stderr=subprocess.STDOUT)
    wall = time.time() - t
    lines = []
    for p in sorted((d / "img").glob(f"{name}-*.fits")):
        lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}")
        if os.environ.get("G7_KEEP") != "1":
            p.unlink()
    (d / "img" / f"{name}.sha256").write_text("\n".join(lines) + "\n")
    print(f"{tag} {name} rc={rc} wall={wall:.1f}s files={len(lines)}")
    sys.exit(rc)


if __name__ == "__main__":
    main()
