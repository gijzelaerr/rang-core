#!/bin/bash
# one lane of P validation: seed K, sky list, one tau, WSClean -j 4, inference 4 threads
K=$1; NAMES=$2; TAU=$3
H=/mnt/c/Users/gijsm/Github/rang/.claude/worktrees/v8a-listobs-1c691e
S=$HOME/Build/tmp/20261121-dl4b-step1
export DL4B_WSCLEAN='docker run --rm --user {uid} -v /mnt/d:/mnt/d -v /home/gijsm/Build/tmp:/home/gijsm/Build/tmp -w {cwd} rang-wsclean-native:3.7 wsclean'
cd $H && ~/Github/rang/.venv/bin/python examples/dl4b_step1.py parm $S/skies $S/lane-t$TAU --names $NAMES --onnx s$K=/mnt/d/rang/dl4b-step1/onnx/seed$K.onnx --taus $TAU --kmax 3 --threads 4 --infer-threads 4
