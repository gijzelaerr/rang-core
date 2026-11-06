#!/usr/bin/env bash
# Build main 0cb508b (detached scratch worktree) and run S1 default for criterion A's reference check.
set -euo pipefail
export PATH=$HOME/.local/bin:$HOME/.cargo/bin:$PATH
W=$HOME/Worktrees/rang/g3-main-0cb508b
O=/mnt/d/rang/outputs/20261106-g3-spectral
[ -d $W ] || git -C $HOME/Worktrees/rang/fp-g3-spectral worktree add -q --detach $W 0cb508b
cd $W/core
flock ~/.rang-heavy.lock cargo +1.93 build --offline --profile gemclean --bin gemclean 2>&1 | tail -2
mkdir -p $O/bin
cp target/gemclean/gemclean $O/bin/gemclean-main-0cb508b
sha256sum $O/bin/gemclean-main-0cb508b
bash $HOME/Worktrees/rang/fp-g3-spectral/research/results/g3-spectral-scripts/id_run.sh $O/bin/gemclean-main-0cb508b main s1 def
cd $HOME/Worktrees/rang/fp-g3-spectral
.venv/bin/python research/results/g3-spectral-scripts/identity.py main s1-def
