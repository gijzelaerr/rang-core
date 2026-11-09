#!/usr/bin/env bash
# merge_check2.sh : after merging main a2450aa (G5 multiscale, C5 selfcal) into fp-g9-stokes. Under the heavy
# lock: build main a2450aa's gemclean and the merged one; criterion A against main a2450aa (D1,
# G3's five configurations and -pol I, -no-update-model-required); one IQUV smoke run (H1p Q2)
# against the frozen binary's output; -multiscale with several polarisations refused.
set -uo pipefail
W=$HOME/Worktrees/rang/fp-g9-stokes
S=$W/research/results/g9-stokes-scripts
O=/mnt/d/rang/outputs/g9-20261109-06
mkdir -p $O $O.code
cp -r $S $O.code/; git -C $W rev-parse HEAD > $O.code/commit; git -C $W status --porcelain > $O.code/status
flock ~/.rang-heavy.lock bash $S/main_ref.sh a2450aa
flock ~/.rang-heavy.lock bash $S/build.sh merge2
M=/mnt/d/rang/outputs/g9-bin/gemclean-main-a2450aa
G=/mnt/d/rang/outputs/g9-bin/gemclean-merge2
cp $M.provenance $G.provenance $O.code/
IDEXTRA=-no-update-model-required bash $S/identity.sh $O $M $G
source $S/cfg.sh
H=/mnt/d/rang/outputs/g9-20261107-03
ms=$H/data/H1p.ms
cfg_args Q2
d=$O/smoke/iquv-joined
rm -rf $d; mkdir -p $d
flock ~/.rang-heavy.lock /usr/bin/time -v -o $d/time.txt $G "${BASE[@]}" "${c[@]}" -no-update-model-required -name $d/g $ms > $d/log.txt 2>&1
echo "smoke iquv-joined rc=$?"
same=0; diff=0
for f in $H/runs/g/H1p-Q2/g-*.fits; do
  if cmp -s $f $d/$(basename $f); then same=$((same+1)); else diff=$((diff+1)); echo "  differs: $(basename $f)"; fi
done
echo "smoke iquv-joined: $same identical, $diff differ (against the frozen H1p-Q2)"
$G "${BASE[@]}" -pol IQUV -multiscale -no-update-model-required -name $O/smoke/refused $ms > $O/smoke/refused.txt 2>&1
echo "multiscale refusal rc=$? $(tail -1 $O/smoke/refused.txt)"
echo merge check 2 done
