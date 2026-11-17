# SPDX-License-Identifier: MIT
"""M3 cases and the M2 flag-stage gate (research/msv4-interop.md section 11).

Steps:

    make-m3 ROOT                     (WSL, python-casacore) c10 to c14 from c5
    convert-m3 ROOT                  (WSL) arms xradio and xms-auto of c10 to c14
    check-m3 ROOT RECEIPT RUN07      (Windows) c10 to c14 per data group, and
                                     c1 to c9 as a control against run 07
    m2 ROOT RECEIPT STRATEGY         (Windows) the flag stage on two copies of
                                     c5 against its kernel fed from MSv4

ROOT is `D:/rang/outputs/msv4-<date>` (`/mnt/d/...` in WSL). The section 4
helpers (case paths, stores, the MSv2 reference, row mapping rules) come
from `msv4_interop.py` beside this file.
"""

import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import msv4_interop as h

M3_CASES = {
    "c10": "c10-flag-row.ms",
    "c11": "c11-corrected-model.ms",
    "c12": "c12-sigma-row.ms",
    "c13": "c13-no-spectrum-weights.ms",
    "c14": "c14-decreasing-freq.ms",
}
M3_ARMS = ("xradio", "xms-auto")
CONTROL_ARMS = ("xradio", "xms-auto")
GROUP_COLUMN = {"base": "DATA", "corrected": "CORRECTED_DATA", "model": "MODEL_DATA"}
CORR_CODES = {v: k for k, v in h.CORR_NAMES.items()}
SPW_REVERSED = ("CHAN_FREQ", "CHAN_WIDTH", "EFFECTIVE_BW", "RESOLUTION")


def m3_paths(root):
    return {k: Path(root) / "ms" / v for k, v in M3_CASES.items()}


# --- make-m3 (WSL, python-casacore) ------------------------------------------


