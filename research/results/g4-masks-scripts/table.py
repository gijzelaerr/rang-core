"""table.py TAG RUN...: one Markdown row per run from score.py's JSON (research/g4-masks.md, 6)."""

import json
import os
import sys
from pathlib import Path

O = Path(os.environ.get("G4_OUT", "D:/rang/outputs/g4-20261109-01"))


def main():
    tag = sys.argv[1]
    print(
        "| run | dirty/PSF max diff | WSCIMGWG rel | BMAJ G/W − 1 | M2 fail | M3 fail "
        "| max flux diff | finishing G/W | majors G/W | σ max diff | verdicts |"
    )
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | --- |")
    for run in sys.argv[2:]:
        r = json.loads((O / "runs" / tag / f"score-{run}.json").read_text())
        rows = r["S"]["rows"]
        img = max(x.get("max_abs_diff_rel", 0) for x in rows)
        wg = max(x.get("wscimgwg_rel", 0) for x in rows)
        bm = [x["bmaj_rel"] for x in rows if "bmaj_rel" in x]
        cells = [run, f"{img:.1e}", f"{wg:.0e}", f"{max(bm):.3f}" if bm else "–"]
        if "M" in r:
            ap = r["M"]["apertures"]
            rel = [
                abs(a["flux_g"] - a["flux_w"]) / abs(a["flux_w"])
                for a in ap
                if abs(a["flux_w"]) > 10 * a["eps"]  # not the masked-out points
            ]
            cells += [
                f"{sum(not a['M2'] for a in ap)}/{len(ap)}",
                f"{sum(not a['M3'] for a in ap)}/{len(ap)}",
                f"{max(rel):.3f}" if rel else "–",
            ]
        else:
            cells += ["–"] * 3
        if "X" in r:
            x = r["X"]
            sd = [
                abs(c["sigma_g"] / c["sigma_w"] - 1)
                for c in x["rows"]
                if c.get("sigma_w")
            ]
            cells += [
                f"{x['finishing_g']}/{x['finishing_w']}",
                f"{x['majors_g']}/{x['majors_w']}",
                f"{max(sd):.3f}",
            ]
        else:
            cells += ["–"] * 3
        v = " ".join(
            f"{k} {'pass' if r[k]['pass'] else 'FAIL'}"
            for k in ("S", "B", "B'", "M", "X")
            if k in r
        )
        cells.append(v)
        print("| " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
