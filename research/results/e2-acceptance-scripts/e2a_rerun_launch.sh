#!/bin/bash
# E2-A rerun, rang arm (gate 1), timed, exclusive, from the frozen wheel venv
# (research/e2-acceptance.md 9.5-9.7). Git Bash. Launch only after the
# coordinator has accepted 9.5 and D: meets 9.6's start rule (605 GiB free).
# PRIORITY=critical only on the coordinator's word.
cd /c/Users/gijsm/Worktrees/rang/e2a-rerun || exit 1
export PYTHONUTF8=1
py=$(cygpath -w "$PWD/.venv/Scripts/python.exe")
wpy='C:\Users\gijsm\Build\tmp\20261111-e2-wheel\venv\Scripts\python.exe'
lock='C:\Users\gijsm\Github\rang\tools\heavy_lock.py'
S=research/results/e2-acceptance-scripts
A='D:\rang\outputs\e2a-20261115'
U=/d/rang/outputs/e2a-20261115
MS="$A\\e2a.ms"
L=$U/e2a-run.log
PRIORITY=${PRIORITY:-normal}
free=$("$wpy" -c "import shutil; print(int(shutil.disk_usage('D:/').free / 2**30))")
echo "$(date -Is) D: free ${free} GiB (start rule 605, 9.6)" >> $L
[ "$free" -ge 605 ] || { echo "$(date -Is) start rule not met; not started" >> $L; exit 2; }
"$py" $S/e2_post.py columns-before "$MS" "$A" >> $L 2>&1 || exit 1
load=$(powershell.exe -NoProfile -Command "(Get-CimInstance Win32_Processor | Measure-Object LoadPercentage -Average).Average" 2>/dev/null | tr -d '\r')
echo "START $(date -Iseconds) cpu_load_pct=$load exclusive $PRIORITY" >> $L
"$py" "$lock" run --priority "$PRIORITY" -- \
  "$wpy" $S/e2_diskguard.py --path 'D:/' --min-free-gib 165 --log "$A\\e2a-guard.jsonl" -- \
  "$wpy" $S/e2_timed.py "$A\\e2a-timed.json" -- \
  "$wpy" -m rang.core_cli run $S/e2a-rerun.yaml "$MS" 2>&1 | grep -v '^heavy_lock: waiting' >> $L
rc=${PIPESTATUS[0]}
echo "END $(date -Iseconds) rc=$rc" >> $L
echo "$(date -Is) D: free $("$wpy" -c "import shutil; print(int(shutil.disk_usage('D:/').free / 2**30))") GiB" >> $L
exit $rc
