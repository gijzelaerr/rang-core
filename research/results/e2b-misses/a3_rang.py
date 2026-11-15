"""Arm A3's rang side and scores (research/e2b-misses.md 9.21), run with this
branch's extension (the worktree's .venv) under tools/heavy_lock.py.

    python a3_rang.py scorer              control X-s (archived tables)
    python a3_rang.py setmodel            rang's 3C286 model on X's copy
    python a3_rang.py models              L's and X's model checks
    python a3_rang.py arms SET [ARM ...]  Gpol arms T, F, K on SET (L, S, X)
    python a3_rang.py score               every control and reading -> a3.json

Arms: T = average_time (the frozen arm's estimator), F = T + average_freq
(the amended arm's), K = F + casa_phase_weights. S has the resolved (DATA)
and point (CORRECTED_DATA) cases. Tables go to P/<SET>/rang/<case>-<arm>."""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "research" / "results" / "e2-average-time"))
import e2avg_common as C
from rang import cal_pol, calmodels, core_chunks, core_ms, rusage
from rang.formats import caltable

P = Path("D:/rang/outputs/e2b-gpol-20261115")
R = Path("D:/rang/outputs/e2-20261111-20-e2b")
RA = Path("D:/rang/outputs/e2-20261112-21-e2b-amended")
LUNO = Path("D:/rang/outputs/chi-offset-20261113-03-luno-s1")
A2 = Path("D:/rang/outputs/e2b-arms-20261114/a2/match-ones/tables")
REFANT = ["m022", "m023", "m024"]
ARMS = {
    "T": {"average_time": True},
    "F": {"average_time": True, "average_freq": True},
    "K": {"average_time": True, "average_freq": True, "casa_phase_weights": True},
}
CLASS_B = 0.1


def sets():
    """{set: (ms, K G B tables or None, {case: data column})}."""
    return {
        "L": (
            LUNO / "base" / "luno4.ms",
            LUNO / "casa-m90" / "tables",
            {"luno": "DATA"},
        ),
        "S": (P / "S" / "sim.ms", None, {"res": "DATA", "pt": "CORRECTED_DATA"}),
        "X": (P / "X" / "x17.ms", R / "rang-run" / "calibrate", {"x17": "DATA"}),
    }


def commit():
    return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=False).stdout.strip()  # fmt: skip


def solve(ms, tdir, data_column, arm):
    tables = [] if tdir is None else [caltable.read(tdir / n) for n in ("K", "G", "B")]
    with core_ms.open_table(ms) as t:
        nrows = t.nrows
    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as t:
        nchan = len(t.getcol("CHAN_FREQ")[0])
    budget = core_chunks.Budget(8.0, int(nrows), (nchan, 4)).chain()
    table, _sol, _info = cal_pol.gpol(
        ms, field_id=0, solint="60s", combine="", refant=REFANT, refantmode="flex",
        minsnr=3.0, minblperant=4, uvrange=">150", gaintable=tables or (),
        interp=["linear"] * 3 if tables else "linear", parang=True, frame="casa",
        model_column="MODEL_DATA", receptor_angle=float(np.deg2rad(-90.0)),
        weight_column=None, budget=budget, data_column=data_column, **ARMS[arm],
    )  # fmt: skip
    return table


def arms(name, which):
    ms, tdir, cases = sets()[name]
    out = P / name / "rang"
    out.mkdir(parents=True, exist_ok=True)
    log = {}
    for case, column in cases.items():
        for arm in which or ARMS:
            t0, c0 = time.perf_counter(), time.process_time()
            table = solve(ms, tdir, column, arm)
            dst = out / f"{case}-{arm}"
            if dst.exists():
                shutil.rmtree(dst)
            caltable.write(table, dst)
            log[f"{case}-{arm}"] = {"wall_s": time.perf_counter() - t0,
                                    "cpu_s": time.process_time() - c0,
                                    "peak_rss_mb": rusage.peak_rss_mb()}  # fmt: skip
            print(case, arm, json.dumps(log[f"{case}-{arm}"]), flush=True)
    log["commit"] = commit()
    C.write(out / f"arms-{'-'.join(which or ARMS)}.json", log)
    return 0


def setmodel():
    ms = P / "X" / "x17.ms"
    receipt = calmodels.set_model(ms, [0], calmodels.caracal_xcal("3C286"))
    C.write(P / "X" / "rang-model.json", receipt)
    return 0


def model_check(ms, rows, casa_npy):
    with core_ms.open_table(ms) as t:
        ours = core_chunks.read_rows(t, "MODEL_DATA", np.asarray(rows))
    theirs = np.load(casa_npy)
    rel = np.abs(ours - theirs) / np.maximum(np.abs(theirs), 1e-30)
    keep = np.abs(theirs) > 1e-3 * np.abs(theirs).max()
    return {"rows": list(map(int, rows)), "max_rel": float(rel[keep].max()),
            "max_abs_jy": float(np.abs(ours - theirs).max())}  # fmt: skip


def models():
    out = {
        "L": model_check(
            LUNO / "base" / "luno4.ms", [0, 7777, 19999], P / "L" / "casa-model.npy"
        ),
        "X": model_check(
            P / "X" / "x17.ms", [0, 60000, 118103], P / "X" / "casa-model.npy"
        ),
    }
    out["L"]["ok"] = out["L"]["max_rel"] <= 1e-6
    out["X"]["ok"] = out["X"]["max_rel"] <= 1e-5
    C.write(P / "models.json", out)
    print(json.dumps(out, indent=1))
    return 0


