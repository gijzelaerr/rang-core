#!/usr/bin/env bash
# build.sh WORKTREE OUTNAME : build the gemclean profile binary and copy it to the outputs dir
set -euo pipefail
export PATH=$HOME/.local/bin:$HOME/.cargo/bin:$PATH
W=$1; NAME=$2
O=/mnt/d/rang/outputs/20261106-g2-memory/bin
mkdir -p $O
cd $W/core
flock ~/.rang-heavy.lock cargo +1.93 build --offline --profile gemclean --bin gemclean 2>&1 | tail -3
T=$(cargo +1.93 metadata --format-version 1 --no-deps --offline | python3 -c 'import sys,json;print(json.load(sys.stdin)["target_directory"])')
cp $T/gemclean/gemclean $O/$NAME
sha256sum $O/$NAME
