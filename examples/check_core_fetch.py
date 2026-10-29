"""Check a range-request fetch against the archived whole tiles.

Usage: python examples/check_core_fetch.py outputs/core-g-<date>-NN outputs/core-g-check-<date>-NN

Criteria 1-5 of research/core-g-http-fetch.md: response statuses and
Content-Range, byte equality of every span with the archived tile, array
equality after decoding, bytes transferred and wall time against the
archived whole-tile fetch. Writes result.json into the check directory.
"""

import json
import sys
import time
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path

import numpy as np
from rangtoy import core, core_fetch, core_zarr

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / "outputs/luno-support-20261029-01/slice"
SOLVE = ROOT / "outputs/luno-solve-20261029-02/inputs"
SECTION6_RECEIPT = ROOT / "outputs/core-section6-20261029-02/receipt.json"
ARCHIVE_OF = {"DATA": SOLVE}
WHOLE_TILE_BYTES = 4_869_187_244
WHOLE_TILE_SECONDS = 461.0 + 325.7 * 2_151_792_632 / 3_222_232_014
ALL_FETCHES_SECONDS = 325.7 + 432.4 + 461.0
BYTES_LIMIT = 760_000_000
REQUESTS_LIMIT = 2200


def archived(key):
    name = key.split("/")[2]
    return ARCHIVE_OF.get(name, SUPPORT) / key


def archived_receipt_hashes():
    hashes = {}
    for receipt in (SUPPORT / "receipt.txt", SOLVE / "receipt.txt"):
        for line in receipt.read_text().splitlines():
            size, digest, key = line.split()
            hashes[key] = (int(size), digest)
    return hashes


