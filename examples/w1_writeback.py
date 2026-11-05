"""W1 write-back checks (research/w1-writeback.md).

    python examples/w1_writeback.py make <ms> <nrow> <nchan> [--flag tiled|ssm] [--seed N]
    python examples/w1_writeback.py write <ms> <out.npz>     # the W1 writes, recorded
    python examples/w1_writeback.py columns <ms>              # MODEL_DATA, CORRECTED_DATA only
    python examples/w1_writeback.py scramble <ms>             # invert FLAG and FLAG_ROW
    python examples/w1_writeback.py restore <ms> <version>
    python examples/w1_writeback.py hashes <ms> <out.json>
    python examples/w1_writeback.py memory <ms> <out.json>
    python examples/w1_writeback.py kill <ms> <times> <seed> <out.json>

`make` writes a small MeasurementSet with the core writer (`default_ms`):
4 antennas' baselines without autocorrelations, linear feeds (XX XY YX YY)
or two parallel hands, random DATA, FLAG, WEIGHT and SIGMA from `seed`.
`tests/test_w1_writeback.py` imports `make_ms`. `write` runs the W1 writes
in place (columns added and initialised where missing, MODEL_DATA = 2 DATA,
a seeded FLAG and FLAG_ROW) and records hashes and the flags for the
oracles (`tools/oracles/w1/`); `memory` measures peak RSS growth of a
chunked session; `kill` interrupts FLAG writes with SIGKILL at times spread
over a write and restores after each.
"""

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from rang import core_ms, core_ms_write
from rang import core_writeback as wb
from rang.formats import flagversions

CORR4 = [9, 10, 11, 12]
CORR2 = [9, 12]


