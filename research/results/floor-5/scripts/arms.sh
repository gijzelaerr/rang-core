#!/bin/bash
# Family I arms, six at a time, each under the heavy lock at 4 slots (floor-5 section 7)
source ~/Build/tmp/20261117-floor5/env.sh
export RAYON_NUM_THREADS=4 OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 MKL_NUM_THREADS=4
one() { $LOCK run --slots 4 --mem 12 -- nice -n 19 ionice -c3 ~/Build/tmp/20261117-floor5/fam1.sh arm $1 > $OUT/logs/arm-$1.log 2>&1; echo "$(date -Is) arm $1 rc $?"; }
export -f one
printf "%s\n" "$@" | xargs -P 6 -I{} bash -c "one {}"
