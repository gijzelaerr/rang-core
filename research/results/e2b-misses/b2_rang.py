"""9.19 step 5: rang's apply with the new P on R/casa/e2b.ms, with the
frozen apply's arguments (R/rang-run/apply/summary.json, as A1's C3), into
E2C_RANG_CORRECTED_DATA and FLAG. The MS's write-back journal is put back
afterwards, and no flag version is added (`flag_backup` names the existing
`rang_original`).

    python b2_rang.py OUT_JSON
"""

import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "python"))

R = Path("D:/rang/outputs/e2-20261111-20-e2b")
MS = R / "casa" / "e2b.ms"


def main(out):
    from rang import applycal
    from rang.formats import flagversions

    journal = MS.parent / "e2b.ms.flagversions" / "rang-writeback.json"
    saved = journal.with_name("rang-writeback.json.e2c-save")
    versions = sorted(p.name for p in journal.parent.iterdir())
    shutil.copy2(journal, saved)
    assert flagversions.exists(MS, "rang_original")
    s = json.loads((R / "rang-run" / "apply" / "summary.json").read_text())
    t0 = time.time()
    calls = []
    for e in s["applied"]:
        applycal.applycal(
            MS, [R / "rang-run" / "calibrate" / n for n in e["tables_applied"]],
            interp=[t["interp"] for t in e["tables"]],
            gainfield=[t["gainfield"] for t in e["tables"]],
            calwt=[t["calwt"] for t in e["tables"]], field=e["fields"],
            applymode=e["applymode"], scan=e["scans"], parang=e["parang"],
            frame=e["frame"], receptor_angle=e["receptor_angle"], parang_flags="none",
            column="E2C_RANG_CORRECTED_DATA", flag_backup="rang_original",
        )  # fmt: skip
        calls.append({"fields": e["fields"], "parang": e["parang"], "frame": e["frame"]})
    secs = time.time() - t0
    shutil.move(saved, journal)
    after = sorted(p.name for p in journal.parent.iterdir())
    rec = {"calls": calls, "secs": secs, "flagversions_unchanged": versions == after}
    Path(out).write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
