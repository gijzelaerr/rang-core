#!/bin/bash
# DL6 dry run, R3 inside WSL on glacier (called by dl6_glacier_train.sh under gpu_run.py).
WW=/home/gijsm/Build/tmp/20261120-dl6-dryrun
cd $WW/code
export CUBLAS_WORKSPACE_CONFIG=:4096:8
export GPU_CHECK="cmd.exe /c python C:/Users/gijsm/.gpu/gpu_run.py check --owner rang --minutes 15"
/usr/bin/time -f "wall %e s rss %M KB" -o $WW/train.time \
  /home/gijsm/Build/tmp/20261119-f5-torch/bin/python examples/f5_train.py \
  $WW/shards/calibrator $WW/train/seed-1 --seed 1 --steps 1000 --device cuda > $WW/train.log 2>&1
