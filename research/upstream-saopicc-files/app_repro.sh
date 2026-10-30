#!/bin/bash
# Minimal reproduction: killMS 3.3.0 against DDFacet's AsyncProcessPool API. usage: app_repro.sh <venv>
V=$1
cd /tmp
echo "--- $V"
$V/bin/python -c "from importlib.metadata import version; print('DDFacet', version('DDFacet'), 'killMS', version('killMS') if __import__('importlib.util').util.find_spec('killMS') else '-')"
echo "1) _init_default"
$V/bin/python -c "from DDFacet.Other import AsyncProcessPool; AsyncProcessPool._init_default(); print('ok')" 2>&1 | grep -v mpi4py | tail -1
echo "2) module-level APP"
$V/bin/python -c "from DDFacet.Other.AsyncProcessPool import APP; print('ok', type(APP).__name__)" 2>&1 | grep -v mpi4py | tail -1
echo "3) init(affinity=...)"
$V/bin/python -c "import inspect; from DDFacet.Other import AsyncProcessPool as A; print(inspect.signature(A.init))" 2>&1 | grep -v mpi4py | tail -1
if $V/bin/python -c "import killMS" 2>/dev/null; then
  echo "4) killMS modules importing APP"
  for m in killMS.Weights.W_DiagBL killMS.Weights.W_AntFull killMS.InterpSols; do
    printf "%s: " $m; $V/bin/python -c "import $m; print('ok')" 2>&1 | grep -v mpi4py | tail -1
  done
fi
