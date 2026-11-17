"""Validation of `calibrate.average_freq` (research/e2-average-freq.md 2): the
LUNO configuration of e2avg_luno.py (calibrate only, `average_time: true`)
plus `average_freq: true`, on a copy of the same converted development MS
(LUNO scans 1-2), scored by e2avg_luno.py's class-B scorer against the CASA
tables of that run (D:\\rang\\outputs\\e2-20261110-11-avg\\casa).

    python e2fa_luno.py RUN      (under tools/heavy_lock.py)
"""

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AVG = HERE.parent / "e2-average-time"
sys.path.insert(0, str(AVG))

import e2avg_common as C  # noqa: E402
import e2avg_luno as L  # noqa: E402

SOURCE_RUN = Path(r"D:\rang\outputs\e2-20261110-11-avg")


def main(run):
    run = Path(run)
    d = run / "luno"
    d.mkdir(parents=True, exist_ok=True)
    src, _ = L.ms_paths(SOURCE_RUN)
    ms = d / src.name
    if not ms.exists():
        shutil.copytree(src, ms)  # the MS only: not its .rang-run or .flagversions
        L.log(run, f"copied {src} to {ms}")
    shutil.copy(SOURCE_RUN / L.STRATEGY, d / L.STRATEGY)
    text = L.CONFIG.replace("  average_time: true\n", "  average_time: true\n  average_freq: true\n")
    assert "average_freq: true" in text
    (d / "config.yaml").write_text(text, encoding="utf-8")
    rc, wall = C.rang_core("run", d / "config.yaml", ms, log=d / "rang-core.log")
    L.log(run, f"rang-core run (average_freq) rc={rc} {wall:.1f}s")
    if rc:
        return rc
    L.score(run, ms=ms, cdir=SOURCE_RUN / "casa", name="luno-freqavg-score.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
