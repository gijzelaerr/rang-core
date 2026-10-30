#!/usr/bin/env bash
# Labelled post-hoc steps after runs -01/-02 (research/o-casa.md, "Measured result").
# Usage: bash tools/oracles/casa/posthoc.sh [image]
# Writes outputs/o-casa-20261030-03-wsclean-j1, -04-arm-e, -05-arm-f (fresh only).
# These are the commands that produced those directories; the inline metric and
# diff scripts were run ad hoc from the session scratchpad and are reproduced here.
set -euo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
image=${1:-rang-o-casa:6.7.6.14}
out="$root/outputs"
dock() {  # dock <run> <name> <threads> <cmd...>
  local run=$1 name=$2 threads=$3; shift 3
  docker run --rm --user "$(id -u):$(id -g)" --network none --tmpfs /tmp -e HOME=/tmp \
    -e OMP_NUM_THREADS="$threads" -v "$root/tools/oracles/casa:/code:ro" -v "$run:/run" -w /run \
    "$image" /usr/bin/time -f "%e %M %x" -o "/run/timing/$name.txt" "$@"
}

# -03: WSClean -j 1 twice on a copy of run -01's calibrated c.ms.
run=$(realpath -m "$out/o-casa-20261030-03-wsclean-j1")
mkdir "$run" "$run/timing"
cp -r "$out/o-casa-20261030-01/c.ms" "$run/"
for k in 1 2; do
  dock "$run" "wsclean-$k" 1 wsclean -gridder wgridder -data-column CORRECTED_DATA -size 512 512 \
    -scale 8asec -weight briggs 0.5 -pol I -niter 0 -make-psf -field 1 -j 1 -name "/run/r$k" /run/c.ms \
    > "$run/wsclean-$k.log" 2>&1
done
docker run --rm --user "$(id -u):$(id -g)" --network none -v "$root/tools/oracles/casa:/code:ro" \
  -v "$run:/run" -v "$out/o-casa-20261030-01/wsclean:/j4a:ro" -v "$out/o-casa-20261030-02/wsclean:/j4b:ro" \
  -w /run "$image" python3 -I -c '
import hashlib, json, sys
import numpy as np
sys.path.insert(0, "/code")
from inspect_tables import image_metrics, read_fits
out = {}
for k in (1, 2):
    _, d = read_fits(f"/run/r{k}-dirty.fits")
    _, p = read_fits(f"/run/r{k}-psf.fits")
    m = image_metrics(d, p)
    for kind in ("dirty", "psf"):
        m[f"{kind}_fits_sha256"] = hashlib.sha256(open(f"/run/r{k}-{kind}.fits", "rb").read()).hexdigest()
    out[f"r{k}"] = m
diff = {}
for kind in ("dirty", "psf"):
    a = read_fits(f"/j4a/c-{kind}.fits")[1]
    b = read_fits(f"/j4b/c-{kind}.fits")[1]
    j1 = read_fits(f"/run/r1-{kind}.fits")[1]
    diff[kind] = {
        "j4_run_to_run_max_abs": float(np.abs(a - b).max()),
        "j4_run_to_run_max_rel": float(np.abs(a - b).max() / np.abs(a).max()),
        "j1_vs_j4_max_rel": float(np.abs(a - j1).max() / np.abs(a).max()),
    }
out["diff"] = diff
json.dump(out, open("/run/metrics.json", "w"), indent=1, sort_keys=True)
print(json.dumps(diff))
'

# -04 / -05: arms E and F of crosscal.py on copies of run -01's work.ms.
for arm in e f; do
  case $arm in e) run=$(realpath -m "$out/o-casa-20261030-04-arm-e") ;; f) run=$(realpath -m "$out/o-casa-20261030-05-arm-f") ;; esac
  mkdir "$run" "$run/timing" "$run/logs"
  cp -r "$out/o-casa-20261030-01/work.ms" "$run/$arm.ms"
  dock "$run" "solve-$arm" 4 /opt/casa/bin/python -I /code/crosscal.py solve "$arm" "/run/$arm.ms" \
    > "$run/logs/solve-$arm.log" 2>&1
  dock "$run" "apply-$arm" 4 /opt/casa/bin/python -I /code/crosscal.py apply "$arm" "/run/$arm.ms" \
    > "$run/logs/apply-$arm.log" 2>&1
done
echo "## done"
