import sys, math, shutil, tempfile, numpy as np
from pathlib import Path
sys.path.insert(0, "examples"); import astrodeconv_sim as a
from astropy.wcs import WCS
s=4; p=a.randomize(s,1000)
ra0,dec0=math.radians(63.36),math.radians(p["dec"]); a.FIELD_DEC[0]=dec0
xyz=np.array([q[1:] for q in a.SPIEL_ANTENNAS]); names=[q[0] for q in a.SPIEL_ANTENNAS]
nd=math.floor(p["synthesis"]*360); times,uvw,_=a.track(xyz,ra0,dec0,nd,10)
a1,a2=np.triu_indices(16,1); rows=(uvw[:,a2]-uvw[:,a1]).reshape(-1,3)
work=Path(tempfile.mkdtemp(dir="/dev/shm")); ms=work/"t.ms"
# first a header: image a zero column
cols={"DATA_Z":np.zeros((len(rows),1,4),np.complex64)}
sig=0.01
a.write_ms(ms,xyz,names,times,rows,np.tile(a1,nd).astype(np.int32),np.tile(a2,nd).astype(np.int32),cols,sig,a.JOB["freq0"],float(p["dfreq"]))
base=["-size","256","256","-scale","1.6asec","-weight","uniform","-temp-dir",str(work),"-reorder","-no-update-model-required"]
a.wsclean(base+["-niter","0","-data-column","DATA_Z","-name",str(work/"z"),str(ms)],work/"z.log",work)
_,h=a.read_image(work/"z-dirty.fits"); w=WCS(h).celestial
pix=[(128,128),(148,141),(60,200),(200,30)]
from rang import core_ms_write as cw
for (x,y) in pix:
    ra,dec=w.wcs_pix2world([x],[y],0)
    txt="#format\nsrc0000 %r %r 1.0 1049833007.8125 0.0\n"%(float(ra[0]),float(dec[0]))
    v=a.predict(txt,rows,ra0,dec0); d=np.zeros((len(rows),1,4),np.complex64); d[:,0,0]=d[:,0,3]=v
    with cw.open_table(str(ms),readonly=False) as t: t.putcol("DATA_Z",d)
    a.wsclean(base+["-niter","0","-data-column","DATA_Z","-name",str(work/"o"),str(ms)],work/"o.log",work)
    img,_=a.read_image(work/"o-dirty.fits"); py,px=np.unravel_index(np.argmax(img),img.shape)
    a.wsclean(base+["-niter","100000000","-auto-threshold","0.125","-auto-mask","5","-mgain","0.8","-data-column","DATA_Z","-name",str(work/"c"),str(ms)],work/"c.log",work)
    m,_=a.read_image(work/"c-model.fits")
    print((x,y),"dirty peak",float(img.max()),"at",(int(px),int(py)),"value at pix",float(img[y,x]),"model sum",float(m.sum()),"model 3x3",float(m[y-1:y+2,x-1:x+2].sum()))
shutil.rmtree(work)
