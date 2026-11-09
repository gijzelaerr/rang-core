#!/usr/bin/env bash
# build_linux.sh COMMIT TAR : the gemclean profile binary of COMMIT built in WSL (rustc 1.93), for
# the same-OS comparison of research/g7-defaults.md (section 1). TAR is `git archive COMMIT` made on
# Windows (a Windows worktree's .git does not resolve from WSL); target dir in
# ~/Build/tmp/20261109-g7-target (removed at the end of the task).
# Run under tools/heavy_lock.py.
set -eu
commit=$1
tar=$2
T=$HOME/Build/tmp/20261109-g7-target
S=$HOME/Build/tmp/20261109-g7-src
rm -rf "$S"
mkdir -p "$S" "$T"
tar -x -C "$S" -f "$tar"
source "$HOME/.cargo/env"
cd "$S/core"
CARGO_TARGET_DIR=$T cargo +1.93 build --profile gemclean --bin gemclean
echo "$commit $(sha256sum "$T/gemclean/gemclean")" | tee "$T/gemclean/gemclean.provenance"
