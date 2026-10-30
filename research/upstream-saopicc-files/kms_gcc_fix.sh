#!/bin/bash
# Make the GCC 15 fix branch in killMS, rebuild without workaround, import the extension.
set -u
export OMP_NUM_THREADS=2
B=~/Build/tmp/20261030-saopicc
cd $B/killMS
git checkout -q -B gcc15-incompatible-pointer-types master
sed -i '293s|^  PyArrayObject \*ObjGridIn,\*ObjWIn;|  PyObject *ObjGridIn,*ObjWIn;|' killMS/Gridder/Gridder.c
git diff
cd $B
T="/usr/bin/time -v"
uv venv -q -p 3.12 venv-kmsfix
echo "=== install-kms-fix (no CFLAGS)" >> logs/timings.txt
$T uv pip install -v --python venv-kmsfix/bin/python --index-url=https://pypi.org/simple --no-cache ./DDFacet ./killMS > logs/install-kms-fix.log 2>&1
echo "rc=$? $(grep -E 'Elapsed|Maximum resident' logs/install-kms-fix.log | tr -s ' ' | tr '\n' ' ')" >> logs/timings.txt
grep -c "Wincompatible-pointer-types" logs/install-kms-fix.log
cd /tmp
$B/venv-kmsfix/bin/python - <<'EOF'
import numpy as np
from killMS.cbuild.Gridder import _pyGridder
print("imported", _pyGridder.__file__)
print([n for n in dir(_pyGridder) if not n.startswith("_")])
EOF
# DDFacet 0.9.1 control venv with permissive flags (astlib also fails on GCC 15)
echo "=== install-ddf091 permissive CFLAGS" >> $B/logs/timings.txt
cd $B
CFLAGS="-Wno-error=incompatible-pointer-types -Wno-error=implicit-function-declaration -Wno-error=int-conversion -Wno-error=implicit-int" \
  $T uv pip install --python venv-ddf091/bin/python --index-url=https://pypi.org/simple "DDFacet==0.9.1" > logs/install-ddf091b.log 2>&1
echo "rc=$? $(grep -E 'Elapsed|Maximum resident' logs/install-ddf091b.log | tr -s ' ' | tr '\n' ' ')" >> logs/timings.txt
echo DONE2 >> logs/timings.txt
