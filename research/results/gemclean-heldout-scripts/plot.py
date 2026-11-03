# plot.py OUTDIR PNG name... : common-beam images and differences, inspection only
import sys, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from rang.core_imaging import read_fits
out,png,*names=sys.argv[1:]
im={n:read_fits(f"{out}/{n}-common-beam.fits")[0] for n in names}
N=next(iter(im.values())).shape[0]
c=N//2; h=450
crop=lambda a,hw=h:a[c-hw:c+hw,c-hw:c+hw]
fig,ax=plt.subplots(2,len(names),figsize=(5*len(names),10),squeeze=False)
for i,n in enumerate(names):
    ax[0,i].imshow(np.arcsinh(crop(im[n])/5e-4),origin="lower",cmap="magma",vmin=-2,vmax=7); ax[0,i].set_title(n+" (centre 45'), asinh")
    ax[1,i].imshow(np.arcsinh(im[n][::4,::4]/5e-4),origin="lower",cmap="magma",vmin=-2,vmax=5); ax[1,i].set_title("full field, 1/4 sampled")
for a in ax.ravel(): a.set_xticks([]); a.set_yticks([])
plt.tight_layout(); plt.savefig(png,dpi=70)
