"""pfb-imaging 0.0.11 arms of big-plan task DF5-O (research/df5o-deconv-oracles.md, section 2.2).

    python examples/oracle_pfb.py run FIELD_DIR RUN_DIR ARM [--repeat K]

Arms: `grid` (init and grid only: the dirty-image precondition),
`pfb-kclean`, `pfb-clark` (kclean without the flux mop), `pfb-sara`. Each
runs the release's legacy chain `init -> grid -> kclean|sara` in the image
`rang-pfb-imaging:0.0.11` (tools/oracles/pfb-imaging/) with `--network
none`, `--backend native`, 4 threads, one worker, and writes
`RUN_DIR/ARM-rK/` (pfb's outputs, one log per step, `run.json` with the
commands, wall time and peak RSS per step from `/usr/bin/time -v`).
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oracle_wsclean_clean import parse_time_v

IMAGE = "rang-pfb-imaging:0.0.11"
THREADS = 4


def steps(arm, field):
    threshold = f"{field['noise']['threshold_3sigma_jy']:.6e}"
    base = "/out/pfb"
    common = ["--nthreads", str(THREADS), "--nworkers", "1", "--backend", "native", "--log-directory", "/out/logs"]
    init = [
        "pfb", "init", "--ms", "/field/field.ms", "--output-filename", base,
        "--data-column", "DATA", "--weight-column", "WEIGHT_SPECTRUM",
        "--channels-per-image", "1", "--chan-average", "1", "--bda-decorr", "1.0",
        "--precision", "double", "--product", "I", "--integrations-per-image", "-1",
        "--no-progressbar", *common,
    ]  # fmt: skip
    grid = [
        "pfb", "grid", "--output-filename", base, "--nx", "1024", "--ny", "1024",
        "--cell-size", "2.0", "--psf-oversize", "1.4", "--epsilon", "1e-6",
        "--do-wgridding", "--product", "I", *common,
    ]  # fmt: skip
    out = [("init", init), ("grid", grid)]
    kclean = [
        "pfb", "kclean", "--output-filename", base, "--niter", "10", "--threshold", threshold,
        "--gamma", "0.1", "--peak-factor", "0.2", "--epsilon", "1e-6", "--do-wgridding",
        "--product", "I", "--nthreads", str(THREADS), "--backend", "native",
        "--log-directory", "/out/logs",
    ]  # fmt: skip
    if arm == "grid":
        return out
    if arm == "pfb-kclean":
        return [*out, ("kclean", kclean)]
    if arm == "pfb-clark":
        return [*out, ("kclean", [*kclean, "--no-mop-flux"])]
    if arm == "pfb-sara":
        sara = [
            "pfb", "sara", "--output-filename", base, "--niter", "10", "--rmsfactor", "1.0",
            "--epsilon", "1e-6", "--do-wgridding", "--bases", "self,db1,db2,db3", "--nlevels", "2",
            "--l1-reweight-from", "5", "--pd-tol", "1.5e-4", "--pd-maxit", "450", "--tol", "5e-4",
            "--gamma", "0.99", "--alpha", "2", "--eta", "5e-4", "--positivity", "1",
            "--init-factor", "0.5", "--product", "I", "--nthreads", str(THREADS),
            "--backend", "native", "--log-directory", "/out/logs",
        ]  # fmt: skip
        return [*out, ("sara", sara)]
    raise SystemExit(f"unknown arm {arm}")


def docker(field_dir, out_dir, command):
    cmd = [
        "docker", "run", "--rm", "--network", "none", "--shm-size", "8g",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "-e", f"OMP_NUM_THREADS={THREADS}", "-e", f"NUMBA_NUM_THREADS={THREADS}",
        "-e", "OPENBLAS_NUM_THREADS=1", "-e", "HOME=/tmp", "-e", "NUMBA_CACHE_DIR=/out/numba-cache",
        "-e", "RAY_USAGE_STATS_ENABLED=0",
        "-v", f"{Path(field_dir).resolve()}:/field:ro",
        "-v", f"{Path(out_dir).resolve()}:/out",
        "-w", "/out", IMAGE, "/usr/bin/time", "-v", *command,
    ]  # fmt: skip
    start = time.perf_counter()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    return proc, time.perf_counter() - start, cmd


def cmd_run(args):
    field_dir = Path(args.field)
    field = json.loads((field_dir / "field.json").read_text())
    out = Path(args.run) / f"{args.arm}-r{args.repeat}"
    if out.exists():
        raise SystemExit(f"{out} exists")
    out.mkdir(parents=True)
    records = []
    for name, command in steps(args.arm, field):
        proc, wall, cmd = docker(field_dir, out, command)
        (out / f"{name}.log").write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr)
        rec = {
            "step": name,
            "command": command,
            "docker_command": cmd,
            "returncode": proc.returncode,
            "docker_wall_s": wall,
            "time_v": parse_time_v(proc.stderr),
        }
        records.append(rec)
        print(json.dumps({k: rec[k] for k in ("step", "returncode", "docker_wall_s", "time_v")}), flush=True)
        if proc.returncode:
            break
    run = {
        "arm": args.arm,
        "repeat": args.repeat,
        "image": IMAGE,
        "steps": records,
        "returncode": max(r["returncode"] for r in records),
        "docker_wall_s": sum(r["docker_wall_s"] for r in records),
        "field_ms_digest": field["hashes"]["ms_digest"],
    }
    (out / "run.json").write_text(json.dumps(run, indent=1))
    if run["returncode"]:
        sys.exit(run["returncode"])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("field")
    r.add_argument("run")
    r.add_argument("arm")
    r.add_argument("--repeat", type=int, default=1)
    args = p.parse_args()
    cmd_run(args)


if __name__ == "__main__":
    main()
