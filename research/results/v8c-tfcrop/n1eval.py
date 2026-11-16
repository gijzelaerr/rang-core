# n1eval.py CONFIG_JSON ARMS... : V8's N1 probe (b05/b04, labelled probe) through rang.tfcrop.plane with a template candidate
import json, sys
import numpy as np
sys.path.insert(0, "C:/Users/gijsm/Worktrees/rang/v8c-tfcrop-poly/python")
sys.path.insert(0, "C:/Users/gijsm/Worktrees/rang/v8c-tfcrop-poly/tools/oracles/casa")
from rang import tfcrop
import tfcrop_template as tt, tfcrop_probe_eval as pe
cfg = json.loads(sys.argv[1])
tt.OPTS.update(cfg.get("opts", {}))
sched = {int(k): [tuple(s) for s in v] for k, v in cfg["sched"].items()}
def rf(avg, valid, kind, maxnp):
    m = int(maxnp)
    if kind == "line":
        tt.OPTS["sched_full"] = {m: [(1, 1)] * cfg.get("nline", 3)}
    else:
        tt.OPTS["sched_full"] = {m: sched.get(m, [(m, 3)] * 3)}
    return tt.template(avg, valid, kind, m, rule="full", clip=2.0, stop=cfg.get("stop", 0.0), resid_of="F", sd_over="kept", nstages=cfg.get("nline", 3) if kind == "line" else 99)
tfcrop.robust_fit = rf
tfcrop.TF["piece_min"] = 0
for b in ("b05", "b04"):
    batch = f"D:/rang/outputs/v8-tfcrop-20261116/probes/{b}"
    job = json.load(open(batch + "/job.json"))
    for case in job:
        if case["name"] not in sys.argv[2:]: continue
        params = dict(case["calls"][0]); casa = pe.load_flags(f"{batch}/out/{case['name']}.npz")
        got = np.zeros_like(casa); eq = n = 0
        for b_, c, _nm, a, nbl in pe.planes(batch, "N1"):
            g = tfcrop.plane(a, np.zeros(a.shape, bool), params); got[b_::nbl, :, c] = g
            eq += bool(np.array_equal(g, casa[b_::nbl, :, c])); n += 1
        tp = int((got & casa).sum())
        print(f"{case['name']:10s} planes equal {eq}/{n} CASA {int(casa.sum())} rang {int(got.sum())} P {tp/max(got.sum(),1):.4f} R {tp/max(casa.sum(),1):.4f}", flush=True)
