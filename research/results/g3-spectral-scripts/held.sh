#!/usr/bin/env bash
# held.sh : held-out skies (seeds from the freeze), their comparison set, then criterion A's identity set.
set -u
X=$(dirname "$(readlink -f "$0")")
O=/mnt/d/rang/outputs/20261106-g3-spectral
B=$O/bin/gemclean-freeze
bash $X/sim.sh H1s --sky-seed 0x1f3ee7f2 --noise-seed 0x77d06fe6
bash $X/sim.sh H2s --sky-seed 0x588f203c --noise-seed 0xdab58ae3
bash $X/batch.sh $B freeze H1s H2s
for form in def coarse; do for s in s1 s2 s3 h1 h2 h3 h4; do bash $X/id_run.sh $B freeze $s $form; done; done
bash $X/id_run.sh $B freeze p256 def
echo HELD-DONE
