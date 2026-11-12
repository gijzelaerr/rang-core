cd /dev/shm/u5cc; W=/dev/shm/u5cc/w
S=/mnt/c/Users/gijsm/Github/rang/.claude/worktrees/u5-upstream-b8efe4/research/u5-upstream-files/casacure/probe.py
echo "## cc reads pc-written never-written FLAG_CATEGORY"; cc/bin/python -I -c "
from casacure import tables as T; t=T.table('$W/pc-unwritten',ack=False)
print('iscelldefined', t.iscelldefined('FLAG_CATEGORY',0), 'getcol', t.getcol('FLAG_CATEGORY').shape, t.getcol('FLAG_CATEGORY').dtype, 'getcell', repr(t.getcell('FLAG_CATEGORY',0)), 'ndim', t.getcoldesc('FLAG_CATEGORY')['ndim'])"
echo "## pc reads cc-written never-written FLAG_CATEGORY"; pc/bin/python -I -c "
import casacore.tables as T; t=T.table('$W/cc-unwritten',ack=False)
print('iscelldefined', t.iscelldefined('FLAG_CATEGORY',0))
try: print(t.getcell('FLAG_CATEGORY',0).shape)
except Exception as e: print('raises', str(e)[:100])"
echo "## 12 raw types"; for b in cc pc; do $b/bin/python -I -c "
import sys
if '$b'=='cc':
    from casacure import tables as T
else:
    import casacore.tables as T
t=T.table('$W/$b-zero',ack=False)
for c in ('D','S','B','A','FLAG_CATEGORY'):
    try:
        v=t.getcol(c); print('$b', c, type(v).__name__, getattr(v,'dtype',None), getattr(v,'shape',len(v) if hasattr(v,'__len__') else None))
    except Exception as e: print('$b', c, 'raises', str(e)[:100])
"; done
