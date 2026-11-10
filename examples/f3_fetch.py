"""F3 Stage 1: fetch LUNO calibrator groups for training and validation
(research/f3-flagger.md, section 4): DATA and FLAG tiles 8-23 and the row
columns of MAIN_3 to MAIN_7, anonymous whole GETs, with a receipt.

Usage: python examples/f3_fetch.py OUT [--head-only]

OUT `RUN` means $RUN_DIR. Refuses any group outside `rang.f3flag.FETCH_GROUPS`
(MAIN_16-MAIN_19 are E2-B's and are never requested). Stops before any GET
if the HEAD total exceeds 5 GB.
"""

import argparse
import hashlib
import http.client
import json
import os
import ssl
import time
from pathlib import Path
from urllib.parse import urlsplit

from rang import f3flag as f3
from rang.core_fetch import Client

LIMIT = 5_000_000_000


def keys():
    out = []
    for g in f3.FETCH_GROUPS:
        f3.check_luno_group(g)
        for name in ("ANTENNA1", "ANTENNA2", "TIME", "FLAG_ROW"):
            out += [f"MAIN/{g}/{name}/.zarray", f"MAIN/{g}/{name}/0"]
        for name in ("DATA", "FLAG"):
            out.append(f"MAIN/{g}/{name}/.zarray")
            out += [f"MAIN/{g}/{name}/0.{t}.0" for t in f3.LUNO_TILES]
    return out


def head(key):
    parts = urlsplit(f3.LUNO_BUCKET)
    c = http.client.HTTPSConnection(
        parts.netloc, timeout=60, context=ssl.create_default_context()
    )
    c.request("HEAD", f"{parts.path.rstrip('/')}/{key}")
    r = c.getresponse()
    r.read()
    c.close()
    if r.status != 200:
        raise OSError(f"HEAD {key}: {r.status}")
    return int(r.getheader("Content-Length"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--head-only", action="store_true")
    args = parser.parse_args()
    out = Path(os.environ["RUN_DIR"]) if args.out == "RUN" else Path(args.out)
    ks = keys()
    sizes = {k: head(k) for k in ks}
    total = sum(sizes.values())
    print(json.dumps({"objects": len(ks), "bytes": total}), flush=True)
    (out / "head.json").parent.mkdir(parents=True, exist_ok=True)
    (out / "head.json").write_text(
        json.dumps({"total": total, "sizes": sizes}, indent=1)
    )
    if total > LIMIT:
        raise SystemExit(f"HEAD total {total} > {LIMIT}: ask the coordinator first")
    if args.head_only:
        return
    client = Client(f3.LUNO_BUCKET)
    lines, records = [], []
    started = time.time()
    for k in ks:
        rec, body = client.get(k)
        if len(body) != sizes[k]:
            raise OSError(f"{k}: {len(body)} bytes, HEAD said {sizes[k]}")
        path = out / "objects" / k
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == rec["sha256"]
        lines.append(f"{rec['bytes']} {rec['sha256']} {k}")
        records.append(
            {
                "key": k,
                "bytes": rec["bytes"],
                "sha256": rec["sha256"],
                "etag": rec["headers"].get("ETag"),
                "last_modified": rec["headers"].get("Last-Modified"),
            }
        )
    client.close()
    (out / "objects" / "receipt.txt").write_text("\n".join(lines) + "\n", newline="\n")
    (out / "result.json").write_text(
        json.dumps(
            {
                "base_url": f3.LUNO_BUCKET,
                "groups": list(f3.FETCH_GROUPS),
                "bytes": total,
                "seconds": time.time() - started,
                "objects": records,
            },
            indent=1,
        )
    )
    print(
        json.dumps(
            {
                "fetched": len(records),
                "bytes": total,
                "seconds": round(time.time() - started, 1),
            }
        )
    )


if __name__ == "__main__":
    main()
