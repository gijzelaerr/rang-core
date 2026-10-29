"""Numcodecs oracle for the Rang core blosc decoder (research/core-section6.md).

Run once in rang-flagging:local:
    python examples/oracle_luno_chunks.py <solve-inputs> <support-slice> <fresh-output-dir>

Decodes every chunk the section 6 prototype reads with numcodecs and writes
the SHA256 of the decoded bytes, the decoded length and the decode time per
chunk to receipt.json. Read only on the inputs.
"""

import json
import sys
import time
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path

import numcodecs

GROUP = "MAIN/MAIN_1"
TILES = range(8, 24)
ROW_COLUMNS = ("ANTENNA1", "ANTENNA2", "TIME", "FLAG_ROW")
TILE_COLUMNS = ("FLAG", "WEIGHT_SPECTRUM", "MODEL_DATA")


def chunks(solve_inputs, support):
    for column in ROW_COLUMNS:
        yield column, support / GROUP / column / "0"
    for column in TILE_COLUMNS:
        for t in TILES:
            yield f"{column}/0.{t}.0", support / GROUP / column / f"0.{t}.0"
    for t in TILES:
        yield f"DATA/0.{t}.0", solve_inputs / GROUP / "DATA" / f"0.{t}.0"


def main():
    solve_inputs, support, out = (Path(x) for x in sys.argv[1:4])
    out.mkdir(parents=True, exist_ok=False)
    records, total = {}, 0.0
    codec = numcodecs.Blosc()
    for key, path in chunks(solve_inputs, support):
        payload = path.read_bytes()
        started = time.perf_counter()
        raw = codec.decode(payload)
        seconds = time.perf_counter() - started
        total += seconds
        records[key] = {
            "path": str(path),
            "compressed_bytes": len(payload),
            "compressed_sha256": sha256(payload).hexdigest(),
            "decoded_bytes": len(raw),
            "decoded_sha256": sha256(raw).hexdigest(),
            "seconds": seconds,
        }
    receipt = {
        "chunks": records,
        "decode_seconds_total": total,
        "versions": {"numcodecs": version("numcodecs")},
        "blosc_version": numcodecs.blosc.VERSION_STRING,
    }
    (out / "receipt.json").write_text(json.dumps(receipt, indent=1) + "\n")
    print(
        json.dumps(
            {
                "chunks": len(records),
                "decode_seconds_total": total,
                "blosc": receipt["blosc_version"],
            }
        )
    )


if __name__ == "__main__":
    main()
