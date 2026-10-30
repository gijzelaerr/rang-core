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


STEPS = {"ct": step_ct, "qc": step_qc}


def main(argv):
    if len(argv) < 3 or argv[1] not in STEPS:
        print(__doc__)
        return 2
    STEPS[argv[1]](*argv[2:])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
