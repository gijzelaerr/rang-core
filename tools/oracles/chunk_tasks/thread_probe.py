# SPDX-License-Identifier: MIT
"""Thread-count probe for stage 1b (research/chunk-task-api-1b.md, section 0).

Runs the chain kernels (K, G, B, Gpol, KCROSS, Xf, Df, F) and CASA-table
applycal on the W3b test MS at RAYON_NUM_THREADS 1, 2 and 4, each in a fresh
process, and prints the SHA-256 of every output. Usage:

    python tools/oracles/chunk_tasks/thread_probe.py WORKDIR

A stage whose hash differs between thread counts cannot be split as N
processes at T/N threads with a bit-identical gate.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def child(work):
    sys.path.insert(0, str(ROOT / "tests"))
    import numpy as np
    from rang import (
        applycal,
        cal_bandpass,
        cal_chain,
        cal_delay,
        cal_fluxscale,
        cal_gain,
        cal_pol,
        core_ms,
    )
    from test_c2e_calibrate import calibrator_ms
    from test_c6w_polwire import _with_feed

    work = Path(work)
    ms = work / "x.ms"
    if not ms.exists():
        ms = _with_feed(calibrator_ms(ms))

    def unit(field, stokes=(1.0, 0.0, 0.0, 0.0)):
        nrow, nchan = cal_fluxscale._field_rows(ms, field, 0)
        return cal_fluxscale.smodel_view(nrow, nchan, stokes)

    out = {}
    k = cal_delay.gaincal(
        ms, field_id=0, refant=0, model=unit(0), weight_column="WEIGHT"
    )
    out["K"] = cal_chain._sha(k[0])
    g = cal_gain.gaincal(ms, field_id=0, refant=0, solint="int", gaintable=[k[0]], minblperant=3,
                         model=unit(0), weight_column="WEIGHT")  # fmt: skip
    out["G"] = cal_chain._sha(g[0])
    b = cal_bandpass.bandpass(ms, field_id=0, refant=0, gaintable=[k[0], g[0]], minblperant=3,
                              model=unit(0), weight_column="WEIGHT")  # fmt: skip
    out["B"] = cal_chain._sha(b[0])
    tables = [k[0]]
    pol = unit(1, (1.0, 0.05, 0.08, 0.0))
    common = {
        "field_id": 1,
        "gaintable": tables,
        "model": pol,
        "weight_column": "WEIGHT",
    }
    out["Gpol"] = cal_chain._sha(
        cal_pol.gpol(ms, solint="int", refant=0, minblperant=2, **common)[0]
    )
    out["KCROSS"] = cal_chain._sha(cal_pol.kcross(ms, solint="int", **common)[0])
    out["Xf"] = cal_chain._sha(cal_pol.xf(ms, combine="scan", **common)[0])
    out["Df"] = cal_chain._sha(
        cal_pol.df(
            ms,
            combine="scan",
            minblperant=2,
            min_data_fraction=0.5,
            minsnr=0.0,
            **common,
        )[0]  # fmt: skip
    )
    run = work / f"apply-{os.environ['RAYON_NUM_THREADS']}.ms"
    shutil.rmtree(run, ignore_errors=True)
    shutil.copytree(ms, run)
    applycal.applycal(run, [k[0], g[0], b[0]], field=[0, 1], parang=True,
                      calwt=[False, True, True])  # fmt: skip
    with core_ms.open_table(run) as t:
        for name in ("CORRECTED_DATA", "FLAG", "WEIGHT"):
            out[f"apply {name}"] = hashlib.sha256(
                np.ascontiguousarray(t.getcol(name)).tobytes()
            ).hexdigest()
    shutil.rmtree(run, ignore_errors=True)
    print(json.dumps(out))


def main(work):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    runs = {}
    for n in (1, 2, 4, 1):  # the first run of 1 also makes the MS
        env = dict(os.environ, RAYON_NUM_THREADS=str(n))
        got = subprocess.run(
            [sys.executable, __file__, "--child", str(work)],
            env=env, capture_output=True, text=True, check=True,
        )  # fmt: skip
        runs.setdefault(n, json.loads(got.stdout.strip().splitlines()[-1]))
    names = runs[1].keys()
    ok = True
    for name in names:
        hashes = {n: runs[n][name] for n in runs}
        same = len(set(hashes.values())) == 1
        ok &= same
        print(f"{name:22s} {'equal' if same else 'DIFFERS'} {runs[1][name][:16]}")
    print("thread probe:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    if sys.argv[1] == "--child":
        child(sys.argv[2])
    else:
        sys.exit(main(sys.argv[1]))
