"""WSClean 3.7 arms of big-plan task DF5-O (research/df5o-deconv-oracles.md, section 2.1).

    python examples/oracle_wsclean_clean.py run FIELD_DIR RUN_DIR ARM [--repeat K]
    python examples/oracle_wsclean_clean.py msread-check FIELD_DIR OUT.json [--image IMAGE]
    python examples/oracle_wsclean_clean.py msread MS          (inside a container)

`run` images a copy of `FIELD_DIR/field.ms` (WSClean opens it read/write) in O-CASA's image
`rang-o-casa:6.7.6.14` (WSClean 3.7) with `--network none` and writes
`RUN_DIR/ARM-rK/` (FITS, source list, log, `run.json` with the command, wall
time, peak RSS from `/usr/bin/time -v` and the counts parsed from the log).
Arms: `dirty` (the `-niter 0` precondition), `ws-hogbom`, `ws-multiscale`,
`ws-multiscale-mask`. The multiscale scales are the protocol's rule as
`field.json` records it; the threshold is its 3 sigma_img.

`msread` (no rang import; any python with python-casacore) prints the
SHA256 of the MS columns the core wrote, read back by python-casacore;
`msread-check` runs it in a container and compares with `field.json`.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

IMAGE = "rang-o-casa:6.7.6.14"
ROOT = Path(__file__).resolve().parents[1]
COMMON = [
    "-size", "1024", "1024", "-scale", "2asec", "-weight", "natural", "-pol", "I",
    "-data-column", "DATA", "-gridder", "wgridder", "-wgridder-accuracy", "1e-6",
    "-no-min-grid-resolution", "-channels-out", "16", "-join-channels",
    "-j", "4", "-no-update-model-required", "-no-reorder",
]  # fmt: skip
CLEAN = ["-nmiter", "10", "-niter", "1000000", "-gain", "0.1", "-mgain", "0.8"]  # fmt: skip
# Deviation D1 (research/df5o-deconv-oracles.md): WSClean 3.7 refuses
# -save-source-list with several output channels and no -fit-spectral-pol, so
# only the reported practice arm (which adds -fit-spectral-pol 4) writes one.


def arm_args(arm, field):
    threshold = f"{field['noise']['threshold_3sigma_jy']:.6e}"
    scales = ",".join(str(s) for s in field["psf"]["multiscale_scales_px"])
    if arm == "dirty":
        return [*COMMON, "-niter", "0", "-make-psf"]
    if arm == "ws-hogbom":
        return [*COMMON, *CLEAN, "-threshold", threshold]
    if arm == "ws-multiscale":
        return [
            *COMMON, *CLEAN, "-threshold", threshold, "-multiscale",
            "-multiscale-scales", scales, "-multiscale-gain", "0.2",
        ]  # fmt: skip
    if arm == "ws-multiscale-mask":
        return [
            *COMMON, *CLEAN, "-auto-mask", "4", "-auto-threshold", "1", "-fit-spectral-pol", "4",
            "-save-source-list", "-multiscale",
            "-multiscale-scales", scales, "-multiscale-gain", "0.2",
        ]  # fmt: skip
    raise SystemExit(f"unknown arm {arm}")


def docker(field_dir, out_dir, command, image=IMAGE, threads=4, extra=()):
    cmd = [
        "docker", "run", "--rm", "--network", "none",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "-e", f"OMP_NUM_THREADS={threads}", "-e", "OPENBLAS_NUM_THREADS=1", "-e", "HOME=/tmp",
        "-v", f"{Path(field_dir).resolve()}:/field:ro",
        "-v", f"{Path(out_dir).resolve()}:/out",
        "-v", f"{ROOT / 'examples'}:/src:ro",
        *extra, "-w", "/out", image, *command,
    ]  # fmt: skip
    start = time.perf_counter()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    return proc, time.perf_counter() - start, cmd


def parse_time_v(text):
    rec = {}
    m = re.search(r"Maximum resident set size \(kbytes\): (\d+)", text)
    if m:
        rec["peak_rss_mb"] = int(m.group(1)) / 1024
    m = re.search(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): ([\d:.]+)", text)
    if m:
        parts = [float(p) for p in m.group(1).split(":")]
        rec["wall_s"] = sum(p * 60**i for i, p in enumerate(reversed(parts)))
    for key, pat in (
        ("user_s", r"User time \(seconds\): ([\d.]+)"),
        ("system_s", r"System time \(seconds\): ([\d.]+)"),
    ):
        m = re.search(pat, text)
        if m:
            rec[key] = float(m.group(1))
    return rec


def parse_wsclean_log(text):
    """Major cycles and minor iterations from WSClean 3.7's log."""
    rec = {}
    majors = re.findall(
        r"Major iteration|== Converting model image to visibilities ==|Starting major iteration (\d+)",
        text,
    )
    rec["predict_passes"] = len(
        re.findall(r"Predicting|== Converting model image", text)
    )
    rec["deconvolution_passes"] = len(re.findall(r"== Deconvolving \(\d+\) ==", text))
    iters = [int(x) for x in re.findall(r"[Ii]teration (\d+)", text)]
    rec["max_iteration_logged"] = max(iters) if iters else 0
    m = re.findall(
        r"(\d+) minor iterations? (?:were )?performed|Minor loop finished.*?(\d+)", text
    )
    rec["stop_lines"] = re.findall(
        r"^.*(?:Stopped on|reached|threshold).*$", text, re.MULTILINE
    )[-6:]
    rec["major_marker_count"] = len(majors)
    rec["minor_summary_matches"] = [list(x) for x in m]
    return rec


