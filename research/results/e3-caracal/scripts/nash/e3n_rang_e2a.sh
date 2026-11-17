#!/bin/bash
# Rang's E2-A arm timed on nash, E3-A's cost comparator (research/e3-caracal.md 10.14):
# the frozen configuration e2a-rerun.yaml (blob f8949999, as on Windows, e2-acceptance 9.5-9.7),
# from a Linux wheel of b2d80dc (e3n_rang_wheel.sh), on a private copy of E3-A's e2a.ms,
# pinned to the timed pass's 16 CPUs on node 0, under the exclusive heavy lock.
#   bash e3n_rang_e2a.sh SRC_MS OUTDIR WHEELDIR
set -u
SRC=$1; O=$2; WD=$3
R=~/Github/rang
S=$R/research/results/e2-acceptance-scripts
WPY=$WD/venv/bin/python
CPUS=0,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30
mkdir -p "$O"; L=$O/e2a-run.log
echo "$(date -Is) config blob $(git -C $R hash-object $S/e2a-rerun.yaml) main $(git -C $R rev-parse --short HEAD)" >> $L
if [ ! -d "$O/e2a.ms" ]; then
  echo "COPY START $(date -Is)" >> $L
  nice -n 19 ionice -c3 python3 $R/tools/heavy_lock.py run --slots 1 --mem 2 -- cp -a "$SRC" "$O/e2a.ms" || exit 1
  echo "COPY END $(date -Is)" >> $L
  "$R/.venv/bin/python" $S/e2_flaghash.py "$O/e2a.ms" "$O/flaghash-copy.json" >> $L 2>&1
fi
cd $R || exit 2
python3 $R/tools/heavy_lock.py status > "$O/lock-status-queue.txt" 2>&1
echo "QUEUE $(date -Is) exclusive load $(cut -d' ' -f1-3 /proc/loadavg)" >> $L
nice -n 19 ionice -c3 python3 $R/tools/heavy_lock.py run -- bash -c "
  python3 $R/tools/heavy_lock.py status > '$O/lock-status-start.txt' 2>&1
  echo \"START \$(date -Is) load \$(cut -d' ' -f1-3 /proc/loadavg) cpus $CPUS\" >> '$L'
  '$WPY' $S/e2_diskguard.py --path $HOME --min-free-gib 1000 --log '$O/e2a-guard.jsonl' -- \
    '$WPY' $S/e2_timed.py '$O/e2a-timed.json' -- \
    numactl --physcpubind=$CPUS '$WPY' -m rang.core_cli run $S/e2a-rerun.yaml '$O/e2a.ms'
  rc=\$?
  echo \"END \$(date -Is) rc=\$rc load \$(cut -d' ' -f1-3 /proc/loadavg)\" >> '$L'
  exit \$rc" >> $L 2>&1
