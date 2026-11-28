# SPDX-License-Identifier: MIT
"""selfcal-io (research/selfcal-io.md): the E2 pilot arms on glacier.

    prepare ARM       OUT/ARM/pilot.ms from OUT/grid/base/pilot.ms (held-out channels
                      flagged as selfcal_grid's prepare), CORRECTED_DATA := DATA, this run
                      directory's apply marked done, OUT/ARM/config.yaml
    run ARM           `rang-core selfcal` on it (the package on sys.path decides main or
                      branch), wall time and peak memory in OUT/ARM/run.json
    compare A B       OUT/compare-A-B.json: stores, FITS, MS columns, marker, solves
    clean ARM         delete OUT/ARM/pilot.ms

Arms: `<code><chunks>`, code M (main, the oracle) or B (branch), chunks 1 (one chunk per
solve) or N (`data.chunk_rows` = one solution interval of averaged rows per chunk).
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[4]
P1_YAML = REPO / "research/results/floor-3/p1.yaml"
# selfcal_grid.FLAGGED_B: imaging-floor's metric channels 4, 12, ..., 252 and neighbours
CH_B = np.arange(4, 256, 8)
FLAGGED_B = np.sort(np.concatenate([CH_B - 1, CH_B, CH_B + 1, CH_B + 2]))
ROWS = 20000
APPLY_STAMP = "selfcal-io-pilot-apply"


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def wjson(path, obj):
    Path(path).write_text(json.dumps(obj, indent=1, sort_keys=True, default=str) + "\n")


def config(arm, nbl):
    cfg = yaml.safe_load(P1_YAML.read_text())
    cfg["data"]["weights"] = "uniform"  # E2's
    if arm.endswith("N"):
        cfg["data"]["chunk_rows"] = int(nbl)  # one averaged interval per chunk
    cfg["selfcal"].update(
        rounds=2,
        terms=[{"type": "Sp", "solint": 120}, {"type": "Sa", "solint": 120}],
        input_column="CORRECTED_1GC",
        output_column="CORRECTED_DATA",
        average_time=True,
    )
    return cfg


def cmd_prepare(out, arm):
    from rang import core_ms, core_ms_write
    from rang import core_pipeline as pipe
    from rang import core_writeback as wb

    q = out / arm
    ms = q / "pilot.ms"
    shutil.rmtree(q, ignore_errors=True)
    q.mkdir(parents=True)
    s0 = time.perf_counter()
    shutil.copytree(out / "grid" / "base" / "pilot.ms", ms)
    with core_ms.open_table(str(ms)) as t:
        n = int(t.nrows)
        a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
    nbl = len(np.unique(a1[a1 != a2] * 1000 + a2[a1 != a2]))
    with core_ms_write.open_table(str(ms), readonly=False) as o:
        for r0 in range(0, n, ROWS):
            k = min(ROWS, n - r0)
            f = np.array(o.getcol("FLAG", r0, k), bool)
            f[:, FLAGGED_B, :] = True
            o.putcol("FLAG", f, r0, k)
    with wb.WriteBack(ms, stage="selfcal-io-prepare") as w:
        w.ensure_column("CORRECTED_DATA", init="data")
    run = pipe.RunDir(q / "run", ms)
    with run.locked():
        run.state["stages"]["apply"] = {"status": "done", "finished": APPLY_STAMP}
        run.save()
    cfg = config(arm, nbl)
    (q / "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    wjson(
        q / "prepare.json",
        {"rows": n, "baselines": nbl, "seconds": time.perf_counter() - s0},
    )
    log("prepared", arm, n, "rows", nbl, "baselines")


def _tree_rss(pid):
    """RSS of the process tree and of its largest rang-core process (the venv's
    python.exe launcher and gemclean excluded)."""
    import psutil

    try:
        p = psutil.Process(pid)
        procs = [p, *p.children(recursive=True)]
    except psutil.Error:
        return 0, 0
    total = mine = 0
    for c in procs:
        try:
            r = c.memory_info().rss
            cmd = " ".join(c.cmdline())
        except psutil.Error:
            continue
        total += r
        if "rang.gemclean" not in cmd:
            mine = max(mine, r)
    return total, mine


def cmd_run(out, arm, src):
    q = out / arm
    env = dict(os.environ)
    if src:
        env["PYTHONPATH"] = str(Path(src).resolve())
    code = "import sys; from rang import core_cli; sys.exit(core_cli.dispatch(sys.argv[1:]))"
    argv = [sys.executable, "-c", code, "selfcal", str(q / "config.yaml"), str(q / "pilot.ms"),
            "--run-dir", str(q / "run")]  # fmt: skip
    probe = subprocess.run(
        [sys.executable, "-c", "import rang, rang._core as c; print(rang.__file__); print(c.__file__)"],
        env=env, capture_output=True, text=True, check=True,
    )  # fmt: skip
    peak = {"tree": 0, "rang": 0}
    s0 = time.perf_counter()
    with (q / "run.log").open("w") as fh:
        proc = subprocess.Popen(argv, env=env, stdout=fh, stderr=subprocess.STDOUT)
        stop = threading.Event()

        def watch():
            while not stop.wait(1.0):
                tree, mine = _tree_rss(proc.pid)
                peak["tree"] = max(peak["tree"], tree)
                peak["rang"] = max(peak["rang"], mine)

        th = threading.Thread(target=watch, daemon=True)
        th.start()
        rc = proc.wait()
        stop.set()
        th.join()
    wall = time.perf_counter() - s0
    rec = {"arm": arm, "rc": rc, "wall_s": wall, "peak_tree_bytes": peak["tree"],
           "peak_rang_bytes": peak["rang"], "package": probe.stdout.split(), "argv": argv,
           "RAYON_NUM_THREADS": env.get("RAYON_NUM_THREADS"),
           "host": os.environ.get("COMPUTERNAME")}  # fmt: skip
    wjson(q / "run.json", rec)
    log("run", arm, "rc", rc, "wall", round(wall, 1))
    return rc


def _hash_tree(path):
    path = Path(path)
    out = {}
    for p in sorted(path.rglob("*")):
        if p.is_file():
            out[p.relative_to(path).as_posix()] = hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
    return out


def _columns_equal(a, b, names):
    from rang import core_ms

    res = {}
    with core_ms.open_table(str(a)) as ta, core_ms.open_table(str(b)) as tb:
        n = int(ta.nrows)
        assert n == int(tb.nrows)
        for name in names:
            if name not in ta.colnames() or name not in tb.colnames():
                res[name] = {"present": [name in ta.colnames(), name in tb.colnames()]}
                continue
            h_a, h_b = hashlib.sha256(), hashlib.sha256()
            for r0 in range(0, n, ROWS):
                k = min(ROWS, n - r0)
                h_a.update(np.ascontiguousarray(ta.getcol(name, r0, k)).tobytes())
                h_b.update(np.ascontiguousarray(tb.getcol(name, r0, k)).tobytes())
            res[name] = {"sha256": [h_a.hexdigest(), h_b.hexdigest()],
                         "equal": h_a.hexdigest() == h_b.hexdigest()}  # fmt: skip
    return res


def _fits(image):
    """The FITS files' sha256 of an image record (its image-report.json names the
    column read, the paths and the timings, so it differs by design)."""
    return {k: v for k, v in image["files"].items() if k.endswith(".fits")}


def cmd_compare(out, a, b):
    qa, qb = out / a, out / b
    sa = json.loads((qa / "run/selfcal/summary.json").read_text())
    sb = json.loads((qb / "run/selfcal/summary.json").read_text())
    res = {"arms": [a, b], "stores": {}, "fits": {}, "solves": {}}
    for fa, fb in zip(sa["fields"], sb["fields"], strict=True):
        for ra, rb in zip(fa["rounds"], fb["rounds"], strict=True):
            k = f"{fa['field']}/round-{ra['round']}"
            ha = _hash_tree(
                qa / "run/selfcal" / fa["field"] / f"round-{ra['round']}" / "gains.qc"
            )
            hb = _hash_tree(
                qb / "run/selfcal" / fb["field"] / f"round-{rb['round']}" / "gains.qc"
            )
            res["stores"][k] = {"files": len(ha), "equal": ha == hb}
            res["fits"][k] = _fits(ra["image"]) == _fits(rb["image"])
            keys = (
                "iterations",
                "converged_fraction",
                "flagged_fraction",
                "time_bins",
                "rows",
            )
            res["solves"][k] = {
                "a": {x: ra["solve"][x] for x in keys}, "b": {x: rb["solve"][x] for x in keys},
                "reads_b": rb["solve"]["settings"].get("reads"),
                "wall_a": ra["solve"]["wall_seconds"], "wall_b": rb["solve"]["wall_seconds"],
                "apply_a": ra["apply"]["wall_seconds"], "apply_b": rb["apply"]["wall_seconds"],
            }  # fmt: skip
        res["fits"][f"{fa['field']}/final"] = _fits(fa["final_image"]) == _fits(
            fb["final_image"]
        )
    res["marker"] = {
        "a": json.loads((qa / "run/selfcal-input.json").read_text()),
        "b": json.loads((qb / "run/selfcal-input.json").read_text()),
    }
    res["marker"]["equal"] = res["marker"]["a"] == res["marker"]["b"]
    res["input"] = {"a": sa["input"], "b": sb["input"]}
    res["columns"] = _columns_equal(
        qa / "pilot.ms", qb / "pilot.ms",
        ["CORRECTED_DATA", "CORRECTED_1GC", "MODEL_DATA", "FLAG", "FLAG_ROW", "DATA"],
    )  # fmt: skip
    res["identical"] = bool(
        all(v["equal"] for v in res["stores"].values())
        and all(res["fits"].values())
        and res["marker"]["equal"]
        and all(v.get("equal") for v in res["columns"].values())
        and all(v["a"] == v["b"] for v in res["solves"].values())
    )
    wjson(out / f"compare-{a}-{b}.json", res)
    log("compare", a, b, "identical", res["identical"])
    return 0 if res["identical"] else 3


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["prepare", "run", "compare", "clean"])
    p.add_argument("arms", nargs="+")
    p.add_argument("--out", required=True)
    p.add_argument(
        "--src", default=None, help="PYTHONPATH of the package to run (main's)"
    )
    a = p.parse_args(argv)
    out = Path(a.out)
    if a.stage == "prepare":
        for arm in a.arms:
            cmd_prepare(out, arm)
    elif a.stage == "run":
        return max(cmd_run(out, arm, a.src) for arm in a.arms)
    elif a.stage == "compare":
        return cmd_compare(out, *a.arms)
    elif a.stage == "clean":
        for arm in a.arms:
            shutil.rmtree(out / arm / "pilot.ms", ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
