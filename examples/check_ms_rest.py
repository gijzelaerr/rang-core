"""The host checker of task E5 (research/e5-table-writer-rest.md).

    python examples/check_ms_rest.py oracle <run> [<label> [<env>=<v>]]
    python examples/check_ms_rest.py cases <run> [<label>] [<case> ...]
    python examples/check_ms_rest.py determinism <run>
    python examples/check_ms_rest.py readback <run>
    python examples/check_ms_rest.py refusals <run>
    python examples/check_ms_rest.py regress <run>
    python examples/check_ms_rest.py serialisation <run>
    python examples/check_ms_rest.py summary <run>

`oracle` runs `examples/oracle_ms_rest.py write` and `write-mf` in the
pinned python-casacore container into `<run>/oracle[-<label>]` (with
environment variables such as `MALLOC_PERTURB_=85`). `cases` replays every
frozen case (or the named ones) with `rang.core_ms_write` into
`<run>/core[-<label>]/<case>` with the oracle's stored values and compares
every file with casacore's (criterion 1: `table.lock` from offset 260; the
two exceptions of the protocol masked, nothing else). The other steps check
criteria 2 to 6; each writes `<run>/<step>.json`; `summary` writes
`<run>/result.json`.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import oracle_ms_rest as oracle
from rang import core, core_ms_write

LOCK_REQUESTS = 260
MS_IMAGE = "rang-ms-reader:local"
# Records no row references any more, by case: the element size of the
# column whose old value they hold.
ORPHAN_BITS = {
    "I-arrays": 64,
    "I-rows-all": 64,
    "I-pointing": 64,
    "I-fixture-pointing": 64,
    "B-new": 64,
    "B-write": 64,
    "F-new": 64,
    "F-write": 64,
}


def outputs_root():
    return (HERE.parent / "outputs").resolve()


def fixture_path():
    return outputs_root() / "tv-caracal-wsl-20261029-01" / "original.ms"


def luno_path():
    return outputs_root() / "luno-solve-20261029-02" / "work.ms"


def tree(path):
    root = Path(path)
    return {
        p.relative_to(root).as_posix(): p
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def write_json(out, step, result, started):
    result["wall_s"] = time.perf_counter() - started
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / f"{step}.json").write_text(json.dumps(result, indent=1, default=str))
    return result


# ---------------------------------------------------------------------------
# The masks of the protocol.


def array_file_order(data):
    """Whether an array file is big-endian: its length field (bytes 4-11)
    is the file's length in the right byte order."""
    le = int.from_bytes(data[4:12], "little")
    be = int.from_bytes(data[4:12], "big")
    if le == len(data):
        return False
    return be == len(data)


def gap_mask(table_dir, name, data, orphan_bits):
    """The alignment gaps of an array file (`table.fNi`, version 0 or 1,
    either byte order) as a boolean mask, from the record chain of the
    oracle's copy; None if the chain does not walk exactly to the end."""
    refs = {}
    for file, offset, bits in core.extension().ms_array_records(str(table_dir)):
        if file == name:
            refs[offset] = bits
    order = "big" if array_file_order(data) else "little"
    mask = np.zeros(len(data), bool)
    version = int.from_bytes(data[0:4], order)
    at, end = 16, 16
    while at < len(data):
        bits = refs.get(at, orphan_bits)
        if bits is None:
            return None
        head = at + (4 if version > 0 else 0)
        ndim = int.from_bytes(data[head : head + 4], order)
        dims = [
            int.from_bytes(
                data[head + 4 + 4 * i : head + 8 + 4 * i], order, signed=True
            )
            for i in range(ndim)
        ]
        n = int(np.prod(dims)) if dims else 1
        values = (n + 7) // 8 if bits == 1 else n * bits // 8
        end = head + 4 + 4 * ndim + values
        nxt = (end + 7) // 8 * 8
        mask[end : min(nxt, len(data))] = True
        at = nxt
    return mask if end == len(data) else None


