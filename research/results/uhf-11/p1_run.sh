#!/bin/bash
# Port check P1 (research/uhf-11.md section 6): rang's Tricolour port against
# Tricolour 0.2.1 with CARACal's firstpass_UHF.yaml on three DL2 train
# calibrator scans. Self-driving; one done-marker per (scan, teacher).
#   setsid nohup bash p1_run.sh ROOT > ROOT/p1.log 2>&1 &
# Run under: tools/heavy_lock.py run --slots 4 --mem 24 -- bash p1_run.sh ROOT
set -euo pipefail
ROOT=${1:?run root}
SRC=$HOME/rang-data/outputs/dl2-data-20261119/ms
SIF=$HOME/rang-data/oracle-images/rang-tricolour_0.2.1-e1.sif
VENV=$HOME/Worktrees/rang/release-040/.venv
STRAT_SRC=$HOME/Github/caracal/caracal/data/meerkat_files/firstpass_UHF.yaml
STRAT_SHA=4c336933bd6c4ad2c075945394d76e270665ce301b8353b7974601e3a0459856
SCANS="1735892129/scan003 1735892129/scan001 1611426666/scan004"
T=4
mkdir -p "$ROOT"/{done,copies,work,labels}
cp --update=none "$STRAT_SRC" "$ROOT/work/firstpass_UHF.yaml"
echo "$STRAT_SHA  $ROOT/work/firstpass_UHF.yaml" | sha256sum -c -
cat > "$ROOT/work/rang.yaml" <<YAML
schema: rang-config
version: 1
data:
  processes: $T
  memory_limit_gb: 16.0
flag:
  strategy: firstpass_UHF.yaml
YAML
for s in $SCANS; do
  cb=${s%/*}; sc=${s#*/}; key=$cb-$sc
  for teacher in tricolour rang; do
    [ -e "$ROOT/done/$key.$teacher" ] && continue
    wc=$ROOT/copies/$teacher/$cb/$sc.ms
    [ -e "$wc" ] && chmod -R u+w "$wc"
    rm -rf "$wc" "$wc.flagversions"; mkdir -p "$(dirname "$wc")"
    t0=$(date +%s.%N)
    nice -n 19 ionice -c3 cp -a "$SRC/$cb/$sc.ms" "$wc"
    chmod -R u+w "$wc"  # the DL2 MSs are frozen read-only
    t1=$(date +%s.%N)
    if [ $teacher = tricolour ]; then
      cp "$ROOT/work/firstpass_UHF.yaml" "$ROOT/work/strategy-$key.yaml"
      /usr/bin/time -v nice -n 19 ionice -c3 apptainer exec --containall --env HOME=/tmp \
        --env OMP_NUM_THREADS=$T --pwd /tmp --bind "$(dirname "$wc"):/ms" --bind "$ROOT/work:/p" \
        "$SIF" sh -c "tricolour -c /p/strategy-$key.yaml -fs polarisation -dc DATA -dpm -nw $T /ms/$sc.ms" \
        > "$ROOT/work/$key.$teacher.log" 2>&1
    else
      rm -rf "$ROOT/work/run-$key"
      RAYON_NUM_THREADS=$T /usr/bin/time -v nice -n 19 ionice -c3 "$VENV/bin/rang-core" flag \
        --run-dir "$ROOT/work/run-$key" "$ROOT/work/rang.yaml" "$wc" > "$ROOT/work/$key.$teacher.log" 2>&1
    fi
    t2=$(date +%s.%N)
    out=$ROOT/labels/$teacher/$key; mkdir -p "$out"
    "$VENV/bin/python" -I - "$wc" "$out" <<'PY'
import sys, numpy as np
from casacore.tables import table
t = table(sys.argv[1], readonly=True, ack=False)
f = t.getcol("FLAG"); r = t.getcol("FLAG_ROW"); t.close()
np.save(sys.argv[2] + "/flag.npy", np.packbits(f.reshape(f.shape[0], -1), axis=1))
np.save(sys.argv[2] + "/flag_row.npy", r)
print("shape", f.shape, "fraction", float(f.mean()))
PY
    echo "$key $teacher copy=$(echo "$t1-$t0"|bc) teach=$(echo "$t2-$t1"|bc)" >> "$ROOT/timings.txt"
    rm -rf "$wc" "$wc.flagversions"
    touch "$ROOT/done/$key.$teacher"
  done
done
"$VENV/bin/python" -I "$(dirname "$0")/p1_compare.py" "$ROOT" > "$ROOT/result.json"
touch "$ROOT/done/ALL"
