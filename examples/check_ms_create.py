"""The host checker of task E4 (research/e4-table-create.md).

    python examples/check_ms_create.py cases <oracle> <out> [<label>]
    python examples/check_ms_create.py determinism <oracle> <out>
    python examples/check_ms_create.py readback <oracle> <out>
    python examples/check_ms_create.py casa <casa-run> <out>
    python examples/check_ms_create.py apply <casa-run> <out>
    python examples/check_ms_create.py refusals <out>
    python examples/check_ms_create.py e3 <e3-oracle> <out>
    python examples/check_ms_create.py serialisation <oracle> <casa-run> <out>
    python examples/check_ms_create.py summary <out>

`cases` replays every N, R and D case of `examples/oracle_ms_create.py`
with `rang.core_ms_write` into `<out>/core[-<label>]/<case>` (R cases on
copies of casacore's own outputs, as the oracle did) with the oracle's
stored values, and compares every file with casacore's (criterion 1:
`table.lock` from offset 260; the alignment gaps of `table.fNi` masked by
the record-chain rule of the protocol, nothing else). The other steps
check criteria 2 to 8; each writes `<out>/<step>.json`; `summary` writes
`<out>/result.json`.
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

import oracle_ms_create as oracle
from rang import core, core_ms_write

LOCK_REQUESTS = 260
MS_IMAGE = "rang-ms-reader:local"
CASA_IMAGE = "rang-o-casa:6.7.6.14"
# Records no row references any more, by case: the element size of the
# column whose old value they hold (N-arrays: row 7 of VC replaced).
ORPHAN_BITS = {"N-arrays": 64, "R-add-arrays": 64}


def outputs_root():
    return (HERE.parent / "outputs").resolve()


def tree(path):
    root = Path(path)
    return {
        p.relative_to(root).as_posix(): p
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def gap_mask(table_dir, name, data, orphan_bits):
    """The alignment gaps of an array file (`table.fNi`) as a boolean mask,
    from the record chain of the oracle's copy; None if the chain does not
    walk exactly to the end of the file."""
    refs = {}
    for file, offset, bits in core.extension().ms_array_records(str(table_dir)):
        if file == name:
            refs[offset] = bits
    mask = np.zeros(len(data), bool)
    version = int.from_bytes(data[0:4], "little")
    at, end = 16, 16
    while at < len(data):
        bits = refs.get(at, orphan_bits)
        if bits is None:
            return None
        head = at + (4 if version > 0 else 0)
        ndim = int.from_bytes(data[head : head + 4], "little")
        dims = [
            int.from_bytes(data[head + 4 + 4 * i : head + 8 + 4 * i], "little")
            for i in range(ndim)
        ]
        n = int(np.prod(dims)) if dims else 1
        values = (n + 7) // 8 if bits == 1 else n * bits // 8
        end = head + 4 + 4 * ndim + values
        nxt = (end + 7) // 8 * 8
        mask[end : min(nxt, len(data))] = True
        at = nxt
    return mask if end == len(data) else None


def compare_trees(ours, theirs, orphan_bits=None):
    """Every file byte for byte; table.lock from its sync record on; the
    gaps of table.fNi masked (only when the files differ)."""
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
        if (
            file.name.startswith("table.f")
            and file.name.endswith("i")
            and len(x) == len(y)
        ):
            mask = gap_mask(b[name].parent, file.name, y, orphan_bits)
            if mask is not None and not np.any(~mask[diff]):
                entry["gap_bytes_masked"] = int(diff.size)
                out["masked"].append(entry)
                continue
        out["differ"].append(entry)
    out["identical"] = not (
        out["missing"] or out["extra"] or out["differ"] or out["masked"]
    )
    out["identical_but_gaps"] = not (out["missing"] or out["extra"] or out["differ"])
    return out


def load_values(oracle_dir, name):
    with np.load(Path(oracle_dir) / "values" / f"{name}.npz", allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def luno_path():
    return outputs_root() / "luno-solve-20261029-02" / "work.ms"


def write_json(out, step, result, started):
    result["wall_s"] = time.perf_counter() - started
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / f"{step}.json").write_text(json.dumps(result, indent=1, default=str))
    return result


# ---------------------------------------------------------------------------
# Criterion 1: the casacore cases.


def replay(oracle_dir, root):
    """Run every case with the core into `root`; (name -> wall, error)."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    sources = {"LUNO": luno_path()}
    sources.update(
        {name: Path(oracle_dir) / "casacore" / name for name, _ in oracle.CASES}
    )
    walls = {}
    for name, f in oracle.CASES:
        stored = load_values(oracle_dir, name)
        try:
            _, wall = oracle.run_case(core_ms_write, name, f, root, sources, stored)
            walls[name] = (wall, None)
        except Exception as e:  # noqa: BLE001 - recorded per case
            walls[name] = (None, f"{type(e).__name__}: {e}")
    return walls


