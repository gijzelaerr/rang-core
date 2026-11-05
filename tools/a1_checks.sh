#!/usr/bin/env bash
# Usage: bash tools/a1_checks.sh RUN_DIR VERSION   (research/a1-simtruth.md, section 5)
# Runs checks 1 to 5 for one version (small or full): CASA listobs, the truth
# tables, applycal with parang False and True, and the host comparisons.
# RUN_DIR holds VERSION/ (MS, twin, truth); results go to RUN_DIR/casa-VERSION/.
set -euo pipefail
run=$(realpath "$1")
v=$2
here=$(cd "$(dirname "$0")/.." && pwd)
py=$here/.venv/bin/python
c=$run/casa-$v
mkdir -p "$c"
step() { echo "## $*"; }
step listobs
bash "$here/tools/a1_casa.sh" "$run" listobs "/run/$v/a1-$v.ms" "/run/casa-$v/listobs-$v.txt" > "$c/listobs.log" 2>&1
step tables
bash "$here/tools/a1_casa.sh" "$run" tables "/run/$v/a1-$v-twin.ms" "/run/$v/truth.npz" "/run/$v/truth.json" "/run/casa-$v" > "$c/tables.log" 2>&1
for parang in False True; do
  step "apply parang=$parang"
  bash "$here/tools/a1_casa.sh" "$run" apply "/run/casa-$v" "$parang" "/run/casa-$v/export-parang$parang.npz" > "$c/apply-$parang.log" 2>&1
done
step "roundtrip parang=False"
"$py" "$here/examples/a1_simtruth_check.py" roundtrip "$run/$v" "$c/export-parangFalse.npz" "$run/$v/a1-$v-twin.ms" "$c/check-roundtrip.json" > "$c/check-roundtrip.log" 2>&1 || true
step "roundtrip parang=True"
"$py" "$here/examples/a1_simtruth_check.py" roundtrip "$run/$v" "$c/export-parangTrue.npz" "$run/$v/a1-$v-twin.ms" "$c/check-parang.json" --parang > "$c/check-parang.log" 2>&1 || true
step noise
"$py" "$here/examples/a1_simtruth_check.py" noise "$run/$v" "$run/$v/a1-$v.ms" "$run/$v/a1-$v-twin.ms" "$c/check-noise.json" > "$c/check-noise.log" 2>&1 || true
step done
