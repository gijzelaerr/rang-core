#!/bin/bash
# Supplement to gated.sh: the second W1/W5 timing per gated sky (gated.sh passed --tag "-r2",
# which argparse read as an option, so those runs never started). Then rescore.
H=/mnt/c/Users/gijsm/Github/rang/.claude/worktrees/v8a-listobs-1c691e
S=$HOME/Build/tmp/20261121-dl4b-step1
export DL4B_WSCLEAN='docker run --rm --user {uid} -v /mnt/d:/mnt/d -v /home/gijsm/Build/tmp:/home/gijsm/Build/tmp -w {cwd} rang-wsclean-native:3.7 wsclean'
cd $H
PY=~/Github/rang/.venv/bin/python
for G in G1 G2 G3 G4; do
  $PY examples/dl4b_step1.py ladder $S/skies $S --names $G --arms W1,W5 --threads 16 --tag=-r2
done
ARMS=W1,W5$(for R in "" "r2"; do for K in 1 2 3; do printf ",P-s$K$R-t5-K1"; done; done)
$PY examples/dl4b_step1.py score $S/skies /mnt/d/rang/dl4b-step1/score-gated.json --names G1,G2,G3,G4 --arms $ARMS
echo "wrepeat done $(date +%FT%T)"
