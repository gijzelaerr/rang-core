#!/bin/sh
# E3-B correctness rerun, resumed after the WSL restart of 2026-11-11 ~20:47:
# the rebuilt e2b.ms (BUILD rc 0) is verified again, then the CARACal pass runs.
set -u
cd /c/Users/gijsm/Worktrees/rang/e3-caracal
E2=/c/Users/gijsm/Worktrees/rang/fp-e2-acceptance
PY=$E2/.venv/Scripts/python.exe
echo "VERIFY START $(date -Is)"
"$PY" /c/Users/gijsm/Github/rang/tools/heavy_lock.py run --slots 2 --mem 8 -- "$PY" $E2/research/results/e2-acceptance-scripts/e2_convert.py verify 'D:\rang\outputs\e3-20261111-input\e2b.ms' "D:\rang\data\e2-b\LBAND_LUNO_CALIBRATORS.zarr:MAIN_16" "D:\rang\data\e2-b\LBAND_LUNO_CALIBRATORS.zarr:MAIN_17" "D:\rang\data\e2-b\LBAND_LUNO_CALIBRATORS.zarr:MAIN_18" "D:\rang\data\e2-b\LBAND_LUNO_CALIBRATORS.zarr:MAIN_19" --json 'D:\rang\outputs\e3-20261111-input\e2b-verify2.json' || exit 1
echo "VERIFY END $(date -Is)"
rm -rf /d/rang/outputs/e3-20261111-b-correct
MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu -- bash /mnt/c/Users/gijsm/Worktrees/rang/e3-caracal/research/results/e3-caracal/scripts/e3_locked.sh b correct /mnt/c/Users/gijsm/Worktrees/rang/e3-caracal/research/results/e3-caracal/configs/e3b-correct.yml /mnt/d/rang/outputs/e3-20261111-input shared 2>&1 | grep -v waiting | tail -4
echo B-CORRECT-END
