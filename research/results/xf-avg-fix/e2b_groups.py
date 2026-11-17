"""Gate 2a of research/xf-avg-fix.md: on E2-B's MS (metadata only), the
averaging groups (`rang.cal_chunks.psi_groups`) of E2-B's P-rotated solves:
Gpol (3C 286, 60 s), KCROSS (3C 286, inf), Xf (3C 286, inf, combine scan),
Df (J1939-6342, inf, combine scan). None means every interval is one group,
so the fixed code averages exactly as before.

    python e2b_groups.py MS OUT.json
"""

import json
import sys
from pathlib import Path

import numpy as np
from rang import cal_chunks, cal_gain, cal_pol, core_ms

SOLVES = [
    ("Gpol", "J1331+3030", "60s", ""),
    ("KCROSS", "J1331+3030", "inf", ""),
    ("Xf", "J1331+3030", "inf", "scan"),
    ("Df", "J1939-6342", "inf", "scan"),
]


def main(ms, out):
    ms = Path(ms)
    with core_ms.open_table(ms / "FIELD") as t:
        names = [str(n) for n in t.getcol("NAME")]
    with core_ms.open_table(ms) as t:
        fields = np.asarray(t.getcol("FIELD_ID"))
    res = []
    for kind, name, solint, combine in SOLVES:
        fid = names.index(name)
        rows = np.flatnonzero(fields == fid)
        m = cal_gain._ms_columns(ms, cal_gain.META_COLUMNS, rows)
        tb, keys = cal_gain.solint_bins(
            m["TIME"], m["SCAN_NUMBER"], m["FIELD_ID"], solint, combine
        )
        table = cal_pol.angle_table(
            ms, m["TIME"], m["ANTENNA1"], m["ANTENNA2"], fid, "casa", -np.pi / 2
        )
        psi = cal_pol.table_angles(table, m["TIME"], m["ANTENNA1"], m["ANTENNA2"])[0]
        group = cal_chunks.psi_groups(tb, m["SCAN_NUMBER"], psi)
        spans = []
        for t in np.unique(tb):
            for s in np.unique(m["SCAN_NUMBER"][tb == t]):
                k = (tb == t) & (m["SCAN_NUMBER"] == s)
                d = np.angle(np.exp(1j * (psi[k] - psi[k][0])))
                spans.append(float(np.degrees(d.max() - d.min())))
        r = {
            "solve": kind, "field": name, "solint": solint, "combine": combine,
            "rows": len(rows), "intervals": len(keys),
            "scans": sorted(int(s) for s in np.unique(m["SCAN_NUMBER"])),
            "max_span_deg": max(spans), "groups": None if group is None
            else int(group.max()) + 1, "unchanged": group is None,
        }  # fmt: skip
        res.append(r)
        print(r)
    Path(out).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
