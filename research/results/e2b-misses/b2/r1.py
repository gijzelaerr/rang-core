# Rehearsal step A: replicate the damaged state on a small copy.
import os, numpy as np
from casacore.tables import table, makecoldesc
ms = "/w/t.ms"
t = table(ms, readonly=False, ack=False)
t.renamecol("CORRECTED_DATA", "E2C_SAVE_CORRECTED_DATA")
cell = list(t.getcell("DATA", 0).shape)
desc = t.getcoldesc("E2C_SAVE_CORRECTED_DATA")
desc.update({"shape": np.array(cell), "ndim": len(cell), "option": 5, "_c_order": True,
             "dataManagerType": "TiledColumnStMan", "dataManagerGroup": "E2CCasaCorrected"})
desc.pop("maxlen", None)
t.addcols(makecoldesc("CORRECTED_DATA", desc), {"TYPE": "TiledColumnStMan", "NAME": "E2CCasaCorrected",
          "SPEC": {"DEFAULTTILESHAPE": np.array([cell[1], 128, 64])}})
t.renamecol("FLAG", "E2C_SAVE_FLAG")
t.addcols(makecoldesc("E2C_SAVE_FLAG_ROW", t.getcoldesc("FLAG_ROW")), {"TYPE": "StandardStMan", "NAME": "E2CSaveFlagRow", "SPEC": {}})
t.putcol("E2C_SAVE_FLAG_ROW", t.getcol("FLAG_ROW"))
dm = t.getdminfo("E2C_SAVE_FLAG"); dm["NAME"] = "E2CFlagCasa"; dm["SPEC"].pop("HYPERCUBES", None)
t.addcols(makecoldesc("FLAG", t.getcoldesc("E2C_SAVE_FLAG")), dm)
t.putcol("FLAG", t.getcol("E2C_SAVE_FLAG"))
print({c: t.getdminfo(c)["SEQNR"] for c in ("CORRECTED_DATA", "E2C_SAVE_FLAG_ROW", "FLAG")})
t.close()
print(sorted(f for f in os.listdir(ms) if f.startswith("table.f")))
