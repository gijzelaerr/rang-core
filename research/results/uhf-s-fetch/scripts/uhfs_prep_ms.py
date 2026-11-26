# SPDX-License-Identifier: MIT
"""uhf-s-fetch: E2-N's steps right after conversion, unchanged (copy of
research/results/e2n-scripts/e2n_prep_ms.py; research/e2n-native.md section 4 and
amendment 1), python-casacore, no visibility read:

    python e2n_prep_ms.py MS OUT_DIR

1. token check: no `token=` in any subtable's string cells or any table or
   column keyword, nor in the conversion log beside the MS;
2. SIGMA_SPECTRUM removed (amendment 1), its storage files with it;
3. the MS map: per SCAN_NUMBER, its FIELD name, rows, first and last TIME,
   and the field list; FEED RECEPTOR_ANGLE; the main table's columns;
4. gate 2a's reference: SHA-256 of FLAG (bool bytes, row-major) and
   FLAG_ROW in blocks of 4,000 rows, as e2_flaghash.py and e2_post.flag_hash.
Writes OUT_DIR/ms-map.json and OUT_DIR/flaghash-input.json.
"""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from casacore.tables import table

BLOCK = 4000


def has_token(value):
    return "token=" in str(value)


def token_check(ms):
    hits = []
    t = table(ms, ack=False)
    if has_token(t.getkeywords()):
        hits.append("main keywords")
    for c in t.colnames():
        if has_token(t.getcolkeywords(c)):
            hits.append(f"main {c} keywords")
    subs = [Path(p).name for p in t.getkeywords().values() if isinstance(p, str)]
    t.close()
    for name in subs:
        s = table(f"{ms}/{name}", ack=False)
        if has_token(s.getkeywords()):
            hits.append(f"{name} keywords")
        for c in s.colnames():
            if has_token(s.getcolkeywords(c)):
                hits.append(f"{name} {c} keywords")
            if (s.nrows() and s.coldatatype(c) == "string"
                    and any(has_token(v) for v in s.getcol(c))):  # fmt: skip
                hits.append(f"{name} {c}")
        s.close()
    log = Path(str(ms)[: -len(".ms")] + "-mvftoms.log")
    if log.is_file() and "token=" in log.read_text(errors="replace"):
        hits.append(log.name)
    return {"subtables": subs, "hits": hits}


def main(ms, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    rec = {"ms": ms, "token_check": token_check(ms)}
    if rec["token_check"]["hits"]:
        raise SystemExit(f"token found: {rec['token_check']['hits']}")
    t = table(ms, readonly=False, ack=False)
    rec["columns_before"] = t.colnames()
    if "SIGMA_SPECTRUM" in t.colnames():
        t.removecols(["SIGMA_SPECTRUM"])
    rec["columns"] = t.colnames()
    t.close()
    t = table(ms, ack=False)
    fields = list(table(f"{ms}/FIELD", ack=False).getcol("NAME"))
    scan = t.getcol("SCAN_NUMBER")
    fid = t.getcol("FIELD_ID")
    tm = t.getcol("TIME")
    rec["fields"] = fields
    rec["rows"] = int(t.nrows())
    rec["scans"] = []
    for s in sorted(set(scan.tolist())):
        m = scan == s
        f = sorted(set(fid[m].tolist()))
        rec["scans"].append({"scan": int(s), "field": [fields[i] for i in f], "rows": int(m.sum()),
                             "dumps": len(set(tm[m].tolist())),
                             "time_first": float(tm[m].min()), "time_last": float(tm[m].max())})  # fmt: skip
    rec["receptor_angle"] = (
        table(f"{ms}/FEED", ack=False).getcol("RECEPTOR_ANGLE").tolist()[:2]
    )
    rec["chan_freq_first_last"] = [
        float(x)
        for x in table(f"{ms}/SPECTRAL_WINDOW", ack=False).getcol("CHAN_FREQ")[0][
            [0, -1]
        ]
    ]
    hf, hr = hashlib.sha256(), hashlib.sha256()
    n = t.nrows()
    shape = None
    for r0 in range(0, n, BLOCK):
        k = min(BLOCK, n - r0)
        f = np.ascontiguousarray(np.asarray(t.getcol("FLAG", r0, k), dtype=bool))
        shape = f.shape[1:]
        hf.update(f.tobytes())
        hr.update(
            np.ascontiguousarray(
                np.asarray(t.getcol("FLAG_ROW", r0, k), dtype=bool)
            ).tobytes()
        )
    t.close()
    fh = {"ms": ms, "rows": int(n), "cell_shape": [int(x) for x in shape],
          "flag_sha256": hf.hexdigest(), "flag_row_sha256": hr.hexdigest()}  # fmt: skip
    rec["seconds"] = time.perf_counter() - t0
    (out / "ms-map.json").write_text(json.dumps(rec, indent=1) + "\n")
    (out / "flaghash-input.json").write_text(json.dumps(fh, indent=1) + "\n")
    print(json.dumps({k: v for k, v in rec.items() if k != "scans"}, indent=1))
    for s in rec["scans"]:
        print(s)
    print(json.dumps(fh))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