def main():
    fetched, check = Path(sys.argv[1]), Path(sys.argv[2])
    check.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    result = json.loads((fetched / "result.json").read_text())
    receipt = json.loads((fetched / "receipt.json").read_text())
    group = result["group"]
    hashes = archived_receipt_hashes()
    section6 = json.loads(SECTION6_RECEIPT.read_text())["input_chunk_sha256"]
    criteria = {}

    # 1. Statuses and Content-Range against the archived object sizes.
    bad = []
    for r in receipt:
        size = archived(r["key"]).stat().st_size
        if r["range"] is None:
            if r["status"] != 200 or r["bytes"] != size:
                bad.append(r["key"])
        else:
            start, end = r["range"]
            expected = f"bytes {start}-{end - 1}/{size}"
            if r["status"] != 206 or r["headers"].get("Content-Range") != expected:
                bad.append([r["key"], r["range"], r["headers"].get("Content-Range")])
    criteria["1_range_support"] = {
        "pass": not bad,
        "failures": bad[:10],
        "count": len(bad),
    }

    # 2. Byte equality of every span and whole object with the archive.
    bad = []
    handles = {}
    with ExitStack() as stack:
        for r in receipt:
            path = archived(r["key"])
            if r["range"] is None:
                body = path.read_bytes()
                expected = sha256(body).hexdigest()
                line = hashes.get(r["key"])
                ok = r["sha256"] == expected and (line is None or line[1] == expected)
                short = r["key"].removeprefix(group + "/")
                if short in section6:
                    ok = ok and section6[short] == r["sha256"]
            else:
                start, end = r["range"]
                if r["key"] not in handles:
                    handles[r["key"]] = stack.enter_context(open(path, "rb"))
                handle = handles[r["key"]]
                handle.seek(start)
                ok = r["sha256"] == sha256(handle.read(end - start)).hexdigest()
            if not ok:
                bad.append([r["key"], r["range"]])
    # The files on disk hash to what the receipt says.
    disk_bad = []
    for r in receipt:
        if r["range"] is None:
            path = fetched / "objects" / r["key"]
        else:
            plan = result["plans"].get(r["key"])
            name = "head"
            if plan is not None and r["range"][0] != 0:
                for first, count, start, end in plan["runs"]:
                    if [start, end] == r["range"]:
                        name = f"{first}-{count}"
            path = fetched / "spans" / r["key"] / name
        if sha256(path.read_bytes()).hexdigest() != r["sha256"]:
            disk_bad.append(str(path))
    criteria["2_byte_equality"] = {
        "pass": not bad and not disk_bad,
        "failures": bad[:10],
        "count": len(bad),
        "disk_failures": disk_bad[:10],
        "spans_checked": len(receipt),
    }

    # 3. Decoded arrays equal read_rows on the archived tiles.
    arrays, stats = core_fetch.decode_slice(fetched)
    rows = np.asarray(result["rows"])
    row_ok = {}
    for name, dtype in result["row_columns"]:
        payload = (SUPPORT / group / name / "0").read_bytes()
        values = np.frombuffer(core.blosc_decode(payload), dtype)[rows]
        row_ok[name] = bool(np.array_equal(arrays[name], values))
    archive_rows = core_fetch.kept_rows(
        {
            name: np.frombuffer(
                core.blosc_decode((SUPPORT / group / name / "0").read_bytes()), dtype
            )
            for name, dtype in result["row_columns"]
        },
        result["stations"],
    )
    row_ok["rows"] = bool(np.array_equal(archive_rows, rows))
    tile_ok = {}
    for name in result["tile_columns"]:
        root = ARCHIVE_OF.get(name, SUPPORT) / group / name
        meta = core_zarr.array_meta(root)
        nchan, ncorr = meta["chunks"][1], meta["chunks"][2]
        row_bytes = nchan * ncorr * np.dtype(meta["dtype"]).itemsize
        parts = []
        for tile in result["tiles"]:
            raw, _ = core_zarr.read_rows(root / f"0.{tile}.0", row_bytes, rows)
            parts.append(
                np.frombuffer(raw, meta["dtype"]).reshape(len(rows), nchan, ncorr)
            )
        expected = np.concatenate(parts, axis=1)
        tile_ok[name] = bool(
            arrays[name].shape == expected.shape
            and np.array_equal(arrays[name].view(np.uint8), expected.view(np.uint8))
        )
    criteria["3_array_equality"] = {
        "pass": all(row_ok.values()) and all(tile_ok.values()),
        "rows": row_ok,
        "tiles": tile_ok,
        "shapes": {k: list(v.shape) for k, v in arrays.items()},
        "blocks_decoded": stats["blocks_decoded"],
    }

    # 4 and 5. Cost against the archived whole-tile fetch.
    criteria["4_bytes"] = {
        "pass": result["bytes"] <= BYTES_LIMIT and result["requests"] <= REQUESTS_LIMIT,
        "bytes": result["bytes"],
        "requests": result["requests"],
        "attempts": result["attempts"],
        "whole_tile_bytes": WHOLE_TILE_BYTES,
        "fraction": result["bytes"] / WHOLE_TILE_BYTES,
    }
    criteria["5_seconds"] = {
        "pass": result["seconds"] < WHOLE_TILE_SECONDS,
        "seconds": result["seconds"],
        "whole_tile_seconds": WHOLE_TILE_SECONDS,
        "all_three_fetches_seconds": ALL_FETCHES_SECONDS,
        "mb_per_second": result["bytes"] / result["seconds"] / 1e6,
        "requests_per_second": result["requests"] / result["seconds"],
        "decode_seconds": stats["decode_seconds"],
    }
    summary = {
        "fetched": str(fetched),
        "all_pass": all(c["pass"] for c in criteria.values()),
        "criteria": criteria,
        "check_seconds": time.perf_counter() - started,
    }
    (check / "result.json").write_text(json.dumps(summary, indent=1) + "\n")
    for name, c in criteria.items():
        print(f"{name}: {'PASS' if c['pass'] else 'FAIL'}")
    print("all pass" if summary["all_pass"] else "FAILED")


if __name__ == "__main__":
    main()
