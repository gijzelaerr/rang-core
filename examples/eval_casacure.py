"""casacure evaluation, host side (research/casacure-evaluation.md, task E2).

Usage (each writes `result.json` or the named file into a fresh directory):

    python examples/eval_casacure.py reads <oracle-dir> <out-dir> [--ms-root DIR] [--no-core]
    python examples/eval_casacure.py bigendian <oracle-dir> <big-dir> <out-dir>
    python examples/eval_casacure.py describe <out.json> <ms> [<ms> ...]
    python examples/eval_casacure.py compare-describe <casacure.json> <casacore.json> <out.json>
    python examples/eval_casacure.py write <oracle-dir> <out-dir>
    python examples/eval_casacure.py inplace <out-dir> <ms> [<ms> ...]
    python examples/eval_casacure.py caltable <out-dir>
    python examples/eval_casacure.py verify-writes <oracle-dir> <out-dir>
    python examples/eval_casacure.py taql <casacore-taql.json> <ms> <out.json>
    python examples/eval_casacure.py measures-cases <oracle-dir> <cases.json>
    python examples/eval_casacure.py measures <cases.json> <casacore.json|-> <out.json>
    python examples/eval_casacure.py uvw <ms> <out.json>
    python examples/eval_casacure.py perf <backend> <what> <ms> <out.json>

`reads` needs only NumPy and casacure (plus `rangtoy.core_ms` unless
`--no-core`), so it runs on a native Windows venv too; the comparator
functions are loaded by path from `examples/check_ms_reader.py`, so
"column-exact" means what it meant in task E. Writes go only into the fresh
output directory; the source MSs are hashed before and after.
"""

import importlib.util
import json
import shutil
import sys
import time
from hashlib import sha256
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RANGES = ((0, 1), (3, 5))
SUBTABLES = ("ANTENNA", "FIELD", "SPECTRAL_WINDOW", "POLARIZATION")


