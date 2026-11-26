# SPDX-License-Identifier: MIT
"""research/k-ambiguity.md section 9: the (block, antenna, scan range)
table of `ka_scan.py` outputs (`OUT/<tag>/<ms>.json`), as Markdown rows,
and a JSON summary.

    python ka_table.py OUT SUMMARY.json
"""

import json
import sys
from pathlib import Path


def main(out, summary):
    rows, seen = {}, {}
    for f in sorted(Path(out).glob("*/*.json")):
        d = json.loads(f.read_text())
        tag = f.parent.name
        s = seen.setdefault(tag, {"ms": 0, "scans": 0, "max_fraction_not_hit": 0.0})
        s["ms"] += 1
        s["scans"] += len(d["scans"])
        s["max_fraction_not_hit"] = max(s["max_fraction_not_hit"], d["max_fraction_not_hit"])
        for h in d["hits"]:
            key = (tag, h["name"])
            label = f.stem if len(d["scans"]) == 1 else f"scan {h['scan']}"
            rows.setdefault(key, []).append(
                {"where": label, "flipped": h["flipped"], "rows": h["rows"],
                 "angle": h["step_angle"], "coherence": h["coherence"]}
            )
    out_rows = []
    for (tag, name), hs in sorted(rows.items()):
        frac = min(min(x / max(r, 1) for x, r in zip(h["flipped"], h["rows"])) for h in hs)
        coh = min(min(h["coherence"]) for h in hs)
        out_rows.append({"block": tag, "antenna": name, "where": [h["where"] for h in hs],
                         "min_fraction": round(frac, 3), "min_coherence": round(coh, 3)})  # fmt: skip
        print(f"| {tag} | {name} | {', '.join(h['where'] for h in hs)} | {frac:.2f} | {coh:.2f} |")
    Path(summary).write_text(json.dumps({"hits": out_rows, "scanned": seen}, indent=1))
    for tag, s in sorted(seen.items()):
        print(tag, s)


if __name__ == "__main__":
    main(*sys.argv[1:3])
