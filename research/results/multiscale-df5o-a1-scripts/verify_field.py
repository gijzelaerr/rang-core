"""Check a copy of DF5-O's field against the hashes in its field.json.

    python verify_field.py FIELD_DIR OUT.json

Exit 1 on any mismatch (issue #23, research/multiscale-df5o-a1.md section 2).
"""

import hashlib
import json
import sys
from pathlib import Path


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def main():
    field_dir, out = Path(sys.argv[1]), Path(sys.argv[2])
    rec = json.loads((field_dir / "field.json").read_text())["hashes"]
    ms = field_dir / "field.ms"
    files = sorted(p for p in ms.rglob("*") if p.is_file())
    rows = {p.relative_to(ms).as_posix(): sha256_file(p) for p in files}
    listing = "".join(f"{k} {v}\n" for k, v in rows.items())
    digest = hashlib.sha256(listing.encode()).hexdigest()
    other = {name: sha256_file(field_dir / name) for name in rec["files"]}
    bad = sorted(
        k
        for k in set(rows) | set(rec["ms_files"])
        if rows.get(k) != rec["ms_files"].get(k)
    )
    bad += sorted(k for k in other if other[k] != rec["files"][k])
    result = {
        "ms_digest": digest,
        "ms_digest_expected": rec["ms_digest"],
        "ms_files": len(rows),
        "mismatches": bad,
        "ok": digest == rec["ms_digest"] and not bad,
    }
    out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
