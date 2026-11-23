#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# DD4 arm O, steps 1-2: per-facet model columns from WSClean predicts, then
# QuartiCal 0.2.7's DD diag_complex solve. Usage: step4_o1.sh SCRATCH CYCLEDIR NDIR PINNED
source "$(dirname "$0")/common4.sh"
s=$1; d=$2; n=$3; pinned=$4; log="$d/o1.log"; : > "$log"
recipe=""
for f in $(seq 0 $((n - 1))); do
  cp "$d/facet$f-model.fits" "$s/pf$f-model.fits"
  wsc "$s" "$log" -predict -name "/w/pf$f" "${grid[@]}" /w/sub.ms
  py - "$s/sub.ms" "MODEL_D$f" <<'PY'
import sys, casacore.tables as pt
t = pt.table(sys.argv[1], readonly=False, ack=False)
t.putcol(sys.argv[2], t.getcol("MODEL_DATA")); t.close()
PY
  recipe="${recipe:+$recipe:}MODEL_D$f"
done
rm -rf "$s/gains" "$s/qclogs"
( cd "$s" && OMP_NUM_THREADS=1 NUMBA_NUM_THREADS=1 /usr/bin/time -f "%e %M %x" -o "$d/qc-time.txt" \
  "$venv/bin/goquartical" \
    input_ms.path="$s/sub.ms" input_ms.data_column=DATA input_ms.weight_column=WEIGHT_SPECTRUM \
    input_ms.time_chunk=0 input_ms.freq_chunk=0 input_model.recipe="$recipe" \
    solver.terms="[G]" solver.iter_recipe="[150]" solver.convergence_criteria=1e-7 \
    solver.convergence_fraction=0.99 solver.reference_antenna=0 solver.robust=false \
    solver.threads=1 mad_flags.enable=false output.flags=false output.overwrite=true \
    output.gain_directory="$s/gains" output.log_directory="$s/qclogs" \
    dask.threads=1 dask.scheduler=single-threaded \
    G.type=diag_complex G.direction_dependent=true G.pinned_directions="$pinned" \
    G.time_interval=4 G.freq_interval=0 >> "$log" 2>&1 )
rm -rf "$d/gains"; cp -r "$s/gains" "$d/gains"
