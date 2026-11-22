# SPDX-License-Identifier: MIT
"""t_score.py T_DIR [OUT.json]: arm T of research/wsclean38-rebaseline.md, sections 4 and 5.

Reads T_DIR/rep{1,2,3}/{w3.7,w3.8,g,gc}/ and T_DIR/mgain{0.9,0.95}/{w3.7,w3.8}/ (GNU time -v
wall, the load records of examples/gemclean_bench_run.sh), marks spoiled jobs (another process
above half a core before or after, other than the probe and the VM host), takes medians and
spreads, and applies the frozen rules: lead sets for pairs A and B per WSClean version and
thread count, 3.8 against 3.7 per sky and setting, and the host control against
gemclean-speed's 2026-11-04 medians. Prints a table and writes OUT.json (default
T_DIR/t-score.json).
"""

import json
import re
import statistics
import sys
from pathlib import Path

SKIES = ["s1", "s2", "s3", "h1", "h2", "h3", "h4"]
THREADS = [16, 1]
# Processes that do not spoil a job: the probe itself and the VM's host process.
IGNORE = re.compile(
    r"(?i)^(wmiprvse|top|powershell|vmmem\w*|vmmemwsl|system|memory compression)(#\d+)?$"
)
# gemclean-speed.md, native pass medians (s): WSClean 3.7 minres and nominres.
OLD = {
    16: {
        "minres": [17.6, 19.0, 16.2, 16.7, 16.4, 41.0, 27.9],
        "nominres": [27.2, 28.2, 22.3, 27.3, 24.0, 66.1, 34.5],
    },
    1: {
        "minres": [52.3, 58.1, 44.5, 52.7, 44.1, 97.1, 54.3],
        "nominres": [112, 115, 83.8, 113, 80.6, 192, 91.4],
    },
}


def wall(timing):
    text = timing.read_text()
    m = re.search(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): (\S+)", text)
    parts = [float(p) for p in m.group(1).split(":")]
    s = 0.0
    for p in parts:
        s = s * 60 + p
    return s


def spoiled(busy):
    """Other processes above half a core before or after the job, as listed."""
    if not busy.exists():
        return ["no load record"]
    found = []
    for line in busy.read_text().splitlines():
        if not line.strip() or line.startswith("=="):
            continue
        if line.startswith("(not available)"):
            continue
        fields = line.split()
        # Windows lines are "<percent> <name>"; WSL lines are top's, the command from field 12.
        name = " ".join(fields[1:]) if len(fields) < 12 else " ".join(fields[11:])
        base = Path(name.split()[0]).name if name else name
        if IGNORE.match(base) or IGNORE.match(name):
            continue
        found.append(line.strip()[:80])
    return found


def jobs(d):
    """name -> (wall, spoil list) for one imager directory."""
    out = {}
    for t in sorted((d / "timing").glob("*.txt")):
        name = t.stem
        out[name] = (wall(t), spoiled(d / "load" / f"{name}.busy.txt"))
    return out


def median_spread(runs, clean_only):
    vals = [w for w, s in runs if not (clean_only and s)]
    if not vals:
        return None, None, 0
    med = statistics.median(vals)
    return med, (max(vals) - min(vals)) / med, len(vals)


