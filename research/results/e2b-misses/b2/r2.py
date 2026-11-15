# Rehearsal step B: a twin header (same seqnr, one column) for the missing
# TiledColumnStMan header: seq dummy managers first, so the target gets SEQNR seq.
import sys, os, shutil, numpy as np
from casacore.tables import table, makecoldesc, makescacoldesc, maketabdesc
seq, nrows, twin = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
cell = [4096, 4]
cols = [makescacoldesc(f"D{i}", 0, datamanagertype="StandardStMan", datamanagergroup=f"Dummy{i}") for i in range(seq)]
desc = {"valueType": "complex", "dataManagerType": "TiledColumnStMan", "dataManagerGroup": "E2CCasaCorrected",
        "option": 5, "maxlen": 0, "comment": "", "ndim": 2, "shape": np.array(cell), "_c_order": True, "keywords": {}}
cols.append(makecoldesc("CORRECTED_DATA", desc))
dmi = {f"*{i+1}": {"TYPE": "StandardStMan", "NAME": f"Dummy{i}", "SPEC": {}, "COLUMNS": [f"D{i}"]} for i in range(seq)}
dmi[f"*{seq+1}"] = {"TYPE": "TiledColumnStMan", "NAME": "E2CCasaCorrected",
                     "SPEC": {"DEFAULTTILESHAPE": np.array([4, 128, 64])}, "COLUMNS": ["CORRECTED_DATA"]}
shutil.rmtree(twin, ignore_errors=True)
tw = table(twin, maketabdesc(cols), nrow=nrows, dminfo=dmi, ack=False)
print("seqnr", tw.getdminfo("CORRECTED_DATA")["SEQNR"])
tw.close()
print(sorted(os.listdir(twin))[-4:])