def make_ms(path, nrow, nchan, ncorr=4, flag="ssm", seed=20261106, nant=4):
    """A MeasurementSet of `nrow` rows (cross-correlations of `nant`
    antennas, repeated in time), `nchan` channels at L band and `ncorr`
    correlations, DATA in a TiledColumnStMan, FLAG in the default
    StandardStMan (`flag="ssm"`) or a TiledColumnStMan (`"tiled"`)."""
    path = Path(path)
    rng = np.random.default_rng(seed)
    desc = [
        core_ms_write.makearrcoldesc(
            "DATA",
            0j,
            shape=[nchan, ncorr],
            valuetype="complex",
            comment="The data column",
        ),
        core_ms_write.makearrcoldesc("FLAG", False, shape=[nchan, ncorr]),
        core_ms_write.makearrcoldesc("WEIGHT", 0.0, shape=[ncorr], valuetype="float"),
        core_ms_write.makearrcoldesc("SIGMA", 0.0, shape=[ncorr], valuetype="float"),
    ]
    rows_per_tile = max(1, 32768 // (nchan * ncorr))
    dminfo = {
        "*1": {
            "TYPE": "TiledColumnStMan",
            "NAME": "TiledData",
            "COLUMNS": ["DATA"],
            "SPEC": {"DEFAULTTILESHAPE": [ncorr, nchan, rows_per_tile]},
        }
    }
    if flag == "tiled":
        dminfo["*2"] = {
            "TYPE": "TiledColumnStMan",
            "NAME": "TiledFlag",
            "COLUMNS": ["FLAG"],
            "SPEC": {"DEFAULTTILESHAPE": [ncorr, nchan, rows_per_tile * 8]},
        }
    pairs = [(a, b) for a in range(nant) for b in range(a + 1, nant)]
    a1 = np.array([pairs[r % len(pairs)][0] for r in range(nrow)], np.int32)
    a2 = np.array([pairs[r % len(pairs)][1] for r in range(nrow)], np.int32)
    times = 5.0e9 + 8.0 * (np.arange(nrow) // len(pairs))
    with core_ms_write.default_ms(str(path), desc, dminfo) as t:
        t.addrows(nrow)
        t.putcolkeyword("DATA", "UNIT", "Jy")
        for start, n in flagversions.spans(nrow, 1024):
            shape = (n, nchan, ncorr)
            data = (
                rng.standard_normal(shape) + 1j * rng.standard_normal(shape)
            ).astype(np.complex64)
            t.putcol("DATA", data, start)
            t.putcol("FLAG", rng.random(shape) < 0.1, start)
            t.flush()
        t.putcol("FLAG_ROW", rng.random(nrow) < 0.05)
        t.putcol("WEIGHT", rng.uniform(0.5, 2.0, (nrow, ncorr)).astype(np.float32))
        t.putcol("SIGMA", np.ones((nrow, ncorr), np.float32))
        t.putcol("ANTENNA1", a1)
        t.putcol("ANTENNA2", a2)
        zeros = np.zeros(nrow, np.int32)
        for name in ("DATA_DESC_ID", "FIELD_ID", "ARRAY_ID", "OBSERVATION_ID"):
            t.putcol(name, zeros)
        for name in ("FEED1", "FEED2", "PROCESSOR_ID", "STATE_ID"):
            t.putcol(name, zeros)
        t.putcol("SCAN_NUMBER", zeros + 1)
        t.putcol("TIME", times)
        t.putcol("TIME_CENTROID", times)
        t.putcol("INTERVAL", np.full(nrow, 8.0))
        t.putcol("EXPOSURE", np.full(nrow, 8.0))
        uvw = rng.uniform(-4000, 4000, (nrow, 3))
        t.putcol("UVW", uvw)
    freq = 1.284e9 + 208984.375 * (np.arange(nchan) - nchan // 2)

    def sub(name, n):
        s = core_ms_write.open_table(path / name, readonly=False)
        s.addrows(n)
        return s

    with sub("SPECTRAL_WINDOW", 1) as s:
        s.putcell("CHAN_FREQ", 0, freq)
        for col in ("CHAN_WIDTH", "EFFECTIVE_BW", "RESOLUTION"):
            s.putcell(col, 0, np.full(nchan, 208984.375))
        s.putcol("REF_FREQUENCY", np.array([freq[nchan // 2]]))
        s.putcol("NUM_CHAN", np.array([nchan], np.int32))
        s.putcol("TOTAL_BANDWIDTH", np.array([208984.375 * nchan]))
        s.putcol("MEAS_FREQ_REF", np.array([5], np.int32))
        s.putcol("NAME", ["L-band"])
        s.putcol("NET_SIDEBAND", np.array([1], np.int32))
        s.putcol("FLAG_ROW", np.array([False]))
    with sub("POLARIZATION", 1) as s:
        corr = CORR4 if ncorr == 4 else CORR2
        s.putcol("NUM_CORR", np.array([ncorr], np.int32))
        s.putcell("CORR_TYPE", 0, np.array(corr, np.int32))
        prod = [[0, 0], [0, 1], [1, 0], [1, 1]] if ncorr == 4 else [[0, 0], [1, 1]]
        s.putcell("CORR_PRODUCT", 0, np.array(prod, np.int32))
        s.putcol("FLAG_ROW", np.array([False]))
    with sub("DATA_DESCRIPTION", 1) as s:
        s.putcol("SPECTRAL_WINDOW_ID", np.array([0], np.int32))
        s.putcol("POLARIZATION_ID", np.array([0], np.int32))
        s.putcol("FLAG_ROW", np.array([False]))
    return path


def sha(ms, column, chunk_rows=1024):
    """SHA-256 of a column's values (read in chunks)."""
    h = hashlib.sha256()
    with core_ms.open_table(ms) as t:
        for start, n in flagversions.spans(t.nrows, chunk_rows):
            h.update(np.ascontiguousarray(t.getcol(column, start, n)).tobytes())
    return h.hexdigest()


def hashes(ms):
    """{column: SHA-256} of every column whose cells are all defined (an
    undefined cell, as FLAG_CATEGORY usually has, is recorded as such)."""
    out = {}
    with core_ms.open_table(ms) as t:
        names = t.colnames()
    for c in names:
        try:
            out[c] = sha(ms, c)
        except OSError as e:
            out[c] = f"unreadable: {e}"
    return out


def copy_ms(src, dst):
    dst = Path(dst)
    shutil.rmtree(dst, ignore_errors=True)
    shutil.rmtree(str(dst) + ".flagversions", ignore_errors=True)
    shutil.copytree(src, dst)
    return dst


def run_writes(ms, out, seed=7, chunk_rows=48):
    """The W1 writes on `ms` (in place), recorded in `out` (npz + json):
    MODEL_DATA, CORRECTED_DATA and WEIGHT_SPECTRUM ensured (added and
    initialised where missing), then per chunk of `chunk_rows` (48: across
    the 8-row data tiles and 64-row flag tiles) MODEL_DATA = 2 DATA,
    CORRECTED_DATA = DATA where the column already existed, and seeded
    FLAG (20 %) and FLAG_ROW (10 %)."""
    ms = Path(ms)
    rng = np.random.default_rng(seed)
    before = hashes(ms)
    record = {"ms": str(ms), "before": before, "seed": seed, "chunk_rows": chunk_rows}
    with wb.WriteBack(ms, stage="w1-oracles", chunk_rows=chunk_rows) as w:
        added = {
            c: w.ensure_column(c)
            for c in ("MODEL_DATA", "CORRECTED_DATA", "WEIGHT_SPECTRUM")
        }
        nchan, ncorr = w.cell
        flags, rows = [], []
        for start, n in w.chunks():
            data = w.read("DATA", start, n)
            w.write("MODEL_DATA", start, 2 * data)
            if not added["CORRECTED_DATA"]:
                w.write("CORRECTED_DATA", start, data)
            f = rng.random((n, nchan, ncorr)) < 0.2
            r = rng.random(n) < 0.1
            w.write_flags(start, f, r)
            flags.append(f)
            rows.append(r)
    record["added"] = added
    record["flag_versions"] = flagversions.versions(ms)
    record["journal"] = wb.read_journal(ms)
    record["after"] = hashes(ms)
    np.savez_compressed(
        out,
        flag=np.concatenate(flags),
        flag_row=np.concatenate(rows),
        **{f"added_{c}": np.bool_(v) for c, v in added.items()},
    )
    Path(str(out) + ".json").write_text(json.dumps(record, indent=1, default=str))
    return record


KILL_CHILD = """
import sys, time
from rang import core_writeback as wb
ms, ready = sys.argv[1], sys.argv[2]
import numpy as np
rng = np.random.default_rng(1)
with wb.WriteBack(ms, stage="kill-test", chunk_rows=int(sys.argv[3])) as w:
    open(ready, "w").close()
    nchan, ncorr = w.cell
    for start, n in w.chunks():
        w.write_flags(start, rng.random((n, nchan, ncorr)) < 0.5, rng.random(n) < 0.5)
"""


def _casacore_reads(ms, image):
    """python-casacore (in `image`) opens `ms` and reads all of FLAG."""
    ms = Path(ms).resolve()
    code = (
        "import sys; from casacore.tables import table; "
        "t = table(sys.argv[1], ack=False); f = t.getcol('FLAG'); "
        "print(t.nrows(), f.shape)"
    )
    p = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-v",
            f"{ms.parent}:/d",
            image,
            "python",
            "-c",
            code,
            f"/d/{ms.name}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return p.returncode == 0


def kill_runs(ms, times, seed, out, casacore_image="rang-ms-reader:local"):
    """SIGKILL a FLAG-writing process at `times` points (seconds after the
    session opened, drawn from `seed` over one uninterrupted run's length),
    restore after each, record the hashes. With `casacore_image`,
    python-casacore in that image also opens the killed MS and reads FLAG."""
    ms = Path(ms)
    f0, r0 = sha(ms, "FLAG"), sha(ms, "FLAG_ROW")
    work = ms.parent / (ms.name + ".kill")
    child = ms.parent / "kill_child.py"
    child.write_text(KILL_CHILD)
    ready = ms.parent / "ready"
    rows = 256

    def start():
        ready.unlink(missing_ok=True)
        p = subprocess.Popen(
            [sys.executable, str(child), str(work), str(ready), str(rows)]
        )
        while not ready.exists():
            if p.poll() is not None:
                raise RuntimeError(
                    f"child exited {p.returncode} before the session opened"
                )
            time.sleep(0.01)
        return p, time.monotonic()

    copy_ms(ms, work)
    p, t0 = start()
    p.wait()
    length = time.monotonic() - t0
    rng = np.random.default_rng(seed)
    cases = []
    for at in sorted(rng.uniform(0.05, 0.95, times) * length):
        copy_ms(ms, work)
        p, t0 = start()
        time.sleep(max(0.0, at - (time.monotonic() - t0)))
        killed = p.poll() is None
        os.kill(p.pid, signal.SIGKILL)
        p.wait()
        case = {"at_s": round(float(at), 3), "killed_running": killed}
        with core_ms.open_table(work) as t:
            case["opens"] = t.nrows > 0
        if casacore_image:
            case["casacore_reads_flag"] = _casacore_reads(work, casacore_image)
        case["journal_state"] = (wb.read_journal(work) or {}).get("state")
        case["flag_differs"] = sha(work, "FLAG") != f0
        try:
            wb.WriteBack(work).begin().close()
            case["refused"] = False
        except wb.InterruptedWriteBack:
            case["refused"] = True
        wb.restore_flags(work)
        case["restored_equal"] = sha(work, "FLAG") == f0 and sha(work, "FLAG_ROW") == r0
        cases.append(case)
        print(json.dumps(case), flush=True)
    result = {"uninterrupted_s": round(length, 3), "chunk_rows": rows, "cases": cases}
    Path(out).write_text(json.dumps(result, indent=1))
    return result


def _vm(key):
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(key + ":"):
            return int(line.split()[1]) * 1024
    return None


def memory_run(ms, out, chunk_rows=512):
    """Peak RSS growth (VmHWM, reset through /proc/self/clear_refs) while a
    session backs up FLAG, adds CORRECTED_DATA (initialised from DATA) and
    rewrites FLAG in chunks of `chunk_rows`."""
    ms = Path(ms)
    with core_ms.open_table(ms) as t:
        nrow = t.nrows
        cell = t.getcol("DATA", 0, 1).shape[1:]
    Path("/proc/self/clear_refs").write_text("5")
    base = _vm("VmRSS")
    t0 = time.monotonic()
    with wb.WriteBack(ms, stage="memory", chunk_rows=chunk_rows) as w:
        w.ensure_column("CORRECTED_DATA")
        for start, n in w.chunks():
            f = w.read("FLAG", start, n)
            w.write_flags(start, ~f)
    wall = time.monotonic() - t0
    peak = _vm("VmHWM")
    column_bytes = nrow * int(np.prod(cell)) * 8
    chunk_bytes = chunk_rows * int(np.prod(cell)) * 8
    growth = peak - base
    result = {
        "nrows": nrow,
        "cell": list(cell),
        "chunk_rows": chunk_rows,
        "rss_before": base,
        "vmhwm_after": peak,
        "growth": growth,
        "chunk_bytes": chunk_bytes,
        "column_bytes": column_bytes,
        "bound_chunk": 4 * chunk_bytes + (64 << 20),
        "bound_quarter_column": column_bytes // 4,
        "pass": growth <= 4 * chunk_bytes + (64 << 20) and growth < column_bytes // 4,
        "wall_s_reported_not_gated": round(wall, 2),
    }
    Path(out).write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sp = p.add_subparsers(dest="cmd", required=True)
    m = sp.add_parser("make")
    m.add_argument("ms")
    m.add_argument("nrow", type=int)
    m.add_argument("nchan", type=int)
    m.add_argument("--flag", default="ssm", choices=("ssm", "tiled"))
    m.add_argument("--seed", type=int, default=20261106)
    w = sp.add_parser("write")
    w.add_argument("ms")
    w.add_argument("out")
    k = sp.add_parser("kill")
    k.add_argument("ms")
    k.add_argument("times", type=int)
    k.add_argument("seed", type=int)
    k.add_argument("out")
    c = sp.add_parser("columns")
    c.add_argument("ms")
    s = sp.add_parser("scramble")
    s.add_argument("ms")
    mem = sp.add_parser("memory")
    mem.add_argument("ms")
    mem.add_argument("out")
    r = sp.add_parser("restore")
    r.add_argument("ms")
    r.add_argument("name")
    h = sp.add_parser("hashes")
    h.add_argument("ms")
    h.add_argument("out")
    a = p.parse_args(argv)
    if a.cmd == "make":
        make_ms(a.ms, a.nrow, a.nchan, flag=a.flag, seed=a.seed)
    elif a.cmd == "write":
        run_writes(a.ms, a.out)
    elif a.cmd == "columns":
        print(wb.add_imaging_columns(a.ms, stage="columns"))
    elif a.cmd == "memory":
        memory_run(a.ms, a.out)
    elif a.cmd == "scramble":
        with wb.WriteBack(a.ms, stage="scramble", chunk_rows=48) as w:
            for start, n in w.chunks():
                f = w.read("FLAG", start, n)
                w.write_flags(start, ~f, ~w.read("FLAG_ROW", start, n))
    elif a.cmd == "restore":
        print(wb.restore_flags(a.ms, a.name))
    elif a.cmd == "hashes":
        Path(a.out).write_text(json.dumps(hashes(a.ms), indent=1))
    else:
        kill_runs(a.ms, a.times, a.seed, a.out)


if __name__ == "__main__":
    main()
