# SPDX-License-Identifier: GPL-3.0-or-later
"""Archive CASA's flags on the first baselines of the D1 probes (S1, S2) so
that CI checks rang's per-row rule against CASA without CASA
(research/v8-tfcrop.md, section 7; `tests/test_v8_tfcrop.py`).

Usage: tfcrop_probe_archive.py PROBES_DIR OUT.json [NBL]

The designs draw their random numbers plane by plane, so the first NBL
baselines of a design rebuilt with `nbl=NBL` are the planes CASA saw.
"""

import base64
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tfcrop_probe_eval import load_flags

ARMS = (("b02", "S1", "p7", 3.0), ("b02", "S1", "p1", 3.0),
        ("b03", "S2", "p7", 3.0), ("b03", "S2", "p7_c4", 4.0))  # fmt: skip


def main(argv):
    root, out = Path(argv[0]), Path(argv[1])
    nbl = int(argv[2]) if len(argv) > 2 else 12
    rec = {"nbl": nbl, "ntime": 40, "nchan": 256, "source": "CASA 6.7.6.14, rang-o-casa",
           "arms": []}  # fmt: skip
    for batch, design, arm, cut in ARMS:
        meta = json.loads((root / batch / f"{design}.json").read_text(encoding="utf-8"))
        full = meta["nbl"]
        flags = load_flags(root / batch / "out" / f"{design}.{arm}.npz")
        sub = np.stack([flags[b::full, :, c] for b in range(nbl) for c in range(4)])
        rec["arms"].append({"design": design, "arm": arm, "freqcutoff": cut,
                            "flags": base64.b64encode(np.packbits(sub.reshape(-1))).decode(),
                            "flagged": int(sub.sum())})  # fmt: skip
    out.write_text(json.dumps(rec, indent=1), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main(sys.argv[1:])
