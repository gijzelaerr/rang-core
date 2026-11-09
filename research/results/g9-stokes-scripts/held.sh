#!/usr/bin/env bash
# held.sh : the held-out sky of research/g9-stokes.md, after the freeze is recorded in the note.
# The frozen binary /mnt/d/rang/outputs/g9-bin/gemclean-freeze (built by `build.sh freeze` on the
# clean freeze commit; its provenance gives the commit) gives H1p's seeds,
# sha256("<commit> <binary sha256> H1p"); simulate H1p, run Q4, Q5, Q0, Q1, Q2, Q3 with both
# imagers, then criterion A's identity runs with the frozen binary.
set -euo pipefail
W=$HOME/Worktrees/rang/fp-g9-stokes
S=$W/research/results/g9-stokes-scripts
O=/mnt/d/rang/outputs/g9-20261107-03
B=/mnt/d/rang/outputs/g9-bin/gemclean-freeze
read -r commit dirty _ < <(head -1 $B.provenance)
test "$dirty" = 0
bsha=$(sha256sum $B | cut -d" " -f1)
h=$(printf "%s %s H1p" "$commit" "$bsha" | sha256sum | cut -c1-16)
sky_seed=0x${h:0:8}; noise_seed=0x${h:8:8}
mkdir -p $O
echo "commit $commit binary $bsha H1p sky $sky_seed noise $noise_seed" | tee $O/freeze.txt
bash $S/sim.sh $O H1p --sky-seed $sky_seed --noise-seed $noise_seed
cp $B.provenance $O.code/
bash $S/batch.sh $O $B H1p Q4 Q5 Q0 Q1 Q2 Q3
mkdir -p /mnt/d/rang/outputs/g9-20261107-04.code
cp -r $S $B.provenance /mnt/d/rang/outputs/g9-bin/gemclean-main-0f5ef06.provenance /mnt/d/rang/outputs/g9-20261107-04.code/
bash $S/identity.sh /mnt/d/rang/outputs/g9-20261107-04 /mnt/d/rang/outputs/g9-bin/gemclean-main-0f5ef06 $B
echo held done
