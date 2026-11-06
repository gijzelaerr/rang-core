#!/usr/bin/env bash
# build.sh TAG : build the gemclean profile binary of the worktree and copy it to the outputs dir
set -euo pipefail
export PATH=$HOME/.local/bin:$HOME/.cargo/bin:$PATH
W=$HOME/Worktrees/rang/fp-g3-spectral
O=/mnt/d/rang/outputs/20261106-g3-spectral/bin
mkdir -p $O
cd $W/core
s=$(date +%s)
flock ~/.rang-heavy.lock cargo +1.93 build --offline --profile gemclean --bin gemclean 2>&1 | tail -2
cp target/gemclean/gemclean $O/gemclean-$1
echo "$(git -C $W rev-parse HEAD) $(git -C $W status --porcelain | wc -l) dirty files; build $(( $(date +%s) - s )) s" > $O/gemclean-$1.provenance
sha256sum $O/gemclean-$1
