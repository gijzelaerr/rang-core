"""Fetch the section 6 four-station LUNO slice with HTTP range requests.

Usage: python examples/fetch_luno_slice.py outputs/core-g-<date>-NN [--workers 8]

research/core-g-http-fetch.md. One measured run against the public RATT
bucket; check it afterwards with examples/check_core_fetch.py.
"""

import argparse
import json
import resource
import sys
import time
from pathlib import Path

from rang import core_fetch

BUCKET = (
    "https://ratt-public-data.s3.af-south-1.amazonaws.com/LBAND_LUNO_CALIBRATORS.zarr"
)
GROUP = "MAIN/MAIN_1"
STATIONS = (0, 1, 2, 3)
TILES = range(8, 24)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    out = Path(args.out)
    if not str(out).startswith("outputs/") or out.exists():
        sys.exit("the output directory must be a fresh path beneath outputs/")
    started = time.perf_counter()
    result = core_fetch.fetch_slice(
        BUCKET, GROUP, STATIONS, TILES, out, workers=args.workers
    )
    decode_started = time.perf_counter()
    arrays, stats = core_fetch.decode_slice(out)
    stats["decode_wall_seconds"] = time.perf_counter() - decode_started
    stats["process_seconds"] = time.perf_counter() - started
    stats["peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    stats["shapes"] = {k: list(v.shape) for k, v in arrays.items()}
    result["decode"] = stats
    (out / "result.json").write_text(json.dumps(result, indent=1) + "\n")
    print(
        f"{result['requests']} requests ({result['attempts']} attempts), "
        f"{result['bytes']:,} bytes in {result['seconds']:.1f} s "
        f"({result['bytes'] / result['seconds'] / 1e6:.2f} MB/s); "
        f"decode {stats['decode_seconds']:.2f} s, {stats['blocks_decoded']} blocks"
    )


if __name__ == "__main__":
    main()
