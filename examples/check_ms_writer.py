"""Check the core table writer against python-casacore (research/e3-table-writer.md).

Usage, on the host (the core writes; python-casacore runs in the container
`rang-ms-reader:local`, started by this script through Docker):

    python examples/check_ms_writer.py cases <oracle-dir> <out>
    python examples/check_ms_writer.py readback <oracle-dir> <out>
    python examples/check_ms_writer.py roundtrip <out> <ms> [<ms> ...]
    python examples/check_ms_writer.py reader <out> <task-e-oracle-dir>
    python examples/check_ms_writer.py addcols <out>
    python examples/check_ms_writer.py locks <out> <ms>
    python examples/check_ms_writer.py serialisation <out> <ms> [<ms> ...]
    python examples/check_ms_writer.py scale <oracle-dir> <out>
    python examples/check_ms_writer.py summary <out>

`<oracle-dir>` is the output of `examples/oracle_ms_write.py write` (cases)
and `scale-build`/`scale-write` (scale). `cases` replays every frozen case
of `<oracle-dir>/cases.json` with `rang.core_ms_write` on a fresh copy of
its input and compares every file with casacore's copy (criterion 1). The
other steps are criteria 2 to 8 in the order of the protocol. Each step
writes `<step>.json` into `<out>` with its wall time; `summary` combines them
into `result.json`. Inputs are read in place and never written.
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
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "python"))

from check_ms_reader import compare_arrays, compare_strings
from oracle_ms_write import apply
from rang import core, core_ms, core_ms_write

IMAGE = "rang-ms-reader:local"
LOCK_REQUESTS = 260
WRITABLE = ("StandardStMan", "TiledShapeStMan", "TiledColumnStMan")


def outputs_root():
    return Path(os.environ.get("RANG_OUTPUTS", ROOT / "outputs")).resolve()


def host_path(path):
    """A container path under /outputs as a host path."""
    path = str(path)
    if path.startswith("/outputs/"):
        return outputs_root() / path[len("/outputs/") :]
    return Path(path)


def tree(path):
    return {
        p.relative_to(path).as_posix(): p
        for p in sorted(Path(path).rglob("*"))
        if p.is_file()
    }


def hashes(path):
    return {
        k: hashlib.sha256(p.read_bytes()).hexdigest()
        for k, p in tree(path).items()
        if p.name != "table.lock"
    }


def padding_only(ours, theirs, elem_bits):
    """True when two array files (`table.fNi`) differ only in the alignment
    gaps between arrays: walks the arrays from byte 16 (version 0 files),
    each at the next multiple of 8, and masks the gap bytes."""
    a, b = bytearray(ours), bytearray(theirs)
    if len(a) != len(b) or a[:16] != b[:16]:
        return False
    pos = 16
    while pos < len(a):
        start = (pos + 7) // 8 * 8
        a[pos:start] = b[pos:start] = bytes(start - pos)
        if start + 4 > len(a):
            break
        ndim = int.from_bytes(a[start : start + 4], "little")
        if not 0 < ndim < 16:
            return False
        dims = [
            int.from_bytes(a[start + 4 + 4 * i : start + 8 + 4 * i], "little")
            for i in range(ndim)
        ]
        n = int(np.prod(dims))
        pos = start + 4 + 4 * ndim + (n * elem_bits + 7) // 8
    return a == b


def compare_trees(ours, theirs, elem_bits=None):
    """Byte comparison of two table trees; table.lock from its sync record on."""
    a, b = tree(ours), tree(theirs)
    out = {
        "missing": sorted(set(b) - set(a)),
        "extra": sorted(set(a) - set(b)),
        "differ": [],
    }
    for name in sorted(set(a) & set(b)):
        x, y = a[name].read_bytes(), b[name].read_bytes()
        if name.endswith("table.lock"):
            x, y = x[LOCK_REQUESTS:], y[LOCK_REQUESTS:]
        if x != y:
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
            if name.endswith("i") and elem_bits:
                entry["alignment_padding_only"] = padding_only(x, y, elem_bits)
            out["differ"].append(entry)
    out["identical"] = not (out["missing"] or out["extra"] or out["differ"])
    out["identical_but_padding"] = not (out["missing"] or out["extra"]) and all(
        d.get("alignment_padding_only") for d in out["differ"]
    )
    return out


def docker(args, mounts, background=False):
    """Run the oracle image; mounts are (host, guest, mode)."""
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
    ]
    for host, guest, mode in mounts:
        cmd += ["-v", f"{host}:{guest}:{mode}"]
    cmd += [IMAGE, *args]
    if background:
        return subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
    start = time.perf_counter()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"container failed: {proc.stdout}\n{proc.stderr}")
    return proc, time.perf_counter() - start


def base_mounts(out):
    return [
        (str(outputs_root()), "/outputs", "ro"),
        (str(HERE), "/ex", "ro"),
        (str(Path(out).resolve()), "/out", "rw"),
    ]


def guest(out, path):
    """The container path of a path under `out`."""
    return "/out/" + Path(path).resolve().relative_to(Path(out).resolve()).as_posix()


def load_values(oracle, name):
    with np.load(Path(oracle) / "values" / f"{name}.npz", allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


class Make:
    makearrcoldesc = staticmethod(core_ms_write.makearrcoldesc)
    maketabdesc = staticmethod(core_ms_write.maketabdesc)


ELEM_BITS = {
    "bool": 1,
    "complex64": 64,
    "complex128": 128,
    "float32": 32,
    "float64": 64,
}


def written_elem_bits(oracle, case):
    """Element size of the arrays a case appends to an array file."""
    values = load_values(oracle, case["name"])
    kinds = {v.dtype.name for v in values.values() if v.ndim > 1}
    return ELEM_BITS.get(kinds.pop()) if len(kinds) == 1 else None


def write_json(out, step, result, started):
    result["step"] = step
    result["wall_s"] = time.perf_counter() - started
    (Path(out) / f"{step}.json").write_text(json.dumps(result, indent=1, default=str))
    print(
        json.dumps(
            {
                "step": step,
                "pass": result.get("pass"),
                "wall_s": round(result["wall_s"], 2),
            }
        )
    )
    return result


# --- criterion 1 ----------------------------------------------------------


def step_cases(oracle, out):
    started = time.perf_counter()
    oracle, out = Path(oracle), Path(out)
    cases = json.loads((oracle / "cases.json").read_text())
    report = []
    for case in cases:
        name = case["name"]
        dst = out / "core" / name
        shutil.copytree(host_path(case["input"]), dst)
        path = dst / case["table"] if case["table"] else dst
        values = load_values(oracle, name)
        ops = [tuple(op) for op in case["ops"]]
        start = time.perf_counter()
        error = None
        try:
            with core_ms_write.open_table(path, readonly=False) as t:
                apply(t, ops, values, Make)
        except Exception as e:  # noqa: BLE001 - recorded, the run goes on
            error = f"{type(e).__name__}: {e}"
        wall = time.perf_counter() - start
        diff = compare_trees(
            dst, oracle / "casacore" / name, written_elem_bits(oracle, case)
        )
        entry = {
            "name": name,
            "error": error,
            "identical": diff["identical"] and error is None,
            "identical_but_padding": diff["identical_but_padding"] and error is None,
            "diff": diff,
            "core_wall_s": wall,
            "casacore_wall_s": case["wall_s"],
            "casacore_error": case["error"],
        }
        report.append(entry)
        flag = (
            "identical"
            if entry["identical"]
            else ("padding only" if entry["identical_but_padding"] else "DIFFERS")
        )
        print(
            f"{name}: {flag}; core {wall * 1e3:.1f} ms, casacore {case['wall_s'] * 1e3:.1f} ms {error or ''}"
        )
    result = {
        "criterion": 1,
        "pass": all(r["identical"] for r in report),
        "pass_masking_alignment_padding": all(
            r["identical_but_padding"] or r["identical"] for r in report
        ),
        "cases": report,
    }
    return write_json(out, "cases", result, started)


# --- criterion 2 ----------------------------------------------------------


def label(path):
    return str(path).strip("/").replace("/", "__")


def load_dump(dump, path):
    """A readback dump, with the table's own path in keyword values (table
    references) and error messages replaced by `<table>`."""
    lab = label(path)
    with np.load(Path(dump) / f"{lab}.npz", allow_pickle=False) as z:
        arrays = {k: z[k] for k in z.files}
    text = (
        (Path(dump) / f"{lab}.json")
        .read_text()
        .replace(str(path).rstrip("/"), "<table>")
    )
    return arrays, json.loads(text)


def read_casacure(path, columns):
    import casacure.tables as ct

    arrays, strings, errors = {}, {}, {}
    t = ct.table(str(path), ack=False)
    try:
        for name in columns:
            try:
                value = t.getcol(name)
            except Exception as e:  # noqa: BLE001 - recorded, the run goes on
                errors[name] = f"{type(e).__name__}: {e}"
                continue
            if isinstance(value, np.ndarray) and value.dtype.kind not in "OU":
                arrays[name] = value
            else:
                strings[name] = [
                    str(x) for x in np.asarray(value, dtype=object).reshape(-1)
                ]
    finally:
        t.close()
    return arrays, strings, errors


def read_core(path, columns):
    arrays, strings, errors = {}, {}, {}
    with core_ms.open_table(path) as t:
        for name in columns:
            if name not in t.columns:
                errors[name] = "missing"
                continue
            try:
                value = t.getcol(name)
            except Exception as e:  # noqa: BLE001 - recorded, the run goes on
                errors[name] = f"{type(e).__name__}: {e}"
                continue
            if value.dtype == object:
                strings[name] = [str(x) for x in value.reshape(-1)]
            else:
                arrays[name] = value
    return arrays, strings, errors


def casacure_disagreements(path, reference, columns):
    """Columns where casacure, reading the reference table itself, does not
    agree with python-casacore (casacure is no oracle there; e.g. every
    column of a 0-row table comes back as int32)."""
    cc = read_casacure(path, columns)
    bad = set(cc[2])
    for failure in compare_reads(reference, cc, columns):
        bad.add(failure.split(":", 1)[0])
    return bad


def compare_reads(expected, actual, columns):
    """Every expected column against a reader's; `expected` = (arrays, meta)."""
    e_arrays, e_meta = expected
    a_arrays, a_strings, _ = actual
    failures = []
    for c in columns:
        if c in e_arrays:
            if c not in a_arrays:
                failures.append(f"{c}: not read")
                continue
            error = compare_arrays(c, e_arrays[c], a_arrays[c])
            if error:
                failures.append(error)
        elif c in e_meta.get("strings", {}):
            if c not in a_strings:
                failures.append(f"{c}: not read")
                continue
            error = compare_strings(c, e_meta["strings"][c], a_strings[c])
            if error:
                failures.append(error)
    return failures


