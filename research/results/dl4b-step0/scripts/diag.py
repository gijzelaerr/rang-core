import sys, torch, numpy as np
sys.path.insert(0, "/mnt/c/Users/gijsm/Github/rang/.claude/worktrees/v8a-listobs-1c691e/examples")
import dl4b_train as T
dev = torch.device("cuda")
data = T.Data("/mnt/d/rang/dl4b-step0/packs-test", dev)
idx = data.train[:8]
d, t, Gf, k, s0 = data.batch(idx, np.zeros(8, int))
s = T.robust_rms(d)
x = torch.stack([d / s, torch.zeros_like(d)], 1)
for name, net in (("init", None), ("ckpt", None)):
    T.setup(1)
    net = T.CAN().to(dev)
    if name == "ckpt":
        c = torch.load("/mnt/d/rang/dl4b-step0/runs/N1-seed1-failed-clip/ckpt.pt", weights_only=False)
        net.load_state_dict(c["net"])
    with torch.no_grad():
        y = net(x)[:, 0]
    print(name, "rms(out)/rms(in)", float(y.std() / x[:, 0].std()), "frac>0", float((y > 0).float().mean()), "max", float(y.max()))
tb = T.bconv(t, k)
print("empty-model loss", float((tb.abs().flatten(1).sum(1) / s0).mean()))
