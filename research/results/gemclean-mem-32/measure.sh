#!/bin/bash
# gemclean-mem-32 measurement (note section 4): build arm A + 0, then main and
# arm A on case Q in one hold, then arm 0's attribution of case I.
set -u
source ~/.rang-env.sh
R=/home/gijs/rang-data/outputs/gemclean-mem-32-20261121
cd ~/Worktrees/rang/gemclean-mem-32-arm
s=$(date +%s)
cargo build -q --profile gemclean --bin gemclean --manifest-path core/Cargo.toml || exit 1
cp core/target/gemclean/gemclean $R/gemclean-arm 2>/dev/null || cp target/gemclean/gemclean $R/gemclean-arm
echo "$(date -u +%FT%TZ) build $(( $(date +%s) - s )) s" >> $R/profile.log
bash $R/profile.sh mq aq ai
