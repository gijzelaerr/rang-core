#!/usr/bin/env bash
# casa_avg.sh : D1 averaged over 2 channels by CASA mstransform into data/D1avg.ms (criterion E).
set -euo pipefail
here=$(dirname "$(readlink -f "$0")")
O=/mnt/d/rang/outputs/20261106-g3-spectral
rm -rf $O/data/D1avg.ms
flock ~/.rang-heavy.lock docker run --rm --user "$(id -u):$(id -g)" --network none --entrypoint "" \
  --tmpfs /tmp -e HOME=/tmp -e OMP_NUM_THREADS=1 -v "$here:/code:ro" -v "$O/data:/data" -w /tmp \
  rang-o-casa:6.7.6.14 /usr/bin/time -f "CASA %e s %M KB" /opt/casa/bin/python -I /code/casa_avg.py /data/D1.ms /data/D1avg.ms
