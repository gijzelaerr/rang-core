import numpy as np, math
from scipy import ndimage
from rang.core_imaging import read_fits
g=read_fits("/mnt/d/rang/outputs/20261103-gemclean-heldout/real/images3/cal3-003-gem-common-beam.fits")[0]
N=g.shape[0]; lab,n=ndimage.label(g>6e-3)
out=[]
for i,sl in enumerate(ndimage.find_objects(lab)):
    ny,nx=sl[0].stop-sl[0].start,sl[1].stop-sl[1].start
    if max(ny,nx)*3<60: continue
    m=lab[sl]==i+1; v=g[sl]*m; yy,xx=np.nonzero(m)
    w=v[m]; cy=(yy*w).sum()/w.sum()+sl[0].start; cx=(xx*w).sum()/w.sum()+sl[1].start
    out.append((round(float(w.sum()/(2*math.pi*(12.7/3/2.3548)**2)),3),round(float(v.max()*1e3),1),round((cy-N/2)*3/60,1),round(-(cx-N/2)*3/60,1),round(max(ny,nx)*3/60,1),int(m.sum())))
out.sort(reverse=True); print('flux Jy, peak mJy, north arcmin, east arcmin, extent arcmin, px'); print(out[:8])
