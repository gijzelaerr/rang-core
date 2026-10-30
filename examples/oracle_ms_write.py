"""The python-casacore side of task E3 (research/e3-table-writer.md).

Runs in `rang-ms-reader:local` (python-casacore 3.8.1, NumPy 2.5.3):

    python examples/oracle_ms_write.py write <out> <fixture.ms> <luno.ms> <imaging.ms>
    python examples/oracle_ms_write.py readback <dump-dir> <table> [<table> ...]
    python examples/oracle_ms_write.py roundtrip <out> <ms> [<ms> ...]
    python examples/oracle_ms_write.py rewrite <table> <column> <seed> <dump-dir>
    python examples/oracle_ms_write.py hold-lock <table> <seconds>
    python examples/oracle_ms_write.py watch <table> <column> <ready-file> <go-file> <dump-dir>
    python examples/oracle_ms_write.py try-lock <table>
    python examples/oracle_ms_write.py scale-build <out>
    python examples/oracle_ms_write.py scale-write <out> <table>...

`write` performs every frozen case on a fresh copy of its input (permanent
locking, the writes, one close) under `<out>/casacore/<case>`, and stores
the values it wrote in `<out>/values/<case>.npz` and the case list in
`<out>/cases.json` with the wall time of every case. The host checker
(`examples/check_ms_writer.py`) replays the same cases with the core writer
through `apply`, which works with python-casacore's table and with
`rang.core_ms_write.Table` alike. `readback` dumps every readable column
and the keywords of the given tables (`<label>.npz` and `<label>.json`).
"""

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

SEED = 20261030


def random_like(rng, arr):
    """Random values of an array's dtype and shape (bools, ints, floats,
    complex numbers with finite parts)."""
    arr = np.asarray(arr)
    if arr.dtype == bool:
        return rng.random(arr.shape) < 0.5
    if arr.dtype.kind in "iu":
        return rng.integers(0, 4, arr.shape).astype(arr.dtype)
    if arr.dtype.kind == "f":
        return rng.standard_normal(arr.shape).astype(arr.dtype)
    if arr.dtype.kind == "c":
        return (
            rng.standard_normal(arr.shape) + 1j * rng.standard_normal(arr.shape)
        ).astype(arr.dtype)
    raise ValueError(arr.dtype)


