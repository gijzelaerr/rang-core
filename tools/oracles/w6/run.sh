#!/usr/bin/env bash
# W6 cases (research/w6-imaging-inputs.md). Small runs: nice, 4 threads, no heavy lock
# (CASA split under the lock).
#   bash run.sh OUTDIR GEMCLEAN dev|held
set -u
O=$1; GEM=$2; SET=$3
HERE=$(dirname "$(readlink -f "$0")")
WT=$HOME/Worktrees/rang/fp-g6-predict
D=/mnt/d/rang/outputs
A1=$D/fp-a1-20261106-simtruth/small/a1-small.ms
UIDS="$(id -u):$(id -g)"
mkdir -p "$O/.code"
cp -r "$HERE" "$O/.code/w6"; git -C "$WT" rev-parse HEAD > "$O/.code/commit.txt"
git -C "$WT" status --porcelain > "$O/.code/status.txt"; git -C "$WT" diff > "$O/.code/diff.patch"
sha256sum "$GEM" > "$O/.code/gemclean.sha256"
R="$O/results.jsonl"

casa_py() { docker run --rm --user "$UIDS" --network none -e HOME=/tmp -v "$O:$O" -v "$D:$D:ro" \
  -v "$HERE:/w6:ro" --entrypoint python3 rang-ms-reader:local "$@"; }
g6py() { docker run --rm --user "$UIDS" --network none -e HOME=/tmp -v "$O:$O"   -v "$WT/tools/oracles/g6:/g6:ro" --entrypoint python3 rang-ms-reader:local "$@"; }
casa() { docker run --rm --user "$UIDS" --network none --entrypoint "" --tmpfs /tmp -e HOME=/tmp \
  -v "$O:$O" -v "$D:$D:ro" -v "$HERE:/w6:ro" rang-o-casa:6.7.6.14 /opt/casa/bin/python -I "$@"; }
wsc() { local out=$1 ms=$2 field=$3; shift 3; mkdir -p "$(dirname "$out")"
  nice -n 10 docker run --rm --user "$UIDS" --network none -e HOME=/tmp -e OMP_NUM_THREADS=4 \
    -v "$O:$O" -v "$D:$D:ro" -w "$O" rang-wsclean-native:3.7 wsclean -gridder wgridder \
    -no-min-grid-resolution -wgridder-accuracy 1e-6 -pol I -size 512 512 -scale 2asec \
    -weight briggs 0 -niter 0 -make-psf -no-update-model-required -data-column DATA -j 4 \
    -field "$field" "$@" -name "$out" "$ms" > "$out.log" 2>&1; }
GARGS=(-size 512 512 -scale 2asec -weight briggs 0 -data-column DATA -j 4)
gem() { local out=$1 ms=$2 field=$3 niter=$4; shift 4; mkdir -p "$(dirname "$out")"
  nice -n 10 "$GEM" -name "$out" "${GARGS[@]}" -niter "$niter" -field "$field" "$@" "$ms" > "$out.log" 2>&1
  echo "gemclean $out exit $?" >> "$O/exits.txt"; }
copy() { rm -rf "$2"; cp -r "$1" "$2"; }
cmp() { "$WT/.venv/bin/python" "$HERE/fits_cmp.py" "$@"; }  # numpy is in the venv
rec() { echo "{\"case\": \"$1\", \"check\": \"$2\", \"result\": $3}" | tee -a "$R"; }
split() { # split SRC OUT SCANS NAME -> prints the field id
  exec 9>"$HOME/.rang-heavy.lock"; flock 9
  casa /w6/casa_split.py "$1" "$2" "$3" "$4" "$2.json" > "$2.log" 2>&1
  flock -u 9
  python3 -c "import json; print(json.load(open('$2.json'))['field_id'])"; }

sc() { # sc LABEL FIELD NAME SCANS
  local L=$1 F=$2 N=$3 S=$4 d=$O/$1
  mkdir -p "$d"; copy "$A1" "$d/full.ms"
  casa_py /w6/prep.py "$d/full.ms" --sentinel MODEL_DATA > "$d/prep.log"
  local id; id=$(split "$A1" "$d/split.ms" "$S" "$N")
  gem "$d/g-full/g" "$d/full.ms" "$F" 300 -scans "$S"            # writes MODEL_DATA (default)
  gem "$d/g-split/g" "$d/split.ms" "$id" 300 -no-update-model-required
  rec "$L" 1a "$(cmp same "$d/g-full/g" "$d/g-split/g")"
  gem "$d/g0/g" "$d/full.ms" "$F" 0 -scans "$S" -no-update-model-required
  wsc "$d/w0/w" "$d/split.ms" "$id"
  rec "$L" 1b "$(cmp bounds "$d/g0/g" "$d/w0/w")"
  rec "$L" 1c "$(casa_py /w6/rows_check.py "$d/full.ms" "$F" "$S")"
}

