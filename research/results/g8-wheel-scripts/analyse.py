"""analyse.py: the gates and tables of research/g8-wheel.md from D:/rang/outputs/g8-20261110-01,
and the archive research/results/g8-wheel.json."""

import json
import os
import statistics
import sys
from pathlib import Path

OUT = Path(os.environ.get("G8_OUT", "D:/rang/outputs/g8-20261110-01"))
ARCHIVE = Path(__file__).resolve().parents[1] / "g8-wheel.json"


def load(path):
    return json.loads(Path(path).read_text())


def identity():
    res = {}
    for f in sorted((OUT / "identity").glob("*/*/result.json")):
        r = load(f)
        res[(r["arm"], r["case"])] = r
    pairs = [
        ("A0", "SB0", "SB", "s1-def"),
        ("A1", "WH", "SB", "s1-def"),
        ("A1", "WH", "SB", "s1-d6"),
        ("A1", "WH", "SB", "d1c1-def"),
        ("A2", "WHL", "SBL", "s1-def"),
        ("A2", "WHL", "SBL", "d1c1-def"),
        ("rep", "WV3", "SB", "s1-def"),
        ("rep", "WF", "SB", "s1-def"),
    ]
    rows = []
    for gate, a, b, case in pairs:
        if (a, case) not in res or (b, case) not in res:
            rows.append({"gate": gate, "a": a, "b": b, "case": case, "missing": True})
            continue
        x, y = res[(a, case)], res[(b, case)]
        ha, hb = x["sha256"], y["sha256"]
        same = sorted(k for k in ha if hb.get(k) == ha[k])
        rows.append(
            {
                "gate": gate, "a": a, "b": b, "case": case, "rc": [x["rc"], y["rc"]],
                "files": len(ha), "identical": len(same) == len(ha) == len(hb) and len(ha) > 0,
                "differ": sorted(set(ha) ^ set(hb) | {k for k in ha if hb.get(k) != ha[k]}),
            }
        )  # fmt: skip
    return rows, {f"{a}/{c}": r for (a, c), r in res.items()}


def timings():
    runs = {}
    for f in sorted((OUT / "runs").glob("*/timing.json")):
        r = load(f)
        runs[r["run"]] = r
    return runs


def cell(runs, arm, j):
    rs = [r for r in runs.values() if r["arm"] == arm and r["j"] == j and r["rc"] == 0]
    return sorted(rs, key=lambda r: r["rep"])


def summary(runs):
    rows = []
    for arm in ("SB", "WH", "WV3", "WF", "SBL", "WHL"):
        for j in (16, 1):
            rs = cell(runs, arm, j)
            if not rs:
                continue
            walls = [r["wall_s"] for r in rs]
            cpu = [(r.get("user_s", 0) + r.get("sys_s", 0)) / r["wall_s"] for r in rs]
            mem = [
                r.get("peak_working_set_bytes") or r.get("max_rss_bytes") or 0
                for r in rs
            ]
            rows.append(
                {
                    "arm": arm, "j": j, "runs": len(rs), "wall_median": statistics.median(walls),
                    "wall_min": min(walls), "wall_max": max(walls),
                    "cpu_per_wall": statistics.median(cpu), "peak_gb": max(mem) / 1e9,
                    "spoiled": sum(r["spoiled"] for r in rs),
                    "commit_gb": max(r.get("peak_job_commit_bytes", 0) for r in rs) / 1e9,
                }
            )  # fmt: skip
    return rows


def ratios(runs, arm, ref):
    out = {}
    for j in (16, 1):
        a = {r["rep"]: r["wall_s"] for r in cell(runs, arm, j)}
        b = {r["rep"]: r["wall_s"] for r in cell(runs, ref, j)}
        if not a or not b:
            continue
        mb = statistics.median(b.values())
        # Paired by repeat; a cell with one repeat against the median of the other (section 4).
        if len(a) == 1 and len(b) > 1:
            pairs = [a[k] / mb for k in a]
        else:
            pairs = [a[k] / b[k] if k in b else a[k] / mb for k in sorted(a)]
        out[j] = {"pairs": pairs, "median": statistics.median(pairs)}
    return out


def pilot_identity(runs):
    """FITS hashes of every arm's pilot runs against SB's (and SBL's)."""
    out = {}
    for arm, ref in (
        ("WH", "SB"),
        ("WV3", "SB"),
        ("WF", "SB"),
        ("WHL", "SBL"),
        ("SB", "SB"),
    ):
        refs = {
            json.dumps(r["sha256"], sort_keys=True)
            for r in cell(runs, ref, 16) + cell(runs, ref, 1)
        }
        mine = [
            json.dumps(r["sha256"], sort_keys=True)
            for r in cell(runs, arm, 16) + cell(runs, arm, 1)
        ]
        if refs and mine:
            out[arm] = {
                "runs": len(mine),
                "distinct_ref": len(refs),
                "all_equal_ref": all(m in refs for m in mine) and len(refs) == 1,
            }
    return out


def main():
    rows, ident = identity()
    runs = timings()
    rec = {
        "identity": rows,
        "identity_runs": ident,
        "summary": summary(runs),
        "ratios": {f"{a}/{b}": ratios(runs, a, b) for a, b in (("WH", "SB"), ("WV3", "SB"), ("WF", "SB"), ("WF", "WH"), ("WV3", "WH"), ("WHL", "SBL"))},
        "pilot_identity": pilot_identity(runs),
        "startup": {a: load(p) for a in ("SB", "WH") if (p := OUT / "startup" / a / "walls.json").exists()},
        "runs": runs,
    }  # fmt: skip
    for p in sorted((OUT / "wheels").glob("*/provenance.txt")) + sorted(
        (OUT / "bin").glob("*.provenance")
    ):
        rec.setdefault("provenance", {})[p.parent.name + "/" + p.name] = (
            p.read_text().strip()
        )
    for p in sorted((OUT / "wheels").glob("WHL/*.tsv")):
        rec.setdefault("linux_build", {})[p.name] = p.read_text()
    ARCHIVE.write_text(json.dumps(rec, indent=1, default=str) + "\n")
    for r in rows:
        print(r)
    for r in rec["summary"]:
        print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})
    for k, v in rec["ratios"].items():
        print(
            k,
            {
                j: (round(x["median"], 4), [round(p, 4) for p in x["pairs"]])
                for j, x in v.items()
            },
        )
    print(rec["pilot_identity"])
    for a, w in rec["startup"].items():
        print(
            "startup",
            a,
            round(statistics.median(w), 4),
            round(min(w), 4),
            round(max(w), 4),
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
