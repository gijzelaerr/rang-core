"""Host checker of task DF-IO (research/dfio-formats.md).

    python examples/check_formats.py ct  <run>   # F1 CASA calibration tables
    python examples/check_formats.py qc  <run>   # F2 QuartiCal gain stores
    python examples/check_formats.py sky <run>   # F3 sky models
    python examples/check_formats.py h5  <run>   # F4 H5parm
    python examples/check_formats.py kms <run>   # F5 killMS solutions
    python examples/check_formats.py fv  <run>   # F6 CASA flag versions
    python examples/check_formats.py summary <run> [<archive.json>]

`<run>` is a fresh `outputs/dfio-<date>-NN`. Each step writes
`<run>/<step>.json` with its frozen criteria and verdicts; the containers
(`rang-o-casa:6.7.6.14`, `rang-formats-oracle:20261030`,
`rang-ms-reader:local`) run with the network off, as this user, with inputs
mounted read-only and only `<run>` writable.
"""

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

import check_ms_create as e4
from rang.formats import caltable

CASA_IMAGE = "rang-o-casa:6.7.6.14"
MS_IMAGE = "rang-ms-reader:local"
FORMATS_IMAGE = "rang-formats-oracle:20261030"
SEED = 20261030
FIELD = "J1939-6342"
CAL = ("K", "G", "B", "Df")


def outputs():
    return (ROOT / "outputs").resolve()


def casa_ms():
    return outputs() / "o-casa-20261030-01" / "c.ms"


def e4_casa():
    return outputs() / "e4-20261030-01" / "casa"


TIMINGS = []


def docker(image, args, mounts, label, env=None):
    """One container run, timed and logged in TIMINGS."""
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
    ]
    cmd += [
        "--tmpfs",
        "/tmp",
        "-e",
        "HOME=/tmp",
        "-e",
        "OMP_NUM_THREADS=4",
        "-e",
        "OPENBLAS_NUM_THREADS=1",
    ]
    for k, v in (env or {}).items():
        cmd += ["-e", f"{k}={v}"]
    for host, guest, mode in mounts:
        cmd += ["-v", f"{Path(host).resolve()}:{guest}:{mode}"]
    cmd += ["-w", "/tmp", image, *args]
    start = time.perf_counter()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    wall = time.perf_counter() - start
    TIMINGS.append(
        {
            "label": label,
            "image": image,
            "wall_s": round(wall, 2),
            "code": proc.returncode,
        }
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"{label} failed: {proc.stdout[-3000:]}\n{proc.stderr[-3000:]}"
        )
    return proc.stdout


def mounts(run, *extra):
    return [(run, "/run", "rw"), (HERE, "/ex", "ro"), *extra]


def guest(run, path):
    return "/run/" + Path(path).resolve().relative_to(Path(run).resolve()).as_posix()


def write_json(run, step, result, started):
    result["wall_s"] = time.perf_counter() - started
    result["timings"] = list(TIMINGS)
    TIMINGS.clear()
    (Path(run) / f"{step}.json").write_text(json.dumps(result, indent=1, default=str))
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "timings"}, indent=1, default=str
        )[:6000]
    )
    return result


def rel_error(got, exp, ok):
    ok = ok & (np.abs(exp) > 0)
    if not ok.any():
        return None, 0
    rel = np.abs(got[ok] - exp[ok]) / np.abs(exp[ok])
    return float(rel.max()), int(ok.sum())


def ms_columns(
    ms,
    names=(
        "DATA",
        "CORRECTED_DATA",
        "FLAG",
        "TIME",
        "ANTENNA1",
        "ANTENNA2",
        "FIELD_ID",
    ),
):
    from rang import core_ms

    with core_ms.open_table(ms) as t:
        return {c: t.getcol(c) for c in names}


def ms_frequencies(ms):
    from rang import core_ms

    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as t:
        return t.getcol("CHAN_FREQ")[0]


def field_index(ms, name=FIELD):
    from rang import core_ms

    with core_ms.open_table(Path(ms) / "FIELD") as t:
        return [str(x) for x in t.getcol("NAME")].index(name)


# ---------------------------------------------------------------------------
# F1: CASA calibration tables.


def _norm_keywords(kw):
    return {
        k: (
            ("Table: " + Path(v[7:]).name)
            if isinstance(v, str) and v.startswith("Table: ")
            else v
        )
        for k, v in kw.items()
    }


def ct_read_check(path, dumps, label):
    """CT-read: the core's CalTable against python-casacore's dump."""
    ct = caltable.read(path)
    problems = []
    for suffix, cells in [("", ct.main)] + [
        (f".{n}", ct.subtables[n]) for n in ct.subtables
    ]:
        dump = e4.load_dump(dumps, label + suffix)
        theirs, meta = dump
        if len(next(iter(cells.values()), [])) != meta["nrows"] and cells:
            problems.append(f"{suffix}: nrows")
        for name, values in cells.items():
            for row, value in enumerate(values):
                key = f"{name}/{row}"
                if value is None:
                    if key in theirs:
                        problems.append(f"{suffix}{key} undefined in the core")
                elif key not in theirs:
                    problems.append(f"{suffix}{key} undefined in casacore")
                elif not e4.same_array(value, theirs[key]):
                    a, b = np.asarray(value), np.asarray(theirs[key])
                    if not (
                        a.dtype == np.uint8
                        and b.dtype == np.uint16
                        and e4.same_array(a.astype(np.uint16), b)
                    ):
                        problems.append(f"{suffix}{key} differs")
        if suffix == "":
            if _norm_keywords(meta["keywords"]) != _norm_keywords(ct.keywords):
                problems.append(f"keywords differ: {meta['keywords']} vs {ct.keywords}")
            info = meta["info"]
            if [
                info.get("type", ""),
                info.get("subType", ""),
                info.get("readme", ""),
            ] != ct.info:
                problems.append(f"info differs: {info} vs {ct.info}")
    return ct, problems


def seeded_tables(ms, nant, times, freqs, fid):
    """CT-synthetic: G (several solutions), B (per channel), K, T from the
    core's seeded gains; subtables from the MS."""
    rng = np.random.default_rng(SEED)
    single = caltable.subtables_from_ms(ms, single_channel=True)
    full = caltable.subtables_from_ms(ms, single_channel=False)
    ants = list(range(nant))
    nt = 4
    t_sol = np.linspace(times.min(), times.max(), nt)
    g = (1 + 0.2 * rng.standard_normal((nt, nant, 1, 2))) * np.exp(
        1j * rng.uniform(-np.pi, np.pi, (nt, nant, 1, 2))
    )
    g[:, 0] = 1
    gflag = np.zeros(g.shape, bool)
    gflag[1, nant - 1, 0, 1] = True
    gflag[3, 1, 0, 0] = True
    nchan = len(freqs)
    b = (1 + 0.1 * rng.standard_normal((1, nant, nchan, 2))) * np.exp(
        1j * 0.3 * rng.standard_normal((1, nant, nchan, 2))
    )
    bflag = np.zeros(b.shape, bool)
    bflag[0, 2, 100:140, :] = True
    k = rng.normal(0, 2.0, (1, nant, 1, 2))
    k[:, 0] = 0
    tt = np.exp(1j * rng.uniform(-np.pi, np.pi, (nt, nant, 1, 1)))
    tt[:, 0] = 1
    t_mid = [float(np.mean(times))]
    common = {"field_id": fid, "refant": 0, "ms_name": "c.ms"}
    return {
        "G": caltable.from_gains(
            "G", t_sol, ants, g, gflag, subtables=single, interval=120.0, **common
        ),
        "B": caltable.from_gains("B", t_mid, ants, b, bflag, subtables=full, **common),
        "K": caltable.from_gains("K", t_mid, ants, k, subtables=single, **common),
        "T": caltable.from_gains(
            "T", t_sol, ants, tt, subtables=single, interval=120.0, **common
        ),
    }


