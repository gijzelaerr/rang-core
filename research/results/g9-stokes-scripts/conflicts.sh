#!/usr/bin/env bash
# conflicts.sh FILE... : print the conflict hunks of each file with line numbers (merge helper).
for f in "$@"; do
  echo "##### $f"
  awk '/^<<<<<<< /{p=1} p{print NR": "$0} /^>>>>>>> /{p=0}' "$f" | cut -c1-220
done
