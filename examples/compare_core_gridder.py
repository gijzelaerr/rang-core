"""Pixel comparison of two sets of dirty and PSF FITS images
(research/core-c-gridder.md, criteria 4 and 7).

    python examples/compare_core_gridder.py REFERENCE CANDIDATE OUTPUT.json

REFERENCE and CANDIDATE are directories holding `<label>-dirty.fits` and
`<label>-psf.fits` for the fifteen archived imaging jobs. For every job and
kind the script reports the maximum absolute difference, the RMS difference,
the maximum difference relative to the reference peak, and whether the WCS
keys agree (floats to 1e-9 degrees). Running it on the archive against the
WSClean rerun is the comparator precondition; on the archive against the
core output it is the measurement.
"""

# Thin wrapper (task P9, research/p9-cli.md): the rules, output, receipt
# and exit status live in rangtoy.core_compare ("gridder"); also
# `rang-core gridder compare ...`.

import sys

from rangtoy.core_compare import main

if __name__ == "__main__":
    sys.exit(main("gridder"))
