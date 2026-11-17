# SPDX-License-Identifier: MIT
"""research/gemclean-memory2.md: a run against the baseline on one field: every
FITS file's SHA-256, the report's `entries`, `image-mask.json`, and memtime.py's
figures.

    compare.py RUNS_DIR FIELD_TAG RUN_TAG [BASE_TAG]   -> JSON on stdout
"""

import json
import sys
from pathlib import Path


def load(d):
    sha = dict(
        (line.split()[1].lstrip("*"), line.split()[0])
        for line in (d / "fits.sha256").read_text().splitlines()
        if line.strip()
    )
    rep = json.loads((d / "image-report.json").read_text(encoding="utf-8"))
    mask = (d / "image-mask.json").read_text(encoding="utf-8")
    t = json.loads((d / "time.json").read_text())
    return sha, rep.get("entries"), mask, t


def main():
    runs, field, tag = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    base = sys.argv[4] if len(sys.argv) > 4 else "base"
    a, b = load(runs / field / base), load(runs / field / tag)
    keys = ("peak_rss_gb", "peak_working_set_gib", "peak_private_gib", "wall_s")
    out = {
        "field": field,
        "run": tag,
        "against": base,
        "fits": len(a[0]),
        "fits_identical": a[0] == b[0],
        "entries_identical": a[1] == b[1],
        "mask_identical": a[2] == b[2],
        "exit": [a[3]["exit"], b[3]["exit"]],
        "base": {k: a[3][k] for k in keys},
        "run_figures": {k: b[3][k] for k in keys},
        "rss_ratio": round(b[3]["peak_rss_gb"] / a[3]["peak_rss_gb"], 3),
        "wall_ratio": round(b[3]["wall_s"] / a[3]["wall_s"], 3),
    }
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
