import json,re
from pathlib import Path
S=Path('/home/gijsm/Build/tmp/20261103-gemclean-heldout/sim')
rows={}
for ds in 'h1 h2 h3 h4'.split():
    for im in ('wsclean','gemclean'):
        j=json.load(open(S/'scores'/f'{im}-{ds}.json'))
        print(ds,im,'noise',j.get('briggs_noise'),'qtruth',j.get('q_truth'),'beam',j.get('beam_arcsec'))
        for n,r in j['jobs'].items():
            log=r.get('log') or {}
            rep=(r.get('report') or {}).get('run') or {}
            maj=rep.get('major_cycles') or log.get('major_iterations') or log.get('majors')
            comps=rep.get('components') or log.get('iterations') or log.get('components')
            rec=r.get('recovery_all',{})
            print(' ',n.replace(ds+'-abs-nominres-',''),'maj',maj,'comp',comps,'Q/Qt %.5f'%r['q_over_q_truth'],'peak uJy %.1f'%(r['exact_residual_inner_peak_abs']*1e6),'rms %.2f'%(r['exact_residual_inner_rms']*1e6),'false px',r.get('false_pixels'),'false mJy %.2f'%(r.get('false_flux_abs',0)*1e3),'flux err mJy %.2f'%(r['total_flux_error']*1e3),'rec %.4f +- %.4f fw %.4f'%(rec.get('mean',0),rec.get('std',0),rec.get('flux_weighted',0)),'px',r['model_pixels'],'neg mJy %.1f'%(r['model_flux_negative']*1e3),'ext',{k:round(v,4) for k,v in r.get('extended',{}).items()} if r.get('extended') else '', 'asc',rep.get('ascending_major_cycles'),'logkeys' if maj is None else '', list(log.keys())[:6] if maj is None else '')