def step_readback(oracle, out):
    started = time.perf_counter()
    oracle, out = Path(oracle), Path(out)
    cases = json.loads((oracle / "cases.json").read_text())
    pairs = []
    for case in cases:
        sub = case["table"]
        ours = out / "core" / case["name"] / sub if sub else out / "core" / case["name"]
        theirs = (
            oracle / "casacore" / case["name"] / sub
            if sub
            else oracle / "casacore" / case["name"]
        )
        pairs.append((case, ours, theirs))
    dump = out / "readback-casacore"
    mounts = base_mounts(out) + [(str(oracle.resolve()), "/oracle", "ro")]
    tables = []
    for _, ours, theirs in pairs:
        tables += [guest(out, ours), "/oracle/" + theirs.relative_to(oracle).as_posix()]
    _, wall = docker(
        ["/ex/oracle_ms_write.py", "readback", guest(out, dump), *tables], mounts
    )
    report = []
    for case, ours, theirs in pairs:
        ref_path = "/oracle/" + theirs.relative_to(oracle).as_posix()
        reference = load_dump(dump, ref_path)
        mine = load_dump(dump, guest(out, ours))
        columns = sorted(set(reference[1]["columns"]))
        values = load_values(oracle, case["name"])
        # Written columns against the values the oracle wrote (whole columns).
        written = []
        for i, op in enumerate(case["ops"]):
            if op[0] in ("putcol", "putstrings") and op[1] in mine[0] | mine[1].get(
                "strings", {}
            ):
                expected = values[f"v{i}"]
                got = mine[0].get(op[1])
                if got is None:
                    got = np.asarray(mine[1]["strings"][op[1]])
                    error = compare_strings(
                        op[1], [str(x) for x in expected], list(got)
                    )
                else:
                    error = compare_arrays(op[1], expected, got)
                written.append({"column": op[1], "error": error})
        entry = {
            "name": case["name"],
            "written_vs_values": written,
            "casacore_on_ours_vs_casacore_on_theirs": compare_reads(
                reference, (mine[0], mine[1].get("strings", {}), {}), columns
            ),
            "keywords_equal": mine[1]["keywords"] == reference[1]["keywords"]
            and mine[1]["columns"] == reference[1]["columns"],
            "casacore_errors_ours": mine[1]["errors"],
            "casacore_errors_theirs": reference[1]["errors"],
        }
        excluded = casacure_disagreements(theirs, reference, columns)
        cc = read_casacure(ours, columns)
        entry["casacure_vs_casacore"] = compare_reads(
            reference, cc, [c for c in columns if c not in excluded]
        )
        entry["casacure_excluded"] = sorted(excluded)
        entry["casacure_unread"] = cc[2]
        co = read_core(ours, columns)
        entry["core_vs_casacore"] = compare_reads(
            reference, co, [c for c in columns if c not in co[2]]
        )
        entry["core_unread"] = co[2]
        entry["pass"] = (
            not entry["casacore_on_ours_vs_casacore_on_theirs"]
            and all(w["error"] is None for w in written)
            and entry["keywords_equal"]
            and not entry["casacure_vs_casacore"]
            and not entry["core_vs_casacore"]
            and entry["casacore_errors_ours"] == entry["casacore_errors_theirs"]
        )
        report.append(entry)
        print(case["name"], "pass" if entry["pass"] else "FAIL")
        if not entry["pass"]:
            print(
                "   ",
                json.dumps(
                    {k: v for k, v in entry.items() if k != "name"}, default=str
                )[:800],
            )
    result = {
        "criterion": 2,
        "pass": all(r["pass"] for r in report),
        "container_wall_s": wall,
        "cases": report,
    }
    return write_json(out, "readback", result, started)