def main():
    root = Path(sys.argv[1])
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else root / "t-score.json"
    reps = sorted(p for p in root.glob("rep*") if p.is_dir())
    cells = {}  # (imager, sky, grid, threads) -> [(wall, spoil)]
    for rep in reps:
        for im in ("w3.7", "w3.8", "g", "gc"):
            d = rep / im
            if not d.is_dir():
                continue
            for name, rec in jobs(d).items():
                sky, _, grid, _, j = name.split("-")
                cells.setdefault((im, sky, grid, int(j[1:])), []).append(rec)
    for m in ("0.9", "0.95"):
        for im in ("w3.7", "w3.8"):
            d = root / f"mgain{m}" / im
            if not d.is_dir():
                continue
            for name, rec in jobs(d).items():
                sky, _, grid, _, j = name.split("-")
                cells.setdefault((im, sky, f"minres-mgain{m}", int(j[1:])), []).append(
                    rec
                )

    # Clean runs where every timed cell has at least two clean repeats, otherwise all (section 5).
    repeated = {k: v for k, v in cells.items() if "mgain" not in k[2]}
    clean_ok = all(sum(1 for _, s in v if not s) >= 2 for v in repeated.values())
    res = {
        "repeats": [p.name for p in reps],
        "clean_rule_applied": clean_ok,
        "spoiled": {
            "|".join(map(str, k)): [s for _, s in v if s]
            for k, v in cells.items()
            if any(s for _, s in v)
        },
    }

    def stat(im, sky, grid, t, clean):
        v = cells.get((im, sky, grid, t))
        if not v:
            return None
        med, spread, n = median_spread(v, clean)
        return {"median": med, "spread": spread, "n": n, "walls": [w for w, _ in v]}

    for label, clean in (("as_rule", clean_ok), ("all_runs", False)):
        table, lead = {}, {}
        for t in THREADS:
            for sky in SKIES:
                row = {}
                for im in ("w3.7", "w3.8"):
                    for grid in (
                        "minres",
                        "nominres",
                        "minres-mgain0.9",
                        "minres-mgain0.95",
                    ):
                        row[f"{im}-{grid}"] = stat(im, sky, grid, t, clean)
                row["g"] = stat("g", sky, "nominres", t, clean)
                row["gc"] = stat("gc", sky, "nominres", t, clean)
                table[f"{sky}-j{t}"] = row
            for v in ("3.7", "3.8"):
                a, b = [], []
                for sky in SKIES:
                    row = table[f"{sky}-j{t}"]
                    if (
                        row["g"]
                        and row[f"w{v}-nominres"]
                        and row["g"]["median"] < row[f"w{v}-nominres"]["median"]
                    ):
                        a.append(sky)
                    ws = [
                        row[f"w{v}-{g}"]["median"]
                        for g in ("minres", "minres-mgain0.9", "minres-mgain0.95")
                        if row[f"w{v}-{g}"]
                    ]
                    if row["gc"] and ws and row["gc"]["median"] < min(ws):
                        b.append(sky)
                lead[f"A-j{t}-{v}"] = a
                lead[f"B-j{t}-{v}"] = b
        stands = all(
            lead[f"{p}-j{t}-3.7"] == lead[f"{p}-j{t}-3.8"]
            for p in "AB"
            for t in THREADS
        )
        faster = {}
        for t in THREADS:
            for sky in SKIES:
                row = table[f"{sky}-j{t}"]
                for grid in (
                    "minres",
                    "nominres",
                    "minres-mgain0.9",
                    "minres-mgain0.95",
                ):
                    x, y = row[f"w3.7-{grid}"], row[f"w3.8-{grid}"]
                    if not (x and y):
                        continue
                    bound = max(x["spread"] or 0, y["spread"] or 0)
                    rel = (x["median"] - y["median"]) / x["median"]
                    faster[f"{sky}-j{t}-{grid}"] = {
                        "ratio_38_37": y["median"] / x["median"],
                        "verdict": "3.8 faster"
                        if rel > bound
                        else ("3.8 slower" if -rel > bound else "level"),
                    }
        host = {}
        for t in THREADS:
            for grid in ("minres", "nominres"):
                over = []
                for i, sky in enumerate(SKIES):
                    x = table[f"{sky}-j{t}"][f"w3.7-{grid}"]
                    if x and abs(x["median"] / OLD[t][grid][i] - 1) > 0.10:
                        over.append(sky)
                host[f"j{t}-{grid}"] = over
        n_over = sum(len(v) for v in host.values())
        res[label] = {
            "table": table,
            "lead_sets": lead,
            "outcome": "stands" if stands else "changed",
            "w38_vs_w37": faster,
            "host_control_over_10pct": host,
            "host_change": n_over >= 2,
        }
    res["outcome_valid"] = len(reps) >= 2
    if not res["outcome_valid"]:
        res["note"] = "fewer than two repeats: incomplete (section 5)"
    out_path.write_text(json.dumps(res, indent=1))

    r = res["as_rule"]
    print(
        f"repeats {res['repeats']}, clean rule applied: {clean_ok}, outcome: {r['outcome']}"
    )
    for k, v in r["lead_sets"].items():
        print(f"  lead {k}: {' '.join(v) or '-'}")
    for t in THREADS:
        print(f"-j {t}: sky  g  gc | 3.7 min nom mg.9 mg.95 | 3.8 min nom mg.9 mg.95")
        for sky in SKIES:
            row = r["table"][f"{sky}-j{t}"]

            def f(c):
                return f"{c['median']:6.1f}" if c else "     -"

            ws = " ".join(
                f(row[f"w{v}-{g}"])
                for v in ("3.7", "3.8")
                for g in ("minres", "nominres", "minres-mgain0.9", "minres-mgain0.95")
            )
            print(f"  {sky} {f(row['g'])} {f(row['gc'])} | {ws}")


if __name__ == "__main__":
    main()
