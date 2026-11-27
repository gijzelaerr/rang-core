#!/usr/bin/env bash
# lane.sh ARM... : the arms' loops one after another (8 slots, 20 GB each)
R=D:/rang/outputs/dd13-20261127
for a in "$@"; do bash $R/scripts/job.sh loop-$a 8 20 -- tools/oracles/dd13/dd13.py loop $R $a; done
