"""solver-flags-2 (#58), design input read before the note was frozen: how
mild each candidate raw start is on E2-N, from FLAG, channel frequencies and
UVW only (no DATA, no stage run).

    python sf2_mild.py MS FLAGVERSION OUT.json

FLAGVERSION is the version in MS.flagversions holding the online flags. Per
field, over cross-correlation rows (sf_score.py's rows), the fraction of
(row, channel) cells flagged in any correlation for:
online; online + Tricolour's static masks on every baseline (the
`apply_static_mask` mapping of core/src/sumthreshold.rs: a channel is masked
when a masked frequency lies in [centre - width/2, centre + width/2));
online + `flag.known_rfi: meerkat_l` (core_pipeline.known_rfi_pass's rule);
online + both.
"""

import json
import sys
from pathlib import Path

import numpy as np
from rang import core_flag, core_ms, meerkat


def static_channels(freq, width):
    out = np.zeros(len(freq), bool)
    for path in core_flag.static_mask_files():
        m = np.sort(core_flag.load_static_mask(path))
        m = m[~np.isnan(m)]
        lb, ub = freq - width * 0.5, freq + width * 0.5
        first = np.searchsorted(m, lb, side="left")
        ok = first < len(m)
        out[ok] |= m[first[ok]] < ub[ok]
    return out


def main(ms, version, outp):
    ms = Path(ms)
    with core_ms.open_table(ms / "SPECTRAL_WINDOW") as t:
        freq = np.asarray(t.getcol("CHAN_FREQ"), np.float64)[0]
        width = np.abs(np.asarray(t.getcol("CHAN_WIDTH"), np.float64)[0])
    with core_ms.open_table(ms / "OBSERVATION") as t:
        tel = str(t.getcol("TELESCOPE_NAME")[0])
    with core_ms.open_table(ms / "FIELD") as t:
        names = [str(n) for n in t.getcol("NAME")]
    st = static_channels(freq, width)
    pall, pshort = meerkat.known_rfi_l(tel, freq, width)
    metres = meerkat.KNOWN_RFI_L_SHORT_M
    with core_ms.open_table(ms) as t:
        fid = t.getcol("FIELD_ID")
        a1, a2 = t.getcol("ANTENNA1"), t.getcol("ANTENNA2")
    out = {"channels": len(freq), "static_channels": int(st.sum()),
           "preset_all": int(pall.sum()), "preset_short": int(pshort.sum()),
           "fields": {}}  # fmt: skip
    fv = ms.parent / f"{ms.name}.flagversions" / f"flags.{version}"
    with core_ms.open_table(fv) as tf, core_ms.open_table(ms) as t:
        for f, name in enumerate(names):
            rows = np.flatnonzero((fid == f) & (a1 != a2))
            if not len(rows):
                continue
            acc = dict.fromkeys(("online", "static", "preset", "both"), 0)
            cells = 0
            for i in range(0, len(rows), 20000):
                r = rows[i : i + 20000]
                fl = tf.getcol_rows("FLAG", r).any(-1)
                uvw = t.getcol_rows("UVW", r)
                near = np.hypot(uvw[:, 0], uvw[:, 1]) < metres
                pre = np.zeros_like(fl)
                pre[:, pall] = True
                pre[np.ix_(near, pshort)] = True
                acc["online"] += int(fl.sum())
                acc["static"] += int((fl | st).sum())
                acc["preset"] += int((fl | pre).sum())
                acc["both"] += int((fl | pre | st).sum())
                cells += fl.size
            out["fields"][name] = {k: v / cells for k, v in acc.items()} | {
                "cells": cells
            }
            print(name, out["fields"][name], flush=True)
    Path(outp).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
