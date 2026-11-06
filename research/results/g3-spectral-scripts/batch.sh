#!/usr/bin/env bash
# batch.sh BIN TAG SKIES... : the comparison set of research/g3-spectral.md (C0-C4, both imagers) per sky.
#   env WS=0 skips WSClean runs that already exist.
set -u
here=$(dirname "$(readlink -f "$0")")
O=/mnt/d/rang/outputs/20261106-g3-spectral
bin=$1; tag=$2; shift 2
st=$HOME/Github/rang/outputs/status/fp-g3.md
for sky in "$@"; do
  for cfg in C0 C1 C2 C3 C4; do
    sed -i "s|^- Now:.*|- Now ($(date +%H:%M)): $tag $sky $cfg|" "$st" 2>/dev/null
    bash "$here/run_g.sh" "$bin" "$tag" "$sky" "$cfg"
    if [ "${WS:-1}" = 1 ] || [ ! -f "$O/runs/wsclean/$sky-$cfg/time.txt" ]; then
      bash "$here/run_w.sh" "$sky" "$cfg"
    fi
  done
done
echo BATCH-DONE
