cd /dev/shm/u5cc
for b in cc pc; do W=/dev/shm/u5cc/tt-$b; rm -rf $W; mkdir -p $W; echo "## $b"; $b/bin/python -I /mnt/d/rang/scratch/u5/casacure/tsmtypes.py $b $W 2>&1; done
echo "## pc reads cc-written"; for f in /dev/shm/u5cc/tt-cc/*.tab; do pc/bin/python -I -c "import casacore.tables as T,sys; t=T.table('$f',ack=False); x=t.getcol('X'); print('$(basename $f)', x.dtype, x.shape, float(abs(x).sum()))" 2>&1 | tail -1; done
