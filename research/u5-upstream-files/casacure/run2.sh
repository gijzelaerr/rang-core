set -u
cd /dev/shm/u5cc
S=/mnt/c/Users/gijsm/Github/rang/.claude/worktrees/u5-upstream-b8efe4/research/u5-upstream-files/casacure/probe.py
W=/dev/shm/u5cc/w
for b in cc pc; do echo "### measures $b"; $b/bin/python -I $S $b $W measures 2>&1; done
echo "### SIGBUS"; pc/bin/python -I $S pc $W mktsm
for b in cc pc; do rm -rf $W/t-$b; cp -r $W/pc-tsm $W/t-$b; echo "### truncate $b"; $b/bin/python -I $S $b $W truncate $W/t-$b 2>&1; echo "exit=$?"; done
echo "### describe"; pc/bin/python -I $S pc $W mkdescribe
for b in cc pc; do echo "### describe $b"; $b/bin/python -I $S $b $W describe $W/pc-describe 2>&1; done
echo "### addcols"; pc/bin/python -I $S pc $W mkaddcols
for b in cc pc; do rm -rf $W/a-$b; cp -r $W/pc-addcols $W/a-$b; echo "### addcols $b"; $b/bin/python -I $S $b $W addcols $W/a-$b 2>&1; done
echo "### pc reads cc addcols"; pc/bin/python -I -c "import casacore.tables as T;t=T.table('$W/a-cc',ack=False);print(t.colnames(), t.getcol('CORRECTED_DATA').shape, t.getcol('TIME')[-1])"
echo "### 13"; pc/bin/python -I $S pc $W mk13
cat > $W/mf.py <<'P'
import casacore.tables as T, sys
T.table(sys.argv[1], T.maketabdesc([T.makescacoldesc("X", 0.0)]), nrow=2, ack=False, dminfo={}).close()
P
echo "### 1b: does cc leave a partial table?"; ls $W/cc-tcsm-var; ls $W/pc-tcsm-var 2>&1
