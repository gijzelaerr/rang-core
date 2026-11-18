# SPDX-License-Identifier: MIT
"""m_runs.py: arm M of research/wsclean38-rebaseline.md (amendment 1), on nash.

WSClean only, through rootless podman: the runs of research/gemclean-ms-mask.md, sections 3
and 7, with $W_IMAGE (default rang-wsclean-native:3.8). Copied from
results/gemclean-ms-mask-scripts/runs.py; the WSClean arguments are unchanged. Paths from
$MSM_OUT, $MSM_H4, $MSM_PILOT. Original docstring:

runs.py: the runs of research/gemclean-ms-mask.md, section 3, for both imagers.

    runs.py g BIN RUN   GeMClean natively on Windows into $O/runs/g/RUN/g-*
    runs.py w RUN       WSClean 3.7 (rang-wsclean-native:3.7) from WSL into $O/runs/wsclean/RUN/w-*

Run each under tools/heavy_lock.py (shared slots, 8 threads). $MSM_OUT (default
D:/rang/outputs/gemclean-ms-mask-20261117, or /mnt/d/... from WSL) holds runs/, masks/ and runs.tsv.
Adapted from research/results/g4-masks-scripts/runs.py.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

WSL = sys.platform != "win32"
D = "/mnt/d" if WSL else "D:"
O = Path(os.environ.get("MSM_OUT", f"{D}/rang/outputs/gemclean-ms-mask-20261117"))
H4 = os.environ.get(
    "MSM_H4", f"{D}/rang/outputs/20261103-gemclean-heldout/sim/data/h4.ms"
)
PILOT = os.environ.get(
    "MSM_PILOT", f"{D}/rang/outputs/20261103-gemclean-heldout/real/cal2.ms"
)
IMAGE = os.environ.get("W_IMAGE", "rang-wsclean-native:3.8")

BASE = [
    "-weight",
    "briggs",
    "0.5",
    "-niter",
    "10000000",
    "-gain",
    "0.1",
    "-mgain",
    "0.95",
    "-nmiter",
    "1000",
    "-data-column",
    "DATA",
    "-field",
    "0",
    "-j",
    "8",
]
SIM = ["-size", "2048", "2048", "-scale", "1.5asec", "-abs-threshold", "0.00004"]
REAL = ["-size", "4096", "4096", "-scale", "3asec", "-abs-threshold", "0.0003"]


def mask(name):
    """The mask, as each imager sees the output directory."""
    return f"/out/masks/{name}" if WSL else str(O / "masks" / name)


def run_args(run):
    table = {
        "RM": (H4, SIM + ["-fits-mask", mask("h4-points.fits"), "-multiscale"]),
        "RH": (H4, SIM + ["-fits-mask", mask("h4-points.fits")]),
        "PM": (PILOT, REAL + ["-fits-mask", mask("source-mask.fits"), "-multiscale"]),
    }
    # Post hoc (section 7): the comparison arms, one major iteration.
    table["RM1"] = table["RM"]
    table["PM1"] = table["PM"]
    return table[run]


def base(run):
    """BASE, with -nmiter 1 for the post hoc arms (section 7)."""
    if run.endswith("1"):
        i = BASE.index("-nmiter")
        return BASE[: i + 1] + ["1"] + BASE[i + 2 :]
    return BASE


def log_row(tag, run, rc, wall, what):
    with open(O / "runs.tsv", "a") as f:
        f.write(f"{tag}\t{run}\t{rc}\t{wall:.1f}\t{what}\n")


def main():
    mode = sys.argv[1]
    if mode == "g":
        binary, run = sys.argv[2:4]
        ms, opts = run_args(run)
        d = O / "runs" / "g" / run
        d.mkdir(parents=True, exist_ok=True)
        # RM, RH and PM ran without -no-update-model-required (section 7).
        keep = [] if run in ("RM", "RH", "PM") else ["-no-update-model-required"]
        cmd = [binary, "-name", str(d / "g"), *base(run), *opts, *keep, ms]
        t = time.time()
        with open(d / "log.txt", "w") as log:
            rc = subprocess.call(cmd, stdout=log, stderr=subprocess.STDOUT)
        wall = time.time() - t
        log_row("g", run, rc, wall, Path(binary).name)
    else:
        run = sys.argv[2]
        ms, opts = run_args(run)
        d = O / "runs" / "wsclean" / run
        (d / "tmp").mkdir(parents=True, exist_ok=True)
        data, name = os.path.dirname(ms), os.path.basename(ms)
        cmd = [
            "podman",
            "run",
            "--rm",
            "--userns=keep-id",
            "--network",
            "none",
            "-e",
            "HOME=/tmp",
            "-e",
            "OMP_NUM_THREADS=8",
            "-v",
            f"{data}:/data:ro",
            "-v",
            f"{d}:/run",
            "-v",
            f"{O}:/out:ro",
            "-w",
            "/run",
            IMAGE,
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
            *base(run),
            *opts,
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
        log_row("wsclean", run, rc, wall, IMAGE)
    print(f"{mode} {run} rc={rc} wall={wall:.1f}s")
    sys.exit(rc)


if __name__ == "__main__":
    main()
