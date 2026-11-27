#!/bin/bash
# SPDX-License-Identifier: MIT
# The UHF gate's CARACal arm (gate 4, E3's reading words, reported only;
# research/uhf-gate.md section 6) on nash: CARACal 8f7bb363 from
# ~/Github/caracal/.venv with the frozen caracal-uhf-{dev,heldout}.yml, Stimela
# classic cabs as singularity images in ~/rang-data/stimela-sif (pull-list.txt
# names each image's public source). CARACal gets its own copy of the block's
# fetched MS (never the rang arm's MS), so its split never sees rang's flags.
#   UG_BLOCK=D|H nohup bash ug_caracal.sh >> $RUN/$UG_BLOCK/caracal/caracal.out 2>&1 &
# The run reads run.yml: the frozen file with two mechanical edits (run.yml.diff):
# getdata dataid set to the MS name (the frozen file leaves it empty), and flag_mask's
# `mask`, which CARACal's schema requires even with the worker disabled (the frozen
# file fails validation without it), set to the schema's example '', so nothing is
# read. Every job nice 19 / ionice idle under the main checkout's heavy lock.
# CARACal is pinned to 16 cores (CARACAL_CPUS): its Tricolour cab ignores
# OMP_NUM_THREADS and took all 36 of nash's cores on D before it was pinned live.
set -u
W=$(cd "$(dirname "$0")/../../../.." && pwd)
RUN=${RUN:-$HOME/rang-data/outputs/uhf-gate-20261126}
LOCK=$HOME/Github/rang/tools/heavy_lock.py
CAR=$HOME/Github/caracal
SID=$HOME/rang-data/stimela-sif
STRATEGY_SHA=4c336933bd6c4ad2c075945394d76e270665ce301b8353b7974601e3a0459856
case ${UG_BLOCK:-} in
  D) CB=1752418159 YML=caracal-uhf-dev.yml ;;
  H) CB=1726220298 YML=caracal-uhf-heldout.yml ;;
  *) echo "UG_BLOCK D or H"; exit 2 ;;
esac
SRC=$HOME/rang-data/uhf-s/ms/$CB.ms
REC=$W/research/results/uhf-s-fetch/$CB/ms-sha256.txt
# CARACAL_RETRY=1: the one retry the coordinator allowed (uhf-gate.md, post hoc
# 2026-11-27), in its own directory, with CARACal's documented crystalball switch
# prep.clearcal {enable: true, addmodel: true} as a third recorded edit
RETRY=${CARACAL_RETRY:-0}
D=$RUN/$UG_BLOCK/caracal
[ "$RETRY" = 1 ] && D=$RUN/$UG_BLOCK/caracal-retry
mkdir -p "$D/msdir" "$D/input" "$D/output" "$D/done"
note() { echo "$(date -Is) $UG_BLOCK caracal $*" | tee -a "$D/caracal.log"; }
source "$HOME/.rang-env.sh" > /dev/null 2>&1
[ "$(git -C "$CAR" rev-parse --short=8 HEAD)" = 8f7bb363 ] || { note "caracal is not 8f7bb363"; exit 2; }
if [ ! -e "$D/done/copy" ]; then
  /usr/bin/time -v -o "$D/time-copy.txt" python3 "$LOCK" run --slots 1 --mem 4 -- \
    nice -n 19 ionice -c3 cp -a "$SRC" "$D/msdir/" || { note "copy failed"; exit 3; }
  (cd "$D/msdir" && /usr/bin/time -v -o "$D/time-hash.txt" python3 "$LOCK" run --slots 1 --mem 4 -- \
    nice -n 19 ionice -c3 sha256sum -c --quiet "$REC" > "$D/hash.out" 2>&1) || { note "copy differs from receipt"; exit 3; }
  touch "$D/done/copy"
  note "copy equal to receipt"
fi
python3 - "$W/research/results/uhf-gate/$YML" "$D/run.yml" "$CB" "$RETRY" << 'EOF'
import sys
src, out, cb, retry = sys.argv[1:5]
t = open(src, encoding="utf-8").read()
edits = [("  dataid: ['']\n", f"  dataid: ['{cb}']\n"),
         ("  flag_mask:\n", "  flag_mask:\n    mask: ''\n")]
if retry == "1":
    sw = "  specweights: {enable: true, mode: uniform}\n"
    edits.append((sw, "  clearcal: {enable: true, addmodel: true}\n" + sw))
for old, new in edits:
    assert t.count(old) == 1, old
    t = t.replace(old, new)
open(out, "w", encoding="utf-8").write(t)
EOF
diff "$W/research/results/uhf-gate/$YML" "$D/run.yml" > "$D/run.yml.diff"
[ "$(grep -c '^[<>]' "$D/run.yml.diff")" = $((3 + RETRY)) ] || { note "run.yml edits"; exit 2; }
cp "$RUN/$UG_BLOCK/cfg/firstpass_UHF.yaml" "$D/input/firstpass_UHF.yaml"
[ "$(sha256sum < "$D/input/firstpass_UHF.yaml" | cut -c1-64)" = "$STRATEGY_SHA" ] || { note "strategy hash"; exit 2; }
sha256sum "$W/research/results/uhf-gate/$YML" "$D/run.yml" "$D/input/firstpass_UHF.yaml" > "$D/inputs-sha256.txt"
cd "$D" || exit 2
note "start"
t0=$(date +%s)
NS=${CARACAL_SLOTS:-16}
OMP_NUM_THREADS=$NS python3 "$LOCK" run --slots "$NS" --mem 160 -- \
  nice -n 19 ionice -c3 /usr/bin/time -v -o "$D/time-caracal.txt" \
  taskset -c "${CARACAL_CPUS:-20-35}" "$CAR/.venv/bin/caracal" -c run.yml -ct singularity -sid "$SID" \
  --general-msdir msdir --general-input input --general-output output \
  < /dev/null >> "$D/caracal-run.out" 2>&1
rc=$?
note "end rc=$rc $(( $(date +%s) - t0 ))s"
exit $rc
