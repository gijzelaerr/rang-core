# SPDX-License-Identifier: MIT
"""research/calchain-floor.md: one rang U arm on a copy of a case's pristine
simulated MS (e2a-3b-k's arm `u` config: `d1_run.rang_config("tt")`).

    python cf_run.py CASE ARM        CASE stepped|const, ARM lin|near|strict|f50|lin2|zs

`f50` (section 11, post hoc): `lin` with ID 50's rows in K1 interval 7
(`cal_gain.solint_bins`, 60 s, field 0) flagged before the run.
`lin2` (section 12): `lin` again with this branch's code after the
`k_zero_start` change, the key off; `zs`: `lin` with `k_zero_start: true`.

The arm's MS is O/CASE/arm-ARM.ms (copied from O/CASE/sim-s0f-u.ms, which
is never written); its run is O/CASE/arm-ARM.ms.rang-run.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DIAG = ROOT / "research" / "results" / "e2a-3b-diag"
sys.path.insert(0, str(DIAG))

import d1_run

O = Path.home() / "rang-data" / "outputs" / "calchain-floor-20261117"
PY = ROOT / ".venv" / "bin" / "python"
THREADS = os.environ.get("K_THREADS", "2")


def config(arm):
    text = d1_run.rang_config("tt")
    head, rest = text.split("\ncalibrate:\n", 1)
    cal, tail = rest.split("\napply:\n", 1)
    if arm == "near":
        n1 = cal.count("interp: [linear]")
        n2 = cal.count("interp: [linear, linear]")
        assert (n1, n2) == (1, 4), (n1, n2)  # G0; B0, K1, G1, B1
        cal = cal.replace("interp: [linear, linear]", "interp: [nearest, nearest]")
        cal = cal.replace("interp: [linear]", "interp: [nearest]")
    text = head + "\ncalibrate:\n" + cal + "\napply:\n" + tail
    return text.replace(
        "e2a-3b-diag.md D1 case", f"calchain-floor.md arm {arm}, from D1 case"
    )


def flag_interval(ms, ant, interval):
    import numpy as np
    from rang import cal_gain, core_ms, core_ms_write

    with core_ms.open_table(ms / "FIELD") as t:
        fid = [str(x) for x in t.getcol("NAME")].index("J1939-6342")
    with core_ms.open_table(ms) as t:
        c = {
            n: np.asarray(t.getcol(n))
            for n in ("TIME", "SCAN_NUMBER", "FIELD_ID", "ANTENNA1", "ANTENNA2")
        }
    rows = np.flatnonzero(c["FIELD_ID"] == fid)
    tb, _ = cal_gain.solint_bins(
        c["TIME"][rows], c["SCAN_NUMBER"][rows], c["FIELD_ID"][rows], "60s", ""
    )
    sel = rows[
        (tb == interval) & ((c["ANTENNA1"][rows] == ant) | (c["ANTENNA2"][rows] == ant))
    ]
    with core_ms_write.open_table(ms, readonly=False) as t:
        f = np.asarray(t.getcol("FLAG"))
        f[sel] = True
        t.putcol("FLAG", f)
    print(f"flagged {len(sel)} rows of antenna {ant} in interval {interval}")


def main(case, arm):
    d = O / case
    ms = d / f"arm-{arm}.ms"
    if ms.exists():
        raise SystemExit(f"{ms} exists")
    t0 = time.perf_counter()
    shutil.copytree(d / "sim-s0f-u.ms", ms)
    copy_s = time.perf_counter() - t0
    if arm == "f50":
        flag_interval(ms, 50, 7)
    cfg = d / f"arm-{arm}.yaml"
    cfg.write_text(config("lin" if arm in ("f50", "lin2") else arm), encoding="utf-8")
    shutil.copy(DIAG / "pinned" / "mk_rfi_flagging_calibrator_fields_firstpass.yaml", d)
    env = {**os.environ, "PYTHONPATH": "", "RAYON_NUM_THREADS": THREADS,
           "OMP_NUM_THREADS": THREADS}  # fmt: skip
    if arm == "strict":
        argv = [
            str(PY),
            str(DIAG / "d1_rang_iter.py"),
            "1000:1e-12:1.0",
            "run",
            str(cfg),
            str(ms),
        ]
    else:
        argv = [str(PY), "-m", "rang.core_cli", "run", str(cfg), str(ms)]
    t0 = time.perf_counter()
    with open(d / f"arm-{arm}.log", "w", encoding="utf-8") as fh:
        rc = subprocess.run(argv, stdout=fh, stderr=subprocess.STDOUT, check=False,
                            env=env).returncode  # fmt: skip
    dt = time.perf_counter() - t0
    (d / f"arm-{arm}-run.json").write_text(
        json.dumps({"exit": rc, "seconds": dt, "copy_seconds": copy_s, "argv": argv})
        + "\n"
    )
    print(case, arm, "rc", rc, f"{dt:.1f}s")
    return rc


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
