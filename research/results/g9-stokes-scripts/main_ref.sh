#!/usr/bin/env bash
# main_ref.sh : build gemclean of main 0f5ef06 in a detached worktree and copy it to
# /mnt/d/rang/outputs/g9-bin/gemclean-main-0f5ef06 (criterion A's reference); the worktree is removed.
set -euo pipefail
export PATH=$HOME/.local/bin:$HOME/.cargo/bin:/usr/local/bin:/usr/bin:/bin
R=$HOME/Worktrees/rang/g9-main-0f5ef06
git -C $HOME/Github/rang worktree add --detach $R 0f5ef06
cd $R/core
cargo +1.93 build --offline --profile gemclean --bin gemclean 2>&1 | tail -1
mkdir -p /mnt/d/rang/outputs/g9-bin
cp target/gemclean/gemclean /mnt/d/rang/outputs/g9-bin/gemclean-main-0f5ef06
sha256sum /mnt/d/rang/outputs/g9-bin/gemclean-main-0f5ef06 | tee /mnt/d/rang/outputs/g9-bin/gemclean-main-0f5ef06.provenance
cd /
git -C $HOME/Github/rang worktree remove --force $R