def step_cases(oracle_dir, out, label=""):
    started = time.perf_counter()
    root = Path(out) / ("core" + (f"-{label}" if label else ""))
    walls = replay(oracle_dir, root)
    casacore_walls = {
        c["name"]: c["wall_s"]
        for c in json.loads((Path(oracle_dir) / "cases.json").read_text())
    }
    report = []
    for name, _ in oracle.CASES:
        wall, error = walls[name]
        entry = {
            "name": name,
            "core_s": wall,
            "casacore_s": casacore_walls.get(name),
            "error": error,
        }
        if error is None:
            entry.update(
                compare_trees(
                    root / name,
                    Path(oracle_dir) / "casacore" / name,
                    ORPHAN_BITS.get(name),
                )
            )
            entry["files"] = len(tree(root / name))
            entry["bytes"] = sum(p.stat().st_size for p in tree(root / name).values())
        else:
            entry["identical"] = entry["identical_but_gaps"] = False
        report.append(entry)
        state = (
            "identical"
            if entry["identical"]
            else ("gaps only" if entry["identical_but_gaps"] else "DIFFERS")
        )
        print(f"{name}: {state} {entry.get('differ', error)}", flush=True)
    result = {
        "cases": report,
        "pass": all(r["identical_but_gaps"] for r in report),
    }
    return write_json(out, "cases" + (f"-{label}" if label else ""), result, started)


def hashes(path):
    out = {}
    for name, p in tree(path).items():
        data = p.read_bytes()
        if name.endswith("table.lock"):
            data = data[LOCK_REQUESTS:]
        out[name] = hashlib.sha256(data).hexdigest()
    return out


def step_determinism(oracle_dir, out):
    """Criterion 5: two core runs and one under MALLOC_PERTURB_=85 give the
    same bytes (no mask); casacore's second and perturbed runs equal its
    first except masked gaps."""
    started = time.perf_counter()
    out = Path(out)
    runs = {}
    for label, env in (("twin", {}), ("perturb", {"MALLOC_PERTURB_": "85"})):
        cmd = [
            sys.executable,
            str(Path(__file__)),
            "cases",
            str(oracle_dir),
            str(out),
            label,
        ]
        subprocess.run(cmd, check=True, env={**os.environ, **env}, capture_output=True)
        runs[label] = out / f"core-{label}"
    core_ok = {}
    for name, _ in oracle.CASES:
        first = hashes(out / "core" / name)
        core_ok[name] = all(hashes(runs[k] / name) == first for k in runs)
    casacore = {}
    for label in ("oracle2", "oracle-perturb"):
        other = Path(oracle_dir).parent / f"{Path(oracle_dir).name}-{label}"
        if not other.exists():
            continue
        per = {}
        for name, _ in oracle.CASES:
            d = compare_trees(
                other / "casacore" / name,
                Path(oracle_dir) / "casacore" / name,
                ORPHAN_BITS.get(name),
            )
            per[name] = {
                "identical": d["identical"],
                "identical_but_gaps": d["identical_but_gaps"],
                "masked": [(m["file"], m["gap_bytes_masked"]) for m in d["masked"]],
                "differ": d["differ"],
            }
        casacore[label] = per
    result = {
        "core_identical_between_runs": core_ok,
        "casacore": casacore,
        "pass": all(core_ok.values())
        and all(
            v["identical_but_gaps"] for per in casacore.values() for v in per.values()
        ),
    }
    return write_json(out, "determinism", result, started)


# ---------------------------------------------------------------------------
# Containers.


