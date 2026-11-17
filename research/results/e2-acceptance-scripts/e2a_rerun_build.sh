#!/bin/bash
# E2-A rerun: rebuild e2a.ms from the ESO137 zarr, verify, FLAG hash
# (research/e2-acceptance.md 9.1 recipe; 9.5 path; 9.8 record). Git Bash.
# Each step is a shared job of the main checkout's heavy lock, inside
# e2_diskguard.py (floor 165 GiB on D:, durable samples of RSS and CPU).
cd /c/Users/gijsm/Worktrees/rang/e2a-rerun || exit 1
export PYTHONUTF8=1
py=$(cygpath -w "$PWD/.venv/Scripts/python.exe")
lock='C:\Users\gijsm\Github\rang\tools\heavy_lock.py'
S=research/results/e2-acceptance-scripts
A='D:\rang\outputs\e2a-20261115'
U=/d/rang/outputs/e2a-20261115
MS="$A\\e2a.ms"
P='D:\rang\data\e2-a\ESO137\ms1_primary.zarr'
T='D:\rang\data\e2-a\ESO137\ms1_target.zarr'
L=$U/build-verify.log
mkdir -p $U
free() { "$py" -c "import shutil; print(int(shutil.disk_usage('D:/').free / 2**30))"; }
echo "$(date -Is) D: free $(free) GiB before build (needs 194 + 165)" >> $L
[ "$(free)" -ge 359 ] || { echo "$(date -Is) not enough disk; build not started" >> $L; exit 2; }
[ -e "$U/e2a.ms" ] && { echo "$(date -Is) $MS exists; not overwritten" >> $L; exit 2; }
step() { # step SLOTS MEM NAME cmd...
  sl=$1 mem=$2 name=$3; shift 3
  t0=$(date +%s)
  "$py" "$lock" run --slots "$sl" --mem "$mem" --poll 5 -- \
    "$py" $S/e2_diskguard.py --path 'D:/' --min-free-gib 165 --log "$A\\$name-guard.jsonl" -- "$@" \
    2>&1 | grep -v '^heavy_lock: waiting' >> $L
  rc=${PIPESTATUS[0]}
  echo "$(date -Is) $name rc=$rc $(( $(date +%s) - t0 ))s" | tee -a $L
  return $rc
}
step 4 8 build "$py" $S/e2_convert.py build "$MS" "$P:MAIN_4" "$T:MAIN_4" "$P:MAIN_5" || exit 1
step 4 8 verify "$py" $S/e2_convert.py verify "$MS" "$P:MAIN_4" "$T:MAIN_4" "$P:MAIN_5" --json "$A\\verify.json" || exit 1
step 2 4 flaghash "$py" $S/e2_flaghash.py "$MS" "$A\\flaghash-input.json" || exit 1
echo "$(date -Is) D: free $(free) GiB after build; du $(du -s --block-size=1G $U/e2a.ms | cut -f1) GiB" >> $L
