"""Read a MeerKAT MVFv4 dataset into core-layout row chunks (task MK1).

    python examples/fetch_meerkat_mvf.py OUT SOURCE [selection options]

SOURCE is an archive RDB URL (`https://…/<cbid>_sdp_l0.full.rdb?token=…`)
or a local `.rdb` next to its `.npy` chunk store. Each chunk lands in
`OUT/chunk-NNNNN/<KEY>.npy` with the keys of `rang.meerkat` (ANTENNA1/2,
TIME, FLAG_ROW, UVW, DATA, FLAG, WEIGHT_SPECTRUM, FLAG_BITS, SCAN_NUMBER,
FIELD_ID) and `OUT/manifest.json`; `OUT/receipt.json` records the timing,
peak RSS and versions. A token in the URL is never written to disk: the
recorded source has its query string removed.

`--native-flags` keeps katdal's L0 ingest flag bits (no `sdp_l1_flags`
upgrade) and makes FLAG from the observatory bits only (static, cam,
data_lost, ingest_rfi, predicted_rfi); FLAG_BITS always holds every bit.
Protocol and conventions: research/mk1-katdal.md.
"""

import argparse
import json
import platform
import sys
import time
from pathlib import Path

from rang import meerkat, rusage


def _channels(text):
    if text is None:
        return None
    start, stop = (int(x) if x else None for x in text.split(":"))
    return slice(start, stop)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path, help="fresh output directory")
    parser.add_argument("source", help="RDB URL or local .rdb")
    parser.add_argument("--scans", type=int, nargs="*", default=None)
    parser.add_argument("--targets", nargs="*", default=None)
    parser.add_argument("--antennas", nargs="*", default=None)
    parser.add_argument("--channels", default=None, help="start:stop")
    parser.add_argument("--autos", action="store_true")
    parser.add_argument("--native-flags", action="store_true")
    parser.add_argument("--dumps", type=int, default=None, help="dumps per chunk")
    parser.add_argument("--ref-ant", default="")
    args = parser.parse_args(argv)
    if args.out.exists():
        raise SystemExit(f"{args.out} exists; use a fresh output directory")
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    started = time.perf_counter()
    loader = meerkat.open_mvf(
        args.source, ref_ant=args.ref_ant, upgrade_flags=not args.native_flags
    )
    loader.select(
        scans=args.scans,
        targets=args.targets,
        antennas=args.antennas,
        channels=_channels(args.channels),
        autos=args.autos,
        flags=list(meerkat.NATIVE_FLAGS) if args.native_flags else "all",
    )
    manifest = loader.save_chunks(args.out, dumps=args.dumps)
    chunks = manifest["chunks"]
    receipt = {
        "task": "MK1",
        "source": loader.source,
        "started_utc": started_utc,
        "open_seconds": loader.open_seconds,
        "seconds": time.perf_counter() - started,
        "chunks": len(chunks),
        "rows": sum(c["rows"] for c in chunks),
        "bytes_in": sum(c["bytes_in"] for c in chunks),
        "katdal_read_seconds": sum(c["read_seconds"] for c in chunks),
        "peak_rss_bytes": rusage.peak_rss_bytes(),
        "native_flags": args.native_flags,
        "selection": manifest["metadata"]["selection"],
        "python": platform.python_version(),
        "katdal": manifest["metadata"]["katdal"],
        "katsdptelstate": manifest["metadata"]["katsdptelstate"],
    }
    (args.out / "receipt.json").write_text(json.dumps(receipt, indent=1) + "\n")
    print(json.dumps({k: receipt[k] for k in ("chunks", "rows", "seconds")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
