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
print(
    "dirty peak/s0",
    float((d.flatten(1).max(1).values / s0).median()),
    "truth max",
    float(t.max()),
    "dirty max",
    float(d.max()),
)
tb = T.bconv(t, k)
print(
    "bconv(t) peak / dirty peak",
    float(tb.flatten(1).max(1).values.median() / d.flatten(1).max(1).values.median()),
)
for lr in (3e-4, 1e-3):
    T.setup(1)
    net = T.CAN().to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    for it in range(601):
        loss = T.loss_fn(net, "N1", d, t, None, k, s0)
        opt.zero_grad()
        loss.backward()
        opt.step()
        if it % 100 == 0:
            print(lr, it, float(loss) / T.empty_loss(t, k, s0))
    # L2 variant
