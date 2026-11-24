import sys

sys.path.insert(0, sys.argv[1])
from pathlib import Path

import dl4s_screen as D
import numpy as np

d = Path(sys.argv[2])
tabs = {n: D.load(d / n) for n in ("K1", "G1", "B1")}
g = tabs["G1"]
i = np.nonzero((g["ant"] == 50) & (g["iv"] == 7))[0]
g["f"][i, :, 0] = True  # CASA's minsnr flag of e2a-3b-k 7: ID 50, interval 7, X
scr = D.screen(
    tabs, ["K1", "G1", "B1"], {"K1": "G1", "G1": "G1", "B1": "G1"}, "amplitude"
)
for n in ("K1", "G1"):
    for o in scr[n]["outliers"]:
        print(n, o["antenna"], o["interval"], o["pol"], o["caught_a"], o["caught_b"])
print(D.events(scr, "E2A", ["K1", "G1", "B1"]))
