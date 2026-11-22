#!/bin/bash
# DL4c step 5: masked images for the cases whose masks are committed (args: CASE-ARM ...), gated in dl4c.sh.
R=$HOME/rang-data/outputs/dl4c-mask-20261120
D=$(dirname "$0")/dl4c.sh
for ca in "$@"; do bash $D image "${ca%-*}" "${ca#*-}"; done >> $R/logs/lanes3.log 2>&1
echo "$(date -Is) lanes3 done: $*" >> $R/logs/driver.log
