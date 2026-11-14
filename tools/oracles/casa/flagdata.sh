#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# CASA flagdata on per-case copies (research/v8b-flagdata.md, section 3).
# Usage: bash tools/oracles/casa/flagdata.sh OUT_DIR PLAN.json [NAME ...]
# Inputs are mounted read-only: /in/cases (V8b's synthetic MSs, $cases),
# /in/luno.ms (the LUNO 1934-638 slice), /in/a1.ms (A1 as C2a's CASA run
# left it), /in/fixture (the five public fixture MSs), /in/heldout ($heldout,
# the ESO137 split, once it exists), /in/df (C6 run 01's CASA Df tables). Each case's copy is made under OUT_DIR.
set -euo pipefail
code=$(cd "$(dirname "$0")" && pwd)
run=$(realpath -m "$1")
plan=$(realpath "$2")
shift 2
image=${RANG_CASA_IMAGE:-rang-o-casa:6.7.6.14}
if [ -e "$run" ]; then echo "$run exists; choose a fresh run directory" >&2; exit 1; fi
mkdir -p "$run"
cases=${RANG_V8B_CASES:-/mnt/d/rang/scratch/v8b-20261113/cases}
luno=$(realpath "$HOME/Github/rang/outputs/luno-solve-20261029-02/work.ms")
a1=/mnt/d/rang/outputs/c2a-20261106-03/casa/a1.ms
fixture=$(realpath "${RANG_FIXTURE_DIR:-$HOME/Github/rang/outputs/b1-20261030-03-fixture/outer_scans}")
df=/mnt/d/rang/outputs/c6-20261106-01/casa
heldout=${RANG_V8B_HELDOUT:-/mnt/d/rang/scratch/v8b-20261113/heldout}
mkdir -p "$heldout"
cp "$plan" "$run/plan.json"
date -u +%FT%TZ > "$run/started.txt"
docker image inspect "$image" --format '{{.Id}}' > "$run/image.txt"
docker run --rm --user "$(id -u):$(id -g)" --network none \
  --tmpfs /tmp -e HOME=/tmp -e OMP_NUM_THREADS=1 \
  -v "$cases:/in/cases:ro" -v "$luno:/in/luno.ms:ro" -v "$a1:/in/a1.ms:ro" \
  -v "$fixture:/in/fixture:ro" -v "$df:/in/df:ro" -v "$heldout:/in/heldout:ro" -v "$code:/code:ro" \
  -v "$run:/run" -w /tmp "$image" \
  /usr/bin/time -f "%e %M %x" -o /run/time.txt \
  /opt/casa/bin/python -I /code/flagdata.py /run /run/plan.json "$@" > "$run/log.txt" 2>&1
sha256sum "$code/flagdata.py" "$code/flagdata.sh" > "$run/code-sha256.txt"
date -u +%FT%TZ > "$run/finished.txt"
