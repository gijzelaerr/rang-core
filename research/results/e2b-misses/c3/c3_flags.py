"""e2b-misses 9.28 (input reconstruction, read-only): can the deleted E2-B
flag states be rebuilt from what is left, hash for hash?

    python c3_flags.py check OUT_JSON
    python c3_flags.py write OUT_NPY      packed rang FLAG after apply (n, 4096, 1) uint8

Reads `R/df-flag-snapshot/flags-after-applycal.npz` (FLAG = CASA's applycal
output and RANG_FLAG = rang's after apply, packed over 4 correlations, MSB
first) and `e3-20261111-input/e2b.ms` (DATA never written; FLAG_ROW, row
columns), both read-only. Compares against the archived hashes:
- `a5-mask/receipts/slim.json` sha256 FLAG: rang's FLAG after apply;
- `c2b/hash_src.json`: DATA, and (FLAG, FLAG_ROW) of the after-calibrate
  version `flags.rang_apply_20261112T013707Z`, interleaved per 500 rows.
"""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

R = Path("D:/rang/outputs/e2-20261111-20-e2b")
NPZ = R / "df-flag-snapshot" / "flags-after-applycal.npz"
E3 = Path("D:/rang/outputs/e3-20261111-input/e2b.ms")
HERE = Path(__file__).resolve().parent
SLIM = json.loads((HERE.parent / "a5-mask" / "receipts" / "slim.json").read_text())
SRC = json.loads((HERE.parent / "c2b" / "hash_src.json").read_text())
B = 500


def unpack(p):
    return np.unpackbits(p, axis=-1, count=4).astype(bool)


def check(out):
    from rang import core_ms

    t0 = time.time()
    z = np.load(NPZ)
    rec = {"npz_keys": sorted(z.files)}
    rf, cf = z["RANG_FLAG"], z["FLAG"]
    rec["shape_packed"] = list(rf.shape)
    n = rf.shape[0]
    h_rang, h_casa = hashlib.sha256(), hashlib.sha256()
    h_v_all, h_v_e3, h_data = hashlib.sha256(), hashlib.sha256(), hashlib.sha256()
    casa_ne_rang = 0
    with core_ms.open_table(E3) as t:
        rec["e3_rows"] = t.nrows
        rec["e3_columns"] = sorted(t.colnames())
        for c in ("ANTENNA1", "ANTENNA2", "FIELD_ID", "SCAN_NUMBER", "TIME"):
            rec[f"rows_equal_{c}"] = bool(np.array_equal(t.getcol(c), z[c]))
        e3_fr = t.getcol("FLAG_ROW")
        for r0 in range(0, n, B):
            k = min(B, n - r0)
            f = unpack(rf[r0 : r0 + k])
            g = unpack(cf[r0 : r0 + k])
            casa_ne_rang += int((f != g).sum())
            h_rang.update(np.ascontiguousarray(f).tobytes())
            h_casa.update(np.ascontiguousarray(g).tobytes())
            fr_all = f.reshape(k, -1).all(-1)
            h_v_all.update(np.ascontiguousarray(f).tobytes())
            h_v_all.update(np.ascontiguousarray(fr_all).tobytes())
            h_v_e3.update(np.ascontiguousarray(f).tobytes())
            h_v_e3.update(np.ascontiguousarray(e3_fr[r0 : r0 + k]).tobytes())
            h_data.update(np.ascontiguousarray(t.getcol("DATA", r0, k)).tobytes())
    rec.update(
        rows=n,
        casa_flag_elements_ne_rang=casa_ne_rang,
        rang_flag_sha256=h_rang.hexdigest(),
        rang_flag_eq_slim=h_rang.hexdigest() == SLIM["sha256"]["FLAG"],
        casa_flag_eq_slim=h_casa.hexdigest() == SLIM["sha256"]["FLAG"],
        version_hash_flagrow_all=h_v_all.hexdigest(),
        version_hash_flagrow_e3=h_v_e3.hexdigest(),
        version_eq_flagrow_all=h_v_all.hexdigest() == SRC["flag_sha256"],
        version_eq_flagrow_e3=h_v_e3.hexdigest() == SRC["flag_sha256"],
        e3_data_sha256=h_data.hexdigest(),
        e3_data_eq_src=h_data.hexdigest() == SRC["data_sha256"],
        secs=time.time() - t0,
    )
    Path(out).write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec, indent=1))


def write(out):
    np.save(out, np.load(NPZ)["RANG_FLAG"])


if __name__ == "__main__":
    {"check": check, "write": write}[sys.argv[1]](sys.argv[2])