def cases(fixture, luno, imaging):
    """The frozen cases: (name, input, table, ops). `ops` refer to values by
    name; `values(name, getcol)` builds them from the input with the seed."""
    complex_desc = {"valuetype": "complex", "ndim": 2}
    out = [
        ("F-flagrow", fixture, "", [("putcol", "FLAG_ROW")]),
        ("F-ant1", fixture, "", [("putcol", "ANTENNA1")]),
        ("F-flag", fixture, "", [("putcol", "FLAG")]),
        ("F-ws", fixture, "", [("putcol", "WEIGHT_SPECTRUM")]),
        ("F-data", fixture, "", [("putcol", "DATA")]),
        ("F-sigma", fixture, "", [("putcol", "SIGMA")]),
        ("F-uvw", fixture, "", [("putcol", "UVW")]),
        (
            "F-ranges",
            fixture,
            "",
            [
                ("putrange", "FLAG", 10, 40),
                ("putrange", "FLAG_ROW", 10, 40),
                ("putcell", "FLAG", 7),
                ("putcell", "DATA", 3),
            ],
        ),
        (
            "F-keywords",
            fixture,
            "",
            [
                ("putkeyword", "RANG_D", 1.5),
                ("putkeyword", "RANG_I", "int32:7"),
                ("putkeyword", "RANG_S", "rang"),
                ("putkeyword", "RANG_A", "float64:[1.0, 2.0, 3.0]"),
                ("putkeyword", "RANG_REC", {"a": 1.0, "b": "x"}),
                ("putcolkeyword", "DATA", "RANG_UNIT", "Jy"),
                ("putcolkeyword", "UVW", "QuantumUnits", "str:['km', 'km', 'km']"),
            ],
        ),
        (
            "F-multi",
            fixture,
            "",
            [
                ("putcol", "FLAG"),
                ("putcol", "FLAG_ROW"),
                ("putcol", "DATA"),
                ("putkeyword", "RANG_D", 2.5),
            ],
        ),
        (
            "F-add-default",
            fixture,
            "",
            [
                ("addcols", "RANG_MODEL_DATA", dict(complex_desc), None),
                ("putcol", "RANG_MODEL_DATA"),
            ],
        ),
        (
            "F-add-group",
            fixture,
            "",
            [
                (
                    "addcols",
                    "CORRECTED_DATA",
                    dict(
                        complex_desc,
                        datamanagertype="StandardStMan",
                        datamanagergroup="RANG_IMAGING_CORRECTED",
                    ),
                    None,
                ),
                ("putcol", "CORRECTED_DATA"),
            ],
        ),
        (
            "F-add-shape",
            fixture,
            "",
            [
                ("addcols", "RANG_MODEL_DATA", dict(complex_desc), None),
                ("putcol", "RANG_MODEL_DATA"),
                ("putcell_shape", "RANG_MODEL_DATA", 3, (10, 4)),
            ],
        ),
        (
            "F-add-tcs",
            fixture,
            "",
            [
                (
                    "addcols",
                    "RANG_TCS",
                    {"valuetype": "boolean", "shape": [4096, 4]},
                    {
                        "TYPE": "TiledColumnStMan",
                        "NAME": "RANG_TCS_DM",
                        "SPEC": {"DEFAULTTILESHAPE": [16, 64, 4]},
                    },
                ),
                ("putcol", "RANG_TCS"),
            ],
        ),
        (
            "F-add-tss",
            fixture,
            "",
            [
                (
                    "addcols",
                    "RANG_TSS",
                    {"valuetype": "float", "shape": [4096, 4]},
                    {
                        "TYPE": "TiledShapeStMan",
                        "NAME": "RANG_TSS_DM",
                        "SPEC": {"DEFAULTTILESHAPE": [16, 64, 4]},
                    },
                ),
                ("putcol", "RANG_TSS"),
            ],
        ),
        (
            "F-add-ssm-new",
            fixture,
            "",
            [
                (
                    "addcols",
                    "RANG_SSM",
                    dict(
                        complex_desc,
                        datamanagertype="StandardStMan",
                        datamanagergroup="RANG_SSM_DM",
                    ),
                    {"TYPE": "StandardStMan", "NAME": "RANG_SSM_DM", "SPEC": {}},
                ),
                ("putcol", "RANG_SSM"),
            ],
        ),
        (
            "F-antenna-strings",
            fixture,
            "ANTENNA",
            [("putstrings", "NAME"), ("putstrings", "STATION")],
        ),
        ("L-flag", luno, "", [("putcol", "FLAG")]),
        ("L-model", luno, "", [("putcol", "MODEL_DATA")]),
        ("L-ws", luno, "", [("putcol", "WEIGHT_SPECTRUM")]),
        ("L-flagrow", luno, "", [("putcol", "FLAG_ROW")]),
        ("L-uvw", luno, "", [("putcol", "UVW")]),
        ("L-kw", luno, "", [("putkeyword", "RANG_D", 2.5)]),
        ("I-corr", imaging, "", [("putcol", "CORRECTED_DATA")]),
    ]
    return out


def keyword_value(v):
    """Typed keyword values from their JSON-able form ("int32:7")."""
    if (
        isinstance(v, str)
        and ":" in v
        and v.split(":", 1)[0] in ("int32", "float64", "str")
    ):
        kind, text = v.split(":", 1)
        parsed = json.loads(text.replace("'", '"'))
        if kind == "str":
            return np.array(parsed)
        return (
            np.asarray(parsed, dtype=kind)[()]
            if not isinstance(parsed, list)
            else np.asarray(parsed, kind)
        )
    return v


def string_values(rng, n):
    """Strings shorter and longer than the 8-byte slot, deterministic."""
    words = ["m0", "m001", "rang-ant", "rang-antenna-name", "x" * 23, "MeerKAT"]
    return [
        words[int(i)] + str(k) for k, i in enumerate(rng.integers(0, len(words), n))
    ]


