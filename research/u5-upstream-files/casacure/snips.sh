cd /dev/shm/u5cc; D=/mnt/c/Users/gijsm/Github/rang/.claude/worktrees/u5-upstream-b8efe4/research/u5-upstream-files/casacure
cp /dev/shm/u5cc/w/ac.py $D/ac.py
for b in cc pc; do
  W=/dev/shm/u5cc/s-$b; rm -rf $W; mkdir -p $W/x
  for s in measures taql desc unwritten addcols_cells; do
    f=$W/x/snip_$s.py; cp $D/snip_$s.py $f
    if [ $b = pc ]; then sed -i -e 's/from casacure.tables import/from casacore.tables import/' -e 's/from casacure.measures import/from casacore.measures import/' $f; fi
    echo "### $s $b"; s0=$(date +%s.%N); (cd $W && /dev/shm/u5cc/$b/bin/python -I $f 2>&1 | sed "s#$W#<dir>#g"); 2>/dev/null; echo "wall $(echo "$(date +%s.%N)-$s0"|bc) s"
  done
  echo "### addcols_cells_read (pc reads $b-written)"; (cd $W && /dev/shm/u5cc/pc/bin/python -I $D/snip_addcols_cells_read.py 2>&1 | sed "s#$W#<dir>#g")
  echo "### pc opens $b tcsm0.tab"; (cd $W && /dev/shm/u5cc/pc/bin/python -I -c "import casacore.tables as pt; pt.table('tcsm0.tab', ack=False).getcol('FLAG')" 2>&1 | tail -1)
  echo "### pc opens $b tcsm4.tab"; (cd $W && /dev/shm/u5cc/pc/bin/python -I -c "import casacore.tables as pt; pt.table('tcsm4.tab', ack=False).getcol('FLAG')" 2>&1 | tail -1)
done
