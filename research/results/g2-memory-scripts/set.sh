#!/usr/bin/env bash
# set.sh BIN TAG [SKIES] : the identity set (seven skies in both forms, then the 256-channel pilot)
O=/mnt/d/rang/outputs/20261106-g2-memory
bin=$1; tag=$2; skies=${3:-"s1 s2 s3 h1 h2 h3 h4"}
for form in def coarse; do
  for s in $skies; do
    bash $O/status.sh "set $tag: $s $form" "${NEXT:-finish the set}"
    bash $O/run1.sh "$bin" "$tag" "$s" "$form"
  done
done
if [ "${PILOT:-1}" = 1 ]; then
  bash $O/status.sh "set $tag: p256 def" "${NEXT:-finish the set}"
  WATCH_GB=24 bash $O/run1.sh "$bin" "$tag" p256 def
fi
echo SET-DONE $tag
