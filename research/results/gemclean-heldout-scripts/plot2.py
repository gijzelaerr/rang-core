import sys, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from rang.core_imaging import read_fits
D="/mnt/d/rang/outputs/20261103-gemclean-heldout/real/images3/"
g=read_fits(D+"cal3-003-gem-common-beam.fits")[0]; f=read_fits(D+"cal3-003-plain-common-beam.fits")[0]
N=g.shape[0]; c=N//2; h=300
cr=lambda a:a[c-h:c+h,c-h:c+h]
fig,ax=plt.subplots(1,3,figsize=(15,5.2))
ax[0].imshow(np.arcsinh(cr(g)/3e-4),origin="lower",cmap="magma",vmin=-1,vmax=8); ax[0].set_title("GeMClean, dataset B, centre 30', common 12.7\" beam")
ax[1].imshow(np.arcsinh(g[::4,::4]/3e-4),origin="lower",cmap="magma",vmin=-2,vmax=6); ax[1].set_title("GeMClean full field 3.4 deg")
d=cr(g-f); ax[2].imshow(d,origin="lower",cmap="RdBu_r",vmin=-2e-4,vmax=2e-4); ax[2].set_title("GeMClean - WSClean plain (+-0.2 mJy)")
for a in ax: a.set_xticks([]); a.set_yticks([])
plt.tight_layout(); plt.savefig(D+"gem-vs-plain.png",dpi=70)
print('max abs diff mJy',np.abs(g-f).max()*1e3,'rms diff uJy',(g-f).std()*1e6)
