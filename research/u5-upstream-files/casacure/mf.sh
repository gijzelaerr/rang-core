cd /dev/shm/u5cc; U=/mnt/c/Users/gijsm/Github/rang/.claude/worktrees/u5-upstream-b8efe4/research/u4-upstream-files
W=/dev/shm/u5cc/u4; echo "table.storage.option: multifile" > $W/aipsrc
CASARCFILES=$W/aipsrc pc/bin/python -I $U/casacure_write_mf.py $W 2>&1 | tail -2
cc/bin/python -I $U/casacure_read.py $W 2>&1 | grep -i multi
