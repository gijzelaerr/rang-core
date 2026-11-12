cd /dev/shm/u5cc; W=/dev/shm/u5cc/w
S=/mnt/c/Users/gijsm/Github/rang/.claude/worktrees/u5-upstream-b8efe4/research/u5-upstream-files/casacure/probe.py
cat > $W/ac.py <<'P'
import os, sys, numpy as np
if sys.argv[1] == "cc":
    from casacure import tables as T
else:
    import casacore.tables as T
path = sys.argv[2]
ls = lambda: {f: os.path.getsize(os.path.join(path, f)) for f in sorted(os.listdir(path)) if f.startswith("table.f")}
print("before", ls())
t = T.table(path, readonly=False, ack=False)
t.addcols(T.makescacoldesc("WEIGHT", 0.0))
t.flush(); t.close()
print("after ", ls())
t = T.table(path, ack=False); print({k: (v["TYPE"], v["NAME"], list(v["COLUMNS"])) for k, v in t.getdminfo().items()})
P
for b in cc pc; do rm -rf $W/a-$b; cp -r $W/pc-addcols $W/a-$b; echo "### addcols scalar no dminfo $b"; $b/bin/python -I $W/ac.py $b $W/a-$b 2>&1; done
echo "### 13 cc open MemoryStMan"; cc/bin/python -I $S cc $W multifile $W/pc-mem
