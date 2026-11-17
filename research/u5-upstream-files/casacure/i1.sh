cd /dev/shm/u5cc; W=/dev/shm/u5cc/w; rm -rf $W/i1-*
for b in cc pc; do echo "## $b"; $b/bin/python -I /mnt/d/rang/scratch/u5/casacure/i1.py $b $W/i1-$b 2>&1; done
echo "## pc opens cc result"; pc/bin/python -I -c "import casacore.tables as T; t=T.table('$W/i1-cc',ack=False); print(t.getcol('FLAG').shape)" 2>&1 | tail -1
echo "## cc opens cc result"; cc/bin/python -I -c "from casacure import tables as T; t=T.table('$W/i1-cc',ack=False); print(t.nrows(), t.getdminfo())" 2>&1 | tail -1
