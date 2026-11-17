# SPDX-License-Identifier: MIT
"""The SPDX line every header-bearing file should carry after step 1 of the
relicensing (research/mit-relicense-audit.md, "Step 1 done: own code MIT").

Writes spdx.csv beside this script: one row per tracked file that has an SPDX
line, with its class and the expected licence expression.
`tests/test_spdx_headers.py` checks every file against it.

A file's class comes from, in order: HELD below; the audit's files.csv (the
shipped files); the class spdx.csv already records (the files outside the
audit's scope, reviewed by hand on 2026-11-17). A new file in none of them is
own code (class a) if its SPDX line is bare `MIT`, the owner's rule for new
code; with any other line it is an error until it is added to HELD with its
class. The test applies the same rule to files not yet listed.

- Class a and c: `MIT`. Class b-permissive: `MIT AND <upstream>` (`MIT` alone
  when the upstream is MIT; the upstream notice stays in the file).
  Every other class keeps the line it has (GPL or LGPL).

    python research/results/mit-relicense-audit/spdx.py           # write spdx.csv
    python research/results/mit-relicense-audit/spdx.py --apply   # also rewrite the lines
"""

import csv
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
LINE = re.compile(
    rb"SPDX-License-Identifier: ([A-Za-z0-9.+-]+(?: (?:AND|OR|WITH) [A-Za-z0-9.+-]+)*)"
)
MIT_CLASSES = {"a", "c"}
# Permissive upstream licence of each b-permissive file, as its header names it.
PERMISSIVE = {"MIT", "BSD-3-Clause"}

# Files kept GPL whatever else says: code that follows GPL or LGPL code or
# source, found among the files outside the audit's scope (2026-11-17).
HELD = {
    # AOFlagger 3.5 `SumThresholdMissing` transcribed (GPL-3.0); Tricolour's kernel.
    "tools/oracles/aoflagger/st_bridge.py": "b-copyleft",
    # Re-chains Tricolour's steps with AOFlagger's kernel semantics; Tricolour's
    # clamping kernel re-expressed.
    "tools/oracles/aoflagger/posthoc/s1_values.py": "b-copyleft",
    # Re-chains Tricolour's functions "exactly as" its flagger does.
    "tools/oracles/aoflagger/tricolour_dump.py": "d",
    # CARACal 8f7bb363 crosscal_worker.py's calls, line by line (GPL-2.0).
    "tools/oracles/casa/crosscal.py": "c-src",
    # Holds a verbatim copy of an older `applycal._field_angles` (c-src).
    "tools/oracles/w3b/angles_memory.py": "c-src",
    # Embeds MeerKAT positions from data/meerkat.itrf.txt (simms copy).
    "docs/_extra/interferometer/index.html": "d",
    # Shipped tests that transcribe CASA (files.csv; stamped 2026-11-17).
    "tests/test_e0_refant_extend.py": "b-copyleft",  # FlagAgentExtension.cc loops
    "tests/test_cal_fluxscale.py": "c-src",  # fluxscale rules in NumPy
    "tests/test_a3_casa_phase_weights.py": "c-src",  # divideCorrByModel in NumPy
}


def tracked_with_header():
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True
    ).stdout.split("\n")
    rows = []
    for p in out:
        if not p or Path(p).suffix in {".md", ".txt", ".csv", ".json"}:
            continue
        f = ROOT / p
        if not f.is_file():
            continue
        with open(f, "rb") as fh:
            head = fh.read(4096).split(b"\n")[:3]
        for line in head:
            m = LINE.search(line)
            if m:
                rows.append((p, m.group(1).decode()))
                break
    return rows


def read_csv(name):
    path = HERE / name
    if not path.is_file():
        return {}
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["path"]: r for r in csv.DictReader(fh)}


def expected(cls, current, upstream_licence):
    if cls in MIT_CLASSES:
        return "MIT"
    if cls == "b-permissive":
        # Before the change: `GPL-3.0-or-later AND <upstream>`; after: `MIT ...`.
        up = current.split(" AND ")[1:] or [upstream_licence]
        assert all(u in PERMISSIVE for u in up), (current, upstream_licence)
        rest = [u for u in up if u != "MIT"]
        return " AND ".join(["MIT", *rest])
    return current


def main(apply):
    audit = read_csv("files.csv")
    known = read_csv("spdx.csv")
    rows, unknown, tot = [], [], {}
    for p, cur in tracked_with_header():
        lic = audit[p]["licence"] if p in audit else "-"
        if p in HELD:
            cls = HELD[p]
        elif p in audit:
            cls = audit[p]["class"]
        elif p in known:
            cls = known[p]["class"]
        elif cur == "MIT":
            cls = "a"
        else:
            unknown.append(p)
            continue
        exp = expected(cls, cur, lic)
        rows.append((p, cls, exp))
        t = tot.setdefault(exp, [0, 0])
        t[0] += 1
        t[1] += len((ROOT / p).read_bytes().splitlines())
        if apply and exp != cur:
            f = ROOT / p
            data = f.read_bytes()
            old = f"SPDX-License-Identifier: {cur}".encode()
            new = f"SPDX-License-Identifier: {exp}".encode()
            assert data.count(old) >= 1
            f.write_bytes(data.replace(old, new, 1))
    if unknown:
        sys.exit("not bare MIT and not classified, add to HELD: " + ", ".join(unknown))
    rows.sort()
    with open(HERE / "spdx.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["path", "class", "spdx"])
        w.writerows(rows)
    print("| SPDX | files | lines |")
    for k, (f, n) in sorted(tot.items(), key=lambda kv: -kv[1][1]):
        print(f"| {k} | {f} | {n:,} |")


if __name__ == "__main__":
    main("--apply" in sys.argv[1:])
