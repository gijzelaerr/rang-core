import json,sys
S='/home/gijsm/Build/tmp/20261103-gemclean-heldout/real/run/'
for n in ('cal3-003-gem','cal2-003-gem','cal2-001-gem'):
    r=json.load(open(S+n+'-report.json')); run=r['run']
    print(n,'ascending',run['ascending_major_cycles'],'maxgap',run['max_abs_gap_relative'],'peakmem',r.get('peak_memory_bytes'),'stop',run['stop'],'tau',run['tau'])
    for c in run['cycles']:
        print({a:(float('%.4g'%b) if isinstance(b,float) else b) for a,b in c.items() if not isinstance(b,(list,dict))})
