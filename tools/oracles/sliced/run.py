"""Sliced-read arms (research/sliced-read.md, sections 2 to 4), native.

    python run.py RUN CASE ARM [--base BASE]   # one arm: copy, configure, run, hash
    python run.py verdict RUN OUT.json         # the frozen comparisons

W3b's harness (`tools/oracles/w3b/run.sh`, bash on WSL) ported to Python for
native Windows: the same configurations and casacure hashes
(`tools/oracles/w3b/compare.py`), the sources at their native paths. CASE is
O, C, P, H or W; ARM is U (W3b's unchunked rule), D, T or M. `--base` runs
the arm with the code of another checkout (its `python/` first on
PYTHONPATH, its extension inside it): the arm directory is then
`CASE-B<ARM>`. Each stage runs in a child process (`stage`) that records
its wall time and peak working set in `timing/<stage>.txt`, in the lines
`/usr/bin/time -v` writes, so W3's verdict reads them.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
_spec = importlib.util.spec_from_file_location(
    "w3b_compare", HERE.parent / "w3b" / "compare.py"
)
w3b = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w3b)
w3 = w3b.w3

DATA = Path(r"D:\rang\outputs")
w3b.STRATEGY = (
    DATA / "sliced-read-data" / "mk_rfi_flagging_calibrator_fields_firstpass.yaml"
)
w3b.SOURCES.update(
    {
        "O": DATA / "sliced-read-data" / "o-casa-work.ms",
        "C": DATA / "fp-a1-20261106-simtruth" / "small" / "a1-small.ms",
        "P": DATA / "c6w-20261106-01" / "prepared.ms",
        "W": DATA / "w3" / "data" / "w3.ms",
        "H": DATA / "c6w-20261106-02" / "prepared.ms",
    }
)

# The frozen comparisons (section 3): (case, arm, reference arm).
PAIRS = [
    *[(c, a, "U") for c in ("O", "C", "P", "H") for a in ("D", "T", "M")],
    ("W", "D", "BD"),
    ("W", "M", "BM"),
    ("W", "M", "D"),
    # Reported: the base's own chunked arms against U.
    *[(c, f"B{a}", "U") for c in ("O", "C", "P", "H") for a in ("D", "T", "M")],
]


def stage(name, config, ms, run_dir, timing):
    """Run one `rang-core` stage in this process; write its wall time, peak
    working set and exit status to `timing`."""
    import runpy

    sys.argv = ["rang-core", name, config, ms, "--run-dir", run_dir]
    start = time.perf_counter()
    status = 0
    try:
        runpy.run_module("rang.core_cli", run_name="__main__")
    except SystemExit as exc:
        status = (
            exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        )
    wall = time.perf_counter() - start
    from rang import rusage

    peak = rusage.peak_rss_bytes()
    m, s = divmod(wall, 60)
    Path(timing).write_text(
        f"\tElapsed (wall clock) time (h:mm:ss or m:ss): {int(m)}:{s:05.2f}\n"
        f"\tMaximum resident set size (kbytes): {peak // 1024}\n"
        f"\tWall seconds: {wall:.3f}\n"
        f"\tExit status: {status}\n",
        encoding="utf-8",
    )
    sys.exit(status)


def arm(run, case, arm, base=None):
    run = Path(run).resolve()
    name = f"{case}-B{arm}" if base else f"{case}-{arm}"
    d = run / name
    if d.exists():
        raise SystemExit(f"{d} exists; choose a fresh run")
    for sub in ("timing", "logs", "hashes"):
        (d / sub).mkdir(parents=True)
    env = dict(os.environ)
    if base:
        env["PYTHONPATH"] = str(Path(base) / "python")
    py = sys.executable
    probe = subprocess.run(
        [py, "-c", "import rang, rang._core; print(rang.__file__, rang._core.__file__)"],
        env=env, capture_output=True, text=True, check=True,
    )  # fmt: skip
    (d / "logs" / "rang-path.txt").write_text(probe.stdout, encoding="utf-8")
    ms = d / "work.ms"
    shutil.copytree(w3b.SOURCES[case], ms)
    # The configuration and M's limit from this checkout's code (the rule of
    # W3b section 2 amendment 2), the same text for the base arms.
    w3b.config(case, arm, str(ms), str(d / "config.yaml"))
    w3.hashes(str(ms), str(d / "hashes" / "pristine.json"))
    stages = ["calibrate"] if case == "W" else ["calibrate", "apply"]
    for s in stages:
        with open(d / "logs" / f"{s}.log", "w", encoding="utf-8") as log:
            status = subprocess.run(
                [py, str(Path(__file__).resolve()), "stage", s, str(d / "config.yaml"),
                 str(ms), str(d / "run"), str(d / "timing" / f"{s}.txt")],
                env=env, stdout=log, stderr=subprocess.STDOUT, check=False,
            ).returncode  # fmt: skip
        (d / "logs" / f"{s}.exit").write_text(f"{status}\n", encoding="utf-8")
        timing = d / "timing" / f"{s}.txt"
        print(f"{name} {s} exit {status} peak {w3._peak_kb(timing)} KB wall "
              f"{_wall(timing)} s", flush=True)  # fmt: skip
        w3.hashes(str(ms), str(d / "hashes" / f"{s}.json"))
        if status != 0:
            break
    if case == "W":
        shutil.rmtree(ms)
        shutil.rmtree(ms.with_name(ms.name + ".flagversions"), ignore_errors=True)


def _row(d):
    stages = [
        s for s in ("calibrate", "apply") if (d / "hashes" / f"{s}.json").is_file()
    ]
    return {
        "hashes": {
            s: json.loads((d / "hashes" / f"{s}.json").read_text()) for s in stages
        },
        "summaries": {
            s: w3._clean(json.loads((d / "run" / s / "summary.json").read_text()))
            for s in stages
            if (d / "run" / s / "summary.json").is_file()
        },
        "stores": w3._files(d / "run" / "calibrate")
        if (d / "run" / "calibrate").is_dir()
        else {},
        "exit": {
            s: int((d / "logs" / f"{s}.exit").read_text())
            for s in stages
            if (d / "logs" / f"{s}.exit").is_file()
        },
        "peak_gb": {
            s: (w3._peak_kb(d / "timing" / f"{s}.txt") or 0) / (1 << 20) for s in stages
        },
        "wall_s": {s: _wall(d / "timing" / f"{s}.txt") for s in stages},
        "limit_gb": w3._limit_gb(d),
    }


def _wall(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if "Wall seconds" in line:
            return float(line.rsplit(":", 1)[1])
    return None


def _compare(r, ref):
    c = {}
    for s, h in r["hashes"].items():
        base = ref["hashes"].get(s)
        if base is None:
            c[f"{s}: missing in the reference"] = True
            continue
        c[f"{s}: columns differing"] = sorted(
            k
            for k in set(h["columns"]) | set(base["columns"])
            if h["columns"].get(k) != base["columns"].get(k)
        )
        fv = [(v["key"], v["columns"]) for v in h["flag_versions"]]
        fb = [(v["key"], v["columns"]) for v in base["flag_versions"]]
        c[f"{s}: flag versions equal"] = fv == fb
    c["stages equal"] = sorted(r["hashes"]) == sorted(ref["hashes"])
    c["exits zero"] = all(v == 0 for v in r["exit"].values()) and all(
        v == 0 for v in ref["exit"].values()
    )
    c["calibrate files equal"] = r["stores"] == ref["stores"]
    c["summaries equal"] = all(
        r["summaries"].get(s) == ref["summaries"].get(s)
        for s in set(r["summaries"]) | set(ref["summaries"])
    )
    c["pass"] = (
        c["stages equal"]
        and c["exits zero"]
        and c["calibrate files equal"]
        and c["summaries equal"]
        and all(not v for k, v in c.items() if k.endswith("columns differing"))
        and all(v for k, v in c.items() if k.endswith("flag versions equal"))
    )
    return c


def verdict(run, out):
    run = Path(run)
    rows = {
        p.name: _row(p)
        for p in sorted(run.iterdir())
        if p.is_dir() and (p / "hashes").is_dir()
    }
    checks = {}
    for case, a, ref in PAIRS:
        x, y = f"{case}-{a}", f"{case}-{ref}"
        if x in rows and y in rows:
            checks[f"{x} vs {y}"] = _compare(rows[x], rows[y])
    report = {
        "checks": checks,
        "all_pass": all(c["pass"] for c in checks.values()),
        "arms": {
            k: {key: r[key] for key in ("exit", "peak_gb", "wall_s", "limit_gb")}
            for k, r in rows.items()
        },
    }
    Path(out).write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: c["pass"] for k, c in checks.items()}, indent=1))
    print("all pass:", report["all_pass"])
    return report


if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    if cmd == "stage":
        stage(*args)
    elif cmd == "verdict":
        verdict(*args)
    else:
        base = None
        if "--base" in args:
            i = args.index("--base")
            base = args[i + 1]
            args = args[:i] + args[i + 2 :]
        arm(cmd, args[0], args[1], base)
