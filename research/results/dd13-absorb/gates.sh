#!/usr/bin/env bash
set -u
R=D:/rang/outputs/dd13-20261127; J="bash $R/scripts/job.sh"; S=tools/oracles/dd13/dd13.py
$J reuse 1 2 -- $S reuse $R || exit 1
$J gateuv 2 12 -- $S gateuv $R &
$J gater 8 20 -- $S gater $R
wait
