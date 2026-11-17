#!/bin/bash
# Pull the 17 stimela cab images of versions.json into apptainer SIF files, by digest,
# under the names Stimela 1.8.3 looks for (stimela_<base>_<tag>.sif), on nash.
#   bash e3n_pull.sh VERSIONS.json SIFDIR
# research/e3-caracal.md 10.14 (nash deviation). Run under nice/ionice.
set -u
V=$1; D=$2
mkdir -p "$D"; export APPTAINER_CACHEDIR=~/Build/cache/apptainer
python3 "$(dirname "$0")/e3n_pull_list.py" "$V" > "$D/pull-list.txt" || exit 1
while read -r name url; do
  if [ -s "$D/$name" ]; then echo "have $name"; continue; fi
  echo "pull $name $url $(date -Is)"
  apptainer pull --name "$D/$name" "$url" || { echo "FAIL $name"; exit 1; }
done < "$D/pull-list.txt"
ls -l "$D"/*.sif
