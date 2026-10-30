#!/bin/bash
# usage: repro.sh <venv>  -- runs the echo recipe with that venv's stimela
set -u
V=$1
D=$(mktemp -d)
cp "$(dirname "$0")/echo.yml" "$D/"
cd "$D"
"$V/bin/python" -c "import sys, importlib.metadata as m; print('python', sys.version.split()[0], 'stimela', m.version('stimela'))"
/usr/bin/time -f "wall %e s, maxrss %M KB" "$V/bin/stimela" run echo.yml hello 2>&1 | grep -v "^\s*$" | tail -8
echo "exit ${PIPESTATUS[0]}"
rm -rf "$D"