def step_ct(run):
    started = time.perf_counter()
    run = Path(run)
    casa = run / "ct" / "casa"
    casa.mkdir(parents=True, exist_ok=True)
    src = e4_casa()
    # The T table, made now by CASA (protocol F1).
    if not (casa / "x.T").exists():
        docker(
            CASA_IMAGE,
            [
                "sh",
                "-c",
                "cp -r /o/c.ms /tmp/x.ms && /opt/casa/bin/python -I /ex/oracle_formats.py casa-t /run/ct/casa/x.T /tmp/x.ms /e4/x.K",
            ],
            mounts(run, (casa_ms(), "/o/c.ms", "ro"), (src, "/e4", "ro")),
            "casa gaincal T",
        )
    tables = {k: src / f"x.{k}" for k in CAL}
    tables["T"] = casa / "x.T"
    # CT-read: python-casacore 3.8.1 dumps.
    dumps = run / "ct" / "dumps"
    pairs = []
    for k, p in tables.items():
        pairs.append(f"casa.{k}=" + ("/e4/" + p.name if k != "T" else guest(run, p)))
    docker(
        MS_IMAGE,
        ["/ex/oracle_ms_create.py", "readback", guest(run, dumps), *pairs],
        mounts(run, (src, "/e4", "ro")),
        "python-casacore dumps",
    )
    read_result, read_tables = {}, {}
    for k, p in tables.items():
        start = time.perf_counter()
        ct, problems = ct_read_check(p, dumps, f"casa.{k}")
        read_tables[k] = ct
        read_result[k] = {
            "problems": problems[:20],
            "pass": not problems,
            "read_s": time.perf_counter() - start,
            "summary": ct.summary(),
        }
    # CT-write-identity: write each read table back, byte rule.
    core_dir = run / "ct" / "core"
    core_dir.mkdir(exist_ok=True)
    identity = {}
    for k, ct in read_tables.items():
        out = core_dir / f"x.{k}"
        if out.exists():
            shutil.rmtree(out)
        start = time.perf_counter()
        caltable.write(ct, out)
        wall = time.perf_counter() - start
        d = e4.compare_trees(out, tables[k])
        identity[k] = {
            "identical_but_gaps": bool(d["identical_but_gaps"]),
            "identical": bool(d["identical"]),
            "differ": d["differ"][:10],
            "write_s": wall,
        }
    # Synthetic tables from the core's gains.
    ms = casa_ms()
    cols = ms_columns(ms)
    fid = field_index(ms)
    freqs = ms_frequencies(ms)
    rows = cols["FIELD_ID"] == fid
    nant = int(max(cols["ANTENNA1"].max(), cols["ANTENNA2"].max())) + 1
    synth = seeded_tables(ms, nant, cols["TIME"][rows], freqs, fid)
    synth_dir = run / "ct" / "synth"
    synth_dir.mkdir(exist_ok=True)
    for k, ct in synth.items():
        out = synth_dir / f"s.{k}"
        if out.exists():
            shutil.rmtree(out)
        caltable.write(ct, out)
    # applycal cases: identity pairs, each CASA type alone and the chain,
    # each synthetic type alone and G+B+K.
    cases = {
        "copy-casa": [f"/e4/x.{k}" for k in CAL],
        "copy-core": [f"/run/ct/core/x.{k}" for k in CAL],
        "copy-casa-T": ["/run/ct/casa/x.T"],
        "copy-core-T": ["/run/ct/core/x.T"],
    }
    for k in CAL:
        cases[f"casa-{k}"] = [f"/e4/x.{k}"]
    cases["casa-T"] = ["/run/ct/casa/x.T"]
    cases["casa-chain"] = [f"/e4/x.{k}" for k in CAL]
    for k in synth:
        cases[f"synth-{k}"] = [f"/run/ct/synth/s.{k}"]
    cases["synth-chain"] = [f"/run/ct/synth/s.{k}" for k in ("G", "B", "K")]
    apply_dir = run / "ct" / "apply"
    if apply_dir.exists():
        shutil.rmtree(apply_dir)
    apply_dir.mkdir()
    script = " && ".join(
        f"cp -r /o/c.ms /run/ct/apply/{name}.ms && /opt/casa/bin/python -I /ex/oracle_ms_create.py casa-apply /run/ct/apply /run/ct/apply/{name}.ms {' '.join(t)}"
        for name, t in cases.items()
    )
    docker(
        CASA_IMAGE,
        ["sh", "-c", script],
        mounts(run, (ms, "/o/c.ms", "ro"), (src, "/e4", "ro")),
        f"casa applycal x{len(cases)}",
    )
    applied = {name: ms_columns(apply_dir / f"{name}.ms") for name in cases}
    copies = {}
    for a, b in (("copy-casa", "copy-core"), ("copy-casa-T", "copy-core-T")):
        copies[b] = {
            c: e4.same_array(applied[a][c], applied[b][c])
            for c in ("CORRECTED_DATA", "FLAG")
        }
    semantics = {}
    lookup = dict(read_tables)
    lookup.update({f"s.{k}": v for k, v in synth.items()})
    for name, paths in cases.items():
        if name.startswith("copy"):
            continue
        tabs = [
            lookup[Path(p).name[2:]]
            if p.startswith("/e4") or "/casa/" in p
            else lookup[Path(p).name]
            for p in paths
        ]
        c = applied[name]
        sel = c["FIELD_ID"] == fid
        start = time.perf_counter()
        exp, eflag = caltable.correct(
            c["DATA"][sel],
            cols["FLAG"][sel],
            c["TIME"][sel],
            c["ANTENNA1"][sel],
            c["ANTENNA2"][sel],
            freqs,
            tabs,
            field_id=fid,
        )
        wall = time.perf_counter() - start
        got, gflag = c["CORRECTED_DATA"][sel], c["FLAG"][sel]
        ok = ~gflag & ~eflag
        worst, n = rel_error(got, exp, ok)
        # Reported, not gated (added post hoc after run -01): the error in
        # float32 epsilons of the cell's largest correlation, which is the
        # scale of CASA's float32 arithmetic when a result cancels.
        scale = np.max(np.abs(exp), axis=-1, keepdims=True) * np.finfo(np.float32).eps
        ulps = np.abs(got - exp) / np.where(scale > 0, scale, 1)
        eps_scaled = float(ulps[ok].max()) if ok.any() else None
        flags_applied = (
            bool(np.all(gflag[eflag & ~cols["FLAG"][sel]])) if eflag.any() else True
        )
        flags_equal = bool(np.array_equal(gflag, eflag | cols["FLAG"][sel]))
        semantics[name] = {
            "tables": paths,
            "cells": n,
            "max_relative": worst,
            "cells_above_1e-6": int(
                np.sum((np.abs(got - exp) > 1e-6 * np.abs(exp)) & ok)
            ),
            "max_error_float32_eps_of_cell": eps_scaled,
            "solution_flags_applied": flags_applied,
            "flags_equal": flags_equal,
            "core_correct_s": wall,
            "pass": bool(worst is not None and worst <= 1e-6 and flags_applied),
        }
    result = {
        "read": read_result,
        "write_identity": identity,
        "apply_copies_bit_identical": copies,
        "semantics": semantics,
        "verdicts": {
            "CT-read": all(r["pass"] for r in read_result.values()),
            "CT-write-identity": all(i["identical_but_gaps"] for i in identity.values())
            and all(all(v.values()) for v in copies.values()),
            "CT-semantics": all(
                s["pass"] for n, s in semantics.items() if n.startswith("casa")
            ),
            "CT-synthetic": all(
                s["pass"] for n, s in semantics.items() if n.startswith("synth")
            ),
        },
    }
    return write_json(run, "ct", result, started)


# ---------------------------------------------------------------------------
# F2: QuartiCal gain stores.


def luno():
    return outputs() / "luno-solve-20261029-02"


def qc_dump_compare(terms, dump):
    """QC-read: the core's store against `xds_from_zarr`'s dump."""
    arrays, meta = dump
    problems = []
    for term, parts in terms.items():
        for i, part in enumerate(parts):
            key = f"{term}/{i}"
            if key not in meta:
                problems.append(f"{key} missing in the dump")
                continue
            names = set(meta[key]["vars"])
            if names != set(part.variables):
                problems.append(
                    f"{key}: variables {sorted(names ^ set(part.variables))}"
                )
            for name in names & set(part.variables):
                theirs = arrays[f"{key}/{name}"]
                ours = part[name]
                if ours.dtype.kind == "U" or theirs.dtype.kind == "U":
                    same = ours.shape == theirs.shape and [
                        str(x) for x in ours.ravel()
                    ] == [str(x) for x in theirs.ravel()]
                else:
                    same = e4.same_array(ours, theirs)
                if not same:
                    problems.append(
                        f"{key}/{name} differs ({ours.dtype}{ours.shape} vs {theirs.dtype}{theirs.shape})"
                    )
                if list(part.variables[name].dims) != meta[key]["vars"][name]["dims"]:
                    problems.append(f"{key}/{name} dims differ")
            ours_attrs = {
                k: v for k, v in part.attrs.items() if k != "__daskms_zarr_attr__"
            }
            theirs_attrs = {
                k: v
                for k, v in meta[key]["attrs"].items()
                if k != "__daskms_zarr_attr__"
            }
            if json.loads(json.dumps(ours_attrs)) != theirs_attrs:
                problems.append(f"{key} attrs differ: {ours_attrs} vs {theirs_attrs}")
    return problems


