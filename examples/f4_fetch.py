"""F4 Stage 1: fetch the held-out LUNO calibrator groups (research/f4-flagger.md,
section 4): DATA and FLAG tiles 8-23 and the row columns of MAIN_0, MAIN_12
and MAIN_14, row chunk 0, anonymous whole GETs, with a receipt. Nothing is
decoded: the groups stay unread until Stage 5.

Usage: python examples/f4_fetch.py OUT [--head-only]

OUT `RUN` means $RUN_DIR. Refuses any group outside `rang.f4flag.FETCH_GROUPS`
(MAIN_16-MAIN_19 are E2-B's and are never requested). If the HEAD total
exceeds 8 GB MAIN_14 is dropped (frozen); if it still does, stops before any GET.
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
from rang import f4flag as f4
from rang.core_fetch import Client

LIMIT = 8_000_000_000


def keys(groups):
    out = []
    for g in groups:
        f4.check_luno_group(g, heldout=True)
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
    groups = list(f4.FETCH_GROUPS)
    ks = keys(groups)
    sizes = {k: head(k) for k in ks}
    total = sum(sizes.values())
    if total > LIMIT:
        groups.remove("MAIN_14")
        ks = keys(groups)
        sizes = {k: sizes[k] for k in ks}
        total = sum(sizes.values())
    print(
        json.dumps({"objects": len(ks), "bytes": total, "groups": groups}), flush=True
    )
    (out / "head.json").parent.mkdir(parents=True, exist_ok=True)
    (out / "head.json").write_text(
        json.dumps({"total": total, "groups": groups, "sizes": sizes}, indent=1)
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
                "groups": groups,
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
