"""Tables and the frozen verdict of research/gemclean-stop28.md from the scored runs.

Usage: python examples/stop28_table.py dev | seen EPS | new EPS   (writes O/summary-<stage>.json)
"""

import json
import os
import sys
from pathlib import Path

O = Path(os.environ.get("O", "D:/rang/outputs/stop28-20261116"))
ARCH = Path("D:/rang/outputs/20261103-gemclean-heldout/sim/scores")
GRID = [0.005, 0.01, 0.02, 0.05, 0.10]


def tag(t):
    return f"e{t:g}"


def row(job, report_dir=None):
    rep = None
    if report_dir is not None:
        rep = json.loads(
            (report_dir / f"{job['name']}-report.json").read_text(encoding="utf-8")
        )["run"]
    majors = rep["major_cycles"] if rep else job["log"]["major_iterations"]
    comps = rep["components"] if rep else job["log"]["components"]
    return {
        "name": job["name"],
        "majors": majors,
        "components": comps,
        "false_mjy": job["false_flux_abs"] * 1e3,
        "q_qt": job["q_over_q_truth"],
        "rec_fw": job["recovery_all"]["flux_weighted"],
        "inner_peak_ujy": job["exact_residual_inner_peak_abs"] * 1e6,
        "cycle_peaks_ujy": [round(c["peak_start"] * 1e6, 3) for c in rep["cycles"]]
        if rep
        else None,
    }


def qd(e, d, eps):
    return {
        "false": e["false_mjy"] <= 1.1 * d["false_mjy"],
        "q": abs(e["q_qt"] / d["q_qt"] - 1) <= 0.002,
        "rec": e["rec_fw"] >= d["rec_fw"] - 0.005,
        "peak": e["inner_peak_ujy"] < (1 + eps) * 100.0,
    }


def qw(x, fast, plain):
    return {
        "false": x["false_mjy"] <= 1.6 * min(fast["false_mjy"], plain["false_mjy"]),
        "q": abs(x["q_qt"] / plain["q_qt"] - 1) <= 0.002,
        "rec": x["rec_fw"] >= plain["rec_fw"] - 0.005,
    }


def show(rows):
    for r in rows:
        print(
            f"  {r['name']:<34} maj {r['majors']:>2} comps {r['components']:>7} false {r['false_mjy']:7.3f} mJy "
            f"Q/Qt {r['q_qt']:.5f} rec {r['rec_fw']:.4f} inner peak {r['inner_peak_ujy']:7.2f}"
        )


def dev():
    out = {}
    for s in ("s1", "s2", "s3"):
        sc = json.loads((O / "scores" / f"dev-{s}.json").read_text(encoding="utf-8"))[
            "jobs"
        ]
        rows = {n: row(j, O / "dev") for n, j in sc.items()}
        print(s)
        show(rows.values())
        d = rows[f"{s}-default"]
        out[s] = {"rows": rows, "checks": {}}
        for t in GRID:
            e = rows[f"{s}-{tag(t)}"]
            c = qd(e, d, t)
            c["saves"] = d["majors"] - e["majors"] >= 1
            out[s]["checks"][tag(t)] = c
    chosen = None
    for t in GRID:
        if all(all(out[s]["checks"][tag(t)].values()) for s in out):
            chosen = t
            break
    print("chosen eps:", chosen)
    out["chosen"] = chosen
    return out


def heldout(stage, eps, wsclean):
    out = {"eps": eps, "skies": {}}
    skies = ("h1", "h2", "h3", "h4") if stage == "seen" else ("h5", "h6", "h7", "h8")
    for s in skies:
        sc = json.loads(
            (O / "scores" / f"{stage}-{s}.json").read_text(encoding="utf-8")
        )["jobs"]
        d = row(sc[f"{s}-default"], O / stage)
        e = row(sc[f"{s}-{tag(eps)}"], O / stage)
        w = json.loads((wsclean / f"wsclean-{s}.json").read_text(encoding="utf-8"))[
            "jobs"
        ]
        fast = row(
            next(j for n, j in w.items() if n.endswith(("-fast-j16", "-fast-j8")))
        )
        plain = row(next(j for n, j in w.items() if "-hogbom-" in n))
        print(s)
        show([d, e, fast, plain])
        rec = {
            "default": d,
            "rule": e,
            "wsclean_fast": fast,
            "wsclean_plain": plain,
            "q_d": qd(e, d, eps),
            "q_w_rule": qw(e, fast, plain),
            "q_w_default": qw(d, fast, plain),
            "saving": d["majors"] - e["majors"],
            "at_most_5": e["majors"] <= 5,
            "below_plain": e["majors"] < plain["majors"]
            and e["false_mjy"] <= plain["false_mjy"],
        }
        print(
            "  Q-D",
            rec["q_d"],
            "Q-W rule",
            rec["q_w_rule"],
            "Q-W default",
            rec["q_w_default"],
        )
        out["skies"][s] = rec
    sk = out["skies"].values()
    qd_ok = all(all(r["q_d"].values()) for r in sk)
    # Q-W counts only where the default itself passes that measure.
    qw_ok = all(
        all(v or not r["q_w_default"][k] for k, v in r["q_w_rule"].items()) for r in sk
    )
    mean_s = sum(r["saving"] for r in sk) / len(out["skies"])
    if not (qd_ok and qw_ok):
        verdict = "failure"
    elif mean_s < 1:
        verdict = "null"
    elif all(r["at_most_5"] for r in sk):
        verdict = "gain"
    else:
        verdict = "partial gain"
    out.update(
        mean_saving=mean_s,
        q_d_all=qd_ok,
        q_w_all=qw_ok,
        verdict=verdict,
        novelty=all(r["below_plain"] for r in sk),
    )
    print("mean saving", mean_s, "verdict", verdict, "novelty reading", out["novelty"])
    return out


def main():
    stage = sys.argv[1]
    if stage == "dev":
        out = dev()
    else:
        eps = float(sys.argv[2])
        out = heldout(stage, eps, ARCH if stage == "seen" else O / "scores")
    (O / f"summary-{stage}.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
