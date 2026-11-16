"""The runs of research/gemclean-stop28.md (issue #28), native on Windows.

Every GeMClean run, simulation and preparation takes the heavy lock on its own
(the main checkout's tools/heavy_lock.py); scores run after the hold.

Usage: python examples/stop28_runs.py STAGE [--tol EPS]
    STAGE: dev (S1-S3, default, -stop-tolerance 0 and the grid), seen (H1-H4),
    simulate (H5-H8), new (H5-H8 runs), bright (the stale-floor cases), pilot.

Paths from the environment, with this host's defaults: BIN (the branch's gemclean
binary, copied out of core/target), PY (a Python with rang), O (outputs), LOCK.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
O = Path(os.environ.get("O", "D:/rang/outputs/stop28-20261116"))
BIN = os.environ.get("BIN", str(O / "bin" / "gemclean.exe"))
PY = os.environ.get("PY", "C:/Users/gijsm/Github/rang/.venv/Scripts/python.exe")
LOCK = os.environ.get("LOCK", "C:/Users/gijsm/Github/rang/tools/heavy_lock.py")
BENCH = Path("D:/rang/outputs/20261102-gemclean/bench")
HELD = Path("D:/rang/outputs/20261103-gemclean-heldout")
GRID = [0.005, 0.01, 0.02, 0.05, 0.10]
THREADS = 8
WSL_PY = "/home/gijsm/Github/rang/.venv/bin/python"


def wsl(path):
    """A Windows path as WSL sees it (D:/x -> /mnt/d/x)."""
    p = Path(path).resolve().as_posix()
    return f"/mnt/{p[0].lower()}{p[2:]}"


def locked(cmd, slots, mem, log):
    """Run cmd under the heavy lock; append a timing row to O/timing.tsv."""
    argv = [sys.executable, LOCK, "run", "--slots", str(slots), "--mem", str(mem), "--"]
    t0 = time.time()
    with open(log, "w", encoding="utf-8") as f:
        code = subprocess.run(
            argv + [str(c) for c in cmd],
            stdout=f,
            stderr=subprocess.STDOUT,
            check=False,
        ).returncode
    wall = time.time() - t0
    with open(O / "timing.tsv", "a", encoding="utf-8") as f:
        f.write(f"{Path(log).stem}\t{wall:.1f}\t{code}\n")
    print(
        Path(log).stem, "exit", code, f"{wall:.0f} s (lock wait included)", flush=True
    )
    return code


def gem(out_dir, name, ms, size, tol=None, scale="1.5asec", thr="100e-6", mem=6):
    """One GeMClean run in the held-out note's settings (accuracy 1e-6, amendment 1)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if (out_dir / f"{name}-report.json").exists():
        print(name, "exists", flush=True)
        return 0
    cmd = [BIN, "-no-update-model-required", "-name", out_dir / name]
    cmd += ["-size", size, size, "-scale", scale, "-weight", "briggs", "0.5"]
    cmd += [
        "-niter",
        "1000000",
        "-gain",
        "0.1",
        "-nmiter",
        "1000",
        "-abs-threshold",
        thr,
    ]
    cmd += ["-wgridder-accuracy", "1e-6", "-data-column", "DATA", "-field", "0"]
    cmd += ["-j", THREADS]
    if tol is not None:
        cmd += ["-stop-tolerance", tol]
    cmd.append(ms)
    (out_dir / f"{name}.cmd").write_text(
        " ".join(map(str, cmd)) + "\n", encoding="utf-8"
    )
    return locked(cmd, THREADS, mem, out_dir / f"{name}.log")


def score(prep, cat, run_dir, out, jobs):
    subprocess.run(
        [
            PY,
            str(HERE / "gemclean_bench_compare.py"),
            "score",
            prep,
            cat,
            run_dir,
            out,
            "--jobs",
            *jobs,
        ],
        check=False,
    )


def prepare(ms, cat, prep, size):
    if (Path(prep) / "vis.c128").exists():
        return
    cmd = [PY, HERE / "gemclean_bench_compare.py", "prepare", ms, cat, prep]
    cmd += ["--size", size, "--scale", "1.5"]
    noise = Path(str(ms)[: -len(".ms")] + ".noise.c64")
    if noise.exists():
        cmd += ["--noise", noise]
    locked(cmd, 4, 12, O / "logs" / f"prepare-{Path(prep).name}.log")


def tol_tag(t):
    return f"e{t:g}"


def dev():
    d = O / "dev"
    for s in ("s1", "s2", "s3"):
        ms = BENCH / "data" / f"{s}.ms"
        jobs = [f"{s}-default", f"{s}-e0"]
        gem(d, f"{s}-default", ms, 2048)
        gem(d, f"{s}-e0", ms, 2048, tol=0)
        for t in GRID:
            gem(d, f"{s}-{tol_tag(t)}", ms, 2048, tol=t)
            jobs.append(f"{s}-{tol_tag(t)}")
        score(
            BENCH / "prep" / s,
            BENCH / "data" / f"{s}.json",
            d,
            O / "scores" / f"dev-{s}.json",
            jobs,
        )


