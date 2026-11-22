import sys

import numpy as np
import torch

sys.path.insert(
    0, "/mnt/c/Users/gijsm/Github/rang/.claude/worktrees/v8a-listobs-1c691e/examples"
)
import dl4b_train as T

dev = torch.device("cuda")
data = T.Data("/mnt/d/rang/dl4b-step0/packs-test", dev)
idx = data.train[:16]
d, t, Gf, k, s0 = data.batch(idx, np.zeros(16, int))
tb = T.bconv(t, k)


def l1(u):
    return float(
        ((T.bconv(u, k) - tb).abs().flatten(1).sum(1) / s0).mean()
    ) / T.empty_loss(t, k, s0)


for lr in (3e-4, 1e-3):
    T.setup(1)
    net = T.CAN().to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    for it in range(601):
        u, m = T.step_model(net, d, torch.zeros_like(d), raw=True)
        loss = (
            (((T.bconv(u, k) - tb) / s0[:, None, None]) ** 2).flatten(1).sum(1).mean()
        )
        opt.zero_grad()
        loss.backward()
        opt.step()
        if it % 100 == 0:
            with torch.no_grad():
                print(
                    lr,
                    it,
                    "mse",
                    float(loss),
                    "L1 ratio (clipped)",
                    l1(m.detach()),
                    "npix>0 median",
                    float((m > 0).flatten(1).sum(1).float().median()),
                )
