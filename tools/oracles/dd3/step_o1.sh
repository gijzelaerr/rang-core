#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# DD3 arm O, steps 1-2: per-facet model columns from WSClean predicts, then
# QuartiCal 0.2.7's DD solve. Usage: step_o1.sh SCRATCH CYCLEDIR
source "$(dirname "$0")/common.sh"
s=$1; d=$2; log="$d/o1.log"; : > "$log"
for f in 0 1 2 3; do
  cp "$d/facet$f-model.fits" "$s/pf$f-model.fits"
  wsc "$s" "$log" -predict -name "/w/pf$f" "${grid[@]}" /w/dd1.ms
  py - "$s/dd1.ms" "MODEL_D$f" <<'PY'
import sys, casacore.tables as pt
t = pt.table(sys.argv[1], readonly=False, ack=False)
t.putcol(sys.argv[2], t.getcol("MODEL_DATA")); t.close()
PY
done
rm -rf "$s/gains" "$s/qclogs"
( cd "$s" && OMP_NUM_THREADS=1 NUMBA_NUM_THREADS=1 /usr/bin/time -f "%e %M %x" -o "$d/qc-time.txt" \
  "$venv/bin/goquartical" \
    input_ms.path="$s/dd1.ms" input_ms.data_column=DATA input_ms.weight_column=WEIGHT_SPECTRUM \
    input_ms.time_chunk=0 input_ms.freq_chunk=0 \
    input_model.recipe=MODEL_D0:MODEL_D1:MODEL_D2:MODEL_D3 \
    solver.terms="[G]" solver.iter_recipe="[150]" solver.convergence_criteria=1e-7 \
    solver.convergence_fraction=0.99 solver.reference_antenna=0 solver.robust=false \
    solver.threads=1 mad_flags.enable=false output.flags=false output.overwrite=true \
    output.gain_directory="$s/gains" output.log_directory="$s/qclogs" \
    dask.threads=1 dask.scheduler=single-threaded \
    G.type=diag_complex G.direction_dependent=true G.pinned_directions="[]" \
    G.time_interval=4 G.freq_interval=0 >> "$log" 2>&1 )
rm -rf "$d/gains"; cp -r "$s/gains" "$d/gains"