def _checker():
    spec = importlib.util.spec_from_file_location(
        "check_ms_reader", HERE / "check_ms_reader.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECK = _checker()


def _peak_rss_mb():
    try:
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except ImportError:  # Windows
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        kernel32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(Counters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
        )
        return counters.PeakWorkingSetSize / 2**20


def file_hashes(root, include_lock=False):
    return {
        p.relative_to(root).as_posix(): sha256(p.read_bytes()).hexdigest()
        for p in sorted(Path(root).rglob("*"))
        if p.is_file() and (include_lock or p.name != "table.lock")
    }


def lock_hashes(root):
    return {
        k: v
        for k, v in file_hashes(root, include_lock=True).items()
        if "table.lock" in k
    }


def oracle_path(entry_path, ms_root):
    """Map the oracle's container path (/outputs/...) to this host."""
    path = Path(entry_path)
    return Path(ms_root) / Path(*path.parts[2:])


def read_casacure(path, columns, start=0, count=None, timings=None):
    import casacure.tables as ct

    arrays, strings = {}, {}
    t = ct.table(str(path), ack=False)
    try:
        for name in columns:
            started = time.perf_counter()
            value = t.getcol(name) if count is None else t.getcol(name, start, count)
            if timings is not None:
                timings.append(
                    (str(path), name, start, count, time.perf_counter() - started)
                )
            if isinstance(value, np.ndarray) and value.dtype.kind not in "OU":
                arrays[name] = value
            else:
                strings[name] = np.asarray(value, dtype=object).tolist()
    finally:
        t.close()
    return arrays, strings


def compare_backend(reader, receipt, oracle_dir, ms_root, label_map=None):
    """Full columns and the two row ranges of every oracle column."""
    full, ranges, timings = [], [], []
    for label, entry in receipt["tables"].items():
        path = oracle_path(entry["path"], ms_root)
        if label_map:
            path = label_map(label, path)
        expected = CHECK.load_oracle(oracle_dir, label)
        columns = [c for c in entry["columns"] if "error" not in entry["columns"][c]]
        try:
            actual = reader(path, columns, 0, None, timings)
        except Exception as error:  # noqa: BLE001 - recorded as a failure
            full.append(f"{label}: {type(error).__name__}: {error}")
            continue
        full += [f"{label}: {f}" for f in CHECK.compare_table(expected, actual)]
        for start, count in RANGES:
            if start + count > entry["nrows"]:
                continue
            sliced = (
                {k: v[start : start + count] for k, v in expected[0].items()},
                {k: v[start : start + count] for k, v in expected[1].items()},
            )
            try:
                actual = reader(path, columns, start, count, timings)
            except Exception as error:  # noqa: BLE001
                ranges.append(f"{label}[{start}:{start + count}]: {error}")
                continue
            ranges += [
                f"{label}[{start}:{start + count}]: {f}"
                for f in CHECK.compare_table(sliced, actual)
            ]
    return full, ranges, timings


def read_core(path, columns, start, count, timings):
    return CHECK.read_with_core(path, columns, start, count, timings)


def cmd_reads(oracle_dir, out, ms_root=None, with_core=True):
    import casacure

    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    ms_root = Path(ms_root) if ms_root else HERE.parent / "outputs"
    receipt = json.loads((Path(oracle_dir) / "receipt.json").read_text())
    mains = {
        label: oracle_path(e["path"], ms_root)
        for label, e in receipt["tables"].items()
        if "." not in label
    }
    before = {label: file_hashes(p) for label, p in mains.items()}
    locks_before = {label: lock_hashes(p) for label, p in mains.items()}
    started = time.perf_counter()
    full, ranges, timings = compare_backend(read_casacure, receipt, oracle_dir, ms_root)
    wall = time.perf_counter() - started
    after = {label: file_hashes(p) for label, p in mains.items()}
    locks_after = {label: lock_hashes(p) for label, p in mains.items()}
    tree = []
    for label in mains:
        if before[label] != after[label]:
            tree.append(f"{label}: changed by the reads")
        if before[label] != receipt["tables"][label]["ms_file_sha256"]:
            tree.append(f"{label}: differs from the oracle receipt")
    result = {
        "casacure": casacure.__version__,
        "numpy": np.__version__,
        "platform": sys.platform,
        "python": sys.version,
        "oracle": str(oracle_dir),
        "ms_root": str(ms_root),
        "ncolumns": sum(
            len([c for c in e["columns"] if "error" not in e["columns"][c]])
            for e in receipt["tables"].values()
        ),
        "ntables": len(receipt["tables"]),
        "wall_s": wall,
        "peak_rss_mb": _peak_rss_mb(),
        "criteria": {
            "R1_full_columns_exact": {"passed": not full, "failures": full},
            "R1_row_ranges_exact": {"passed": not ranges, "failures": ranges},
            "R2_tree_unchanged": {"passed": not tree, "failures": tree},
        },
        "reported": {
            "table_lock_changed": {
                label: sorted(
                    k
                    for k in set(locks_before[label]) | set(locks_after[label])
                    if locks_before[label].get(k) != locks_after[label].get(k)
                )
                for label in mains
            }
        },
        "timings": [
            {"table": t, "column": c, "start": s, "count": n, "seconds": sec}
            for t, c, s, n, sec in timings
        ],
    }
    if with_core:
        cfull, cranges, ctimings = compare_backend(
            read_core, receipt, oracle_dir, ms_root
        )
        # R4: casacure against core_ms directly, full columns.
        direct = []
        for label, entry in receipt["tables"].items():
            path = oracle_path(entry["path"], ms_root)
            columns = [
                c for c in entry["columns"] if "error" not in entry["columns"][c]
            ]
            direct += [
                f"{label}: {f}"
                for f in CHECK.compare_table(
                    read_core(path, columns, 0, None, []),
                    read_casacure(path, columns),
                )
            ]
        result["reported"]["R4_core_ms_vs_oracle"] = cfull + cranges
        result["reported"]["R4_casacure_vs_core_ms"] = direct
        result["reported"]["core_ms_timings"] = [
            {"table": t, "column": c, "start": s, "count": n, "seconds": sec}
            for t, c, s, n, sec in ctimings
        ]
    _finish(out / "result.json", result)


def cmd_bigendian(oracle_dir, big_dir, out):
    """R6: read big-endian deep copies made by python-casacore."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    receipt = json.loads((Path(oracle_dir) / "receipt.json").read_text())
    big_dir = Path(big_dir)
    copies = {"ms0": big_dir / "ms0-big.ms", "ms1": big_dir / "ms1-big.ms"}
    sub = {
        label: e
        for label, e in receipt["tables"].items()
        if label.split(".")[0] in copies
    }
    small = dict(receipt, tables=sub)

    def remap(label, path):
        base = copies[label.split(".")[0]]
        return base / label.split(".")[1] if "." in label else base

    result = {"criteria": {}, "reported": {}}
    full, ranges, _ = compare_backend(
        read_casacure, small, oracle_dir, HERE.parent / "outputs", remap
    )
    result["criteria"]["R6_casacure_bigendian_exact"] = {
        "passed": not full and not ranges,
        "failures": full + ranges,
    }
    try:
        cfull, cranges, _ = compare_backend(
            read_core, small, oracle_dir, HERE.parent / "outputs", remap
        )
        result["reported"]["R6_core_ms_bigendian"] = {
            "passed": not cfull and not cranges,
            "failures": (cfull + cranges)[:50],
            "nfailures": len(cfull + cranges),
        }
    except Exception as error:  # noqa: BLE001
        result["reported"]["R6_core_ms_bigendian"] = {"error": str(error)}
    _finish(out / "result.json", result)


def describe_table(path):
    import casacure.tables as ct

    t = ct.table(str(path), ack=False)
    try:
        cols = {
            name: {
                "desc": _plain(t.getcoldesc(name)),
                "keywords": _plain(t.getcolkeywords(name)),
            }
            for name in t.colnames()
        }
        return {
            "nrows": t.nrows(),
            "keywords": _plain(t.getkeywords()),
            "dminfo": _plain(t.getdminfo()),
            "columns": cols,
        }
    finally:
        t.close()


def _plain(value):
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def cmd_describe(out, mss):
    result = {}
    for ms in mss:
        result[ms] = {"main": describe_table(ms)}
        for sub in SUBTABLES:
            result[ms][sub] = describe_table(Path(ms) / sub)
    Path(out).write_text(json.dumps(result, indent=1, default=str) + "\n")


def _diff(a, b, path=""):
    """Paths at which two JSON-like values differ."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(f"{path}/{k}: only casacore")
            elif k not in b:
                out.append(f"{path}/{k}: only casacure")
            else:
                out += _diff(a[k], b[k], f"{path}/{k}")
        return out
    if a != b:
        return [f"{path}: casacure {a!r} != casacore {b!r}"[:300]]
    return []


def cmd_compare_describe(ours, theirs, out):
    """R5 (reported): descriptions, dminfo and keywords.

    Table paths in `Table:` keywords and the casacore-only `info` record are
    normalised; the dminfo comparison ignores cache-size SPEC fields.
    """
    a = json.loads(Path(ours).read_text())
    b = json.loads(Path(theirs).read_text())
    result = {}

    def norm(record):
        record = json.loads(json.dumps(record))
        for key, value in list(record.get("keywords", {}).items()):
            if isinstance(value, str) and value.startswith("Table:"):
                record["keywords"][key] = "Table: " + value.rsplit("/", 1)[-1]
        record.pop("info", None)
        return record

    for ms in b:
        host = next(k for k in a if k.endswith(ms.lstrip("/").split("/", 1)[1]))
        for name in b[ms]:
            x, y = norm(a[host][name]), norm(b[ms][name])
            result[f"{ms}:{name}"] = {
                "columns": _diff(x["columns"], y["columns"]),
                "keywords": _diff(x["keywords"], y["keywords"]),
                "dminfo": _diff(x["dminfo"], y["dminfo"]),
            }
    Path(out).write_text(json.dumps(result, indent=1) + "\n")
    for key, value in result.items():
        print(key, {k: len(v) for k, v in value.items()})


# Writes ---------------------------------------------------------------------

WRITE_COLUMNS = (
    "TIME",
    "ANTENNA1",
    "ANTENNA2",
    "UVW",
    "DATA",
    "FLAG",
    "FLAG_ROW",
    "WEIGHT",
    "WEIGHT_SPECTRUM",
    "SIGMA",
    "DATA_DESC_ID",
    "FIELD_ID",
    "SCAN_NUMBER",
    "INTERVAL",
    "EXPOSURE",
    "TIME_CENTROID",
)
TILED = {"DATA": [4, 4096, 8], "FLAG": [4, 4096, 64], "WEIGHT_SPECTRUM": [4, 4096, 16]}


def flag_pattern(shape):
    """The frozen FLAG pattern (every 7th cell set); same as the oracle's."""
    return (np.arange(int(np.prod(shape))) % 7 == 0).reshape(shape)


def written_arrays(oracle_dir):
    """What the W1 writes put into the main table: the fixture's columns."""
    arrays, _ = CHECK.load_oracle(oracle_dir, "ms0")
    main = {k: arrays[k] for k in WRITE_COLUMNS}
    main["MODEL_DATA"] = (arrays["DATA"] * np.float32(0.5)).astype(np.complex64)
    return main


VALUE = {"WEIGHT_SPECTRUM": (0.0, "float"), "FLAG": (False, "boolean")}


def _write_ms(path, oracle_dir, tiled, fixed_flag=False):
    """`fixed_flag` (post hoc, variant c) also redeclares FLAG with a fixed
    cell shape, which casacore's TiledColumnStMan requires."""
    import casacure.tables as ct

    main = written_arrays(oracle_dir)
    nchan, ncorr = main["DATA"].shape[1:]
    names = ("DATA", "MODEL_DATA", "WEIGHT_SPECTRUM") + (
        ("FLAG",) if fixed_flag else ()
    )
    extra = [
        ct.makearrcoldesc(
            name,
            VALUE.get(name, (0j, "complex"))[0],
            ndim=2,
            shape=[nchan, ncorr],
            valuetype=VALUE.get(name, (0j, "complex"))[1],
            datamanagertype="TiledColumnStMan" if tiled and name in TILED else "",
            datamanagergroup=f"Tiled{name}" if tiled and name in TILED else "",
            # Variant d sets ColumnDesc::FixedShape (4) explicitly, which
            # casacore implies from a given shape and casacure does not.
            options=4 if fixed_flag == "option4" else 0,
        )
        for name in names
    ]
    desc = ct.maketabdesc(extra)
    dminfo = None
    if tiled:
        dminfo = {
            f"*{i + 1}": {
                "TYPE": "TiledColumnStMan",
                "NAME": f"Tiled{name}",
                "SPEC": {"DEFAULTTILESHAPE": shape},
                "COLUMNS": [name],
            }
            for i, (name, shape) in enumerate(TILED.items())
        }
    t = ct.default_ms(str(path), desc, dminfo)
    try:
        t.addrows(main["TIME"].shape[0])
        for name, value in main.items():
            t.putcol(name, value)
        t.flush()
        dminfo_out = _plain(t.getdminfo())
    finally:
        t.close()
    for sub in SUBTABLES:
        arrays, strings = CHECK.load_oracle(oracle_dir, f"ms0.{sub}")
        s = ct.table(str(Path(path) / sub), readonly=False, ack=False)
        try:
            n = (
                next(iter(arrays.values())).shape[0]
                if arrays
                else len(next(iter(strings.values())))
            )
            s.addrows(n)
            for name, value in arrays.items():
                if name in s.colnames():
                    s.putcol(name, value)
            for name, value in strings.items():
                if name in s.colnames():
                    s.putcol(name, np.asarray(value, dtype=object))
            s.flush()
        finally:
            s.close()
    return dminfo_out


VARIANTS = {
    "a-default": (False, False),
    "b-tiled": (True, False),
    # Added after the first run (post hoc): FLAG redeclared fixed-shape.
    "c-posthoc-tiled-fixed-flag": (True, True),
    # And with the FixedShape option set explicitly (post hoc).
    "d-posthoc-tiled-option4": (True, "option4"),
}


def cmd_write(oracle_dir, out, *variants):
    """W1: create MSs with casacure (default managers, TiledColumnStMan).

    With variant names, write only those into an existing directory and
    merge them into its `write.json`."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=bool(variants))
    record = out / "write.json"
    result = json.loads(record.read_text()) if variants and record.exists() else {}
    for variant in variants or ("a-default", "b-tiled"):
        tiled, fixed_flag = VARIANTS[variant]
        path = out / f"w1-{variant}.ms"
        started = time.perf_counter()
        try:
            dminfo = _write_ms(path, oracle_dir, tiled, fixed_flag)
            result[variant] = {
                "path": str(path),
                "wall_s": time.perf_counter() - started,
                "dminfo": dminfo,
                "files": file_hashes(path),
            }
        except Exception as error:  # noqa: BLE001 - recorded
            result[variant] = {"error": f"{type(error).__name__}: {error}"}
    result["peak_rss_mb" + ("-" + "-".join(variants) if variants else "")] = (
        _peak_rss_mb()
    )
    _finish(record, result, gate=False)
    # W3 needs a copy that python-casacore writes into.
    if not variants and (out / "w1-a-default.ms").exists():
        shutil.copytree(out / "w1-a-default.ms", out / "w3-interop.ms")


def cmd_inplace(out, mss):
    """W4: putcol FLAG and addcols CORRECTED_DATA on copies of the MSs."""
    import casacure.tables as ct

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    result = {}
    for index, ms in enumerate(mss):
        target = out / f"w4-ms{index}.ms"
        shutil.copytree(ms, target)
        before = file_hashes(target)
        entry = {"source": str(ms), "path": str(target)}
        try:
            t = ct.table(str(target), readonly=False, ack=False)
            entry["dminfo_before"] = _plain(t.getdminfo())
            shape = t.getcol("FLAG").shape
            data = t.getcol("DATA")
            started = time.perf_counter()
            t.putcol("FLAG", flag_pattern(shape))
            t.flush()
            entry["putcol_flag_s"] = time.perf_counter() - started
            desc = ct.makearrcoldesc(
                "CORRECTED_DATA",
                0j,
                ndim=2,
                shape=list(shape[1:]),
                valuetype="complex",
            )
            started = time.perf_counter()
            t.addcols(ct.maketabdesc([desc]))
            t.putcol(
                "CORRECTED_DATA", (data * np.complex64(1 + 1j)).astype(np.complex64)
            )
            t.flush()
            entry["addcols_corrected_s"] = time.perf_counter() - started
            entry["dminfo_after"] = _plain(t.getdminfo())
            t.close()
        except Exception as error:  # noqa: BLE001
            entry["error"] = f"{type(error).__name__}: {error}"
        after = file_hashes(target)
        entry["files_changed"] = sorted(k for k in before if before[k] != after.get(k))
        entry["files_added"] = sorted(set(after) - set(before))
        entry["files_removed"] = sorted(set(before) - set(after))
        result[f"ms{index}"] = entry
    _finish(out / "inplace.json", result, gate=False)


def cmd_caltable(out):
    """W5: a synthetic G Jones calibration table written with casacure."""
    import casacure.tables as ct

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    nant, ntime, nchan, ncorr = 4, 3, 1, 2
    rng = np.random.default_rng(20261030)
    nrow = nant * ntime
    cols = {
        "TIME": np.repeat(5.0e9 + np.arange(ntime) * 8.0, nant),
        "FIELD_ID": np.zeros(nrow, np.int32),
        "SPECTRAL_WINDOW_ID": np.zeros(nrow, np.int32),
        "ANTENNA1": np.tile(np.arange(nant, dtype=np.int32), ntime),
        "ANTENNA2": np.full(nrow, -1, np.int32),
        "INTERVAL": np.full(nrow, 8.0),
        "SCAN_NUMBER": np.ones(nrow, np.int32),
        "OBSERVATION_ID": np.zeros(nrow, np.int32),
        "CPARAM": (
            rng.normal(1, 0.1, (nrow, nchan, ncorr))
            + 1j * rng.normal(0, 0.1, (nrow, nchan, ncorr))
        ).astype(np.complex64),
        "PARAMERR": np.full((nrow, nchan, ncorr), 0.01, np.float32),
        "FLAG": np.zeros((nrow, nchan, ncorr), bool),
        "SNR": np.full((nrow, nchan, ncorr), 100.0, np.float32),
        "WEIGHT": np.ones((nrow, nchan, ncorr), np.float32),
    }
    descs = []
    for name, value in cols.items():
        if value.ndim == 1:
            descs.append(ct.makescacoldesc(name, value[0].item()))
        else:
            descs.append(
                ct.makearrcoldesc(
                    name,
                    value.flat[0].item(),
                    ndim=2,
                    valuetype={"c": "complex", "f": "float", "b": "boolean"}[
                        value.dtype.kind
                    ],
                )
            )
    path = out / "w5-gain.G"
    result = {"path": str(path)}
    try:
        t = ct.table(str(path), ct.maketabdesc(descs), nrow=nrow)
        for name, value in cols.items():
            t.putcol(name, value)
        t.putkeywords(
            {
                "ParType": "Complex",
                "MSName": "w1-a-default.ms",
                "VisCal": "G Jones",
                "PolBasis": "unknown",
            }
        )
        result["has_putinfo"] = hasattr(t, "putinfo")
        if hasattr(t, "putinfo"):
            t.putinfo({"type": "Calibration", "subType": "G Jones", "readme": ""})
        for sub in ("ANTENNA", "FIELD", "SPECTRAL_WINDOW", "OBSERVATION", "HISTORY"):
            s = ct.default_ms_subtable(sub, str(path / sub))
            s.close()
            t.putkeyword(sub, "Table: " + str(path / sub))
        t.flush()
        t.close()
    except Exception as error:  # noqa: BLE001
        result["error"] = f"{type(error).__name__}: {error}"
    result["table_info_written"] = (path / "table.info").exists()
    # Workaround copy: the same table with a hand-written table.info.
    if path.exists():
        fixed = out / "w5-gain-info.G"
        shutil.copytree(path, fixed)
        (fixed / "table.info").write_text("Type = Calibration\nSubType = G Jones\n\n")
        result["workaround"] = str(fixed)
    np.savez(out / "w5-columns.npz", **cols)
    _finish(out / "caltable.json", result, gate=False)


def cmd_verify_writes(oracle_dir, out):
    """Gate W1 and W4 on the python-casacore read-backs; report W2, W3, W5."""
    out = Path(out)
    result = {"criteria": {}, "reported": {}}
    written = written_arrays(oracle_dir)
    sub_expected = {s: CHECK.load_oracle(oracle_dir, f"ms0.{s}") for s in SUBTABLES}
    write = json.loads((out / "write.json").read_text())
    for variant in [v for v in VARIANTS if v in write]:
        dump = out / f"readback-w1-{variant}"
        failures = []
        if "error" in write.get(variant, {}):
            failures.append(write[variant]["error"])
        elif not (dump / "receipt.json").exists():
            failures.append("no python-casacore read-back")
        else:
            arrays, _ = CHECK.load_oracle(dump, "ms0")
            expected = ({k: v for k, v in written.items()}, {})
            got = ({k: arrays.get(k) for k in written if k in arrays}, {})
            failures += CHECK.compare_table(expected, got)
            for sub, exp in sub_expected.items():
                actual = CHECK.load_oracle(dump, f"ms0.{sub}")
                failures += [f"{sub}: {f}" for f in CHECK.compare_table(exp, actual)]
            if VARIANTS[variant][0]:
                receipt = json.loads((dump / "receipt.json").read_text())
                dm = receipt["tables"]["ms0"]["dminfo"]
                for name in TILED:
                    kinds = [v["TYPE"] for v in dm.values() if name in v["COLUMNS"]]
                    if kinds != ["TiledColumnStMan"]:
                        failures.append(f"{name}: stored by {kinds}")
        result["criteria"][f"W1_{variant}"] = {
            "passed": not failures,
            "failures": failures,
        }
        # W2: core_ms reads the casacure-written MS.
        path = out / f"w1-{variant}.ms"
        w2 = []
        try:
            got = CHECK.read_with_core(path, list(written), 0, None, [])
            w2 = CHECK.compare_table((written, {}), got)
        except Exception as error:  # noqa: BLE001
            w2 = [f"{type(error).__name__}: {error}"]
        result["reported"][f"W2_core_ms_{variant}"] = w2
    # W3: python-casacore wrote ~pattern into FLAG; casacure reads it.
    import casacure.tables as ct

    interop = out / "w3-interop.ms"
    if interop.exists():
        t = ct.table(str(interop), ack=False)
        flag = t.getcol("FLAG")
        others = {k: t.getcol(k) for k in written if k != "FLAG"}
        t.close()
        w3 = CHECK.compare_arrays("FLAG", ~flag_pattern(flag.shape), flag)
        rest = CHECK.compare_table(
            ({k: v for k, v in written.items() if k != "FLAG"}, {}), (others, {})
        )
        result["reported"]["W3_casacore_put_casacure_read"] = [w3] if w3 else [] + rest
    # W4: in-place writes read back by python-casacore.
    inplace = json.loads((out / "inplace.json").read_text())
    for label, entry in inplace.items():
        failures = [entry["error"]] if "error" in entry else []
        dump = out / f"readback-w4-{label}"
        if not (dump / "receipt.json").exists():
            failures.append("no python-casacore read-back")
        else:
            original, _ = CHECK.load_oracle(oracle_dir, label)
            arrays, _ = CHECK.load_oracle(dump, "ms0")
            flag = arrays.get("FLAG")
            if flag is None:
                failures.append("FLAG missing")
            else:
                err = CHECK.compare_arrays("FLAG", flag_pattern(flag.shape), flag)
                if err:
                    failures.append(err)
            corrected = arrays.get("CORRECTED_DATA")
            if corrected is None:
                failures.append("CORRECTED_DATA missing")
            else:
                exp = (original["DATA"] * np.complex64(1 + 1j)).astype(np.complex64)
                err = CHECK.compare_arrays("CORRECTED_DATA", exp, corrected)
                if err:
                    failures.append(err)
            rest = {k: v for k, v in original.items() if k not in ("FLAG",)}
            failures += CHECK.compare_table(
                (rest, {}), ({k: arrays.get(k) for k in rest if k in arrays}, {})
            )
            receipt = json.loads((dump / "receipt.json").read_text())
            dm = receipt["tables"]["ms0"]["dminfo"]
            entry["flag_manager_after"] = [
                v["TYPE"] for v in dm.values() if "FLAG" in v["COLUMNS"]
            ]
        result["criteria"][f"W4_{label}"] = {
            "passed": not failures,
            "failures": failures,
        }
        result["reported"][f"W4_{label}_files"] = {
            "changed": entry.get("files_changed"),
            "added": entry.get("files_added"),
            "removed": entry.get("files_removed"),
            "flag_manager_before": [
                v["TYPE"]
                for v in entry.get("dminfo_before", {}).values()
                if "FLAG" in v["COLUMNS"]
            ],
            "flag_manager_after_casacore": entry.get("flag_manager_after"),
        }
    # W5 (reported).
    info_path = out / "caltable-info.json"
    if info_path.exists():
        info = json.loads(info_path.read_text())
        cols = dict(np.load(out / "w5-columns.npz"))
        report = {}
        for path, entry in info.items():
            if "error" in entry:
                report[path] = entry
                continue
            values = []
            for name, value in cols.items():
                got = entry["columns"].get(name)
                if name == "CPARAM":
                    got = np.asarray(got["real"]) + 1j * np.asarray(got["imag"])
                if got is None or not np.allclose(np.asarray(got), value, atol=0):
                    values.append(name)
            report[path] = {
                "info": entry["info"],
                "keywords": sorted(entry["keywords"]),
                "value_mismatches": values,
            }
        result["reported"]["W5_caltable"] = report
    _finish(out / "result.json", result)


# TaQL, measures, uvw --------------------------------------------------------


def cmd_taql(theirs, ms, out):
    import casacure.tables as ct

    reference = json.loads(Path(theirs).read_text())
    t = ct.table(str(ms), ack=False)
    result = {}
    for label, ref in reference.items():
        entry = {"query": ref["query"]}
        try:
            sel = ct.taql(ref["query"].replace("$t", "$1"), tables=[t])
            entry["nrows"] = sel.nrows()
            # casacure's rownumbers() takes no table argument (python-casacore's
            # rownumbers(parent) maps to parent rows); reported as is.
            entry["rownumbers"] = [int(r) for r in sel.rownumbers()]
            cols = (
                ["ANTENNA1"]
                if label == "unique_ant1"
                else ["TIME", "ANTENNA1", "ANTENNA2"]
            )
            for col in cols:
                entry[col] = np.asarray(sel.getcol(col)).tolist() if sel.nrows() else []
            # Equal selections: same row count and the same values, in order,
            # of the selected columns. Row numbers are reported separately:
            # casacure's rownumbers() cannot map to the parent table.
            entry["equal"] = all(entry.get(k) == ref.get(k) for k in ["nrows"] + cols)
            entry["rownumbers_equal"] = entry["rownumbers"] == ref.get("rownumbers")
        except Exception as error:  # noqa: BLE001
            entry["error"] = f"{type(error).__name__}: {error}"
            entry["equal"] = False
        entry["casacore"] = {k: ref.get(k) for k in ("nrows", "error") if k in ref}
        result[label] = entry
    t.close()
    Path(out).write_text(json.dumps(result, indent=1) + "\n")
    print({k: v["equal"] for k, v in result.items()})


def cmd_measures_cases(oracle_dir, out):
    """The frozen measures cases: LUNO fields and epochs, the fixture epoch,
    2010-01-01 and 2026-10-30, at m000 and at the MeerKAT array centre."""
    luno, _ = CHECK.load_oracle(oracle_dir, "ms1")
    field, names = CHECK.load_oracle(oracle_dir, "ms1.FIELD")
    ant, _ = CHECK.load_oracle(oracle_dir, "ms1.ANTENNA")
    fixture, _ = CHECK.load_oracle(oracle_dir, "ms0")
    times = np.unique(luno["TIME"])
    epochs = {
        "luno-start": times[0] / 86400,
        "luno-end": times[-1] / 86400,
        "fixture": float(np.unique(fixture["TIME"])[0]) / 86400,
        "2010-01-01": 55197.0,
        "2026-10-30": 61343.5,
    }
    # MeerKAT array reference (katpoint's ref_location, WGS84
    # -30:42:39.8, 21:26:38.0, 1086.6 m) converted to ITRF with astropy.
    from astropy import units as u
    from astropy.coordinates import EarthLocation

    centre = EarthLocation.from_geodetic(
        lon=21.443889 * u.deg, lat=-30.711056 * u.deg, height=1086.6 * u.m
    )
    sites = {
        "m000": ant["POSITION"][0].tolist(),
        "centre": [float(centre.x.value), float(centre.y.value), float(centre.z.value)],
    }
    cases = []
    for site, xyz in sites.items():
        for epoch, mjd in epochs.items():
            for i, name in enumerate(names["NAME"]):
                ra, dec = field["PHASE_DIR"][i, 0]
                cases.append(
                    {
                        "site": site,
                        "itrf_m": xyz,
                        "epoch": epoch,
                        "mjd_utc": float(mjd),
                        "field": name,
                        "ra_rad": float(ra),
                        "dec_rad": float(dec),
                    }
                )
    Path(out).write_text(json.dumps(cases, indent=1) + "\n")


def _astropy_case(case):
    from astropy import units as u
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord
    from astropy.time import Time

    loc = EarthLocation.from_geocentric(*case["itrf_m"], unit=u.m)
    t = Time(case["mjd_utc"], format="mjd", scale="utc")
    src = SkyCoord(case["ra_rad"] * u.rad, case["dec_rad"] * u.rad, frame="fk5")
    frame = AltAz(obstime=t, location=loc, pressure=0)
    altaz = src.transform_to(frame)
    # Parallactic angle: position angle of the zenith seen from the source.
    zenith = SkyCoord(alt=90 * u.deg, az=0 * u.deg, frame=frame).transform_to("fk5")
    pa = src.position_angle(zenith).to(u.deg).value
    geo = loc.to_geodetic("WGS84")
    return {
        "astropy_az_deg": float(altaz.az.deg),
        "astropy_el_deg": float(altaz.alt.deg),
        "astropy_parangle_deg": float((pa + 180) % 360 - 180),
        "astropy_wgs84_lon_deg": float(geo.lon.deg),
        "astropy_wgs84_lat_deg": float(geo.lat.deg),
        "astropy_wgs84_h_m": float(geo.height.to(u.m).value),
        "astropy_TAI_mjd": float(t.tai.mjd),
        "astropy_TT_mjd": float(t.tt.mjd),
        "astropy_UT1_mjd": float(t.ut1.mjd),
    }


def _casacure_case(case):
    import casacure.measures as cm
    import casacure.quanta as qa

    dm = cm.measures()
    out = {}
    pos = dm.position("ITRF", *(qa.quantity(v, "m") for v in case["itrf_m"]))
    epoch = dm.epoch("UTC", qa.quantity(case["mjd_utc"], "d"))
    dm.do_frame(pos)
    dm.do_frame(epoch)
    src = dm.direction(
        "J2000", qa.quantity(case["ra_rad"], "rad"), qa.quantity(case["dec_rad"], "rad")
    )
    for ref in ("AZEL", "AZELGEO"):
        azel = dm.measure(src, ref)
        out[f"casacure_{ref}_az_deg"] = float(np.degrees(azel["m0"]["value"]))
        out[f"casacure_{ref}_el_deg"] = float(np.degrees(azel["m1"]["value"]))
    for key, ref in (("parangle", "AZEL"), ("parangle_geo", "AZELGEO")):
        try:
            zenith = dm.direction(ref, qa.quantity(0, "deg"), qa.quantity(90, "deg"))
            out[f"casacure_{key}_deg"] = float(
                dm.posangle(src, zenith).get_value("deg")
            )
        except Exception as error:  # noqa: BLE001
            out[f"casacure_{key}_error"] = str(error)
    for key, fn in (("wgs84", lambda: dm.measure(pos, "WGS84")),):
        try:
            wgs = fn()
            out["casacure_wgs84_lon_deg"] = float(np.degrees(wgs["m0"]["value"]))
            out["casacure_wgs84_lat_deg"] = float(np.degrees(wgs["m1"]["value"]))
            out["casacure_wgs84_h_m"] = float(wgs["m2"]["value"])
        except Exception as error:  # noqa: BLE001
            out[f"casacure_{key}_error"] = str(error)
    for ref in ("TAI", "TT", "UT1"):
        try:
            out[f"casacure_{ref}_mjd"] = float(dm.measure(epoch, ref)["m0"]["value"])
        except Exception as error:  # noqa: BLE001
            out[f"casacure_{ref}_error"] = str(error)
    return out


def _wrap(deg):
    return (np.asarray(deg) + 180.0) % 360.0 - 180.0


def cmd_measures(cases_path, casacore_path, out):
    from astropy.utils import iers

    iers.conf.auto_download = False
    import astropy
    import astropy_iers_data

    cases = json.loads(Path(cases_path).read_text())
    casacore = (
        json.loads(Path(casacore_path).read_text()) if casacore_path != "-" else None
    )
    rows = []
    for i, case in enumerate(cases):
        row = dict(case)
        row.update(_astropy_case(case))
        try:
            row.update(_casacure_case(case))
        except Exception as error:  # noqa: BLE001
            row["casacure_error"] = f"{type(error).__name__}: {error}"
        if casacore is not None:
            row.update(
                {k: v for k, v in casacore[i].items() if k.startswith("casacore")}
            )
        rows.append(row)

    def arcsec(a, b, wrap=True):
        d = np.asarray(a) - np.asarray(b)
        return np.abs(_wrap(d) if wrap else d) * 3600

    summary = {}
    for who in ("casacure", "casacore"):
        for ref in ("AZEL", "AZELGEO"):
            key_az, key_el = f"{who}_{ref}_az_deg", f"{who}_{ref}_el_deg"
            ok = [r for r in rows if key_az in r]
            if not ok:
                continue
            for epoch in sorted({r["epoch"] for r in ok}):
                sel = [r for r in ok if r["epoch"] == epoch]
                daz = arcsec(
                    [r[key_az] for r in sel], [r["astropy_az_deg"] for r in sel]
                )
                dalt = arcsec(
                    [r[key_el] for r in sel], [r["astropy_el_deg"] for r in sel], False
                )
                cosel = np.cos(np.radians([r["astropy_el_deg"] for r in sel]))
                summary[f"{who}_{ref}_vs_astropy_{epoch}"] = {
                    "max_az_cos_el_arcsec": float(np.max(daz * cosel)),
                    "max_el_arcsec": float(np.max(dalt)),
                }
        for pa in ("parangle", "parangle_geo"):
            key = f"{who}_{pa}_deg"
            ok = [r for r in rows if key in r]
            if ok:
                for epoch in sorted({r["epoch"] for r in ok}):
                    sel = [r for r in ok if r["epoch"] == epoch]
                    d = arcsec(
                        [r[key] for r in sel], [r["astropy_parangle_deg"] for r in sel]
                    )
                    summary[f"{who}_{pa}_vs_astropy_{epoch}"] = {
                        "max_arcsec": float(np.max(d))
                    }
        for ref in ("TAI", "TT", "UT1"):
            key = f"{who}_{ref}_mjd"
            ok = [r for r in rows if key in r]
            if ok:
                d = [abs(r[key] - r[f"astropy_{ref}_mjd"]) * 86400e3 for r in ok]
                summary[f"{who}_{ref}_vs_astropy_max_ms"] = float(np.max(d))
        key = f"{who}_wgs84_lat_deg"
        ok = [r for r in rows if key in r]
        if ok:
            summary[f"{who}_wgs84_vs_astropy"] = {
                "max_lat_arcsec": float(
                    max(abs(r[key] - r["astropy_wgs84_lat_deg"]) * 3600 for r in ok)
                ),
                "max_lon_arcsec": float(
                    max(
                        abs(
                            _wrap(
                                r[f"{who}_wgs84_lon_deg"] - r["astropy_wgs84_lon_deg"]
                            )
                        )
                        * 3600
                        for r in ok
                    )
                ),
                "max_h_m": float(
                    max(abs(r[f"{who}_wgs84_h_m"] - r["astropy_wgs84_h_m"]) for r in ok)
                ),
            }
    if casacore is not None:
        ok = [
            r
            for r in rows
            if "casacore_parangle_deg" in r and "casacure_parangle_deg" in r
        ]
        if ok:
            summary["casacure_vs_casacore_AZEL_parangle_max_deg"] = float(
                np.max(
                    np.abs(
                        _wrap(
                            [
                                r["casacure_parangle_deg"] - r["casacore_parangle_deg"]
                                for r in ok
                            ]
                        )
                    )
                )
            )
            summary["casacore_AZEL_minus_AZELGEO_parangle_deg"] = {
                r["field"] + "@" + r["epoch"] + "@" + r["site"]: float(
                    _wrap(r["casacore_parangle_deg"] - r["casacore_parangle_geo_deg"])
                )
                for r in ok
            }
    result = {
        "astropy": astropy.__version__,
        "astropy_iers_data": astropy_iers_data.__version__,
        "iers_auto_download": False,
        "summary": summary,
        "rows": rows,
    }
    Path(out).write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(summary, indent=1))


def cmd_uvw(ms, out):
    """M3: stored UVW against an astropy uvw (ITRF baseline, J2000 phase centre)."""
    from astropy import units as u
    from astropy.coordinates import SkyCoord
    from astropy.time import Time
    from astropy.utils import iers

    iers.conf.auto_download = False
    import casacure.tables as ct

    t = ct.table(str(ms), ack=False)
    uvw = t.getcol("UVW")
    time_s = t.getcol("TIME")
    a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
    fid = t.getcol("FIELD_ID")
    t.close()
    pos = ct.table(str(Path(ms) / "ANTENNA"), ack=False).getcol("POSITION")
    phase = ct.table(str(Path(ms) / "FIELD"), ack=False).getcol("PHASE_DIR")[:, 0]
    result = {"ms": str(ms), "fields": {}}
    from astropy.coordinates import FK5, EarthLocation

    def project(b, ra, dec):
        east = np.array([-np.sin(ra), np.cos(ra), 0.0])
        north = np.array(
            [-np.sin(dec) * np.cos(ra), -np.sin(dec) * np.sin(ra), np.cos(dec)]
        )
        source = np.array(
            [np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)]
        )
        return np.array([b @ east, b @ north, b @ source])

    for f in np.unique(fid):
        sel = fid == f
        times = Time(time_s[sel] / 86400, format="mjd", scale="utc")
        src = SkyCoord(phase[f, 0] * u.rad, phase[f, 1] * u.rad, frame="fk5")
        date_uvw = np.empty((sel.sum(), 3))
        j2000_uvw = np.empty((sel.sum(), 3))
        gcrs = {}
        for i, (tt, p, q) in enumerate(zip(times, a1[sel], a2[sel])):
            # (1) Frame of date, first order: the source precessed to the
            # equinox of date, the ITRF baseline rotated by GAST (no polar
            # motion, no aberration).
            app = src.transform_to(FK5(equinox=tt))
            b = pos[p] - pos[q]
            gast = tt.sidereal_time("apparent", longitude=0).rad
            rotated = np.array(
                [
                    b[0] * np.cos(gast) - b[1] * np.sin(gast),
                    b[0] * np.sin(gast) + b[1] * np.cos(gast),
                    b[2],
                ]
            )
            date_uvw[i] = project(rotated, app.ra.rad, app.dec.rad)
            # (2) J2000 (post hoc, after review): GCRS antenna positions at
            # TIME, baseline projected on the J2000 phase centre.
            key = float(tt.mjd)
            if key not in gcrs:
                gcrs[key] = np.array(
                    [
                        EarthLocation.from_geocentric(*x, unit=u.m)
                        .get_gcrs(tt)
                        .cartesian.xyz.to(u.m)
                        .value
                        for x in pos
                    ]
                )
            j2000_uvw[i] = project(
                gcrs[key][p] - gcrs[key][q], phase[f, 0], phase[f, 1]
            )
        stored = uvw[sel]
        length = np.linalg.norm(stored, axis=1)
        entry = {"rows": int(sel.sum()), "max_baseline_m": float(np.max(length))}
        for label, calc in (("date_first_order", date_uvw), ("j2000_gcrs", j2000_uvw)):
            diff = calc - stored
            entry[label] = {
                "max_abs_diff_m": float(np.max(np.abs(diff))),
                "rms_diff_m": float(np.sqrt(np.mean(diff**2))),
            }
        result["fields"][int(f)] = entry
    Path(out).write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))


# Rust crate (R3) --------------------------------------------------------------


def cmd_rust_args(oracle_dir, ms_root=None):
    """Print the `<label>=<dir>` arguments of the Rust reader for the oracle."""
    receipt = json.loads((Path(oracle_dir) / "receipt.json").read_text())
    root = Path(ms_root) if ms_root else HERE.parent / "outputs"
    print(
        " ".join(
            f"{label}={oracle_path(e['path'], root)}"
            for label, e in receipt["tables"].items()
        )
    )


def cmd_rust_compare(oracle_dir, rust_out, out):
    """R3: the Rust program's bytes against the oracle (strings by value)."""
    receipt = json.loads((Path(oracle_dir) / "receipt.json").read_text())
    failures, compared, errors = [], 0, {}
    for label, entry in receipt["tables"].items():
        arrays, strings = CHECK.load_oracle(oracle_dir, label)
        folder = Path(rust_out) / label
        index = {}
        if (folder / "columns.tsv").exists():
            for line in (folder / "columns.tsv").read_text().splitlines():
                parts = line.split("\t")
                index[parts[0]] = parts[1:]
        for name in entry["columns"]:
            if "error" in entry["columns"][name]:
                continue
            status = index.get(name)
            if not status or status[0] != "ok":
                failures.append(f"{label}:{name}: {status}")
                errors[f"{label}:{name}"] = status
                continue
            compared += 1
            if name in arrays:
                expected = np.ascontiguousarray(arrays[name]).tobytes()
                got = (folder / f"{name}.bin").read_bytes()
                if expected != got:
                    failures.append(
                        f"{label}:{name}: {len(got)} bytes, expected {len(expected)}"
                    )
            else:
                expected = list(np.asarray(strings[name], dtype=object).reshape(-1))
                got = [
                    json.loads(s)
                    for s in (folder / f"{name}.strings").read_text().splitlines()
                ]
                if expected != got:
                    failures.append(f"{label}:{name}: strings differ")
    result = {
        "criteria": {
            "R3_rust_crate_exact": {"passed": not failures, "failures": failures}
        },
        "compared": compared,
        "errors": errors,
    }
    _finish(Path(out), result)


# Performance ------------------------------------------------------------------


def _all_tables(ms):
    ms = Path(ms)
    return [ms] + sorted(p for p in ms.iterdir() if (p / "table.dat").exists())


def cmd_perf(backend, what, ms, out):
    started = time.perf_counter()
    nbytes = 0
    if backend == "casacure":
        import casacure.tables as ct

        def opener(p):
            return ct.table(str(p), ack=False)
    elif backend == "core_ms":
        sys.path.insert(0, str(HERE.parent / "python"))
        from rangtoy import core_ms

        def opener(p):
            return core_ms.open_table(p)
    else:
        raise SystemExit(backend)
    started = time.perf_counter()
    tables = _all_tables(ms) if what == "all" else [Path(ms)]
    skipped = []
    for path in tables:
        t = opener(path)
        names = t.colnames() if what == "all" else ["DATA"]
        for name in names:
            try:
                value = t.getcol(name)
            except Exception as error:  # noqa: BLE001 - unreadable columns listed
                skipped.append(f"{path.name}:{name}: {type(error).__name__}")
                continue
            nbytes += getattr(value, "nbytes", 0)
        t.close()
    wall = time.perf_counter() - started
    Path(out).write_text(
        json.dumps(
            {
                "backend": backend,
                "what": what,
                "wall_s": wall,
                "peak_rss_mb": _peak_rss_mb(),
                "bytes": nbytes,
                "skipped": skipped,
            }
        )
        + "\n"
    )


def _finish(path, result, gate=True):
    if gate:
        passed = all(c["passed"] for c in result.get("criteria", {}).values())
        result["passed"] = passed
    Path(path).write_text(json.dumps(result, indent=1, default=str) + "\n")
    for name, criterion in result.get("criteria", {}).items():
        print(
            name, "PASS" if criterion["passed"] else "FAIL", criterion["failures"][:5]
        )
    if "passed" in result:
        print("overall", "PASS" if result["passed"] else "FAIL")


def main():
    command, args = sys.argv[1], sys.argv[2:]
    if command == "reads":
        flags = [a for a in args if a.startswith("--")]
        rest = [a for a in args if not a.startswith("--")]
        root = None
        if "--ms-root" in args:
            root = args[args.index("--ms-root") + 1]
            rest.remove(root)
        cmd_reads(rest[0], rest[1], root, "--no-core" not in flags)
    elif command == "bigendian":
        cmd_bigendian(*args)
    elif command == "describe":
        cmd_describe(args[0], args[1:])
    elif command == "compare-describe":
        cmd_compare_describe(*args)
    elif command == "write":
        cmd_write(*args)
    elif command == "inplace":
        cmd_inplace(args[0], args[1:])
    elif command == "caltable":
        cmd_caltable(*args)
    elif command == "verify-writes":
        cmd_verify_writes(*args)
    elif command == "taql":
        cmd_taql(*args)
    elif command == "measures-cases":
        cmd_measures_cases(*args)
    elif command == "measures":
        cmd_measures(*args)
    elif command == "uvw":
        cmd_uvw(*args)
    elif command == "rust-args":
        cmd_rust_args(*args)
    elif command == "rust-compare":
        cmd_rust_compare(*args)
    elif command == "perf":
        cmd_perf(*args)
    else:
        raise SystemExit(f"unknown command {command}")


if __name__ == "__main__":
    main()
