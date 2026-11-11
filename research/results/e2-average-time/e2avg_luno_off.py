"""The LUNO configuration of e2avg_luno.py without `calibrate.average_time`
(every row solved) on a fresh conversion, scored against the CASA tables of
another run: separates the averaging's share of a rang-CASA difference from
the rest. Only where the unaveraged solve fits (a development slice).

    E2AVG_DRY="--rows N --chan A:B" python e2avg_luno_off.py RUN CASA_RUN
"""

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import e2avg_common as C
import e2avg_luno as L


def main(run, casa_run):
    run = Path(run)
    run.mkdir(parents=True, exist_ok=True)
    shutil.copy(Path(casa_run) / L.STRATEGY, run / L.STRATEGY)
    ms, _ = L.ms_paths(run)
    if not ms.exists():
        L.build(run)
    d = ms.parent
    shutil.copy(run / L.STRATEGY, d / L.STRATEGY)
    text = L.CONFIG.replace("  average_time: true\n", "").replace(
        "memory_limit_gb: 8", "memory_limit_gb: 24"
    )
    (d / "config.yaml").write_text(text, encoding="utf-8")
    rc, wall = C.rang_core("run", d / "config.yaml", ms, log=d / "rang-core.log")
    L.log(run, f"rang-core run (unaveraged) rc={rc} {wall:.1f}s")
    if rc:
        return rc
    _, casa_ms = L.ms_paths(casa_run)
    L.score(run, ms=ms, cdir=casa_ms.parent, name="luno-off-score.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
