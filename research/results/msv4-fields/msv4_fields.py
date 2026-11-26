# SPDX-License-Identifier: MIT
"""C1 and C6 re-measured after amendment A3 (research/msv4-cli.md section 10).

Steps (ROOT is `D:/rang/outputs/msv4-fields-<date>`; M6's root is read only):

    copy ROOT        store copies of M6's `before` stores (both arms, every case)
    cli ROOT         M7's `cli` step unchanged: C1 (and C4), run-directory snapshots
    products ROOT    M7's `products` step unchanged: C6 with its frozen keys
    fieldids ROOT    the declared addition: each group's field_id against the MSv2's
    check ROOT OUT   the A3 rule over the step logs, written to OUT

M7's harness (`../msv4-cli/msv4_cli.py`) is imported, not copied, so its
comparators are the frozen ones.
"""

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
_spec = importlib.util.spec_from_file_location(
    "msv4_cli", HERE.parents[1] / "msv4-cli" / "msv4_cli.py"
)
m7 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m7)


def copy(root):
    root = Path(root)
    entry = {}
    for case, (src, _) in m7.CASES.items():
        for arm in m7.ARMS:
            before = m7.m6_store(arm, src, "before")
            entry[f"{case}/{arm}"] = str(before)
            m7._fresh(before, m7.store(root, arm, case, "cli"))
    m7._log(root, "copy", "sources", entry)


def fieldids(root):
    root = Path(root)
    for case in m7.CASES:
        for arm in m7.ARMS:
            snap = root / "products" / arm / case
            if case in m7.NO_MSV2 or not snap.exists():
                m7._log(root, "fieldids", f"{case}/{arm}", {"ids": "not measured"})
                continue
            ya = json.loads((snap / "rang-run" / "flag" / "summary.json").read_text())
            ms_run = m7.M6 / "msv2" / f"{case}.ms.rang-run"
            yb = json.loads((ms_run / "flag" / "summary.json").read_text())
            want = {(g["field"], str(g["scan"])): g["field_id"] for g in yb["groups"]}
            got = {}
            for g in ya["groups"]:
                got.setdefault((g["field"], str(g["scan"])), set()).add(g["field_id"])
            misses = []
            for key, ids in sorted(got.items()):
                expect = {want.get(key)} if arm == "xradio" else {None}
                if ids != expect:
                    misses.append(
                        f"{key}: {sorted(ids, key=str)} vs {sorted(expect, key=str)}"
                    )
            m7._log(
                root,
                "fieldids",
                f"{case}/{arm}",
                {
                    "ids": "match" if not misses else "mismatch",
                    "misses": misses,
                    "groups": len(ya["groups"]),
                    "field_ids": sorted({str(i) for v in got.values() for i in v}),
                    "store_fields": sorted({g["store_field"] for g in ya["groups"]}),
                },
            )


def check(root, out):
    root = Path(root)
    logs = {
        s: json.loads((root / f"{s}.json").read_text())
        for s in ("cli", "products", "fieldids")
    }
    table, ok = {}, True
    for case in m7.CASES:
        if case in m7.NOT_MEASURED:
            continue
        for arm in m7.ARMS:
            key = f"{case}/{arm}"
            c1 = logs["cli"].get(key, {}).get("c1", "missing")
            c6 = logs["products"].get(key, {}).get("c6", "missing")
            ids = logs["fieldids"].get(key, {}).get("ids", "missing")
            row = {"c1": c1, "c6": c6, "field_ids": ids}
            table[key] = row
            if case not in m7.DECIDING:
                continue
            ok &= c1 == "match"
            if case not in m7.NO_MSV2:
                ok &= c6 == "match" and ids == "match"
    receipt = {
        "rule": "research/msv4-cli.md section 10 (A3): C1 and C6 (+ field_id) on every "
        "measured deciding case of both arms",
        "outcome": "pass" if ok else "fail",
        "cases": table,
    }
    Path(out).write_text(json.dumps(receipt, indent=1, sort_keys=True))
    print(json.dumps({"outcome": receipt["outcome"]}))


def main(argv):
    step, root, *rest = argv
    {
        "copy": copy,
        "cli": m7.cli,
        "products": m7.products,
        "fieldids": fieldids,
        "check": check,
    }[step](root, *rest)


if __name__ == "__main__":
    main(sys.argv[1:])
