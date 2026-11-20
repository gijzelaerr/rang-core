#!/bin/bash
# DL2: move running teacher streams to --priority critical without losing work (dl2-data.md
# amendment 8). Every 60 s: a teach_block.sh stream not yet started with PRIORITY=critical, whose
# heavy-lock ticket is still waiting (the lock process has no child yet), is stopped by process
# group and relaunched with the same arguments and PRIORITY=critical. A stream whose teacher is
# running is left alone until its next wait. Exits when no such stream is left.
S=~/Worktrees/rang/dl2-data/research/results/dl2-scripts
R=~/rang-data/outputs/dl2-data-20261119
cd $R
while :; do
  left=0
  for pid in $(pgrep -f "^/bin/bash .*teach_block.sh"); do
    grep -qz "^PRIORITY=critical$" /proc/$pid/environ 2>/dev/null && continue
    left=1
    pg=$(ps -o pgid= -p $pid | tr -d " ")
    lock=$(pgrep -g $pg -f "heavy_lock.py run" | head -1)
    [ -z "$lock" ] && continue
    pgrep -P $lock > /dev/null && continue        # holds its slots: running
    args=$(tr "\0" " " < /proc/$pid/cmdline | sed "s#^/bin/bash ##; s#^[^ ]*teach_block.sh ##")
    kill -TERM -- -$pg; sleep 3
    echo "REQUEUE $(date -u +%FT%TZ) teach_block.sh $args -> priority critical" >> logs/teach.log
    PRIORITY=critical setsid nohup $S/teach_block.sh $args >/dev/null 2>&1 </dev/null &
  done
  [ $left = 0 ] && break
  sleep 60
done
echo "REQUEUE-END $(date -u +%FT%TZ)" >> logs/teach.log
