set -u
cd /dev/shm/u5cc
S=/mnt/c/Users/gijsm/Github/rang/.claude/worktrees/u5-upstream-b8efe4/research/u5-upstream-files/casacure/probe.py
W=/dev/shm/u5cc/w; rm -rf $W; mkdir -p $W
for p in dminfo measures taql unwritten; do for b in cc pc; do echo "### $p $b"; $b/bin/python -I $S $b $W $p 2>&1; done; done
echo "### open cc-written with pc"; pc/bin/python -I $S pc $W open $W/cc-tcsm-var $W/cc-tcsm-shape $W/cc-plain-shape 2>&1
echo "### open pc-written with cc"; cc/bin/python -I $S cc $W open $W/pc-plain-shape 2>&1