# --- criterion 3 ----------------------------------------------------------


def writable_columns(path):
    """Columns the core reads and writes: StandardStMan and tiled managers,
    no string arrays."""
    with core_ms.open_table(path) as t:
        out = []
        for name, c in t.columns.items():
            if c["manager_type"] not in WRITABLE or not c["supported"]:
                continue
            if c["is_array"] and c["dtype"] == "str":
                continue
            out.append(name)
        return out


def core_roundtrip(path):
    """Read every writable column with core_ms and write it back unchanged."""
    written, skipped = [], {}
    columns = writable_columns(path)
    values = {}
    with core_ms.open_table(path) as reader:
        for c in columns:
            try:
                values[c] = reader.getcol(c)
            except Exception as e:  # noqa: BLE001 - recorded, the run goes on
                skipped[c] = f"{type(e).__name__}: {e}"
    with core_ms_write.open_table(path, readonly=False) as t:
        for c in columns:
            if c in values:
                t.putcol(c, values[c])
                written.append(c)
    return written, skipped


def step_roundtrip(out, *mss):
    started = time.perf_counter()
    out = Path(out)
    rt = out / "roundtrip"
    rt.mkdir(parents=True)
    container = [
        "/outputs/" + Path(m).resolve().relative_to(outputs_root()).as_posix()
        for m in mss
    ]
    _, casacore_wall = docker(
        ["/ex/oracle_ms_write.py", "roundtrip", guest(out, rt), *container],
        base_mounts(out),
    )
    casacore_report = json.loads((rt / "roundtrip.json").read_text())
    report, tables = [], []
    for ms in mss:
        name = Path(ms).resolve().parent.name
        dst = rt / "core" / name
        shutil.copytree(ms, dst)
        for path in [dst] + sorted(p.parent for p in dst.glob("*/table.dat")):
            start = time.perf_counter()
            written, skipped = core_roundtrip(path)
            rel = path.relative_to(rt).as_posix()
            theirs = casacore_report.get(rel.replace("core/", "casacore/", 1), {})
            report.append(
                {
                    "table": rel,
                    "core_columns": written,
                    "core_skipped": skipped,
                    "casacore_columns": theirs.get("columns"),
                    "same_columns": sorted(written)
                    == sorted(theirs.get("columns", [])),
                    "core_wall_s": time.perf_counter() - start,
                    "casacore_wall_s": theirs.get("wall_s"),
                }
            )
            tables.append(path)
        diff = compare_trees(dst, rt / "casacore" / name)
        report.append({"ms": name, "files_vs_casacore": diff})
        print(
            name,
            "files identical" if diff["identical"] else "files DIFFER",
            json.dumps(diff)[:400],
        )
    # Read-back identity with the inputs in all three readers.
    originals = {}
    for ms in mss:
        name = Path(ms).resolve().parent.name
        src = Path(ms).resolve()
        originals[name] = [src] + sorted(p.parent for p in src.glob("*/table.dat"))
    dump = out / "roundtrip-readback"
    guest_tables = []
    for paths in originals.values():
        guest_tables += [
            "/outputs/" + p.relative_to(outputs_root()).as_posix() for p in paths
        ]
    guest_tables += [guest(out, path) for path in tables]
    _, wall = docker(
        ["/ex/oracle_ms_write.py", "readback", guest(out, dump), *guest_tables],
        base_mounts(out),
    )
    readback = []
    for name, paths in originals.items():
        for k, p in enumerate(paths):
            mine = rt / "core" / name if k == 0 else rt / "core" / name / p.name
            reference = load_dump(
                dump, "/outputs/" + p.relative_to(outputs_root()).as_posix()
            )
            casa = load_dump(dump, guest(out, mine))
            columns = sorted(reference[1]["columns"])
            entry = {
                "table": mine.relative_to(rt).as_posix(),
                "casacore": compare_reads(
                    reference, (casa[0], casa[1].get("strings", {}), {}), columns
                ),
                "keywords_equal": casa[1]["keywords"] == reference[1]["keywords"],
            }
            excluded = casacure_disagreements(p, reference, columns)
            cc = read_casacure(mine, columns)
            entry["casacure"] = compare_reads(
                reference, cc, [c for c in columns if c not in excluded]
            )
            entry["casacure_excluded"] = sorted(excluded)
            co = read_core(mine, columns)
            entry["core"] = compare_reads(
                reference, co, [c for c in columns if c not in co[2]]
            )
            entry["pass"] = (
                not (entry["casacore"] or entry["casacure"] or entry["core"])
                and entry["keywords_equal"]
            )
            readback.append(entry)
    files_ok = all(r["files_vs_casacore"]["identical"] for r in report if "ms" in r)
    columns_ok = all(r["same_columns"] for r in report if "table" in r)
    result = {
        "criterion": 3,
        "pass": files_ok and columns_ok and all(r["pass"] for r in readback),
        "files_identical": files_ok,
        "same_columns_written": columns_ok,
        "readback_identical": all(r["pass"] for r in readback),
        "casacore_roundtrip_wall_s": casacore_wall,
        "readback_container_wall_s": wall,
        "tables": report,
        "readback": readback,
    }
    return write_json(out, "roundtrip", result, started)


