O=/mnt/d/rang/dl4b-step1/orient; cd $O
WS="docker run --rm --user $(id -u):$(id -g) -v /mnt/d:/mnt/d -v /dev/shm:/dev/shm -w $O rang-wsclean-native:3.7 wsclean"
W1="-size 4096 4096 -scale 1.5asec -weight briggs 0.5 -j 16 -niter 10000000 -no-update-model-required -multiscale -auto-mask 5 -auto-threshold 3 -mgain 0.8"
cp H5-c-model-after1.fits H5-d-model.fits
/usr/bin/time -f "predict wall %e s" $WS -size 4096 4096 -scale 1.5asec -weight briggs 0.5 -j 16 -predict -name H5-d $O/H5.ms > H5-d-p.log 2>&1; tail -1 H5-d-p.log
/usr/bin/time -f "continue wall %e s" $WS $W1 -continue -name H5-d $O/H5.ms > H5-d-c.log 2>&1; tail -1 H5-d-c.log; grep -E "Inversion:|major iterations|iterations in total|rror" H5-d-c.log | tail -4
~/Github/rang/.venv/bin/python - <<PY
from astropy.io import fits
a=fits.getdata("$O/H5-W1-model.fits").squeeze(); b=fits.getdata("$O/H5-d-model.fits").squeeze()
ra=fits.getdata("$O/H5-W1-residual.fits").squeeze(); rb=fits.getdata("$O/H5-d-residual.fits").squeeze()
print("continue vs full: model flux", float(a.sum()), float(b.sum()), "residual rms", float(ra.std()), float(rb.std()))
PY
