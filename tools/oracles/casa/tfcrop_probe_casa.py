# SPDX-License-Identifier: GPL-3.0-or-later
"""CASA side of the tfcrop probes (research/v8-tfcrop.md, section 3, labelled
probe). Runs inside `rang-o-casa:6.7.6.14` with `/opt/casa/bin/python -I`.

Usage: tfcrop_probe_casa.py OUT_DIR JOB.json

JOB.json is a list of `{"name", "template", "data", "calls": [params, ...]}`:
the template MS is copied to /tmp, DATA (complex64, (row, chan, corr)) and
FLAG of the `data` npz are written into the copy, every call runs as
`casatasks.flagdata(vis=COPY, flagbackup=False, **params)`, and FLAG and
FLAG_ROW are saved to OUT_DIR/NAME.npz (`np.packbits` of FLAG, its shape,
FLAG_ROW) with the calls' returns and walls in OUT_DIR/NAME.json. One CASA
process serves the whole job, so a probe batch costs seconds.
"""

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np


def main(argv):
    from casatasks import flagdata
    from casatools import table

    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    job = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    cache = {}
    for case in job:
        t0 = time.time()
        work = Path("/tmp/work.ms")
        if work.exists():
            shutil.rmtree(work)
        shutil.copytree(case["template"], work)
        if case["data"] not in cache:
            z = np.load(case["data"])
            cache = {case["data"]: (z["data"], z["flag"])}
        data, flag = cache[case["data"]]
        tb = table()
        tb.open(str(work), nomodify=False)
        try:
            tb.putcol("DATA", np.ascontiguousarray(np.transpose(data, (2, 1, 0))))
            tb.putcol("FLAG", np.ascontiguousarray(np.transpose(flag, (2, 1, 0))))
            tb.putcol("FLAG_ROW", np.zeros(data.shape[0], bool))
        finally:
            tb.close()
        log = {"name": case["name"], "calls": []}
        for params in case["calls"]:
            t1 = time.time()
            err = None
            try:
                ret = flagdata(vis=str(work), flagbackup=False, **params)
            except Exception as exc:  # noqa: BLE001 - recorded
                ret, err = None, repr(exc)
            log["calls"].append({"params": params, "error": err,
                                 "return": None if ret is None else str(ret)[:2000],
                                 "wall_s": time.time() - t1})  # fmt: skip
        tb.open(str(work))
        try:
            f = np.ascontiguousarray(np.transpose(tb.getcol("FLAG"), (2, 1, 0)))
            fr = tb.getcol("FLAG_ROW")
        finally:
            tb.close()
        np.savez_compressed(out / f"{case['name']}.npz", flag=np.packbits(f.reshape(-1)),
                            shape=np.array(f.shape), flag_row=fr)  # fmt: skip
        log["flagged"] = int(f.sum())
        log["wall_s"] = time.time() - t0
        (out / f"{case['name']}.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
        print(f"{case['name']}: {log['flagged']} flagged, {log['wall_s']:.1f} s", flush=True)
        shutil.rmtree(work)


if __name__ == "__main__":
    main(sys.argv[1:])
