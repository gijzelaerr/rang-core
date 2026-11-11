#!/bin/sh
# Development test of the E3 measure tools on LUNO dev scans 1-2 (5,000 rows per group).
set -u
cd /c/Users/gijsm/Worktrees/rang/e3-caracal
R=research/results/e3-caracal
W=/mnt/c/Users/gijsm/Worktrees/rang/e3-caracal/$R
S='D:\rang\data\e2-d\LBAND_LUNO_CALIBRATORS.zarr'
sh $R/scripts/e3_build.sh 'D:\rang\outputs\e3-20261111-smoke-input\smoke.ms' 'D:\rang\outputs\e3-20261111-smoke-input\verify2.json' "$S:MAIN_0" "$S:MAIN_1" --rows 5000 || exit 1
rm -rf /d/rang/outputs/e3-20261111-smoke-dev
MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu -- bash $W/scripts/e3_locked.sh smoke dev $W/configs/smoke.yml /mnt/d/rang/outputs/e3-20261111-smoke-input shared | grep -v "waiting\|^[.O8Z?=+:~,\$I7D]*\$" | tail -3
SPLIT=/mnt/d/rang/outputs/e3-20261111-smoke-dev/msdir/smoke-cal.ms
cat > /d/rang/outputs/e3-20261111-smoke-dev-measure.sh <<EOS
set -e
~/Github/caracal/.venv/bin/python $W/scripts/e3_vis_measures.py $SPLIT /mnt/d/rang/outputs/e3-20261111-smoke-dev/vis.json
bash $W/scripts/e3_leak.sh $SPLIT J1939-6342 /mnt/d/rang/outputs/e3-20261111-smoke-dev/leak 8
~/Github/caracal/.venv/bin/python $W/scripts/e3_leak_measure.py /mnt/d/rang/outputs/e3-20261111-smoke-dev/leak /mnt/d/rang/outputs/e3-20261111-smoke-dev/leak.json
EOS
MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu -- python3 /mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py run --slots 8 --mem 16 -- bash /mnt/d/rang/outputs/e3-20261111-smoke-dev-measure.sh 2>&1 | grep -v waiting | tail -20
echo DEVTEST-END
