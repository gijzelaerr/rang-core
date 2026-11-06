"""Oracle side of task C4b (research/c4b-apply-ms.md), run with CASA's Python
in `rang-o-casa:6.7.6.14`:

    python oracle_apply_ms.py prepare <ms> <field_ids> <weights 0|1> <flagrow 0|1> <seed>
    python oracle_apply_ms.py apply <case.json>
    python oracle_apply_ms.py export <ms> <out.npz> [<hashes.json>]

`prepare` edits a copy in place with casatools: SIGMA, SIGMA_SPECTRUM (when
present), WEIGHT and WEIGHT_SPECTRUM set to independent uniform values in
[0.5, 2) (seeded), and/or FLAG_ROW set on 5 % of the rows of the given
fields (FLAG left as it is). `apply` runs `applycal` with the case's
arguments (`parang=False`, `flagbackup=False`). `export` writes the
compared columns of an MS as (row, chan, corr) arrays read with casatools
(casacore 3.7.1), and the SHA-256 of every column's values.
"""

import hashlib
import json
import sys
import time

import numpy as np

COMPARED = (
    "CORRECTED_DATA",
    "FLAG",
    "FLAG_ROW",
    "WEIGHT",
    "WEIGHT_SPECTRUM",
    "SIGMA",
    "SIGMA_SPECTRUM",
    "FIELD_ID",
    "DATA",
)


def _rows_first(a):
    a = np.asarray(a)
    return np.ascontiguousarray(a.T) if a.ndim > 1 else a


def prepare(ms, field_ids, weights, flagrow, seed):
    from casatools import table

    rng = np.random.default_rng(int(seed))
    tb = table()
    tb.open(ms, nomodify=False)
    names = tb.colnames()
    if int(weights):
        for name in ("SIGMA", "SIGMA_SPECTRUM", "WEIGHT", "WEIGHT_SPECTRUM"):
            if name not in names:
                continue
            shape = tb.getcol(name).shape
            tb.putcol(name, rng.uniform(0.5, 2.0, shape).astype(np.float32))
    if int(flagrow):
        fields = [int(f) for f in str(field_ids).split(",")]
        fid = tb.getcol("FIELD_ID")
        rows = np.flatnonzero(np.isin(fid, fields))
        pick = rng.choice(rows, max(1, len(rows) // 20), replace=False)
        fr = tb.getcol("FLAG_ROW")
        fr[pick] = True
        tb.putcol("FLAG_ROW", fr)
    tb.close()


def apply(case_json):
    from casatasks import applycal

    with open(case_json) as f:
        case = json.load(f)
    start = time.perf_counter()
    applycal(
        vis=case["ms"],
        field=case["field"],
        gaintable=case["gaintable"],
        interp=case["interp"],
        gainfield=case["gainfield"],
        calwt=case["calwt"],
        applymode=case.get("applymode", "calflag"),
        parang=False,
        flagbackup=False,
    )
    case["wall_s"] = time.perf_counter() - start
    with open(case_json + ".done", "w") as f:
        json.dump(case, f)


def export(ms, out, hashes=None):
    from casatools import table

    tb = table()
    tb.open(ms)
    names = tb.colnames()
    arrays = {}
    for name in COMPARED:
        if name in names:
            arrays[name] = _rows_first(tb.getcol(name))
    np.savez(out, **arrays)
    if hashes:
        digest = {}
        for name in names:
            try:
                values = tb.getcol(name)
            except RuntimeError:
                continue  # an undefined column (FLAG_CATEGORY)
            digest[name] = hashlib.sha256(
                np.ascontiguousarray(values).tobytes()
            ).hexdigest()
        with open(hashes, "w") as f:
            json.dump(digest, f, indent=1, sort_keys=True)
    tb.close()


def main(argv):
    if len(argv) >= 7 and argv[1] == "prepare":
        prepare(*argv[2:7])
        return 0
    if len(argv) == 3 and argv[1] == "apply":
        apply(argv[2])
        return 0
    if len(argv) in (4, 5) and argv[1] == "export":
        export(*argv[2:])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
