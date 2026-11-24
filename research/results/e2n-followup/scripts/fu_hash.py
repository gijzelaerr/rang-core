"""FLAG and FLAG_ROW SHA-256 of an MS (e2_post.flag_hash) against E2-N's 9.1 hashes.

python fu_hash.py MS INPUT.json OUT.json      exit 0 if equal
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "e2-acceptance-scripts"))

import e2_post as P

ms, want, out = sys.argv[1:4]
got = P.flag_hash(Path(ms))
want = json.loads(Path(want).read_text())
ok = all(got[k] == want[k] for k in ("rows", "flag_sha256", "flag_row_sha256"))
mtimes = {p.name: p.stat().st_mtime for p in sorted(Path(ms).glob("table.f*"))}
P.write(
    Path(out), {"ms": ms, "hash": got, "input": want, "equal": ok, "mtimes": mtimes}
)
sys.exit(0 if ok else 1)
