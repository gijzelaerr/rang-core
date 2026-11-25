import json,sys
r=json.load(open(sys.argv[1]))
print({k:r[k] for k in ('rows_heldout','heldout_rows_dropped_flagged_gain','insample_rows_dropped_flagged_gain','seconds')})
for n,x in r['results'].items(): print(n, 'H', round(x['H_heldout'],5), '+-', round(x['H_heldout_se'],5), 'in', round(x['H_insample'],5), [(round(d['dH'],5),round(d['se'],5),d['reading'][:5]) for d in x['dH']], x.get('heldout_rows_offaxis_converged_fraction'), x.get('H_heldout_converged_rows'), x.get('H_heldout_other_rows'))
for p,x in r['pairs'].items(): print(p, round(x['dH'],5), round(x['se'],5), x['reading'])
