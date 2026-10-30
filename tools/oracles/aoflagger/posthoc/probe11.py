"""Horizontal masked SumThreshold: bridge with and without the xRight quirk vs
AOFlagger (fixed hybrid.lua, vertical = false) on synthetic data (post-hoc)."""
import os
import sys
import numpy as np
import aoflagger

sys.path.insert(0, "/work/tools/oracles/aoflagger")
import st_bridge

f = aoflagger.AOFlagger()
s = f.load_strategy_file("/work/tools/oracles/aoflagger/hybrid.lua")
for vertical in (False, True):
    open("/tmp/p.lua", "w").write("return {vertical = %s}\n" % ("true" if vertical else "false"))
    os.environ["RANG_AFLAG_PARAMS"] = "/tmp/p.lua"
    rng = np.random.default_rng(13)
    tot = {"quirk": 0, "intended": 0, "other_direction_model": 0}
    for trial in range(40):
        h, w = (60, 1) if vertical else (60, 30)
        img = rng.normal(0, 0.3, (h, w)).astype(np.float32)
        img[rng.random((h, w)) < 0.05] += 1.3
        miss = rng.random((h, w)) < 0.3
        iset = f.make_image_set(w, h, 1)
        iset.set_image_buffer(0, img)
        fm = f.make_flag_mask(w, h, False)
        fm.set_buffer(miss)
        ao = np.array(s.run(iset, fm).get_buffer(), bool)
        if vertical:
            cols, cmiss = img.T.copy(), miss.T.copy()
            q = st_bridge.aoflagger_columns(cols, cmiss, vertical=True).T
            i = st_bridge.aoflagger_columns(cols, cmiss, vertical=False, quirk=False).T
            o = st_bridge.aoflagger_columns(cols, cmiss, vertical=False, quirk=True).T
            # width 1: the horizontal L = 1 pass also runs; it equals vertical L = 1.
        else:
            q = st_bridge.aoflagger_columns(img, miss, vertical=False, quirk=True)
            i = st_bridge.aoflagger_columns(img, miss, vertical=False, quirk=False)
            o = st_bridge.aoflagger_columns(img, miss, vertical=True)
        tot["quirk"] += int((ao != q).sum())
        tot["intended"] += int((ao != i).sum())
        tot["other_direction_model"] += int((ao != o).sum())
    print("vertical" if vertical else "horizontal", "differences from AOFlagger over 40 images:", tot)
