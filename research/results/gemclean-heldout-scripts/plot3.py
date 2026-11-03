import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from rang.core_imaging import read_fits
D="/mnt/d/rang/outputs/20261103-gemclean-heldout/real/images3/"
g=read_fits(D+"cal3-003-gem-common-beam.fits")[0]; c=2048; h=170
a=g[c-h+10:c+h+10,c-h:c+h]
fig,ax=plt.subplots(1,1,figsize=(8,8)); ax.imshow(np.arcsinh(a/5e-3),origin="lower",cmap="magma",vmin=0,vmax=5.5); ax.set_title("GeMClean centre 17', asinh(I/5 mJy)"); ax.set_xticks([]);ax.set_yticks([])
plt.tight_layout(); plt.savefig(D+"gem-zoom.png",dpi=60)
