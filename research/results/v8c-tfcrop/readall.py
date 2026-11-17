# readall.py BATCH ARM... : invert every group of RO-<arm>, save readout-<batch>.json
import json, sys
import numpy as np
sys.path.insert(0, "C:/Users/gijsm/Worktrees/rang/v8c-tfcrop-poly/tools/oracles/casa")
import tfcrop_readout as ro
import warnings; warnings.simplefilter("ignore")
b = sys.argv[1]; P = f"D:/rang/outputs/v8c-tfcrop-20261116/probes/{b}"
cut = 3.0
res = {}
for arm in sys.argv[2:]:
    spec = json.load(open(f"{P}/spec-{arm}.json"))
    nsel = spec.get("nsel")
    for gi, (a, fl) in sorted(ro.group_planes(P, f"RO-{arm}", arm, nsel).items()):
        g = spec["groups"][gi]; A = a.mean(axis=(0, 1))
        F0 = A / (1 + np.array(g["m0"][: a.shape[2]])) if "m0" in g else A
        F, lo, hi, bad = ro.invert(a, fl, spec.get("cutoff", cut), F0=F0, iters=30)
        res[f"{arm}.{g['name']}"] = {"A": A.tolist(), "F": F.tolist(), "lo": lo.tolist(), "hi": hi.tolist(), "crossed": bad}
        d = F / A - 1; w = (hi - lo) / A
        print(f"{arm}.{g['name']:12s} crossed {bad:3d} width med {np.nanmedian(w):.1e}  F/A-1 (1e-5) ch0..4 {np.round(d[:5]*1e5,1)} "
              f"q {np.round(d[[32,64,128,192,250]]*1e5,1)} last3 {np.round(d[-3:]*1e5,1)}")
json.dump(res, open(f"{P}/readout-{b}.json", "w"))
