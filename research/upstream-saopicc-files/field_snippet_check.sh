#!/bin/bash
# Check the issue #75 conversion snippet: field-0 MS images; after the snippet it fails as reported.
set -u
export OMP_NUM_THREADS=2
B=~/Build/tmp/20261030-saopicc; V=$B/venv-ddf100
mkdir -p $B/field/snippet; cd $B/field/snippet
rm -rf f0.ms; cp -r ~/Github/rang/outputs/luno-solve-20261029-02/work.ms f0.ms
$V/bin/python - <<'EOF'
from casacore.tables import table
t = table("f0.ms", readonly=False, ack=False); t.putcol("FIELD_ID", 0 * t.getcol("FIELD_ID")); t.close()
f = table("f0.ms/FIELD", readonly=False, ack=False); f.removerows(list(range(1, f.nrows()))); print("FIELD rows", f.nrows()); f.close()
EOF
run() { $V/bin/DDF.py --Data-MS f0.ms --Data-ColName DATA --Output-Mode Dirty --Image-NPix 128 --Image-Cell 30 --Output-Name img --Parallel-NCPU 2 --Cache-Reset 1 --Log-Boring 1 > $1.log 2>&1; echo "$1 exit $?"; grep -m2 "no rows\|valid Measurement" $1.log | cut -c1-200; }
run single-field-0
# the snippet from the issue
$V/bin/python - <<'EOF'
from casacore.tables import table
f = table("f0.ms/FIELD", readonly=False, ack=False); f.copyrows(f, startrowin=0, nrow=1); print("FIELD rows", f.nrows()); f.close()
t = table("f0.ms", readonly=False, ack=False); t.putcol("FIELD_ID", t.getcol("FIELD_ID") + 1); t.close()
EOF
run after-snippet
