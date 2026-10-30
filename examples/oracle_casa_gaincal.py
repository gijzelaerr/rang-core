"""Task L5-C: CASA `gaincal` on L5's intervals (research/l5c-casa-gaincal.md).

Usage (host, worktree venv):
    python examples/oracle_casa_gaincal.py run {fixture,slice} outputs/l5c-<date>-NN

`run` writes the core's problem arrays (L5's loader) into
`<run>/<set>/problem.npz`, then drives the O-CASA image
(`rang-o-casa:6.7.6.14`) step by step, each step one network-less
container timed by `/usr/bin/time` inside it:

- `copy` (KERN python3, python-casacore): two copies of the source MS
  (`g.ms`, `t.ms`), gated element for element against the core's arrays,
  with FLAG/FLAG_ROW = the core's solve flags (held-out cells included),
  MODEL_DATA = the core's model and SCAN_NUMBER = 1 + the core's time bin;
- `solve G|G-r1|G-r2|G-r3|T|G-wholeband` (CASA venv): one `gaincal` per
  32-channel chunk (`solint='inf'`, `combine=''`, `calmode='ap'`,
  `refant='m000'`, `minsnr=0`, `minblperant=1`); the restarts pre-apply the
  earlier passes; the whole-band call is for cost only;
- `flags` (python3): FLAG with the held-out cells unflagged, for `applycal`;
- `apply G|T` (CASA venv): `applycal` per chunk, `interp='nearest'`;
- `export G|T` (python3): DATA, CORRECTED_DATA, FLAG, rows to `export-*.npz`;
then hashes everything into `<run>/<set>/receipt.json`. The container side
(`container-*` subcommands) imports no `rang`; every input is read-only.
"""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "rang-o-casa:6.7.6.14"
CHUNK = 32  # channels per core frequency bin (L5's grid 2 x 32)
REFANT = "m000"
SOURCES = {
    # set: (source MS relative to the repository, its model column)
    "fixture": ("outputs/tv-response-wsl-20261029-01/clean/work.ms", "RANG_MODEL_DATA"),
    "slice": ("outputs/luno-solve-20261029-02/work.ms", "MODEL_DATA"),
}
SOLVE_ARMS = ("G", "G-r1", "G-r2", "G-r3", "T", "G-wholeband")
GAINCAL = {
    "solint": "inf",
    "combine": "",
    "calmode": "ap",
    "refant": REFANT,
    "minsnr": 0.0,
    "minblperant": 1,
    "solnorm": False,
    "solmode": "",
}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def sha256_array(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def tree_sha256(path):
    """SHA256 over sorted relative paths and file hashes (no table.lock)."""
    path = Path(path)
    h = hashlib.sha256()
    for f in sorted(p for p in path.rglob("*") if p.is_file()):
        if f.name == "table.lock":
            continue
        h.update(f.relative_to(path).as_posix().encode())
        h.update(sha256_file(f).encode())
    return h.hexdigest()


def write_json(path, payload):
    def default(v):
        if isinstance(v, np.ndarray):
            return v.tolist()
        if isinstance(v, np.generic):
            return v.item()
        return str(v)

    Path(path).write_text(json.dumps(payload, indent=1, default=default) + "\n")


def chunks(nchan):
    return [(k, CHUNK * k, CHUNK * k + CHUNK - 1) for k in range(nchan // CHUNK)]


# --- container side: KERN python3 with python-casacore -------------------------


def container_copy(setdir, src, model_column):
    import casacore.tables as pt

    setdir = Path(setdir)
    p = dict(np.load(setdir / "problem.npz"))
    report = {"source": src, "model_column": model_column, "copies": {}}
    for name in ("g", "t"):
        dst = setdir / f"{name}.ms"
        shutil.copytree(src, dst, copy_function=shutil.copyfile)
        lock = dst / "table.lock"
        if lock.exists():
            lock.unlink()
        t = pt.table(str(dst), readonly=False, ack=False)
        gates = {
            "ANTENNA1": bool(np.array_equal(t.getcol("ANTENNA1"), p["antenna1"])),
            "ANTENNA2": bool(np.array_equal(t.getcol("ANTENNA2"), p["antenna2"])),
            "TIME": bool(np.array_equal(t.getcol("TIME"), p["times"])),
            "DATA": bool(np.array_equal(t.getcol("DATA"), p["data"])),
            "WEIGHT_SPECTRUM": bool(
                np.array_equal(t.getcol("WEIGHT_SPECTRUM"), p["weights"])
            ),
            "model": bool(np.array_equal(t.getcol(model_column), p["model"])),
            "one_field": len(np.unique(t.getcol("FIELD_ID"))) == 1,
            "one_ddid": len(np.unique(t.getcol("DATA_DESC_ID"))) == 1,
            "nchan": int(t.getcol("DATA", 0, 1).shape[1]) == p["data"].shape[1],
            "no_model_keyword": not any("model" in k.lower() for k in t.getkeywords()),
            "no_source_model": not (
                (dst / "SOURCE").is_dir()
                and "SOURCE_MODEL"
                in pt.table(str(dst / "SOURCE"), ack=False).colnames()
            ),
        }
        if not all(gates.values()):
            t.close()
            report["copies"][name] = {"gates": gates}
            write_json(setdir / "copy.json", report)
            raise SystemExit(f"gate failed for {name}.ms: {gates}")
        if "MODEL_DATA" not in t.colnames():
            desc = t.getcoldesc("DATA")
            for key in ("comment", "dataManagerType", "dataManagerGroup"):
                desc.pop(key, None)
            t.addcols(pt.maketabdesc(pt.makecoldesc("MODEL_DATA", desc)))
        t.putcol("MODEL_DATA", p["model"])
        t.putcol("FLAG", p["flag"])
        t.putcol("FLAG_ROW", p["flag_row"])
        t.putcol("SCAN_NUMBER", (1 + p["time_map"]).astype(np.int32))
        t.flush()
        back = {
            "MODEL_DATA": bool(np.array_equal(t.getcol("MODEL_DATA"), p["model"])),
            "FLAG": bool(np.array_equal(t.getcol("FLAG"), p["flag"])),
            "FLAG_ROW": bool(np.array_equal(t.getcol("FLAG_ROW"), p["flag_row"])),
            "SCAN_NUMBER": bool(
                np.array_equal(t.getcol("SCAN_NUMBER"), 1 + p["time_map"])
            ),
        }
        t.close()
        report["copies"][name] = {"gates": gates, "read_back": back}
        if not all(back.values()):
            write_json(setdir / "copy.json", report)
            raise SystemExit(f"read-back failed for {name}.ms: {back}")
    write_json(setdir / "copy.json", report)
    return 0


def container_flags(setdir, name):
    """FLAG of `<name>.ms` = solve flags with the held-out cells unflagged."""
    import casacore.tables as pt

    setdir = Path(setdir)
    p = np.load(setdir / "problem.npz")
    flag = p["flag"] & ~p["heldout"][..., None]
    t = pt.table(str(setdir / f"{name}.ms"), readonly=False, ack=False)
    t.putcol("FLAG", flag)
    t.flush()
    ok = bool(np.array_equal(t.getcol("FLAG"), flag))
    t.close()
    write_json(
        setdir / f"flags-{name}.json",
        {"apply_flag_sha256": sha256_array(flag), "read_back": ok},
    )
    return 0 if ok else 1


def container_export(setdir, arm):
    import casacore.tables as pt

    setdir = Path(setdir)
    name = {"G": "g", "T": "t"}[arm]
    t = pt.table(str(setdir / f"{name}.ms"), ack=False)
    cols = {
        c: t.getcol(c)
        for c in ("DATA", "CORRECTED_DATA", "FLAG", "ANTENNA1", "ANTENNA2", "TIME")
    }
    t.close()
    np.savez(setdir / f"export-{arm}.npz", **cols)
    write_json(
        setdir / f"export-{arm}.json",
        {c: sha256_array(v) for c, v in cols.items()},
    )
    return 0


# --- container side: the CASA venv ------------------------------------------------


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _call(task, **params):
    started = time.perf_counter()
    entry = {"params": params}
    try:
        returned = task(**params)
        entry["ok"] = True
        if isinstance(returned, dict):
            entry["solvestats"] = _jsonable(returned.get("solvestats", {}))
    except Exception as error:  # noqa: BLE001 - every CASA failure is recorded
        entry["ok"] = False
        entry["error"] = f"{type(error).__name__}: {error}"
    entry["seconds"] = time.perf_counter() - started
    return entry


def container_solve(setdir, arm):
    from casatasks import casalog, gaincal

    setdir = Path(setdir)
    casalog.setlogfile(str(setdir / "logs" / f"casa-solve-{arm}.log"))
    nchan = int(np.load(setdir / "problem.npz")["data"].shape[1])
    vis = str(setdir / ("t.ms" if arm == "T" else "g.ms"))
    gaintype = "T" if arm == "T" else "G"
    out = setdir / "tables" / arm
    out.mkdir(parents=True)
    log = {
        "arm": arm,
        "vis": vis,
        "gaintype": gaintype,
        "settings": GAINCAL,
        "calls": [],
    }
    started = time.perf_counter()
    if arm == "G-wholeband":
        entry = _call(
            gaincal,
            vis=vis,
            caltable=str(out / "all.tab"),
            spw="",
            gaintype=gaintype,
            gaintable=[],
            **GAINCAL,
        )
        entry["chunk"] = None
        entry["table"] = (out / "all.tab").is_dir()
        log["calls"].append(entry)
    else:
        passes = {"G-r1": ["G"], "G-r2": ["G", "G-r1"], "G-r3": ["G", "G-r1", "G-r2"]}
        for k, lo, hi in chunks(nchan):
            cal = out / f"c{k:03d}.tab"
            pre = [setdir / "tables" / a / f"c{k:03d}.tab" for a in passes.get(arm, [])]
            if not all(p.is_dir() for p in pre):
                log["calls"].append(
                    {"chunk": k, "skipped": "no earlier solution", "table": False}
                )
                continue
            entry = _call(
                gaincal,
                vis=vis,
                caltable=str(cal),
                spw=f"0:{lo}~{hi}",
                gaintype=gaintype,
                gaintable=[str(p) for p in pre],
                interp=["nearest"] * len(pre),
                **GAINCAL,
            )
            entry["chunk"] = k
            entry["table"] = cal.is_dir()
            log["calls"].append(entry)
    log["seconds"] = time.perf_counter() - started
    log["task_seconds"] = float(sum(c.get("seconds", 0.0) for c in log["calls"]))
    log["failed"] = [c["chunk"] for c in log["calls"] if c.get("ok") is False]
    write_json(setdir / "casa" / f"solve-{arm}.json", log)
    return 1 if log["failed"] else 0


def container_apply(setdir, arm):
    from casatasks import applycal, casalog

    setdir = Path(setdir)
    casalog.setlogfile(str(setdir / "logs" / f"casa-apply-{arm}.log"))
    nchan = int(np.load(setdir / "problem.npz")["data"].shape[1])
    vis = str(setdir / ("t.ms" if arm == "T" else "g.ms"))
    log = {"arm": arm, "vis": vis, "calls": []}
    started = time.perf_counter()
    for k, lo, hi in chunks(nchan):
        cal = setdir / "tables" / arm / f"c{k:03d}.tab"
        if not cal.is_dir():
            log["calls"].append({"chunk": k, "skipped": "no table"})
            continue
        entry = _call(
            applycal,
            vis=vis,
            spw=f"0:{lo}~{hi}",
            gaintable=[str(cal)],
            interp=["nearest"],
            calwt=[False],
            applymode="calflag",
            parang=False,
            flagbackup=False,
        )
        entry["chunk"] = k
        log["calls"].append(entry)
    log["seconds"] = time.perf_counter() - started
    log["failed"] = [c["chunk"] for c in log["calls"] if c.get("ok") is False]
    write_json(setdir / "casa" / f"apply-{arm}.json", log)
    return 1 if log["failed"] else 0


# --- host side --------------------------------------------------------------------


def prepare(dataset, setdir):
    """The arrays the core solves (L5's loader), for the container gates."""
    sys.path.insert(0, str(ROOT / "examples"))
    import run_l5_solver_study as l5

    started = time.perf_counter()
    problem, state, _, info = l5.load(dataset)
    if state is None:  # the fixture: times from its state
        from validate_core_phase2 import FIXTURE

        with np.load(FIXTURE / "state.npz") as z:
            times = z["times"]
    else:
        times = state["times"]
    nchan = problem["data"].shape[1]
    if not np.array_equal(problem["freq_map"], np.arange(nchan) // CHUNK):
        raise SystemExit("frequency bins are not 32-channel chunks")
    heldout = np.asarray(problem["validation"] | problem["test"], bool)
    flag = np.asarray(problem["flag"], bool)
    if flag.ndim == 2:
        flag = np.repeat(flag[..., None], 4, axis=-1)
    arrays = {
        "data": problem["data"],
        "weights": problem["weights"],
        "model": problem["model"],
        "flag": flag,
        "flag_row": np.asarray(problem["flag_row"], bool),
        "antenna1": problem["antenna1"].astype(np.int32),
        "antenna2": problem["antenna2"].astype(np.int32),
        "times": np.asarray(times, np.float64),
        "time_map": problem["time_map"].astype(np.int32),
        "heldout": heldout,
    }
    np.savez(setdir / "problem.npz", **arrays)
    report = {
        "dataset": dataset,
        "loader": info,
        "shape": list(problem["data"].shape),
        "intervals": [int(problem["ntime_bins"]), int(problem["nfreq_bins"])],
        "heldout_cells": int(heldout.sum()),
        "heldout_flagged_in_solve_flags": int((heldout & flag.any(-1)).sum()),
        "sha256": {k: sha256_array(v) for k, v in arrays.items()},
        "seconds": time.perf_counter() - started,
    }
    if report["heldout_flagged_in_solve_flags"] != report["heldout_cells"]:
        raise SystemExit("solve flags do not contain every held-out cell")
    write_json(setdir / "prepare.json", report)
    return report


def docker(run, setdir, src, step, argv, casa):
    """One timed container step; returns its exit status."""
    rel = setdir.relative_to(run)
    timing = f"/run/{rel}/timing/{step}.txt"
    python = ["/opt/casa/bin/python"] if casa else ["python3"]
    cmd = [
        "docker",
        "run",
        "--rm",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--network",
        "none",
        "--tmpfs",
        "/tmp",
        "-e",
        "HOME=/tmp",
        "-e",
        "OMP_NUM_THREADS=4",
        "-v",
        f"{src}:/src.ms:ro",
        "-v",
        f"{ROOT / 'examples'}:/code:ro",
        "-v",
        f"{run}:/run",
        "-w",
        f"/run/{rel}",
        IMAGE,
        "/usr/bin/time",
        "-f",
        "%e %M %U %S %x",
        "-o",
        timing,
        *python,
        "-I",
        "/code/oracle_casa_gaincal.py",
        *argv,
    ]
    print(f"## {setdir.name} {step}", flush=True)
    with open(setdir / "logs" / f"{step}.log", "w") as log:
        status = subprocess.run(
            cmd, stdout=log, stderr=subprocess.STDOUT, check=False
        ).returncode
    return status


def read_timing(path):
    wall, rss, user, system, status = Path(path).read_text().split()[-5:]
    return {
        "wall_seconds": float(wall),
        "peak_rss_mb": int(rss) / 1024,
        "user_seconds": float(user),
        "system_seconds": float(system),
        "exit": int(status),
    }


def image_facts():
    out = subprocess.run(
        ["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return {"image": IMAGE, "id": out.stdout.strip()}


def run(dataset, run_dir):
    run_dir = Path(run_dir).resolve()
    setdir = run_dir / dataset
    if setdir.exists():
        raise SystemExit(f"{setdir} exists; choose a fresh run directory")
    for sub in ("logs", "timing", "casa"):
        (setdir / sub).mkdir(parents=True)
    started = time.time()
    src_rel, model_column = SOURCES[dataset]
    src = (ROOT / src_rel).resolve()
    prepare(dataset, setdir)
    steps = [
        ("copy", ["container-copy", f"/run/{dataset}", "/src.ms", model_column], False)
    ]
    steps += [
        (f"solve-{a}", ["container-solve", f"/run/{dataset}", a], True)
        for a in SOLVE_ARMS
    ]
    for arm, name in (("G", "g"), ("T", "t")):
        steps += [
            (f"flags-{arm}", ["container-flags", f"/run/{dataset}", name], False),
            (f"apply-{arm}", ["container-apply", f"/run/{dataset}", arm], True),
            (f"export-{arm}", ["container-export", f"/run/{dataset}", arm], False),
        ]
    status = {}
    for step, argv, casa in steps:
        status[step] = docker(run_dir, setdir, src, step, argv, casa)
        if status[step] != 0:
            print(f"step {step} exited {status[step]}", flush=True)
            break
    receipt = {
        "task": "L5-C",
        "dataset": dataset,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "image": image_facts(),
        "source_ms": {
            "path": src_rel,
            "model_column": model_column,
            "tree_sha256": tree_sha256(src),
        },
        "code_sha256": {
            p: sha256_file(ROOT / p)
            for p in (
                "examples/oracle_casa_gaincal.py",
                "examples/run_l5_solver_study.py",
            )
        },
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "git_status": subprocess.check_output(
            ["git", "status", "--short"], cwd=ROOT, text=True
        ),
        "host": {"python": platform.python_version(), "loadavg": os.getloadavg()},
        "settings": {"gaincal": GAINCAL, "chunk_channels": CHUNK, "omp_num_threads": 4},
        "status": status,
        "timing": {
            p.stem: read_timing(p) for p in sorted((setdir / "timing").glob("*.txt"))
        },
        "outputs": {
            "tables": {
                str(p.relative_to(setdir)): tree_sha256(p)
                for p in sorted((setdir / "tables").glob("*/*.tab"))
            },
            "exports": {
                p.name: sha256_file(p) for p in sorted(setdir.glob("export-*.npz"))
            },
        },
    }
    write_json(setdir / "receipt.json", receipt)
    failed = {k: v for k, v in status.items() if v}
    print(
        json.dumps(
            {
                "dataset": dataset,
                "failed": failed,
                "wall_seconds": time.time() - started,
            }
        )
    )
    return 1 if failed else 0


def main(argv):
    command = argv[1] if len(argv) > 1 else ""
    if command == "run":
        return run(argv[2], argv[3])
    if command == "container-copy":
        return container_copy(*argv[2:5])
    if command == "container-solve":
        return container_solve(*argv[2:4])
    if command == "container-flags":
        return container_flags(*argv[2:4])
    if command == "container-apply":
        return container_apply(*argv[2:4])
    if command == "container-export":
        return container_export(*argv[2:4])
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
