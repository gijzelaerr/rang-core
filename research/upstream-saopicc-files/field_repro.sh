#!/bin/bash
# DDFacet default --Selection-Field 0 on an MS whose rows are all FIELD_ID 1.
# usage: field_repro.sh <venv> <label>
set -u
export OMP_NUM_THREADS=2
B=~/Build/tmp/20261030-saopicc
V=$1; L=$2
mkdir -p $B/field/$L; cd $B/field/$L
rm -rf f1.ms; cp -r ~/Github/rang/outputs/luno-solve-20261029-02/work.ms f1.ms
$V/bin/python - <<'EOF'
from casacore.tables import table, taql
t = table("f1.ms", ack=False)
print("rows", t.nrows(), "FIELD_ID/DATA_DESC_ID pairs", sorted(set(zip(t.getcol("FIELD_ID"), t.getcol("DATA_DESC_ID")))))
print("FIELD rows", table("f1.ms/FIELD", ack=False).nrows())
EOF
/usr/bin/time -f "WALL %e s RSS %M kB" $V/bin/DDF.py --Data-MS f1.ms --Data-ColName DATA --Output-Mode Dirty \
  --Image-NPix 128 --Image-Cell 30 --Output-Name img --Parallel-NCPU 2 --Cache-Reset 1 --Log-Boring 1 > run.log 2>&1
echo "exit $?" >> run.log
grep -n "no rows\|valid Measurement\|Error\|WALL\|exit" run.log | cut -c1-260