# --- criterion 4 ----------------------------------------------------------


def step_reader(out, task_e_oracle):
    started = time.perf_counter()
    out = Path(out)
    check = out / "reader-check"
    proc = subprocess.run(  # noqa: PLW1510 - exit codes are read
        [sys.executable, str(HERE / "check_ms_reader.py"), task_e_oracle, str(check)],
        capture_output=True,
        text=True,
        env=dict(os.environ),
    )
    reader = (
        json.loads((check / "result.json").read_text())
        if (check / "result.json").exists()
        else {}
    )
    unchanged = subprocess.run(  # noqa: PLW1510 - exit codes are read
        [
            "git",
            "-C",
            str(ROOT),
            "diff",
            "--quiet",
            "f36ff80",
            "--",
            "python/rang/core_ms.py",
            "examples/check_ms_reader.py",
            "examples/oracle_ms_columns.py",
        ]
    ).returncode
    diff = subprocess.run(  # noqa: PLW1510 - exit codes are read
        ["git", "-C", str(ROOT), "diff", "-U0", "f36ff80", "--", "core/src/ms.rs"],
        capture_output=True,
        text=True,
    ).stdout
    removed = [
        line[1:]
        for line in diff.splitlines()
        if line.startswith("-") and not line.startswith("---")
    ]
    added = [
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]

    def norm(lines):
        return sorted(
            line.replace("pub ", "").strip()
            for line in lines
            if not line.strip().startswith("///") and line.strip()
        )

    only_visibility = norm(removed) == norm(added)
    tests_untouched = "mod tests" not in diff and "#[test]" not in diff
    # Gated as frozen: the comparator passes, the reader files and the
    # reader tests are unchanged; the size of the ms.rs change is reported.
    ok = proc.returncode == 0 and unchanged == 0 and tests_untouched
    result = {
        "criterion": 4,
        "pass": ok,
        "check_ms_reader_exit": proc.returncode,
        "check_ms_reader_result": reader,
        "reader_files_unchanged": unchanged == 0,
        "ms_rs_changes_only_visibility_and_docs_reported": only_visibility,
        "reader_tests_untouched": tests_untouched,
        "ms_rs_lines_changed": len(added),
    }
    return write_json(out, "reader", result, started)


