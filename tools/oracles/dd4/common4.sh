# SPDX-License-Identifier: MIT
# Shared settings of DD4's WSL steps (research/dd4-eso137.md, section 4).
set -euo pipefail
venv=${QC_VENV:-$HOME/Build/tmp/20261123-dd15/venv-qc027}
image=rang-wsclean-native:3.7
grid=(-gridder wgridder -wgridder-accuracy 1e-6 -no-min-grid-resolution -size 2880 2880 -scale 3asec -pol I -j ${DD4_J:-8})
wsc() {  # scratch log args...
  local s=$1 log=$2; shift 2
  docker run --rm --user "$(id -u):$(id -g)" --network none --entrypoint "" -v "$s:/w" -w /w \
    "$image" wsclean "$@" >> "$log" 2>&1
}
py() { "$venv/bin/python" -I "$@"; }
