#!/usr/bin/env bash
set -u
R=D:/rang/outputs/dd14-20261127; J="bash $R/scripts/job.sh"; S=tools/oracles/dd14/dd14.py
$J beam 1 4 -- $S beam $R || exit 1
$J apertures 2 6 -- $S apertures $R || exit 1
$J gateo 2 16 -- $S gateo $R || exit 1
$J insert 2 16 -- $S insert $R || exit 1
$J psf 4 10 -- $S psf $R || exit 1
$J gater 4 16 -- $S gater $R || exit 1
echo PREP_OK >> $R/times.log