# --- criterion 5 ----------------------------------------------------------

ADDED = {
    # case: (column, first row, rows); F-add-shape's row 3 has another shape,
    # so casacore reads and rewrites the uniform rows after it.
    "F-add-default": ("RANG_MODEL_DATA", 0, -1),
    "F-add-group": ("CORRECTED_DATA", 0, -1),
    "F-add-shape": ("RANG_MODEL_DATA", 4, -1),
    "F-add-tcs": ("RANG_TCS", 0, -1),
    "F-add-tss": ("RANG_TSS", 0, -1),
    "F-add-ssm-new": ("RANG_SSM", 0, -1),
}


def step_addcols(out):
    started = time.perf_counter()
    out = Path(out)
    report = []
    for k, (name, (column, first, nrow)) in enumerate(ADDED.items()):
        src = out / "core" / name
        dst = out / "addcols" / name
        shutil.copytree(src, dst)
        dump = out / "addcols" / f"{name}-dump"
        count = None if nrow < 0 else nrow
        try:
            _, wall = docker(
                [
                    "/ex/oracle_ms_write.py",
                    "rewrite",
                    guest(out, dst),
                    column,
                    str(1000 + k),
                    guest(out, dump),
                    str(first),
                    str(nrow),
                ],
                base_mounts(out),
            )
            with np.load(dump / f"rewrite-{column}.npz") as z:
                before, new, after = z["before"], z["new"], z["after"]
            with core_ms.open_table(src) as t:
                core_before = t.getcol(column, first, count)
            with core_ms.open_table(dst) as t:
                core_after = t.getcol(column, first, count)
            entry = {
                "name": name,
                "column": column,
                "rows": [first, nrow],
                "casacore_read_equals_core_read": compare_arrays(
                    column, core_before, before
                ),
                "casacore_rewrite_read_back": compare_arrays(column, new, after),
                "core_reads_casacore_rewrite": compare_arrays(column, new, core_after),
                "container_wall_s": wall,
            }
        except Exception as e:  # noqa: BLE001 - recorded, the run goes on
            entry = {
                "name": name,
                "column": column,
                "error": f"{type(e).__name__}: {e}",
            }
        entry["pass"] = "error" not in entry and all(
            entry[k] is None
            for k in (
                "casacore_read_equals_core_read",
                "casacore_rewrite_read_back",
                "core_reads_casacore_rewrite",
            )
        )
        report.append(entry)
        print(name, "pass" if entry["pass"] else f"FAIL {entry}")
    result = {"criterion": 5, "pass": all(r["pass"] for r in report), "cases": report}
    return write_json(out, "addcols", result, started)


