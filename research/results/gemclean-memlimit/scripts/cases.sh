#!/bin/bash
# SPDX-License-Identifier: MIT
# The F and V cases of research/gemclean-memlimit.md section 3 (and clarification 1), in order.
S=/c/Users/gijsm/Worktrees/rang/gemclean-memlimit/research/results/gemclean-memlimit/scripts/run.sh
O=/d/rang/outputs/20261128-gemclean-memlimit
H=$O/H/pilot.ms; B=$O/base/pilot.ms
run() { bash $S image "$@"; }
run F1-bin $H 4096 1e-6 bin -memory-limit 1000
run F2-bin $H 2048 1e-6 bin -memory-limit 1000
run F3-bin $H 4096 1e-4 bin -memory-limit 1000
run F4-bin $H 2048 1e-4 bin -memory-limit 1000
run F1 $H 4096 1e-6 ext -memory-limit 1000
run F2 $H 2048 1e-6 ext -memory-limit 1000
run F3 $H 4096 1e-4 ext -memory-limit 1000
run F4 $H 2048 1e-4 ext -memory-limit 1000
run V1 $B 4096 1e-6 ext -memory-limit 1000
run V1-plain $B 4096 1e-6 ext
run V2 $B 2048 1e-6 ext -memory-limit 1000
run V3 $H 3072 1e-6 ext -memory-limit 1000
run V4 $B 4096 1e-4 ext -memory-limit 1000
run V5 $H 3072 1e-4 ext -memory-limit 1000
echo cases done
