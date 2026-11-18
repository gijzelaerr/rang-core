#!/bin/bash
# Mirror nash's driver status into the Windows main checkout every 10 min (under 15 lines).
DST=/c/Users/gijsm/Github/rang/outputs/status/sdm03-default.md
while true; do
  ssh -o BatchMode=yes -o ConnectTimeout=20 gijs@nash.ru.ac.za 'cat ~/rang-data/outputs/sdm03-default-20261118/status.md' > $DST.tmp 2>/dev/null && [ -s $DST.tmp ] && head -14 $DST.tmp > $DST
  rm -f $DST.tmp
  sleep 600
done