def make_m3(root):
    import numpy as np
    from casacore import tables

    src = h.case_paths(root)["c5"]
    paths = m3_paths(root)

    def fresh(case, base=src):
        dst = paths[case]
        if dst.exists():
            shutil.rmtree(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(base, dst)  # keeps table.lock (section 7)
        return dst

    def bare(desc):
        return {
            k: v
            for k, v in desc.items()
            if k not in ("dataManagerType", "dataManagerGroup")
        }

    with tables.table(str(fresh("c10")), readonly=False, ack=False) as t:
        flag_row = t.getcol("FLAG_ROW")
        flag_row[2::5] = True
        t.putcol("FLAG_ROW", flag_row)
        print("c10: FLAG_ROW set on", int(flag_row.sum()), "of", t.nrows(), "rows")

    with tables.table(str(fresh("c11")), readonly=False, ack=False) as t:
        data = t.getcol("DATA")
        assert data.dtype == np.complex64
        for name, factor in (
            ("CORRECTED_DATA", np.complex64(0.5 - 0.25j)),
            ("MODEL_DATA", np.complex64(2)),
        ):
            desc = tables.makecoldesc(name, bare(t.getcoldesc("DATA")))
            t.addcols(tables.maketabdesc(desc))
            values = data * factor
            assert values.dtype == np.complex64
            t.putcol(name, values)
        sigma = t.getcol("SIGMA_SPECTRUM")
        sigma[0, 0, 0] = 0
        sigma[1, 1, 1] = np.nan
        sigma[2, 2, 2] = -1
        t.putcol("SIGMA_SPECTRUM", sigma)
        print("c11: columns", sorted(t.colnames()))

    with tables.table(str(fresh("c12", paths["c11"])), readonly=False, ack=False) as t:
        t.removecols("SIGMA_SPECTRUM")
        sigma = t.getcol("SIGMA")
        sigma[3, 0] = 0
        t.putcol("SIGMA", sigma)
        print("c12: columns", sorted(t.colnames()))

    with tables.table(str(fresh("c13")), readonly=False, ack=False) as t:
        t.removecols(["WEIGHT_SPECTRUM", "SIGMA_SPECTRUM"])
        print("c13: columns", sorted(t.colnames()))

    dst = fresh("c14")
    with tables.table(str(dst / "SPECTRAL_WINDOW"), readonly=False, ack=False) as t:
        for name in SPW_REVERSED:
            values = t.getcol(name)
            t.putcol(name, np.ascontiguousarray(values[:, ::-1]))
        print("c14: CHAN_FREQ first/last", t.getcol("CHAN_FREQ")[0, [0, -1]])


def convert_m3(root):
    h.convert(root, None, M3_ARMS, m3_paths(root))


# --- check-m3 (Windows, rang.core_ms and rang.msv4) -------------------------


def sigma_weight(sigma):
    """Section 11's S: 1/(s*s) where s is finite and > 0, else 0, in s's dtype."""
    import numpy as np

    sigma = np.asarray(sigma)
    valid = np.isfinite(sigma) & (sigma > 0)
    safe = np.where(valid, sigma, sigma.dtype.type(1))
    return np.where(valid, 1 / (safe * safe), sigma.dtype.type(0)).astype(
        sigma.dtype, copy=False
    )


def _reference(ms):
    import numpy as np
    from rang import core_ms

    ref = h._ms_reference(ms)
    with core_ms.open_table(ms) as t:
        cols = set(t.columns)
        ref["columns"] = sorted(cols)
        ref["FLAG_ROW"] = np.asarray(t.getcol("FLAG_ROW"), bool)
        ref["extra"] = {}
        for ddid, cells in ref["cells"].items():
            rows = np.flatnonzero(ref["DATA_DESC_ID"] == ddid)
            extra = {}
            for name in ("CORRECTED_DATA", "MODEL_DATA"):
                if name in cols:
                    extra[name] = t.getcol_rows(name, rows)
            nchan = cells["DATA"].shape[1]
            if "SIGMA_SPECTRUM" in cols:
                sigma, source = t.getcol_rows("SIGMA_SPECTRUM", rows), "SIGMA_SPECTRUM"
            else:
                sigma = np.repeat(t.getcol_rows("SIGMA", rows)[:, None, :], nchan, 1)
                source = "SIGMA repeated"
            extra["S"] = sigma_weight(sigma)
            extra["S_source"] = source
            ref["extra"][ddid] = extra
    return ref


def _pick(part, rows, ref, ddid):
    """Section 4's row mapping: MSv2 rows of `ddid`, the loader row of each
    (-1 if none), the channel map, the 1 ms fallbacks and failures."""
    import numpy as np

    failures = []
    spw_freq = ref["chan_freq"][ref["dd_spw"][ddid]]
    where = {f: i for i, f in enumerate(part.frequency.tolist())}
    chan = np.asarray([where[f] for f in spw_freq.tolist()], np.int64)
    names = part.antenna_names
    key = {}
    for i in range(len(rows["TIME"])):
        k = (rows["TIME"][i], names[rows["ANTENNA1"][i]], names[rows["ANTENNA2"][i]])
        if k in key:
            failures.append(f"{part.name}: duplicate loader row {k}")
        key[k] = i
    times = np.unique(rows["TIME"])
    msrows = np.flatnonzero(ref["DATA_DESC_ID"] == ddid)
    pick = np.full(len(msrows), -1, np.int64)
    fallback = 0
    for j, r in enumerate(msrows):
        n1, n2 = ref["names"][ref["ANTENNA1"][r]], ref["names"][ref["ANTENNA2"][r]]
        t = ref["TIME"][r]
        i = key.get((t, n1, n2))
        if i is None and len(times):
            near = times[np.argmin(np.abs(times - t))]
            if abs(near - t) <= h.NEAREST_S:
                i = key.get((near, n1, n2))
                fallback += i is not None
        if i is not None:
            pick[j] = i
    return msrows, pick, chan, fallback, failures


MEASURES = (
    "data",
    "FLAG cells",
    "FLAG with FLAG_ROW",
    "weight W",
    "weight S",
    "UVW",
    "TIME",
    "coverage",
)


def _deciding_weight(group, ref):
    if group == "corrected":
        return ("W",)
    if group == "base" and "CORRECTED_DATA" not in ref["columns"]:
        return ("W",)
    return ("W", "S")


def check_groups(ms, path, ref):
    """Section 11's measures per data group of one case × arm."""
    import numpy as np
    from rang import msv4

    out = {"store": str(path), "partitions": {}, "groups": {}}
    try:
        ps = msv4.open_processing_set(path)
    except Exception as exc:  # noqa: BLE001 (booked)
        return {**out, "outcome": "refused", "error": f"{type(exc).__name__}: {exc}"}
    out["refused_partitions"] = ps.refused
    implied = {"base"}
    implied |= {"corrected"} if "CORRECTED_DATA" in ref["columns"] else set()
    implied |= {"model"} if "MODEL_DATA" in ref["columns"] else set()
    nms = len(ref["TIME"])
    state = {}
    for pname in ps.names:
        node = ps.tree[pname]
        groups = dict(node.attrs["data_groups"])
        out["partitions"][pname] = {"data_groups": sorted(groups)}
        for g in sorted(set(groups) | implied):
            st = state.setdefault(
                g,
                {
                    "used": np.zeros(nms, np.int64),
                    "loader_rows": 0,
                    "pads": 0,
                    "fallback": 0,
                    "ok": {m: [] for m in MEASURES},
                    "writer": [],
                    "reader": [],
                    "failures": [],
                },
            )
            if g not in groups:
                st["writer"].append(f"{pname}: no data group {g!r}")
                continue
            try:
                part = msv4.Partition(node, pname, g)
                rows = part.rows()
            except ValueError as exc:
                where = "writer" if "has no" in str(exc) else "reader"
                st[where].append(f"{pname}: {exc}")
                continue
            st["loader_rows"] += len(rows["TIME"])
            st["pads"] += rows["PADS"]
            hits = h._ddid_of(part, ref)
            if len(hits) != 1:
                st["failures"].append(f"{pname}: DATA_DESC_ID mapping {hits}")
                continue
            ddid = hits[0]
            msrows, pick, chan, fallback, failures = _pick(part, rows, ref, ddid)
            st["fallback"] += fallback
            st["failures"] += failures
            ok = pick >= 0
            st["used"][msrows[ok]] += 1
            sel, lrows = pick[ok], msrows[ok]
            if np.unique(sel).size != sel.size:
                st["failures"].append(f"{pname}: a loader row maps to two MSv2 rows")
            cells = ref["cells"][ddid]
            extra = ref["extra"][ddid]

            def cell(name, rows=rows, sel=sel, chan=chan):
                return rows[name][sel][:, chan, :]

            column = GROUP_COLUMN.get(g)
            want = cells["DATA"] if g == "base" else extra.get(column)
            if want is not None:
                st["ok"]["data"].append(h._same(cell("DATA"), want[ok]))
            flag_row = ref["FLAG_ROW"][lrows][:, None, None]
            st["ok"]["FLAG cells"].append(h._same(cell("FLAG"), cells["FLAG"][ok]))
            st["ok"]["FLAG with FLAG_ROW"].append(
                h._same(cell("FLAG"), cells["FLAG"][ok] | flag_row)
            )
            got_w = cell("WEIGHT_SPECTRUM")
            st["ok"]["weight W"].append(h._same(got_w, cells["WEIGHT_SPECTRUM"][ok]))
            st["ok"]["weight S"].append(h._same(got_w, extra["S"][ok]))
            st["ok"]["UVW"].append(h._same(rows["UVW"][sel], ref["UVW"][lrows]))
    for g, st in sorted(state.items()):
        coverage = (
            bool(np.all(st["used"] == 1))
            and st["loader_rows"] == nms
            and not st["failures"]
        )
        measures = {}
        for m in MEASURES:
            if m == "coverage":
                measures[m] = "match" if coverage else "mismatch"
            elif m == "TIME":
                measures[m] = (
                    "match" if coverage and st["fallback"] == 0 else "mismatch"
                )
            elif not st["ok"][m]:
                measures[m] = "not measured"
            else:
                measures[m] = "match" if all(st["ok"][m]) else "mismatch"
        weights = [
            w for w in _deciding_weight(g, ref) if measures[f"weight {w}"] == "match"
        ]
        deciding = {
            k: measures[k]
            for k in ("data", "FLAG with FLAG_ROW", "UVW", "TIME", "coverage")
        }
        deciding["weight"] = "match" if weights else "mismatch"
        if st["writer"]:
            outcome = "writer outcome"
        elif st["reader"]:
            outcome = "refused"
        elif all(v == "match" for v in deciding.values()):
            outcome = "match"
        else:
            outcome = "mismatch"
        out["groups"][g] = {
            "implied_by_ms": g in implied,
            "outcome": outcome,
            "measures": measures,
            "deciding": deciding,
            "weight_matches": [
                w for w in ("W", "S") if measures[f"weight {w}"] == "match"
            ],
            "weight_deciding_candidates": list(_deciding_weight(g, ref)),
            "loader_rows": st["loader_rows"],
            "pads": st["pads"],
            "time_fallback_rows": st["fallback"],
            "unmapped_ms_rows": int(np.sum(st["used"] == 0)),
            "writer": st["writer"],
            "reader": st["reader"],
            "failures": st["failures"][:20],
        }
    implied_out = [out["groups"][g]["outcome"] for g in sorted(implied)]
    out["outcome"] = "match" if all(o == "match" for o in implied_out) else "not met"
    return out


def check_m3(root, receipt, run07):
    import numpy as np  # noqa: F401
    from rang import core

    previous = json.loads(Path(run07).read_text())
    conv = json.loads((Path(root) / "convert.json").read_text())
    result = {
        "note": "research/msv4-interop.md section 11",
        "commit": _commit(),
        "extension": str(core.extension().__file__),
        "versions": h._versions(),
        "root": str(root),
        "control": {},
        "cases": {},
    }
    started = time.perf_counter()
    for case, ms in h.case_paths(root).items():
        ref = h._ms_reference(ms)
        entry = {}
        for arm in CONTROL_ARMS:
            now = h.check_arm(ms, h.store(root, arm, case), ref)["measures"]
            then = previous["cases"][case]["arms"][arm]["measures"]
            entry[arm] = {"measures": now, "equals_run07": now == then}
        result["control"][case] = entry
        print(case, "control", {a: v["equals_run07"] for a, v in entry.items()})
    for case, ms in m3_paths(root).items():
        entry = {"ms": str(ms), "arms": {}}
        try:
            ref = _reference(ms)
        except Exception as exc:  # noqa: BLE001 (booked `not measured`)
            entry["outcome"] = "not measured"
            entry["error"] = f"{type(exc).__name__}: {exc}"
            result["cases"][case] = entry
            print(case, "not measured", entry["error"])
            continue
        entry["rows"] = len(ref["TIME"])
        entry["columns"] = ref["columns"]
        entry["S_source"] = {d: e["S_source"] for d, e in ref["extra"].items()}
        entry["FLAG_ROW_rows"] = int(ref["FLAG_ROW"].sum())
        for arm in M3_ARMS:
            written = conv.get(f"{case}/{arm}", {})
            if written.get("outcome") != "written":
                entry["arms"][arm] = {
                    "outcome": written.get("outcome", "not measured"),
                    "error": written.get("error", "no conversion log entry"),
                }
                continue
            t0 = time.perf_counter()
            arm_out = check_groups(ms, h.store(root, arm, case), ref)
            arm_out["check_seconds"] = round(time.perf_counter() - t0, 3)
            arm_out["convert_seconds"] = written.get("seconds")
            entry["arms"][arm] = arm_out
        result["cases"][case] = entry
        print(
            case,
            {
                a: (
                    v.get("outcome"),
                    {g: x["outcome"] for g, x in v.get("groups", {}).items()},
                )
                for a, v in entry["arms"].items()
            },
            flush=True,
        )
    result["seconds"] = round(time.perf_counter() - started, 3)
    Path(receipt).write_text(json.dumps(result, indent=1, sort_keys=True, default=str))
    print("receipt", receipt)


# --- m2 (Windows): the flag stage against its kernel fed from MSv4 ----------


def _msv2_meta(ms):
    import numpy as np
    from rang import core_ms

    with core_ms.open_table(Path(ms) / "ANTENNA") as t:
        names = [str(n) for n in t.getcol("NAME")]
        positions = np.asarray(t.getcol("POSITION"), np.float64)
    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as t:
        freq = np.asarray(t.getcol("CHAN_FREQ", 0, 1)[0], np.float64)
        width = np.asarray(t.getcol("CHAN_WIDTH", 0, 1)[0], np.float64)
    with core_ms.open_table(Path(ms) / "POLARIZATION") as t:
        corr = np.asarray(t.getcol("CORR_TYPE", 0, 1)[0], np.int32)
    with core_ms.open_table(ms) as t:
        fields = sorted(set(np.asarray(t.getcol("FIELD_ID")).tolist()))
    return {
        "names": names,
        "positions": positions,
        "freq": freq,
        "width": width,
        "corr": corr,
        "fields": fields,
    }


def _store_meta(part, meta):
    """Store metadata for the kernel, each compared with the MSv2's bit for
    bit; a differing one is replaced by the MSv2's (a labelled fallback)."""
    import numpy as np

    node = part.node
    ant = node["antenna_xds"].ds
    pos = np.asarray(
        ant["ANTENNA_POSITION"].transpose("antenna_name", ...).values, np.float64
    )
    order = [meta["names"].index(a) for a in part.antenna_names]
    width_attr = part.ds["frequency"].attrs.get("channel_width", {})
    width = np.asarray(width_attr.get("data", np.nan), np.float64)
    width = np.broadcast_to(width, part.frequency.shape).astype(np.float64)
    corr = np.asarray([CORR_CODES.get(p, -1) for p in part.polarization], np.int32)
    store = {
        "positions": pos,
        "freq": np.asarray(part.frequency, np.float64),
        "width": width,
        "corr": corr,
    }
    want = {
        "positions": meta["positions"][order],
        "freq": meta["freq"],
        "width": meta["width"],
        "corr": meta["corr"],
    }
    used, report = {}, {}
    for k, value in store.items():
        same = h._same(np.ascontiguousarray(value), np.ascontiguousarray(want[k]))
        report[k] = "match" if same else "fallback (MSv2's)"
        used[k] = value if same else want[k]
    return used, report


def m2(root, receipt, strategy_path):
    import numpy as np
    from rang import cal_chain, core, core_flag, core_ms, msv4

    text = Path(strategy_path).read_text()
    sha = hashlib.sha256(Path(strategy_path).read_bytes()).hexdigest()
    strategies = core_flag.parse_strategy(text)
    src = h.case_paths(root)["c5"]
    meta = _msv2_meta(src)
    with core_ms.open_table(src) as t:
        before = np.asarray(t.getcol("FLAG"), bool)
    result = {
        "note": "research/msv4-interop.md section 11 (M2)",
        "commit": _commit(),
        "extension": str(core.extension().__file__),
        "versions": h._versions(),
        "strategy": str(strategy_path),
        "strategy_sha256": sha,
        "case": "c5",
        "ms": str(src),
        "msv2": {},
        "arms": {},
    }
    flags = {}
    for copy in ("a", "b"):
        dst = Path(root) / "m2" / f"c5-copy-{copy}.ms"
        if dst.exists():
            shutil.rmtree(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)
        t0 = time.perf_counter()
        summary = cal_chain.flag_corrected(
            dst, meta["fields"], strategies, column="DATA"
        )
        seconds = time.perf_counter() - t0
        with core_ms.open_table(dst) as t:
            flags[copy] = np.asarray(t.getcol("FLAG"), bool)
            ref = {k: t.getcol(k) for k in ("TIME", "ANTENNA1", "ANTENNA2")}
        result["msv2"][copy] = {
            "path": str(dst),
            "seconds": round(seconds, 3),
            "flag_sha256": summary["flag_sha256"],
            "flagged_before": int(before.sum()),
            "flagged_after": int(flags[copy].sum()),
        }
    deterministic = h._same(flags["a"], flags["b"])
    added = int(flags["a"].sum()) > int(before.sum())
    result["msv2_deterministic"] = deterministic
    result["stage_adds_flags"] = added
    for arm in M3_ARMS:
        path = h.store(root, arm, "c5")
        ps = msv4.open_processing_set(path)
        (pname,) = ps.names
        part = ps.partition(pname)
        pieces = list(part.chunks(time_rows=4))
        rows = {
            k: np.concatenate([p[k] for p in pieces])
            for k in ("DATA", "FLAG", "ANTENNA1", "ANTENNA2", "TIME")
        }
        used, report = _store_meta(part, meta)
        t0 = time.perf_counter()
        out = core_flag.flag_rows(
            rows["DATA"],
            rows["FLAG"],
            rows["ANTENNA1"],
            rows["ANTENNA2"],
            rows["TIME"],
            used["positions"],
            used["freq"],
            used["width"],
            used["corr"],
            strategies,
            masks=None,
            want_intensity=False,
            want_stages=False,
        )
        seconds = time.perf_counter() - t0
        new = rows["FLAG"] | out["flags"]
        names = part.antenna_names
        key = {
            (rows["TIME"][i], names[rows["ANTENNA1"][i]], names[rows["ANTENNA2"][i]]): i
            for i in range(len(rows["TIME"]))
        }
        pick = np.asarray(
            [
                key.get(
                    (
                        ref["TIME"][r],
                        meta["names"][ref["ANTENNA1"][r]],
                        meta["names"][ref["ANTENNA2"][r]],
                    ),
                    -1,
                )
                for r in range(len(ref["TIME"]))
            ],
            np.int64,
        )
        coverage = bool(np.all(pick >= 0)) and len(rows["TIME"]) == len(ref["TIME"])
        same = coverage and h._same(new[pick], flags["a"])
        fallback = any(v != "match" for v in report.values())
        if same and deterministic and added:
            outcome = "partial (metadata fallback)" if fallback else "pass"
        else:
            outcome = "fail"
        differing = int(np.sum(new[pick] != flags["a"])) if coverage else None
        result["arms"][arm] = {
            "store": str(path),
            "chunks": len(pieces),
            "rows": len(rows["TIME"]),
            "pads": int(sum(p["PADS"] for p in pieces)),
            "metadata": report,
            "coverage": coverage,
            "flags_identical": same,
            "differing_cells": differing,
            "flagged_after": int(new.sum()),
            "kernel_seconds": round(seconds, 3),
            "outcome": outcome,
        }
        print(arm, result["arms"][arm], flush=True)
    Path(receipt).write_text(json.dumps(result, indent=1, sort_keys=True, default=str))
    print("msv2 deterministic", deterministic, "adds flags", added, "receipt", receipt)


def _commit():
    import subprocess

    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        check=False,
        text=True,
        cwd=Path(__file__).parent,
    ).stdout.strip()


def main(argv):
    cmd = argv[0]
    if cmd == "make-m3":
        make_m3(argv[1])
    elif cmd == "convert-m3":
        convert_m3(argv[1])
    elif cmd == "check-m3":
        check_m3(argv[1], argv[2], argv[3])
    elif cmd == "m2":
        m2(argv[1], argv[2], argv[3])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
