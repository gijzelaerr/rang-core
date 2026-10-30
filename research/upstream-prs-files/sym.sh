#!/bin/bash
# Control for QuartiCal #452: the same solves with w_XY = w_YX (their mean).
set -u
B=~/Build/tmp/20261030-upstream-prs/conv
cd $B
export NUMBA_CACHE_DIR=$B/numba-cache
rm -rf scan9sym.ms && cp -r scan9.ms scan9sym.ms
../venv-qc027/bin/python -c "
from casacore.tables import table
t = table('scan9sym.ms', readonly=False, ack=False)
for c in ('WEIGHT_SPECTRUM', 'WEIGHT'):
    w = t.getcol(c); m = 0.5 * (w[..., 1] + w[..., 2]); w[..., 1] = m; w[..., 2] = m; t.putcol(c, w)
t.close()"
for cfg in "defaults 1 1 1e-6" "t2f32 2 32 1e-7"; do
  set -- $cfg
  for k in 25 50; do
    ../venv-qc027/bin/goquartical input_ms.path=scan9sym.ms input_ms.data_column=DATA input_model.recipe=MODEL_DATA \
      solver.terms=[G] G.type=complex G.time_interval=$2 G.freq_interval=$3 solver.convergence_criteria=$4 \
      solver.iter_recipe=[$k] solver.convergence_fraction=1.0 output.gain_directory=sym-$1/k$k/gains.qc \
      output.log_directory=sym-$1/k$k/logs.qc output.flags=false > sym-$1-k$k.log 2>&1
    ../venv-qc027/bin/python -c "
from daskms.experimental.zarr import xds_from_zarr
ds = xds_from_zarr('sym-$1/k$k/gains.qc::G')[0]
print('sym $1 k$k conv_perc', float(ds.conv_perc.values.ravel()[0]))"
  done
done
