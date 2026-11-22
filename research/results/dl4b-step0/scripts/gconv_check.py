"""Torch image-domain operator (dl4b_train.gconv with Data.batch's augmentation of
G) against numpy (dl4b_step0.conv on the augmented images), one validation
field, all 8 augmentation codes. Usage: gconv_check.py EVAL_DIR PSFG_DIR"""

import sys
from pathlib import Path

import numpy as np
import torch

here = Path(__file__).resolve().parents[4] / "examples"
sys.path.insert(0, str(here))
import dl4b_train as T


class S:
    """dl4b_step0's conv and read_split, copied (that module needs rang)."""

    @staticmethod
    def conv(m, G):
        M = np.zeros((512, 512))
        M[:256, :256] = m
        c = np.fft.irfft2(np.fft.rfft2(M) * np.fft.rfft2(np.fft.ifftshift(G.astype(float))), s=(512, 512))  # fmt: skip
        return c[:256, :256]

    @staticmethod
    def read_split(data):
        lines = (data.parent / "split.csv").read_text().split()[1:]
        return {int(a): b for a, b in (line.split(",") for line in lines)}


ev, pg = Path(sys.argv[1]), Path(sys.argv[2])
split = S.read_split(ev)
seed = min(s for s, v in split.items() if v == "validation")
k, i = divmod(seed, 10)
z = np.load(ev / f"shard-{k:03d}.npz")
G = np.load(pg / f"psfg-{k:03d}.npz")["G"][i]
m = z["model_b"][3 * i + 2].astype(np.float64)
dev = torch.device("cuda")
worst = 0.0
for a in range(8):
    mm, gg = m.copy(), G.copy()
    dims = [d for bit, d in ((2, 0), (1, 1)) if a & bit]
    if dims:
        mm = np.flip(mm, dims).copy()
        gg = np.roll(np.flip(gg, dims), [1] * len(dims), dims)
    if a & 4:
        mm, gg = mm.T.copy(), gg.T.copy()
    ref = S.conv(mm, gg)
    # torch path through Data.batch's flip/roll/transpose of G
    Gt = torch.from_numpy(G.copy()).to(dev)
    mt = torch.from_numpy(m.astype(np.float32)).to(dev)
    if dims:
        Gt = Gt.flip(dims).roll([1] * len(dims), dims)
        mt = mt.flip(dims)
    if a & 4:
        Gt, mt = Gt.T.clone(), mt.T.clone()
    Gf = torch.fft.rfft2(torch.fft.ifftshift(Gt[None], dim=(-2, -1)))
    out = T.gconv(mt[None], Gf)[0].double().cpu().numpy()
    err = float(np.abs(out - ref).max() / np.abs(ref).max())
    # and: augmenting the unaugmented result must equal the augmented-operator result
    base = S.conv(m, G)
    if dims:
        base = np.flip(base, dims)
    if a & 4:
        base = base.T
    equiv = float(np.abs(base - ref).max() / np.abs(ref).max())
    print(f"aug {a}: torch vs numpy {err:.2e}; equivariance {equiv:.2e}")
    worst = max(worst, err, equiv)
print("worst", worst, "PASS" if worst < 1e-5 else "FAIL")
