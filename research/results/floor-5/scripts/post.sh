#!/bin/bash
# floor-5 scoring: score (7 fam2 arms), twobytwo (Dm03), summary; 2 threads, 2 slots
source ~/Build/tmp/20261117-floor5/env.sh
export RAYON_NUM_THREADS=2 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2
export RANG_FLOOR5_G1RERUN=$OUT/g1
F=$OUT/family2
L="$LOCK run --slots 2 --mem 16 -- nice -n 19 ionice -c3 $HOME/Build/tmp/20261117-floor5/fam1.sh"
$L score R3=$F/R3/image Dm1=$F/Dm1/image Dm03=$F/Dm03/image Dms03=$F/Dms03/image Du1=$F/Du1/image S=$F/S/image C0=$F/C0/image || exit 1
$L twobytwo $F/Dm03/image || exit 1
$L summary || exit 1
echo "post done"
