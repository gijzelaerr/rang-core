#!/bin/bash
# Hogbom on the four-station slice geometry with synthetic DATA; 15 min cap per run.
# usage: hogbom_run.sh <label> <mode> <uvw_scale> [extra DDF args]   (mode: point | field | real)
set -u
export OMP_NUM_THREADS=2
S=/mnt/c/Users/gijsm/AppData/Local/Temp/claude/C--Users-gijsm-Github-rang/aa19215f-384c-42dc-a46d-e0ce70222d6d/scratchpad/u3
B=~/Build/tmp/20261030-saopicc
V=$B/venv-ddf100
L=$1; M=$2; SC=$3; shift 3
mkdir -p $B/hogbom/$L; cd $B/hogbom/$L
rm -rf s.ms; cp -r ~/Github/rang/outputs/luno-solve-20261029-02/work.ms s.ms
[ "$M" != real ] && $V/bin/python $S/hogbom_synth.py s.ms $M $SC
timeout 900 /usr/bin/time -f "WALL %e s RSS %M kB CPU %P" $V/bin/DDF.py --Data-MS s.ms --Data-ColName DATA \
  --Image-NPix 512 --Image-Cell 8 --Weight-Mode Briggs --Weight-Robust 0.5 \
  --Output-Name img --Parallel-NCPU 4 --Cache-Reset 1 --Log-Boring 1 --Selection-Field 1 \
  --Output-Mode Clean --Facets-NFacets 3 --Deconv-Mode Hogbom --Deconv-MaxMajorIter 3 --Deconv-PeakFactor 0.05 \
  --Output-Images dDpPmMrR "$@" > run.log 2>&1
echo "exit $?" >> run.log
grep -n "overflow\|Running major cycle\|Dirty image peak\|Reached\|Converged\|stopped\|WALL\|exit\|Error" run.log | cut -c1-200 | tail -20
