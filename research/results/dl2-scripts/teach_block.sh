#!/bin/bash
# DL2: the three flag teachers on one (non-held-out) block, after its conversion ended
# (research/dl2-data.md section 6, amendment 4). Per scan: the private copy under a
# 1-slot booking (I/O only), then the teachers under a THREADS-slot booking.
# Usage: teach_block.sh CBID [THREADS] [K/N]  (K/N: only the scans at positions = K mod N,
# so N jobs on one block take disjoint scans; amendment 7)
R=~/rang-data/outputs/dl2-data-20261119
S=~/Worktrees/rang/dl2-data/research/results/dl2-scripts
PY=~/Worktrees/rang/dl2-data/.venv-dl2/bin/python
LOCK="python3 $HOME/Github/rang/tools/heavy_lock.py run"
T=${2:-8}
STREAM=${3:-0/1}
K=${STREAM%/*}; NS=${STREAM#*/}
source ~/.rang-env.sh
cd $R
until grep -q "END .* $1 rc" logs/blocks.log; do sleep 60; done
echo "START $(date -u +%FT%TZ) teach $1 stream $STREAM threads $T free $(df -BG --output=avail $R | tail -1)" >> logs/teach.log
rc=0
for n in $($PY -c "import json,sys;s=[x['scan'] for x in json.load(open(sys.argv[1]))['scans'] if 'ms_hash' in x]; k,n=int(sys.argv[2]),int(sys.argv[3]); print(' '.join(str(v) for i,v in enumerate(s) if i % n == k))" manifests/$1.json $K $NS); do
  if [ -e done/rang/$1/$n.done ] && [ -e done/tricolour/$1/$n.done ] && [ -e done/aoflagger/$1/$n.done ]; then continue; fi
  $LOCK --slots 1 --mem 4 -- nice -n 19 ionice -c3 $PY -u $S/dl2_teach.py $R rang,tricolour,aoflagger $1 --scans $n --copy-only >> logs/teach-$1-s$K.log 2>&1 || { rc=$?; break; }
  /usr/bin/time -f "scan $n wall %e s" $LOCK --slots $T --mem $((6*T)) -- nice -n 19 ionice -c3 $PY -u $S/dl2_teach.py $R rang,tricolour,aoflagger $1 --scans $n --threads $T >> logs/teach-$1-s$K.log 2>&1 || { rc=$?; break; }
done
echo "END $(date -u +%FT%TZ) teach $1 stream $STREAM rc $rc free $(df -BG --output=avail $R | tail -1)" >> logs/teach.log
