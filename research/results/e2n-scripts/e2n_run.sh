#!/bin/bash
# E2-N rang arm (gate 1), research/e2n-native.md sections 5 and 8: one shared
# heavy-lock job (12 slots, 40 GB), the disk guard (floor 165 GiB, start rule
# 412 GiB at grant), e2_timed.py, then `rang-core run e2n.yaml e2n.ms` from
# the wheel venv. Git Bash. CONFIG overrides the configuration (the as_is arm).
cd /c/Users/gijsm/Worktrees/rang/e2n || exit 1
export PYTHONUTF8=1
py='C:\Users\gijsm\Github\rang\.venv\Scripts\python.exe'
wpy='C:\Users\gijsm\Build\tmp\20261116-e2n\wheel-venv\Scripts\python.exe'
lock='C:\Users\gijsm\Github\rang\tools\heavy_lock.py'
S=research/results/e2-acceptance-scripts
N=research/results/e2n-scripts
A='D:\rang\outputs\e2n-20261116'
U=/d/rang/outputs/e2n-20261116
MS="$A\\e2n.ms"
CONFIG=${CONFIG:-$N/e2n.yaml}
TAG=${TAG:-e2n}
START_MIN=${START_MIN:-412}
L=$U/$TAG-run.log
free=$("$wpy" -c "import shutil; print(int(shutil.disk_usage('D:/').free / 2**30))")
echo "$(date -Is) D: free ${free} GiB (start rule $START_MIN)" >> $L
[ "$free" -ge "$START_MIN" ] || { echo "$(date -Is) start rule not met at queue time; not started" >> $L; exit 2; }
"$py" $S/e2_post.py columns-before "$MS" "$A\\R" >> $L 2>&1 || exit 1
load=$(powershell.exe -NoProfile -Command "(Get-CimInstance Win32_Processor | Measure-Object LoadPercentage -Average).Average" 2>/dev/null | tr -d '\r')
echo "START $(date -Iseconds) cpu_load_pct=$load shared 12 slots 40 GB config $CONFIG" >> $L
RAYON_NUM_THREADS=12 "$py" "$lock" run --slots 12 --mem 40 -- \
  "$wpy" $S/e2_diskguard.py --path 'D:/' --min-free-gib 165 --start-min-free-gib "$START_MIN" --log "$A\\$TAG-guard.jsonl" -- \
  "$wpy" $S/e2_timed.py "$A\\$TAG-timed.json" -- \
  "$wpy" -m rang.core_cli run "$CONFIG" "$MS" 2>&1 | grep -v '^heavy_lock: waiting' >> $L
rc=${PIPESTATUS[0]}
echo "END $(date -Iseconds) rc=$rc" >> $L
echo "$(date -Is) D: free $("$wpy" -c "import shutil; print(int(shutil.disk_usage('D:/').free / 2**30))") GiB" >> $L
exit $rc
