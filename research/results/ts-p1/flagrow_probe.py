"""TS-P1 14.6: does leaving FLAG_ROW rows out of GeMClean's weight grid change
any archived GeMClean case? It changes an image only through rows whose
FLAG_ROW is set and whose Stokes I weight is nonzero (both hands unflagged,
finite, weight > 0): those rows used to enter the uniform/Briggs density and
no longer do (their gridding weight was already zero). This counts such
samples, over every field, in the thirteen archived G2-G9 Measurement Sets of
research/results/gemclean-beam-uv/probe.jsonl. Zero everywhere means every
archived GeMClean output is unchanged bit for bit.

    python flagrow_probe.py   # writes flagrow_probe.jsonl beside this file
"""

import json
from pathlib import Path

import numpy as np
from rang import core_ms

HERE = Path(__file__).resolve().parent
LIST = HERE.parents[0] / "gemclean-beam-uv" / "probe.jsonl"


def probe(path, block=20000):
    t = core_ms.open_table(path)
    names = t.colnames()
    nrow = t.nrows
    rows_flagged = samples = 0
    for r0 in range(0, nrow, block):
        k = min(block, nrow - r0)
        frow = np.asarray(t.getcol("FLAG_ROW", r0, k)).astype(bool)
        if not frow.any():
            continue
        idx = np.flatnonzero(frow) + r0
        rows_flagged += len(idx)
        flag = t.getcol_rows("FLAG", idx)
        if "WEIGHT_SPECTRUM" in names:
            w = t.getcol_rows("WEIGHT_SPECTRUM", idx)
        else:
            w = np.broadcast_to(t.getcol_rows("WEIGHT", idx)[:, None, :], flag.shape)
        ok = ~flag[..., 0] & ~flag[..., 3] & (w[..., 0] > 0) & (w[..., 3] > 0)
        samples += int(ok.sum())
    return {"ms": path, "rows": nrow, "flag_row_rows": rows_flagged,
            "flag_row_samples_with_weight": samples}  # fmt: skip


def main():
    out = HERE / "flagrow_probe.jsonl"
    lines = []
    for line in LIST.read_text(encoding="utf-8").splitlines():
        ms = json.loads(line)["ms"]
        rec = probe(ms)
        print(json.dumps(rec), flush=True)
        lines.append(json.dumps(rec))
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
