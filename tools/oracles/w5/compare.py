# SPDX-License-Identifier: GPL-3.0-or-later
"""W5: compare arm S (the chain recipe under Stimela) with arm H (the four
commands by hand) of one case (research/w5-stimela.md, gates 1 and 2).

    python tools/oracles/w5/compare.py S_MS H_MS OUT.json

Both arms' MSs have the same basename in different directories and use the
default run directory `<ms>.rang-run`. Needs casacure and astropy.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
from astropy.io import fits
from casacure.tables import table
from rang.formats import caltable

STAGES = ("flag", "calibrate", "apply", "image")
TIMEY = re.compile(r"(time|seconds|started|finished|utc|when|_at$|wall|cpu|rss|pid)")


def column_hashes(ms):
    out = {}
    with table(str(ms), readonly=True, ack=False) as t:
        for name in t.colnames():
            try:
                values = t.getcol(name)
            except RuntimeError as exc:
                out[name] = f"unreadable: {exc}"
                continue
            out[name] = hashlib.sha256(
                np.ascontiguousarray(values).tobytes()
            ).hexdigest()
    return out


def table_equal(a, b):
    """Every main cell, keyword and subtable cell (C2e's gate 1 rule)."""
    ta, tb = caltable.read(a), caltable.read(b)
    diffs = []
    if ta.vis_cal != tb.vis_cal:
        diffs.append("VisCal")
    if ta.keywords != tb.keywords:
        diffs.append("keywords")
    parts = [("main", ta.main, tb.main)] + [
        (f"sub {k}", ta.subtables[k], tb.subtables.get(k, {})) for k in ta.subtables
    ]
    if set(ta.subtables) != set(tb.subtables):
        diffs.append("subtables")
    for part, ma, mb in parts:
        if set(ma) != set(mb):
            diffs.append(f"{part}: columns")
            continue
        for name in ma:
            xs, ys = ma[name], mb[name]
            if len(xs) != len(ys):
                diffs.append(f"{part} {name}: rows")
                continue
            for x, y in zip(xs, ys):
                if (x is None) != (y is None) or (
                    x is not None and not np.array_equal(np.asarray(x), np.asarray(y))
                ):
                    diffs.append(f"{part} {name}")
                    break
    files_a = sorted(p.relative_to(a) for p in Path(a).rglob("*") if p.is_file())
    files_b = sorted(p.relative_to(b) for p in Path(b).rglob("*") if p.is_file())
    same = files_a == files_b and all(
        (Path(a) / f).read_bytes() == (Path(b) / f).read_bytes() for f in files_a
    )
    differing = sorted(
        str(f)
        for f in set(files_a) & set(files_b)
        if (Path(a) / f).read_bytes() != (Path(b) / f).read_bytes()
    )
    return {
        "equal": not diffs,
        "differences": diffs,
        "files_identical": same,
        "files_differing": differing,
    }


def fits_equal(a, b):
    with fits.open(a) as fa, fits.open(b) as fb:
        if len(fa) != len(fb):
            return {"equal": False, "why": "HDU count"}
        data_equal, header_diffs = True, []
        for ha, hb in zip(fa, fb):
            da, db = ha.data, hb.data
            if (da is None) != (db is None):
                data_equal = False
            elif da is not None:
                da, db = np.asarray(da), np.asarray(db)
                if (
                    da.dtype != db.dtype
                    or da.shape != db.shape
                    or da.tobytes() != db.tobytes()
                ):
                    data_equal = False
            keys = set(ha.header) | set(hb.header)
            header_diffs += sorted(
                k for k in keys if k and ha.header.get(k) != hb.header.get(k)
            )
    return {"equal": data_equal, "header_differences": header_diffs}


def flag_versions(ms):
    """[(name, sha256 of FLAG, sha256 of FLAG_ROW)] in list order."""
    root = Path(str(ms) + ".flagversions")
    listing = root / "FLAG_VERSION_LIST"
    if not listing.is_file():
        return []
    out = []
    for line in listing.read_text().splitlines():
        name = line.split(" : ")[0].strip()
        if not name:
            continue
        with table(str(root / f"flags.{name}"), readonly=True, ack=False) as t:
            out.append(
                (
                    name,
                    *(
                        hashlib.sha256(
                            np.ascontiguousarray(t.getcol(c)).tobytes()
                        ).hexdigest()
                        for c in ("FLAG", "FLAG_ROW")
                    ),
                )
            )
    return out


def scrub(value, arm_dir):
    """Times removed, the arm's directory replaced by <ARM>."""
    if isinstance(value, dict):
        return {
            k: scrub(v, arm_dir)
            for k, v in value.items()
            if not TIMEY.search(k.lower())
        }
    if isinstance(value, list):
        return [scrub(v, arm_dir) for v in value]
    if isinstance(value, str):
        value = value.replace(arm_dir, "<ARM>")
        return re.sub(r"\d{8}T\d{6}Z|\d{4}-\d{2}-\d{2}T[\d:.+]+", "<UTC>", value)
    return value


def leaves(value, prefix=""):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from leaves(v, f"{prefix}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from leaves(v, f"{prefix}[{i}]")
    else:
        yield prefix, value


def json_diff(a, b):
    la, lb = dict(leaves(a)), dict(leaves(b))
    return sorted(
        k for k in set(la) | set(lb) if la.get(k, "<absent>") != lb.get(k, "<absent>")
    )


def receipts(run_dir, arm_dir):
    out = {}
    for path in sorted((run_dir / "receipts").glob("*.rang-receipt.json")):
        r = json.loads(path.read_text())
        out.setdefault(r["stage"], []).append(
            {"command": scrub(r["command"], arm_dir), "exit": r["exit"]}
        )
    return out


def main(s_ms, h_ms, out):
    s_ms, h_ms = Path(s_ms).resolve(), Path(h_ms).resolve()
    assert s_ms.name == h_ms.name, "the arms' MSs must share a basename"
    s_arm, h_arm = str(s_ms.parent), str(h_ms.parent)
    s_run, h_run = Path(str(s_ms) + ".rang-run"), Path(str(h_ms) + ".rang-run")
    result = {"s_ms": str(s_ms), "h_ms": str(h_ms)}

    # Gate 1: the stages done, and the same command per stage.
    states = {}
    for arm, run in (("S", s_run), ("H", h_run)):
        state = json.loads((run / "state.json").read_text())
        states[arm] = {st: state["stages"].get(st, {}).get("status") for st in STAGES}
    rs, rh = receipts(s_run, s_arm), receipts(h_run, h_arm)
    result["gate1"] = {
        "states": states,
        "receipts_S": rs,
        "receipts_H": rh,
        "pass": all(v == "done" for v in states["S"].values())
        and all(v == "done" for v in states["H"].values())
        and rs == rh
        and all(len(v) == 1 and v[0]["exit"] == 0 for v in rs.values())
        and sorted(rs) == sorted(STAGES),
    }

    # Gate 2a: every MS column.
    hs, hh = column_hashes(s_ms), column_hashes(h_ms)
    cols = sorted(set(hs) | set(hh))
    differing = [c for c in cols if hs.get(c) != hh.get(c)]
    result["gate2a"] = {
        "columns": len(cols),
        "differing": differing,
        "sha256_S": hs,
        "pass": not differing and set(hs) == set(hh),
    }

    # Gate 2b: every table the calibrate stage lists.
    sumS = json.loads((s_run / "calibrate" / "summary.json").read_text())
    sumH = json.loads((h_run / "calibrate" / "summary.json").read_text())
    names_s = [t["name"] for t in sumS["tables"]]
    names_h = [t["name"] for t in sumH["tables"]]
    tables = {}
    for t in sumS["tables"]:
        th = next((u for u in sumH["tables"] if u["name"] == t["name"]), None)
        if th is None or t.get("format") != "casa":
            tables[t["name"]] = {"equal": False, "why": "missing or not casa"}
            continue
        tables[t["name"]] = table_equal(t["path"], th["path"])
        appended = Path(t["path"] + ".append")
        if appended.exists():
            tables[t["name"] + ".append"] = table_equal(
                str(appended), th["path"] + ".append"
            )
    result["gate2b"] = {
        "tables": tables,
        "pass": names_s == names_h
        and bool(tables)
        and all(v["equal"] for v in tables.values()),
        "all_files_identical": all(v.get("files_identical") for v in tables.values()),
    }

    # Gate 2c: every FITS file under <run>/image/.
    fs = sorted(p.relative_to(s_run) for p in (s_run / "image").rglob("*.fits"))
    fh = sorted(p.relative_to(h_run) for p in (h_run / "image").rglob("*.fits"))
    images = {str(f): fits_equal(s_run / f, h_run / f) for f in fs if f in fh}
    result["gate2c"] = {
        "files": len(fs),
        "images": images,
        "pass": fs == fh and bool(fs) and all(v["equal"] for v in images.values()),
    }

    # Gate 2d: flag versions, FLAG and FLAG_ROW in order.
    vs, vh = flag_versions(s_ms), flag_versions(h_ms)
    result["gate2d"] = {
        "versions_S": [v[0] for v in vs],
        "versions_H": [v[0] for v in vh],
        "pass": len(vs) == len(vh)
        and bool(vs)
        and all(a[1:] == b[1:] for a, b in zip(vs, vh))
        and [re.sub(r"_\d{8}T.*", "", v[0]) for v in vs]
        == [re.sub(r"_\d{8}T.*", "", v[0]) for v in vh],
    }

    # Reported: stage summaries and state with times and arm paths removed.
    reported = {}
    for st in STAGES:
        a = s_run / st / "summary.json"
        b = h_run / st / "summary.json"
        if a.is_file() and b.is_file():
            reported[st] = json_diff(
                scrub(json.loads(a.read_text()), s_arm),
                scrub(json.loads(b.read_text()), h_arm),
            )
    reported["state"] = json_diff(
        scrub(json.loads((s_run / "state.json").read_text()), s_arm),
        scrub(json.loads((h_run / "state.json").read_text()), h_arm),
    )
    result["reported_summary_differences"] = reported
    result["pass"] = all(
        result[g]["pass"] for g in ("gate1", "gate2a", "gate2b", "gate2c", "gate2d")
    )
    Path(out).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                g: result[g]["pass"]
                for g in ("gate1", "gate2a", "gate2b", "gate2c", "gate2d")
            }
        )
    )
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