def apply(tab, ops, values, make):
    """Perform `ops` on an open table. `values` maps op index to the array
    to write; `make` provides makearrcoldesc and maketabdesc."""
    for i, op in enumerate(ops):
        kind = op[0]
        if kind == "putcol":
            tab.putcol(op[1], values[f"v{i}"])
        elif kind == "putstrings":
            tab.putcol(op[1], list(values[f"v{i}"]))
        elif kind == "putrange":
            tab.putcol(op[1], values[f"v{i}"], startrow=op[2], nrow=op[3])
        elif kind in ("putcell", "putcell_shape"):
            tab.putcell(op[1], op[2], values[f"v{i}"])
        elif kind == "putkeyword":
            tab.putkeyword(op[1], keyword_value(op[2]))
        elif kind == "putcolkeyword":
            tab.putcolkeyword(op[1], op[2], keyword_value(op[3]))
        elif kind == "addcols":
            d = dict(op[2])
            value = {"complex": 0j, "boolean": False, "float": 0.0}[d["valuetype"]]
            desc = make.makearrcoldesc(op[1], value, **d)
            if op[3] is None:
                tab.addcols(make.maketabdesc(desc))
            else:
                tab.addcols(make.maketabdesc(desc), op[3])
        else:
            raise ValueError(kind)


def make_values(tab, ops, rng, nrows):
    """The values each op writes, drawn from the seeded generator."""
    out = {}
    for i, op in enumerate(ops):
        kind = op[0]
        if kind == "putcol" and op[0] == "putcol":
            if op[1] in tab.colnames():
                out[f"v{i}"] = random_like(rng, tab.getcol(op[1]))
            else:
                out[f"v{i}"] = None  # filled after the addcols that makes it
        elif kind == "putstrings":
            out[f"v{i}"] = np.array(string_values(rng, nrows))
        elif kind == "putrange":
            out[f"v{i}"] = random_like(rng, tab.getcol(op[1], op[2], op[3]))
        elif kind == "putcell":
            out[f"v{i}"] = random_like(rng, tab.getcell(op[1], op[2]))
        elif kind == "putcell_shape":
            out[f"v{i}"] = random_like(rng, np.zeros(op[3], np.complex64))
    return out


def files(path):
    return sorted(p for p in Path(path).rglob("*") if p.is_file())


def cmd_write(out, fixture, luno, imaging):
    from casacore import tables

    out = Path(out)
    (out / "values").mkdir(parents=True)
    report = []
    for name, src, sub, ops in cases(fixture, luno, imaging):
        dst = out / "casacore" / name
        shutil.copytree(src, dst)
        path = dst / sub if sub else dst
        rng = np.random.default_rng(SEED)
        with tables.table(str(path), ack=False) as t:
            values = make_values(t, ops, rng, t.nrows())
            # Values of columns the case adds: shaped as DATA.
            for i, op in enumerate(ops):
                if op[0] == "putcol" and values[f"v{i}"] is None:
                    add = next(o for o in ops if o[0] == "addcols" and o[1] == op[1])
                    vt = add[2]["valuetype"]
                    shape = (t.nrows(), *add[2].get("shape", [4096, 4]))
                    dtype = {
                        "complex": np.complex64,
                        "boolean": bool,
                        "float": np.float32,
                    }[vt]
                    values[f"v{i}"] = random_like(rng, np.zeros(shape, dtype))
        start = time.perf_counter()
        error = None
        try:
            t = tables.table(
                str(path), readonly=False, lockoptions="permanent", ack=False
            )
            apply(t, ops, values, tables)
            t.close()
        except Exception as e:  # noqa: BLE001 - recorded, the case stays in the list
            error = f"{type(e).__name__}: {e}"
        wall = time.perf_counter() - start
        np.savez(out / "values" / f"{name}.npz", **{k: v for k, v in values.items()})
        report.append(
            {
                "name": name,
                "input": str(src),
                "table": sub,
                "ops": ops,
                "wall_s": wall,
                "error": error,
            }
        )
        print(f"{name}: {wall * 1e3:.1f} ms {error or ''}", flush=True)
    (out / "cases.json").write_text(json.dumps(report, indent=1, default=str))


def plain(v):
    """Keywords as JSON: arrays as {dtype, shape, values}."""
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items()}
    if isinstance(v, np.ndarray):
        return {
            "dtype": str(v.dtype),
            "shape": list(v.shape),
            "values": [plain(x) for x in v.reshape(-1).tolist()],
        }
    if isinstance(v, (np.generic,)):
        return {"scalar": str(v.dtype), "value": plain(v.item())}
    if isinstance(v, complex):
        return [v.real, v.imag]
    if isinstance(v, bytes):
        return v.decode()
    return v


