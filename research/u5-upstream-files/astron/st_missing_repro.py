# SumThresholdMissing::horizontal: a missing sample at x = 1 enters the running sum.
# Usage: python3 st_missing_repro.py <dir with st_missing_repro.lua>
import sys

import aoflagger
import numpy as np

f = aoflagger.AOFlagger()
s = f.load_strategy_file(sys.argv[1] + "/st_missing_repro.lua")
w, h = 64, 8
rng = np.random.default_rng(1)
base = np.abs(rng.normal(0, 1, (h, w))).astype(np.float32)
for col in (1, 10):
    img = base.copy()
    miss = np.zeros((h, w), bool)
    img[:, col] = 1e4  # a hot sample in every row ...
    miss[:, col] = True  # ... that is marked missing
    iset = f.make_image_set(w, h, 1)
    iset.set_image_buffer(0, img)
    fm = f.make_flag_mask(w, h, False)
    fm.set_buffer(miss)
    out = np.array(s.run(iset, fm).get_buffer(), bool)
    print(
        f"missing hot column x={col}: flagged non-missing samples {int((out & ~miss).sum())} of {int((~miss).sum())}"
    )
