cd /dev/shm/u5cc; W=/dev/shm/u5cc/w
for b in cc pc; do rm -rf $W/c-$b; cp -r $W/pc-addcols $W/c-$b; $b/bin/python -I /mnt/d/rang/scratch/u5/casacure/ac2.py $b $W/c-$b 2>&1
echo "## pc reads $b-added CORRECTED_DATA"; pc/bin/python -I -c "
import casacore.tables as T; t=T.table('$W/c-$b',ack=False)
print('iscelldefined', t.iscelldefined('CORRECTED_DATA',0))
for f in (lambda: t.getcell('CORRECTED_DATA',0).shape, lambda: t.getcol('CORRECTED_DATA').shape, lambda: (t.getcol('TIME')[-1], t.getcol('DATA').shape)):
    try: print(f())
    except Exception as e: print('raises', str(e)[:120])
print({k:(v['TYPE'],v['NAME'],list(v['COLUMNS'])) for k,v in t.getdminfo().items()})
" 2>&1; done
echo "## pc reads a-cc (scalar WEIGHT added by cc)"; pc/bin/python -I -c "
import casacore.tables as T; t=T.table('$W/a-cc',ack=False); print(t.getcol('TIME')[-1], t.getcol('DATA').shape, t.getcol('WEIGHT').shape, float(abs(t.getcol('DATA')).sum()))"