# --- criterion 6 ----------------------------------------------------------


def wait_for_line(proc, text, timeout):
    deadline = time.time() + timeout
    lines = []
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        lines.append(line)
        if text in line:
            return True, lines
    return False, lines


def step_locks(out, ms):
    started = time.perf_counter()
    out = Path(out)
    locks = out / "locks"
    locks.mkdir(parents=True)
    # (i) casacore holds the write lock; the core must fail and change nothing.
    held = locks / "held.ms"
    shutil.copytree(ms, held)
    before = hashes(held)
    proc = docker(
        ["/ex/oracle_ms_write.py", "hold-lock", guest(out, held), "12"],
        base_mounts(out),
        background=True,
    )
    locked, lines = wait_for_line(proc, "locked", 60)
    t0 = time.perf_counter()
    refused = None
    try:
        core_ms_write.open_table(
            held, readonly=False, lock_attempts=3, lock_wait=1.0
        ).close()
    except OSError as e:
        refused = str(e)
    refused_after_s = time.perf_counter() - t0
    unchanged = hashes(held) == before
    proc.wait(timeout=120)
    rest = proc.stdout.read()
    flags_row = core_ms.open_table(held).getcol("FLAG_ROW")
    with core_ms_write.open_table(
        held, readonly=False, lock_attempts=3, lock_wait=1.0
    ) as t:
        t.putcol("FLAG_ROW", ~flags_row)
    after_release = np.array_equal(
        core_ms.open_table(held).getcol("FLAG_ROW"), ~flags_row
    )
    part_i = {
        "casacore_locked": locked,
        "core_refused": refused,
        "refused_after_s": refused_after_s,
        "files_unchanged_while_locked": unchanged,
        "core_write_after_release": bool(after_release),
        "container_output": "".join(lines) + rest,
    }
    part_i["pass"] = bool(
        locked and refused and "locked" in refused and unchanged and after_release
    )
    # (ii) a casacore reader open across the core's write sees the new values.
    watched = locks / "watched.ms"
    shutil.copytree(ms, watched)
    ready, go, dump = locks / "ready", locks / "go", locks / "watch-dump"
    proc = docker(
        [
            "/ex/oracle_ms_write.py",
            "watch",
            guest(out, watched),
            "FLAG_ROW",
            guest(out, ready),
            guest(out, go),
            guest(out, dump),
        ],
        base_mounts(out),
        background=True,
    )
    deadline = time.time() + 60
    while not ready.exists() and time.time() < deadline:
        time.sleep(0.1)
    original = core_ms.open_table(watched).getcol("FLAG_ROW")
    new = ~original
    with core_ms_write.open_table(
        watched, readonly=False, lock_attempts=10, lock_wait=1.0
    ) as t:
        t.putcol("FLAG_ROW", new)
    go.write_text("go")
    proc.wait(timeout=180)
    output = proc.stdout.read()
    with np.load(dump / "watch-FLAG_ROW.npz") as z:
        first, second = z["first"], z["second"]
    part_ii = {
        "reader_first_read_is_original": compare_arrays("FLAG_ROW", original, first),
        "reader_second_read_is_new": compare_arrays("FLAG_ROW", new, second),
        "container_output": output,
    }
    part_ii["pass"] = (
        part_ii["reader_first_read_is_original"] is None
        and part_ii["reader_second_read_is_new"] is None
    )
    # (iii), reported: while the core holds the lock (another host process,
    # for HOLD seconds), byte 0 of table.lock is taken and casacore, opening
    # the table, waits until the core releases; after that it gets the lock
    # at once.
    hold = 8
    core_held = locks / "core-held.ms"
    shutil.copytree(ms, core_held)
    holder = (
        "import sys, time\n"
        f"sys.path.insert(0, {str(ROOT / 'python')!r})\n"
        "from rang import core_ms_write\n"
        f"t = core_ms_write.open_table({str(core_held)!r}, readonly=False)\n"
        "print('held', flush=True)\n"
        f"time.sleep({hold})\n"
        "t.close()\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", holder], stdout=subprocess.PIPE, text=True
    )
    held_line = proc.stdout.readline().strip()
    during, _ = docker(
        ["/ex/oracle_ms_write.py", "try-lock", guest(out, core_held)], base_mounts(out)
    )
    proc.wait(timeout=60)
    after, _ = docker(
        ["/ex/oracle_ms_write.py", "try-lock", guest(out, core_held)], base_mounts(out)
    )
    during = json.loads(during.stdout.strip().splitlines()[-1])
    after = json.loads(after.stdout.strip().splitlines()[-1])
    part_iii = {
        "core_held": held_line == "held",
        "core_hold_s": hold,
        "casacore_while_core_holds": during,
        "casacore_after_core_closed": after,
        "note": "casacore's open waits for a read lock, so it waits for the core",
    }
    part_iii["as_expected"] = (
        part_iii["core_held"]
        and not during["lock_free_at_start"]
        and during["acquired"]
        and during["waited_s"] >= 3
        and after["lock_free_at_start"]
        and after["acquired"]
        and after["waited_s"] < 3
    )
    result = {
        "criterion": 6,
        "pass": part_i["pass"] and part_ii["pass"],
        "held_lock": part_i,
        "open_reader": part_ii,
        "core_holds_casacore_waits_reported": part_iii,
    }
    return write_json(out, "locks", result, started)


