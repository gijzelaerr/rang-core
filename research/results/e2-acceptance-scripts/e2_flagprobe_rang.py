"""E2 flag probe: rang's Tricolour port (`core_flag.flag_rows`) on one
extracted scan group, keeping the window flags after each step.

    python e2_flagprobe_rang.py GROUP.npz STRATEGY.yaml OUT.npz [all]

Runs natively on Windows or in a Linux build (WSL). By default only the probed
baseline's rows are flagged, on the group's time grid, as the flag stage does;
`all` flags the whole group in one call. OUT.npz holds `stages` (step, time,
chan) and `intensity` of the probed baseline and `flags` (its rows' final
flags, any corr).
"""

import importlib.util
import platform
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
# An installed rang (the Linux wheel built from this worktree) wins; else the
# worktree's own package (the native editable build).
if importlib.util.find_spec("rang") is None:
    sys.path.insert(0, str(ROOT / "python"))
from rang import core_flag


def main():
    group, strategy, out = sys.argv[1:4]
    whole = len(sys.argv) > 4 and sys.argv[4] == "all"
    g = np.load(group)
    _scan, a1, a2 = g["probe"]
    sel = (g["antenna1"] == a1) & (g["antenna2"] == a2)
    rows = np.arange(len(g["time"])) if whole else np.flatnonzero(sel)
    strategies = core_flag.parse_strategy(Path(strategy).read_text(encoding="utf-8"))
    masks = [core_flag.load_static_mask(p) for p in core_flag.static_mask_files()]
    t0 = time.perf_counter()
    res = core_flag.flag_rows(
        g["data"][rows],
        g["flag_in"][rows],
        g["antenna1"][rows],
        g["antenna2"][rows],
        g["time"][rows],
        g["antenna_position"],
        g["chan_freq"],
        g["chan_width"],
        g["corr_type"],
        strategies,
        masks=masks,
        want_intensity=True,
        want_stages=True,
        time_grid=np.unique(g["time"]),
    )
    seconds = time.perf_counter() - t0
    ubl = res["ubl"]
    probe = int(np.flatnonzero((ubl[:, 0] == a1) & (ubl[:, 1] == a2))[0])
    names = list(res["stages"])
    stages = np.stack([np.asarray(res["stages"][n][probe, 0]) for n in names])
    flags = res["flags"].any(-1)[sel[rows]]
    np.savez(
        out,
        stages=stages,
        intensity=res["intensity"][probe, 0],
        flags=flags,
        seconds=seconds,
        core_seconds=res["seconds"],
        rows=len(rows),
        names=np.array(names),
        platform=platform.platform(),
    )
    print(
        "rang",
        platform.system(),
        "all" if whole else "baseline",
        "rows",
        len(rows),
        "seconds",
        round(seconds, 2),
        "flagged",
        int(flags.sum()),
    )


if __name__ == "__main__":
    main()
