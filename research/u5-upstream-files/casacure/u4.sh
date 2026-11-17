cd /dev/shm/u5cc; U=/mnt/c/Users/gijsm/Github/rang/.claude/worktrees/u5-upstream-b8efe4/research/u4-upstream-files
W=/dev/shm/u5cc/u4; rm -rf $W; mkdir -p $W
echo "## #24"; pc/bin/python -I $U/casacure_write.py $W >/dev/null 2>&1; cc/bin/python -I $U/casacure_read.py $W 2>&1 | head -20
echo "## #28"; cc/bin/python -I $U/casacure_write_side.py cure $W 2>&1 | tail -8; pc/bin/python -I $U/casacure_write_side.py core $W 2>&1 | tail -6
echo "## #29"; cc/bin/python -I $U/casacure_float_matrix.py $W casacure 2>&1 | tail -12
echo "## #25"; cc/bin/python -I $U/casacure_ragged_snippet.py casacure $W 2>&1 | tail -3
