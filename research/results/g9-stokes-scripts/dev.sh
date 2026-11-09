#!/usr/bin/env bash
# dev.sh : the development runs of research/g9-stokes.md (D1 and P1) with the binary of the
# protocol commit, tagged dev1; the .code snapshot records the commit.
set -u
W=$HOME/Worktrees/rang/fp-g9-stokes
S=$W/research/results/g9-stokes-scripts
O=/mnt/d/rang/outputs/g9-20261107-02
bash $S/build.sh dev1
B=/mnt/d/rang/outputs/g9-bin/gemclean-dev1
mkdir -p $O.code
cp -r $S $O.code/ ; git -C $W rev-parse HEAD > $O.code/commit-dev1; cp $B.provenance $O.code/
bash $S/batch.sh $O $B D1 Q0 Q1 Q2
bash $S/batch.sh $O $B P1 Q4 Q5 Q0 Q1 Q2 Q6 Q3
echo dev done
