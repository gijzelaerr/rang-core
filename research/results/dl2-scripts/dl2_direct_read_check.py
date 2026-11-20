"""One-off check (research/dl2-data.md amendment 6): AOFlagger 2.13.0 with -direct-read
against its default read on the same scan.

    python dl2_direct_read_check.py ROOT CBID SCAN

Makes a private copy of the frozen scan under ROOT/work/direct-read-check/, runs
AOFlagger with -direct-read forced, extracts FLAG as dl2_teach does, and prints its
flag.npy SHA-256 beside the existing label's. Writes nothing under labels/ or done/.
"""

import json
import shutil
import sys
from pathlib import Path

import dl2_teach as T


def main():
    root, cbid, scan = Path(sys.argv[1]).resolve(), sys.argv[2], int(sys.argv[3])
    block = json.loads((root / "manifests" / f"{cbid}.json").read_text())
    s = next(x for x in block["scans"] if x["scan"] == scan)
    ms = root / "ms" / cbid / s["ms"]
    work = root / "work" / "direct-read-check"
    wc = work / "copy" / s["ms"]
    T.private_copy(ms, wc)
    T.DIRECT_READ_BYTES = 0
    rfis = root / T.RFIS
    rc, wall, rss = T.teach("aoflagger", rfis, wc, work, 4, work / "aoflagger.log")
    out = work / "out"
    out.mkdir(exist_ok=True)
    shape = T.extract(wc, out)
    new = T.sha256_file(out / "flag.npy")
    old = T.sha256_file(
        root / "labels" / "aoflagger" / cbid / f"scan{scan:03d}" / "flag.npy"
    )
    print(json.dumps({"rc": rc, "wall_s": round(wall, 1), "peak_rss_kb": rss,
                      "direct_sha256": new, "auto_sha256": old, "identical": new == old,
                      **shape}))  # fmt: skip
    shutil.rmtree(wc)


if __name__ == "__main__":
    main()
