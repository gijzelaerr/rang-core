import numpy as np, json
from pathlib import Path
from rang.core_imaging import read_fits
P=Path('/mnt/d/rang/outputs/20261103-gemclean-heldout/real/prep')
m=json.loads((P/'meta.json').read_text()); n,c=m['nrow'],m['nchan']
vis=np.memmap(P/'vis.c64',np.complex64,'r',shape=(n,c)); gw=np.memmap(P/'wgt.f32',np.float32,'r',shape=(n,c))
# channel differences on 5 % of the rows; the imaging-weighted variance of a difference
rows=np.arange(0,n,20)
v=np.asarray(vis[rows]); g=np.asarray(gw[rows],np.float64)
ok=(g[:,1:]>0)&(g[:,:-1]>0)
d=v[:,1:]-v[:,:-1]
# robust per-part sigma of the difference, in bands of gw/ raw
s_all=1.4826*np.median(np.abs(d[ok].real))/np.sqrt(2)
print('robust sigma per part per visibility (Jy)',s_all)
# noise of the image: sqrt(sum gw^2 sigma^2)/sum gw, with sigma^2 uniform (weights after the gains are close to uniform)
sumg=0.0;sumg2=0.0
for r0 in range(0,n,50000):
    x=np.asarray(gw[r0:r0+50000],np.float64); sumg+=x.sum(); sumg2+=(x**2).sum()
print('thermal I image rms estimate Jy',s_all*np.sqrt(sumg2)/sumg, 'eff',sumg**2/sumg2)
for name in ('cal-autoest-residual','cal-dirty-dirty'):
    r,_=read_fits(f'/home/gijsm/Build/tmp/20261103-gemclean-heldout/real/run/{name}.fits')
    N=r.shape[0]; b=N//8
    boxes=[r[N//2-3*b:N//2-2*b,N//2-3*b:N//2-2*b],r[N//2+2*b:N//2+3*b,N//2-3*b:N//2-2*b],r[N//2-3*b:N//2-2*b,N//2+2*b:N//2+3*b],r[N//2+2*b:N//2+3*b,N//2+2*b:N//2+3*b]]
    mad=lambda a:1.4826*float(np.median(np.abs(a-np.median(a))))
    print(name,'mad all',mad(r),'corners',[round(mad(x),6) for x in boxes],'peak',float(np.abs(r).max()))
m_,_=read_fits('/home/gijsm/Build/tmp/20261103-gemclean-heldout/real/run/cal-autoest-model.fits')
print('autoest model flux',float(m_.sum()),'neg',float(m_[m_<0].sum()),'px',int((m_!=0).sum()))
