#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# W1 M3 checks (research/w1-writeback.md, tolerances 3e and 7): an MS of
# 8,192 rows x 1,024 channels x 4 correlations written by the core writer,
# then the memory run and SIGKILL at 8 times spread over a FLAG write.
# Usage: bash tools/oracles/w1/m3.sh /mnt/d/rang/w1/m3-20261106-NN
set -euo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
py="$root/.venv/bin/python"
ex="$root/examples/w1_writeback.py"
run=$(realpath -m "$1")
if [ -e "$run" ]; then echo "$run exists; choose a fresh run directory" >&2; exit 1; fi
mkdir -p "$run/timing" "$run/logs"
git -C "$root" rev-parse HEAD > "$run/code-commit.txt"
git -C "$root" status --short > "$run/code-status.txt"
t() { local name=$1; shift; echo "## $name"; /usr/bin/time -f "%e %M %x" -o "$run/timing/$name.txt" "$@" > "$run/logs/$name.log" 2>&1; }
# Data generation takes the heavy lock (AGENTS.md; other agents share the host).
t make flock "$HOME/.rang-heavy.lock" "$py" "$ex" make "$run/m3.ms" 8192 1024 --flag ssm --seed 20261106
du -sb "$run/m3.ms" > "$run/m3-size.txt"
cp -r "$run/m3.ms" "$run/m3-mem.ms"
t memory "$py" "$ex" memory "$run/m3-mem.ms" "$run/memory.json"
rm -rf "$run/m3-mem.ms" "$run/m3-mem.ms.flagversions"
t kill "$py" "$ex" kill "$run/m3.ms" 8 20261106 "$run/kill.json"
rm -rf "$run/m3.ms.kill" "$run/m3.ms.kill.flagversions"