def heldout(stage, skies, tol, data, prep_root):
    d = O / stage
    for s, size in skies:
        ms = data / f"{s}.ms"
        prep = prep_root / s
        prepare(ms, data / f"{s}.json", prep, size)
        mem = 12 if size == 4096 else 6
        gem(d, f"{s}-default", ms, size, mem=mem)
        gem(d, f"{s}-{tol_tag(tol)}", ms, size, tol=tol, mem=mem)
        score(
            prep,
            data / f"{s}.json",
            d,
            O / "scores" / f"{stage}-{s}.json",
            [f"{s}-default", f"{s}-{tol_tag(tol)}"],
        )


def simulate():
    data = O / "data"
    data.mkdir(parents=True, exist_ok=True)
    for h in ("H5", "H6", "H7", "H8"):
        ms = data / f"{h.lower()}.ms"
        if ms.exists():
            continue
        cmd = [
            PY,
            HERE / "gemclean_bench_simulate.py",
            ms,
            "--sky",
            h,
            "--size",
            "2048",
            "--scale",
            "1.5",
        ]
        cmd += [
            "--catalogue",
            data / f"{h.lower()}.json",
            "--noise-out",
            data / f"{h.lower()}.noise.c64",
        ]
        locked(cmd, 4, 6, O / "logs" / f"simulate-{h.lower()}.log")


def bright(tol):
    d = O / "bright"
    w = O / "bright-ms"
    w.mkdir(parents=True, exist_ok=True)
    cases = [
        ("h1-plus30", HELD / "sim/data/h1.ms", 2048, 30, 0),
        ("h4-plus30", HELD / "sim/data/h4.ms", 2048, 30, 0),
        ("s2-plus30-off20", BENCH / "data/s2.ms", 2048, 30, 20),
        ("h3-plus100", HELD / "sim/data/h3.ms", 4096, 100, 0),
    ]
    for name, src, size, jy, off in cases:
        done = all(
            (d / f"{name}-{t}-report.json").exists() for t in ("default", tol_tag(tol))
        )
        if not done:
            ms = w / f"{name}.ms"
            shutil.rmtree(ms, ignore_errors=True)
            shutil.copytree(src, ms)
            # casacure lives in the WSL venv; the copy is on D:, seen as /mnt/d.
            add = subprocess.run(
                ["wsl", "-e", WSL_PY, "-I", wsl(HERE / "stale_floor_add.py"), wsl(ms)]
                + [str(jy), str(off), "1.5"],
                check=False,
            )
            if add.returncode != 0:
                raise SystemExit(f"{name}: no source added")
            mem = 12 if size == 4096 else 6
            gem(d, f"{name}-default", ms, size, mem=mem)
            gem(d, f"{name}-{tol_tag(tol)}", ms, size, tol=tol, mem=mem)
            shutil.rmtree(ms)
        for t in ("default", tol_tag(tol)):
            subprocess.run(
                [
                    PY,
                    "-I",
                    HERE / "stale_floor_score.py",
                    str(d / f"{name}-{t}"),
                    str(jy),
                    str(O / "scores" / "bright.jsonl"),
                ],
                check=False,
            )
    shutil.rmtree(w, ignore_errors=True)


def pilot(tol):
    d = O / "pilot"
    real = HELD / "real"
    for ms, thr, name in (
        ("cal2.ms", "0.003", "a-3mjy"),
        ("cal3.ms", "0.003", "b-3mjy"),
        ("cal2.ms", "0.001", "a-1mjy"),
    ):
        for t, tag in ((None, "default"), (tol, tol_tag(tol))):
            gem(
                d,
                f"{name}-{tag}",
                real / ms,
                4096,
                tol=t,
                scale="3asec",
                thr=thr,
                mem=20,
            )


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "stage", choices=["dev", "seen", "simulate", "new", "bright", "pilot"]
    )
    p.add_argument("--tol", type=float)
    a = p.parse_args()
    for sub in ("logs", "scores"):
        (O / sub).mkdir(parents=True, exist_ok=True)
    if a.stage == "dev":
        dev()
    elif a.stage == "simulate":
        simulate()
    elif a.tol is None:
        raise SystemExit("--tol is needed after the development stage")
    elif a.stage == "seen":
        skies = [("h1", 2048), ("h2", 2048), ("h3", 4096), ("h4", 2048)]
        heldout("seen", skies, a.tol, HELD / "sim/data", O / "prep")
    elif a.stage == "new":
        skies = [("h5", 2048), ("h6", 2048), ("h7", 2048), ("h8", 2048)]
        heldout("new", skies, a.tol, O / "data", O / "prep")
    elif a.stage == "bright":
        bright(a.tol)
    else:
        pilot(a.tol)
    print(
        json.dumps({"stage": a.stage, "finished": time.strftime("%Y-%m-%d %H:%M:%S")}),
        flush=True,
    )


if __name__ == "__main__":
    main()
