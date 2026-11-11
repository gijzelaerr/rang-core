#!/bin/sh
# E3-B correctness rerun (try 2, 30 GB container cap) from a rebuilt e2b.ms; then the section 5 measures on its split.
set -u
cd /c/Users/gijsm/Worktrees/rang/e3-caracal
sh research/results/e3-caracal/scripts/e3_build.sh 'D:\rang\outputs\e3-20261111-input\e2b.ms' 'D:\rang\outputs\e3-20261111-input\e2b-verify2.json' "D:\rang\data\e2-b\LBAND_LUNO_CALIBRATORS.zarr:MAIN_16" "D:\rang\data\e2-b\LBAND_LUNO_CALIBRATORS.zarr:MAIN_17" "D:\rang\data\e2-b\LBAND_LUNO_CALIBRATORS.zarr:MAIN_18" "D:\rang\data\e2-b\LBAND_LUNO_CALIBRATORS.zarr:MAIN_19" || exit 1
rm -rf /d/rang/outputs/e3-20261111-b-correct
MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu -- bash /mnt/c/Users/gijsm/Worktrees/rang/e3-caracal/research/results/e3-caracal/scripts/e3_locked.sh b correct /mnt/c/Users/gijsm/Worktrees/rang/e3-caracal/research/results/e3-caracal/configs/e3b-correct.yml /mnt/d/rang/outputs/e3-20261111-input shared | grep -v "waiting\|^[.O8Z?=+:~,\]*\$" | tail -3
echo B-CORRECT-END