def cmd_run(args):
    field_dir = Path(args.field)
    field = json.loads((field_dir / "field.json").read_text())
    out = Path(args.run) / f"{args.arm}-r{args.repeat}"
    if out.exists():
        raise SystemExit(f"{out} exists")
    out.mkdir(parents=True)
    wargs = arm_args(args.arm, field)
    command = [
        "/usr/bin/time",
        "-v",
        "wsclean",
        *wargs,
        "-name",
        f"/out/{args.arm}",
        "/out/field.ms",
    ]
    # WSClean opens the MS read/write even with -no-update-model-required
    # (deviation D2): it images a copy, removed after the run once its
    # columns are checked unchanged against field.json.
    shutil.copytree(field_dir / "field.ms", out / "field.ms")
    proc, wall, cmd = docker(field_dir, out, command)
    (out / "wsclean.log").write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr)
    check, _, _ = docker(
        field_dir,
        out,
        ["python3", "-I", "/src/oracle_wsclean_clean.py", "msread", "/out/field.ms"],
    )
    got = (
        json.loads(check.stdout.strip().splitlines()[-1])
        if check.returncode == 0
        else {}
    )
    copy_unchanged = all(got.get(k) == v for k, v in field["hashes"]["columns"].items())
    shutil.rmtree(out / "field.ms")
    rec = {
        "arm": args.arm,
        "repeat": args.repeat,
        "image": IMAGE,
        "wsclean_args": wargs,
        "docker_command": cmd,
        "returncode": proc.returncode,
        "docker_wall_s": wall,
        "time_v": parse_time_v(proc.stderr),
        "log": parse_wsclean_log(proc.stdout),
        "field_ms_digest": field["hashes"]["ms_digest"],
        "ms_copy_columns_unchanged": copy_unchanged,
    }
    (out / "run.json").write_text(json.dumps(rec, indent=1))
    print(
        json.dumps(
            {
                k: rec[k]
                for k in ("arm", "repeat", "returncode", "docker_wall_s", "time_v")
            }
        )
    )
    if proc.returncode:
        sys.exit(proc.returncode)


def msread(path):
    """SHA256 of TIME, UVW, DATA, WEIGHT_SPECTRUM, FLAG and the subtables'
    key columns as python-casacore reads them."""
    import numpy as np
    from casacore import tables as pt

    out = {}
    with pt.table(path, ack=False) as t:
        nrow = t.nrows()
        for col in ("TIME", "UVW", "DATA", "WEIGHT_SPECTRUM", "FLAG"):
            h = hashlib.sha256()
            step = 8064
            for start in range(0, nrow, step):
                h.update(
                    np.ascontiguousarray(
                        t.getcol(col, start, min(step, nrow - start))
                    ).tobytes()
                )
            out[col] = h.hexdigest()
        out["nrow"] = nrow
    with pt.table(f"{path}/SPECTRAL_WINDOW", ack=False) as t:
        out["CHAN_FREQ"] = t.getcol("CHAN_FREQ").tolist()
    with pt.table(f"{path}/FIELD", ack=False) as t:
        out["PHASE_DIR"] = t.getcol("PHASE_DIR").tolist()
    with pt.table(f"{path}/ANTENNA", ack=False) as t:
        out["ANTENNA_POSITION"] = hashlib.sha256(
            np.ascontiguousarray(t.getcol("POSITION")).tobytes()
        ).hexdigest()
        out["nant"] = t.nrows()
    with pt.table(f"{path}/POLARIZATION", ack=False) as t:
        out["CORR_TYPE"] = t.getcol("CORR_TYPE").tolist()
    return out


def cmd_msread_check(args):
    field_dir = Path(args.field)
    field = json.loads((field_dir / "field.json").read_text())
    out_json = Path(args.out)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    python = "python3" if args.image == IMAGE else "/opt/pfb/bin/python"
    proc, wall, _ = docker(
        field_dir,
        out_json.parent,
        [python, "-I", "/src/oracle_wsclean_clean.py", "msread", "/field/field.ms"],
        image=args.image,
    )
    if proc.returncode:
        print(proc.stderr)
        sys.exit(proc.returncode)
    got = json.loads(proc.stdout.strip().splitlines()[-1])
    want = field["hashes"]["columns"]
    import numpy as np

    rec = {
        "image": args.image,
        "columns_equal": {k: got[k] == want[k] for k in want},
        "nrow_equal": got["nrow"] == field["geometry"]["nrow"],
        "chan_freq_equal": bool(
            np.array_equal(
                np.array(got["CHAN_FREQ"])[0], np.array(field["geometry"]["freqs_hz"])
            )
        ),
        "phase_dir": got["PHASE_DIR"],
        "nant": got["nant"],
        "corr_type": got["CORR_TYPE"],
        "wall_s": wall,
    }
    rec["pass"] = (
        all(rec["columns_equal"].values())
        and rec["nrow_equal"]
        and rec["chan_freq_equal"]
    )
    out_json.write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec))


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("field")
    r.add_argument("run")
    r.add_argument("arm")
    r.add_argument("--repeat", type=int, default=1)
    m = sub.add_parser("msread")
    m.add_argument("ms")
    c = sub.add_parser("msread-check")
    c.add_argument("field")
    c.add_argument("out")
    c.add_argument("--image", default=IMAGE)
    args = p.parse_args()
    if args.cmd == "run":
        cmd_run(args)
    elif args.cmd == "msread":
        print(json.dumps(msread(args.ms)))
    else:
        cmd_msread_check(args)


if __name__ == "__main__":
    main()
