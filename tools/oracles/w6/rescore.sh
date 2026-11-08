#!/usr/bin/env bash
# W6: the image comparisons of run.sh again on its outputs (no imager rerun).
#   bash rescore.sh OUTDIR dev|held
O=$1; SET=$2
HERE=$(dirname "$(readlink -f "$0")")
P="$HOME/Worktrees/rang/fp-g6-predict/.venv/bin/python $HERE/fits_cmp.py"
row() { echo "{\"case\": \"$1\", \"check\": \"$2\", \"result\": $($P "$3" "$4" "$5")}"; }
sc() { row "$1" 1a same "$O/$1/g-full/g" "$O/$1/g-split/g"; row "$1" 1b bounds "$O/$1/g0/g" "$O/$1/w0/w"; }
unit() {
  row "$1" 2a same "$O/$1/g-unit/g" "$O/$1/g-u1/g"
  row "$1" 2b same "$O/$1/g-unit/g" "$O/$1/g-plain/g"
  row "$1" 2c bounds "$O/$1/g0/g" "$O/$1/w0/w"
}
{
  case $SET in
    dev)
      sc SC-d; unit U-d
      row WU 3a same "$O/wu/g-wu/g" "$O/wu/g-nw/g"
      row WU 3b bounds "$O/wu/g0/g" "$O/wu/w0/w"
      row WU 3c same "$O/wu/run-wu/image/SIM-TARGET/image" "$O/wu/run-nw/image/SIM-TARGET/image"
      ;;
    held)
      sc SC-h1; sc SC-h2; unit U-h
      row E2 4b same "$O/e2/run/image/SIM-TARGET/image" "$O/e2/g-split/image"
      ;;
  esac
} | tee "$O/results-scored.jsonl"
