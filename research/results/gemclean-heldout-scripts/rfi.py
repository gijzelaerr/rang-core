import numpy as np, json, math
from pathlib import Path
from rang import core_wgridder
from rang.core_imaging import read_fits
ARC=math.pi/180/3600
P=Path('/mnt/d/rang/outputs/20261103-gemclean-heldout/real/prep')
m=json.loads((P/'meta.json').read_text()); n,c=m['nrow'],m['nchan']
freq=np.fromfile(P/'freq.f64')
uvw=np.fromfile(P/'uvw.f64').reshape(n,3)
vis=np.memmap(P/'vis.c64',np.complex64,'r',shape=(n,c)); gw=np.memmap(P/'wgt.f32',np.float32,'r',shape=(n,c))
model,_=read_fits('/home/gijsm/Build/tmp/20261103-gemclean-heldout/real/run/cal-autoest-model.fits')
rows=np.sort(np.random.default_rng(1).choice(n,41000,replace=False))
kw=dict(pixsize_x=3*ARC,pixsize_y=3*ARC,epsilon=1e-5,flip_v=True,flip_w=True)
pred=core_wgridder.dirty2vis(uvw=uvw[rows],freq=freq,dirty=np.ascontiguousarray(model.T,np.float64),**kw)
v=np.asarray(vis[rows]); g=np.asarray(gw[rows])>0
print('all',np.mean(g), 'model explains: Sum|V|^2 / Sum|V-M|^2', float((np.abs(v[g])**2).sum()/(np.abs(v[g]-pred[g])**2).sum()))
e=v-pred
ch=[]
for k in range(0,512,16):
    s=g[:,k:k+16]; a=e[:,k:k+16][s]
    d=(np.abs(a)**2).mean() if a.size else 0
    ch.append((round(float(freq[k]/1e6),1),round(float(s.mean()),2),round(float(np.sqrt(d/2)),3),round(float(1.4826*np.median(np.abs(a.real))) if a.size else 0,3)))
print('freq, unflagged fraction, rms per part, robust per part');
for x in ch: print(x)
L=np.hypot(uvw[rows,0],uvw[rows,1])
for lo,hi in ((0,100),(100,300),(300,1000),(1000,3000),(3000,9000)):
    s=(L>=lo)&(L<hi); a=e[s][g[s]]; b=v[s][g[s]]
    print('baseline',lo,hi,'n',a.size,'rms part',round(float(np.sqrt((np.abs(a)**2).mean()/2)),3),'robust',round(float(1.4826*np.median(np.abs(a.real))),3),'|V| rms',round(float(np.sqrt((np.abs(b)**2).mean()/2)),3))