def docker(image, args, mounts, env=None):
    """Run a container (network off, this user); mounts are (host, guest,
    mode). Returns the wall time."""
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
    ]
    if image == CASA_IMAGE:
        cmd += [
            "--tmpfs",
            "/tmp",
            "-e",
            "HOME=/tmp",
            "-e",
            "OMP_NUM_THREADS=4",
            "-w",
            "/run",
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
    return time.perf_counter() - start


def casa_ms():
    return outputs_root() / "o-casa-20261030-01" / "c.ms"


def run_mounts(run):
    return [(str(Path(run).resolve()), "/run", "rw"), (str(HERE), "/ex", "ro")]


def guest(run, path):
    return "/run/" + Path(path).resolve().relative_to(Path(run).resolve()).as_posix()


# ---------------------------------------------------------------------------
# Reads: python-casacore dumps and the core's reads.


def read_table_cells(path):
    """Every cell of every column (None: undefined) and the column info,
    read by the core without writing."""
    with core_ms_write.open_table(path) as reader:
        nrows, columns = reader.nrows, dict(reader.columns)
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
    """Two python-casacore dumps: metadata, definedness and every cell."""
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


def core_vs_dump(path, dump):
    """The core's reads of a table against python-casacore's dump."""
    cells, meta = dump
    nrows, core_cells, errors = read_table_cells(path)
    problems = [f"{k}: {v}" for k, v in errors.items()]
    if nrows != meta["nrows"]:
        problems.append(f"nrows {nrows} != {meta['nrows']}")
    for name, values in core_cells.items():
        if "error" in meta["columns"].get(name, {}):
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
                # python-casacore 3.8.1 returns uChar cells as uint16.
                uchar = value.dtype == np.uint8 and theirs.dtype == np.uint16
                if not (uchar and same_array(value.astype(np.uint16), theirs)):
                    problems.append(f"{key} differs")
    return problems


def tables_of(path):
    """A table and its subtables: (suffix, path)."""
    path = Path(path)
    return [("", path)] + [
        (f".{p.parent.name}", p.parent) for p in sorted(path.glob("*/table.dat"))
    ]


# ---------------------------------------------------------------------------
# Criterion 2: CASA's calibration tables.

CAL = {"K": "K Jones", "G": "G Jones", "B": "B Jones", "Df": "Df Jones"}


def caltable_contents(path, dump_meta):
    """The MAIN and subtable contents of a calibration table as the core
    reads them, for `create_caltable`."""
    _, main, errors = read_table_cells(path)
    if errors:
        raise RuntimeError(f"{path}: {errors}")
    subtables = {}
    for name in core_ms_write.CAL_SUBTABLES:
        _, values, errors = read_table_cells(Path(path) / name)
        if errors:
            raise RuntimeError(f"{path}/{name}: {errors}")
        subtables[name] = values
    kw = dump_meta["keywords"]
    return main, subtables, kw


def step_casa(run, out):
    """Solve K, G, B, Df with CASA (if not done), dump CASA's tables with
    python-casacore, rebuild each with `create_caltable` from the core's
    reads, compare every file (criterion 2)."""
    started = time.perf_counter()
    run, out = Path(run), Path(out)
    casa = run / "casa"
    timings = {}
    if not (casa / "x.Df").exists():
        timings["casa_solve_s"] = docker(
            CASA_IMAGE,
            [
                "sh",
                "-c",
                (
                    "rm -rf /run/casa && mkdir -p /run/casa && cp -r /o/c.ms /run/casa/x.ms && "
                    "/opt/casa/bin/python -I /ex/oracle_ms_create.py casa-solve /run/casa /run/casa/x.ms"
                ),
            ],
            run_mounts(run) + [(str(casa_ms()), "/o/c.ms", "ro")],
        )
    dumps = run / "dumps"
    pairs = [f"casa.{k}={guest(run, casa / f'x.{k}')}" for k in CAL]
    timings["dump_s"] = docker(
        MS_IMAGE,
        ["/ex/oracle_ms_create.py", "readback", guest(run, dumps), *pairs],
        run_mounts(run),
    )
    report = []
    core_cal = run / "core-cal"
    core_cal.mkdir(exist_ok=True)
    for k, vis_cal in CAL.items():
        _, meta = load_dump(dumps, f"casa.{k}")
        main, subtables, kw = caltable_contents(casa / f"x.{k}", meta)
        start = time.perf_counter()
        core_ms_write.create_caltable(
            core_cal / f"x.{k}",
            kw["VisCal"],
            main,
            subtables,
            kw["MSName"],
            kw["PolBasis"],
            kw["CASA_Version"],
            float_param=kw["ParType"] == "Float",
        )
        wall = time.perf_counter() - start
        d = compare_trees(core_cal / f"x.{k}", casa / f"x.{k}")
        d.update(
            {
                "name": f"C-{k}",
                "vis_cal": vis_cal,
                "core_s": wall,
                "files": len(tree(casa / f"x.{k}")),
            }
        )
        d["bytes"] = sum(p.stat().st_size for p in tree(casa / f"x.{k}").values())
        d["rows"] = len(main["TIME"])
        report.append(d)
        print(
            f"C-{k}: {'identical' if d['identical'] else ('gaps only' if d['identical_but_gaps'] else 'DIFFERS')} {d['differ']}",
            flush=True,
        )
    solve = (
        json.loads((casa / "casa-solve.json").read_text())
        if (casa / "casa-solve.json").exists()
        else {}
    )
    result = {
        "cases": report,
        "casa_task_s": solve,
        "timings": timings,
        "pass": all(r["identical_but_gaps"] for r in report),
    }
    return write_json(out, "casa", result, started)


# ---------------------------------------------------------------------------
# Criterion 4: CASA applies the core's tables.


def synthetic_g(run, ms):
    """A G table from the core's own seeded gains (one solution per antenna,
    reference antenna 0, a few flagged), its subtables from the MS."""
    rng = np.random.default_rng(oracle.SEED)
    _, ant, _ = read_table_cells(ms / "ANTENNA")
    _, field, _ = read_table_cells(ms / "FIELD")
    _, spw, _ = read_table_cells(ms / "SPECTRAL_WINDOW")
    _, obs, _ = read_table_cells(ms / "OBSERVATION")
    with core_ms_write.open_table(ms) as t:
        time_ = t.getcol("TIME")
        field_id = t.getcol("FIELD_ID")
    names = [str(x) for x in field["NAME"]]
    fid = names.index(oracle.FIELD)
    nant = len(ant["NAME"])
    amp = 1 + 0.2 * rng.standard_normal((nant, 2))
    phase = rng.uniform(-np.pi, np.pi, (nant, 2))
    gains = (amp * np.exp(1j * phase)).astype(np.complex64)
    gains[0] = 1  # the reference antenna
    flags = np.zeros((nant, 2), bool)
    flags[nant - 1, 1] = True
    t0 = float(np.mean(time_[field_id == fid]))
    main = {
        "TIME": [t0] * nant,
        "FIELD_ID": [fid] * nant,
        "SPECTRAL_WINDOW_ID": [0] * nant,
        "ANTENNA1": list(range(nant)),
        "ANTENNA2": [0] * nant,
        "INTERVAL": [0.0] * nant,
        "SCAN_NUMBER": [-1] * nant,
        "OBSERVATION_ID": [0] * nant,
        "CPARAM": [gains[a][None, :] for a in range(nant)],
        "PARAMERR": [np.zeros((1, 2), np.float32)] * nant,
        "FLAG": [flags[a][None, :] for a in range(nant)],
        "SNR": [np.full((1, 2), 100, np.float32)] * nant,
        "WEIGHT": [None] * nant,
    }
    keep = lambda values, name: {
        k: v for k, v in values.items() if k in core_ms_write.CAL_COLUMNS[name]
    }
    # One solution channel per window, as gaincal writes it: the mean
    # frequency and the summed width of the window's channels.
    spw = dict(spw)
    for col in ("CHAN_FREQ",):
        spw[col] = [np.array([np.mean(c)]) for c in spw[col]]
    for col in ("CHAN_WIDTH", "EFFECTIVE_BW", "RESOLUTION"):
        spw[col] = [np.array([np.sum(c)]) for c in spw[col]]
    spw["NUM_CHAN"] = [np.int32(1) for _ in spw["NUM_CHAN"]]
    subtables = {
        "ANTENNA": keep(ant, "ANTENNA"),
        "FIELD": keep(field, "FIELD"),
        "SPECTRAL_WINDOW": keep(spw, "SPECTRAL_WINDOW"),
        "OBSERVATION": keep(obs, "OBSERVATION"),
    }
    core_ms_write.create_caltable(
        run / "core-cal" / "synth.G", "G Jones", main, subtables, "synth.ms"
    )
    return gains, flags, fid


def expected_correction(data, a1, a2, gains, flags):
    """V_pq,ab / (g_p,a conj(g_q,b)) for correlations XX, XY, YX, YY; the
    correlations of a flagged solution flagged."""
    pols = [(0, 0), (0, 1), (1, 0), (1, 1)]
    out = np.empty_like(data)
    bad = np.zeros(data.shape, bool)
    for c, (a, b) in enumerate(pols):
        g = gains[a1, a] * np.conj(gains[a2, b])
        out[:, :, c] = data[:, :, c] / g[:, None]
        bad[:, :, c] = (flags[a1, a] | flags[a2, b])[:, None]
    return out, bad


def step_apply(run, out):
    started = time.perf_counter()
    run, out = Path(run), Path(out)
    apply = run / "apply"
    if apply.exists():
        shutil.rmtree(apply)
    apply.mkdir()
    gains, flags, fid = synthetic_g(run, casa_ms())
    tables = {
        "casa": [f"/run/casa/x.{k}" for k in CAL],
        "core": [f"/run/core-cal/x.{k}" for k in CAL],
        "synth": ["/run/core-cal/synth.G"],
    }
    script = " && ".join(
        f"cp -r /o/c.ms /run/apply/{name}.ms && /opt/casa/bin/python -I /ex/oracle_ms_create.py casa-apply /run/apply /run/apply/{name}.ms {' '.join(t)}"
        for name, t in tables.items()
    )
    wall = docker(
        CASA_IMAGE,
        ["sh", "-c", script],
        run_mounts(run) + [(str(casa_ms()), "/o/c.ms", "ro")],
    )
    cols = {}
    for name in tables:
        with core_ms_write.open_table(apply / f"{name}.ms") as t:
            cols[name] = {
                c: t.getcol(c)
                for c in (
                    "CORRECTED_DATA",
                    "FLAG",
                    "DATA",
                    "ANTENNA1",
                    "ANTENNA2",
                    "FIELD_ID",
                )
            }
    a, b = cols["casa"], cols["core"]
    copies = {c: same_array(a[c], b[c]) for c in ("CORRECTED_DATA", "FLAG")}
    s = cols["synth"]
    rows = s["FIELD_ID"] == fid
    exp, bad = expected_correction(
        s["DATA"][rows], s["ANTENNA1"][rows], s["ANTENNA2"][rows], gains, flags
    )
    got, flag = s["CORRECTED_DATA"][rows], s["FLAG"][rows]
    ok = ~flag & ~bad & (np.abs(exp) > 0)
    rel = np.abs(got[ok] - exp[ok]) / np.abs(exp[ok])
    synth = {
        "cells_compared": int(ok.sum()),
        "max_relative": float(rel.max()) if rel.size else None,
        "solution_flags_applied": bool(np.all(flag[bad])),
        "pass": bool(rel.size and rel.max() <= 1e-6 and np.all(flag[bad])),
    }
    result = {
        "copies_bit_identical": copies,
        "synthetic": synth,
        "apply_wall_s": wall,
        "pass": all(copies.values()) and synth["pass"],
    }
    print(json.dumps(result, indent=1), flush=True)
    return write_json(out, "apply", result, started)


# ---------------------------------------------------------------------------
# Criterion 3: read-back.


def step_readback(run, out):
    """python-casacore dumps the core's tables and the oracle's; they must
    agree, and the core must read the oracle's tables as python-casacore
    does (CASA's calibration tables included)."""
    started = time.perf_counter()
    run, out = Path(run), Path(out)
    dumps = run / "dumps"
    pairs = []
    for name, _ in oracle.CASES:
        pairs += [
            f"core.{name}={guest(run, run / 'core' / name)}",
            f"cc.{name}={guest(run, run / 'oracle' / 'casacore' / name)}",
        ]
    for k in CAL:
        pairs += [f"corecal.{k}={guest(run, run / 'core-cal' / f'x.{k}')}"]
    if not (dumps / "casa.K.json").exists():
        pairs += [f"casa.{k}={guest(run, run / 'casa' / f'x.{k}')}" for k in CAL]
    wall = docker(
        MS_IMAGE,
        ["/ex/oracle_ms_create.py", "readback", guest(run, dumps), *pairs],
        run_mounts(run),
    )
    report = {}
    groups = [
        (f"core.{n}", f"cc.{n}", run / "oracle" / "casacore" / n)
        for n, _ in oracle.CASES
    ]
    groups += [(f"corecal.{k}", f"casa.{k}", run / "casa" / f"x.{k}") for k in CAL]
    for ours, theirs, path in groups:
        for suffix, table in tables_of(path):
            a = load_dump(dumps, ours + suffix)
            b = load_dump(dumps, theirs + suffix)
            problems = compare_dumps(a, b)
            core_problems = core_vs_dump(table, b)
            report[theirs + suffix] = {
                "python_casacore_same": not problems,
                "core_reads_same": not core_problems,
                "problems": problems[:10],
                "core_problems": core_problems[:10],
                "cells": len(b[0]),
            }
    bad = {
        k: v
        for k, v in report.items()
        if not (v["python_casacore_same"] and v["core_reads_same"])
    }
    for k, v in bad.items():
        print(k, v["problems"][:3], v["core_problems"][:3])
    result = {
        "tables": len(report),
        "cells": sum(v["cells"] for v in report.values()),
        "failures": bad,
        "container_s": wall,
        "pass": not bad,
    }
    return write_json(out, "readback", result, started)


# ---------------------------------------------------------------------------
# Criterion 6: refusals.


def step_refusals(out):
    started = time.perf_counter()
    out = Path(out)
    scratch = out / "refusals"
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    pt = core_ms_write
    arr = pt.makearrcoldesc("A", 0.0, shape=[4], valuetype="float")
    var = pt.makearrcoldesc("V", 0.0, ndim=1, valuetype="float")
    sca = pt.makescacoldesc("I", 0)

    def dm(kind, cols, spec=None):
        return {"*1": {"TYPE": kind, "NAME": "X", "SPEC": spec or {}, "COLUMNS": cols}}

    attempts = {
        "IncrementalStMan": lambda p: pt.create_table(
            p, [sca], 3, dm("IncrementalStMan", ["I"])
        ),
        "MemoryStMan": lambda p: pt.create_table(p, [sca], 3, dm("MemoryStMan", ["I"])),
        "TiledDataStMan": lambda p: pt.create_table(
            p, [arr], 3, dm("TiledDataStMan", ["A"])
        ),
        "variable-shape TiledShapeStMan": lambda p: pt.create_table(
            p, [var], 3, dm("TiledShapeStMan", ["V"], {"DEFAULTTILESHAPE": [4, 8]})
        ),
        "MultiFile": lambda p: pt.create_table(p, [sca], 3, multifile=True),
        "big-endian": lambda p: pt.create_table(p, [sca], 3, endian="big"),
    }
    report = {}
    for label, f in attempts.items():
        path = scratch / label.replace(" ", "-")
        try:
            f(path).close()
            report[label] = {"refused": False}
        except Exception as e:  # noqa: BLE001 - the refusal is the result
            report[label] = {
                "refused": True,
                "names_e5": "E5" in str(e),
                "message": str(e),
                "no_table": not (path / "table.dat").exists(),
            }
    fixture = outputs_root() / "tv-caracal-wsl-20261029-01" / "original.ms"
    if fixture.exists():
        for label, op in (
            ("add rows (IncrementalStMan)", lambda t: t.addrows(1)),
            ("remove rows (IncrementalStMan)", lambda t: t.removerows([0])),
        ):
            copy = scratch / ("fixture-" + label.split()[0])
            shutil.copytree(fixture, copy)
            before = hashes(copy)
            t = pt.open_table(copy, readonly=False)
            try:
                op(t)
                report[label] = {"refused": False}
            except Exception as e:  # noqa: BLE001
                report[label] = {
                    "refused": True,
                    "names_e5": "E5" in str(e),
                    "message": str(e),
                }
            finally:
                t.close()
            after = hashes(copy)
            changed = sorted(
                k
                for k in before
                if before[k] != after.get(k)
                and not k.endswith(("table.dat", "table.lock"))
            )
            report[label]["data_files_unchanged"] = not changed
    result = {
        "attempts": report,
        "pass": all(v["refused"] and v["names_e5"] for v in report.values())
        and all(v.get("no_table", True) for v in report.values())
        and all(v.get("data_files_unchanged", True) for v in report.values()),
    }
    print(json.dumps(result, indent=1), flush=True)
    return write_json(out, "refusals", result, started)


# ---------------------------------------------------------------------------
# Criteria 7 and 8.


def step_e3(e3_oracle, out):
    """E3's checker steps cases, roundtrip and serialisation against its
    frozen oracle with the E4 writer."""
    started = time.perf_counter()
    out = Path(out) / "e3"
    if out.exists():
        shutil.rmtree(out)
    results = {}
    for step, args in (
        ("cases", [str(e3_oracle), str(out)]),
        ("roundtrip", [str(out)] + [str(outputs_root() / p) for p in E3_MSS]),
        ("serialisation", [str(out)] + [str(outputs_root() / p) for p in E3_MSS]),
    ):
        cmd = [sys.executable, str(HERE / "check_ms_writer.py"), step, *args]
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        data = (
            json.loads((out / f"{step}.json").read_text())
            if (out / f"{step}.json").exists()
            else {}
        )
        results[step] = {
            "returncode": proc.returncode,
            "stderr": proc.stderr[-2000:],
            "result": data,
        }
    cases = results["cases"]["result"].get("cases", [])
    identical = sum(1 for c in cases if c.get("identical"))
    padding = sum(
        1 for c in cases if not c.get("identical") and c.get("identical_but_padding")
    )
    result = {
        "cases_identical": identical,
        "cases_padding_only": padding,
        "roundtrip_pass": results["roundtrip"]["result"].get("pass"),
        "serialisation_pass": results["serialisation"]["result"].get("pass"),
        "details": {
            k: {"returncode": v["returncode"], "stderr": v["stderr"]}
            for k, v in results.items()
        },
    }
    result["pass"] = (
        identical == 20
        and padding == 4
        and bool(result["roundtrip_pass"])
        and bool(result["serialisation_pass"])
    )
    print(json.dumps({k: v for k, v in result.items() if k != "details"}), flush=True)
    return write_json(Path(out).parent, "e3", result, started)


E3_MSS = (
    "tv-caracal-wsl-20261029-01/original.ms",
    "luno-solve-20261029-02/work.ms",
    "tv-next-imaging-wsl-20261029-01/caracal-diagnostic.ms",
)


def step_serialisation(run, out):
    started = time.perf_counter()
    run = Path(run)
    tables = [run / "oracle" / "casacore" / n for n, _ in oracle.CASES]
    tables += [run / "casa" / f"x.{k}" for k in CAL]
    report, totals = {}, [0, 0, 0]
    for t in tables:
        n_tables, ssm, tiled, failures = core.extension().ms_serialisation_check(str(t))
        totals = [totals[0] + n_tables, totals[1] + ssm, totals[2] + tiled]
        report[t.name] = failures
    result = {
        "tables": totals[0],
        "ssm_files": totals[1],
        "tiled_headers": totals[2],
        "failures": {k: v for k, v in report.items() if v},
    }
    result["pass"] = not result["failures"]
    print(json.dumps(result), flush=True)
    return write_json(out, "serialisation", result, started)


def step_summary(out):
    out = Path(out)
    names = {
        "1 byte identity, casacore cases": "cases",
        "2 byte identity, CASA caltables": "casa",
        "3 read-back": "readback",
        "4 CASA applies the core's tables": "apply",
        "5 determinism": "determinism",
        "6 refusals": "refusals",
        "7 E3 unchanged": "e3",
        "8 serialisation identity": "serialisation",
    }
    result = {}
    for label, step in names.items():
        f = out / f"{step}.json"
        result[label] = json.loads(f.read_text()).get("pass") if f.exists() else None
    result["all_pass"] = all(v is True for v in result.values())
    (out / "result.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    return result


def main(argv):
    steps = {
        "cases": step_cases,
        "determinism": step_determinism,
        "casa": step_casa,
        "apply": step_apply,
        "readback": step_readback,
        "refusals": step_refusals,
        "e3": step_e3,
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
