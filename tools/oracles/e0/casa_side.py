# SPDX-License-Identifier: GPL-3.0-or-later
"""The container side of task E0's comparisons (research/e0-refant-extend.md),
in `rang-o-casa:6.7.6.14`:

    python3 -I casa_side.py prepare <src.ms> <dst.ms> [<flag.npz>]
    python3 -I casa_side.py edit <ms> <edit.json>
    /opt/casa/bin/python -I casa_side.py flagdata <ms> <calls.json> <result.json>

`prepare` copies an MS (dropping `table.lock`) and, with `flag.npz`, ORs its
boolean `flag` (row, chan, corr) into FLAG (python-casacore, the image's
system Python). `edit` applies, in order: `antenna_names` (ANTENNA NAME),
`telescope` (OBSERVATION TELESCOPE_NAME), `flag_rows` (FLAG set on these
rows), `scan` ({"rows", "value"}: SCAN_NUMBER), `time` ([{"rows", "value"}]:
TIME), `remove_rows` (last, by a deep copy of the other rows). `flagdata` runs CASA 6.7.6.14's `flagdata` once
per call, in order, on `ms` and records the wall time of each.
"""

import json
import shutil
import sys
import time
from pathlib import Path


def prepare(src, dst, flag_npz=None):
    shutil.copytree(src, dst)
    lock = Path(dst) / "table.lock"
    if lock.exists():
        lock.unlink()
    from casacore.tables import table

    with table(dst, readonly=False, ack=False) as t:
        if flag_npz is not None:
            import numpy as np

            extra = np.load(flag_npz)["flag"]
            flag = t.getcol("FLAG")
            assert flag.shape == extra.shape, (flag.shape, extra.shape)
            t.putcol("FLAG", flag | extra)
        t.flush()


def edit(ms, spec_path):
    import numpy as np
    from casacore.tables import table

    spec = json.loads(Path(spec_path).read_text())
    if "antenna_names" in spec:
        with table(f"{ms}/ANTENNA", readonly=False, ack=False) as t:
            t.putcol("NAME", spec["antenna_names"])
    if "telescope" in spec:
        with table(f"{ms}/OBSERVATION", readonly=False, ack=False) as t:
            t.putcol("TELESCOPE_NAME", [spec["telescope"]] * t.nrows())
    with table(ms, readonly=False, ack=False) as t:
        if "flag_rows" in spec:
            flag = t.getcol("FLAG")
            flag[np.asarray(spec["flag_rows"], int)] = True
            t.putcol("FLAG", flag)
        if "scan" in spec:
            scan = t.getcol("SCAN_NUMBER")
            scan[np.asarray(spec["scan"]["rows"], int)] = spec["scan"]["value"]
            t.putcol("SCAN_NUMBER", scan)
        for item in spec.get("time", []):
            values = t.getcol("TIME")
            values[np.asarray(item["rows"], int)] = item["value"]
            t.putcol("TIME", values)
        t.flush()
        if spec.get("remove_rows"):
            # A1's storage managers cannot remove rows (run e0-20261106-05), so
            # the other rows are deep-copied into a new table that replaces it.
            gone = {int(r) for r in spec["remove_rows"]}
            keep = [r for r in range(t.nrows()) if r not in gone]
            t.selectrows(keep).copy(f"{ms}.keep", deep=True)
    if spec.get("remove_rows"):
        shutil.rmtree(ms)
        shutil.move(f"{ms}.keep", ms)
        with table(ms, readonly=False, ack=False) as t:
            t.flush()


def flagdata(ms, calls_path, result_path):
    from casatasks import flagdata as task

    calls = json.loads(Path(calls_path).read_text())
    out = []
    for kwargs in calls:
        start = time.perf_counter()
        ret = task(vis=ms, **kwargs)
        out.append({"kwargs": kwargs, "wall_s": time.perf_counter() - start,
                    "returned": repr(ret)})  # fmt: skip
    Path(result_path).write_text(json.dumps(out, indent=1) + "\n")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "prepare" and len(argv) in (4, 5):
        prepare(*argv[2:])
    elif cmd == "edit" and len(argv) == 4:
        edit(argv[2], argv[3])
    elif cmd == "flagdata" and len(argv) == 5:
        flagdata(argv[2], argv[3], argv[4])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
