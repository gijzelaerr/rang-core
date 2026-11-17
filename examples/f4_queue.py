"""F4 Stages 1-3, queued (research/f4-flagger.md, section 8): native Windows,
one step at a time, each under tools/heavy_lock.py via examples/f4_run.py,
with the frozen stop rules checked between steps.

Usage: python examples/f4_queue.py [--from STEP] [--only STEP,...]

Steps (run names D:\\rang\\outputs\\f4-20261111-NN-*):
  sim      02 f4sim-t (unread until Stage 5)
  stage1   03 Stop-E and Stop-Z4 per class on validation
  nadelta  03 NA's delta per class on validation (Amendment 1)
  parity   04 Rust against NumPy/JAX on MAIN_7 and ESO137 chunk 10 (U4)
  c1u4     05 C1(U4) on LUNO MAIN_1, 4 threads (idle host; stop if > 0.45)
  shards   06 calibrators, 07 targets: labels, audit, shards (train, validation)
A class that stops (Stop-E, Stop-Z4, label audit) is skipped from then on;
parity or C1(U4) failing stops everything. Training (GPU, WSL) is not here:
research/f4-flagger.md, "Staged runs", lists it.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(r"D:\rang\outputs")
PY = sys.executable
F3 = {
    "calibrator": OUT / "f3-20261110-13-shards-cal",
    "target": OUT / "f3-20261110-08-shards-target",
}
VALIDATION = {"calibrator": "luno:MAIN_7", "target": "eso:10"}
SHARDS = {
    "calibrator": "f4-20261111-06-shards-cal",
    "target": "f4-20261111-07-shards-target",
}
STEPS = ("sim", "stage1", "nadelta", "parity", "c1u4", "shards")


# Shared heavy-lock slots (threads, GB) per step; only the cost timing is
# exclusive. RAYON_NUM_THREADS matches the slots.
SHARE = {
    "sim": (4, 12),
    "stage1": (4, 12),
    "nadelta": (4, 8),
    "parity": (4, 24),
    "shards": (4, 16),
}


def run(name, cmd, env=None, share=None):
    lock = ["--lock"]
    env = dict(env or {})
    if share:
        lock += ["--slots", str(share[0]), "--mem", str(share[1])]
        env.setdefault("RAYON_NUM_THREADS", str(share[0]))
    full = [PY, str(ROOT / "examples/f4_run.py"), name, *lock, "--", *cmd]
    rc = subprocess.call(full, cwd=ROOT, env=dict(os.environ, **env))
    if rc:
        raise SystemExit(f"{name}: rc {rc}")


def ex(script):
    return [PY, str(ROOT / "examples" / script)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="start", default="sim", choices=STEPS)
    parser.add_argument("--only")
    args = parser.parse_args()
    steps = STEPS[STEPS.index(args.start) :]
    if args.only:
        steps = [s for s in args.only.split(",") if s in STEPS]
    classes = ["calibrator", "target"]
    verdict = OUT / "f4-20261111-queue.json"
    state = json.loads(verdict.read_text(encoding="utf-8")) if verdict.exists() else {}

    def save():
        verdict.write_text(json.dumps(state, indent=1), encoding="utf-8")

    for k in ("stopped", "results"):
        state.setdefault(k, {})
    classes = [c for c in classes if c not in state["stopped"]]
    if "sim" in steps:
        run(
            "f4-20261111-02-sim-test",
            [*ex("f2_simulate.py"), "RUN", "f4sim-t"],
            share=SHARE["sim"],
        )
    if "stage1" in steps:
        for c in classes:
            name = f"f4-20261111-03-stage1-{c}"
            run(
                name,
                [*ex("f4_eval.py"), "stage1", "RUN/stage1.json", "--class", c]
                + ["--flags-from", str(F3[c])],
                share=SHARE["stage1"],
            )
            r = json.loads((OUT / name / "stage1.json").read_text(encoding="utf-8"))
            state["results"][f"stage1-{c}"] = {
                k: r[k] for k in ("ZE_antenna_local_recall", "stop_E", "stop_Z4")
            }
            if r["stop_E"]:
                state["stopped"][c] = "Stop-E"
            elif r["stop_Z4"]:
                state["stopped"][c] = "Stop-Z4"
            save()
        classes = [c for c in classes if c not in state["stopped"]]
    if "nadelta" in steps:
        for c in ("calibrator", "target"):
            name = f"f4-20261111-03-nadelta-{c}"
            run(
                name,
                [*ex("f4_eval.py"), "na-delta", "RUN/na-delta.json", "--class", c],
                share=SHARE["nadelta"],
            )
            r = json.loads((OUT / name / "na-delta.json").read_text(encoding="utf-8"))
            state["results"][f"nadelta-{c}"] = r["delta"]
            save()
    if "parity" in steps:
        for c in ("calibrator", "target"):
            name = f"f4-20261111-04-parity-{c}"
            run(
                name,
                [*ex("f4_parity.py"), "RUN/parity.json", "--set", VALIDATION[c]],
                share=SHARE["parity"],
            )
            r = json.loads((OUT / name / "parity.json").read_text(encoding="utf-8"))
            state["results"][f"parity-{c}"] = r["pass"]
            save()
            if not r["pass"]:
                raise SystemExit(f"parity fails on {c}: one round of fixes, then stop")
    if "c1u4" in steps:
        name = "f4-20261111-05-c1u4"
        run(
            name,
            [*ex("f4_cost.py"), "time", "RUN/c1u4.json", "--set", "luno:MAIN_1"]
            + ["--n4", "U4"],
            env={"RAYON_NUM_THREADS": "4"},
        )
        r = json.loads((OUT / name / "c1u4.json").read_text(encoding="utf-8"))
        state["results"]["c1u4"] = {k: r[k] for k in ("c1", "all_clean")}
        save()
        if not r["all_clean"]:
            raise SystemExit("C1(U4) not clean (host busy): rerun with --from c1u4")
        if r["c1"] > 0.45:
            state["stopped"]["all"] = f"C1(U4) {r['c1']:.3f} > 0.45"
            save()
            raise SystemExit(state["stopped"]["all"])
    if "shards" in steps:
        for c in classes:
            name = SHARDS[c]
            for role in ("validation", "train"):
                run(
                    name,
                    [*ex("f4_shards.py"), "RUN", "--class", c, "--role", role]
                    + ["--flags-from", str(F3[c])],
                    share=SHARE["shards"],
                )
                audit = OUT / name / c / role / "audit.json"
                a = json.loads(audit.read_text(encoding="utf-8"))
                state["results"][f"audit-{c}-{role}"] = a["stop"]
                save()
                if a["stop"] and role == "train":
                    state["stopped"][c] = f"label audit: {a['stop']}"
                    save()
    print(json.dumps(state))


if __name__ == "__main__":
    main()
