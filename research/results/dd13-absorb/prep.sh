#!/usr/bin/env bash
set -u
R=D:/rang/outputs/dd13-20261127; J="bash $R/scripts/job.sh"
$J insertO 2 10 -- tools/oracles/dd8/dd8.py insert $R || exit 1
$J setup 1 2 -- tools/oracles/dd12/dd12.py setup $R || exit 1
$J psf-O 4 10 -- tools/oracles/dd12/dd12.py psf $R O || exit 1