def load_qc_dump(path):
    with np.load(path, allow_pickle=False) as z:
        arrays = {k: z[k] for k in z.files}
    return arrays, json.loads(Path(str(path) + ".json").read_text())


def metadata_identity(ours, theirs):
    """Every metadata file (.zarray, .zattrs, .zgroup, .zmetadata) of two
    stores byte for byte; chunk files are not compared (memcpyed blosc
    frames against lz4)."""
    names = lambda root: {p.relative_to(root).as_posix() for p in root.rglob(".z*")}
    a, b = names(Path(ours)), names(Path(theirs))
    differ = sorted(
        n
        for n in a & b
        if (Path(ours) / n).read_bytes() != (Path(theirs) / n).read_bytes()
    )
    return {
        "files": len(a | b),
        "only_one_side": sorted(a ^ b),
        "differ": differ,
        "identical": not differ and a == b,
    }


def bins(values, per):
    """Solution-interval index of each value (sorted unique values, `per`
    consecutive values per interval; QuartiCal's integer intervals)."""
    u = np.unique(values)
    return (np.searchsorted(u, values) // per).astype(int)


def step_qc(run):
    from rang.formats import quartical_store as qs

    started = time.perf_counter()
    run = Path(run)
    qc = run / "qc"
    qc.mkdir(parents=True, exist_ok=True)
    src = luno()
    m = mounts(
        run,
        (src / "work.ms", "/o/work.ms", "ro"),
        (src / "solve" / "gains.qc", "/o/gains.qc", "ro"),
    )
    py = "/opt/qc/bin/python -I /ex/oracle_formats.py"
    # The parametrised (delay) store, made now by QuartiCal on a copy.
    if not (qc / "delay" / "gains.qc").exists():
        docker(
            FORMATS_IMAGE,
            [
                "sh",
                "-c",
                f"cp -r /o/work.ms /tmp/w.ms && {py} qc-delay /tmp/w.ms /run/qc/delay",
            ],
            m,
            "quartical delay solve",
        )
    stores = {
        "archived": src / "solve" / "gains.qc",
        "delay": qc / "delay" / "gains.qc",
    }
    guests = {"archived": "/o/gains.qc", "delay": "/run/qc/delay/gains.qc"}
    # The core's reads and rewrites.
    reads, rewrites = {}, {}
    for name, path in stores.items():
        start = time.perf_counter()
        reads[name] = qs.read(path)
        read_s = time.perf_counter() - start
        out = qc / f"core-{name}.qc"
        if out.exists():
            shutil.rmtree(out)
        start = time.perf_counter()
        qs.write(reads[name], out)
        rewrites[name] = {"read_s": read_s, "write_s": time.perf_counter() - start}
    # A store from seeded gains on the archived grid.
    rng = np.random.default_rng(SEED)
    base = reads["archived"]["G"][0]
    nt, nf, na, nd = base["gains"].shape[:4]
    g = np.zeros((nt, nf, na, nd, 2, 2), complex)
    g[..., 0, 0] = (1 + 0.1 * rng.standard_normal((nt, nf, na, nd))) * np.exp(
        1j * rng.uniform(-np.pi, np.pi, (nt, nf, na, nd))
    )
    g[..., 1, 1] = (1 + 0.1 * rng.standard_normal((nt, nf, na, nd))) * np.exp(
        1j * rng.uniform(-np.pi, np.pi, (nt, nf, na, nd))
    )
    g[..., 0, 1] = 0.05 * (
        rng.standard_normal((nt, nf, na, nd))
        + 1j * rng.standard_normal((nt, nf, na, nd))
    )
    g[..., 1, 0] = 0.05 * (
        rng.standard_normal((nt, nf, na, nd))
        + 1j * rng.standard_normal((nt, nf, na, nd))
    )
    seeded = qs.complex_partition(
        g,
        np.zeros((nt, nf, na, nd), bool),
        base["gain_time"],
        base["gain_freq"],
        base["antenna"],
        field_id=base.attrs["FIELD_ID"],
        field_name=base.attrs["FIELD_NAME"],
        scan=base.attrs["SCAN_NUMBER"],
        ddid=base.attrs["DATA_DESC_ID"],
    )
    if (qc / "core-seeded.qc").exists():
        shutil.rmtree(qc / "core-seeded.qc")
    qs.write({"G": [seeded]}, qc / "core-seeded.qc")
    # Dumps by xds_from_zarr of every store.
    dumps = qc / "dumps"
    dumps.mkdir(exist_ok=True)
    targets = {
        **guests,
        "core-archived": "/run/qc/core-archived.qc",
        "core-delay": "/run/qc/core-delay.qc",
        "core-seeded": "/run/qc/core-seeded.qc",
    }
    script = " && ".join(
        f"{py} qc-dump {p} /run/qc/dumps/{n}.npz" for n, p in targets.items()
    )
    docker(FORMATS_IMAGE, ["sh", "-c", script], m, "xds_from_zarr dumps x5")
    read_check = {
        n: qc_dump_compare(reads[n], load_qc_dump(dumps / f"{n}.npz")) for n in stores
    }
    seeded_check = qc_dump_compare(
        {"G": [seeded]}, load_qc_dump(dumps / "core-seeded.npz")
    )
    rewrite_check = {}
    for n, path in stores.items():
        a, b = load_qc_dump(dumps / f"{n}.npz"), load_qc_dump(dumps / f"core-{n}.npz")
        same = set(a[0]) == set(b[0]) and all(
            (
                a[0][k].dtype.kind in "U"
                and [str(x) for x in a[0][k].ravel()]
                == [str(x) for x in b[0][k].ravel()]
            )
            or e4.same_array(a[0][k], b[0][k])
            for k in a[0]
        )
        rewrite_check[n] = {
            "xds_equal": bool(same and a[1] == b[1]),
            "metadata": metadata_identity(qc / f"core-{n}.qc", path),
            **rewrites[n],
        }
    # QuartiCal applies each store (load_from, no iterations).
    apply = qc / "apply"
    if apply.exists():
        shutil.rmtree(apply)
    apply.mkdir()
    cases = {
        "archived": ("/o/gains.qc", "G", "complex", "2", "32"),
        "core-archived": ("/run/qc/core-archived.qc", "G", "complex", "2", "32"),
        "core-seeded": ("/run/qc/core-seeded.qc", "G", "complex", "2", "32"),
        "delay": ("/run/qc/delay/gains.qc", "K", "delay", "2", "0"),
        "core-delay": ("/run/qc/core-delay.qc", "K", "delay", "2", "0"),
    }
    script = " && ".join(
        f"cp -r /o/work.ms /run/qc/apply/{n}.ms && {py} qc-apply /run/qc/apply/{n}.ms {s} {t} /run/qc/apply/{n} {k} {ti} {fi}"
        for n, (s, t, k, ti, fi) in cases.items()
    )
    docker(FORMATS_IMAGE, ["sh", "-c", script], m, "quartical load_from apply x5")
    cols = {
        n: ms_columns(
            apply / f"{n}.ms",
            ("DATA", "CORRECTED_DATA", "FLAG", "TIME", "ANTENNA1", "ANTENNA2"),
        )
        for n in cases
    }
    applied = {
        "core-archived": e4.same_array(
            cols["archived"]["CORRECTED_DATA"], cols["core-archived"]["CORRECTED_DATA"]
        ),
        "core-delay": e4.same_array(
            cols["delay"]["CORRECTED_DATA"], cols["core-delay"]["CORRECTED_DATA"]
        ),
    }
    # The core's correction with the seeded gains.
    c = cols["core-seeded"]
    tb = bins(c["TIME"], 2)
    fb = np.arange(c["DATA"].shape[1]) // 32
    gp = g[tb[:, None], fb[None, :], c["ANTENNA1"][:, None], 0]
    gq = g[tb[:, None], fb[None, :], c["ANTENNA2"][:, None], 0]
    v = c["DATA"].reshape(c["DATA"].shape[:2] + (2, 2)).astype(complex)
    exp = np.linalg.inv(gp) @ v @ np.conj(np.swapaxes(np.linalg.inv(gq), -1, -2))
    exp = exp.reshape(c["DATA"].shape)
    worst, n = rel_error(c["CORRECTED_DATA"], exp, ~c["FLAG"])
    seeded_apply = {
        "cells": n,
        "max_relative": worst,
        "pass": bool(worst is not None and worst <= 1e-6),
    }
    result = {
        "read": {k: {"problems": v[:20], "pass": not v} for k, v in read_check.items()},
        "seeded_store_read_by_daskms": {
            "problems": seeded_check[:20],
            "pass": not seeded_check,
        },
        "rewrite": rewrite_check,
        "apply_bit_identical": applied,
        "seeded_apply": seeded_apply,
        "summary": {k: qs.summary(v) for k, v in reads.items()},
        "verdicts": {
            "QC-read": all(not v for v in read_check.values()),
            "QC-write-a": all(
                r["xds_equal"] and r["metadata"]["identical"]
                for r in rewrite_check.values()
            ),
            "QC-write-b": all(applied.values()),
            "QC-write-c": seeded_apply["pass"] and not seeded_check,
        },
    }
    return write_json(run, "qc", result, started)


# ---------------------------------------------------------------------------
# F3: sky models.

LSM = "l1m-20261030-00-fieldmodel/pks1934-638.lsm"
LSM_SHA256 = "0964b9f4c547bb802bfb16a2e8fdccddff84beeec05b6f3492521a46fa77d101"
DDF_RUN = "ddfacet-feasibility-20261030-01/runs/clean-hmp"


def ulps(a, b):
    a, b = float(a), float(b)
    if a == b:
        return 0
    return abs(int(np.float64(a).view(np.int64)) - int(np.float64(b).view(np.int64)))


def compare_tigger(
    sources, dump, angle_ulps=0, fields=("i", "q", "u", "v", "freq0", "spi", "shape")
):
    """Core sources against a Tigger dump: names and every value; angles
    may differ by `angle_ulps` (reported)."""
    problems, worst = [], 0
    theirs = dump["sources"]
    if [s.name for s in sources] != [d["name"] for d in theirs]:
        return ["names or order differ"], None
    for s, d in zip(sources, theirs):
        for key in ("ra", "dec"):
            u = ulps(getattr(s, key), float(d[key]))
            worst = max(worst, u)
            if u > angle_ulps:
                problems.append(f"{s.name} {key} {u} ulp")
        for key in ("i", "q", "u", "v"):
            if key in fields and float(getattr(s, key)) != float(d[key]):
                problems.append(f"{s.name} {key}")
        if "freq0" in fields and s.spi and float(d["freq0"]) != float(s.freq0):
            problems.append(f"{s.name} freq0")
        flat = not s.spi and d["spi"] in ([], ["0.0"], ["0"])
        if (
            "spi" in fields
            and tuple(float(x) for x in d["spi"]) != tuple(s.spi)
            and not flat
        ):
            problems.append(f"{s.name} spi {d['spi']} vs {s.spi}")
        if "shape" in fields:
            shape = None if not s.gaussian else [s.emaj, s.emin, s.pa]
            got = None if d["shape"] is None else [float(x) for x in d["shape"]]
            if shape != got:
                problems.append(f"{s.name} shape {got} vs {shape}")
    return problems, worst


def compare_sources(a, b, angle_tol=0.0, shape_rel=0.0):
    problems = []
    if [s.name for s in a] != [s.name for s in b]:
        return ["names or order differ"]
    for s, t in zip(a, b):
        for key in ("ra", "dec"):
            if abs(getattr(s, key) - getattr(t, key)) > angle_tol:
                problems.append(
                    f"{s.name} {key} {getattr(s, key) - getattr(t, key):.3g}"
                )
        for key in ("i", "q", "u", "v"):
            if float(getattr(s, key)) != float(getattr(t, key)):
                problems.append(f"{s.name} {key}")
        if tuple(s.spi) != tuple(t.spi) or (s.spi and s.freq0 != t.freq0):
            problems.append(f"{s.name} spectrum")
        for key in ("emaj", "emin", "pa"):
            x, y = getattr(s, key), getattr(t, key)
            if abs(x - y) > shape_rel * max(abs(x), abs(y)):
                problems.append(f"{s.name} {key} {x} vs {y}")
    return problems


def step_sky(run):
    import oracle_formats
    from rang import core, core_ms
    from rang.formats import sky

    started = time.perf_counter()
    run = Path(run)
    d = run / "sky"
    d.mkdir(parents=True, exist_ok=True)
    lsm_path = outputs() / LSM
    sha = e4.hashlib.sha256(lsm_path.read_bytes()).hexdigest()
    if sha != LSM_SHA256:
        raise SystemExit(f"CARACal lsm SHA256 {sha} != {LSM_SHA256}")
    sources = sky.load(lsm_path)
    # The core writes the model in each format.
    (d / "core.lsm.html").write_text(sky.dumps_html(sources, freq0=1.3e9))
    (d / "core.txt").write_text(sky.dumps_ascii(sources))
    (d / "core.wsclean.txt").write_text(sky.dumps_wsclean(sources))
    py = "/opt/sky/bin/python -I /ex/oracle_formats.py"
    tc = "/opt/sky/bin/tigger-convert -f"
    m = mounts(run, (lsm_path, "/o/m.lsm", "ro"), (casa_ms(), "/o/c.ms", "ro"))
    script = " && ".join(
        [
            f"{py} tigger-dump /o/m.lsm /run/sky/tigger-of-lsm.json",
            f"{py} tigger-dump /run/sky/core.lsm.html /run/sky/tigger-of-core-html.json",
            f"{py} tigger-dump /run/sky/core.txt /run/sky/tigger-of-core-ascii.json",
            f"{tc} /run/sky/core.lsm.html /run/sky/t.lsm.html > /run/sky/convert.log 2>&1",
            f"PYTHONHASHSEED=0 {tc} /run/sky/t.lsm.html /run/sky/t2.lsm.html >> /run/sky/convert.log 2>&1",
            f"{tc} /run/sky/core.lsm.html /run/sky/t.txt >> /run/sky/convert.log 2>&1",
            f"PYTHONHASHSEED=0 {tc} /o/m.lsm /run/sky/tigger-own.lsm.html >> /run/sky/convert.log 2>&1",
            f"{tc} -o BBS /o/m.lsm /run/sky/t.cat >> /run/sky/convert.log 2>&1",
            f"{py} tigger-dump /run/sky/t.cat /run/sky/tigger-of-bbs.json",
            f"{py} wsclean-dump /run/sky/core.wsclean.txt /run/sky/africanus-of-core.json",
            f"cp -r /o/c.ms /run/sky/cb.ms && {py} crystalball /run/sky/cb.ms /run/sky/core.wsclean.txt",
        ]
    )
    docker(
        FORMATS_IMAGE, ["sh", "-c", script], m, "tigger-convert, africanus, crystalball"
    )
    # WSClean 3.7 writes a source list of its own.
    if not (d / "ws-sources.txt").exists():
        docker(
            CASA_IMAGE,
            [
                "sh",
                "-c",
                "cp -r /o/c.ms /tmp/w.ms && /usr/bin/python3 -I /ex/oracle_formats.py wsclean-list /tmp/w.ms /run/sky/ws",
            ],
            m,
            "wsclean -save-source-list",
        )
    docker(
        FORMATS_IMAGE,
        [
            "sh",
            "-c",
            f"{py} wsclean-dump /run/sky/ws-sources.txt /run/sky/africanus-of-wsclean.json",
        ],
        m,
        "africanus load of the WSClean list",
    )

    def load(name):
        return json.loads((d / name).read_text())

    res = {}
    p, worst = compare_tigger(sources, load("tigger-of-lsm.json"), angle_ulps=4)
    res["SKY-tigger-read"] = {
        "problems": p[:20],
        "max_angle_ulps": worst,
        "pass": not p,
    }
    p1, w1 = compare_tigger(sources, load("tigger-of-core-html.json"))
    t_html = sky.load_html(d / "t.lsm.html")
    p2 = compare_sources(sources, t_html.sources)
    own = (d / "tigger-own.lsm.html").read_text()
    ours = (d / "core.lsm.html").read_text()
    res["SKY-html"] = {
        "tigger_loads_core": {"problems": p1[:20], "max_angle_ulps": w1},
        "core_reads_tigger_convert": {"problems": p2[:20]},
        "pass": not p1 and not p2,
        "reported": {
            "tigger_fixed_point_hashseed0": (d / "t.lsm.html").read_text()
            == (d / "t2.lsm.html").read_text(),
            "core_html_equals_tigger_html_of_lsm": ours == own,
            "lines_differing_from_tigger_html_of_lsm": sum(
                1 for x, y in zip(ours.splitlines(), own.splitlines()) if x != y
            ),
        },
    }
    p1, _ = compare_tigger(sources, load("tigger-of-core-ascii.json"))
    try:
        p2 = compare_sources(sources, sky.load(d / "t.txt"))
    except ValueError as err:
        p2 = [f"core cannot read tigger-convert's ASCII: {err}"]
    res["SKY-ascii"] = {
        "tigger_loads_core": {"problems": p1[:20]},
        "core_reads_tigger_ascii": {"problems": p2[:20]},
        "pass": not p1 and not p2,
    }
    # WSClean text: africanus' read of the core's list.
    af = load("africanus-of-core.json")
    core_back = sky.load_wsclean(d / "core.wsclean.txt")
    p = []
    for k, s in enumerate(sources):
        if af["Name"][k] != s.name:
            p.append(f"name {k}")
            continue
        for key, val in (("Ra", s.ra), ("Dec", s.dec)):
            if abs(float(af[key][k]) - val) > 1e-12:
                p.append(f"{s.name} {key} {float(af[key][k]) - val:.3g}")
        spi = [float(x) for x in af["SpectralIndex"][k]]
        while spi and spi[-1] == 0.0:  # the writer pads with zero terms
            spi.pop()
        if float(af["I"][k]) != s.i or spi != list(s.spi):
            p.append(f"{s.name} I or SpectralIndex")
        if s.spi and float(af["ReferenceFrequency"][k]) != s.freq0:
            p.append(f"{s.name} ReferenceFrequency")
        if af["LogarithmicSI"][k] is not True:
            p.append(f"{s.name} LogarithmicSI")
        if s.gaussian:
            for key, val in (
                ("MajorAxis", s.emaj),
                ("MinorAxis", s.emin),
                ("Orientation", s.pa),
            ):
                if float(af[key][k]) != val:
                    p.append(f"{s.name} {key} {float(af[key][k]) - val:.3g}")
    p_back = compare_sources(sources, core_back, angle_tol=1e-12, shape_rel=0.0)
    # Crystalball against the core's prediction (field J1939-6342).
    cb = ms_columns(d / "cb.ms", ("MODEL_DATA", "UVW", "FIELD_ID", "FLAG"))
    fid = field_index(casa_ms())
    with core_ms.open_table(casa_ms() / "FIELD") as t:
        ra0, dec0 = t.getcol("PHASE_DIR")[fid, 0]
    freqs = ms_frequencies(casa_ms())
    rows = cb["FIELD_ID"] == fid
    comp = sky.components(sources, (ra0, dec0))
    start = time.perf_counter()
    vis = core.predict_components(cb["UVW"][rows], freqs, **comp)
    predict_s = time.perf_counter() - start
    v_core = vis.astype(np.complex64)
    model = cb["MODEL_DATA"][rows]
    flux_sum = np.sum(np.abs([s.flux(freqs) for s in sources]), axis=0)
    bound = 2.0**-22 * flux_sum
    dxx = np.abs(v_core - model[..., 0])
    dyy = np.abs(v_core - model[..., 3])
    worst = float(max((dxx / bound).max(), (dyy / bound).max()))
    cross_zero = bool(np.all(model[..., 1] == 0) and np.all(model[..., 2] == 0))
    ulp = np.spacing(np.abs(v_core).astype(np.float32))
    res["SKY-wsclean"] = {
        "africanus_reads_core": {"problems": p[:20], "problem_count": len(p)},
        "core_reads_its_own": {"problems": p_back[:20]},
        "crystalball": {
            "rows": int(rows.sum()),
            "channels": len(freqs),
            "max_error_over_bound": worst,
            "max_abs_error": float(max(dxx.max(), dyy.max())),
            "max_error_in_ulps_of_v": float(max((dxx / ulp).max(), (dyy / ulp).max())),
            "bit_identical_cells_fraction": float(np.mean(v_core == model[..., 0])),
            "cross_hands_zero": cross_zero,
            "core_predict_s": predict_s,
            "crystalball_wall_s": json.loads(
                (d / "cb.ms.crystalball.json").read_text()
            )["wall_s"],
            "pass": worst <= 1.0 and cross_zero,
        },
    }
    afw = load("africanus-of-wsclean.json")
    ws = sky.load_wsclean(d / "ws-sources.txt")
    pw = []
    if [s.name for s in ws] != afw["Name"]:
        pw.append("names differ")
    for k, s in enumerate(ws):
        for key, val in (("Ra", s.ra), ("Dec", s.dec), ("I", s.i)):
            if float(afw[key][k]) != val:
                pw.append(f"{s.name} {key} {float(afw[key][k]) - val:.3g}")
        spi = [float(x) for x in afw["SpectralIndex"][k]]
        while spi and spi[-1] == 0.0:  # the core drops trailing zero terms
            spi.pop()
        if spi != list(s.spi):
            pw.append(f"{s.name} SpectralIndex")
        if afw["LogarithmicSI"][k] != s.log_si:
            pw.append(f"{s.name} LogarithmicSI")
    res["SKY-wsclean"]["wsclean_list_read"] = {
        "components": len(ws),
        "problems": pw[:20],
        "pass": not pw,
    }
    res["SKY-wsclean"]["pass"] = (
        not p and not p_back and res["SKY-wsclean"]["crystalball"]["pass"] and not pw
    )
    # BBS: Tigger's BBS file read by the core and by Tigger.
    bbs = sky.load_bbs(d / "t.cat")
    pb, wb = compare_tigger(bbs, load("tigger-of-bbs.json"), angle_ulps=4)
    res["SKY-bbs"] = {
        "problems": pb[:20],
        "problem_count": len(pb),
        "max_angle_ulps": wb,
        "against_the_lsm": compare_sources(
            sources, bbs, angle_tol=1e-9, shape_rel=1e-9
        )[:10],
        "pass": not pb,
    }
    # DicoModel: the restricted unpickler against DDFacet's own load.
    ddf = outputs() / DDF_RUN
    md = mounts(run, (ddf, "/ddf", "ro"))
    dpy = "/opt/ddf/bin/python -I /ex/oracle_formats.py"
    nodes = sky.read_clustercat(ddf / "img.NodesCatImaged.npy")
    np.savez(d / "clustercat-values.npz", cat=nodes)
    sky.write_clustercat(d / "core-clustercat.npy", nodes)
    docker(
        FORMATS_IMAGE,
        [
            "sh",
            "-c",
            (
                f"{dpy} dicomodel-dump /ddf/img.DicoModel /run/sky/dicomodel-ddf.npz && "
                f"{dpy} npy-dump /ddf/img.NodesCatImaged.npy /run/sky/clustercat-ddf.npz && "
                f"{dpy} npy-save /run/sky/clustercat-values.npz cat /run/sky/clustercat-ddf.npy"
            ),
        ],
        md,
        "DDFacet DicoModel and ClusterCat",
    )
    start = time.perf_counter()
    dico = sky.load_dicomodel(ddf / "img.DicoModel")
    dico_s = time.perf_counter() - start
    arrays, meta = {}, {}
    oracle_formats._flatten("", dico, arrays, meta)
    theirs_meta = json.loads((d / "dicomodel-ddf.npz.json").read_text())
    with np.load(d / "dicomodel-ddf.npz", allow_pickle=False) as z:
        theirs = [z[f"a{i}"] for i in range(len(z.files))]
    same_meta = (
        json.loads(json.dumps(meta)) == theirs_meta["meta"]
        and list(arrays) == theirs_meta["arrays"]
    )
    same_arrays = len(theirs) == len(arrays) and all(
        e4.same_array(a, b) for a, b in zip(arrays.values(), theirs)
    )
    bad = d / "evil.pickle"
    bad.write_bytes(b"cos\nsystem\n(S'echo pwned'\ntR.")
    try:
        sky.load_dicomodel(bad)
        refused = False
    except Exception as err:  # noqa: BLE001 - the refusal is the result
        refused = "not allowed" in str(err)
    res["SKY-dicomodel"] = {
        "structure_equal": bool(same_meta),
        "arrays_bit_exact": bool(same_arrays),
        "crafted_pickle_refused": refused,
        "summary": sky.dicomodel_summary(dico),
        "read_s": dico_s,
        "pass": bool(same_meta and same_arrays and refused),
    }
    with np.load(d / "clustercat-ddf.npz", allow_pickle=False) as z:
        cat_ddf = z["a"]
    cc = {
        "read_bit_exact": bool(e4.same_array(nodes, cat_ddf)),
        "write_byte_identical": (d / "core-clustercat.npy").read_bytes()
        == (d / "clustercat-ddf.npy").read_bytes(),
        "dtype": str(nodes.dtype),
        "rows": len(nodes),
    }
    cc["pass"] = cc["read_bit_exact"] and cc["write_byte_identical"]
    res["SKY-clustercat"] = cc
    result = {
        "lsm_sha256": sha,
        "components": len(sources),
        **res,
        "verdicts": {k: v["pass"] for k, v in res.items()},
    }
    return write_json(run, "sky", result, started)


# ---------------------------------------------------------------------------
# F4: H5parm.


def antenna_names(ms):
    from rang import core_ms

    with core_ms.open_table(Path(ms) / "ANTENNA") as t:
        return [str(x) for x in t.getcol("NAME")], t.getcol("POSITION")


def step_h5(run):
    from rang.formats import h5parm

    started = time.perf_counter()
    run = Path(run)
    d = run / "h5"
    d.mkdir(parents=True, exist_ok=True)
    ms = casa_ms()
    cols = ms_columns(ms)
    freqs = ms_frequencies(ms)
    names, positions = antenna_names(ms)
    times = np.unique(cols["TIME"])
    rng = np.random.default_rng(SEED)
    shape = (len(times), len(freqs), len(names), 1, 2)
    amp = 1 + 0.1 * rng.standard_normal(shape)
    phase = rng.uniform(-np.pi, np.pi, shape)
    gains = amp * np.exp(1j * phase)
    ss = h5parm.diagonal_solset(
        None, times, freqs, names, positions, amplitude=amp, phase=phase
    )
    core_h5 = d / "core.h5"
    if core_h5.exists():
        core_h5.unlink()
    start = time.perf_counter()
    h5parm.write(core_h5, {"sol000": ss})
    write_s = time.perf_counter() - start
    np.savez(
        d / "values.npz",
        time=times,
        freq=freqs,
        ant=np.array(names),
        ant_pos=positions.astype(np.float32),
        dir=np.zeros(2, np.float32),
        amp=amp,
        phase=phase,
        weight=np.ones(shape),
    )
    py = "/opt/h5/bin/python -I /ex/oracle_formats.py"
    ref = d / "losoto.h5"
    if ref.exists():
        ref.unlink()
    script = " && ".join(
        [
            f"{py} losoto-dump /run/h5/core.h5 /run/h5/losoto-of-core.json",
            f"{py} losoto-make /run/h5/losoto.h5 /run/h5/values.npz",
            f"{py} h5-list /run/h5/core.h5 /run/h5/list-core.json",
            f"{py} h5-list /run/h5/losoto.h5 /run/h5/list-losoto.json",
        ]
    )
    docker(
        FORMATS_IMAGE, ["sh", "-c", script], mounts(run), "losoto read, make and list"
    )
    # H5-losoto: losoto's read of the core's file.
    info = json.loads((d / "losoto-of-core.json").read_text())
    with np.load(d / "losoto-of-core.json.npz", allow_pickle=False) as z:
        lo = {k: z[k] for k in z.files}
    p = []
    sol = info.get("sol000", {})
    for st, kind, vals in (
        ("amplitude000", "amplitude", amp),
        ("phase000", "phase", phase),
    ):
        entry = sol.get("soltabs", {}).get(st)
        if not entry or entry["type"] != kind or entry["axes"] != list(h5parm.AXES):
            p.append(f"{st}: {entry}")
            continue
        if not e4.same_array(lo[f"sol000/{st}/val"], vals):
            p.append(f"{st} val differs")
        if not np.array_equal(lo[f"sol000/{st}/weight"], np.ones(shape)):
            p.append(f"{st} weight differs")
        for a, v in (("time", times), ("freq", freqs)):
            if not e4.same_array(lo[f"sol000/{st}/axis/{a}"], v):
                p.append(f"{st} axis {a}")
        if [str(x) for x in lo[f"sol000/{st}/axis/ant"]] != names:
            p.append(f"{st} axis ant")
    if sorted(sol.get("antennas", {})) != sorted(names):
        p.append("antenna table")
    # The core's read of losoto's own file.
    ref_read = h5parm.read(ref)["sol000"]
    pr = []
    for st, vals in (("amplitude000", amp), ("phase000", phase)):
        t = ref_read.soltabs[st]
        if t.axes != h5parm.AXES or not e4.same_array(t.val, vals):
            pr.append(f"{st} val or axes")
        if not np.array_equal(t.weight, np.ones(shape)):
            pr.append(f"{st} weight")
        if list(t.axis_values["ant"]) != names or not e4.same_array(
            t.axis_values["time"], times
        ):
            pr.append(f"{st} axis values")
    own = h5parm.read(core_h5)["sol000"]
    p_own = (
        [] if e4.same_array(h5parm.diagonal_gains(own), gains) else ["own read differs"]
    )
    # The layout listing, core against losoto (reported).
    lc = {r["path"]: r for r in json.loads((d / "list-core.json").read_text())}
    ll = {r["path"]: r for r in json.loads((d / "list-losoto.json").read_text())}
    listing = {
        "only_core": sorted(set(lc) - set(ll)),
        "only_losoto": sorted(set(ll) - set(lc)),
        "class_or_dtype_differ": sorted(
            k
            for k in set(lc) & set(ll)
            if (lc[k]["class"], lc[k]["dtype"]) != (ll[k]["class"], ll[k]["dtype"])
        ),
        "attrs_differ": {
            k: sorted(set(lc[k]["attrs"].items()) ^ set(ll[k]["attrs"].items()))
            for k in sorted(set(lc) & set(ll))
            if lc[k]["attrs"] != ll[k]["attrs"]
        },
    }
    res = {
        "H5-losoto": {
            "losoto_reads_core": p[:20],
            "core_reads_losoto": pr[:20],
            "core_reads_its_own": p_own,
            "listing": listing,
            "write_s": write_s,
            "bytes": core_h5.stat().st_size,
            "pass": not p and not pr and not p_own,
        }
    }
    # H5-dp3: DP3 applycal on a copy of the MS.
    dp3_ms = d / "dp3.ms"
    if dp3_ms.exists():
        shutil.rmtree(dp3_ms)
    try:
        # DP3 refuses a Measurement Set with more than one FIELD row: CASA
        # split makes a one-field copy of the MS (deviation, recorded).
        docker(
            CASA_IMAGE,
            [
                "sh",
                "-c",
                "/opt/casa/bin/python -I /ex/oracle_formats.py casa-split /o/c.ms /run/h5/dp3.ms J1939-6342",
            ],
            mounts(run, (ms, "/o/c.ms", "ro")),
            "casa split (one field)",
        )
        docker(
            FORMATS_IMAGE,
            ["sh", "-c", f"{py} dp3-apply /run/h5/dp3.ms /run/h5/core.h5"],
            mounts(run),
            "DP3 applycal",
        )
        c = ms_columns(dp3_ms)
        tix = np.searchsorted(times, c["TIME"])
        a1, a2 = c["ANTENNA1"], c["ANTENNA2"]
        g = gains[:, :, :, 0, :]
        exp = np.empty(c["DATA"].shape, complex)
        for k, (pa, qb) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
            exp[..., k] = c["DATA"][..., k] / (
                g[tix, :, a1, pa] * np.conj(g[tix, :, a2, qb])
            )
        flag = c["FLAG"]
        worst, n = rel_error(c["CORRECTED_DATA"], exp, ~flag)
        res["H5-dp3"] = {
            "cells": n,
            "max_relative": worst,
            "dp3_log_tail": json.loads((d / "dp3.ms.dp3.json").read_text())["log"][
                -600:
            ],
            "pass": bool(worst is not None and worst <= 1e-6),
        }
    except RuntimeError as err:
        res["H5-dp3"] = {"error": str(err)[-2000:], "pass": False, "open": True}
    result = {**res, "verdicts": {k: v["pass"] for k, v in res.items()}}
    return write_json(run, "h5", result, started)


# ---------------------------------------------------------------------------
# F5: killMS solutions.


def step_kms(run):
    import oracle_formats
    from rang.formats import killms, sky

    started = time.perf_counter()
    run = Path(run)
    d = run / "kms"
    (d / "in").mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    names, _ = antenna_names(casa_ms())
    nt, nch, na, nd = 3, 2, len(names), 2
    t0 = 5.0e9 + 60.0 * np.arange(nt)
    t1 = t0 + 60.0
    df = 1048576.0  # a power of two: MergeSols needs (f1 - f0) / df whole
    f0 = 1.0e9
    cat = np.zeros(nd, sky.CLUSTERCAT_DTYPE)
    cat["Name"] = [b"d0", b"d1"]
    cat["ra"], cat["dec"] = [5.146, 5.15], [-1.112, -1.11]
    cat["SumI"], cat["Cluster"] = [10.0, 1.0], [0, 1]
    beam_times = np.array([t0[0], t1[-1]])
    files, gains = [], []
    for half in range(2):
        g = 0.1 * (
            rng.standard_normal((nt, nch, na, nd, 2, 2))
            + 1j * rng.standard_normal((nt, nch, na, nd, 2, 2))
        )
        g[..., 0, 0] += 1
        g[..., 1, 1] += 1
        g = g.astype(np.complex64)
        gains.append(g)
        dom = np.zeros((nch, 2))
        dom[:, 0] = f0 + (half * nch + np.arange(nch)) * df
        dom[:, 1] = dom[:, 0] + df
        path = d / "in" / f"half{half}.sols.npz"
        killms.write(
            path,
            killms.make_sols(t0, t1, g),
            names,
            cat,
            dom,
            beam_times=beam_times,
            ms_name=f"half{half}.ms",
            model_name="core",
        )
        files.append(path)
    # np.load without pickle reads the core's files.
    no_pickle = True
    for path in files:
        try:
            with np.load(path, allow_pickle=False) as z:
                for k in z.files:
                    z[k]
        except ValueError:
            no_pickle = False
    py = "/opt/ddf/bin/python -I /ex/oracle_formats.py"
    merged = d / "merged.npz"
    if merged.exists():
        merged.unlink()
    docker(
        FORMATS_IMAGE,
        [
            "sh",
            "-c",
            f"{py} merge-sols '/run/kms/in/*.npz' /run/kms/merged.npz && {py} npz-dump /run/kms/merged.npz /run/kms/merged-dump.npz",
        ],
        mounts(run),
        "killMS MergeSols",
    )
    start = time.perf_counter()
    ours = killms.read(merged)
    read_s = time.perf_counter() - start
    arrays, meta = {}, {}
    for k in sorted(ours):
        oracle_formats._flatten(k, ours[k], arrays, meta)
    theirs_meta = json.loads((d / "merged-dump.npz.json").read_text())
    with np.load(d / "merged-dump.npz", allow_pickle=False) as z:
        theirs = {name: z[f"a{i}"] for i, name in enumerate(theirs_meta["arrays"])}
    read_exact = set(arrays) == set(theirs) and all(
        e4.same_array(arrays[k], theirs[k]) for k in arrays
    )
    object_members = sorted(k for k, v in ours.items() if np.asarray(v).dtype.hasobject)
    expected = killms.merge([killms.read(p) for p in files])
    gm, ge = ours["Sols"].G.astype(complex), expected["Sols"].G.astype(complex)
    worst, n = rel_error(gm, ge, np.ones(gm.shape, bool))
    exact = {
        "FreqDomains": e4.same_array(ours["FreqDomains"], expected["FreqDomains"]),
        "MaskedSols": e4.same_array(ours["MaskedSols"], expected["MaskedSols"]),
        "t0": e4.same_array(
            np.asarray(ours["Sols"].t0), np.asarray(expected["Sols"].t0)
        ),
        "t1": e4.same_array(
            np.asarray(ours["Sols"].t1), np.asarray(expected["Sols"].t1)
        ),
    }
    res = {
        "KMS": {
            "core_files_load_without_pickle": no_pickle,
            "merged_read_bit_exact": bool(read_exact),
            "merged_members": sorted(ours),
            "merged_object_members": object_members,
            "G_max_relative": worst,
            "G_cells": n,
            "exact": exact,
            "read_s": read_s,
            "pass": bool(
                no_pickle
                and read_exact
                and worst is not None
                and worst <= 1e-6
                and all(exact.values())
            ),
        }
    }
    result = {**res, "verdicts": {k: v["pass"] for k, v in res.items()}}
    return write_json(run, "kms", result, started)


# ---------------------------------------------------------------------------
# F6: CASA flag versions.


def step_fv(run):
    from rang.formats import flagversions

    started = time.perf_counter()
    run = Path(run)
    d = run / "fv"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    ms = d / "core.ms"
    shutil.copytree(casa_ms(), ms)
    original = ms_columns(ms, ("FLAG", "FLAG_ROW"))
    rng = np.random.default_rng(SEED)
    flag = rng.random(original["FLAG"].shape) < 0.3
    flag_row = rng.random(original["FLAG_ROW"].shape) < 0.1
    start = time.perf_counter()
    flagversions.save(ms, "rang_dfio", "DF-IO seeded flags", flag, flag_row)
    save_s = time.perf_counter() - start
    py = "/opt/casa/bin/python -I /ex/oracle_formats.py"
    docker(
        CASA_IMAGE,
        [
            "sh",
            "-c",
            f"{py} casa-flagversions /run/fv/core.ms list x && {py} casa-flagversions /run/fv/core.ms restore rang_dfio",
        ],
        mounts(run),
        "casa flagmanager list and restore",
    )
    after = ms_columns(ms, ("FLAG", "FLAG_ROW"))
    listed = json.loads((Path(str(ms) + ".list.json")).read_text())
    res = {
        "FV": {
            "restored_FLAG_bit_exact": bool(e4.same_array(after["FLAG"], flag)),
            "restored_FLAG_ROW_bit_exact": bool(
                e4.same_array(after["FLAG_ROW"], flag_row)
            ),
            "flags_changed_by_restore": bool(
                not np.array_equal(after["FLAG"], original["FLAG"])
            ),
            "list_result": str(listed.get("result"))[:600],
            "save_s": save_s,
        }
    }
    res["FV"]["pass"] = (
        res["FV"]["restored_FLAG_bit_exact"]
        and res["FV"]["restored_FLAG_ROW_bit_exact"]
    )
    shutil.rmtree(ms)  # the MS copy (61 MB); the JSON keeps the verdict
    result = {**res, "verdicts": {k: v["pass"] for k, v in res.items()}}
    return write_json(run, "fv", result, started)


# ---------------------------------------------------------------------------
# The archive: every measured verdict, frozen and post hoc, in one table.

# Which run holds which measurement (research/dfio-formats.md, "Runs").
RUNS = {
    "ct": ("dfio-20261030-01", "frozen"),
    "ct-posthoc": ("dfio-20261030-02", "post hoc"),
    "qc": (
        "dfio-20261030-03",
        "frozen (second attempt, the first stopped in the core decoder)",
    ),
    "sky": (
        "dfio-20261030-03",
        "frozen (second attempt, the first stopped in Crystalball)",
    ),
    "sky-posthoc": ("dfio-20261030-04", "post hoc"),
    "h5": ("dfio-20261030-03", "frozen (second attempt)"),
    "h5-posthoc": ("dfio-20261030-04", "post hoc"),
    "kms": (
        "dfio-20261030-03",
        "frozen (second attempt, the first stopped in the core reader)",
    ),
    "fv": ("dfio-20261030-01", "frozen"),
}


def _strip(result):
    return {k: v for k, v in result.items() if k != "timings"}


def step_summary(archive):
    started = time.perf_counter()
    runs = {
        k: json.loads((outputs() / run / f"{k.split('-')[0]}.json").read_text())
        for k, (run, _) in RUNS.items()
    }
    ct, ctp, qc, sk, skp, h5, h5p, kms, fv = (
        runs[k]
        for k in (
            "ct",
            "ct-posthoc",
            "qc",
            "sky",
            "sky-posthoc",
            "h5",
            "h5-posthoc",
            "kms",
            "fv",
        )
    )

    def v(ok):
        return "pass" if ok else "fail"

    def worst(sem, prefix):
        rows = {k: s for k, s in sem.items() if k.startswith(prefix)}
        return {
            k: [
                s["max_relative"],
                s.get("cells_above_1e-6"),
                s.get("max_error_float32_eps_of_cell"),
            ]
            for k, s in rows.items()
        }

    table = [
        {
            "format": "CASA caltable",
            "direction": "read",
            "oracle": "python-casacore 3.8.1 dump of CASA 6.7.6's K, G, B, Df, T",
            "verdict": v(ct["verdicts"]["CT-read"]),
            "run": "ct",
        },
        {
            "format": "CASA caltable",
            "direction": "write",
            "oracle": "byte rule against CASA's tables; applycal bit-identical",
            "verdict": v(ct["verdicts"]["CT-write-identity"]),
            "run": "ct",
        },
        {
            "format": "CASA caltable",
            "direction": "semantics (read)",
            "oracle": "applycal CORRECTED_DATA, 1e-6 relative",
            "verdict": v(ct["verdicts"]["CT-semantics"]),
            "run": "ct",
            "post_hoc": {
                "verdict": v(ctp["verdicts"]["CT-semantics"]),
                "max_relative_cells_eps": worst(ctp["semantics"], "casa"),
            },
        },
        {
            "format": "CASA caltable",
            "direction": "write (core gains)",
            "oracle": "applycal of core-made G, B, K, T, 1e-6 relative",
            "verdict": v(ct["verdicts"]["CT-synthetic"]),
            "run": "ct",
            "post_hoc": {
                "verdict": v(ctp["verdicts"]["CT-synthetic"]),
                "max_relative_cells_eps": worst(ctp["semantics"], "synth"),
            },
        },
        {
            "format": "QuartiCal store",
            "direction": "read",
            "oracle": "dask-ms xds_from_zarr (QuartiCal 0.2.7 venv)",
            "verdict": v(qc["verdicts"]["QC-read"]),
            "run": "qc",
        },
        {
            "format": "QuartiCal store",
            "direction": "write",
            "oracle": "metadata bytes, xds_from_zarr, QuartiCal load_from apply bit-identical, seeded 1e-6",
            "verdict": v(
                all(
                    qc["verdicts"][k]
                    for k in ("QC-write-a", "QC-write-b", "QC-write-c")
                )
            ),
            "run": "qc",
            "seeded_max_relative": qc["seeded_apply"]["max_relative"],
        },
        {
            "format": "Tigger lsm (ASCII)",
            "direction": "read",
            "oracle": "Tigger 1.8.0 load",
            "verdict": v(sk["verdicts"]["SKY-tigger-read"]),
            "run": "sky",
            "max_angle_ulps": sk["SKY-tigger-read"]["max_angle_ulps"],
        },
        {
            "format": "Tigger lsm.html",
            "direction": "write and read",
            "oracle": "Tigger load, tigger-convert round trip",
            "verdict": v(sk["verdicts"]["SKY-html"]),
            "run": "sky",
        },
        {
            "format": "Tigger lsm (ASCII)",
            "direction": "write",
            "oracle": "Tigger load; core read of tigger-convert's ASCII",
            "verdict": v(sk["verdicts"]["SKY-ascii"]),
            "run": "sky",
            "note": "Tigger loads the core's file; tigger-convert writes multi-term spectra as a Python list in the spi column, which neither Tigger nor the core can read",
        },
        {
            "format": "WSClean source list",
            "direction": "write",
            "oracle": "africanus load; Crystalball 0.4.3 predict, float32 bound",
            "verdict": v(sk["verdicts"]["SKY-wsclean"]),
            "run": "sky",
            "crystalball": sk["SKY-wsclean"]["crystalball"],
            "africanus_problems": sk["SKY-wsclean"]["africanus_reads_core"][
                "problem_count"
            ],
            "post_hoc": {
                "africanus_problems": skp["SKY-wsclean"]["africanus_reads_core"][
                    "problem_count"
                ]
            },
        },
        {
            "format": "WSClean source list",
            "direction": "read",
            "oracle": "WSClean 3.7 -save-source-list, africanus load",
            "verdict": v(sk["SKY-wsclean"]["wsclean_list_read"]["pass"]),
            "run": "sky",
            "components": sk["SKY-wsclean"]["wsclean_list_read"]["components"],
        },
        {
            "format": "BBS skymodel",
            "direction": "read",
            "oracle": "Tigger's BBS load of tigger-convert -o BBS",
            "verdict": v(sk["verdicts"]["SKY-bbs"]),
            "run": "sky",
            "note": "Tigger skips the multi-term source of its own file and writes axes and orientation in radians",
            "post_hoc": {"against_the_lsm": skp["SKY-bbs"]["against_the_lsm"][:3]},
        },
        {
            "format": "DDFacet DicoModel",
            "direction": "read",
            "oracle": "DDFacet 1.0.0.0 MyPickle.Load",
            "verdict": v(sk["verdicts"]["SKY-dicomodel"]),
            "run": "sky",
        },
        {
            "format": "DDFacet ClusterCat",
            "direction": "read and write",
            "oracle": "np.load / np.save (DDFacet's NumPy 2.3.2)",
            "verdict": v(sk["verdicts"]["SKY-clustercat"]),
            "run": "sky",
        },
        {
            "format": "H5parm",
            "direction": "write and read",
            "oracle": "losoto 2.7.1 H5parm API; losoto-made file",
            "verdict": v(h5["verdicts"]["H5-losoto"]),
            "run": "h5",
        },
        {
            "format": "H5parm",
            "direction": "apply",
            "oracle": "DP3 6.6.0 applycal, 1e-6 relative",
            "verdict": v(h5["verdicts"]["H5-dp3"]),
            "run": "h5",
            "post_hoc": {
                "verdict": v(h5p["verdicts"]["H5-dp3"]),
                "max_relative": h5p["H5-dp3"].get("max_relative"),
            },
        },
        {
            "format": "killMS solutions",
            "direction": "write",
            "oracle": "killMS 3.3.0 MergeSols.py",
            "verdict": v(kms["verdicts"]["KMS"]),
            "run": "kms",
            "G_max_relative": kms["KMS"]["G_max_relative"],
        },
        {
            "format": "killMS solutions",
            "direction": "read",
            "oracle": "np.load(allow_pickle=True) of MergeSols' output",
            "verdict": v(kms["KMS"]["merged_read_bit_exact"]),
            "run": "kms",
        },
        {
            "format": "CASA flag versions",
            "direction": "write",
            "oracle": "CASA flagmanager restore and list",
            "verdict": v(fv["verdicts"]["FV"]),
            "run": "fv",
        },
    ]
    for row in table:
        row["run_dir"], row["label"] = RUNS[row["run"]]
    image = subprocess.run(
        ["docker", "image", "inspect", FORMATS_IMAGE, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    result = {
        "task": "DF-IO (research/dfio-formats.md)",
        "table": table,
        "runs": {k: {"run_dir": r, "label": lab} for k, (r, lab) in RUNS.items()},
        "oracle_images": {
            "formats": [FORMATS_IMAGE, image],
            "casa": CASA_IMAGE,
            "ms_reader": MS_IMAGE,
        },
        "steps": {k: _strip(r) for k, r in runs.items()},
        "timings": {k: r.get("timings", []) for k, r in runs.items()},
        "seed": SEED,
    }
    Path(archive).write_text(json.dumps(result, indent=1, default=str) + "\n")
    print(
        json.dumps(
            [(r["format"], r["direction"], r["verdict"]) for r in table], indent=0
        )
    )
    return {"wall_s": time.perf_counter() - started}


STEPS = {
    "ct": step_ct,
    "qc": step_qc,
    "sky": step_sky,
    "h5": step_h5,
    "kms": step_kms,
    "fv": step_fv,
    "summary": step_summary,
}


def main(argv):
    if len(argv) < 3 or argv[1] not in STEPS:
        print(__doc__)
        return 2
    STEPS[argv[1]](*argv[2:])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
