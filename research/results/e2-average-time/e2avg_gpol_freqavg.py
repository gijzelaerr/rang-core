"""Post hoc (after luno-score.json and luno-gpol-ones.json, 2026-11-11): is
the Gpol class-B miss on LUNO scan 1 CASA's frequency pre-averaging? CASA's
G-type solves average the selected channels of a window before solving;
rang's kernel takes every channel as a sample of one frequency bin.

Arm `control`: `cal_pol.gpol` as the chain called it (rang's own K, G, B
tables, average_time, 8 GiB budget); must equal the frozen rang Gpol.
Arm `freqavg`: the same with `cal_gain._kernel` wrapped to average each
chunk's data and model over channels first (weighted by the solve weights
over unflagged cells, per row and correlation; a cell with no weight is
flagged), so the solve sees one channel. Both scored against CASA's Gpol.
    python e2avg_gpol_freqavg.py RUN   (under tools/heavy_lock.py)"""

import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import e2avg_common as C
import e2avg_luno as L
from rang import cal_gain, cal_pol, core_chunks, core_ms
from rang.formats import caltable


def freq_averaged(kernel):
    def wrapped(data, model, weights, flag, *args, **kw):
        w = np.where(flag, 0.0, weights.astype(np.float64))
        sw = w.sum(axis=1, keepdims=True)
        with np.errstate(invalid="ignore", divide="ignore"):
            d = np.where(sw > 0, (w * data).sum(axis=1, keepdims=True) / sw, 0)
            m = np.where(sw > 0, (w * model).sum(axis=1, keepdims=True) / sw, 0)
        kw["freq_bin"] = None
        return kernel(d.astype(np.complex64), m.astype(np.complex64),
                      sw.astype(np.float32), sw <= 0, *args, **kw)  # fmt: skip
    return wrapped


def solve(ms, run):
    rdir = Path(str(ms) + ".rang-run") / "calibrate"
    tables = [caltable.read(rdir / n) for n in ("K", "G", "B")]
    with core_ms.open_table(ms) as t:
        nrows = t.nrows
    with core_ms.open_table(Path(ms) / "SPECTRAL_WINDOW") as t:
        nchan = len(t.getcol("CHAN_FREQ")[0])
    budget = core_chunks.Budget(8.0, int(nrows), (nchan, 4)).chain()
    table, sol, info = cal_pol.gpol(
        ms, field_id=0, solint="60s", combine="", refant=["m022", "m023", "m024"],
        refantmode="flex", minsnr=3.0, minblperant=4, uvrange=">150",
        gaintable=tables, interp=["linear"] * 3, parang=True, frame="casa",
        model_column="MODEL_DATA", receptor_angle=float(np.deg2rad(-90.0)),
        weight_column=None, budget=budget, average_time=True,
    )  # fmt: skip
    return table


def main(run):
    run = Path(run)
    own, casa_ms = L.ms_paths(run)
    frozen = C.table(Path(str(own) + ".rang-run") / "calibrate" / "Gpol")
    casa = C.table(casa_ms.parent / "Gpol")
    out = {}
    original = cal_gain._kernel
    for arm in ("control", "freqavg"):
        cal_gain._kernel = original if arm == "control" else freq_averaged(original)
        t0 = time.perf_counter()
        tab = solve(own, run)
        out[arm] = {
            "wall_s": time.perf_counter() - t0,
            "vs_frozen_rang": C.term_diff(tab, frozen, "phase"),
            "vs_casa": C.term_diff(tab, casa, "phase"),
        }
        print(arm, json.dumps(out[arm]), flush=True)
    cal_gain._kernel = original
    C.write(run / "luno-gpol-freqavg.json", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
