#!/bin/bash
# Build sdists of the licence branches from git archive and print the licence classifier in PKG-INFO.
set -u
B=~/Build/tmp/20261030-saopicc
mkdir -p $B/sdist
for r in DDFacet killMS; do
  rm -rf $B/sdist/$r; mkdir -p $B/sdist/$r/src
  git -C $B/$r archive licence-classifier-gplv2plus | tar -x -C $B/sdist/$r/src
  s=$(date +%s.%N)
  (cd $B/sdist/$r/src && uv build -q --sdist --index-url=https://pypi.org/simple -o $B/sdist/$r/dist > $B/sdist/$r/build.log 2>&1)
  echo "$r sdist rc=$? wall=$(echo "$(date +%s.%N)-$s" | bc) s"
  tar -xzOf $B/sdist/$r/dist/*.tar.gz --wildcards '*/PKG-INFO' | grep -i "^Classifier: License"
done
