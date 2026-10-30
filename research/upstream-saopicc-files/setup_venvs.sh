#!/bin/bash
# Build the venvs for the saopicc checks. Log timings with /usr/bin/time -v.
set -u
export OMP_NUM_THREADS=2
B=~/Build/tmp/20261030-saopicc
cd $B
mkdir -p logs
T="/usr/bin/time -v"
run() { # name, cmd...
  local name=$1; shift
  echo "=== $name: $*" >> logs/timings.txt
  $T "$@" > logs/$name.log 2>&1
  local rc=$?
  echo "rc=$rc $(grep -E 'Elapsed|Maximum resident' logs/$name.log | tr -s ' ' | tr '\n' ' ')" >> logs/timings.txt
  return $rc
}
IDX=--index-url=https://pypi.org/simple
uv venv -q -p 3.12 venv-ddf100
uv venv -q -p 3.12 venv-ddf091
run install-ddf100 uv pip install --python venv-ddf100/bin/python $IDX ./DDFacet
run install-ddf091 uv pip install --python venv-ddf091/bin/python $IDX "DDFacet==0.9.1"
# killMS master on GCC 15, no workaround: expected to fail
run install-kms-plain uv pip install --python venv-ddf100/bin/python $IDX --no-deps --no-cache --reinstall ./killMS
# with the workaround and verbose build output to collect all promoted warnings
CFLAGS=-Wno-error=incompatible-pointer-types run install-kms-workaround uv pip install -v --python venv-ddf100/bin/python $IDX --no-deps --no-cache --reinstall ./killMS
echo DONE >> logs/timings.txt
