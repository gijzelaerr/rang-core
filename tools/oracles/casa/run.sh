#!/usr/bin/env bash
# Run the O-CASA oracle once into a fresh run directory (research/o-casa.md).
# Usage: bash tools/oracles/casa/run.sh outputs/o-casa-20261030-NN [image]
# Needs the worktree .venv (compare.py imports rang) and the built image.
set -euo pipefail
export PATH=$HOME/.cargo/bin:$PATH  # compare.py builds the TV kernel on demand
root=$(cd "$(dirname "$0")/../../.." && pwd)
code="$root/tools/oracles/casa"
run=$(realpath -m "$1")
image=${2:-rang-o-casa:6.7.6.14}
if [ -e "$run" ]; then echo "$run exists; choose a fresh run directory" >&2; exit 1; fi
mkdir -p "$run/timing" "$run/logs" "$run/casa" "$run/wsclean"
slice=$(realpath "$root/outputs/luno-support-20261029-01/slice")
inputs=$(realpath "$root/outputs/luno-solve-20261029-02/inputs")
archived=$(realpath "$root/outputs/luno-solve-20261029-02/work.ms")

host() {  # host step, timed
  local name=$1; shift
  echo "## $name"
  /usr/bin/time -f "%e %M %x" -o "$run/timing/$name.txt" "$@" > "$run/logs/$name.log" 2>&1
}
ctr() {  # container step, timed inside the container
  local name=$1; shift
  echo "## $name"
  docker run --rm --user "$(id -u):$(id -g)" --network none \
    --tmpfs /tmp -e HOME=/tmp -e OMP_NUM_THREADS=4 \
    -v "$slice:/slice:ro" -v "$inputs:/inputs:ro" -v "$archived:/archived/work.ms:ro" \
    -v "$code:/code:ro" -v "$root/examples/build_luno_ms.py:/b.py:ro" \
    -v "$run:/run" -w /run "$image" \
    /usr/bin/time -f "%e %M %x" -o "/run/timing/$name.txt" "$@" > "$run/logs/$name.log" 2>&1
}
casa() { ctr "$1" /opt/casa/bin/python -I /code/crosscal.py "${@:2}"; }
cc() { ctr "$1" python3 -I /code/inspect_tables.py "${@:2}"; }

date -u +%FT%TZ > "$run/started.txt"
host inputs python3 "$code/receipt.py" inputs "$run/inputs-check.json"
host split "$root/.venv/bin/python" "$code/compare.py" split "$run"
ctr build python3 -I /b.py /slice /inputs /run/work.ms
cc equal equal /archived/work.ms /run/work.ms /run/ms-equality.json
cc prepare prepare /run
ctr image-lists sh -c 'cp /opt/image-debs.txt /opt/image-pip.txt /run/'
for arm in a b d c; do
  casa "solve-$arm" solve "$arm" "/run/$arm.ms"
  casa "apply-$arm" apply "$arm" "/run/$arm.ms"
done
for arm in ch sh; do
  casa "solve-$arm" solve "$arm" "/run/$arm.ms"
  cc "restore-$arm" restore /run "$arm"
  casa "apply-$arm" apply "$arm" "/run/$arm.ms"
done
casa flagdata-tfcrop flagdata tfcrop /run/tfcrop.ms
casa flagdata-rflag flagdata rflag /run/rflag.ms
casa setjy-sr2016 setjy "Stevens-Reynolds 2016" /run/fs-sr2016.ms
casa setjy-pb2010 setjy "Perley-Butler 2010" /run/fs-pb2010.ms
ctr wsclean-c wsclean -gridder wgridder -data-column CORRECTED_DATA -size 512 512 \
  -scale 8asec -weight briggs 0.5 -pol I -niter 0 -make-psf -field 1 -j 4 -name /run/wsclean/c /run/c.ms
cc summarize summarize /run
host compare "$root/.venv/bin/python" "$code/compare.py" compare "$run"
date -u +%FT%TZ > "$run/finished.txt"
python3 "$code/receipt.py" final "$run" "$image" "$run/receipt.json"
echo "## done $run"
