"""Compare the core's imaging weights and Stokes I with the WSClean oracle.

Protocol: research/core-b-weighting.md. Two modes:

* ``--oracle-only``: the comparator precondition. Checks the rerun images and
  header sums against the archive, the repeated WSClean runs against the first
  runs (WSClean's own reproducibility), and the structure of the stored
  ``IMAGING_WEIGHT_SPECTRUM`` column. Prints the measured spreads and the
  tolerance the rule derives from them.
* default: runs the core on every oracle job and evaluates the frozen
  criteria 1-5 and 7, writing ``compare.json`` next to the oracle.

    .venv/bin/python examples/compare_core_weights.py outputs/core-b-20261030-01
"""

# Thin wrapper (task P9, research/p9-cli.md): the rules, output, receipt
# and exit status live in rang.core_compare ("weights"); also
# `rang-core weights compare ...`.

import sys

from rang.core_compare import main

if __name__ == "__main__":
    sys.exit(main("weights"))
