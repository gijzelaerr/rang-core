"""Task C2e, run -00 (research/c2e-calibrate.md section 1): the library's
default paths give the same tables before and after C2e's additive edits.

    python examples/probe_c2e_defaults.py <code root> <out.json>

Imports `rang` from `<code root>/python` (main's checkout, then this
branch's) and writes SHA-256 hashes of every main-table cell of K, G and B
from `rang.cal_chain.primary` on O-CASA's slice and of G and F from
`rang.cal_fluxscale.bootstrap` on A1 small (fields 0 and 2, unit models,
A1's truth K and B pre-applied). Inputs are only read.
"""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / "python"))

import numpy as np
from rang import cal_chain, cal_fluxscale, cal_gain
from rang.formats import caltable

SLICE = Path.home() / "Github/rang/outputs/o-casa-20261030-01/work.ms"
A1 = Path("/mnt/d/rang/outputs/fp-a1-20261106-simtruth")


def sha(table):
    digest = hashlib.sha256()
    for name in sorted(table.main):
        digest.update(name.encode())
        for cell in table.main[name]:
            digest.update(
                b"-" if cell is None else np.ascontiguousarray(cell).tobytes()
            )
    return digest.hexdigest()


def main():
    out = {"rang": str(Path(cal_chain.__file__).resolve())}
    prim = cal_chain.primary(
        SLICE, field_id=1, refant=["m000"], b_combine="scan", minblperant=3, fillgaps=70
    )
    for k, v in prim.items():
        out[f"slice {k}"] = sha(v[0])
    ms = A1 / "small/a1-small.ms"
    pre = [
        caltable.read(A1 / "casa-small/truth.K"),
        caltable.read(A1 / "casa-small/truth.B"),
    ]
    nrow, nchan = cal_fluxscale._field_rows(ms, 0, 0)
    g, _, _ = cal_gain.gaincal(
        ms, field_id=0, refant=0, gaintable=pre,
        model=cal_fluxscale.smodel_array(nrow, nchan),
    )  # fmt: skip
    out["a1 G"] = sha(g)
    f, record, merged = cal_fluxscale.bootstrap(ms, g, [2], gaintable=pre, refant=0)
    out["a1 F"] = sha(f)
    out["a1 merged"] = sha(merged)
    out["a1 fd"] = cal_fluxscale.summary(record)
    Path(sys.argv[2]).write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
