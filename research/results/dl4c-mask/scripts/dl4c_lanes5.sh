#!/bin/bash
# DL4c amendment 3: images under dl4c2.sh (-niter 10000000), one lane, gated at three jobs (coordinator, 2026-11-21) (args: CASE-ARM ...).
R=$HOME/rang-data/outputs/dl4c-mask-20261120
D=$(dirname "$0")/dl4c3.sh
for ca in "$@"; do bash $D image "${ca%-*}" "${ca#*-}"; done >> $R/logs/lanes4.log 2>&1
echo "$(date -Is) lanes4 done: $*" >> $R/logs/driver.log
