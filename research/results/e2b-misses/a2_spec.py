"""Arm A2's case specs (research/e2b-misses.md 9.1): `e2_casa3b.casa_calls`'
setjy (primary), K, G, B, Gsec, Gapp append and fluxscale, unchanged, on a
case copy, with this arm's flag and weight steps (`a2_casa.py tasks`).

    python a2_spec.py OUT_DIR     -> OUT_DIR/<case>/spec.json, cases.json

Inside the container `/w` is WSL's `~/e2b-arms-20261114` (the case MSs and
tables) and `/p` is OUT_DIR. Cases: flags {match, after} x weights
{spec, ones}; `match` swaps field 2's FLAG to the after-calibrate version
before the Gapp append (rang's F saw the A step's flags) and first makes
`F_fs` on the flag stage's flags.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "e2-acceptance-scripts"))

import e2_casa3b as X

R = Path(r"D:\rang\outputs\e2-20261111-20-e2b")
FIRST = 118104  # source row of the copy's row 0 (a2_casa.py base checks it)
FV = {
    "stage": "/w/src/fv/flags.rang_calibrate_20261112T010110Z",
    "after": "/w/src/fv/flags.rang_apply_20261112T013707Z",
}
CASES = [("after", "spec"), ("match", "ones"), ("match", "spec"), ("after", "ones")]
KEEP = {("setjy", X.FCAL), ("gaincal", "K"), ("gaincal", "G"), ("bandpass", "B"),
        ("gaincal", "Gsec"), ("copytree", "Gapp"), ("gaincal", "Gapp"),
        ("fluxscale", "F")}  # fmt: skip


def key(c):
    a = c["args"]
    if c["task"] == "setjy":
        return ("setjy", a["field"])
    t = a.get("fluxtable") or a.get("caltable") or a.get("dst") or ""
    return (c["task"], t.rsplit("/", 1)[-1])


def retarget(obj, t):
    if isinstance(obj, str):
        return obj.replace("/p/casa/tables", t)
    if isinstance(obj, list):
        return [retarget(x, t) for x in obj]
    if isinstance(obj, dict):
        return {k: retarget(v, t) for k, v in obj.items()}
    return obj


def case_spec(flags, weights):
    name = f"{flags}-{weights}"
    ms, t = f"/w/{name}/e2b.ms", f"/w/{name}/tables"
    calls = [c for c in X.casa_calls(ms, X.refant_names(R)) if key(c) in KEEP]
    assert [key(c) for c in calls] == [
        ("setjy", X.FCAL), ("gaincal", "K"), ("gaincal", "G"), ("bandpass", "B"),
        ("gaincal", "Gsec"), ("copytree", "Gapp"), ("gaincal", "Gapp"), ("fluxscale", "F"),
    ], [key(c) for c in calls]  # fmt: skip
    calls = retarget(calls, t)
    first = FV["stage"] if flags == "match" else FV["after"]
    pre = [{"logfile": f"/w/{name}/casa.log"},
           {"task": "putflags", "args": {"vis": ms, "version": first, "first": FIRST}}]  # fmt: skip
    pre.append({"task": "weights_ones" if weights == "ones" else "weights_read",
                "args": {"vis": ms}})  # fmt: skip
    solves, gapp = calls[:5], calls[5:]
    mid = []
    if flags == "match":
        mid = retarget(json.loads(json.dumps(gapp).replace("/Gapp", "/Gapp_fs")
                                  .replace(f"{t}/F\"", f"{t}/F_fs\"")), t)  # fmt: skip
        mid.append({"task": "putflags", "args": {"vis": ms, "version": FV["after"],
                    "first": FIRST, "field": 2}})  # fmt: skip
    return name, pre + solves + mid + gapp


def main(out):
    out = Path(out)
    names = []
    for flags, weights in CASES:
        name, spec = case_spec(flags, weights)
        (out / name).mkdir(parents=True, exist_ok=True)
        (out / name / "spec.json").write_text(json.dumps(spec, indent=1) + "\n")
        names.append(name)
    (out / "cases.json").write_text(json.dumps(names) + "\n")
    print(names)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
