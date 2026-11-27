#!/usr/bin/env bash
R=D:/rang/outputs/dd13-20261127; J="bash $R/scripts/job.sh"; S=tools/oracles/dd13/dd13.py
$J diag 2 14 -- $S diag $R || exit 1
$J score 1 2 -- $S score $R
