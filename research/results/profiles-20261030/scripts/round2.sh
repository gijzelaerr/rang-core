#!/usr/bin/env bash
# S1 round 2: solver convergence curve, perf-stat counts of build variants,
# coverage of the live chains, pytest durations. Usage: bash round2.sh
set -uo pipefail
cd ~/Worktrees/rang/simplification-review
export PATH=$HOME/.cargo/bin:$PATH
export RUSTUP_TOOLCHAIN=1.93
py=.venv/bin/python
S=/mnt/c/Users/gijsm/AppData/Local/Temp/claude/C--Users-gijsm-Github-rang/aa19215f-384c-42dc-a46d-e0ce70222d6d/scratchpad/s1
B=$HOME/Build/tmp/20261030-rang-s1
out=outputs/simplification-review-20261030-05
mkdir -p $out
echo "## convergence $(cut -d' ' -f1-3 /proc/loadavg)"
/usr/bin/time -f 'convergence %e s %M KB' env OPENBLAS_NUM_THREADS=1 $py $S/convergence.py outputs/core-k-20261030-01/fetch $out/convergence.json > $out/convergence.log 2>&1
tail -1 $out/convergence.log
echo "## perf stat variants $(cut -d' ' -f1-3 /proc/loadavg)"
for v in default lto v3; do
  for i in 1 2; do
    perf stat -x, -e instructions:u,cycles:u,task-clock -o $out/stat-$v-$i.txt -- env OPENBLAS_NUM_THREADS=1 RANG_CORE_LIB=$B/$v/release/librang_core.so $py $S/profile_campaign.py outputs/core-k-20261030-01/fetch $out/stat-$v-$i --images original --no-reference > /dev/null 2>&1
  done
done
grep -h "instructions\|cycles\|task-clock" $out/stat-*.txt | head -30
echo "## pytest durations $(cut -d' ' -f1-3 /proc/loadavg)"
/usr/bin/time -f 'pytest %e s %M KB %P' $py -m pytest -q --durations=0 -p no:cacheprovider > $out/pytest-durations.txt 2>&1
tail -3 $out/pytest-durations.txt
echo "## coverage $(cut -d' ' -f1-3 /proc/loadavg)"
bash $S/coverage.sh outputs/simplification-review-20261030-06 > /tmp/s1-coverage.log 2>&1
tail -5 /tmp/s1-coverage.log
echo "## done $(cut -d' ' -f1-3 /proc/loadavg)"
