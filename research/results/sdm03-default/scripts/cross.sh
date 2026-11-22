#!/bin/bash
# post hoc (not gating): each reserve scan arms models scored on the other scan state
source ~/Build/tmp/20261118-sdm03/env.sh
for pair in "MAIN_6 MAIN_1" "MAIN_1 MAIN_6"; do
  set -- $pair; on=$1; from=$2; st=$OUT/cross-$from-on-$on; mkdir -p $st
  for f in $OUT/r-$on/*; do b=$(basename $f); case $b in family2|img) continue;; esac; [ -e $st/$b ] || ln -s $f $st/$b; done
  $PY $SD real --group MAIN_4 -- score $(for a in A0 SDa Sa Sm SDm03 W-SDa; do echo $a=$OUT/r-$from/img/$a/image; done) --out $st --held $HELD
done
