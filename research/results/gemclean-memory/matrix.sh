#!/bin/bash
# The scaling matrix of research/gemclean-memory.md step 1 (Git Bash; the
# caller wraps it in the main checkout's heavy_lock.py).
#   matrix.sh GEMCLEAN MS OUTDIR   -> OUTDIR/matrix.jsonl
set -u
G=$1; MS=$2; O=$3; PY=${PY:-C:/Users/gijsm/Github/rang/.venv/Scripts/python.exe}
P=$(cd "$(dirname "$0")" && pwd)/probe.py
mkdir -p "$O"
for pol in I IQUV; do
  for n in 256 512 1024 2048; do
    for c in 1 2 4 8; do
      "$PY" "$P" run "$G" "$MS" "$O" $n $c $pol -j 4 >> "$O/matrix.jsonl"
    done
  done
done