def cmd_readback(dump, tables_in):
    from casacore import tables

    dump = Path(dump)
    dump.mkdir(parents=True, exist_ok=True)
    for path in tables_in:
        label = str(path).strip("/").replace("/", "__")
        arrays, meta = {}, {"columns": {}, "errors": {}}
        with tables.table(str(path), ack=False, lockoptions="autonoread") as t:
            meta["nrows"] = t.nrows()
            meta["keywords"] = plain(t.getkeywords())
            for c in t.colnames():
                meta["columns"][c] = plain(t.getcolkeywords(c))
                try:
                    v = t.getcol(c)
                except Exception as e:  # noqa: BLE001 - recorded, the run goes on
                    meta["errors"][c] = f"{type(e).__name__}: {e}"
                    continue
                if isinstance(v, (list, dict)) or (
                    isinstance(v, np.ndarray) and v.dtype.kind in "OU"
                ):
                    try:
                        meta.setdefault("strings", {})[c] = [
                            str(x) for x in np.asarray(v).reshape(-1)
                        ]
                    except Exception as e:  # noqa: BLE001 - recorded, the run goes on
                        meta["errors"][c] = f"{type(e).__name__}: {e}"
                else:
                    arrays[c] = v
        np.savez(dump / f"{label}.npz", **arrays)
        (dump / f"{label}.json").write_text(json.dumps(meta, default=str))
        print(label, len(arrays), "columns", flush=True)


def cmd_roundtrip(out, mss):
    """Read every readable column of each table and write it back unchanged,
    one session per table (criterion 3, casacore's side)."""
    from casacore import tables

    out = Path(out)
    report = {}
    for src in mss:
        dst = out / "casacore" / Path(src).parent.name
        shutil.copytree(src, dst)
        for path in [dst] + sorted(p.parent for p in dst.glob("*/table.dat")):
            t = tables.table(
                str(path), readonly=False, lockoptions="permanent", ack=False
            )
            written = []
            start = time.perf_counter()
            for c in t.colnames():
                dm = t.getdminfo(c)["TYPE"]
                if dm not in ("StandardStMan", "TiledShapeStMan", "TiledColumnStMan"):
                    continue
                desc = t.getcoldesc(c)
                if desc["valueType"] == "string" and "ndim" in desc:
                    continue  # string arrays are not written by the core (E4/E5)
                try:
                    v = t.getcol(c)
                except Exception:  # noqa: BLE001, S112 - unreadable columns are not written
                    continue
                t.putcol(c, v)
                written.append(c)
            t.close()
            report[str(path.relative_to(out))] = {
                "columns": written,
                "wall_s": time.perf_counter() - start,
            }
            print(path.relative_to(out), len(written), flush=True)
    (out / "roundtrip.json").write_text(json.dumps(report, indent=1))


def cmd_rewrite(path, column, seed, dump, startrow="0", nrow="-1"):
    """Criterion 5: casacore reads a column the core added (rows `startrow`
    onwards), writes new values, reads them back; the values are stored for
    the host."""
    from casacore import tables

    rng = np.random.default_rng(int(seed))
    start, n = int(startrow), int(nrow)
    with tables.table(str(path), readonly=False, ack=False) as t:
        before = t.getcol(column, start, n)
        new = random_like(rng, before)
        t.putcol(column, new, start, n)
        t.flush()
        after = t.getcol(column, start, n)
    Path(dump).mkdir(parents=True, exist_ok=True)
    np.savez(Path(dump) / f"rewrite-{column}.npz", before=before, new=new, after=after)
    print("rewrite", column, "equal", bool(np.array_equal(new, after)), flush=True)


def cmd_hold_lock(path, seconds):
    """Hold casacore's write lock for `seconds` (criterion 6 (i))."""
    from casacore import tables

    t = tables.table(str(path), readonly=False, lockoptions="user", ack=False)
    t.lock(write=True)
    print("locked", flush=True)
    time.sleep(float(seconds))
    t.unlock()
    t.close()
    print("released", flush=True)


