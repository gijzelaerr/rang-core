#!/bin/bash
# Run one pass under the main checkout's heavy lock (WSL side).
#   bash e3_locked.sh LEG PASS CONFIG RAWDIR shared|exclusive
R=$(cd "$(dirname "$0")" && pwd)
LOCK=/mnt/c/Users/gijsm/Github/rang/tools/heavy_lock.py
if [ "$5" = exclusive ]; then
  python3 $LOCK run -- bash "$R/e3_pass.sh" "$1" "$2" "$3" "$4"
else
  python3 $LOCK run --slots 8 --mem 24 -- bash "$R/e3_pass.sh" "$1" "$2" "$3" "$4"
fi
rc=$?
RUN=/mnt/d/rang/outputs/e3-20261111-$1-$2
echo "rc=$rc"; cat "$RUN/wall.txt"; tail -25 "$RUN/caracal-stdout.log"
exit $rc
