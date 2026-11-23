#!/bin/bash
# F7 D9 (research/f7-flagger.md), validation only: dead-zone levels 60 (D9a) and 70 (D9b), each
# with D7's recipe re-sharded at its level, seed 2, tau per arm, W4 off, then the screen on
# ESO137 chunk 10. Uses f7-draft's own venv (kernel e9090157 or later). Bookings from D3's
# measured peaks: target train shards 165 GB (book 180), validation 21 GB (32), trainer 56 GB (64).
O=$HOME/rang-data/outputs/f7-d9-20261123
PY=$HOME/Worktrees/rang/f7-draft/.venv/bin/python
source $(dirname $0)/common.sh
[ -f $HOME/Worktrees/rang/f7-draft/outputs/venv.done ] || { log "no venv"; exit 1; }
job build 8 16 env CARGO_BUILD_JOBS=8 .venv/bin/maturin develop --release -q || exit 1
job test 4 8 $PY -m pytest -q -p no:cacheprovider tests/test_f5_flag.py || exit 1
arm(){ a=$1; L=$2; R=$HOME/rang-data/outputs/f7-$a-20261123; mkdir -p $R
  SA="--class target --level $L --degree 1 --flags-from $FL --data-root $D --sarao-root $C --ao-sif $SIF"
  job $a-shards-validation 8 32 $PY examples/f6_shards.py $R/shards --role validation $SA || return 1
  job $a-shards-train 12 180 $PY examples/f6_shards.py $R/shards --role train $SA || return 1
  job $a-shards-eso-extra 12 180 $PY examples/f6_shards.py $R/shards --role train $SA --sources eso --f4-realisations 8 || return 1
  log "$a train shards: $(ls $R/shards/target/train/*.npz | wc -l) ($(ls $R/shards/target/train/eso-*.npz | wc -l) ESO137)"
  job $a-train 12 64 $PY examples/f5_train.py $R/shards/target $R/train-target/seed-2 --seed 2 --steps 30000 --device cpu --balance-real || return 1
  job $a-tau 8 40 $PY examples/f6_tau.py $R/tau-target --class target --train-dir $R/train-target --shards $R/shards --level $L --degree 1 --flags-from $FL --data-root $D --sarao-root $C || return 1
  $PY -c "
import json;m=json.load(open('$R/tau-target/method.json'));m['kappa']=None;m['method']='N5';m['note']='F7 $a: level $L, W4 off'
json.dump(m,open('$R/method.json','w'),indent=1)"
  job $a-screen 8 16 $PY examples/f7_gdrop_arms.py $R/screen-eso-10.json --method $R/method.json --set eso:10 --data-root $D
}
arm d9a 60 & sleep 60; arm d9b 70 & wait; touch $O/d9.done; log "D9 done"
