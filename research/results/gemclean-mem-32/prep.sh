#!/bin/bash
# gemclean-mem-32 profile inputs on nash: main's gemclean binary, and own
# copies of E2-N's J1331+3030 (field 1) and target (field 3) rows.
set -eu
source ~/.rang-env.sh
R=/home/gijs/rang-data/outputs/gemclean-mem-32-20261121
W=~/Worktrees/rang/gemclean-mem-32
cd $W
s=$(date +%s)
cargo build -q --profile gemclean --bin gemclean --manifest-path core/Cargo.toml
cp core/target/gemclean/gemclean $R/gemclean-main
echo build $(( $(date +%s) - s )) s
~/Worktrees/rang/dl2-data/.venv-dl2/bin/python - <<PY
import time
from casacore.tables import table
t = table('/home/gijs/rang-data/outputs/e2n-20261116/e2n.ms', ack=False, readonly=True)
for fid, name in ((1, 'q'), (3, 'i')):
    s = time.time()
    sub = t.query('FIELD_ID==%d' % fid)
    sub.copy('/home/gijs/rang-data/outputs/gemclean-mem-32-20261121/%s.ms' % name, deep=True)
    sub.close()
    print(name, 'copied', round(time.time() - s), 's')
PY
