"""A3 re-verification with a noisy background (post-hoc): spikes at 0.999 and
1.001 of 6*sens on N(0, 0.01) noise, for the old and the fixed all-flagged mask."""
import os
import aoflagger
import numpy as np
f = aoflagger.AOFlagger()
sens = 0.5
os.environ["RANG_SENS"] = str(sens)
rng = np.random.default_rng(7)
for lua in ("/probe/st_abs.lua", "/probe/st_abs2.lua"):
    s = f.load_strategy_file(lua)
    for v in (6 * sens * 0.999, 6 * sens * 1.001):
        img = rng.normal(0, 0.01, (64, 14)).astype(np.float32)
        img[30, 7] = v
        iset = f.make_image_set(14, 64, 1)
        iset.set_image_buffer(0, img)
        o = np.array(s.run(iset).get_buffer())
        print(lua.split("/")[-1], f"v={v:.4f}", "spike flagged", bool(o[30, 7]), "total", int(o.sum()))
