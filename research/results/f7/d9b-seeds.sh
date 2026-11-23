#!/bin/bash
# F7 D9b freeze rule (research/f7-flagger.md): seeds 1 and 3 on D9b's shards (level 70, D7 recipe),
# then f6_tau over seeds 1-3 (median by validation loss), method W4 off, the ESO137 screen on the
# selected seed. Validation only; the held-out read waits for the selected seed's complete scorer.
O=$HOME/rang-data/outputs/f7-d9b-20261123
PY=$HOME/Worktrees/rang/f7-draft/.venv/bin/python
source $(dirname $0)/common.sh
SA="--class target --level 70 --degree 1 --flags-from $FL --data-root $D --sarao-root $C"
for s in 1 3; do job d9b-train-s$s 12 64 $PY examples/f5_train.py $O/shards/target $O/train-target/seed-$s --seed $s --steps 30000 --device cpu --balance-real & sleep 30; done
wait
[ -f $O/d9b-train-s1.done ] && [ -f $O/d9b-train-s3.done ] || { log "d9b seeds FAILED"; exit 1; }
job d9b-tau3 8 40 $PY examples/f6_tau.py $O/tau3-target --train-dir $O/train-target --shards $O/shards $SA || exit 1
$PY -c "
import json;m=json.load(open('$O/tau3-target/method.json'));m['kappa']=None;m['method']='N5';m['note']='F7 D9b freeze candidate: level 70, median seed, W4 off'
json.dump(m,open('$O/method3.json','w'),indent=1)"
log "d9b selected: $($PY -c "import json;m=json.load(open('$O/method3.json'));print(m['seed'],m['tau'])")"
job d9b-screen3 8 16 $PY examples/f7_gdrop_arms.py $O/screen3-eso-10.json --method $O/method3.json --set eso:10 --data-root $D
touch $O/seeds.done
