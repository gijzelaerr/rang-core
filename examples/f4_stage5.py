# SPDX-License-Identifier: GPL-3.0-or-later
"""F4 calibrators, Stage 5 chain (research/f4-flagger.md, "Rerun rule" and
"Stage 5 chain", 2026-11-17). Native Windows, one process, detached.

Usage: python examples/f4_stage5.py

1. C1(U4) by gated attempts (examples/f4_c1_gate.py) every 15 min: a skip
   (gate: other CPUs > 1 over 10 s) does not count; the first timed attempt
   with all six repeats clean decides (stop if > 0.45); after two timed
   attempts without a clean one, stop and hand to the coordinator.
2. Only then the held-out quality runs, once: f4_eval.py real on LUNO
   MAIN_0, MAIN_12, MAIN_14 (--heldout, arms with NA and N4NA, delta 0.1)
   and f4_eval.py sim on f4sim-t (calibrator), in parallel, shared 4 slots.
3. Cost C1 for N4 at 4 and 1 threads on luno:MAIN_1, gated the same way;
   per thread count the first all-clean timed attempt decides, at most
   three timed attempts, else the last one is reported as provisional.
State: D:/rang/outputs/f4-20261111-stage5.json.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(r"D:\rang\outputs")
PY = sys.executable
STATE = OUT / "f4-20261111-stage5.json"
STATUS = Path(r"C:\Users\gijsm\Github\rang\outputs\status\f4.md")
N4 = "D:/rang/outputs/f4-20261111-08-train-calibrator/seed-2/weights.npz@-1.0"
SIM = "D:/rang/outputs/f4-20261111-02-sim-test/f4sim-t"
SETS = ("MAIN_0", "MAIN_12", "MAIN_14")
ARMS = "T,A,N4,N3,Z4,ZE,U4,N,NA,N4NA"
WAIT = 900
MAX_SKIPS = 400


def note(line):
    with open(STATUS, "a", encoding="utf-8") as f:
        f.write(f"- {time.strftime('%m-%d %H:%M')} stage5: {line}\n")


def run(name, cmd, threads, share=None):
    lock = ["--lock"] + (
        ["--slots", str(share[0]), "--mem", str(share[1])] if share else []
    )
    env = dict(os.environ, RAYON_NUM_THREADS=str(threads))
    full = [PY, str(ROOT / "examples/f4_run.py"), name, *lock, "--", PY, *cmd]
    return subprocess.Popen(full, cwd=ROOT, env=env)


def gated(prefix, n4, threads, max_timed, state, key):
    """Gated timing attempts; returns the deciding record."""
    rec = state.setdefault(key, {"skips": 0, "timed": []})
    while rec["skips"] < MAX_SKIPS:
        k = rec["skips"] + len(rec["timed"]) + 1
        name = f"{prefix}{k}"
        cmd = ["examples/f4_c1_gate.py", "time", "RUN/c1.json", "--set", "luno:MAIN_1"]
        rc = run(name, cmd + ["--n4", n4], threads).wait()
        if rc == 3:
            rec["skips"] += 1
            save(state)
            time.sleep(WAIT)
            continue
        if rc:
            rec["error"] = f"{name} rc {rc}"
            save(state)
            raise SystemExit(rec["error"])
        r = json.loads((OUT / name / "c1.json").read_text(encoding="utf-8"))
        rec["timed"].append(
            {
                "run": name,
                "c1": r["c1"],
                "all_clean": r["all_clean"],
                "median": r["median_wall"],
            }
        )
        save(state)
        note(f"{key} timed {name}: c1 {r['c1']:.3f} clean {r['all_clean']}")
        if r["all_clean"]:
            rec["decided"] = rec["timed"][-1] | {"provisional": False}
            break
        if len(rec["timed"]) >= max_timed:
            rec["decided"] = rec["timed"][-1] | {"provisional": True}
            break
        time.sleep(WAIT)
    save(state)
    return rec.get("decided")


def save(state):
    STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")


def main():
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    note("chain started")
    d = state.get("c1u4", {}).get("decided") or gated(
        "f4-20261111-05f", "U4", 4, 2, state, "c1u4"
    )
    if not d or d["provisional"]:
        state["stopped"] = "no clean C1(U4) in two timed attempts: to the coordinator"
        save(state)
        note(state["stopped"])
        return
    if d["c1"] > 0.45:
        state["stopped"] = f"C1(U4) {d['c1']:.3f} > 0.45 (section 8): F4 stops"
        save(state)
        note(state["stopped"])
        return
    if "quality" not in state:
        note(f"C1(U4) clean {d['c1']:.3f}: held-out quality runs start")
        procs = {}
        for s in SETS:
            cmd = ["examples/f4_eval.py", "real", f"RUN/{s}.json", "--set", f"luno:{s}"]
            cmd += ["--heldout", "--arms", ARMS, "--na-delta", "0.1", "--n4", N4]
            procs[s] = run(f"f4-20261111-13-heldout-{s}", cmd, 4, (4, 16))
        cmd = [
            "examples/f4_eval.py",
            "sim",
            "RUN/sim.json",
            SIM,
            "--class",
            "calibrator",
        ]
        procs["sim"] = run("f4-20261111-13-heldout-sim", cmd + ["--n4", N4], 4, (4, 16))
        state["quality"] = {k: p.wait() for k, p in procs.items()}
        save(state)
        note(f"quality rc {state['quality']}")
    for threads in (4, 1):
        key = f"c1n4_t{threads}"
        if not state.get(key, {}).get("decided"):
            gated(f"f4-20261111-14-c1n4-t{threads}-", N4, threads, 3, state, key)
    state["done"] = True
    save(state)
    note("chain done")


if __name__ == "__main__":
    main()
