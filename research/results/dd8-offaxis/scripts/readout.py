"""DD8's frozen readings (research/dd8-offaxis.md sections 3-5) from the grid and score records."""
import json, sys
from pathlib import Path
R = Path("D:/rang/outputs/dd8-20261125")
def g(name):
    p = R / "grid" / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None
BASE = {"free": [0.988, 0.974, 0.939], "pinned": [0.997, 0.993, 0.956]}
def rule(r, base, base_step=None):
    f = r["perdir_converged"][1:]
    if any(x <= 0.10 and b > 0.10 for x, b in zip(f, base)): return "reproduces"
    if any(b - x >= 0.20 for x, b in zip(f, base)): return "weakens"
    return "neither"
out = {}
for name, kind in (("O-F", "free"), ("O-P", "pinned"), ("O-X", "free"), ("OH-F", "free"), ("BH-F", "free")):
    r = g(name)
    if r: out[name] = {"perdir": [round(x, 4) for x in r["perdir_converged"]], "rule": rule(r, BASE[kind]),
                       "lifted": all(x > 0.10 for x in r["perdir_converged"][1:]),
                       "step_med": [s["median"] for s in r["step_stats"]], "e_over_ehat": r["e_over_ehat"],
                       "accurate": r["accurate"], "iterations": r["iterations"]}
for name in ("O-F-2000", "O-F-64"):
    r = g(name)
    if r: out[name] = {"perdir": [round(x, 4) for x in r["perdir_converged"]], "lifted": all(x > 0.10 for x in r["perdir_converged"][1:]),
                       "e_over_ehat": r["e_over_ehat"], "step_med": [s["median"] for s in r["step_stats"]]}
F500 = {16: [0.11552346570397112, 0.08507821901323706, 0.037605294825124424], 64: [0.79375, 0.7541666666666667, 0.7515657620041754],
        4: [0.0658011212747123, 0.042195337857775156, 0.010537251409913921]}
CEIL = {4: 112 / 113, 16: 28 / 29, 64: 7 / 8}
for ti, name in ((16, "L2000-16"), (64, "L2000-64")):
    r = g(name)
    if r:
        f = r["perdir_converged"][1:]
        G = [(a - b) / (CEIL[ti] - b) for a, b in zip(f, F500[ti])]
        m = min(G)
        out[name] = {"perdir": [round(x, 4) for x in r["perdir_converged"]], "G": G,
                     "reading": "mostly iterations" if m >= 0.5 else "partly iterations" if m >= 0.1 else "not iterations",
                     "stopped_before_cap": r["stopped_before_cap"], "step_med": [s["median"] for s in r["step_stats"]]}
r12, rc = g("R12"), g("R1cR2")
if r12:
    m12 = min(r12["perdir_converged"][1:]); mc = min(rc["perdir_converged"][1:]) if rc else None
    rd = "no gain" if m12 < 0.347 else ("pending control" if mc is None else "adds, not specific" if mc >= 0.347 else "R1 adds to R2")
    out["R12"] = {"perdir": r12["perdir_converged"], "min": m12, "R1cR2": rc and rc["perdir_converged"], "reading": rd,
                  "step_med": [s["median"] for s in r12["step_stats"]]}
r = g("R12-64")
if r:
    m = min(r["perdir_converged"][1:])
    out["R12-64"] = {"perdir": r["perdir_converged"], "min": m, "reading": "repairs" if m >= 0.702 else "partly" if m >= 0.354 else "no"}
r = g("RH-MF")
if r:
    ref = F500[4]; f = r["perdir_converged"][1:]
    out["bridge"] = {"perdir": r["perdir_converged"], "comparable": all(abs(a - b) <= 0.05 for a, b in zip(f, ref))}
for name in ("RH-L2000", "R2H"):
    r = g(name)
    if r: out[name] = {"perdir": r["perdir_converged"], "step_med": [s["median"] for s in r["step_stats"]]}
print(json.dumps(out, indent=1))
