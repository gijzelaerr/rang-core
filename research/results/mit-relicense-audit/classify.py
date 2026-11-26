# SPDX-License-Identifier: MIT
"""The provenance register files.csv (research/mit-relicense-audit.md): totals
per class and per upstream, and the rewrite candidates per piece.

files.csv is edited by hand; it is the source of truth (since 2026-11-26; on
2026-11-17 this script wrote it from a table of its own). One row per tracked
source file (`.py`, `.sh`, `.rs`, `.cc`, `.wgsl`) under python/rang, core/src,
core/py/src, src and tools, plus the audit's rows for tests/:

    path, lines, class, upstream, licence, upstream_files, derived_lines_est,
    piece, decision

Own new code is one row: class `a`, upstream `-`, licence `-`, derived 0.
A derived file names its upstream with version or commit, the upstream's
licence, an estimate of the lines that follow upstream code, and in `piece`
the functions or sections that do, so that rewrites can be chosen per piece.
`decision` holds an owner decision (for example "rewrite later (owner
2026-11-26)"). Classes are the audit's: a, b-permissive, b-copyleft, c-src,
c, d. tests/test_licence_register.py and tools/prepush_check.py require a row
for every file in scope and a tracked file for every row.

    python research/results/mit-relicense-audit/classify.py           # totals
    python research/results/mit-relicense-audit/classify.py --lines   # also refresh `lines`
"""

import csv
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SCOPE = ("python/rang", "core/src", "core/py/src", "src", "tools")
SUFFIXES = {".py", ".sh", ".rs", ".cc", ".wgsl"}
COLUMNS = [
    "path",
    "lines",
    "class",
    "upstream",
    "licence",
    "upstream_files",
    "derived_lines_est",
    "piece",
    "decision",
]
ORDER = ["a", "b-permissive", "b-copyleft", "c-src", "c", "d"]
COPYLEFT = {"b-copyleft", "c-src", "d"}


def read():
    with open(HERE / "files.csv", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def in_scope():
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", *SCOPE],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [p for p in out if Path(p).suffix in SUFFIXES]


def main(refresh):
    rows = read()
    paths = {r["path"] for r in rows}
    missing = sorted(set(in_scope()) - paths)
    gone = sorted(p for p in paths if not (ROOT / p).is_file())
    if missing or gone:
        sys.exit(f"files.csv: no row for {missing}; row without a file for {gone}")
    if refresh:
        for r in rows:
            r["lines"] = str(len((ROOT / r["path"]).read_bytes().splitlines()))
        rows.sort(key=lambda r: r["path"])
        with open(HERE / "files.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, COLUMNS, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    per = defaultdict(lambda: [0, 0, 0])
    perup = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        n, d, cls = int(r["lines"]), int(r["derived_lines_est"]), r["class"]
        accs = [per[cls]]
        if r["upstream"] != "-":
            accs.append(perup[(r["upstream"], cls)])
        for acc in accs:
            acc[0] += 1
            acc[1] += n
            acc[2] += d
    print("| class | files | lines | derived lines (est.) |")
    for k in ORDER:
        print(f"| {k} | {per[k][0]} | {per[k][1]:,} | {per[k][2]:,} |")
    tot = [sum(v[i] for v in per.values()) for i in range(3)]
    print(f"| total | {tot[0]} | {tot[1]:,} | {tot[2]:,} |")
    print()
    print("| upstream | class | files | lines | derived lines (est.) |")
    for (up, cls), v in sorted(perup.items(), key=lambda kv: -kv[1][2]):
        print(f"| {up} | {cls} | {v[0]} | {v[1]:,} | {v[2]:,} |")
    print()
    print("Rewrite candidates (copyleft classes, by derived lines):")
    print("| path | class | derived | upstream | licence | piece | decision |")
    cand = [r for r in rows if r["class"] in COPYLEFT]
    for r in sorted(cand, key=lambda r: -int(r["derived_lines_est"])):
        print(
            f"| {r['path']} | {r['class']} | {r['derived_lines_est']} | "
            f"{r['upstream']} | {r['licence']} | {r['piece']} | {r['decision']} |"
        )


if __name__ == "__main__":
    main("--lines" in sys.argv[1:])