def phase_diff(a, b):
    """`term_diff` (phase) plus equal interval counts and a per-antenna
    table (median over intervals and hands)."""
    d = C.term_diff(a, b, "phase")
    d["intervals"] = [len(np.unique(np.round(t.column("TIME"), 3))) for t in (a, b)]
    pa, fa, pb, fb, _, _ = C.matched(a, b)
    ka = C.keyed(a)
    ant = np.array([k[1] for k in sorted(set(ka) & set(C.keyed(b)))])
    ok = ~fa & ~fb
    deg = np.degrees(np.abs(np.angle(pa / np.where(ok, pb, 1))))
    per = {}
    for x in np.unique(ant):
        v = deg[ant == x][ok[ant == x]]
        if v.size:
            per[int(x)] = float(np.median(v))
    d["per_antenna_median_deg"] = per
    d["class_b"] = bool(d["abs_deg"].get("median", np.inf) <= CLASS_B)
    return d


def scorer():
    out = {}
    for label, run in (("frozen", R), ("amended", RA)):
        a = C.table(run / "rang-run" / "calibrate" / "Gpol")
        b = C.table(run / "casa" / "tables" / "Gpol")
        out[label] = phase_diff(a, b)
        out[label]["archived"] = json.loads((run / "g3b.json").read_text())["terms"][
            "Gpol"
        ]
    C.write(P / "scorer.json", out)
    for k, v in out.items():
        print(k, v["abs_deg"], "archived", v["archived"]["abs_deg"])
    return 0


def truth_diff(table, truth_npz, ant_names, mean=False):
    """Rang's or CASA's Gpol against the simulation's gains, both in
    m022's gauge (phase of antenna minus m022's, per hand)."""
    z = np.load(truth_npz)
    ref = ant_names.index("m022")
    a = table.column("ANTENNA1")
    # mean=True (post hoc, 9.22): the true relative gain averaged over the
    # solution interval (1 s steps), not taken at the solution TIME.
    offs = np.linspace(-0.5, 0.5, 61) if mean else np.zeros(1)
    t = table.column("TIME")[:, None] - float(z["t0"])
    t = t + offs[None, :] * table.column("INTERVAL")[:, None]

    def phase(ants):
        return z["phase0"][ants][:, None, :] + float(z["drift_rad"]) * np.sin(
            2 * np.pi * t[:, :, None] / float(z["drift_period_s"])
            + z["theta"][ants][:, None, :]
        )

    rel = np.exp(1j * (phase(a) - phase(np.full_like(a, ref)))).mean(axis=1)
    g = table.params[:, 0, :]  # (row, hand)
    f = table.flags[:, 0, :]
    d = np.degrees(np.abs(np.angle(g * np.conj(rel))))
    return C.stats(d[~f])


def score():
    out = {"commit": commit(), "sets": {}}
    for name, (ms, _, cases) in sets().items():
        casa = P / name / "casa"
        for case in cases:
            ref = {"L": "Gpol", "S": f"Gpol-{case}", "X": "Gpol-CM"}[name]
            if not (casa / ref).exists():
                continue
            c = C.table(casa / ref)
            row = {}
            for arm in ARMS:
                p = P / name / "rang" / f"{case}-{arm}"
                if p.exists():
                    row[arm] = phase_diff(C.table(p), c)
                    if name == "X":
                        row[arm + "_vs_CR"] = phase_diff(
                            C.table(p), C.table(casa / "Gpol-CR")
                        )
            out["sets"][f"{name}/{case}"] = row
    controls = {}
    x0 = P / "X" / "rang" / "x17-T"
    if x0.exists():
        d = C.term_diff(
            C.table(x0), C.table(R / "rang-run" / "calibrate" / "Gpol"), "phase"
        )
        d["met"] = bool(d["abs_deg"]["max"] <= 1e-4 and d["flags_differ"] == 0)
        controls["X0"] = d
    for key, a, b in (("XC", P / "X" / "casa" / "Gpol-CC", R / "casa" / "tables" / "Gpol"),
                      ("LC", P / "L" / "casa" / "Gpol", LUNO / "casa-m90" / "tables" / "Gpol")):  # fmt: skip
        if a.exists():
            d = C.term_diff(C.table(a), C.table(b), "phase")
            d["met"] = bool(d["abs_deg"]["median"] <= 1e-3 and d["flags_differ"] == 0)
            controls[key] = d
    pt = out["sets"].get("S/pt", {})
    if pt:
        controls["S-pt"] = {"met": all(pt[a]["class_b"] for a in ("F", "K") if a in pt)}
    out["controls"] = controls
    truth = P / "S" / "truth.npz"
    if truth.exists():
        with core_ms.open_table(LUNO / "base" / "luno4.ms" / "ANTENNA") as t:
            names = [str(n) for n in t.getcol("NAME")]
        tr = {}
        for case in ("res", "pt"):
            for label, p in [("casa", P / "S" / "casa" / f"Gpol-{case}")] + [
                (arm, P / "S" / "rang" / f"{case}-{arm}") for arm in ARMS
            ]:
                if p.exists():
                    tr[f"{case}-{label}"] = truth_diff(C.table(p), truth, names)
                    tr[f"{case}-{label}-interval-mean"] = truth_diff(
                        C.table(p), truth, names, mean=True
                    )
        out["truth"] = tr
    C.write(P / "a3.json", out)
    for k, v in out["sets"].items():
        print(k, {a: (round(d["abs_deg"].get("median", np.nan), 4), d["flags_differ"])
                  for a, d in v.items()})  # fmt: skip
    print(json.dumps(controls, indent=1, default=str)[:3000])
    return 0


def main(argv):
    cmd = argv[1]
    if cmd == "arms":
        return arms(argv[2], argv[3:])
    return {"scorer": scorer, "setmodel": setmodel, "models": models, "score": score}[
        cmd
    ]()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
