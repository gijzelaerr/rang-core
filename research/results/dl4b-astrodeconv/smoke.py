import sys, json, time; sys.path.insert(0, "examples")
import astrodeconv_sim as a
t=time.time(); rec, fields, psf, big = a.simulate_seed(0, "/dev/shm", pilot=True)
print(json.dumps(rec, indent=1, default=float)[:3500])
for f in a.FLUX_SETS:
    fd=fields[f]; print(f, fd["n_inside"], fd["flux_inside"], fd["beam_a"], {k: float(abs(v).max()) for k,v in fd["prod"].items()})
import numpy as np; np.savez("/home/gijs/rang-data/outputs/dl4b-astrodeconv-20261119/smoke-s0.npz", **{f"{k}_{f}": v for f in a.FLUX_SETS for k, v in fields[f]["prod"].items()}, comps1000=fields[1000]["comps"], psf=psf)
print("wall", time.time()-t)
