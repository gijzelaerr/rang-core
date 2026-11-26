"""DL4s stage 3: the compact archive of every block's screen.json.

    python dl4s_summary.py BLOCKS_DIR OUT.json

Per block, arm and reading: outliers and uncaught outliers per term, the
(block, term) instances (literal and 5-sigma readings), and the uncaught
outliers of the key-on arm under the amplitude reading (2.4's count).
"""

import json
import sys
from pathlib import Path

KEEP = ("field", "antenna", "interval", "scan", "pol", "channels",
        "uncaught_channels", "max_dev", "value", "significant_5sigma")  # fmt: skip


def main(blocks, out):
    res = {"blocks": {}, "instances": {}}
    for f in sorted(Path(blocks).glob("*/screen.json")):
        r = json.loads(f.read_text())
        b = {}
        for arm in ("off", "on"):
            for rd in ("amplitude", "complex"):
                x = r[arm][rd]
                b[f"{arm}/{rd}"] = {
                    "terms": {
                        n: {
                            "outliers": len(v["outliers"]),
                            "uncaught": sum(
                                not o["caught_a"] and not o["caught_b"]
                                for o in v["outliers"]
                            ),
                            "solutions": v["solutions"],
                            "flagged": v["flagged"],
                            "no_median": v["no_median"],
                            "intervals_per_field": v["intervals_per_field"],
                        }
                        for n, v in x["terms"].items()
                    },
                    "instances": x["instances"],
                }
        b["uncaught_on_amplitude"] = {
            n: [
                {k: o[k] for k in KEEP}
                for o in v["outliers"]
                if not o["caught_a"] and not o["caught_b"]
            ]
            for n, v in r["on"]["amplitude"]["terms"].items()
        }
        b["k_zero_start_removed"] = r["k_zero_start_removed"]
        b["k_zero_start_added"] = r["k_zero_start_added"]
        res["blocks"][r["block"]] = b
    for key in ("on/amplitude", "on/complex", "off/amplitude", "off/complex"):
        for sig in ("literal", "significant"):
            pairs = sorted(
                p
                for b in res["blocks"].values()
                for p in b[key]["instances"][sig]["block_terms"]
            )
            res["instances"][f"{key}/{sig}"] = {"n": len(pairs), "pairs": pairs}
    Path(out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    for k, v in res["instances"].items():
        print(k, v["n"], v["pairs"])
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
