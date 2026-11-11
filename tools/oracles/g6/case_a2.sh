#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# G6 criterion 5 (research/g6-predict.md): rang-core image with write_model
# against the binary's after-clean column, case A without model columns.
#   bash case_a2.sh OUTDIR GEMCLEAN
set -eu
O=$1; GEM=$2
source "$(dirname "$(readlink -f "$0")")/lib.sh"
A1=$D/fp-a1-20261106-simtruth/small/a1-small.ms
mkdir -p "$O"; snapshot
for x in core bin; do
  rm -rf "$O/$x.ms"; cp -r "$A1" "$O/$x.ms"
  casa_py /g6/prep.py "$O/$x.ms" --flags 3
done
casa_py /g6/compare.py "$O/core.ms" --hashes "$O/core-before.json"
cat > "$O/config.yaml" <<EOF
schema: rang-config
version: 1
fields:
  target: [SIM-TARGET]
image:
  gemclean: $GEM
  column: DATA
  size: [512, 512]
  scale: 2asec
  weight: briggs
  robust: 0.0
  niter: 300
  threads: 4
  write_model: true
run:
  stages: [image]
EOF
(cd "$O" && rang_py -m rang.core_cli image config.yaml core.ms --run-dir "$O/run" > "$O/core.log" 2>&1)
# The binary with the argv rang-core gave it, writing the model itself.
argv=$(python3 -c "import json,sys; s=json.load(open('$O/run/image/summary.json')); print(' '.join(a for a in s['images'][0]['argv'][1:-1] if a != '-no-update-model-required'))")
mkdir -p "$O/bin-img"
argv=${argv//$O\/run\/image\/SIM-TARGET/$O\/bin-img}
gem a2 $argv "$O/bin.ms" > "$O/bin.log" 2>&1
casa_py /g6/compare.py "$O/core.ms" --g MODEL_DATA --w MODEL_DATA --field 3 --before "$O/core-before.json" --out "$O/core-self.json" > /dev/null
python3 - "$O" <<'PY'
import hashlib, json, pathlib, subprocess, sys
o = pathlib.Path(sys.argv[1])
s = json.load(open(o / "run/image/summary.json"))["images"][0]
print("model summary", s["model"])
def files(d):
    return {p.name.split("-", 1)[1]: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.glob("*.fits"))}
a, b = files(o / "run/image/SIM-TARGET"), files(o / "bin-img")
print("fits equal", a == b, sorted(a))
PY
rang_py "$HERE/rang_hash.py" "$O/core.ms" MODEL_DATA > "$O/core-hash.json"
rang_py "$HERE/rang_hash.py" "$O/bin.ms" MODEL_DATA > "$O/bin-hash.json"
python3 - "$O" <<'PY'
import json, sys
o = sys.argv[1]
a = json.load(open(f"{o}/core-hash.json")); b = json.load(open(f"{o}/bin-hash.json"))
c = json.load(open(f"{o}/core-self.json"))
print("criterion_5", a["sha256_rang"] == b["sha256_rang"], "other columns changed", c["other_columns_changed"], c["desc_g"], c["dminfo_g"])
PY
