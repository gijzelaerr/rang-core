"""Oracle side of task C4a (research/c4a-apply.md), run with CASA's Python
in `rang-o-casa:6.7.6.14`:

    python oracle_apply.py <run> <ms> <interp;interp;...> <table> ...
    python oracle_apply.py edit-flags <ms> <field_id> <a1,a2,c0,c1,corr;...>

The first form runs `applycal` on `<ms>` with DF-IO's `casa-apply` settings
(`applymode='calflag'`, `calwt=[False]`, `gainfield='nearest'`,
`parang=False`, `flagbackup=False`, field J1939-6342) and one `interp`
string per table, separated by `;` (CASA's own `'<time>,<freq>'` strings
contain commas), and appends the call and its wall time to
`<run>/casa-apply.json`. The second (held-out set, section 5) rewrites
FLAG of the field's rows of baseline `a1`-`a2` in channels `c0` to `c1 - 1`
so that only correlation `corr` is flagged there, with casatools.
"""

import json
import sys
import time
from pathlib import Path

FIELD = "J1939-6342"


def edit_flags(ms, field_id, spec):
    from casatools import table

    tb = table()
    tb.open(ms, nomodify=False)
    flag = tb.getcol("FLAG")  # (corr, chan, row)
    a1, a2 = tb.getcol("ANTENNA1"), tb.getcol("ANTENNA2")
    field = tb.getcol("FIELD_ID")
    for item in spec.split(";"):
        p, q, c0, c1, corr = (int(x) for x in item.split(","))
        rows = (field == int(field_id)) & (a1 == p) & (a2 == q)
        flag[:, c0:c1, rows] = False
        flag[corr, c0:c1, rows] = True
    tb.putcol("FLAG", flag)
    tb.close()


def main(argv):
    if len(argv) == 5 and argv[1] == "edit-flags":
        edit_flags(argv[2], argv[3], argv[4])
        return 0
    if len(argv) < 5:
        print(__doc__)
        return 2
    run, ms, interp, tables = argv[1], argv[2], argv[3].split(";"), argv[4:]
    if len(interp) != len(tables):
        raise SystemExit("give one interp per table")
    from casatasks import applycal

    start = time.perf_counter()
    applycal(
        vis=ms,
        field=FIELD,
        applymode="calflag",
        gaintable=list(tables),
        interp=interp,
        calwt=[False],
        gainfield=["nearest"] * len(tables),
        parang=False,
        flagbackup=False,
    )
    wall = time.perf_counter() - start
    with open(Path(run) / "casa-apply.json", "a") as f:
        f.write(
            json.dumps({"ms": ms, "tables": tables, "interp": interp, "wall_s": wall})
            + "\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
