"""DL4a (#41) screening driver (research/dl4a-screen.md sections 3-5). On nash, in the
dl4a-screen worktree's venv.

    python dl4a_screen.py ROOT models
    python dl4a_screen.py ROOT solve ARM TERM SOLINT [--max-iterations N]
    python dl4a_screen.py ROOT score

ROOT holds D/pilot.ms and D/config.yaml (`examples/selfcal_grid.py prepare D`) and
D/run, the baseline `rang-core selfcal` run at the defaults. `models` predicts each
round's model images into MODEL_R1 and MODEL_R2 (`core_pipeline._selfcal_model`, the
stage's own predictor settings). `solve` runs one solve-only arm on the one-call path
(`cal_selfcal.solve(..., stream=False, start=...)`) and writes solves/<tag>.npz and
<tag>.json (iterations, fraction, wall), with a done-marker; `--max-iterations 1` gives
the read and set-up wall for the ceiling. ARM: A0 (identity), A1 (A0's gains shifted by
one interval), A2 (Sa from Sp's solution, same solint), A3 (A2, else A1). TERM: Sp
(against MODEL_R1) or Sa (against MODEL_R2). SOLINT: inf or 120s. `score` writes
score.json: the same-solution gate per arm, iterations, the ceiling and the outcome
inputs (section 5); the outcome itself is read from the note's frozen rule.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import yaml

TERMS = {"Sp": "MODEL_R1", "Sa": "MODEL_R2"}


def load(root):
    from rang import core_pipeline

    d = root / "D"
    cfg = yaml.safe_load((d / "config.yaml").read_text())
    resolved = d / "run" / "config.resolved.json"
    if resolved.exists():
        cfg = json.loads(resolved.read_text())
    summary = json.loads((d / "run" / "selfcal" / "summary.json").read_text())
    return core_pipeline, cfg, summary


def field_record(summary):
    fields = summary["fields"]
    if len(fields) != 1:
        raise SystemExit(f"expected one field, got {len(fields)}")
    return fields[0]


def cmd_models(root):
    core_pipeline, cfg, summary = load(root)
    ms = root / "D" / "pilot.ms"
    rec = field_record(summary)
    done = root / "done"
    done.mkdir(exist_ok=True)
    out = {}
    for k in (1, 2):
        mark = done / f"model-R{k}.done"
        if mark.exists():
            continue
        prefix = Path(rec["rounds"][k - 1]["store"]).parent / cfg["image"]["name"]
        c = json.loads(json.dumps(cfg))
        c["selfcal"]["model_column"] = f"MODEL_R{k}"
        t0 = time.perf_counter()
        model = core_pipeline._selfcal_model(
            {"config": c, "ms": ms}, rec["field_id"], prefix, None
        )
        out[f"R{k}"] = {
            "prefix": str(prefix),
            "wall_s": time.perf_counter() - t0,
            "rows": model.get("rows"),
        }
        mark.write_text(json.dumps(out[f"R{k}"]) + "\n")
    print(json.dumps(out))


def solve_one(root, arm, term_type, solint, max_iterations=None):
    from rang import cal_selfcal, core_ms

    _, cfg, summary = load(root)
    rec = field_record(summary)
    sc = cfg["selfcal"]
    ms = root / "D" / "pilot.ms"
    with core_ms.open_table(ms) as t:
        fid = t.getcol("FIELD_ID")
    rows = np.flatnonzero(fid == rec["field_id"])
    term = {"name": term_type, "type": term_type, "solint": solint, "freqint": "inf"}
    if max_iterations is not None:
        term["max_iterations"] = int(max_iterations)
    start = None
    if arm in ("A1", "A2", "A3"):
        start = arm_start(root, arm, term_type, solint)
    refant = summary["refant"]
    settings = rec["rounds"][0]["solve"]["settings"]
    weights = None if settings["weights"] == "unit" else settings["weights"]
    t0 = time.perf_counter()
    sol = cal_selfcal.solve(
        ms, term, rows=rows, field_id=rec["field_id"], input_column=sc["input_column"],
        model_column=TERMS[term_type], weight_column=weights,
        refant=refant, minuvw_m=sc["minuvw_m"], gain_clip=sc["gain_clip"], budget=None,
        stream=False, start=start,
    )  # fmt: skip
    wall = time.perf_counter() - t0
    return sol, wall


def arm_start(root, arm, term_type, solint):
    base = np.load(root / "solves" / f"A0-{term_type}-{solint}.npz")
    g = base["gains"]
    shifted = np.ones_like(g)
    shifted[1:] = g[:-1]
    if arm == "A1":
        return shifted
    if term_type != "Sa":
        raise SystemExit("A2 and A3 start Sa from Sp")
    sp = np.load(root / "solves" / f"A0-Sp-{solint}.npz")
    tsp, tsa = sp["gain_time"], base["gain_time"]
    out = shifted.copy() if arm == "A3" else np.ones_like(g)
    for i, t in enumerate(tsa):
        j = int(np.argmin(np.abs(tsp - t)))
        if abs(tsp[j] - t) < 1.0:  # the same interval (both terms share the solint)
            out[i] = sp["gains"][j]
    return out


def cmd_solve(root, arm, term_type, solint, max_iterations):
    tag = f"{arm}-{term_type}-{solint}" + (
        f"-it{max_iterations}" if max_iterations else ""
    )
    outdir = root / "solves"
    outdir.mkdir(exist_ok=True)
    mark = root / "done" / f"solve-{tag}.done"
    if mark.exists():
        print(f"{tag}: done, skipped")
        return
    sol, wall = solve_one(root, arm, term_type, solint, max_iterations)
    np.savez(
        outdir / f"{tag}.npz", gains=sol.gains, flags=sol.flags, gain_time=sol.gain_time
    )
    info = {"arm": arm, "term": term_type, "solint": solint, "max_iterations": max_iterations,
            "iterations": sol.iterations, "fraction": sol.converged_fraction,
            "wall_s": round(wall, 2), "ngains": int(np.prod(sol.gains.shape[:3])),
            "intervals": int(sol.gains.shape[0])}  # fmt: skip
    (outdir / f"{tag}.json").write_text(json.dumps(info, indent=1) + "\n")
    (root / "done").mkdir(exist_ok=True)
    mark.write_text(json.dumps(info) + "\n")
    print(json.dumps(info))


def products(g, flags):
    """Parallel-hand products g_p conj(g_q), p < q, per interval and bin; NaN where flagged."""
    g = np.where(flags, np.nan, g)
    na = g.shape[2]
    p, q = np.triu_indices(na, 1)
    return g[:, :, p, :] * np.conj(g[:, :, q, :])


def cmd_score(root):
    out = {"arms": {}, "gate": {"median_rel": 1e-5, "p99_rel": 1e-4}}
    sdir = root / "solves"
    for f in sorted(sdir.glob("A*-*.json")):
        info = json.loads(f.read_text())
        if info.get("max_iterations"):
            continue
        tag = f.stem
        a, t, s = tag.split("-")
        res = dict(info)
        if a != "A0":
            x = np.load(sdir / f"{tag}.npz")
            b = np.load(sdir / f"A0-{t}-{s}.npz")
            same_flags = bool(np.array_equal(x["flags"], b["flags"]))
            px, pb = products(x["gains"], x["flags"]), products(b["gains"], b["flags"])
            rel = np.abs(px - pb) / np.abs(pb)
            rel = rel[np.isfinite(rel)]
            res.update(flags_equal=same_flags, rel_median=float(np.median(rel)),
                       rel_p99=float(np.percentile(rel, 99)), rel_max=float(rel.max()),
                       eligible=bool(same_flags and np.median(rel) <= 1e-5
                                     and np.percentile(rel, 99) <= 1e-4))  # fmt: skip
        out["arms"][tag] = res
    for f in sorted(sdir.glob("A0-*-it1.json")):
        info = json.loads(f.read_text())
        t, s = info["term"], info["solint"]
        full = out["arms"].get(f"A0-{t}-{s}")
        if full:
            per = (full["wall_s"] - info["wall_s"]) / max(full["iterations"] - 1, 1)
            out.setdefault("ceiling", {})[f"{t}-{s}"] = {
                "read_setup_s": info["wall_s"], "s_per_iteration": per,
                "max_saving_s": per * (full["iterations"] - 1),
            }  # fmt: skip
    base = root / "D" / "run" / "selfcal" / "summary.json"
    if base.exists():
        out["baseline_selfcal_summary"] = str(base)
    (root / "score.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("cmd", choices=["models", "solve", "score"])
    p.add_argument("arm", nargs="?")
    p.add_argument("term", nargs="?", choices=list(TERMS))
    p.add_argument("solint", nargs="?")
    p.add_argument("--max-iterations", type=int, default=None)
    a = p.parse_args(argv)
    root = a.root.resolve()
    if a.cmd == "models":
        cmd_models(root)
    elif a.cmd == "solve":
        cmd_solve(root, a.arm, a.term, a.solint, a.max_iterations)
    else:
        cmd_score(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
