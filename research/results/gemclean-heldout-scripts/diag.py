import numpy as np, json, math
from pathlib import Path
from rang import core_wgridder, core_ms
from rang.core_imaging import read_fits
ARC=math.pi/180/3600
P=Path('/mnt/d/rang/outputs/20261103-gemclean-heldout/real/prep2')
S='/home/gijsm/Build/tmp/20261103-gemclean-heldout/real/'
m=json.loads((P/'meta.json').read_text()); n,c=m['nrow'],m['nchan']
freq=np.fromfile(P/'freq.f64')
uvw=np.fromfile(P/'uvw.f64').reshape(n,3)
vis=np.memmap(P/'vis.c64',np.complex64,'r',shape=(n,c)); gw=np.memmap(P/'wgt.f32',np.float32,'r',shape=(n,c))
with core_ms.open_table(S+'cal2.ms') as t:
    a1=t.getcol('ANTENNA1');a2=t.getcol('ANTENNA2');tm=t.getcol('TIME')
utime,ti=np.unique(tm,return_inverse=True)
model,_=read_fits(S+'run/cal2-003-plain-model.fits')
L=np.hypot(uvw[:,0],uvw[:,1])
rows=np.nonzero(L<400)[0]
print('short rows',rows.size,'of',n,'baselines',len(set(zip(a1[rows],a2[rows]))))
kw=dict(pixsize_x=3*ARC,pixsize_y=3*ARC,epsilon=1e-5,flip_v=True,flip_w=True)
pred=core_wgridder.dirty2vis(uvw=uvw[rows],freq=freq,dirty=np.ascontiguousarray(model.T,np.float64),**kw)
v=np.asarray(vis[rows]); g=np.asarray(gw[rows],np.float64); ok=g>0
e=(v-pred)*ok
tot=(g*np.abs(e)**2).sum()
allq=m['q0']
print('share of total weight in these rows',g.sum()/m['gridding_weight_sum'],'share of Q',0.5*tot/m['gridding_weight_sum'],'of Q_final',0.5*tot/m['gridding_weight_sum']/0.2951)
x=(g*np.abs(e)**2)[ok]; xs=np.sort(x)[::-1]; cs=np.cumsum(xs)/xs.sum()
print('top 0.1%% cells hold %.3f, 1%% %.3f, 10%% %.3f of short-baseline misfit'%(cs[int(.001*x.size)],cs[int(.01*x.size)],cs[int(.1*x.size)]))
# per-baseline
b=a1[rows]*100+a2[rows]; ub,bi=np.unique(b,return_inverse=True)
pb=np.bincount(bi,(g*np.abs(e)**2).sum(1))/np.maximum(np.bincount(bi,g.sum(1)),1)
ln=np.bincount(bi,L[rows])/np.bincount(bi)
o=np.argsort(-pb)[:12]
print('worst baselines (ant1,ant2,length m,weighted mean |e|^2):',[(int(ub[i]//100),int(ub[i]%100),round(float(ln[i])),round(float(pb[i]),1)) for i in o],'median',float(np.median(pb)))
# per time
pt=np.bincount(ti[rows],(g*np.abs(e)**2).sum(1),minlength=len(utime))/np.maximum(np.bincount(ti[rows],g.sum(1),minlength=len(utime)),1)
print('per-time mean|e|^2 percentiles',np.percentile(pt,[0,10,50,90,100]).round(1).tolist(),'worst idx',np.argsort(-pt)[:8].tolist())
# per channel: both residual, data and residual after removing a linear-in-frequency scale (spectral mismatch test)
pc=(g*np.abs(e)**2).sum(0)/np.maximum(g.sum(0),1)
print('per-16chan mean|e|^2',[round(float(pc[i:i+16].mean()),1) for i in range(0,256,16)])
# coherent residual: band- and time-mean of e per baseline vs its rms (steady error vs outliers)
# Median |e| fractional against |M| per chan on short baselines and fit alpha of V relative to M
M=pred; A=(np.conj(M)*v*ok).sum(0).real; B=(np.abs(M)**2*ok).sum(0)
ratio=A/np.maximum(B,1e-30)
print('per-16chan <V M*>/<|M|^2>',[round(float(np.nanmean(ratio[i:i+16])),3) for i in range(0,256,16)])
f=freq/1e9; okc=B>0; print('fit alpha of ratio',np.polyfit(np.log(f[okc]),np.log(np.maximum(ratio[okc],1e-3)),1).tolist())
e2=(v-(pred*np.interp(freq,freq[okc],ratio[okc])[None,:]))*ok
print('misfit after per-channel scale: fraction left',(g*np.abs(e2)**2).sum()/tot)
