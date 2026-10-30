#!/bin/bash
# Count source files with/without a GPL header ("or (at your option) any later version").
# usage: count_headers.sh <repo-dir>
cd "$1" || exit 1
total=0; later=0; only2=0; none=0
nonelist=$(mktemp)
while IFS= read -r f; do
  total=$((total+1))
  if grep -qi "any later version" "$f"; then later=$((later+1))
  elif grep -qi "General Public License" "$f"; then only2=$((only2+1))
  else none=$((none+1)); echo "$f" >> "$nonelist"; fi
done < <(git ls-files '*.py' '*.c' '*.cc' '*.cpp' '*.h' '*.hpp' | sort)
echo "repo=$(basename "$PWD") head=$(git rev-parse --short HEAD) total=$total or_later=$later gpl_other=$only2 no_header=$none"
echo "-- files without a GPL header (first 25):"; head -25 "$nonelist"
echo "-- empty __init__.py among them: $(while read -r f; do [ ! -s "$f" ] && echo "$f"; done < "$nonelist" | wc -l)"
rm -f "$nonelist"
