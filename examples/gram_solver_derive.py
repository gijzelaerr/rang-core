"""Derived numbers of research/gram-solver.md from the runs of gram_solver_jobs.sh.

Usage: python examples/gram_solver_derive.py ROOT

Reads ROOT/runs and ROOT/evals, writes ROOT/derived.json and prints tables:
per-operation instruction counts by difference, the fit against the visibility
count and its break-even, image differences between backends at the same iterate,
the accuracy study against the proved bounds, and the projection, marked as an
extrapolation. Needs numpy.
"""

import json
import sys
from pathlib import Path

import numpy as np

G = 1e9


def perf(run, name):
    path = run / "timing" / f"{name}.perf"
    out = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split(",")
            if len(parts) > 2 and parts[0].isdigit():
                out[parts[2].split(":")[0]] = int(parts[0])
    return out


def last_json(run, name):
    path = run / f"{name}.log"
    if not path.exists():
        return {}
    rows = [
        line
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.startswith("{")
    ]
    return json.loads(rows[-1]) if rows else {}


def evals(root, name):
    path = root / "evals" / f"{name}.jsonl"
    if not path.exists():
        return {}
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("{"):
            rec = json.loads(line)
            rows[Path(rec["file"]).name] = rec
    return rows


def counts(root, run):
    base = perf(run, "c-read").get("instructions", 0)
    out = {}
    per = {}
    for suffix, reps_exact, reps_gram in (
        ("", 10, 50),
        ("-k4", 5, 20),
        ("-k16", 5, 20),
    ):
        read = perf(run, f"c-read{suffix}").get("instructions", base)
        ex = perf(run, f"c-exact-apply{suffix}")
        setup = perf(run, f"c-gram-setup{suffix}")
        ga = perf(run, f"c-gram-apply{suffix}")
        if not (ex and setup and ga):
            continue
        vis = last_json(run, f"c-read{suffix}").get("vis")
        gram = (ga["instructions"] - setup["instructions"]) / reps_gram
        gram_cycles = (ga["cycles"] - setup["cycles"]) / reps_gram
        per[suffix or "-k1"] = {
            "vis": vis,
            "read_G": read / G,
            "exact_total_G": ex["instructions"] / G,
            "gram_setup_total_G": setup["instructions"] / G,
            "gram_apply_G": gram / G,
            "gram_apply_Gcycles": gram_cycles / G,
            "reps_exact": reps_exact,
        }
    out["per_stride"] = per
    psf_s, psf_a = perf(run, "c-psf-setup"), perf(run, "c-psf-apply")
    if psf_s and psf_a:
        out["psf_setup_total_G"] = psf_s["instructions"] / G
        out["psf_apply_G"] = (psf_a["instructions"] - psf_s["instructions"]) / 200 / G
        out["psf_apply_Gcycles"] = (psf_a["cycles"] - psf_s["cycles"]) / 200 / G
    return out


def difference(a, b):
    d = a - b
    return {
        "rel_l2": float(np.linalg.norm(d) / max(np.linalg.norm(b), 1e-300)),
        "sup": float(np.abs(d).max()),
        "l1": float(np.abs(d).sum()),
        "flux": float(d.sum()),
    }


def main(argv):
    root = Path(argv[1])
    run = root / "runs" / "s1"
    derived = {"counts": counts(root, run)}
    print(json.dumps(derived["counts"], indent=1))

    # The same iterates.
    matched = {}
    for k in (50, 100, 200, 300):
        a, b = run / f"m-gram-x{k}.f64", run / f"m-exact-x{k}.f64"
        if a.exists() and b.exists():
            matched[k] = difference(np.fromfile(a), np.fromfile(b))
    derived["matched"] = matched
    print("matched", json.dumps(matched, indent=1))

    # The minimiser of each operator, against the control: the same warm start and
    # iterations with exact outer cycles, so that solver noise cancels.
    ref_path = run / "acc-exact-x.f64"
    if ref_path.exists():
        ref = np.fromfile(ref_path)
        acc = {}
        for path in sorted(run.glob("*-x.f64")):
            if path.name.startswith(("acc-s", "c1", "r-")):
                acc[path.name] = difference(np.fromfile(path), ref)
        derived["images_against_control"] = acc
        print("images", json.dumps(acc, indent=1))

    # Fits in the visibility count N (millions): a pass is P(N), the setup beyond
    # the dirty image is S(N). A pass is total / (reps + 1/2): the dirty image is
    # half a pass (67 G against 131 G from sp-exact and c-exact-apply on S1).
    per = derived["counts"]["per_stride"]
    if len(per) >= 2:
        n = np.array([v["vis"] / 1e6 for v in per.values()])
        passes = np.array(
            [v["exact_total_G"] / (v["reps_exact"] + 0.5) for v in per.values()]
        )
        setup = np.array(
            [v["gram_setup_total_G"] - p / 2 for v, p in zip(per.values(), passes)]
        )
        apply_g = float(np.mean([v["gram_apply_G"] for v in per.values()]))
        pb, pa = np.polyfit(n, passes, 1)
        sb, sa = np.polyfit(n, setup, 1)
        derived["fit"] = {
            "n_millions": n.tolist(),
            "pass_G": passes.tolist(),
            "setup_beyond_dirty_G": setup.tolist(),
            "pass_G_per_million": pb,
            "pass_G_intercept": pa,
            "setup_G_per_million": sb,
            "setup_G_intercept": sa,
            "gram_apply_G": apply_g,
        }
        # EXTRAPOLATION, 2048² at this W: 3,200 FISTA iterations on the PSF (2.55 G
        # each with the solver's own work) or the Gram operator (22 G) and M = 9
        # outer cycles.
        inner_psf, inner_gram, k, m = 2.55, 22.0, 3200, 9
        rows = {}
        for big in (14.5, 100.0, 1e3, 1e4):
            p = pa + pb * big
            sg = sa + sb * big
            rows[str(big)] = {
                "pass_G": p,
                "psf_exact_T": (k * inner_psf + m * p) / 1e3,
                "psf_gram_T": (k * inner_psf + sg + m * apply_g) / 1e3,
                "gram_only_T": (k * inner_gram + sg) / 1e3,
                "exact_every_iteration_T": k * p / 1e3,
            }
        derived["projection_extrapolated"] = rows
        print(json.dumps(derived["fit"], indent=1))
        print(json.dumps(rows, indent=1))
    (root / "derived.json").write_text(json.dumps(derived, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv)
