"""Direction arguments of sumthreshold vs sumthreshold_masked (post-hoc).
A horizontal (time) run of 8 samples at 0.6 and a vertical (frequency) run of
8 samples at 0.6, on zeros: only an L=8 window (threshold 0.42) detects them."""
import glob
import aoflagger
import numpy as np
f = aoflagger.AOFlagger()
img = np.zeros((64, 32), np.float32)
img[10, 4:12] = 0.6     # horizontal run (x = time)
img[30:38, 20] = 0.6    # vertical run (y = frequency)
for lua in sorted(glob.glob("/probe/dir_*.lua")):
    s = f.load_strategy_file(lua)
    iset = f.make_image_set(32, 64, 1)
    iset.set_image_buffer(0, img)
    o = np.array(s.run(iset).get_buffer())
    print(lua.split("/")[-1].ljust(36), "horizontal run found", bool(o[10, 4:12].all()), "vertical run found", bool(o[30:38, 20].all()))
