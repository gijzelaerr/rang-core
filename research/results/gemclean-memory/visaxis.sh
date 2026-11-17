#!/bin/bash
# The visibility axis of research/gemclean-memory.md step 1 (Git Bash; the
# caller wraps it in the main checkout's heavy_lock.py): IQUV joined, 8
# joined channels, 1024^2, -auto-mask 5, on 37,200 / 74,400 / 148,800 rows
# of 256 channels.   visaxis.sh GEMCLEAN DIR OUTDIR -> OUTDIR/visaxis.jsonl
set -u
G=$1; D=$2; O=$3; PY=${PY:-C:/Users/gijsm/Github/rang/.venv/Scripts/python.exe}
P=$(cd "$(dirname "$0")" && pwd)/probe.py
mkdir -p "$O"
for t in 75 150 300; do
  "$PY" "$P" run "$G" "$D/v32-t$t.ms" "$O/t$t" 1024 8 IQUV -auto-mask 5 -j 4 \
    | sed "s/^{/{\"ntime\": $t, /" >> "$O/visaxis.jsonl"
done
