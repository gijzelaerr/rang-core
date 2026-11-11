# SPDX-License-Identifier: GPL-3.0-or-later
"""One line per G6 case from its JSON files (research/g6-predict.md).

python summary.py OUTDIR LABEL"""

import json
import pathlib
import re
import sys


def peak_gb(path):
    try:
        text = pathlib.Path(path).read_text()
    except FileNotFoundError:
        return None
    m = re.search(r"Maximum resident set size \(kbytes\): (\d+)", text)
    return int(m.group(1)) * 1024 / 1e9 if m else None


def main():
    o, label = pathlib.Path(sys.argv[1]), sys.argv[2]
    out = {"case": label}
    c = o / f"{label}-compare.json"
    if c.exists():
        c = json.loads(c.read_text())
        out.update(
            {
                k: c.get(k)
                for k in (
                    "criterion_1",
                    "criterion_2",
                    "rel_l2",
                    "max_abs_over_max_w",
                    "rows_g",
                    "rows_w",
                    "selected_rows",
                    "rows_differ",
                    "chan_differ",
                    "unselected_changed",
                    "other_columns_changed",
                )
            }
        )
        h = o / f"{label}-rang-hash.json"
        if h.exists():
            out["readback_equal"] = (
                json.loads(h.read_text())["sha256_rang"] == c["sha256_g"]
            )
        out["desc"] = c.get("desc_g")
    d = o / f"{label}-dft.json"
    if d.exists():
        d = json.loads(d.read_text())
        out["criterion_3"] = d["criterion_3"]
        out["dft"] = {k: v for k, v in d.items() if k.startswith("MODEL")}
        out["dft_conjugate"] = d["conjugate_used"]
    out["peak_gb_gemclean"] = peak_gb(o / f"time-gemclean-{label}.txt")
    out["peak_gb_wsclean"] = peak_gb(o / f"time-wsclean-{label}.txt")
    text = json.dumps(out, indent=1, sort_keys=True, default=str)
    (o / f"{label}-summary.json").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
