"""F5 Amendment 3: fetch the reserved LUNO calibrator groups for the post hoc
calibrator arm N5-ph (research/f5-flagger.md): DATA and FLAG tiles 8-23 and the
row columns of MAIN_8, 9, 10, 11, 13 and 15, row chunk 0, anonymous whole GETs
from the public bucket, with a receipt. Nothing is decoded: the groups stay
unread until N5-ph is scored. Resumable: an object already on disk with the
size HEAD reports is kept (its sha256 goes in the receipt).

Usage: python examples/f5_fetch.py OUT [--head-only]
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

from rang import f3flag as f3
from rang import f5flag as f5
from rang.core_fetch import Client

HERE = Path(__file__).resolve().parent
import importlib.util

spec = importlib.util.spec_from_file_location("f4_fetch", HERE / "f4_fetch.py")
f4f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f4f)


def keys(groups):
    out = []
    for g in groups:
        if g not in f5.RESERVED_GROUPS:
            raise SystemExit(f"{g} is not one of F5's reserved groups")
        for name in ("ANTENNA1", "ANTENNA2", "TIME", "FLAG_ROW"):
            out += [f"MAIN/{g}/{name}/.zarray", f"MAIN/{g}/{name}/0"]
        for name in ("DATA", "FLAG"):
            out.append(f"MAIN/{g}/{name}/.zarray")
            out += [f"MAIN/{g}/{name}/0.{t}.0" for t in f3.LUNO_TILES]
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--head-only", action="store_true")
    a = p.parse_args()
    groups = list(f5.RESERVED_GROUPS)
    ks = keys(groups)
    sizes = {k: f4f.head(k) for k in ks}
    total = sum(sizes.values())
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "head.json").write_text(
        json.dumps({"total": total, "groups": groups, "sizes": sizes}, indent=1)
    )
    print(
        json.dumps({"objects": len(ks), "bytes": total, "groups": groups}), flush=True
    )
    if a.head_only:
        return
    client = Client(f3.LUNO_BUCKET)
    lines, started = [], time.time()
    for k in ks:
        path = a.out / "objects" / k
        if path.exists() and path.stat().st_size == sizes[k]:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            rec, body = client.get(k)
            if len(body) != sizes[k]:
                raise OSError(f"{k}: {len(body)} bytes, HEAD said {sizes[k]}")
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".part")
            tmp.write_bytes(body)
            tmp.replace(path)
            digest = rec["sha256"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        lines.append(f"{sizes[k]} {digest} {k}")
    client.close()
    (a.out / "objects" / "receipt.txt").write_text(
        "\n".join(lines) + "\n", newline="\n"
    )
    rec = {
        "base_url": f3.LUNO_BUCKET,
        "groups": groups,
        "bytes": total,
        "seconds": time.time() - started,
    }
    (a.out / "result.json").write_text(json.dumps(rec, indent=1))
    print(json.dumps(rec))


if __name__ == "__main__":
    main()
