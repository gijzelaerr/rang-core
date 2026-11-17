#!/bin/bash
# Build rang's E2 wheel on nash at the frozen wheel's commit b2d80dc (research/e3-caracal.md 10.14)
# and install it into a fresh venv with freeze-2.txt's pins, for rang's E2-A timed run on nash.
#   bash e3n_rang_wheel.sh OUTDIR FREEZE2.txt
# The source is a `git archive` export of b2d80dc from ~/Github/rang (no checkout).
set -eu
O=$1; FRZ=$2
mkdir -p "$O/src"
git -C ~/Github/rang archive b2d80dc | tar -x -C "$O/src"
cd "$O/src"
for m in Cargo.toml core/Cargo.toml core/py/Cargo.toml; do cargo +1.93 fetch --manifest-path "$m"; done
LOCK=~/Github/rang/tools/heavy_lock.py
echo "BUILD START $(date -Is) load $(cut -d' ' -f1-3 /proc/loadavg)"
python3 $LOCK run --slots 8 --mem 16 -- \
  /usr/bin/time -f "wall %e s rss %M KB" ~/Github/rang/.venv/bin/maturin build --release -o "$O/dist"
echo "BUILD END $(date -Is) load $(cut -d' ' -f1-3 /proc/loadavg)"
sha256sum "$O"/dist/*.whl | tee "$O/wheel.sha256"
uv venv -q --python 3.14 "$O/venv"
W=$(ls "$O"/dist/*.whl)
# freeze-2.txt's pins, rang-core from this wheel with the imaging extra (e2-acceptance 6.4)
grep -v '^rang-core' "$FRZ" > "$O/pins.txt"
uv pip install -q --python "$O/venv/bin/python" -r "$O/pins.txt" "rang-core[imaging] @ file://$W"
uv pip freeze --python "$O/venv/bin/python" | tee "$O/freeze-nash.txt"
"$O/venv/bin/python" -c "import rang, rang._core; print('ok', rang.__file__)"
