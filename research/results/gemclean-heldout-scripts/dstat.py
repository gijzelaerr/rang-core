import numpy as np, sys, json, math
from rang.core_imaging import read_fits
def mad(a): return 1.4826*float(np.median(np.abs(a-np.median(a))))
res={}
for name,p in (("raw","/mnt/d/rang/outputs/20261103-gemclean-heldout/real/dirty/raw-dirty"),("cal","/home/gijsm/Build/tmp/20261103-gemclean-heldout/real/run/cal-dirty")):
    d,h=read_fits(p+"-dirty.fits"); psf,hp=read_fits(p+"-psf.fits")
    n=d.shape[0]; k=np.unravel_index(np.argmax(d),d.shape)
    # sigma in four corner boxes of the inner field, away from centre, and the whole
    b=n//8
    corners=[d[n//2-3*b:n//2-2*b,n//2-3*b:n//2-2*b],d[n//2+2*b:n//2+3*b,n//2-3*b:n//2-2*b],d[n//2-3*b:n//2-2*b,n//2+2*b:n//2+3*b],d[n//2+2*b:n//2+3*b,n//2+2*b:n//2+3*b]]
    res[name]=dict(peak=float(d.max()),min=float(d.min()),peak_yx=[int(x) for x in k],mad_all=mad(d),mad_corners=[mad(c) for c in corners],rms_all=float(np.sqrt(np.mean(d**2))),
      peak_over_mad=float(d.max())/mad(d),wscnvis=h.get("WSCNVIS"),wscimgwg=h.get("WSCIMGWG"),bmaj=hp.get("BMAJ",0)*3600,bmin=hp.get("BMIN",0)*3600,bpa=hp.get("BPA"),
      psf_max=float(psf.max()),psf_far_sidelobe_abs=float(np.abs(psf[:n//2-200,:]).max()),crval=[h.get("CRVAL1"),h.get("CRVAL2")])
    print(name,json.dumps(res[name]))
json.dump(res,open("/mnt/d/rang/outputs/20261103-gemclean-heldout/real/dirty-stats.json","w"),indent=1)
