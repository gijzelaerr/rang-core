"""Post hoc (after luno-score.json, 2026-11-11): is the Gpol class-B miss on
LUNO scan 1 the weights? rang solves Gpol with 1/SIGMA^2 (SIGMA is 1 on this
MS, so unit weights); CASA with WEIGHT_SPECTRUM (2 % over channels). On the
oracle copy (its frozen tables already written): initweights wtmode='ones',
then CASA's Gpol call unchanged into casa/Gpol-ones, scored as Gpol.
    python e2avg_gpol_ones.py RUN   (under tools/heavy_lock.py)"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import e2avg_common as C
import e2avg_luno as L


def main(run):
    run = Path(run)
    _, casa_ms = L.ms_paths(run)
    d = casa_ms.parent
    refant = json.loads((d / "refant.json").read_text())["refant"]
    calls = L.casa_calls("/run/casa/luno-dev.ms", refant)
    gpol = [c for c in calls if c["args"].get("caltable", "").endswith("/Gpol")][0]
    gpol = {"task": "gaincal", "args": {**gpol["args"], "caltable": "/run/casa/Gpol-ones"}}
    spec = [{"task": "initweights", "args": {"vis": "/run/casa/luno-dev.ms",
             "wtmode": "ones", "dowtsp": True}}, gpol]  # fmt: skip
    C.write(d / "casa-spec-ones.json", spec)
    script = ("/opt/casa/bin/python -I /ex/oracle_pol.py tasks /run/casa/casa-spec-ones.json "
              "/run/casa/casa-tasks-ones.json")  # fmt: skip
    rc = L.docker(run, "rang-o-casa:6.7.6.14",
                  [(run, "/run", "rw"), (L.ROOT / "examples", "/ex", "ro")], script,
                  "casa-ones")  # fmt: skip
    if rc:
        return rc
    own, _ = L.ms_paths(run)
    r = C.table(Path(str(own) + ".rang-run") / "calibrate" / "Gpol")
    out = {"Gpol_vs_casa_ones": C.term_diff(r, C.table(d / "Gpol-ones"), "phase"),
           "casa_ones_vs_casa": C.term_diff(C.table(d / "Gpol-ones"), C.table(d / "Gpol"), "phase")}
    C.write(run / "luno-gpol-ones.json", out)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
