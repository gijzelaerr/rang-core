#!/bin/bash
# DL6 dry run, R3 on glacier's GPU (coordinator 2026-11-20): wait for nash's
# shards, copy them here, train seed 1 for 1,000 steps under gpu_run.py
# (owner rang), copy the weights back and start nash's second booking (tau,
# validation scorer). Run from Git Bash on glacier.
set -u
N=gijs@nash.ru.ac.za
R=/home/gijs/rang-data/outputs/dl6-dryrun-20261120
L=D:/rang/outputs/dl6-dryrun-20261120
WW=/home/gijsm/Build/tmp/20261120-dl6-dryrun
log() { echo "$(date -u +%FT%TZ) $*"; }
until ssh -o ConnectTimeout=20 $N "grep -q 'awaiting glacier training' $R/chain.log" 2>/dev/null; do
  if ssh -o ConnectTimeout=20 $N "grep -q 'rc=[1-9]' $R/chain.log" 2>/dev/null; then log "nash chain failed"; exit 1; fi
  sleep 120
done
log "shards ready on nash"
mkdir -p $L
t0=$(date +%s)
scp -q -r $N:$R/shards $L/ || { log "copy failed"; exit 1; }
log "copied $(du -sh $L/shards | cut -f1) in $(( $(date +%s) - t0 )) s"
wsl.exe -e bash -lc "rm -rf $WW/shards && cp -r /mnt/d/rang/outputs/dl6-dryrun-20261120/shards $WW/"
# Held until DL1's final exclusive timing on glacier is done (coordinator 2026-11-20).
DONE=/c/Users/gijsm/Github/rang/.claude/worktrees/chunk-task-api-946978/outputs/dl1/final-timing.done
until [ -f $DONE ]; do
  [ "$(date -u +%H%M)" -ge 1840 ] && break
  sleep 60
done
log "DL1 timing done: $([ -f $DONE ] && echo yes || echo no)"
if [ "$(date -u +%H%M)" -ge 1840 ]; then log "past 20:40 SAST: glacier is exclusive for #47 21:00-06:30; train after 06:30 SAST"; exit 2; fi
t0=$(date +%s)
MSYS_NO_PATHCONV=1 python C:/Users/gijsm/.gpu/gpu_run.py run --owner rang --vram 2 --hours 0.5 -- wsl.exe -e bash $WW/train.sh
rc=$?
log "train rc=$rc wall $(( $(date +%s) - t0 )) s (booking included)"
[ $rc -ne 0 ] && exit $rc
mkdir -p $L/train
wsl.exe -e bash -lc "cp -r $WW/train $WW/train.log $WW/train.time /mnt/d/rang/outputs/dl6-dryrun-20261120/"
ssh $N "mkdir -p $R/train" && scp -q -r $L/train/seed-1 $N:$R/train/ && scp -q $L/train.log $L/train.time $N:$R/ || { log "copy back failed"; exit 1; }
ssh $N "touch $R/train.done; cd $R && nohup setsid python3 ~/Github/rang/tools/heavy_lock.py run --slots 8 --mem 48 -- nice -n 19 ionice -c3 bash dl6_chain.sh > chain2.out 2>&1 < /dev/null &"
log "nash second booking queued"
