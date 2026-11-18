"""E2-N follow-up, job 2 (research/e2n-followup.md): Tricolour rerun as E2-N's
gate 3a ran it, with the differing cells kept this time.

    python fu_tricolour.py run   MS R STRATEGY   Tricolour 0.2.1, E2-N's argv  -> R/tricolour.out
    python fu_tricolour.py dump  MS R            every differing cell          -> R/fu-3a-cells.json, .npz
    python fu_tricolour.py restore MS R INPUT    FLAG back to rang_original, hash against INPUT

`run` is e2_post.tricolour's container call, unchanged (same image, argv and
16 threads); `dump` is its comparison (FLAG after Tricolour against rang's FLAG
after the flag stage, cell = row x channel, differing if any correlation
differs), plus each cell's position and a 7 x 7 (time x channel) window of both
flag sets on its baseline. Run through e2n_nash.py's apptainer runner.
"""

import json
import shutil
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT / "research" / "results" / "e2n-scripts"),
                str(ROOT / "research" / "results" / "e2-acceptance-scripts")]  # fmt: skip

import e2_post as P
import e2n_nash  # noqa: F401  (patches e2_post.docker to apptainer)

HALF = 3


def run(ms, r, strategy):
    ms, r = Path(ms), Path(r)
    shutil.copy(strategy, r / "tricolour-strategy.yaml")
    base = "tricolour -c /p/tricolour-strategy.yaml -fs polarisation -dc DATA -dpm"
    rc = P.docker(r, P.TRICOLOUR_IMAGE, [(ms.parent, "/ms"), (r, "/p")],
                  f"{base} /ms/{ms.name}", "tricolour", 16)  # fmt: skip
    P.write(r / "fu-tricolour-run.json", {"tricolour_exit": rc})
    return rc


def rang_flag_version(r):
    s = json.loads((Path(r) / "rang-run-moved" / "state.json").read_text())
    return s["stages"]["calibrate"]["flag_version"]  # before calibrate = after flag


def dump(ms, r):
    from rang import core_ms
    from rang.formats import flagversions

    ms, r = Path(ms), Path(r)
    name = rang_flag_version(r)
    cells, acc = [], {"elements_differ": 0, "cells_differ": 0, "rang_only": 0,
                      "tricolour_only": 0, "corr_partial": 0, "cells": 0}  # fmt: skip
    with core_ms.open_table(ms) as t:
        n = t.nrows
        for r0 in range(0, n, P.BLOCK):
            k = min(P.BLOCK, n - r0)
            a = np.asarray(flagversions.load(ms, name, r0, k)[0], bool)
            b = np.asarray(t.getcol("FLAG", r0, k), bool)
            d = (a != b).any(-1)
            acc["elements_differ"] += int((a != b).sum())
            acc["cells_differ"] += int(d.sum())
            acc["rang_only"] += int((a.any(-1) & ~b.any(-1)).sum())
            acc["tricolour_only"] += int((~a.any(-1) & b.any(-1)).sum())
            acc["corr_partial"] += int((d & ~(a != b).all(-1)).sum())
            acc["cells"] += int(d.size)
            for i, c in zip(*np.nonzero(d)):
                cells.append({"row": int(r0 + i), "chan": int(c),
                              "rang": a[i, c].astype(int).tolist(),
                              "tricolour": b[i, c].astype(int).tolist()})  # fmt: skip
        cols = {c: np.asarray(t.getcol(c)) for c in
                ("TIME", "SCAN_NUMBER", "FIELD_ID", "ANTENNA1", "ANTENNA2")}  # fmt: skip
        with core_ms.open_table(ms / "SPECTRAL_WINDOW") as s:
            freq = np.asarray(s.getcol("CHAN_FREQ"))[0]
        with core_ms.open_table(ms / "FIELD") as s:
            fields = [str(x) for x in s.getcol("NAME")]
        with core_ms.open_table(ms / "ANTENNA") as s:
            ants = [str(x) for x in s.getcol("NAME")]
        nchan = freq.size
        win_a, win_b, win_data = [], [], []
        for cell in cells:
            row, c = cell["row"], cell["chan"]
            sc, a1, a2 = (
                int(cols[k][row]) for k in ("SCAN_NUMBER", "ANTENNA1", "ANTENNA2")
            )
            same = np.nonzero((cols["SCAN_NUMBER"] == sc) & (cols["ANTENNA1"] == a1)
                              & (cols["ANTENNA2"] == a2))[0]  # fmt: skip
            same = same[np.argsort(cols["TIME"][same])]
            it = int(np.nonzero(same == row)[0][0])
            c0, c1 = max(0, c - HALF), min(nchan, c + HALF + 1)
            wa = np.full((2 * HALF + 1, 2 * HALF + 1, 4), -1, np.int8)
            wb = wa.copy()
            wd = np.full((2 * HALF + 1, 2 * HALF + 1, 4), np.nan, np.float32)
            for j in range(-HALF, HALF + 1):
                if 0 <= it + j < same.size:
                    rr = int(same[it + j])
                    fa = np.asarray(flagversions.load(ms, name, rr, 1)[0], bool)[
                        0, c0:c1
                    ]
                    fb = np.asarray(t.getcol("FLAG", rr, 1), bool)[0, c0:c1]
                    dd = np.abs(np.asarray(t.getcol("DATA", rr, 1))[0, c0:c1])
                    s0 = c0 - (c - HALF)
                    wa[j + HALF, s0 : s0 + fa.shape[0]] = fa
                    wb[j + HALF, s0 : s0 + fb.shape[0]] = fb
                    wd[j + HALF, s0 : s0 + dd.shape[0]] = dd
            win_a.append(wa)
            win_b.append(wb)
            win_data.append(wd)
            cell.update({
                "time": float(cols["TIME"][row]), "scan": sc,
                "field": fields[int(cols["FIELD_ID"][row])],
                "ant1": ants[a1], "ant2": ants[a2],
                "time_index_in_scan": it, "times_in_scan": int(same.size),
                "freq_mhz": float(freq[c] / 1e6),
                "neighbours_flagged_rang_3x3": int((wa[HALF - 1 : HALF + 2, HALF - 1 : HALF + 2] == 1).any(-1).sum()),
                "neighbours_flagged_tricolour_3x3": int((wb[HALF - 1 : HALF + 2, HALF - 1 : HALF + 2] == 1).any(-1).sum()),
                "abs_data": np.abs(np.asarray(t.getcol("DATA", row, 1))[0, c]).tolist(),
            })  # fmt: skip
    np.savez_compressed(r / "fu-3a-windows.npz", rang=np.array(win_a), tricolour=np.array(win_b),
                        abs_data=np.array(win_data))  # fmt: skip
    P.write(r / "fu-3a-cells.json", {"rang_version": name, **acc, "exact": acc["elements_differ"] == 0,
                                     "window_half": HALF, "cells_list": cells})  # fmt: skip
    return 0


def restore(ms, r, input_json):
    return P.restore(ms, r, input_json, label="fu-3a-restore")


if __name__ == "__main__":
    step, *args = sys.argv[1:]
    sys.exit({"run": run, "dump": dump, "restore": restore}[step](*args))
