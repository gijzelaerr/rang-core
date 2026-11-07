#!/usr/bin/env bash
# avg_batch.sh BIN TAG : criterion E (channel averaging against CASA mstransform).
set -u
here=$(dirname "$(readlink -f "$0")")
O=/mnt/d/rang/outputs/20261106-g3-spectral
bin=$1; tag=$2
[ -d $O/data/D1avg.ms ] || bash "$here/casa_avg.sh"
bash "$here/run_g.sh" "$bin" "$tag" D1 A1
bash "$here/run_g.sh" "$bin" "$tag" D1 A4
bash "$here/run_g.sh" "$bin" "$tag" D1avg P1
bash "$here/run_g.sh" "$bin" "$tag" D1avg P4
bash "$here/run_w.sh" D1avg P1
bash "$here/run_w.sh" D1avg P4
echo AVG-DONE
