#!/bin/bash
# pfb-imaging real commands on the DF5-O simulated field (read-only input), plain venv, latest release.
S=/mnt/d/rang/scratch/u4; O=/home/gijsm/Github/rang/outputs/u4-20261102-01/logs
F=/home/gijsm/Github/rang/outputs/df5o-20261031-01/field/field.ms
W=$S/w/pfb/run; rm -rf $W; mkdir -p $W/logs; cd $W
export OPENBLAS_NUM_THREADS=1 PATH=$S/pfb/venv/bin:$PATH UV_LINK_MODE=copy
COMMON="--nthreads 4 --log-directory $W/logs"
t() { name=$1; shift; /usr/bin/time -f "$name wall %e s rss %M kB exit %x" -a -o $O/timings.txt "$@" > $O/pfb-$name.log 2>&1; echo "$name exit $?"; tail -6 $O/pfb-$name.log | cut -c1-200; }
INIT="pfb init --ms $F --output-filename $W/a --data-column DATA --weight-column WEIGHT_SPECTRUM --channels-per-image 1 --chan-average 1 --bda-decorr 1.0 --precision double --product I --integrations-per-image -1 --no-progressbar"
t init-closure $INIT --nthreads 4 --log-directory $W/logs
grep -c zarr_format $O/pfb-init-closure.log
~/.local/bin/uv pip install -q --python $S/pfb/venv/bin/python --index-url https://pypi.org/simple 'xarray<2026.4' 2>&1 | tail -1
~/.local/bin/uv pip freeze --python $S/pfb/venv/bin/python | grep -E '^(xarray|zarr)=='
rm -rf $W/a*; t init-bound $INIT --nthreads 4 --log-directory $W/logs
t grid pfb grid --output-filename $W/a --nx 256 --ny 256 --cell-size 8.0 --psf-oversize 1.4 --epsilon 1e-6 --do-wgridding --product I --nthreads 4 --log-directory $W/logs
KC="pfb kclean --output-filename $W/a --niter 2 --threshold 1e-3 --gamma 0.1 --peak-factor 0.2 --epsilon 1e-6 --do-wgridding --product I --nthreads 4 --backend native --log-directory $W/logs"
t kclean-plain $KC
grep -n "threading layer\|core/kclean.py\|set_num_threads" $O/pfb-kclean-plain.log | head -5 | cut -c1-160
LD_LIBRARY_PATH=$S/pfb/venv/lib t kclean-ldpath $KC
