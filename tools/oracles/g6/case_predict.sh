#!/usr/bin/env bash
# G6 predict parity (research/g6-predict.md, criteria 1, 2, 3, 6): the same model
# images through gemclean -predict (MODEL_DATA) and WSClean -predict
# (MODEL_WSCLEAN) into one fresh copy of the MS.
#   bash case_predict.sh OUTDIR GEMCLEAN LABEL MS MODEL_PREFIX SIZE SCALE [extra args for both...]
# Extra args are channel options (-channels-out n, -channel-range s e).
# Single-channel cases also get the exact-sky check (dft.py).
set -eu
O=$1; GEM=$2; L=$3; MS=$4; M=$5; SIZE=$6; SCALE=$7; shift 7
EXTRA=("$@")
source "$(dirname "$(readlink -f "$0")")/lib.sh"
mkdir -p "$O"; snapshot
rm -rf "$O/$L.ms"; cp -r "$MS" "$O/$L.ms"
# WSClean -predict with -channels-out writes temporary files beside the
# model images: both imagers read a copy of them in $O.
mkdir -p "$O/$L-models"; cp "$M"-*model.fits "$O/$L-models/"; M=$O/$L-models/$(basename "$M")
casa_py /g6/compare.py "$O/$L.ms" --hashes "$O/$L-before.json"
exec 9>"$HOME/.rang-heavy.lock"; flock 9
{ date -Iseconds; cat /proc/loadavg; } > "$O/$L-load.txt"
gem "$L" -predict -name "$M" -field 0 -j 16 "${EXTRA[@]}" "$O/$L.ms" > "$O/$L-gemclean.log" 2>&1
wsc "$L" -predict -gridder wgridder -no-min-grid-resolution -wgridder-accuracy 1e-6 -pol I \
  -size "$SIZE" "$SIZE" -scale "$SCALE" -field 0 -j 16 "${EXTRA[@]}" -model-column MODEL_WSCLEAN \
  -name "$M" "$O/$L.ms" > "$O/$L-wsclean.log" 2>&1
{ date -Iseconds; cat /proc/loadavg; } >> "$O/$L-load.txt"
flock -u 9
casa_py /g6/compare.py "$O/$L.ms" --field 0 --before "$O/$L-before.json" --out "$O/$L-compare.json" > /dev/null
rang_py "$HERE/rang_hash.py" "$O/$L.ms" MODEL_DATA > "$O/$L-rang-hash.json"
case " ${EXTRA[*]} " in
  *-channels-out*) ;;
  *) rang_py "$HERE/dft.py" "$O/$L.ms" "$M-model.fits" --field 0 --out "$O/$L-dft.json" > /dev/null ;;
esac
python3 "$HERE/summary.py" "$O" "$L"