def multifile_mask(data):
    """The MultiFile header tail: block 0 from the header length on."""
    mask = np.zeros(len(data), bool)
    if len(data) < 64:
        return mask
    length = int.from_bytes(data[32:40], "big")
    block = int.from_bytes(data[40:48], "big")
    mask[length : min(block, len(data))] = True
    return mask


def compare_trees(ours, theirs, orphan_bits=None):
    """Every file byte for byte; table.lock from its sync record on; the
    gaps of table.fNi and the MultiFile header tail masked."""
    a, b = tree(ours), tree(theirs)
    out = {
        "missing": sorted(set(b) - set(a)),
        "extra": sorted(set(a) - set(b)),
        "differ": [],
        "masked": [],
    }
    for name in sorted(set(a) & set(b)):
        x, y = a[name].read_bytes(), b[name].read_bytes()
        if name.endswith("table.lock"):
            x, y = x[LOCK_REQUESTS:], y[LOCK_REQUESTS:]
        if x == y:
            continue
        n = min(len(x), len(y))
        diff = np.flatnonzero(
            np.frombuffer(x[:n], np.uint8) != np.frombuffer(y[:n], np.uint8)
        )
        entry = {
            "file": name,
            "ours": len(x),
            "theirs": len(y),
            "bytes_differing": int(diff.size) + abs(len(x) - len(y)),
            "first_difference": int(diff[0]) if diff.size else n,
        }
        file = Path(name)
        mask = None
        if len(x) == len(y):
            if file.name.startswith("table.f") and file.name.endswith("i"):
                mask = gap_mask(b[name].parent, file.name, y, orphan_bits)
                kind = "gap_bytes_masked"
            elif file.name == "table.mf":
                mask = multifile_mask(y)
                kind = "multifile_header_bytes_masked"
        if mask is not None and not np.any(~mask[diff]):
            entry[kind] = int(diff.size)
            out["masked"].append(entry)
            continue
        out["differ"].append(entry)
    out["identical"] = not (
        out["missing"] or out["extra"] or out["differ"] or out["masked"]
    )
    out["identical_but_masked"] = not (out["missing"] or out["extra"] or out["differ"])
    return out


# ---------------------------------------------------------------------------
# The oracle runs.


def docker(image, args, mounts, env=None, extra=()):
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        *extra,
    ]
    for k, v in (env or {}).items():
        cmd += ["-e", f"{k}={v}"]
    for host, guest, mode in mounts:
        cmd += ["-v", f"{host}:{guest}:{mode}"]
    cmd += [image, *args]
    start = time.perf_counter()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"container failed: {proc.stdout[-3000:]}\n{proc.stderr[-3000:]}"
        )
    return time.perf_counter() - start, proc.stdout


def run_mounts(run):
    return [
        (str(Path(run).resolve()), "/run", "rw"),
        (str(HERE), "/ex", "ro"),
        (str(fixture_path()), "/fx/original.ms", "ro"),
        (str(luno_path()), "/fx/work.ms", "ro"),
    ]


def guest(run, path):
    return "/run/" + Path(path).resolve().relative_to(Path(run).resolve()).as_posix()


def step_oracle(run, label="", *envs):
    started = time.perf_counter()
    run = Path(run)
    name = "oracle" + (f"-{label}" if label else "")
    out = run / name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    env = dict(e.split("=", 1) for e in envs)
    (run / "casarc").write_text("table.storage.option: multifile\n")
    wall, log = docker(
        MS_IMAGE,
        [
            "/ex/oracle_ms_rest.py",
            "write",
            f"/run/{name}",
            "/fx/original.ms",
            "/fx/work.ms",
        ],
        run_mounts(run),
        env,
    )
    wall_mf, log_mf = docker(
        MS_IMAGE,
        ["/ex/oracle_ms_rest.py", "write-mf", f"/run/{name}"],
        run_mounts(run),
        {**env, "CASARCFILES": "/run/casarc"},
    )
    (out / "oracle.log").write_text(log + log_mf)
    result = {"container_s": wall, "container_mf_s": wall_mf, "env": env, "pass": True}
    print(log + log_mf, flush=True)
    return write_json(run, name, result, started)


