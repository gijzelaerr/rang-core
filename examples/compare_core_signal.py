"""Compare a core signal-track result with an oracle (research/core-phase3c-b.md).

Usage:
    python examples/compare_core_signal.py <core result.json> <oracle.json> <receipt.json>

The oracle is the archive (its `raw_result` is used) or a host reproduction's
result.json. Field classes follow the frozen criteria 1-5.
"""

# Thin wrapper (task P9, research/p9-cli.md): the rules, output, receipt
# and exit status live in rangtoy.core_compare ("signal"); also
# `rang-core signal compare ...`.

import sys

from rangtoy.core_compare import main

if __name__ == "__main__":
    sys.exit(main("signal"))
