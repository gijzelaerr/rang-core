# SPDX-License-Identifier: GPL-3.0-or-later
"""F3 arm A (research/f3-flagger.md, section 2): AOFlagger 3.5's shipped
generic-default.lua per baseline on the four correlations (8 real images),
with the input mask, inside rang-aflag-aoflagger:3.5.0.

Usage (in the container): python3 f3_aoflag.py IN_DIR
IN_DIR holds vis.npy (nbl, nt, nc, 4) complex64 and mask.npy (nbl, nt, nc)
bool; writes flags.npy (nbl, nt, nc) bool (the strategy's output, which
includes the input mask) and aoflag.json (timing).
"""

import json
import sys
import time

import aoflagger
import numpy as np

STRATEGY = "/usr/share/aoflagger/strategies/generic-default.lua"


def main():
    d = sys.argv[1]
    vis = np.load(f"{d}/vis.npy", mmap_mode="r")
    mask = np.load(f"{d}/mask.npy", mmap_mode="r")
    nbl, nt, nc, _ = vis.shape
    f = aoflagger.AOFlagger()
    s = f.load_strategy_file(STRATEGY)
    out = np.zeros((nbl, nt, nc), bool)
    t0 = time.perf_counter()
    for b in range(nbl):
        m = np.ascontiguousarray(mask[b].T)  # (nc, nt): height = channels
        if m.all():
            out[b] = True
            continue
        v = np.asarray(vis[b])
        iset = f.make_image_set(nt, nc, 8)
        for c in range(4):
            x = np.where(np.isfinite(v[..., c]), v[..., c], 0)
            iset.set_image_buffer(2 * c, np.ascontiguousarray(x.real.T, np.float32))
            iset.set_image_buffer(2 * c + 1, np.ascontiguousarray(x.imag.T, np.float32))
        fm = f.make_flag_mask(nt, nc, False)
        fm.set_buffer(m)
        res = np.array(s.run(iset, fm).get_buffer(), bool).reshape(nc, nt)
        out[b] = res.T | mask[b]
    wall = time.perf_counter() - t0
    np.save(f"{d}/flags.npy", out)
    with open(f"{d}/aoflag.json", "w") as fh:
        json.dump(
            {
                "strategy": STRATEGY,
                "aoflagger": ".".join(str(x) for x in aoflagger.AOFlagger.get_version())
                if hasattr(aoflagger.AOFlagger, "get_version")
                else "3.5.0",
                "baselines": nbl,
                "seconds": wall,
            },
            fh,
        )
    print(json.dumps({"baselines": nbl, "seconds": round(wall, 1)}), flush=True)


if __name__ == "__main__":
    main()
