#!/bin/bash
# F7 seed spread (research/f7-flagger.md), validation only: D7's recipe and shards, seeds 1, 3;
# tau per seed, W4 off; screened with f7_gdrop_arms.py on ESO137 chunk 10.
O=$HOME/rang-data/outputs/f7-seeds-20261123
source $(dirname $0)/common.sh
one(){ s=$1; R=$O/s$s
  job train-s$s 12 64 $PY examples/f5_train.py $D7/shards/target $R/train-target/seed-$s --seed $s --steps 30000 --device cpu --balance-real || return 1
  job tau-s$s 8 40 $PY examples/f6_tau.py $R/tau-target --class target --train-dir $R/train-target --shards $D7/shards --level 40 --degree 1 --flags-from $FL --data-root $D --sarao-root $C || return 1
  $PY -c "
import json;m=json.load(open('$R/tau-target/method.json'));m['kappa']=None;m['method']='N5';m['note']='F7 seed spread: D7 recipe, seed $s, W4 off'
json.dump(m,open('$R/method.json','w'),indent=1)"
  job screen-s$s 8 16 $PY examples/f7_gdrop_arms.py $R/screen-eso-10.json --method $R/method.json --set eso:10 --data-root $D
}
one 1 & one 3 & wait; touch $O/seeds.done; log "seeds done"
