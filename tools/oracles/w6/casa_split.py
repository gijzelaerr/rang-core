"""CASA 6.7.6 split of scans (W6 criterion 1a, 4b): DATA, flags kept.

    /opt/casa/bin/python -I casa_split.py MS OUT SCANS FIELD_NAME OUT.json
Writes the new id of FIELD_NAME in OUT."""

import json
import sys
import time

from casatasks import split
from casatools import table


def main():
    ms, out, scans, name, report = sys.argv[1:6]
    t0 = time.perf_counter()
    split(vis=ms, outputvis=out, scan=scans, datacolumn="data", keepflags=True)
    tb = table()
    tb.open(out + "/FIELD")
    names = list(tb.getcol("NAME"))
    tb.close()
    tb.open(out)
    nrows = tb.nrows()
    tb.close()
    json.dump(
        {
            "scans": scans,
            "field": name,
            "field_id": names.index(name),
            "fields": names,
            "rows": nrows,
            "wall_s": time.perf_counter() - t0,
        },
        open(report, "w"),
        indent=1,
    )


if __name__ == "__main__":
    main()
