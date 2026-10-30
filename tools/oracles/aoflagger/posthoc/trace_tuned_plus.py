"""A-FLAG post-hoc: why tuned+ returns no new flags on the holdout first steps (iteration trace)."""
import os, sys
import numpy as np
sys.path.insert(0, "/work/examples"); sys.path.insert(0, "/work/tools/oracles/aoflagger")
import oracle_aoflagger as oa
import st_bridge
import aoflagger

O = "/work/outputs/core-d-oracle-20261029-01/run/"
for lab, step in (("strategy-00-holdout_masked", "02-sum_threshold"), ("strategy-00-operational", "02-sum_threshold")):
    st = np.load(O + lab + "/stages.npz"); names = list(st.files); k = names.index(step)
    vis = np.load(O + lab + "/intensity.npz")["intensity"]
    images, masks, nan = oa.stage_inputs(vis, st[names[k - 1]])
    open("/tmp/p.lua", "w").write(oa.lua_table(dict(ntime=14, outlier_nsigma=10, spike_width_time=12.5, spike_width_freq=10.0, num_major_iterations=1)))
    os.environ["RANG_AFLAG_PARAMS"] = "/tmp/p.lua"
    f = aoflagger.AOFlagger(); s = f.load_strategy_file("/work/tools/oracles/aoflagger/tuned.lua")
    for b in (1, 4):
        it = masks[b].copy(); fr = []
        for i in range(5):
            det = oa._run(f, s, images[b], it)
            out = st_bridge.smear_and_cut(det.T, 3, 3, 0.6, 0.8).T | nan[b]
            fr.append((round(float(det.mean()), 3), round(float(out.mean()), 3), int((out & ~masks[b]).sum())))
            it |= out
        print(lab[:22], "bl", b, "input", round(float(masks[b].mean()), 3), "per iteration (det frac, out frac, out new):", fr)
