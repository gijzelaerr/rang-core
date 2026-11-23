#!/bin/bash
# Detached: at 2026-11-22 06:50 SAST start the step-1 seed loop (gpu_seeds_sun.sh) through
# gpu_run (which waits for a free GPU lock). Logs to /mnt/d/rang/dl4b-step1/sunday-waiter.log.
L=/mnt/d/rang/dl4b-step1/sunday-waiter.log
echo "$(date +%FT%T) waiter armed (pid $$)" >> $L
while [ "$(date +%Y%m%d%H%M)" -lt 202611220650 ]; do sleep 60; done
echo "$(date +%FT%T) starting; t_speed running: $(pgrep -fc t_speed.sh)" >> $L
cmd.exe /c "python C:/Users/gijsm/.gpu/gpu_run.py run --owner rang --vram 11 --hours 14 -- wsl -d Ubuntu -- bash -c \"HOURS=5 bash /mnt/c/Users/gijsm/Github/rang/.claude/worktrees/v8a-listobs-1c691e/research/results/dl4b-step1/gpu_seeds_sun.sh 12000 8 1 2 3\"" >> $L 2>&1
echo "$(date +%FT%T) seed loop exit $?" >> $L
