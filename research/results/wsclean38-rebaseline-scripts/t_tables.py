# SPDX-License-Identifier: MIT
"""t_tables.py T_DIR OUT_DIR: arm T's compact tables (research/wsclean38-rebaseline.md 7.4).

Reporting only, written after t_score.py (frozen) ran; it decides nothing. It reads the same
job records through t_score's own functions and writes:
- OUT_DIR/t-clean-reading.json: lead sets and 3.8-against-3.7 verdicts on the clean runs only
  (spoiled jobs dropped, every cell kept that has at least one clean run), the second reading
  section 5 asks to report when the clean rule cannot apply;
- OUT_DIR/t-compact.md: medians per sky and thread count, GeMClean/WSClean ratios for pairs A and
  B, 3.8/3.7 ratios with verdicts, and tonight's 3.7 against gemclean-speed's 2026-11-04 medians.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import t_score as ts  # noqa: E402

GRIDS = ("minres", "nominres", "minres-mgain0.9", "minres-mgain0.95")


def cells_of(root):
    cells = {}
    for rep in sorted(p for p in root.glob("rep*") if p.is_dir()):
        for im in ("w3.7", "w3.8", "g", "gc"):
            d = rep / im
            if d.is_dir():
                for name, rec in ts.jobs(d).items():
                    sky, _, grid, _, j = name.split("-")
                    cells.setdefault((im, sky, grid, int(j[1:])), []).append(rec)
    for m in ("0.9", "0.95"):
        for im in ("w3.7", "w3.8"):
            d = root / f"mgain{m}" / im
            if d.is_dir():
                for name, rec in ts.jobs(d).items():
                    sky, _, grid, _, j = name.split("-")
                    cells.setdefault((im, sky, f"minres-mgain{m}", int(j[1:])), []).append(rec)
    return cells


def reading(cells, clean):
    def stat(im, sky, grid, t):
        v = cells.get((im, sky, grid, t))
        if not v:
            return None
        med, spread, n = ts.median_spread(v, clean)
        return None if n == 0 else {"median": med, "spread": spread, "n": n}

    table, lead, faster = {}, {}, {}
    for t in ts.THREADS:
        for sky in ts.SKIES:
            row = {f"{im}-{g}": stat(im, sky, g, t) for im in ("w3.7", "w3.8") for g in GRIDS}
            row["g"] = stat("g", sky, "nominres", t)
            row["gc"] = stat("gc", sky, "nominres", t)
            table[f"{sky}-j{t}"] = row
            for g in GRIDS:
                x, y = row[f"w3.7-{g}"], row[f"w3.8-{g}"]
                if x and y:
                    bound = max(x["spread"], y["spread"])
                    rel = (x["median"] - y["median"]) / x["median"]
                    faster[f"{sky}-j{t}-{g}"] = {
                        "ratio_38_37": y["median"] / x["median"],
                        "bound": bound,
                        "verdict": "3.8 faster" if rel > bound
                        else ("3.8 slower" if -rel > bound else "level"),
                    }
        for v in ("3.7", "3.8"):
            a, b = [], []
            for sky in ts.SKIES:
                row = table[f"{sky}-j{t}"]
                if row["g"] and row[f"w{v}-nominres"] and row["g"]["median"] < row[f"w{v}-nominres"]["median"]:
                    a.append(sky)
                ws = [row[f"w{v}-{g}"]["median"] for g in GRIDS if g != "nominres" and row[f"w{v}-{g}"]]
                if row["gc"] and ws and row["gc"]["median"] < min(ws):
                    b.append(sky)
            lead[f"A-j{t}-{v}"], lead[f"B-j{t}-{v}"] = a, b
    return table, lead, faster


def main():
    root, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    cells = cells_of(root)
    table, lead, faster = reading(cells, clean=False)
    ctable, clead, cfaster = reading(cells, clean=True)
    stands = all(clead[f"{p}-j{t}-3.7"] == clead[f"{p}-j{t}-3.8"] for p in "AB" for t in ts.THREADS)
    (out / "t-clean-reading.json").write_text(json.dumps(
        {"note": "reported, not the rule: spoiled jobs dropped (section 5's second reading)",
         "lead_sets": clead, "outcome": "stands" if stands else "changed",
         "w38_vs_w37": cfaster, "table": ctable}, indent=1))

    f = lambda c: f"{c['median']:.1f}" if c else "-"  # noqa: E731
    L = ["# Arm T, compact (all runs: the frozen rule's reading)", ""]
    for t in ts.THREADS:
        L += [f"## -j {t}", "",
              "| sky | g | gc | 3.7 nom | 3.8 nom | 3.7 best min | 3.8 best min | A g/3.7 | A g/3.8 | B gc/3.7 | B gc/3.8 |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for sky in ts.SKIES:
            r = table[f"{sky}-j{t}"]
            best = {v: min(r[f"w{v}-{g}"]["median"] for g in GRIDS if g != "nominres" and r[f"w{v}-{g}"]) for v in ("3.7", "3.8")}
            g, gc = r["g"]["median"], r["gc"]["median"]
            L.append(f"| {sky} | {g:.1f} | {gc:.1f} | {f(r['w3.7-nominres'])} | {f(r['w3.8-nominres'])} | "
                     f"{best['3.7']:.1f} | {best['3.8']:.1f} | {g / r['w3.7-nominres']['median']:.2f} | "
                     f"{g / r['w3.8-nominres']['median']:.2f} | {gc / best['3.7']:.2f} | {gc / best['3.8']:.2f} |")
        L.append("")
    L += ["## 3.8 / 3.7 (verdict under the spread rule; mgain cells are one run, spread 0)", "",
          "| sky-j | minres | nominres | mgain 0.9 | mgain 0.95 |", "|---|---|---|---|---|"]
    for t in ts.THREADS:
        for sky in ts.SKIES:
            cs = [faster.get(f"{sky}-j{t}-{g}") for g in GRIDS]
            L.append(f"| {sky}-j{t} | " + " | ".join(
                f"{c['ratio_38_37']:.3f} {c['verdict'].replace('3.8 ', '')}" if c else "-" for c in cs) + " |")
    L += ["", "## Host control: tonight's 3.7 / gemclean-speed 2026-11-04", "",
          "| j-grid | " + " | ".join(ts.SKIES) + " |", "|---|" + "---:|" * len(ts.SKIES)]
    for t in ts.THREADS:
        for g in ("minres", "nominres"):
            L.append(f"| j{t} {g} | " + " | ".join(
                f"{table[f'{s}-j{t}'][f'w3.7-{g}']['median'] / ts.OLD[t][g][i]:.3f}" for i, s in enumerate(ts.SKIES)) + " |")
    L += ["", "## Lead sets", "", "| set | all runs (rule) | clean runs only (reported) |", "|---|---|---|"]
    for k in lead:
        L.append(f"| {k} | {' '.join(lead[k]) or '-'} | {' '.join(clead[k]) or '-'} |")
    (out / "t-compact.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
