"""E2 flag probe (finish-plan 7 item 27): where rang's flag stage and
Tricolour 0.2.1 differ on E1's m32, by baseline and scan, and one scan group
extracted for the single-baseline runs.

    python e2_flagprobe_extract.py OUT [SCAN A1 A2]

Writes OUT/diff-by-baseline.json and OUT/group-scan<S>.npz: the whole scan
group (DATA, the input FLAG `rang_flag_*`, rang's flags after the flag stage
`rang_calibrate_*`, Tricolour's FLAG, TIME, ANTENNA1/2) and the metadata
`core_flag.flag_rows` needs. Without SCAN A1 A2 the probed baseline is the
one with most differing cells in the scan with most differing cells.
"""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "python"))
from rang import core_ms
from rang.formats import flagversions

MS = r"D:\rang\outputs\e1-20261109-03\ms\a1-full-m32.ms"
TMS = r"D:\rang\outputs\e1-20261109-04-tricolour\ms\a1-full-m32.ms"


def version(prefix):
    return next(v for v, _ in flagversions.versions(MS) if v.startswith(prefix))


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    with core_ms.open_table(MS) as t:
        cols = {
            n: t.getcol(n)
            for n in ("TIME", "ANTENNA1", "ANTENNA2", "FIELD_ID", "SCAN_NUMBER")
        }
        cols["DATA_DESC_ID"] = t.getcol("DATA_DESC_ID")
        ant = t.subtable("ANTENNA")
        pos = ant.getcol("POSITION")
        spw = t.subtable("SPECTRAL_WINDOW")
        chan_freq = spw.getcol("CHAN_FREQ")[0]
        chan_width = spw.getcol("CHAN_WIDTH")[0]
        pol = t.subtable("POLARIZATION")
        corr_type = pol.getcol("CORR_TYPE")[0]
    rang = flagversions.load(MS, version("rang_calibrate_"))[0].any(-1)
    with core_ms.open_table(TMS) as t:
        tri = t.getcol("FLAG").any(-1)
    d = rang != tri
    rows = np.flatnonzero(d.any(-1))
    keys = {}
    for r in rows:
        k = (
            int(cols["SCAN_NUMBER"][r]),
            int(cols["ANTENNA1"][r]),
            int(cols["ANTENNA2"][r]),
        )
        e = keys.setdefault(k, [0, 0])
        e[0] += int((rang[r] & ~tri[r]).sum())
        e[1] += int((~rang[r] & tri[r]).sum())
    table = sorted(
        (
            {
                "scan": k[0],
                "a1": k[1],
                "a2": k[2],
                "rang_only": v[0],
                "tricolour_only": v[1],
            }
            for k, v in keys.items()
        ),
        key=lambda e: -(e["rang_only"] + e["tricolour_only"]),
    )
    (out / "diff-by-baseline.json").write_text(json.dumps(table, indent=1))
    print(json.dumps(table[:10], indent=1))
    if len(sys.argv) > 4:
        scan, a1, a2 = map(int, sys.argv[2:5])
    else:
        scan, a1, a2 = table[0]["scan"], table[0]["a1"], table[0]["a2"]
    group = np.flatnonzero(cols["SCAN_NUMBER"] == scan)
    fields = np.unique(cols["FIELD_ID"][group])
    ddids = np.unique(cols["DATA_DESC_ID"][group])
    assert len(fields) == 1 and len(ddids) == 1, (fields, ddids)
    start, stop = int(group[0]), int(group[-1]) + 1
    assert stop - start == len(group), "scan rows are not contiguous"
    with core_ms.open_table(MS) as t:
        data = t.getcol("DATA", start, stop - start)
    flag_in = flagversions.load(MS, version("rang_flag_"), start, stop - start)[0]
    np.savez(
        out / f"group-scan{scan}.npz",
        data=data,
        flag_in=flag_in,
        rang=rang[start:stop],
        tricolour=tri[start:stop],
        time=cols["TIME"][start:stop],
        antenna1=cols["ANTENNA1"][start:stop],
        antenna2=cols["ANTENNA2"][start:stop],
        field_id=int(fields[0]),
        antenna_position=pos,
        chan_freq=chan_freq,
        chan_width=chan_width,
        corr_type=corr_type,
        probe=np.array([scan, a1, a2]),
    )
    print("probe", scan, a1, a2, "rows", stop - start, "data", data.shape)


if __name__ == "__main__":
    main()