# --- criterion 7 ----------------------------------------------------------


def step_serialisation(out, *mss):
    started = time.perf_counter()
    report = []
    for ms in mss:
        tables, ssm, tiled, failures = core.extension().ms_serialisation_check(str(ms))
        report.append(
            {
                "ms": str(ms),
                "tables": tables,
                "ssm_files": ssm,
                "tiled_headers": tiled,
                "failures": failures,
            }
        )
        print(ms, tables, ssm, tiled, failures or "identical")
    result = {
        "criterion": 7,
        "pass": all(not r["failures"] for r in report),
        "tables": report,
    }
    return write_json(out, "serialisation", result, started)


# --- criterion 8 ----------------------------------------------------------


def vm_status(key="VmHWM"):
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(key + ":"):
            return int(line.split()[1]) * 1024
    return 0


def vm_hwm():
    return vm_status("VmHWM")


def reset_hwm():
    """Reset the peak RSS to the current RSS (`clear_refs` 5); returns
    whether VmHWM then equals VmRSS within 1 MiB."""
    try:
        Path("/proc/self/clear_refs").write_text("5")
    except OSError:
        return False
    return vm_status("VmHWM") - vm_status("VmRSS") < 1024**2


def step_scale(oracle, out):
    started = time.perf_counter()
    oracle, out = Path(oracle), Path(out)
    flags = np.load(oracle / "scale-flags.npy")
    casacore_walls = json.loads((oracle / "scale-casacore.json").read_text())
    report = []
    for name in sorted(casacore_walls):
        src = oracle / "inputs" / name
        dst = out / "scale" / name
        shutil.copytree(src, dst)
        # Without the reset the peak of an earlier step (the comparison of
        # the previous table) would hide this write's allocations.
        hwm_reset = reset_hwm()
        hwm_before = vm_hwm()
        start = time.perf_counter()
        with core_ms_write.open_table(dst, readonly=False) as t:
            t.putcol("FLAG", flags)
        wall = time.perf_counter() - start
        growth = vm_hwm() - hwm_before
        diff = compare_trees(dst, oracle / "casacore" / name)
        entry = {
            "table": name,
            "cells": int(flags.size),
            "core_wall_s": wall,
            "casacore_wall_s": casacore_walls[name],
            "hwm_reset": hwm_reset,
            "hwm_before_bytes": hwm_before,
            "hwm_growth_bytes": growth,
            "identical": diff["identical"],
            "diff": diff,
        }
        entry["pass"] = diff["identical"] and hwm_reset and growth <= 64 * 1024**2
        report.append(entry)
        print(
            name,
            f"{wall:.2f} s (casacore {casacore_walls[name]:.2f} s)",
            f"HWM +{growth / 1e6:.1f} MB",
            diff["identical"],
        )
    result = {"criterion": 8, "pass": all(r["pass"] for r in report), "tables": report}
    return write_json(out, "scale", result, started)


