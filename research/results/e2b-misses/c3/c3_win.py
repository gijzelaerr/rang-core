"""e2b-misses 9.28's Windows steps, native (no 9p), this worktree's build.

python c3_win.py apply FID OUT_JSON   rang's apply (today's main) on the D: copy of
                                      field FID into E2C_RANG_CORRECTED_DATA and FLAG,
                                      with the frozen apply's arguments (c2b_win.py)
"""

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WT = HERE.parents[3]
R = Path("D:/rang/outputs/e2-20261111-20-e2b")
P = Path("D:/rang/outputs/e2b-confirm-20261116")
NAMES = {0: "J1331+3030", 1: "J1939-6342", 2: "J1833-2103"}


def apply(fid):
    import rang
    from rang import applycal

    name = NAMES[fid]
    copy = P / f"f{fid}.ms"
    s = json.loads((R / "rang-run" / "apply" / "summary.json").read_text())
    calls = []
    for e in s["applied"]:
        if name not in e["fields"]:
            continue
        applycal.applycal(
            copy, [R / "rang-run" / "calibrate" / n for n in e["tables_applied"]],
            interp=[t["interp"] for t in e["tables"]],
            gainfield=[t["gainfield"] for t in e["tables"]],
            calwt=[t["calwt"] for t in e["tables"]], field=[name],
            applymode=e["applymode"], scan=e["scans"], parang=e["parang"],
            frame=e["frame"], receptor_angle=e["receptor_angle"], parang_flags="none",
            column="E2C_RANG_CORRECTED_DATA",
        )  # fmt: skip
        calls.append({"fields": [name], "tables": e["tables_applied"], "parang": e["parang"],
                      "frame": e["frame"], "receptor_angle": e["receptor_angle"]})  # fmt: skip
    assert len(calls) == 1, calls
    head = subprocess.run(["git", "-C", str(WT), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()  # fmt: skip
    return {"calls": calls, "rang_file": rang.__file__, "worktree_head": head}


def main(mode, *a):
    t0 = time.time()
    rec = apply(int(a[0]))
    rec["secs"] = time.time() - t0
    Path(a[-1]).write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
