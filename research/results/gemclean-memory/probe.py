"""Peak memory of GeMClean's polarisation path against channels x
polarisations x image size (research/gemclean-memory.md, step 1).

    probe.py make OUT_MS [NANT NTIME NCHAN]   a synthetic MS (W1's writer):
        NANT antennas, NTIME integrations, NCHAN channels, 4 correlations,
        a 1 Jy point source in XX and YY plus noise, 10 % of the cells
        flagged in all four correlations at once (as after E2-B's P flag
        spread), unit WEIGHT.
    probe.py run GEMCLEAN MS OUTDIR SIZE CHANNELS POL [extra ...]
        one joined run (-pol POL -join-polarizations when POL has several,
        -channels-out CHANNELS -join-channels when CHANNELS > 1) of the
        gemclean binary or `python -m rang.gemclean` (GEMCLEAN = "python"),
        with -memory-report; prints one JSON line: the peak working set /
        VmHWM from the run's own report, the heap phases and the buffers.

The binary's allocator counts heap bytes on every platform (Linux
HugePageAlloc, elsewhere CountingAlloc); the wheel's does not, so for
`python` only the peak resident set is reported.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]


def make(out, nant=16, ntime=200, nchan=64, seed=20261501):
    sys.path.insert(0, str(ROOT / "examples"))
    import w1_writeback as w1
    from rang import core_ms_write

    nb = nant * (nant - 1) // 2
    nrow = nb * ntime
    ms = w1.make_ms(out, nrow, nchan, ncorr=4, flag="tiled", seed=seed, nant=nant)
    rng = np.random.default_rng(seed + 1)
    base = np.array([5109224.0, 2006790.0, -3239100.0])
    with core_ms_write.open_table(ms / "ANTENNA", readonly=False) as t:
        t.addrows(nant)
        t.putcol("POSITION", base + 150.0 * np.arange(nant)[:, None] * [1, 0.5, 0.2])
        t.putcol("NAME", [f"m{a:03d}" for a in range(nant)])
    with core_ms_write.open_table(ms / "FIELD", readonly=False) as t:
        t.addrows(1)
        t.putcol("NAME", ["CAL"])
        t.putcol("PHASE_DIR", np.array([[[0.0, -1.0]]]))
    with core_ms_write.open_table(ms, readonly=False) as t:
        uvw = t.getcol("UVW")
        uvw[:, 2] *= 0.02  # nearly coplanar
        t.putcol("UVW", uvw)
        t.putcol("WEIGHT", np.ones((nrow, 4), np.float32))
        t.putcol("FLAG_ROW", np.zeros(nrow, bool))
        step = 4096
        for start in range(0, nrow, step):
            n = min(step, nrow - start)
            noise = 0.05 * (
                rng.standard_normal((n, nchan, 4)) + 1j * rng.standard_normal((n, nchan, 4))
            )
            data = noise.astype(np.complex64)
            data[..., 0] += 1.0
            data[..., 3] += 1.0
            flag = np.repeat((rng.random((n, nchan)) < 0.1)[..., None], 4, axis=2)
            t.putcol("DATA", data, start, n)
            t.putcol("FLAG", flag, start, n)
    print(json.dumps({"ms": str(ms), "nant": nant, "nrow": nrow, "nchan": nchan, "seed": seed}))


def run(gemclean, ms, outdir, size, channels, pol, extra):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    name = outdir / f"n{size}-c{channels}-{pol}"
    cmd = [sys.executable, "-m", "rang.gemclean"] if gemclean == "python" else [gemclean]
    cmd += ["-name", str(name), "-size", str(size), str(size), "-scale", "4asec"]
    cmd += ["-weight", "briggs", "0", "-niter", "100000", "-mgain", "0.9"]
    cmd += ["-auto-threshold", "3", "-wgridder-accuracy", "1e-4"]
    cmd += ["-data-column", "DATA", "-no-update-model-required", "-memory-report"]
    if len(pol) > 1 and "," not in pol:
        cmd += ["-pol", pol, "-join-polarizations"]
    elif pol != "I":
        cmd += ["-pol", pol]
    if channels > 1:
        cmd += ["-channels-out", str(channels), "-join-channels"]
    cmd += list(extra) + [str(ms)]
    t0 = time.time()
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    wall = time.time() - t0
    (outdir / f"{name.name}.out").write_text(out.stdout + out.stderr, encoding="utf-8")
    rec = {"size": size, "channels": channels, "pol": pol, "exit": out.returncode, "wall_s": round(wall, 2)}
    if out.returncode == 0:
        rep = json.loads(Path(f"{name}-report.json").read_text(encoding="utf-8"))
        rec["peak_rss_gb"] = round(int(rep["peak_memory_bytes"]) / 1e9, 4) if rep.get("peak_memory_bytes") else None
        mem = rep.get("memory")
        if mem:
            rec["heap_peak_gb"] = round(max(int(p["heap_peak_bytes"]) for p in mem["phases"]) / 1e9, 4)
            top = max(mem["phases"], key=lambda p: int(p["heap_peak_bytes"]))
            rec["heap_peak_phase"] = top["label"]
            rec["buffers_gb"] = {b["label"]: round(int(b["bytes"]) / 1e9, 4) for b in mem["buffers"]}
        for f in outdir.glob(f"{name.name}*.fits"):
            f.unlink()
    print(json.dumps(rec))
    return rec


if __name__ == "__main__":
    if sys.argv[1] == "make":
        make(sys.argv[2], *map(int, sys.argv[3:6]))
    else:
        g, ms, od, size, ch, pol = sys.argv[2:8]
        run(g, ms, od, int(size), int(ch), pol, sys.argv[8:])
