#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Usage: bash tools/a1_casa.sh RUN_DIR SUBCOMMAND ARGS...   (research/a1-simtruth.md)
# One network-less rang-o-casa container step of examples/a1_simtruth_casa.py,
# with RUN_DIR mounted at /run (paths in ARGS are under /run) and the step
# timed by /usr/bin/time inside the container.
set -euo pipefail
run=$(realpath "$1")
shift
code=$(realpath "$(dirname "$0")/../examples")
mkdir -p "$run/timing"
step=$1
exec docker run --rm --user "$(id -u):$(id -g)" --network none --tmpfs /tmp \
  -e HOME=/tmp -e OMP_NUM_THREADS=4 \
  -v "$code:/code:ro" -v "$run:/run" -w /run rang-o-casa:6.7.6.14 \
  /usr/bin/time -f "%e %M %U %S %x" -o "/run/timing/$step-$(date +%H%M%S).txt" \
  /opt/casa/bin/python -I /code/a1_simtruth_casa.py "$@"
