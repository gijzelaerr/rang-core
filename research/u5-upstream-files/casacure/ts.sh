for r in cc pc; do /dev/shm/u5cc/$r/bin/python -I -c "
if '$r'=='cc':
    from casacure import tables as T
else:
    import casacore.tables as T
t=T.table('/dev/shm/u5cc/d-cc/desc.tab',ack=False); s=t.getdminfo()['*2']['SPEC']; print('$r', 'DEFAULTTILESHAPE', s.get('DEFAULTTILESHAPE'), 'MAXIMUMCACHESIZE', s.get('MAXIMUMCACHESIZE'))"; done
