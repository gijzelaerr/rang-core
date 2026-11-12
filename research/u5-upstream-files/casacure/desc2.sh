cd /dev/shm/u5cc; D=/mnt/c/Users/gijsm/Github/rang/.claude/worktrees/u5-upstream-b8efe4/research/u5-upstream-files/casacure
for b in cc pc; do W=/dev/shm/u5cc/d-$b; rm -rf $W; mkdir -p $W/x; f=$W/x/s.py; cp $D/snip_desc.py $f
 [ $b = pc ] && sed -i 's/from casacure.tables import/from casacore.tables import/' $f
 echo "### desc $b"; (cd $W && /dev/shm/u5cc/$b/bin/python -I $f 2>&1); done
for r in cc pc; do for w in cc pc; do echo "### $r reads $w desc.tab"; /dev/shm/u5cc/$r/bin/python -I -c "
import sys
if '$r'=='cc':
    from casacure import tables as T
else:
    import casacore.tables as T
t=T.table('/dev/shm/u5cc/d-$w/desc.tab',ack=False)
print([(c, t.getcoldesc(c)['dataManagerType'], t.getcoldesc(c)['dataManagerGroup']) for c in ('TIME','DATA')])
print({k:v for k,v in t.getdminfo()['*2']['SPEC']['HYPERCUBES']['*1'].items() if k!='ID'})"; done; done
echo "### pc opens cc tsm8.tab"; /dev/shm/u5cc/pc/bin/python -I -c "import casacore.tables as pt; pt.table('/dev/shm/u5cc/d-cc/tsm8.tab', ack=False)" 2>&1 | tail -1
