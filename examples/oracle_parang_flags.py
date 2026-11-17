"""Oracle side of task df-flag-rule (research/p-flag-spread.md), run with
CASA's Python in `rang-o-casa:6.7.6.14`:

    python oracle_parang_flags.py <run> <ms> <field> <parang 0|1> <interp;...> [<table> ...]

`applycal` with `applymode='calflag'`, `calwt=[False]`,
`gainfield='nearest'`, `flagbackup=False` and one `interp` per table
(separated by `;`); with no table, P alone (`parang=True`). Appends the call
and its wall time to `<run>/casa-apply.json`.
"""

import json
import sys
import time
from pathlib import Path


def main(argv):
    if len(argv) < 6:
        print(__doc__)
        return 2
    run, ms, field, parang = argv[1], argv[2], argv[3], bool(int(argv[4]))
    tables = argv[6:]
    interp = [m for m in argv[5].split(";") if m]
    if len(interp) != len(tables):
        raise SystemExit("give one interp per table")
    from casatasks import applycal

    start = time.perf_counter()
    applycal(
        vis=ms,
        field=field,
        applymode="calflag",
        gaintable=list(tables),
        interp=interp,
        calwt=[False] * max(1, len(tables)),
        gainfield=["nearest"] * len(tables),
        parang=parang,
        flagbackup=False,
    )
    wall = time.perf_counter() - start
    with open(Path(run) / "casa-apply.json", "a") as f:
        f.write(
            json.dumps(
                {
                    "ms": ms,
                    "tables": tables,
                    "interp": interp,
                    "parang": parang,
                    "wall_s": wall,
                }
            )
            + "\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
