"""The rerun's rang flag versions against E2-N's surviving ones (research/e2n-followup.md,
amendment 2026-11-22): FLAG and FLAG_ROW SHA-256 (e2_post.flag_hash) of rang_original and
of each stage's version (rang_flag_*, rang_calibrate_*, rang_apply_*), matched by stage.

python fu_flagversions.py NEW_MS E2N_MS OUT.json     exit 0 if every stage's hashes are equal
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "e2-acceptance-scripts"))

import e2_post as P

STAGES = ("original", "flag", "calibrate", "apply")


def versions(ms):
    d = Path(str(ms) + ".flagversions")
    out = {}
    for p in sorted(d.glob("flags.rang_*")):
        stage = p.name[len("flags.rang_") :].split("_")[0]
        out[stage] = p
    return out


new_ms, old_ms, out = sys.argv[1:4]
new, old = versions(new_ms), versions(old_ms)
res, ok = {}, True
for s in STAGES:
    if s not in new or s not in old:
        res[s] = {"missing": [x for x, v in (("new", new), ("e2n", old)) if s not in v]}
        ok = False
        continue
    a, b = P.flag_hash(new[s]), P.flag_hash(old[s])
    eq = a == b
    ok &= eq
    res[s] = {
        "new": new[s].name,
        "e2n": old[s].name,
        "new_hash": a,
        "e2n_hash": b,
        "equal": eq,
    }
P.write(Path(out), {"stages": res, "all_equal": ok})
sys.exit(0 if ok else 1)
