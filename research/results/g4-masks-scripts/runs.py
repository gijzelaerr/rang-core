"""runs.py: the runs of research/g4-masks.md, section 3, for both imagers.

    runs.py g BIN TAG RUN   GeMClean natively on Windows into $O/runs/TAG/RUN/g-*
    runs.py w RUN           WSClean 3.7 (rang-wsclean-native:3.7) from WSL into $O/runs/wsclean/RUN/w-*

Run each under tools/heavy_lock.py. $G4_OUT (default D:/rang/outputs/g4-20261109-01, or
/mnt/d/rang/outputs/g4-20261109-01 from WSL) holds runs/, masks/ and runs.tsv. Held-out H reads
$G4_HELD (default .../g4-20261109-03).
"""

import os
import subprocess
import sys
import time
from pathlib import Path

WSL = sys.platform != "win32"
D = "/mnt/d" if WSL else "D:"
O = Path(os.environ.get("G4_OUT", f"{D}/rang/outputs/g4-20261109-01"))
HELD = Path(os.environ.get("G4_HELD", f"{D}/rang/outputs/g4-20261109-03"))
BENCH = f"{D}/rang/outputs/20261102-gemclean/bench/data"
H4 = f"{D}/rang/outputs/20261103-gemclean-heldout/sim/data/h4.ms"
PILOT = f"{D}/rang/outputs/20261103-gemclean-heldout/real/cal2.ms"
G3 = f"{D}/rang/outputs/20261106-g3-spectral/data"

BASE = [
    "-weight",
    "briggs",
    "0.5",
    "-niter",
    "1000000",
    "-gain",
    "0.1",
    "-mgain",
    "0.8",
    "-nmiter",
    "1000",
    "-data-column",
    "DATA",
    "-field",
    "0",
    "-j",
    "16",
]
SIM = ["-size", "2048", "2048", "-scale", "1.5asec"]
THR = ["-abs-threshold", "0.0001"]
AUTO = ["-auto-mask", "6", "-auto-threshold", "1"]
DIRTY = ["-niter", "0"]


def mask(name):
    """The truth mask, as each imager sees the output directory."""
    return f"/out/masks/{name}" if WSL else str(O / "masks" / name)


def run_args(run):
    s2 = f"{BENCH}/s2.ms"
    table = {
        "T0": (s2, SIM + THR + DIRTY),
        "T1": (s2, SIM + THR + DIRTY + ["-taper-gaussian", "10"]),
        "T2": (s2, SIM + THR + DIRTY + ["-minuv-l", "300", "-maxuv-l", "20000"]),
        "T3": (s2, SIM + THR + DIRTY + ["-minuvw-m", "150", "-maxuvw-m", "5000"]),
        "T4": (
            s2,
            SIM
            + THR
            + DIRTY
            + [
                "-minuv-l",
                "300",
                "-taper-inner-tukey",
                "200",
                "-maxuv-l",
                "20000",
                "-taper-tukey",
                "5000",
            ],
        ),
        "T5": (
            f"{G3}/D2.ms",
            SIM
            + THR
            + DIRTY
            + [
                "-channels-out",
                "4",
                "-join-channels",
                "-taper-gaussian",
                "8asec",
                "-minuv-l",
                "300",
            ],
        ),
        "T6": (
            s2,
            SIM + THR + DIRTY + ["-taper-edge", "2000", "-taper-edge-tukey", "1000"],
        ),
        # T6' (post hoc, section 6): an edge that reaches the data (T6's 2000 does not).
        "T6p": (
            s2,
            SIM + THR + DIRTY + ["-taper-edge", "35000", "-taper-edge-tukey", "5000"],
        ),
        "F1": (s2, SIM + THR + ["-fits-mask", mask("s2-truth.fits")]),
        "F2": (s2, SIM + THR + ["-fits-mask", mask("s2-truth.fits"), "-multiscale"]),
        "A1": (s2, SIM + AUTO),
        "A2": (H4, SIM + AUTO + ["-multiscale"]),
        "A3": (
            H4,
            SIM + AUTO + ["-multiscale", "-taper-gaussian", "8asec", "-minuv-l", "300"],
        ),
        "A4": (
            f"{G3}/D2.ms",
            SIM
            + AUTO
            + ["-channels-out", "4", "-join-channels", "-fit-spectral-pol", "2"],
        ),
        "P": (
            PILOT,
            ["-size", "4096", "4096", "-scale", "3asec", "-multiscale"] + AUTO,
        ),
        "H": (
            str(HELD / "data" / "h.ms"),
            SIM
            + AUTO
            + [
                "-multiscale",
                "-taper-gaussian",
                "8asec",
                "-minuv-l",
                "300",
                "-maxuvw-m",
                "6000",
            ],
        ),
    }
    return table[run]


def log_row(tag, run, rc, wall, what):
    with open(O / "runs.tsv", "a") as f:
        f.write(f"{tag}\t{run}\t{rc}\t{wall:.1f}\t{what}\n")


def main():
    mode = sys.argv[1]
    if mode == "g":
        binary, tag, run = sys.argv[2:5]
        extra = sys.argv[5:]
        ms, opts = run_args(run)
        d = O / "runs" / tag / run
        d.mkdir(parents=True, exist_ok=True)
        cmd = [binary, "-name", str(d / "g"), *BASE, *opts, *extra, ms]
        t = time.time()
        with open(d / "log.txt", "w") as log:
            rc = subprocess.call(cmd, stdout=log, stderr=subprocess.STDOUT)
        wall = time.time() - t
        log_row(tag, run, rc, wall, Path(binary).name)
    else:
        run = sys.argv[2]
        extra = sys.argv[3:]
        ms, opts = run_args(run)
        d = O / "runs" / "wsclean" / run
        (d / "tmp").mkdir(parents=True, exist_ok=True)
        data, name = os.path.dirname(ms), os.path.basename(ms)
        uid = f"{os.getuid()}:{os.getgid()}"
        cmd = [
            "docker",
            "run",
            "--rm",
            "--user",
            uid,
            "--network",
            "none",
            "-e",
            "HOME=/tmp",
            "-e",
            "OMP_NUM_THREADS=16",
            "-v",
            f"{data}:/data:ro",
            "-v",
            f"{d}:/run",
            "-v",
            f"{O}:/out:ro",
            "-w",
            "/run",
            "rang-wsclean-native:3.7",
            "/usr/bin/time",
            "-v",
            "-o",
            "/run/time.txt",
            "wsclean",
            "-gridder",
            "wgridder",
            "-no-min-grid-resolution",
            "-wgridder-accuracy",
            "1e-6",
            "-pol",
            "I",
            "-no-update-model-required",
            "-temp-dir",
            "/run/tmp",
            *BASE,
            *opts,
            *extra,
            "-name",
            "/run/w",
            f"/data/{name}",
        ]
        t = time.time()
        with open(d / "log.txt", "w") as log:
            rc = subprocess.call(cmd, stdout=log, stderr=subprocess.STDOUT)
        wall = time.time() - t
        try:
            (d / "tmp").rmdir()
        except OSError:
            pass
        log_row("wsclean", run, rc, wall, "rang-wsclean-native:3.7")
    print(f"{mode} {run} rc={rc} wall={wall:.1f}s")
    sys.exit(rc)


if __name__ == "__main__":
    main()