unit() { # unit LABEL FIELD
  local L=$1 F=$2 d=$O/$1
  mkdir -p "$d"; copy "$A1" "$d/u.ms"
  casa_py /w6/prep.py "$d/u.ms" --random-ws 20261181 > "$d/prep.log"
  copy "$d/u.ms" "$d/u1.ms"; casa_py /w6/prep.py "$d/u1.ms" --unit >> "$d/prep.log"
  gem "$d/g-unit/g" "$d/u.ms" "$F" 300 -unit-weights -no-update-model-required
  gem "$d/g-u1/g" "$d/u1.ms" "$F" 300 -no-update-model-required
  gem "$d/g-plain/g" "$d/u.ms" "$F" 300 -no-update-model-required
  rec "$L" 2a "$(cmp same "$d/g-unit/g" "$d/g-u1/g")"
  rec "$L" 2b "$(cmp same "$d/g-unit/g" "$d/g-plain/g")"
  gem "$d/g0/g" "$d/u.ms" "$F" 0 -unit-weights -no-update-model-required
  wsc "$d/w0/w" "$d/u1.ms" "$F"
  rec "$L" 2c "$(cmp bounds "$d/g0/g" "$d/w0/w")"
  local name; name=$(casa_py -c "import casacore.tables as ct; print(ct.table('$A1/FIELD', ack=False).getcol('NAME')[$F])")
  g6py /g6/compare.py "$d/u.ms" --hashes "$d/u-before.json"
  cat > "$d/config.yaml" <<EOF
schema: rang-config
version: 1
fields:
  target: [$name]
data:
  weights: uniform
image:
  gemclean: $GEM
  column: DATA
  size: [512, 512]
  scale: 2asec
  weight: briggs
  robust: 0.0
  niter: 300
  threads: 4
run:
  stages: [image]
EOF
  (cd "$d" && nice -n 10 "$WT/.venv/bin/python" -m rang.core_cli image config.yaml u.ms --run-dir "$d/run" > "$d/core.log" 2>&1)
  echo "rang-core $L exit $?" >> "$O/exits.txt"
  g6py /g6/compare.py "$d/u.ms" --hashes "$d/u-after.json"
  rec "$L" 2d "$(python3 -c "import json; a=json.load(open('$d/u-before.json')); b=json.load(open('$d/u-after.json')); print(json.dumps({'unchanged': a==b, 'columns': len(a['columns'])}))")"
}

fallback() { # WU and NW, field 3
  local d=$O/wu
  mkdir -p "$d"; copy "$A1" "$d/base.ms"
  casa_py /w6/prep.py "$d/base.ms" --random-weight 20261182 > "$d/prep.log"
  copy "$d/base.ms" "$d/wu.ms"; casa_py /w6/prep.py "$d/wu.ms" --undefine-ws >> "$d/prep.log"
  copy "$d/base.ms" "$d/nw.ms"; casa_py /w6/prep.py "$d/nw.ms" --drop-ws >> "$d/prep.log"
  gem "$d/g-wu/g" "$d/wu.ms" 3 300 -no-update-model-required
  gem "$d/g-nw/g" "$d/nw.ms" 3 300 -no-update-model-required
  rec WU 3a "$(cmp same "$d/g-wu/g" "$d/g-nw/g")"
  gem "$d/g0/g" "$d/wu.ms" 3 0 -no-update-model-required
  wsc "$d/w0/w" "$d/wu.ms" 3
  rec WU 3b "$(cmp bounds "$d/g0/g" "$d/w0/w")"
  for x in wu nw; do
    cat > "$d/config-$x.yaml" <<EOF
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
run:
  stages: [image]
EOF
    (cd "$d" && nice -n 10 "$WT/.venv/bin/python" -m rang.core_cli image "config-$x.yaml" "$x.ms" --run-dir "$d/run-$x" > "$d/core-$x.log" 2>&1)
    echo "rang-core $x exit $?" >> "$O/exits.txt"
  done
  rec WU 3c "$(cmp same "$d/run-wu/image/SIM-TARGET/image" "$d/run-nw/image/SIM-TARGET/image")"
}

e2() { # the E2-A-shaped stand-in
  local d=$O/e2
  mkdir -p "$d"; copy "$A1" "$d/e2.ms"
  copy "$A1" "$d/unit.ms"; casa_py /w6/prep.py "$d/unit.ms" --unit > "$d/prep.log"
  cat > "$d/config.yaml" <<EOF
schema: rang-config
version: 1
fields:
  fcal: [J1939-6342]
  target: [SIM-TARGET]
data:
  weights: uniform
  scans: [1, 4, 6]
image:
  gemclean: $GEM
  fields: [target]
  column: DATA
  size: [512, 512]
  scale: 2asec
  weight: briggs
  robust: 0.0
  niter: 300
  threads: 4
run:
  stages: [image]
EOF
  (cd "$d" && nice -n 10 "$WT/.venv/bin/python" -m rang.core_cli image config.yaml e2.ms --run-dir "$d/run" > "$d/core.log" 2>&1)
  echo "rang-core e2 exit $?" >> "$O/exits.txt"
  local id; id=$(split "$d/unit.ms" "$d/split.ms" "1,4,6" SIM-TARGET)
  # The argv rang-core gave gemclean, on the split, without -scans and -unit-weights.
  mapfile -t argv < <(python3 - "$d" "$id" <<'PY'
import json, sys
d, fid = sys.argv[1], sys.argv[2]
a = json.load(open(f"{d}/run/image/summary.json"))["images"][0]["argv"][1:-1]
out, i = [], 0
while i < len(a):
    if a[i] == "-scans":
        i += 2; continue
    if a[i] == "-unit-weights":
        i += 1; continue
    if a[i] == "-field":
        out += ["-field", fid]; i += 2; continue
    if a[i] == "-name":
        out += ["-name", f"{d}/g-split/image"]; i += 2; continue
    out.append(a[i]); i += 1
print("\n".join(out))
PY
)
  mkdir -p "$d/g-split"
  nice -n 10 "$GEM" "${argv[@]}" "$d/split.ms" > "$d/g-split.log" 2>&1
  echo "gemclean e2 split exit $?" >> "$O/exits.txt"
  rec E2 4b "$(cmp same "$d/run/image/SIM-TARGET/image" "$d/g-split/image")"
}

case $SET in
  dev) sc SC-d 3 SIM-TARGET 4,6,10; unit U-d 3; fallback ;;
  held) sc SC-h1 3 SIM-TARGET 12,16,20; sc SC-h2 2 SIM-GCAL 5,9,13,17; unit U-h 2; e2 ;;
esac
cat "$O/exits.txt"
