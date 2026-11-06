"""Post-hoc re-evaluation for task C4b (research/c4b-apply-ms.md): the
current `rang.applycal` against the CASA exports of an earlier run of
`examples/check_apply_ms.py`, for the cases whose input is an unedited copy
(`S-plain`, `A-plain`), which can be rebuilt without CASA.

    python examples/recheck_apply_ms.py <run> <out.json> [--outputs <dir>]

Labelled post hoc wherever it is reported: it fits the data it re-reads.
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_apply_ms as cam
from rang import applycal, cal_apply, core_ms
from rang.formats import caltable


def main(argv):
    run, out = Path(argv[1]), Path(argv[2])
    outputs = Path.home() / "Github/rang/outputs"
    if "--outputs" in argv:
        outputs = Path(argv[argv.index("--outputs") + 1])
    sources = {
        "S-plain": (outputs / "o-casa-20261030-01" / "c.ms").resolve(),
        "A-plain": cam.A1_SMALL,
    }
    e4 = (outputs / "e4-20261030-01" / "casa").resolve()
    report = {}
    with tempfile.TemporaryDirectory(dir="/mnt/d/rang/outputs") as tmp:
        for case, (variant, _cf, rfield, tabs, calwt) in cam.cases(e4).items():
            if variant not in sources:
                continue
            ms = Path(tmp) / f"{case}.ms"
            shutil.copytree(sources[variant], ms)
            tables = [
                caltable.read(run / p if str(p).startswith("synth/") else Path(p))
                for p, _, _ in tabs
            ]
            applycal.applycal(
                ms,
                tables,
                interp=[m for _, m, _ in tabs],
                gainfield=[g for _, _, g in tabs],
                calwt=calwt,
                field=rfield,
            )
            with core_ms.open_table(ms) as t:
                got, flag = t.getcol("CORRECTED_DATA"), t.getcol("FLAG")
            c = np.load(run / "export" / f"casa-{case}.npz")
            every = np.ones(got.shape, bool)
            report[case] = {
                "all_cells": cal_apply.class_c(got, c["CORRECTED_DATA"], every),
                "flags_exact": bool(np.array_equal(flag, c["FLAG"])),
            }
            a = report[case]["all_cells"]
            print(
                f"{case:16s} pass={a['pass']} eps={a['max_float32_eps_of_cell']:.3g} "
                f"failing={a['failing']} flags={report[case]['flags_exact']}"
            )
    out.write_text(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