def load_values(oracle_dir, name):
    with np.load(Path(oracle_dir) / "values" / f"{name}.npz", allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def casacore_walls(oracle_dir):
    out = {}
    for f in ("cases.json", "cases-mf.json"):
        p = Path(oracle_dir) / f
        if p.exists():
            out.update({c["name"]: c["wall_s"] for c in json.loads(p.read_text())})
    return out


# ---------------------------------------------------------------------------
# Criterion 1: the cases.


def replay(oracle_dir, root, only=()):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    sources = {"FIXTURE": fixture_path(), "LUNO": luno_path()}
    sources.update(
        {name: Path(oracle_dir) / "casacore" / name for name, _ in oracle.CASES}
    )
    walls = {}
    for name, f in oracle.CASES:
        if only and name not in only:
            continue
        stored = load_values(oracle_dir, name)
        try:
            _, wall = oracle.run_case(core_ms_write, name, f, root, sources, stored)
            walls[name] = (wall, None)
        except Exception as e:  # noqa: BLE001 - recorded per case
            walls[name] = (None, f"{type(e).__name__}: {e}")
    return walls


REFUSAL_CASES = ("T-reshape",)


def step_cases(run, label="", *only):
    started = time.perf_counter()
    run = Path(run)
    oracle_dir = run / "oracle"
    root = run / ("core" + (f"-{label}" if label else ""))
    walls = replay(oracle_dir, root, only)
    cwalls = casacore_walls(oracle_dir)
    report = []
    for name, f in oracle.CASES:
        if name not in walls:
            continue
        wall, error = walls[name]
        entry = {
            "name": name,
            "core_s": wall,
            "casacore_s": cwalls.get(name),
            "error": error,
        }
        if error is None:
            entry.update(
                compare_trees(
                    root / name, oracle_dir / "casacore" / name, ORPHAN_BITS.get(name)
                )
            )
            files = tree(root / name)
            entry["files"] = len(files)
            entry["bytes"] = sum(p.stat().st_size for p in files.values())
            if name in REFUSAL_CASES:
                stored = load_values(oracle_dir, name)
                entry["both_refuse"] = bool(stored.get("refused", False))
        else:
            entry["identical"] = entry["identical_but_masked"] = False
        report.append(entry)
        state = (
            "identical"
            if entry["identical"]
            else ("masked only" if entry["identical_but_masked"] else "DIFFERS")
        )
        detail = entry.get("differ", error)
        print(
            f"{name}: {state} {detail if detail else ''} {entry.get('masked', '') or ''}",
            flush=True,
        )
    result = {"cases": report, "pass": all(r["identical_but_masked"] for r in report)}
    return write_json(run, "cases" + (f"-{label}" if label else ""), result, started)


def hashes(path):
    out = {}
    for name, p in tree(path).items():
        data = p.read_bytes()
        if name.endswith("table.lock"):
            data = data[LOCK_REQUESTS:]
        out[name] = hashlib.sha256(data).hexdigest()
    return out


def step_determinism(run):
    """Criterion 3: two core runs and one under MALLOC_PERTURB_=85 give the
    same bytes (no mask); casacore's second and perturbed runs equal its
    first except in masked bytes."""
    started = time.perf_counter()
    run = Path(run)
    for label, env in (("twin", {}), ("perturb", {"MALLOC_PERTURB_": "85"})):
        cmd = [sys.executable, str(Path(__file__)), "cases", str(run), label]
        subprocess.run(cmd, check=True, env={**os.environ, **env}, capture_output=True)
    core_ok = {}
    for name, _ in oracle.CASES:
        first = hashes(run / "core" / name)
        core_ok[name] = all(
            hashes(run / f"core-{k}" / name) == first for k in ("twin", "perturb")
        )
    casacore = {}
    for label in ("oracle-twin", "oracle-perturb"):
        other = run / label
        if not other.exists():
            continue
        per = {}
        for name, _ in oracle.CASES:
            d = compare_trees(
                other / "casacore" / name,
                run / "oracle" / "casacore" / name,
                ORPHAN_BITS.get(name),
            )
            per[name] = {
                "identical": d["identical"],
                "identical_but_masked": d["identical_but_masked"],
                "masked": [
                    (
                        m["file"],
                        m.get(
                            "gap_bytes_masked", m.get("multifile_header_bytes_masked")
                        ),
                    )
                    for m in d["masked"]
                ],
                "differ": d["differ"],
            }
        casacore[label] = per
    result = {
        "core_identical_between_runs": core_ok,
        "casacore": casacore,
        "pass": all(core_ok.values())
        and all(
            v["identical_but_masked"] for per in casacore.values() for v in per.values()
        ),
    }
    print(json.dumps({"core": core_ok}, indent=0), flush=True)
    return write_json(run, "determinism", result, started)


# ---------------------------------------------------------------------------
# Criterion 2: read-back.


def read_table_cells(path):
    """Every cell of every column (None: undefined), read by the core
    without writing; a column that cannot be read is recorded."""
    nrows, columns = core_ms_write.describe(path)
    cells, errors = {}, {}
    for name in columns:
        try:
            values = core_ms_write.read_cells(path, name, 0, nrows) if nrows else []
        except Exception as e:  # noqa: BLE001 - recorded per column
            errors[name] = str(e)
            continue
        cells[name] = values
    return nrows, cells, errors


def same_array(a, b):
    a, b = np.asarray(a), np.asarray(b)
    if a.dtype.kind in "USO" or b.dtype.kind in "USO":
        return a.shape == b.shape and [str(x) for x in a.reshape(-1)] == [
            str(x) for x in b.reshape(-1)
        ]
    return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()


def load_dump(dump_dir, label):
    with np.load(Path(dump_dir) / f"{label}.npz", allow_pickle=False) as z:
        cells = {k: z[k] for k in z.files}
    meta = json.loads((Path(dump_dir) / f"{label}.json").read_text())
    return cells, meta


def compare_dumps(a, b):
    (ca, ma), (cb, mb) = a, b
    problems = []
    for key in ("nrows", "info", "keywords"):
        if ma[key] != mb[key]:
            problems.append(f"{key} differ")
    for name in sorted(set(ma["columns"]) | set(mb["columns"])):
        if ma["columns"].get(name) != mb["columns"].get(name):
            problems.append(f"column {name} keywords or errors differ")
    if set(ca) != set(cb):
        problems.append(f"defined cells differ: {sorted(set(ca) ^ set(cb))[:5]}")
    for k in sorted(set(ca) & set(cb)):
        if not same_array(ca[k], cb[k]):
            problems.append(f"cell {k} differs")
            if len(problems) > 20:
                break
    return problems


def core_vs_dump(path, dump, skip=()):
    cells, meta = dump
    nrows, core_cells, errors = read_table_cells(path)
    problems = [f"{k}: {v}" for k, v in errors.items() if k not in skip]
    if nrows != meta["nrows"]:
        problems.append(f"nrows {nrows} != {meta['nrows']}")
    for name, values in core_cells.items():
        if "error" in meta["columns"].get(name, {}) or name in skip:
            continue
        for row, value in enumerate(values):
            key = f"{name}/{row}"
            if value is None:
                if key in cells:
                    problems.append(f"{key} undefined in the core")
            elif key not in cells:
                problems.append(f"{key} undefined in casacore")
            elif not same_array(value, cells[key]):
                theirs = np.asarray(cells[key])
                uchar = value.dtype == np.uint8 and theirs.dtype == np.uint16
                if not (uchar and same_array(value.astype(np.uint16), theirs)):
                    problems.append(f"{key} differs")
    return problems


def tables_of(path):
    path = Path(path)
    return [("", path)] + [
        (f".{p.parent.name}", p.parent) for p in sorted(path.glob("*/table.dat"))
    ]


def casacure_reads(path):
    """casacure's cells of a table (None when it cannot open it)."""
    try:
        from casacure import tables as cc
    except ImportError:
        return None, "casacure is not installed"
    try:
        t = cc.table(str(path), ack=False)
    except Exception as e:  # noqa: BLE001 - recorded
        return None, str(e)
    cells, errors = {}, {}
    try:
        for name in t.colnames():
            for row in range(t.nrows()):
                try:
                    if not t.iscelldefined(name, row):
                        continue
                    if t.isscalarcol(name):
                        value = t.getcol(name, row, 1)[0]
                    else:
                        value = t.getcell(name, row)
                except Exception as e:  # noqa: BLE001 - recorded per column
                    errors[name] = str(e)
                    break
                arr = np.asarray(value)
                if arr.dtype.kind in "USO":
                    arr = np.asarray(arr, dtype=str)
                cells[f"{name}/{row}"] = arr
    finally:
        t.close()
    return cells, errors


def step_readback(run):
    """python-casacore dumps the core's tables and casacore's; they must
    agree; casacure reads both alike where it can; the core reads
    casacore's tables as python-casacore does."""
    started = time.perf_counter()
    run = Path(run)
    dumps = run / "dumps"
    pairs = []
    for name, _ in oracle.CASES:
        pairs += [
            f"core.{name}={guest(run, run / 'core' / name)}",
            f"cc.{name}={guest(run, run / 'oracle' / 'casacore' / name)}",
        ]
    wall, _ = docker(
        MS_IMAGE,
        ["/ex/oracle_ms_rest.py", "readback", guest(run, dumps), *pairs],
        run_mounts(run),
    )
    memory = {}
    for name, columns in oracle.MEMORY_COLUMNS.items():
        for side, base in (
            ("core", run / "core"),
            ("casacore", run / "oracle" / "casacore"),
        ):
            for c in columns:
                target = dumps / f"memory.{side}.{name}.{c}.json"
                try:
                    docker(
                        MS_IMAGE,
                        [
                            "/ex/oracle_ms_rest.py",
                            "read-column",
                            guest(run, target),
                            guest(run, base / name),
                            c,
                        ],
                        run_mounts(run),
                    )
                except RuntimeError:
                    pass  # casacore aborts at exit; the record is written first
                memory[f"{side}.{name}.{c}"] = (
                    json.loads(target.read_text())
                    if target.exists()
                    else {"error": "no record"}
                )
            try:
                core_ms_write.read_cells(base / name, columns[0], 0, 1)
                memory[f"core-reader.{side}.{name}"] = "read"
            except Exception as e:  # noqa: BLE001 - the refusal is the result
                memory[f"core-reader.{side}.{name}"] = f"raises: {e}"
    report = {}
    for name, _ in oracle.CASES:
        path = run / "oracle" / "casacore" / name
        skip = oracle.MEMORY_COLUMNS.get(name, ())
        for suffix, table in tables_of(path):
            a = load_dump(dumps, f"core.{name}{suffix}")
            b = load_dump(dumps, f"cc.{name}{suffix}")
            problems = compare_dumps(a, b)
            core_problems = core_vs_dump(table, b, skip if not suffix else ())
            cc_ours, cc_err = casacure_reads(run / "core" / name / suffix.lstrip("."))
            cc_theirs, _ = casacure_reads(table)
            if cc_ours is None or cc_theirs is None:
                casacure = {"reads": False, "reason": cc_err}
            else:
                same = set(cc_ours) == set(cc_theirs) and all(
                    same_array(cc_ours[k], cc_theirs[k]) for k in cc_ours
                )
                casacure = {"reads": True, "same": same}
            report[f"{name}{suffix}"] = {
                "python_casacore_same": not problems,
                "core_reads_same": not core_problems,
                "casacure": casacure,
                "problems": problems[:10],
                "core_problems": core_problems[:10],
                "cells": len(b[0]),
            }
    bad = {
        k: v
        for k, v in report.items()
        if not (v["python_casacore_same"] and v["core_reads_same"])
        or (v["casacure"].get("reads") and not v["casacure"].get("same"))
    }
    for k, v in bad.items():
        print(k, v["problems"][:3], v["core_problems"][:3], v["casacure"], flush=True)
    memory_ok = all(
        "error" in memory.get(f"{side}.{n}.{c}", {})
        for n, cols in oracle.MEMORY_COLUMNS.items()
        for side in ("core", "casacore")
        for c in cols
    ) and all(
        str(memory.get(f"core-reader.{side}.{n}", "")).startswith("raises")
        for n in oracle.MEMORY_COLUMNS
        for side in ("core", "casacore")
    )
    result = {
        "tables": len(report),
        "cells": sum(v["cells"] for v in report.values()),
        "casacure_unreadable": sorted(
            k for k, v in report.items() if not v["casacure"]["reads"]
        ),
        "memory_columns": memory,
        "memory_columns_refused_both": memory_ok,
        "failures": bad,
        "container_s": wall,
        "pass": not bad and memory_ok,
    }
    return write_json(run, "readback", result, started)


# ---------------------------------------------------------------------------
# Criterion 5: refusals.


def step_refusals(run):
    started = time.perf_counter()
    run = Path(run)
    scratch = run / "refusals"
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    pt = core_ms_write
    arr = pt.makearrcoldesc("A", 0.0, shape=[4], valuetype="float")

    def dm(kind, cols, spec=None):
        return {"*1": {"TYPE": kind, "NAME": "X", "SPEC": spec or {}, "COLUMNS": cols}}

    def tds_put(p):
        td = oracle.tds_desc(pt)
        pt.table(str(p), td, nrow=3, dminfo=oracle.TDS_DM).close()
        before = hashes(p)
        t = pt.open_table(p, readonly=False)
        try:
            t.putcol("D", np.zeros((3, 4, 8), np.float32))
        finally:
            t.close()
            after = hashes(p)
            changed = sorted(
                k
                for k in before
                if before[k] != after.get(k)
                and not k.endswith(("table.dat", "table.lock"))
            )
            report["TiledDataStMan values: data files unchanged"] = not changed

    attempts = {
        "TiledCellStMan": lambda p: pt.create_table(
            p, [arr], 3, dm("TiledCellStMan", ["A"])
        ),
        "TiledDataStMan values": tds_put,
        "MultiHDF5": lambda p: pt.create_table(p, [arr], 3, multifile="hdf5"),
    }
    report = {}
    for label, f in attempts.items():
        path = scratch / label.replace(" ", "-")
        before = hashes(path) if path.exists() else None
        try:
            r = f(path)
            if r is not None:
                r.close()
            report[label] = {"refused": False}
        except Exception as e:  # noqa: BLE001 - the refusal is the result
            entry = {"refused": True, "names_e6": "E6" in str(e), "message": str(e)}
            if label != "TiledDataStMan values":
                entry["no_table"] = not (path / "table.dat").exists()
            report[label] = entry
        del before
    flags = {k: report.pop(k) for k in list(report) if not isinstance(report[k], dict)}
    result = {
        "attempts": report,
        "checks": flags,
        "pass": all(v["refused"] and v["names_e6"] for v in report.values())
        and all(v.get("no_table", True) for v in report.values())
        and all(flags.values()),
    }
    print(json.dumps(result, indent=1), flush=True)
    return write_json(run, "refusals", result, started)


# ---------------------------------------------------------------------------
# Criterion 4: E3 and E4 unchanged; criterion 6: serialisation.

E3_MSS = (
    "tv-caracal-wsl-20261029-01/original.ms",
    "luno-solve-20261029-02/work.ms",
    "tv-next-imaging-wsl-20261029-01/caracal-diagnostic.ms",
)


def step_regress(run):
    started = time.perf_counter()
    run = Path(run)
    out3 = run / "e3"
    out4 = run / "e4"
    for o in (out3, out4):
        if o.exists():
            shutil.rmtree(o)
    results = {}
    steps = [
        (
            "e3.cases",
            "check_ms_writer.py",
            ["cases", str(outputs_root() / "e3-20261030-01"), str(out3)],
            out3 / "cases.json",
        ),
        (
            "e3.roundtrip",
            "check_ms_writer.py",
            ["roundtrip", str(out3)] + [str(outputs_root() / p) for p in E3_MSS],
            out3 / "roundtrip.json",
        ),
        (
            "e3.serialisation",
            "check_ms_writer.py",
            ["serialisation", str(out3)] + [str(outputs_root() / p) for p in E3_MSS],
            out3 / "serialisation.json",
        ),
        (
            "e4.cases",
            "check_ms_create.py",
            ["cases", str(outputs_root() / "e4-20261030-01" / "oracle"), str(out4)],
            out4 / "cases.json",
        ),
    ]
    for label, script, args, target in steps:
        t0 = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, str(HERE / script), *args],
            check=False,
            capture_output=True,
            text=True,
        )
        data = json.loads(target.read_text()) if target.exists() else {}
        results[label] = {
            "returncode": proc.returncode,
            "stderr": proc.stderr[-2000:],
            "result": data,
            "wall_s": time.perf_counter() - t0,
        }
    e3 = results["e3.cases"]["result"].get("cases", [])
    e3_identical = sum(1 for c in e3 if c.get("identical"))
    e3_padding = sum(
        1 for c in e3 if not c.get("identical") and c.get("identical_but_padding")
    )
    e4 = results["e4.cases"]["result"].get("cases", [])
    e4_ok = sum(1 for c in e4 if c.get("identical_but_gaps"))
    result = {
        "e3_cases_identical": e3_identical,
        "e3_cases_padding_only": e3_padding,
        "e3_roundtrip_pass": results["e3.roundtrip"]["result"].get("pass"),
        "e3_serialisation_pass": results["e3.serialisation"]["result"].get("pass"),
        "e4_cases_identical_or_gaps": e4_ok,
        "e4_cases": len(e4),
        "details": {
            k: {
                "returncode": v["returncode"],
                "stderr": v["stderr"],
                "wall_s": v["wall_s"],
            }
            for k, v in results.items()
        },
    }
    result["pass"] = (
        e3_identical == 20
        and e3_padding == 4
        and bool(result["e3_roundtrip_pass"])
        and bool(result["e3_serialisation_pass"])
        and e4_ok == 18
        and len(e4) == 18
    )
    print(json.dumps({k: v for k, v in result.items() if k != "details"}), flush=True)
    return write_json(run, "regress", result, started)


