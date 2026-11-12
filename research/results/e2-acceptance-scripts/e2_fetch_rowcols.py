"""Row columns and group attributes only of one MAIN group (a preflight, no cube
column): python e2_fetch_rowcols.py STORE GROUP OUT. research/e2-acceptance.md."""

import hashlib
import json
import sys
from pathlib import Path

import e2_fetch as f

store, group, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
keys, _ = f.listing(f"{store}/MAIN/{group}/")
cubes = f.CUBES | f.SKIP
want = [
    (k, s)
    for k, s in keys
    if not k.endswith("/")
    and k[len(f"{store}/MAIN/{group}/") :].split("/")[0] not in cubes
]
man = {}
for k, s in want:
    b = f.Getter().get(k)
    p = out / k
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b)
    man[k] = {"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
(out / "manifest.json").write_text(json.dumps(man, indent=0))
print(len(man), sum(v["bytes"] for v in man.values()))
