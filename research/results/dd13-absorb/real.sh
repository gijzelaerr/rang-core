#!/usr/bin/env bash
# section 7: the frozen rule calls for the real reading of the best arm (QP12)
R=D:/rang/outputs/dd13-20261127; J="bash $R/scripts/job.sh"
$J psf-real 4 10 -- tools/oracles/dd12/dd12.py psf $R real || exit 1
$J loop-R-QP12 8 20 -- tools/oracles/dd13/dd13.py loop $R R-QP12
