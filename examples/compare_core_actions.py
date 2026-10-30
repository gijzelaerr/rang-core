"""Compare a core actions result with an oracle (research/core-phase3-actions.md).

Usage:
    python examples/compare_core_actions.py <core result.json> <oracle.json> <receipt.json>

The oracle is the archive or a host reproduction's result.json. Field classes
follow the frozen criteria 1-4.
"""

# Thin wrapper (task P9, research/p9-cli.md): the rules, output, receipt
# and exit status live in rang.core_compare ("actions"); also
# `rang-core actions compare ...`.

import sys

from rang.core_compare import main

if __name__ == "__main__":
    sys.exit(main("actions"))
