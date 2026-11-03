#!/usr/bin/env bash
# casacore proof, then niter 0 on raw (from D:) and on calibrated (scratch copy)
set -uo pipefail
G=/mnt/c/Users/gijsm/AppData/Local/Temp/claude/gh
W=/home/gijsm/Worktrees/rang/gemclean-heldout
D=/mnt/d/rang/outputs/20261103-gemclean-heldout/real
S=/home/gijsm/Build/tmp/20261103-gemclean-heldout/real
mkdir -p $S/run $D/dirty
IMG=rang-o-casa:6.7.6.14
docker run --rm --user "$(id -u):$(id -g)" --network none -e HOME=/tmp -v $G:/g:ro -v $D:/d:ro -v $S:/s $IMG python3 /g/cc_read.py /d/raw.ms /s/cc.npz | tee $D/casacore-read.json
cd /tmp; $W/.venv/bin/python -I $G/cc_cmp.py $S/cc.npz $D/casacore-compare.json
ws(){ # ws NAME MSPATH_DIR MSNAME extra...
  name=$1; dir=$2; ms=$3; out=$4; shift 4
  flock /home/gijsm/.rang-heavy.lock /usr/bin/time -v -o $out/$name.time docker run --rm --user "$(id -u):$(id -g)" --network none -e HOME=/tmp -e OMP_NUM_THREADS=16 -v $dir:/data:ro -v $out:/run -w /run $IMG \
    wsclean -gridder wgridder -data-column DATA -field 0 -size 4096 4096 -scale 3asec -weight briggs 0.5 -pol I -j 16 -abs-mem 20 -no-update-model-required -temp-dir /run/tmp -no-min-grid-resolution -wgridder-accuracy 1e-6 "$@" -name /run/$name /data/$ms > $out/$name.log 2>&1
  echo "$name rc=$?"
}
mkdir -p $D/dirty/tmp
ws raw-dirty $D raw.ms $D/dirty -niter 0 -make-psf
rm -rf $D/dirty/tmp
[ -d $S/cal.ms ] || cp -r $D/cal.ms $S/cal.ms
mkdir -p $S/run/tmp
ws cal-dirty $S cal.ms $S/run -niter 0 -make-psf
rm -rf $S/run/tmp
echo REAL1-DONE
