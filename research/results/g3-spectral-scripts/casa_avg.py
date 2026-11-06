"""casa_avg.py IN OUT: CASA 6.7.6 mstransform, DATA averaged over 2 channels (criterion E)."""

import sys

from casatasks import mstransform

mstransform(
    vis=sys.argv[1],
    outputvis=sys.argv[2],
    datacolumn="data",
    chanaverage=True,
    chanbin=2,
)
