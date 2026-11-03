import numpy as np, sys
from rang.core_imaging import read_fits
S='/home/gijsm/Build/tmp/20261103-gemclean-heldout/real/run/'
mad=lambda a:1.4826*float(np.median(np.abs(a-np.median(a))))
for name in sys.argv[1:]:
    r,_=read_fits(S+name+'-residual.fits'); m,_=read_fits(S+name+'-model.fits')
    N=r.shape[0]; b=N//8
    boxes=[r[N//2-3*b:N//2-2*b,N//2-3*b:N//2-2*b],r[N//2+2*b:N//2+3*b,N//2-3*b:N//2-2*b],r[N//2-3*b:N//2-2*b,N//2+2*b:N//2+3*b],r[N//2+2*b:N//2+3*b,N//2+2*b:N//2+3*b]]
    ib=(slice(N//6,N-N//6),slice(N//6,N-N//6))
    print(name,'corner mad uJy',[round(mad(x)*1e6) for x in boxes],'inner mad',round(mad(r[ib])*1e6),'inner peak mJy',round(float(np.abs(r[ib]).max())*1e3,3),'edge peak mJy',round(float(np.abs(r).max())*1e3,3),'flux',round(float(m.sum()),3),'neg',round(float(m[m<0].sum()),3),'px',int((m!=0).sum()))
