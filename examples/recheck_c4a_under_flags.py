"""Development set of task C4b (research/c4b-apply-ms.md, section 4): C4a's
kept `applycal` exports re-evaluated with the current kernel on every cell,
flagged cells included (post hoc against C4b's protocol; not its verdict).

    python examples/recheck_c4a_under_flags.py <out.json> [--outputs <dir>]

Reads `/mnt/d/rang/outputs/c4a-20261106-0{1,2,3,4}` (exports and tables)
and O-CASA's `c.ms` and E4's tables under `<dir>` (default
`~/Github/rang/outputs`).
"""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import check_apply as ca
import check_formats as cf
from rang import cal_apply
from rang.formats import caltable

RUNS = {
    "c4a-20261106-01": None,
    "c4a-20261106-02": None,
    "c4a-20261106-03": 20261107,
    "c4a-20261106-04": 20261108,
}


def main(argv):
    out = Path(argv[1])
    outputs = Path.home() / "Github/rang/outputs"
    if "--outputs" in argv:
        outputs = Path(argv[argv.index("--outputs") + 1])
    ms = outputs / "o-casa-20261030-01" / "c.ms"
    e4 = outputs / "e4-20261030-01" / "casa"
    t_table = outputs / "dfio-20261030-02" / "ct" / "casa" / "x.T"
    cols = cf.ms_columns(ms)
    fid = cf.field_index(ms)
    freqs = cf.ms_frequencies(ms)
    sel = cols["FIELD_ID"] == fid
    nant = int(max(cols["ANTENNA1"].max(), cols["ANTENNA2"].max())) + 1
    data, base_flag = cols["DATA"][sel], cols["FLAG"][sel]
    a1, a2, times = cols["ANTENNA1"][sel], cols["ANTENNA2"][sel], cols["TIME"][sel]
    report = {}
    for name, seed in RUNS.items():
        run = Path("/mnt/d/rang/outputs") / name
        if seed is None:
            plan, edited = ca.frozen_cases(e4, t_table), set()
        else:
            plan, edited = ca.heldout_cases(seed)
        for case, tabs in plan.items():
            export = run / "export" / f"{case}.npz"
            if not export.is_file():
                continue
            z = np.load(export)
            casa, cflag = z["corrected"], z["flag"]
            f0 = ca.edit_flags(base_flag, a1, a2) if case in edited else base_flag
            tables = []
            for p, _ in tabs:
                path = run / p if str(p).startswith("synth/") else Path(p)
                tables.append(caltable.read(path))
            got, gflag = cal_apply.apply(
                data,
                f0,
                times,
                a1,
                a2,
                freqs,
                tables,
                field_id=fid,
                interp=[m for _, m in tabs],
                nant=nant,
            )
            every = np.ones(cflag.shape, bool)
            under = gflag & ~f0
            both_ok = ~cflag & ~gflag
            entry = {
                "flags_exact": bool(np.array_equal(cflag, gflag)),
                "all_cells": cal_apply.class_c(got, casa, every),
                "unflagged": cal_apply.class_c(got, casa, both_ok),
                "under_solution_flags": cal_apply.class_c(got, casa, under)
                if under.any()
                else None,
                "under_input_flags": cal_apply.class_c(got, casa, f0)
                if f0.any()
                else None,
            }
            report[f"{name}/{case}"] = entry
            a = entry["all_cells"]
            print(
                f"{name}/{case:24s} flags={entry['flags_exact']} all: pass={a['pass']} "
                f"eps={a['max_float32_eps_of_cell']:.3g} failing={a['failing']}"
            )
    out.write_text(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
