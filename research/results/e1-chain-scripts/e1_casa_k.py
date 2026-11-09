"""Post hoc probe (research/e1-chain.md 7): CASA 6.7.6.14 gaincal K on m32's
flux calibrator with the flags of the flag stage (the Tricolour copy, -04),
refant m000, solint inf, nothing pre-applied, as CARACal's first K; exports
the delays. Runs in rang-o-casa: /opt/casa/bin/python -I e1_casa_k.py MS OUT."""

import json
import sys

import numpy as np
from casatasks import gaincal
from casatools import table

ms, out = sys.argv[1], sys.argv[2]
gaincal(
    vis=ms,
    caltable=out + "/casa.K",
    field="J1939-6342",
    gaintype="K",
    solint="inf",
    refant="m000",
    minsnr=3.0,
    minblperant=4,
)
tb = table()
tb.open(out + "/casa.K")
res = {
    "time": tb.getcol("TIME").tolist(),
    "antenna": tb.getcol("ANTENNA1").tolist(),
    "fparam": np.asarray(tb.getcol("FPARAM"))[:, 0, :].T.tolist(),
    "flag": np.asarray(tb.getcol("FLAG"))[:, 0, :].T.tolist(),
}
tb.close()
with open(out + "/casa_k.json", "w") as fh:
    json.dump(res, fh)
