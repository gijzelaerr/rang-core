#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# W6 criterion 5 (research/w6-imaging-inputs.md): G2's identity set with the final
# binary and -no-update-model-required, against G2's runs/c34 *.sha256. Heavy:
# one run at a time under ~/.rang-heavy.lock. The FITS files are deleted after hashing.
#   bash identity.sh OUTDIR GEMCLEAN
set -u
O=$1; GEM=$2
D=/mnt/d/rang/outputs
REF=$D/20261106-g2-memory/runs/c34/img
mkdir -p "$O/id"
sha256sum "$GEM" > "$O/id/gemclean.sha256"
data() {
  case $1 in
    s1|s2|s3) echo "$D/20261102-gemclean/bench/data/$1.ms" ;;
    h1|h2|h3|h4) echo "$D/20261103-gemclean-heldout/sim/data/$1.ms" ;;
    p256) echo "$D/20261103-gemclean-heldout/real/cal2.ms" ;;
  esac
}
for tag in s1-def s1-coarse s2-def s2-coarse s3-def s3-coarse h1-def h1-coarse h2-def h2-coarse \
           h3-def h3-coarse h4-def h4-coarse p256-def; do
  sky=${tag%%-*}
  mapfile -t argv < <(python3 - "$REF/$tag-report.json" "$O/id/$tag" <<'PY'
import json, sys
a = json.load(open(sys.argv[1]))["argv"][:-1]
a[a.index("-name") + 1] = sys.argv[2]
print("\n".join(a))
PY
)
  exec 9>"$HOME/.rang-heavy.lock"; flock 9
  /usr/bin/time -v -o "$O/id/$tag-time.txt" "$GEM" "${argv[@]}" -no-update-model-required \
    "$(data "$sky")" > "$O/id/$tag.log" 2>&1
  rc=$?
  flock -u 9
  (cd "$O/id" && sha256sum "$tag"-{dirty,psf,model,residual,image}.fits > "$tag.sha256")
  python3 - "$O/id/$tag.sha256" "$REF/$tag.sha256" "$tag" "$rc" <<'PY' | tee -a "$O/id/results.txt"
import sys
mine = dict(l.split()[::-1] for l in open(sys.argv[1]))
ref = dict(l.split()[::-1] for l in open(sys.argv[2]))
same = [k for k in ref if mine.get(k) == ref[k]]
print(sys.argv[3], "exit", sys.argv[4], "identical", len(same), "of", len(ref))
PY
  rm -f "$O/id/$tag"-{dirty,psf,model,residual,image}.fits
done
