#!/usr/bin/env bash
# until.sh ARM MODEL FREEFLAG : real-data intervals 16, 64, 450 in order, stop at the first lifted (section 3)
R=D:/rang/outputs/dd6-20261125; PY=C:/Users/gijsm/Github/rang/.venv/Scripts/python.exe
arm=$1; model=$2; free=$3
for ti in 16 64 450; do
  slots=4; mem=15; [ $ti = 450 ] && slots=2
  bash $R/scripts/lane.sh "real-$arm-$ti|$slots|$mem|grid $R/real $ti $model $R/grid/real-$arm-$ti.json $free"
  $PY -c "import json,sys;r=json.load(open(sys.argv[1]));sys.exit(0 if all(x>0.10 for x in r['perdir_converged'][1:]) else 1)" $R/grid/real-$arm-$ti.json && break
done