def cmd_try_lock(path):
    """Whether byte 0 of table.lock is write-locked by another process (one
    non-blocking fcntl attempt), then how long casacore takes to open the
    table for writing and take the write lock (opening with user locking
    waits for a read lock; `lock()` returns None and raises on failure)."""
    import fcntl

    from casacore import tables

    with open(Path(path) / "table.lock", "r+b") as f:
        try:
            fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB, 1, 0)
            fcntl.lockf(f, fcntl.LOCK_UN, 1, 0)
            free = True
        except OSError:
            free = False
    start = time.perf_counter()
    t = tables.table(str(path), readonly=False, lockoptions="user", ack=False)
    try:
        t.lock(write=True, nattempts=30)
        got = t.haslock(write=True)
    except RuntimeError:
        got = False
    waited = time.perf_counter() - start
    print(
        json.dumps(
            {
                "lock_free_at_start": free,
                "acquired": bool(got),
                "waited_s": round(waited, 2),
            }
        ),
        flush=True,
    )
    if got:
        t.unlock()
    t.close()


def cmd_watch(path, column, ready, go, dump):
    """Criterion 6 (ii): open with auto locking, read, unlock, wait for the
    host's write, read again without reopening."""
    from casacore import tables

    t = tables.table(str(path), ack=False, lockoptions="auto")
    first = t.getcol(column)
    t.unlock()
    Path(ready).write_text("ready")
    deadline = time.time() + 120
    while not Path(go).exists() and time.time() < deadline:
        time.sleep(0.1)
    second = t.getcol(column)
    t.close()
    Path(dump).mkdir(parents=True, exist_ok=True)
    np.savez(Path(dump) / f"watch-{column}.npz", first=first, second=second)
    print("watch done", flush=True)


SCALE_ROWS, SCALE_CHAN = 41786, 2048


def cmd_scale_build(out):
    """Two synthetic tables of L1's chunk-0 size with a Bool FLAG [2048, 4]:
    FixedShape indirect StandardStMan, and TiledShapeStMan."""
    from casacore import tables

    out = Path(out)
    for name, dminfo in (
        ("scale-ssm.tab", None),
        (
            "scale-tss.tab",
            {
                "*1": {
                    "TYPE": "TiledShapeStMan",
                    "NAME": "TiledFlag",
                    "SPEC": {"DEFAULTTILESHAPE": [16, 2048, 4]},
                    "COLUMNS": ["FLAG"],
                }
            },
        ),
    ):
        desc = tables.maketabdesc(
            [
                tables.makearrcoldesc("FLAG", False, shape=[SCALE_CHAN, 4]),
                tables.makescacoldesc("FLAG_ROW", False),
            ]
        )
        start = time.perf_counter()
        t = tables.table(
            str(out / name), desc, nrow=SCALE_ROWS, dminfo=dminfo or {}, ack=False
        )
        t.putcol("FLAG", np.zeros((SCALE_ROWS, SCALE_CHAN, 4), bool))
        t.close()
        print(name, f"{time.perf_counter() - start:.2f} s", flush=True)


def cmd_scale_write(out, srcs):
    """casacore's whole-array FLAG putcol (seeded values saved for the host)."""
    from casacore import tables

    out = Path(out)
    rng = np.random.default_rng(SEED)
    flags = rng.random((SCALE_ROWS, SCALE_CHAN, 4)) < 0.3
    np.save(out / "scale-flags.npy", flags)
    report = {}
    for src in srcs:
        dst = out / "casacore" / Path(src).name
        shutil.copytree(src, dst)
        t = tables.table(str(dst), readonly=False, lockoptions="permanent", ack=False)
        start = time.perf_counter()
        t.putcol("FLAG", flags)
        t.close()
        report[Path(src).name] = time.perf_counter() - start
        print(Path(src).name, f"{report[Path(src).name]:.2f} s", flush=True)
    (out / "scale-casacore.json").write_text(json.dumps(report))


def main(argv):
    mode, args = argv[1], argv[2:]
    if mode == "write":
        cmd_write(*args)
    elif mode == "readback":
        cmd_readback(args[0], args[1:])
    elif mode == "roundtrip":
        cmd_roundtrip(args[0], args[1:])
    elif mode == "rewrite":
        cmd_rewrite(*args)
    elif mode == "hold-lock":
        cmd_hold_lock(*args)
    elif mode == "watch":
        cmd_watch(*args)
    elif mode == "try-lock":
        cmd_try_lock(*args)
    elif mode == "scale-build":
        cmd_scale_build(*args)
    elif mode == "scale-write":
        cmd_scale_write(args[0], args[1:])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
