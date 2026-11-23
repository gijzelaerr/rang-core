#!/bin/bash
# Gated read (section 5/6), inside ONE exclusive heavy-lock hold: per sky, in a fixed order,
# W1, W5, P seeds 1-3 (K, tau from the validation choice), then the same again (repeat r2).
# Usage: gated.sh K TAU
KK=$1; TAU=$2
H=/mnt/c/Users/gijsm/Github/rang/.claude/worktrees/v8a-listobs-1c691e
S=$HOME/Build/tmp/20261121-dl4b-step1
O=/mnt/d/rang/dl4b-step1/onnx
export DL4B_WSCLEAN='docker run --rm --user {uid} -v /mnt/d:/mnt/d -v /home/gijsm/Build/tmp:/home/gijsm/Build/tmp -w {cwd} rang-wsclean-native:3.7 wsclean'
cd $H
PY=~/Github/rang/.venv/bin/python
for G in G1 G2 G3 G4; do
  for R in "" "-r2"; do
    $PY examples/dl4b_step1.py ladder $S/skies $S --names $G --arms W1,W5 --threads 16 --tag "$R"
    for K in 1 2 3; do
      $PY examples/dl4b_step1.py parm $S/skies $S --names $G --onnx "s$K${R/-/}=$O/seed$K.onnx" --taus $TAU --kmax $KK --threads 16 --infer-threads 16
    done
  done
done
ARMS=W1,W5$(for R in "" "r2"; do for K in 1 2 3; do printf ",P-s$K$R-t$TAU-K$KK"; done; done)
$PY examples/dl4b_step1.py score $S/skies /mnt/d/rang/dl4b-step1/score-gated.json --names G1,G2,G3,G4 --arms $ARMS
echo "gated done $(date +%FT%T)"
