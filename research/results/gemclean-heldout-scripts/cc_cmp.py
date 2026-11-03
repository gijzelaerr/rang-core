import importlib.util, json, sys, numpy as np
from pathlib import Path
W=Path("/home/gijsm/Worktrees/rang/gemclean-heldout/examples/gemclean_heldout_real.py")
spec=importlib.util.spec_from_file_location("real",W); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
Z=Path("/mnt/d/rang/data/eso137-pilot/ESO137/ms1_target.zarr"); main=m.main_group(Z)
c=np.load(sys.argv[1]); res={}
for r in c["rows"]:
    r=int(r); ch=r//50000; i=r-ch*50000
    D=m.cube(main,"DATA",ch)[i]; F=m.cube(main,"FLAG",ch)[i]; W_=m.cube(main,"WEIGHT_SPECTRUM",ch)[i]; U=m.row_column(main,"UVW",ch)[i]
    res[r]=dict(data=bool(np.array_equal(D,c[f"data_{r}"],equal_nan=True)),flag=bool(np.array_equal(F,c[f"flag_{r}"])),wt=bool(np.array_equal(W_,c[f"wt_{r}"])),uvw=bool(np.array_equal(U,c[f"uvw_{r}"])))
print(json.dumps(res)); json.dump(res,open(sys.argv[2],"w"),indent=1)
