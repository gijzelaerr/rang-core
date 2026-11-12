#!/bin/bash
# Run each probe twice plainly and with MALLOC_PERTURB_=85/170; cmp the outputs. Usage: run.sh <venv-python> <workdir> <case>...
PY=$1; W=$2; shift 2
P=$(dirname "$0")/probe.py
for c in "$@"; do
  for v in plain1 plain2 p85 p170; do
    case $v in p85) export MALLOC_PERTURB_=85;; p170) export MALLOC_PERTURB_=170;; *) unset MALLOC_PERTURB_;; esac
    echo "== $c $v"; "$PY" "$P" "$c" "$W/$c-$v" 2>&1 | tail -15
  done; unset MALLOC_PERTURB_
  for v in plain2 p85 p170; do
    (cd "$W/$c-plain1" && find . -type f ! -name table.lock | sort | while read f; do
      n=$(cmp -l "$f" "$W/$c-$v/$f" 2>/dev/null | wc -l); [ "$n" != 0 ] && echo "DIFF plain1 vs $v: $f $n bytes (size $(stat -c%s "$f"))"; done)
  done
done
