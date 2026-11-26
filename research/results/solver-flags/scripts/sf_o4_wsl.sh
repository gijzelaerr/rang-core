#!/bin/bash
# solver-flags O4 (A1's flux calibrator) in WSL on glacier: QuartiCal 0.2.7 in a uv venv,
# the MS scratch on WSL ext4; the cut copied to D: for rang's side (Windows).
set -euo pipefail
B=$HOME/Build/tmp/20261125-solver-flags
QC=$B/venv-qc027
S=/mnt/c/Users/gijsm/Worktrees/rang/solver-flags/research/results/solver-flags/scripts
SRC=/mnt/d/rang/outputs/solver-flags-20261125/a1/a1-M0.ms
D=/mnt/d/rang/outputs/solver-flags-20261125/oracle-a1
mkdir -p "$B" "$D"
if [ ! -x "$QC/bin/python" ]; then
  uv venv -q -p 3.12 "$QC"
  uv pip install -q -p "$QC/bin/python" --index-url https://pypi.org/simple "quartical==0.2.7"
fi
"$QC/bin/python" -c "import importlib.metadata as m; print('quartical', m.version('quartical'))"
ver=$(grep -o "^rang_calibrate_[0-9TZ]*" "$SRC.flagversions/FLAG_VERSION_LIST" | head -1)
rm -rf "$B/sub.ms"
t0=$(date +%s)
"$QC/bin/python" -I "$S/sf_oracle.py" cut "$SRC" J1939-6342 "$ver" "$B/sub.ms"
echo "cut $(( $(date +%s) - t0 )) s"
rm -rf "$D/sub.ms"; cp -r "$B/sub.ms" "$D/sub.ms"; cp "$B/sub.ms.cut.json" "$D/"
t0=$(date +%s)
rm -rf "$B/G"
"$QC/bin/python" -I "$S/sf_oracle.py" qc "$B/sub.ms" "$B/G" G 4
echo "qc $(( $(date +%s) - t0 )) s"
mkdir -p "$D/G"; rm -rf "$D/G/qc-1" "$D/G/qc-2"
cp -r "$B/G/qc-1" "$B/G/qc-2" "$B/G/flag-before.npy" "$D/G/"
rm -rf "$B/sub.ms"
