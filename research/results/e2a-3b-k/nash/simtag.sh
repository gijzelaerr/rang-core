#!/bin/bash
# simtag.sh CASE SEED : make one simulated case and run its four arms (research/e2a-3b-k.md step 4)
set -e
CASE=$1; SEED=$2
P=~/Worktrees/rang/e2a-3b-k/.venv/bin/python
cd ~/Worktrees/rang/e2a-3b-k/research/results/e2a-3b-k
if [ "$CASE" = s1f ]; then TAG=s0f; elif [ "$CASE" = s1 ] && [ "$SEED" = none ]; then TAG=s0; else TAG=$CASE-$SEED; fi
export RAYON_NUM_THREADS=$K_THREADS OMP_NUM_THREADS=$K_THREADS
t0=$(date +%s); $P k_sim.py make $CASE $SEED; echo "make $(( $(date +%s)-t0 )) s"
$P k_run.py copy sim-$TAG-u.ms sim-$TAG-d.ms
$P k_run.py copy sim-$TAG-u.ms sim-$TAG-casa.ms
$P k_run.py rang sim-$TAG-u.ms u
$P k_run.py casa c $TAG
$P k_run.py casa ck $TAG
$P k_run.py rang sim-$TAG-d.ms d
$P k_score.py sim $TAG > ~/rang-data/outputs/e2a-3b-k-20261117/score-sim-$TAG.txt
