cd /dev/shm/u5cc; W=/dev/shm/u5cc/w; rm -rf $W/i1b-*
for b in cc pc; do echo "## $b"; $b/bin/python -I /mnt/d/rang/scratch/u5/casacure/i1b.py $b $W/i1b-$b 2>&1; done
for x in i1b-cc i1b-cc.ms; do echo "## pc opens $x"; pc/bin/python -I -c "import casacore.tables as T; t=T.table('$W/$x',ack=False); print(t.nrows(), t.getcol('FLAG').shape)" 2>&1 | tail -1; done
