# SPDX-License-Identifier: GPL-3.0-or-later
"""MSv4 read path against the MSv2 path (research/msv4-interop.md).

Steps (section 4 of the note):

    extract ZIP ROOT          (any OS) the fixture zip into ROOT/fixture
    make-gaps ROOT            (WSL, python-casacore) c8: c5 with rows removed
    convert ROOT [--arms a,b] [ids]       (WSL, xradio 1.3.1 and xarray-ms 0.5.14)
    check ROOT RECEIPT [--arms a,b] [ids] (Windows, rang.core_ms and rang.msv4)

Arms: `xradio`, `xms` (xarray-ms defaults) and `xms-auto` (xarray-ms with
`auto_corrs=True`, section 10). `convert` defaults to `xradio,xms` (the
first part), `check` to every arm with a conversion log entry.

ROOT is `D:/rang/outputs/msv4-<date>` (`/mnt/d/...` in WSL). Archived MSs are
named by their Windows paths and mapped to `/mnt/d` off Windows.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

FIXTURE_SCANS = {
    "c1": "1672727931_sdp_l0_scan_1.ms",
    "c2": "1672727931_sdp_l0_scan_4.ms",
    "c3": "1672727931_sdp_l0_scan_5.ms",
    "c4": "1672727931_sdp_l0_scan_8.ms",
    "c5": "1672727931_sdp_l0_scan_9.ms",
}
ARCHIVED = {
    "c6": "D:/rang/c3a/c3a-20261106-01/A-casa.ms",
    "c7": "D:/rang/outputs/c7a-20261106-03/M1-casa.ms",
    "c9": "D:/rang/outputs/msv2-edge-cases/20261113/ms/m05-var-spw-tssm",
}
ARMS = ("xradio", "xms", "xms-auto")
CONVERT_ARMS = ("xradio", "xms")
CORR_NAMES = {9: "XX", 10: "XY", 11: "YX", 12: "YY", 5: "RR", 6: "RL", 7: "LR", 8: "LL"}
NEAREST_S = 1e-3  # the frozen fallback mapping of TIME (section 4)


def _native(path):
    path = str(path)
    if os.name != "nt" and len(path) > 2 and path[1] == ":":
        return f"/mnt/{path[0].lower()}{path[2:]}"
    return path


def case_paths(root):
    root = Path(root)
    cases = {k: root / "fixture" / "outer_scans" / v for k, v in FIXTURE_SCANS.items()}
    cases.update({k: Path(_native(v)) for k, v in ARCHIVED.items()})
    cases["c8"] = root / "ms" / "c8-scan9-gaps.ms"
    return dict(sorted(cases.items()))


def store(root, arm, case):
    return Path(root) / "ps" / arm / f"{case}.ps.zarr"


def extract(zip_path, root):
    out = Path(root) / "fixture"
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out)
    print("extracted", zip_path, "to", out)


def make_gaps(root):
    from casacore import tables

    src = case_paths(root)["c5"]
    dst = Path(root) / "ms" / "c8-scan9-gaps.ms"
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tables.table(str(src), ack=False) as t:
        times = sorted(set(t.getcol("TIME")))
        a1, a2, tm = t.getcol("ANTENNA1"), t.getcol("ANTENNA2"), t.getcol("TIME")
        names = list(tables.table(str(src / "ANTENNA"), ack=False).getcol("NAME"))
        i1, i2, i3 = names.index("m001"), names.index("m002"), names.index("m003")
        drop = [
            r
            for r in range(t.nrows())
            if (a1[r] == i1 and a2[r] == i2 and tm[r] in times[3:6])
            or (a1[r] == i3 and a2[r] == i3 and tm[r] == times[-1])
        ]
        # Tiled managers cannot remove rows: deep-copy a selection instead.
        keep = [r for r in range(t.nrows()) if r not in set(drop)]
        sel = t.selectrows(keep)
        sel.copy(str(dst), deep=True).close()
        sel.close()
    with tables.table(str(dst), ack=False) as t:
        print("c8: removed rows", drop, "left", t.nrows())


def convert(root, ids=None, arms=CONVERT_ARMS):
    import xarray
    from xradio.measurement_set import convert_msv2_to_processing_set

    log_path = Path(root) / "convert.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else {}
    for case, ms in case_paths(root).items():
        if ids and case not in ids:
            continue
        for arm in arms:
            out = store(root, arm, case)
            if out.exists():
                shutil.rmtree(out)
            out.parent.mkdir(parents=True, exist_ok=True)
            started = time.perf_counter()
            entry = {"ms": str(ms)}
            try:
                if arm == "xradio":
                    convert_msv2_to_processing_set(
                        in_file=str(ms), out_file=str(out), persistence_mode="w"
                    )
                elif arm == "xms":
                    tree = xarray.open_datatree(str(ms), engine="xarray-ms:msv2")
                    tree.to_zarr(str(out))
                elif arm == "xms-auto":
                    tree = xarray.open_datatree(
                        str(ms), engine="xarray-ms:msv2", auto_corrs=True
                    )
                    tree.to_zarr(str(out))
                else:
                    raise SystemExit(f"unknown arm {arm!r}")
                entry["outcome"] = "written"
            except Exception as exc:  # noqa: BLE001 (recorded as `writer fails`)
                entry["outcome"] = "writer fails"
                entry["error"] = f"{type(exc).__name__}: {exc}"[:500]
            entry["seconds"] = round(time.perf_counter() - started, 3)
            log[f"{case}/{arm}"] = entry
            print(case, arm, entry, flush=True)
    log_path.write_text(json.dumps(log, indent=1, sort_keys=True))


# --- check (native, ra-ng readers) -------------------------------------------


def _same(a, b):
    import numpy as np

    a, b = np.asarray(a), np.asarray(b)
    return (
        a.shape == b.shape
        and a.dtype == b.dtype
        and np.ascontiguousarray(a).tobytes() == np.ascontiguousarray(b).tobytes()
    )


def _ms_reference(ms):
    import numpy as np
    from rang import core_ms

    with core_ms.open_table(ms) as t:
        ref = {c: t.getcol(c) for c in ("TIME", "ANTENNA1", "ANTENNA2", "DATA_DESC_ID")}
        ref["UVW"] = t.getcol("UVW")
        # Cell columns per DATA_DESC_ID: their shapes differ between windows.
        ref["cells"], ref["weight_source"], ref["weight_note"] = {}, {}, {}
        for ddid in np.unique(ref["DATA_DESC_ID"]).tolist():
            rows = np.flatnonzero(ref["DATA_DESC_ID"] == ddid)
            cells = {c: t.getcol_rows(c, rows) for c in ("DATA", "FLAG", "WEIGHT")}
            source = "WEIGHT repeated"
            if "WEIGHT_SPECTRUM" in t.columns:
                try:
                    cells["WEIGHT_SPECTRUM"] = t.getcol_rows("WEIGHT_SPECTRUM", rows)
                    source = "WEIGHT_SPECTRUM"
                except Exception as exc:  # noqa: BLE001 (an unwritten column)
                    ref["weight_note"][ddid] = str(exc)[:200]
            if source != "WEIGHT_SPECTRUM":
                nchan = cells["DATA"].shape[1]
                cells["WEIGHT_SPECTRUM"] = np.repeat(
                    cells["WEIGHT"][:, None, :], nchan, axis=1
                )
            ref["cells"][ddid] = cells
            ref["weight_source"][ddid] = source
    with core_ms.open_table(Path(ms) / "ANTENNA") as t:
        ref["names"] = [str(n) for n in t.getcol("NAME")]
    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as t:
        ref["chan_freq"] = [t.getcol("CHAN_FREQ", r, 1)[0] for r in range(t.nrows)]
    with core_ms.open_table(Path(ms) / "DATA_DESCRIPTION") as t:
        ref["dd_spw"] = t.getcol("SPECTRAL_WINDOW_ID")
        ref["dd_pol"] = t.getcol("POLARIZATION_ID")
    with core_ms.open_table(Path(ms) / "POLARIZATION") as t:
        ref["corr"] = [
            tuple(
                CORR_NAMES.get(int(c), str(c)) for c in t.getcol("CORR_TYPE", r, 1)[0]
            )
            for r in range(t.nrows)
        ]
    return ref


def _ddid_of(part, ref):
    import numpy as np

    freq = np.sort(part.frequency)
    hits = [
        d
        for d in range(len(ref["dd_spw"]))
        if np.array_equal(np.sort(ref["chan_freq"][ref["dd_spw"][d]]), freq)
        and ref["corr"][ref["dd_pol"][d]] == part.polarization
    ]
    return hits


def check_arm(ms, path, ref):
    """Measures of one case × arm (section 4)."""
    import numpy as np
    from rang import msv4

    out = {"store": str(path), "partitions": {}, "measures": {}}
    measures = out["measures"]
    try:
        ps = msv4.open_processing_set(path)
    except Exception as exc:  # noqa: BLE001 (recorded as `refused`)
        return {**out, "outcome": "refused", "error": f"{type(exc).__name__}: {exc}"}
    out["refused_partitions"] = ps.refused
    used = np.zeros(len(ref["TIME"]), np.int64)
    loader_rows = 0
    pads = 0
    fallback = 0
    fields = {k: [] for k in ("DATA", "FLAG", "WEIGHT_SPECTRUM", "UVW")}
    failures = []
    for pname in ps.names:
        try:
            part = ps.partition(pname)
            rows = part.rows()
        except Exception as exc:  # noqa: BLE001 (recorded as `refused`)
            out["partitions"][pname] = {"refused": f"{type(exc).__name__}: {exc}"}
            failures.append(f"{pname}: refused")
            continue
        pads += rows["PADS"]
        nrows = len(rows["TIME"])
        loader_rows += nrows
        hits = _ddid_of(part, ref)
        info = {"rows": nrows, "pads": rows["PADS"], "ddid": hits}
        out["partitions"][part.name] = info
        if len(hits) != 1:
            failures.append(f"{part.name}: DATA_DESC_ID mapping {hits}")
            continue
        ddid = hits[0]
        spw_freq = ref["chan_freq"][ref["dd_spw"][ddid]]
        where = {f: i for i, f in enumerate(part.frequency.tolist())}
        chan = np.asarray([where[f] for f in spw_freq.tolist()], np.int64)
        info["channels_reordered"] = bool(np.any(chan != np.arange(len(chan))))
        names = part.antenna_names
        key = {}
        for i in range(nrows):
            k = (
                rows["TIME"][i],
                names[rows["ANTENNA1"][i]],
                names[rows["ANTENNA2"][i]],
            )
            if k in key:
                failures.append(f"{part.name}: duplicate loader row {k}")
            key[k] = i
        times = np.unique(rows["TIME"])
        msrows = np.flatnonzero(ref["DATA_DESC_ID"] == ddid)
        pick = np.full(len(msrows), -1, np.int64)
        for j, r in enumerate(msrows):
            n1, n2 = ref["names"][ref["ANTENNA1"][r]], ref["names"][ref["ANTENNA2"][r]]
            t = ref["TIME"][r]
            i = key.get((t, n1, n2))
            if i is None and len(times):
                near = times[np.argmin(np.abs(times - t))]
                if abs(near - t) <= NEAREST_S:
                    i = key.get((near, n1, n2))
                    if i is not None:
                        fallback += 1
            if i is not None:
                pick[j] = i
        ok = pick >= 0
        used[msrows[ok]] += 1
        sel = pick[ok]
        lrows = msrows[ok]
        for name, oks in fields.items():
            got = rows[name][sel]
            if name == "UVW":
                want = ref["UVW"][lrows]
            else:
                got = got[:, chan, :]
                want = ref["cells"][ddid][name][ok]
            oks.append(_same(got, want))
        if np.unique(sel).size != sel.size:
            failures.append(f"{part.name}: a loader row maps to two MSv2 rows")
    nms = len(ref["TIME"])
    coverage = bool(np.all(used == 1)) and loader_rows == nms and not failures
    measures["coverage"] = "match" if coverage else "mismatch"
    for name, oks in fields.items():
        measures[name] = "match" if oks and all(oks) and coverage else "mismatch"
    measures["TIME"] = "match" if fallback == 0 and coverage else "mismatch"
    measures["antenna names"] = "match" if coverage else "mismatch"
    out.update(
        ms_rows=nms,
        loader_rows=loader_rows,
        pads=pads,
        unmapped_ms_rows=int(np.sum(used == 0)),
        multiply_mapped_ms_rows=int(np.sum(used > 1)),
        time_fallback_rows=fallback,
        weight_source=ref["weight_source"],
        failures=failures[:20],
    )
    refused = [n for n, v in out["partitions"].items() if "refused" in v]
    if refused:
        for k in measures:
            measures[k] = "refused"
    out["outcome"] = (
        "refused"
        if refused
        else "match"
        if all(v == "match" for v in measures.values())
        else "mismatch"
    )
    return out


def check(root, receipt, ids=None, arms=ARMS):
    import numpy as np  # noqa: F401
    import rang
    from rang import core

    convert_log = Path(root) / "convert.json"
    conv = json.loads(convert_log.read_text()) if convert_log.exists() else {}
    result = {
        "note": "research/msv4-interop.md",
        "commit": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            check=False,
            text=True,
            cwd=Path(__file__).parent,
        ).stdout.strip(),
        "extension": str(core.extension().__file__),
        "rang": str(Path(rang.__file__).parent),
        "versions": _versions(),
        "root": str(root),
        "cases": {},
    }
    for case, ms in case_paths(root).items():
        if ids and case not in ids:
            continue
        started = time.perf_counter()
        ref = _ms_reference(ms)
        entry = {"ms": str(ms), "rows": len(ref["TIME"]), "arms": {}}
        for arm in arms:
            written = conv.get(f"{case}/{arm}", {})
            if written.get("outcome") != "written":
                entry["arms"][arm] = {
                    "outcome": written.get("outcome", "not measured"),
                    "error": written.get("error", "no conversion log entry"),
                }
                continue
            t0 = time.perf_counter()
            arm_out = check_arm(ms, store(root, arm, case), ref)
            arm_out["check_seconds"] = round(time.perf_counter() - t0, 3)
            arm_out["convert_seconds"] = written.get("seconds")
            entry["arms"][arm] = arm_out
        entry["seconds"] = round(time.perf_counter() - started, 3)
        result["cases"][case] = entry
        print(case, {a: v.get("outcome") for a, v in entry["arms"].items()}, flush=True)
    Path(receipt).write_text(json.dumps(result, indent=1, sort_keys=True, default=str))
    print("receipt", receipt)


def _versions():
    from importlib.metadata import PackageNotFoundError, version

    out = {"python": sys.version.split()[0]}
    for name in ("numpy", "xarray", "zarr", "numcodecs", "rang-core"):
        try:
            out[name] = version(name)
        except PackageNotFoundError:
            out[name] = None
    return out


def _arms(argv, default):
    if "--arms" in argv:
        i = argv.index("--arms")
        arms = tuple(a for a in argv[i + 1].split(",") if a)
        unknown = set(arms) - set(ARMS)
        if unknown:
            raise SystemExit(f"unknown arms {sorted(unknown)}")
        return arms, argv[:i] + argv[i + 2 :]
    return default, argv


def main(argv):
    cmd = argv[0]
    default = CONVERT_ARMS if cmd == "convert" else ARMS
    arms, argv = _arms(argv, default)
    if cmd == "extract":
        extract(argv[1], argv[2])
    elif cmd == "make-gaps":
        make_gaps(argv[1])
    elif cmd == "convert":
        convert(argv[1], set(argv[2:]) or None, arms)
    elif cmd == "check":
        check(argv[1], argv[2], set(argv[3:]) or None, arms)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
