# SPDX-License-Identifier: GPL-3.0-or-later
"""W3 comparisons (research/w3-chunking.md, section 3).

    python compare.py hashes MS OUT.json       # SHA-256 per column and flag version, casacure
    python compare.py config CASE ARM NROWS OUT.yaml STRATEGY
    python compare.py verdict RUN OUT.json     # every arm against U, criteria 1-8

Columns are read with casacure (python-casacore's API, not rang's reader) in
row chunks, so hashing a whole-array MS stays within a few hundred MB. A
column's hash is over its cells in row order (C order, the dtype casacure
returns); flag versions are hashed the same way, keyed by their order and
stage prefix (their names carry the time).
"""

import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
from casacure.tables import table

CHUNK_BYTES = 128 << 20
ARMS = ("U", "D", "T", "M")


def _column_hash(t, name):
    nrows = t.nrows()
    first = t.getcol(name, 0, 1)
    per_row = max(1, first.nbytes)
    step = max(1, CHUNK_BYTES // per_row)
    digest = hashlib.sha256()
    for start in range(0, nrows, step):
        n = min(step, nrows - start)
        digest.update(np.ascontiguousarray(t.getcol(name, start, n)).tobytes())
    return digest.hexdigest()


def table_hashes(path, names=None):
    with table(str(path), readonly=True, ack=False) as t:
        out = {}
        for name in names or t.colnames():
            try:
                out[name] = _column_hash(t, name)
            except RuntimeError as exc:  # undefined cells
                out[name] = f"unreadable: {exc}"
        return out


def hashes(ms, out):
    ms = Path(ms)
    record = {"ms": str(ms), "columns": table_hashes(ms), "flag_versions": []}
    root = ms.with_name(ms.name + ".flagversions")
    listing = root / "FLAG_VERSION_LIST"
    if listing.is_file():
        for line in listing.read_text(encoding="utf-8").splitlines():
            name = line.split(" : ")[0].strip()
            if not name:
                continue
            record["flag_versions"].append(
                {
                    "name": name,
                    "key": re.sub(r"_\d{8}T\d{6}Z(_\d+)?$", "", name),
                    "columns": table_hashes(
                        root / f"flags.{name}", ["FLAG", "FLAG_ROW"]
                    ),
                }
            )
    Path(out).write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    return record


# -- configurations (section 2) ------------------------------------------------------

CASES = {
    "S": {"fcal": "J1939-6342", "gcal": "SIM-GCAL", "target": "SIM-TARGET"},
    "O": {"fcal": "J1939-6342", "gcal": None, "target": None},
    "W": {"fcal": "J1939-6342", "gcal": "SIM-GCAL", "target": "SIM-TARGET"},
    "L": {"fcal": "J1939-6342", "gcal": None, "target": None},
    # The merge check (research/w3-chunking.md 5.3): A1 small with C2e's chain.
    "C": {"fcal": "J1939-6342", "gcal": "SIM-GCAL", "target": None},
}
TINY = {"S": 7, "O": 7, "W": 4096, "C": 7}
CHAIN = [
    "calibrate:",
    "  model: {source: setjy}",
    "  refant: m000",
    "  primary:",
    "    terms:",
    "      - {type: K, name: K}",
    "      - {type: G, name: G, preapply: [K], interp: [linear]}",
    "      - {type: B, name: B, combine: scan, fillgaps: 2, preapply: [K, G]}",
    "      - {type: A, name: A}",
    "  secondary:",
    "    terms:",
    "      - {type: F, name: F, preapply: [K, B], interp: [linear, linear]}",
    "apply:",
    "  targets:",
    "    - {field: [J1939-6342], tables: [K, G, B]}",
    "    - {field: [SIM-GCAL], tables: [K, F, B], gainfield: [J1939-6342, nearest, J1939-6342]}",
]


def config(case, arm, nrows, out, strategy):
    c = CASES[case]
    data = []
    if arm == "U":
        data.append(f"chunk_rows: {int(nrows)}")
    elif arm == "T":
        data.append(f"chunk_rows: {TINY[case]}")
    elif arm == "M":
        data.append("memory_limit_gb: 2")
    fields = [f"  fcal: [{c['fcal']}]"]
    if c["gcal"]:
        fields.append(f"  gcal: [{c['gcal']}]")
    if c["target"]:
        fields.append(f"  target: [{c['target']}]")
    lines = ["schema: rang-config", "version: 1", "fields:", *fields]
    if data:
        lines += ["data:", *[f"  {d}" for d in data]]
    lines += ["flag:", f"  strategy: {strategy}"]
    if case == "C":
        lines += CHAIN
    elif case == "L":
        lines += [
            "calibrate:",
            "  model: {source: unity}",
            "  primary:",
            "    terms: [{type: complex, solint: int, freqint: 16}]",
        ]
    else:
        lines += [
            "calibrate:",
            "  model: {source: setjy}",
            "  primary:",
            "    terms:",
            "      - {type: complex, name: Gint, solint: int, freqint: 16}",
            "      - {type: complex, name: G2, solint: 2, freqint: 512}",
            # Amendment 1 (research/w3-chunking.md 2): the secondary term with a
            # setjy model is refused (C2d), so a third primary term takes its
            # settings: one time bin per scan, a bin per channel.
            "      - {type: complex, name: Gchan, solint: inf, freqint: 1}",
        ]
    Path(out).write_text("\n".join(lines) + "\n", encoding="utf-8")


# -- the verdict -----------------------------------------------------------------

VOLATILE = re.compile(
    r"(seconds|started|finished|updated|created|flag_version|store|strategy$|"
    r"receipt|ms$|path|chunking|rang_original_saved_now|restored_before|"
    # The merge check (research/w3-chunking.md 5.3): C2e's F step records the
    # path of its appended table.
    r"append_table)"
)


def _clean(value):
    """A summary without times, paths, flag-version names and chunking."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if not VOLATILE.search(str(k))}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def _files(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != "summary.json"
    }


def _peak_kb(path):
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if "Maximum resident set size" in line:
            return int(line.rsplit(":", 1)[1])
    return None


def _limit_gb(arm_dir):
    text = (arm_dir / "config.yaml").read_text(encoding="utf-8")
    m = re.search(r"memory_limit_gb:\s*([0-9.]+)", text)
    return float(m.group(1)) if m else 8.0


def verdict(run, out):
    run = Path(run)
    report = {"cases": {}}
    for case in CASES:
        arms = {a: run / f"{case}-{a}" for a in ARMS if (run / f"{case}-{a}").is_dir()}
        if not arms:
            continue
        rows = {}
        for arm, d in arms.items():
            stages = [
                s
                for s in ("flag", "calibrate", "apply")
                if (d / "hashes" / f"{s}.json").is_file()
            ]
            rows[arm] = {
                "hashes": {
                    s: json.loads((d / "hashes" / f"{s}.json").read_text())
                    for s in stages
                },
                "summaries": {
                    s: _clean(json.loads((d / "run" / s / "summary.json").read_text()))
                    for s in stages
                    if (d / "run" / s / "summary.json").is_file()
                },
                "stores": _files(d / "run" / "calibrate")
                if (d / "run" / "calibrate").is_dir()
                else {},
                "peak_gb": {
                    s: (_peak_kb(d / "timing" / f"{s}.txt") or 0) / (1 << 20)
                    for s in ("flag", "calibrate", "apply")
                    if (d / "timing" / f"{s}.txt").is_file()
                },
                "limit_gb": _limit_gb(d),
            }
        ref_arm = "U" if "U" in rows else "D"
        ref = rows[ref_arm]
        checks = {}
        for arm, r in rows.items():
            if arm == ref_arm:
                continue
            c = {}
            for stage, h in r["hashes"].items():
                base = ref["hashes"].get(stage)
                if base is None:
                    continue
                diff = sorted(
                    k
                    for k in set(h["columns"]) | set(base["columns"])
                    if h["columns"].get(k) != base["columns"].get(k)
                )
                c[f"{stage}: columns differing"] = diff
                fv = [(v["key"], v["columns"]) for v in h["flag_versions"]]
                fb = [(v["key"], v["columns"]) for v in base["flag_versions"]]
                c[f"{stage}: flag versions equal"] = fv == fb
            c["gain store files equal"] = r["stores"] == ref["stores"]
            c["summaries equal"] = {
                s: r["summaries"].get(s) == ref["summaries"].get(s)
                for s in r["summaries"]
            }
            checks[f"{arm} vs {ref_arm}"] = c
        memory = {
            arm: {
                "limit_gb": r["limit_gb"],
                "peak_gb": r["peak_gb"],
                "within": all(v <= r["limit_gb"] for v in r["peak_gb"].values()),
            }
            for arm, r in rows.items()
        }
        report["cases"][case] = {
            "reference": ref_arm,
            "checks": checks,
            "memory": memory,
        }
    Path(out).write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1))
    return report


if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    if cmd == "hashes":
        hashes(*args)
    elif cmd == "config":
        config(*args)
    elif cmd == "verdict":
        verdict(*args)
    else:
        raise SystemExit(__doc__)
