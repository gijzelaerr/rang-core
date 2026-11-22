#!/bin/bash
# apply-calwt (#48): the A1 truth arm (research/apply-calwt.md section 5, S), on nash.
set -euo pipefail
WT=$HOME/Worktrees/rang/apply-calwt
PY=$WT/.venv/bin/python
S=$WT/research/results/apply-calwt/scripts
A=$HOME/rang-data/outputs/apply-calwt-20261120/a1
source "$HOME/.rang-env.sh"
LOCK="python3 $HOME/Github/rang/tools/heavy_lock.py run"
NICE="nice -n 19 ionice -c3"
cd "$A"
[ -e done.flags ] || { $NICE "$PY" -I "$S/calwt_a1.py" flags "$A" > flags.json; touch done.flags; }
if [ ! -e done.cfg ]; then
  cp "$WT/research/results/e1-chain-scripts/e1_config.yaml" a1.yaml
  cp "$WT/research/results/e2n-scripts/mk_rfi_flagging_calibrator_fields_firstpass.yaml" .
  sed -i 's/^  stages: \[flag, calibrate, apply, selfcal\]$/  stages: [calibrate, apply]/; s/^  calwt: false$/  calwt: true/' a1.yaml
  grep -q '^  stages: \[calibrate, apply\]$' a1.yaml
  grep -q '^  calwt: true$' a1.yaml
  sha256sum a1.yaml > done.cfg
fi
if [ ! -e done.run ]; then
  $LOCK --slots 2 --mem 8 -- $NICE env RAYON_NUM_THREADS=2 /usr/bin/time -v -o run.time \
    "$PY" -m rang.core_cli run a1.yaml "$A/a1-small.ms" > run.log 2>&1
  touch done.run
fi
[ -e done.score ] || { $NICE "$PY" -I "$S/calwt_a1.py" score "$A" "$A/score-a1.json"; touch done.score; }
