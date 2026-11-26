"""#60 rule 3 trace (research/k-fallback-60.md): why arm B's bandpass flags more solutions than A's.

    python k60_btrace.py RUN_ROOT OUT.json

Per arm, from the flag version saved at the start of calibrate (the solves' input) on J1939-6342:
per antenna, channel and parallel hand, the number of baselines longer than 150 m (E2-N's uvrange)
with at least one unflagged cell. A B solution with fewer than minblperant (4) such baselines has
no data to be solved from. Classifies the B-table cells flagged in arm B and not in arm A.
"""

import json
import sys
from pathlib import Path

import numpy as np

PRIMARY, MINBL, UVMIN = "J1939-6342", 4, 150.0


def support(ms, version):
    from rang import core_ms
    from rang.formats import flagversions

    with core_ms.open_table(f"{ms}/FIELD") as t:
        fid = [str(n) for n in t.getcol("NAME")].index(PRIMARY)
    with core_ms.open_table(f"{ms}/ANTENNA") as t:
        nant = t.nrows
    with core_ms.open_table(ms) as t:
        rows = np.flatnonzero(t.getcol("FIELD_ID") == fid)
        a1, a2 = t.getcol("ANTENNA1")[rows], t.getcol("ANTENNA2")[rows]
        uvw = t.getcol("UVW")[rows]
    nchan = None
    live = {}
    breaks = np.flatnonzero(np.diff(rows) != 1) + 1
    i = 0
    for run in np.split(rows, breaks):
        for s in range(0, len(run), 20000):
            start, n = int(run[s]), int(min(20000, len(run) - s))
            f, fr = flagversions.load(ms, version, start, n)
            ok = ~f & ~fr[:, None, None]
            nchan = f.shape[1]
            for j in range(n):
                k = i + j
                p, q = int(a1[k]), int(a2[k])
                if p == q or np.hypot(*uvw[k, :2]) <= UVMIN:
                    continue
                cell = ok[j][:, [0, 3]]
                if cell.any():
                    key = (p, q)
                    live[key] = live.get(key, np.zeros((nchan, 2), bool)) | cell
            i += n
    count = np.zeros((nant, nchan, 2), np.int32)
    for (p, q), m in live.items():
        count[p] += m
        count[q] += m
    return count


def btable(path):
    from rang.formats import caltable

    main = caltable.read(path).main
    ant = np.asarray(main["ANTENNA1"])
    flag = np.stack([np.asarray(f, bool) for f in main["FLAG"]])  # (row, chan, hand)
    return ant, flag


def main(root, out):
    root = Path(root)
    rec = {}
    tabs, counts = {}, {}
    for arm in "AB":
        ms = root / arm / "e2n.ms"
        summ = json.loads((root / arm / "e2n.ms.rang-run/calibrate/summary.json").read_text())
        counts[arm] = support(ms, summ["flag_version"])
        tabs[arm] = btable(root / arm / "e2n.ms.rang-run/calibrate/B")
        rec[arm] = {"flag_version": summ["flag_version"]}
    (aa, fa), (ab, fb) = tabs["A"], tabs["B"]
    assert np.array_equal(aa, ab)
    nant = counts["B"].shape[0]
    ca = counts["A"][aa][:, :, :2]
    cb = counts["B"][ab][:, :, :2]
    extra = fb[..., :2] & ~fa[..., :2]
    rec["B_flagged_A"] = float(fa[..., :2].mean())
    rec["B_flagged_B"] = float(fb[..., :2].mean())
    rec["extra_cells"] = int(extra.sum())
    rec["extra_with_fewer_than_minblperant_baselines_in_B"] = int((extra & (cb < MINBL)).sum())
    rec["extra_with_enough_baselines_in_B"] = int((extra & (cb >= MINBL)).sum())
    rec["flagged_B_with_enough_baselines"] = int((fb[..., :2] & (cb >= MINBL)).sum())
    rec["flagged_A_with_enough_baselines"] = int((fa[..., :2] & (ca >= MINBL)).sum())
    rec["extra_per_antenna"] = {int(a): int(extra[aa == a].sum()) for a in range(nant)
                                if extra[aa == a].any()}  # fmt: skip
    Path(out).write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])
