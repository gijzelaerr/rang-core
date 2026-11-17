#!/bin/bash
# job.sh SLOTS MEM NAME CMD...  : one heavy-lock job, detached, log in O/jobs/NAME.log
S=$1; M=$2; N=$3; shift 3
O=~/rang-data/outputs/e2a-3b-k-20261117; mkdir -p $O/jobs
cd ~/Worktrees/rang/e2a-3b-k/research/results/e2a-3b-k
export K_THREADS=$S
nohup nice -n 19 ionice -c3 python3 ~/Github/rang/tools/heavy_lock.py run --slots $S --mem $M -- bash -c "echo START \$(date -Is) load \$(cut -d\" \" -f1-3 /proc/loadavg); $*; rc=\$?; echo END \$(date -Is) rc=\$rc load \$(cut -d\" \" -f1-3 /proc/loadavg)" > $O/jobs/$N.log 2>&1 < /dev/null &
echo launched $N