def step_serialisation(run):
    started = time.perf_counter()
    run = Path(run)
    report, totals = {}, [0, 0, 0, 0]
    for name, _ in oracle.CASES:
        t = run / "oracle" / "casacore" / name
        if (t / "table.mf").exists():
            report[name] = core.extension().ms_multifile_check(str(t))
            totals_mf = report[name]
            if not totals_mf:
                report[name] = []
            continue
        n_tables, ssm, tiled, ism, failures = (
            core.extension().ms_serialisation_check_e5(str(t))
        )
        totals = [
            totals[0] + n_tables,
            totals[1] + ssm,
            totals[2] + tiled,
            totals[3] + ism,
        ]
        report[name] = failures
    result = {
        "tables": totals[0],
        "ssm_files": totals[1],
        "tiled_headers": totals[2],
        "ism_files": totals[3],
        "failures": {k: v for k, v in report.items() if v},
    }
    result["pass"] = not result["failures"]
    print(json.dumps(result), flush=True)
    return write_json(run, "serialisation", result, started)


def step_summary(run):
    run = Path(run)
    names = {
        "1 byte identity": "cases",
        "2 read-back": "readback",
        "3 determinism": "determinism",
        "4 E3 and E4 unchanged": "regress",
        "5 refusals": "refusals",
        "6 serialisation identity": "serialisation",
    }
    result = {}
    for label, step in names.items():
        f = run / f"{step}.json"
        result[label] = json.loads(f.read_text()).get("pass") if f.exists() else None
    result["all_pass"] = all(v is True for v in result.values())
    (run / "result.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    return result


def main(argv):
    steps = {
        "oracle": step_oracle,
        "cases": step_cases,
        "determinism": step_determinism,
        "readback": step_readback,
        "refusals": step_refusals,
        "regress": step_regress,
        "serialisation": step_serialisation,
        "summary": step_summary,
    }
    if len(argv) < 2 or argv[1] not in steps:
        print(__doc__)
        return 2
    steps[argv[1]](*argv[2:])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
