#!/usr/bin/env bash
# main_ref.sh [COMMIT] : build gemclean of main COMMIT (default 0f5ef06) in a detached worktree and
# copy it to /mnt/d/rang/outputs/g9-bin/gemclean-main-COMMIT (criterion A's reference); the
# worktree is removed. Run under the heavy lock.
set -euo pipefail
export PATH=$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:/usr/bin:/bin
C=${1:-0f5ef06}
R=$HOME/Worktrees/rang/g9-main-$C
git -C $HOME/Github/rang worktree add --detach $R $C
cd $R/core
cargo +1.93 build --offline --profile gemclean --bin gemclean 2>&1 | tail -1
mkdir -p /mnt/d/rang/outputs/g9-bin
cp target/gemclean/gemclean /mnt/d/rang/outputs/g9-bin/gemclean-main-$C
sha256sum /mnt/d/rang/outputs/g9-bin/gemclean-main-$C | tee /mnt/d/rang/outputs/g9-bin/gemclean-main-$C.provenance
cd /
git -C $HOME/Github/rang worktree remove --force $R
