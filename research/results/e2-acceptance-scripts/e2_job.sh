#!/bin/sh
# E1b and E2 job wrapper (research/e2-acceptance.md): runs one command from the
# worktree under tools/heavy_lock.py, appending START (with the 1-min load of the
# host as Windows reports it), the output, and END with the exit code to LOG,
# so a restarted session can tell what finished.  Usage: e2_job.sh LOG CMD... (CMD py: the worktree's venv python)
log=$1; shift
cd /c/Users/gijsm/Worktrees/rang/fp-e2-acceptance || exit 1
export PYTHONUTF8=1
load=$(powershell.exe -NoProfile -Command "(Get-CimInstance Win32_Processor | Measure-Object LoadPercentage -Average).Average" 2>/dev/null | tr -d '\r')
echo "START $(date -Iseconds) cpu_load_pct=$load $*" >> "$log"
py=$(cygpath -w "$PWD/.venv/Scripts/python.exe")
[ "$1" = py ] && { shift; set -- "$py" "$@"; }
"$py" tools/heavy_lock.py run -- "$@" >> "$log" 2>&1
rc=$?
echo "END $(date -Iseconds) rc=$rc" >> "$log"
exit $rc
