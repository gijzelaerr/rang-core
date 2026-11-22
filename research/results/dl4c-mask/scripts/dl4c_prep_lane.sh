#!/bin/bash
# DL4c: the prepare steps after the first lane's failure (prep dir pre-made); gated.
R=$HOME/rang-data/outputs/dl4c-mask-20261120
D=$(dirname "$0")/dl4c.sh
for c in T1 T2 T3; do bash $D prep $c; done > $R/logs/prep-lane.log 2>&1
