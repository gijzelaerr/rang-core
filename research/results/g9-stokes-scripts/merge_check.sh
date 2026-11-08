#!/usr/bin/env bash
# merge_check.sh : after merging main 3defaae (G6/W6) into fp-g9-stokes. Under the heavy lock:
# build main 3defaae's gemclean and the merged one; criterion A against main 3defaae (D1, G3's
# five configurations and -pol I); smoke tests of the merged binary against the frozen binary's
# held-out output: H1p Q2 (IQUV joined) byte for byte, and Q1 with -scans 1 (H1p has one scan, so
# the same images) and -unit-weights refused nowhere.
set -uo pipefail
W=$HOME/Worktrees/rang/fp-g9-stokes
S=$W/research/results/g9-stokes-scripts
O=/mnt/d/rang/outputs/g9-20261108-05
mkdir -p $O $O.code
cp -r $S $O.code/; git -C $W rev-parse HEAD > $O.code/commit; git -C $W status --porcelain > $O.code/status
flock ~/.rang-heavy.lock bash $S/main_ref.sh 3defaae
flock ~/.rang-heavy.lock bash $S/build.sh merge1
M=/mnt/d/rang/outputs/g9-bin/gemclean-main-3defaae
G=/mnt/d/rang/outputs/g9-bin/gemclean-merge1
cp $M.provenance $G.provenance $O.code/
IDEXTRA=-no-update-model-required bash $S/identity.sh $O $M $G
source $S/cfg.sh
H=/mnt/d/rang/outputs/g9-20261107-03
ms=$H/data/H1p.ms
smoke() {  # smoke NAME CFG EXTRA... : the merged binary, compared file by file with the frozen run
  local name=$1 cfg=$2; shift 2
  cfg_args "$cfg"
  local d=$O/smoke/$name
  rm -rf $d; mkdir -p $d
  flock ~/.rang-heavy.lock /usr/bin/time -v -o $d/time.txt $G "${BASE[@]}" "${c[@]}" "$@" -name $d/g $ms > $d/log.txt 2>&1
  echo "smoke $name rc=$?"
  local same=0 diff=0
  for f in $H/runs/g/H1p-$cfg/g-*.fits; do
    if cmp -s $f $d/$(basename $f); then same=$((same+1)); else diff=$((diff+1)); echo "  differs: $(basename $f)"; fi
  done
  echo "smoke $name: $same identical, $diff differ (against the frozen H1p-$cfg)"
}
smoke iquv-joined Q2 -no-update-model-required
smoke iquv-scans Q1 -no-update-model-required -scans 1
# Without -no-update-model-required several polarisations are refused (MODEL_DATA is Stokes I only).
$G "${BASE[@]}" -pol IQUV -niter 0 -name $O/smoke/refused $ms > $O/smoke/refused.txt 2>&1; echo "refusal rc=$? $(tail -1 $O/smoke/refused.txt)"
echo merge check done
