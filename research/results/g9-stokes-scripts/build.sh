#!/usr/bin/env bash
# build.sh [TAG] : build the gemclean profile binary of the worktree; with TAG copy it to
# /mnt/d/rang/outputs/g9-bin/gemclean-TAG with its provenance (commit, dirty files, sha256).
set -euo pipefail
export PATH=$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:/usr/bin:/bin
W=$HOME/Worktrees/rang/fp-g9-stokes
cd $W/core
cargo +1.93 build --offline --profile gemclean --bin gemclean 2>&1 | grep -E "^(error|warning)" -A14 | head -120 || true
test -x target/gemclean/gemclean
if [ $# -ge 1 ]; then
  O=/mnt/d/rang/outputs/g9-bin
  mkdir -p $O
  cp target/gemclean/gemclean $O/gemclean-$1
  echo "$(git -C $W rev-parse HEAD) $(git -C $W status --porcelain | wc -l) dirty files" > $O/gemclean-$1.provenance
  sha256sum $O/gemclean-$1 | tee -a $O/gemclean-$1.provenance
fi