# --- summary ----------------------------------------------------------------


def step_summary(out):
    out = Path(out)
    steps = [
        "cases",
        "readback",
        "roundtrip",
        "reader",
        "addcols",
        "locks",
        "serialisation",
        "scale",
    ]
    result = {"criteria": {}, "wall_s": {}}
    for step in steps:
        path = out / f"{step}.json"
        if not path.exists():
            result["criteria"][step] = None
            continue
        data = json.loads(path.read_text())
        result["criteria"][f"{data.get('criterion')} {step}"] = data["pass"]
        result["wall_s"][step] = data.get("wall_s")
        if step == "cases":
            result["criterion_1_masking_alignment_padding"] = data[
                "pass_masking_alignment_padding"
            ]
    result["pass"] = all(v for v in result["criteria"].values())
    (out / "result.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    return result


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    step, args = argv[1], argv[2:]
    steps = {
        "cases": step_cases,
        "readback": step_readback,
        "roundtrip": step_roundtrip,
        "reader": step_reader,
        "addcols": step_addcols,
        "locks": step_locks,
        "serialisation": step_serialisation,
        "scale": step_scale,
        "summary": step_summary,
    }
    if step not in steps:
        raise SystemExit(__doc__)
    out = args[1] if step in ("cases", "readback", "scale") else args[0]
    Path(out).mkdir(parents=True, exist_ok=True)
    steps[step](*args)


if __name__ == "__main__":
    main(sys.argv)
