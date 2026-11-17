#!/bin/bash
# job.sh SLOTS MEM NAME CMD... : one heavy-lock job, detached, nice 19 / ionice idle, log in O/jobs/NAME.log
S=$1; M=$2; N=$3; shift 3
O=~/rang-data/outputs/calchain-floor-20261117; mkdir -p $O/jobs
cd ~/Worktrees/rang/calchain-floor/research/results/calchain-floor
export K_THREADS=$S RAYON_NUM_THREADS=$S OMP_NUM_THREADS=$S
P=~/Worktrees/rang/calchain-floor/.venv/bin/python
nohup nice -n 19 ionice -c3 python3 ~/Github/rang/tools/heavy_lock.py run --slots $S --mem $M -- bash -c "echo START \$(date -Is) load \$(cut -d' ' -f1-3 /proc/loadavg); P=$P; $*; rc=\$?; echo END \$(date -Is) rc=\$rc" > $O/jobs/$N.log 2>&1 < /dev/null &
echo launched $N
