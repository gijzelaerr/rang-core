#!/usr/bin/env bash
# The pilot-512 (real MeerKAT, 4096², 3asec, threshold 3 mJy, coarse = G7 default): the CPU
# baseline (a931b6c) and -gpu (Gate 2), then Gate 1 on its model. Usage: pilot_runs.sh REV BUDGET
REV=$1; BUD=$2
W=/c/Users/gijsm/Worktrees/rang/gpu-grid
O=D:/rang/outputs/20261116-gpu-grid
bash $W/outputs/gpu-grid/run_sky.sh $W/outputs/gpu-grid/bin/gemclean-a931b6c-cpu.exe $O/base pilot-coarse pilot coarse 8
nvidia-smi --query-gpu=memory.used --format=csv,noheader > $O/gate2/gpu/pilot-coarse.gpu
bash $W/outputs/gpu-grid/run_sky.sh $W/outputs/gpu-grid/bin/gemclean-$REV-gpu.exe $O/gate2/gpu pilot-coarse pilot coarse 8 -gpu -gpu-memory $BUD
grep -h "components\|^gpu:\|^wall" $O/base/pilot-coarse.log $O/gate2/gpu/pilot-coarse.log
RAYON_NUM_THREADS=8 $W/outputs/gpu-grid/bin/gpu_grid_parity-ref.exe D:/rang/outputs/20261103-gemclean-heldout/real/cal.ms 4096 3 1e-4 single \
  $O/base/pilot-coarse-model.fits $BUD > $O/gate1/pilot-coarse-b$BUD.json 2> $O/gate1/pilot-coarse-b$BUD.err
echo "pilot parity rc $?"
RAYON_NUM_THREADS=8 $W/outputs/gpu-grid/bin/gpu_grid_parity-ref.exe D:/rang/outputs/20261103-gemclean-heldout/real/cal.ms 4096 3 1e-4 single \
  - $BUD > $O/gate1/pilot-coarse-dirty-b$BUD.json 2> $O/gate1/pilot-coarse-dirty-b$BUD.err
echo "pilot dirty rc $?"
