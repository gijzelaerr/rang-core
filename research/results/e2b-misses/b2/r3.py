# Rehearsal step C: open the repaired table and run b2_cols' restore logic (without hashes).
import sys
from casacore.tables import table
ms = sys.argv[1]
t = table(ms, readonly=False, ack=False)
print("opened", sorted(t.colnames()))
t.removecols([c for c in ("CORRECTED_DATA", "FLAG") if c in t.colnames()])
t.renamecol("E2C_SAVE_CORRECTED_DATA", "CORRECTED_DATA")
t.renamecol("E2C_SAVE_FLAG", "FLAG")
t.putcol("FLAG_ROW", t.getcol("E2C_SAVE_FLAG_ROW"))
t.removecols(["E2C_SAVE_FLAG_ROW"])
print("restored", sorted(t.colnames()))
t.close()
t = table(ms, ack=False); print("reopen ok", t.nrows(), t.getcol("CORRECTED_DATA", 0, 1).shape); t.close()
