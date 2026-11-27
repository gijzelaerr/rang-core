#!/bin/bash
# SPDX-License-Identifier: MIT
# The UHF gate's CARACal arm (gate 4, E3's reading words, reported only;
# research/uhf-gate.md section 6) on nash: CARACal 8f7bb363 from
# ~/Github/caracal/.venv with the frozen caracal-uhf-{dev,heldout}.yml, Stimela
# classic cabs as singularity images in ~/rang-data/stimela-sif (pull-list.txt
# names each image's public source). CARACal gets its own copy of the block's
# fetched MS (never the rang arm's MS), so its split never sees rang's flags.
#   UG_BLOCK=D|H nohup bash ug_caracal.sh >> $RUN/$UG_BLOCK/caracal/caracal.out 2>&1 &
# Only the MS name (getdata dataid) is given on the command line; the frozen
# file leaves it empty. Every job nice 19 / ionice idle under the main
# checkout's heavy lock.
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
D=$RUN/$UG_BLOCK/caracal
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
cp "$W/research/results/uhf-gate/$YML" "$D/$YML"
cp "$RUN/$UG_BLOCK/cfg/firstpass_UHF.yaml" "$D/input/firstpass_UHF.yaml"
[ "$(sha256sum < "$D/input/firstpass_UHF.yaml" | cut -c1-64)" = "$STRATEGY_SHA" ] || { note "strategy hash"; exit 2; }
sha256sum "$D/$YML" "$D/input/firstpass_UHF.yaml" > "$D/inputs-sha256.txt"
cd "$D" || exit 2
note "start"
t0=$(date +%s)
OMP_NUM_THREADS=16 python3 "$LOCK" run --slots 16 --mem 160 -- \
  nice -n 19 ionice -c3 /usr/bin/time -v -o "$D/time-caracal.txt" \
  "$CAR/.venv/bin/caracal" -c "$YML" -ct singularity -sid "$SID" \
  --general-msdir msdir --general-input input --general-output output \
  --getdata-dataid "$CB" < /dev/null >> "$D/caracal-run.out" 2>&1
rc=$?
note "end rc=$rc $(( $(date +%s) - t0 ))s"
exit $rc
