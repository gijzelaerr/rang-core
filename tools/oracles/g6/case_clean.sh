#!/usr/bin/env bash
# G6 after-clean cases (research/g6-predict.md, criteria 4, 2, 7): gemclean images
# a fresh copy and writes MODEL_DATA (the default); gemclean -predict of the FITS it
# wrote goes to MODEL_PRED (unless SKIP_SELF=1) and WSClean -predict of them to
# MODEL_WSCLEAN; the FITS files are compared with a stored run REF_PREFIX.
#   bash case_clean.sh OUTDIR GEMCLEAN LABEL MS REF_PREFIX SIZE SCALE gemclean-args...
# gemclean-args: the imaging options after -name (channel options included).
set -eu
O=$1; GEM=$2; L=$3; MS=$4; REF=$5; SIZE=$6; SCALE=$7; shift 7
ARGS=("$@")
source "$(dirname "$(readlink -f "$0")")/lib.sh"
mkdir -p "$O/$L-img"; snapshot
rm -rf "$O/$L.ms"; cp -r "$MS" "$O/$L.ms"
casa_py /g6/compare.py "$O/$L.ms" --hashes "$O/$L-before.json"
CH=()
for ((i = 0; i < ${#ARGS[@]}; i++)); do
  case "${ARGS[$i]}" in
    -channels-out) CH+=(-channels-out "${ARGS[$((i + 1))]}") ;;
    -channel-range) CH+=(-channel-range "${ARGS[$((i + 1))]}" "${ARGS[$((i + 2))]}") ;;
  esac
done
exec 9>"$HOME/.rang-heavy.lock"; flock 9
{ date -Iseconds; cat /proc/loadavg; } > "$O/$L-load.txt"
gem "$L" -name "$O/$L-img/g" "${ARGS[@]}" -memory-report "$O/$L.ms" > "$O/$L-gemclean.log" 2>&1
if [ "${SKIP_SELF:-0}" != 1 ]; then
  gem "$L-self" -predict -name "$O/$L-img/g" -field 0 -j 16 "${CH[@]}" -model-column MODEL_PRED \
    "$O/$L.ms" > "$O/$L-self.log" 2>&1
fi
wsc "$L" -predict -gridder wgridder -no-min-grid-resolution -wgridder-accuracy 1e-6 -pol I \
  -size "$SIZE" "$SIZE" -scale "$SCALE" -field 0 -j 16 "${CH[@]}" -model-column MODEL_WSCLEAN \
  -name "$O/$L-img/g" "$O/$L.ms" > "$O/$L-wsclean.log" 2>&1
{ date -Iseconds; cat /proc/loadavg; } >> "$O/$L-load.txt"
flock -u 9
casa_py /g6/compare.py "$O/$L.ms" --field 0 --before "$O/$L-before.json" --out "$O/$L-compare.json" > /dev/null
if [ "${SKIP_SELF:-0}" != 1 ]; then
  casa_py /g6/compare.py "$O/$L.ms" --g MODEL_DATA --w MODEL_PRED --field 0 --out "$O/$L-self.json" > /dev/null
fi
rang_py "$HERE/rang_hash.py" "$O/$L.ms" MODEL_DATA > "$O/$L-rang-hash.json"
python3 - "$O" "$L" "$REF" <<'PY'
import hashlib, json, pathlib, sys
o, label, ref = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
mine = {p.name[len("g-"):]: sha(p) for p in sorted((o / f"{label}-img").glob("g-*.fits"))}
rp = pathlib.Path(ref)
theirs = {p.name[len(rp.name) + 1:]: sha(p) for p in sorted(rp.parent.glob(rp.name + "-*.fits"))}
diff = sorted(k for k in mine if theirs.get(k) != mine[k])
out = {"fits_files": len(mine), "reference_files": len(theirs), "fits_differ": diff,
       "fits_identical": not diff and set(mine) == set(theirs)}
s = o / f"{label}-self.json"
if s.exists():
    s = json.loads(s.read_text())
    out["self_bit_identical"] = s["sha256_g"] == s["sha256_w"]
rep = json.loads((o / f"{label}-img" / "g-report.json").read_text())
out["model_update"] = rep.get("model_update")
(o / f"{label}-fits.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
print(json.dumps(out, sort_keys=True))
PY
python3 "$HERE/summary.py" "$O" "$L"
