"""E2-B transfer and leakage rows' development tables (research/e2-acceptance.md
6.5): on the development MS (LUNO scans 1-2), FLAG restored from
`rang_original` and any run directory moved aside, then one arm's
`rang-core run` of e2b-dev.yaml (or e2b-amended-dev.yaml), its run directory
moved to OUT/rang-run, FLAG after calibrate saved as flag version NAME
(the CASA development copy's flags; there is no later rang version to read
it from) with its hash, and FLAG restored again. The FLAG hashes before and
after are written to OUT/devtables.json.

    python e2_devtables.py MS CONFIG OUT NAME
(run with the arm's venv python; the caller wraps it in heavy_lock)
"""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import e2_flaghash


def restore(ms):
    from rang import core_writeback

    return int(core_writeback.restore_flags(ms, "rang_original"))


def main(ms, config, out, name):
    ms, out = Path(ms), Path(out)
    out.mkdir(parents=True, exist_ok=False)
    run = Path(str(ms) + ".rang-run")
    rec = {"ms": str(ms), "config": str(config), "python": sys.executable}
    if run.exists():
        dest = out / "rang-run-before"
        shutil.move(str(run), dest)
        rec["moved_before"] = str(dest)
    rec["restored_rows_before"] = restore(ms)
    e2_flaghash.main(str(ms), str(out / "flaghash-before.json"))
    t0 = time.perf_counter()
    with open(out / "run.log", "w", encoding="utf-8") as fh:
        rc = subprocess.call([sys.executable, "-m", "rang.core_cli", "run", str(config), str(ms)],
                             stdout=fh, stderr=subprocess.STDOUT)  # fmt: skip
    rec["run_exit"] = rc
    rec["run_seconds"] = time.perf_counter() - t0
    shutil.move(str(run), out / "rang-run")
    from rang import core_writeback

    rec["saved_version"] = name
    rec["saved_now"] = bool(
        core_writeback.backup_flags(ms, name, "E2-B dev: after calibrate")
    )
    e2_flaghash.main(str(ms), str(out / "flaghash-after-calibrate.json"))
    rec["restored_rows_after"] = restore(ms)
    e2_flaghash.main(str(ms), str(out / "flaghash-after.json"))
    a = json.loads((out / "flaghash-before.json").read_text())
    b = json.loads((out / "flaghash-after.json").read_text())
    rec["flag_restored_equal"] = a["flag_sha256"] == b["flag_sha256"] and (
        a["flag_row_sha256"] == b["flag_row_sha256"]
    )
    (out / "devtables.json").write_text(
        json.dumps(rec, indent=1) + "\n", encoding="utf-8"
    )
    print(json.dumps(rec, indent=1))
    return 0 if rc == 0 and rec["flag_restored_equal"] else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
