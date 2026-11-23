#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# DD1 oracle (research/dd1-facet-gains.md, section 5): QuartiCal 0.2.7's
# direction-dependent diag_complex solve on cases P1-P4.
# Usage (WSL): bash tools/oracles/dd1/run_qc.sh SIMDIR SCRATCH OUTDIR
#   SIMDIR  the simulation (dd1.ms), e.g. /mnt/d/rang/outputs/dd1-20261123-01
#   SCRATCH a fresh directory on WSL's ext4 (the MS is copied there)
#   OUTDIR  where the gain stores, logs and timings go back to
# QC_VENV: the QuartiCal 0.2.7 venv (default ~/Build/tmp/20261123-dd15/venv-qc027).
set -euo pipefail
sim=$(realpath -m "$1"); scratch=$(realpath -m "$2"); out=$(realpath -m "$3")
venv=${QC_VENV:-$HOME/Build/tmp/20261123-dd15/venv-qc027}
if [ -e "$scratch" ]; then echo "$scratch exists; choose a fresh directory" >&2; exit 1; fi
mkdir -p "$scratch" "$out/timing" "$out/logs"
cp -r "$sim/dd1.ms" "$scratch/dd1.ms"
"$venv/bin/python" -c "import quartical, numba, sys; print(sys.version); print('numba', numba.__version__)" > "$out/versions.txt"
"$venv/bin/pip" freeze 2>/dev/null >> "$out/versions.txt" || "$venv/bin/python" -m pip freeze >> "$out/versions.txt" 2>/dev/null || true
export OMP_NUM_THREADS=1 NUMBA_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
run() {  # case column time_interval freq_interval pinned
  local name=$1 col=$2 ti=$3 fi=$4 pinned=$5
  echo "## $name"
  ( cd "$scratch" && /usr/bin/time -f "%e %M %x" -o "$out/timing/$name.txt" \
    "$venv/bin/goquartical" \
      input_ms.path="$scratch/dd1.ms" input_ms.data_column="$col" \
      input_ms.weight_column=WEIGHT_SPECTRUM input_ms.time_chunk=0 input_ms.freq_chunk=0 \
      input_model.recipe=MODEL_D0:MODEL_D1:MODEL_D2:MODEL_D3 \
      solver.terms="[G]" solver.iter_recipe="[50]" solver.convergence_criteria=1e-7 \
      solver.reference_antenna=0 solver.robust=false solver.threads=1 \
      mad_flags.enable=false output.flags=false output.overwrite=true \
      output.gain_directory="$scratch/gains-$name" output.log_directory="$scratch/logs-$name" \
      dask.threads=1 dask.scheduler=single-threaded \
      G.type=diag_complex G.direction_dependent=true G.pinned_directions="$pinned" \
      G.time_interval="$ti" G.freq_interval="$fi" \
      > "$out/logs/$name.log" 2>&1 )
  cp -r "$scratch/gains-$name" "$out/gains-$name"
}
date -u +%FT%TZ > "$out/started.txt"
run P1 DATA 4 0 "[]"
run P2 DATA 1 4 "[]"
run P3 DATA_NF 4 0 "[]"
run P4 DATA 4 0 "[0]"
date -u +%FT%TZ > "$out/finished.txt"
