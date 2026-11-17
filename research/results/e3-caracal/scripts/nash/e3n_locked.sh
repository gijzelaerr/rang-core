#!/bin/bash
# Run one nash pass under ~/Github/rang's heavy lock (research/e3-caracal.md 10.14).
#   bash e3n_locked.sh LEG PASS CONFIG RAWDIR shared|exclusive SLOTS MEM_GB CPULIST KILL_GIB
R=$(cd "$(dirname "$0")" && pwd)
LOCK=~/Github/rang/tools/heavy_lock.py
if [ "$5" = exclusive ]; then
  nice -n 19 ionice -c3 python3 $LOCK run -- bash "$R/e3n_pass.sh" "$1" "$2" "$3" "$4" "$8" "$9"
else
  nice -n 19 ionice -c3 python3 $LOCK run --slots "$6" --mem "$7" -- bash "$R/e3n_pass.sh" "$1" "$2" "$3" "$4" "$8" "$9"
fi
rc=$?
RUN=~/rang-data/outputs/e3-20261117-$1-$2
echo "rc=$rc"; cat "$RUN/wall.txt"; tail -25 "$RUN/caracal-stdout.log"
exit $rc
