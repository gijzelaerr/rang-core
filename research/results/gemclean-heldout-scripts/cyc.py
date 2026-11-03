import json
S='/home/gijsm/Build/tmp/20261103-gemclean-heldout/sim/gemclean/'
for d in 'h1 h2 h3 h4'.split():
    r=json.load(open(S+f'{d}-abs-nominres-fast-j16-report.json'))['run']
    print(d,[(c['components'],round(c['peak_start']*1e3,3),c['stop'][:4],round(c['stale_linf']*1e6,1)) for c in r['cycles']],'maxgap',r['max_abs_gap_relative'],'asc',r['ascending_major_cycles'])
