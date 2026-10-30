"""Compare a core prospective result with an oracle (research/core-phase3b.md).

Usage:
    python examples/compare_core_prospective.py <core result.json> <oracle.json> <receipt.json>

The oracle is either the archive (its `raw_result_projection` is used) or a
host reproduction's raw `result.json`. Field classes follow the frozen
criteria 1-5; the receipt also carries the reported margins (criterion 6).
"""

# Thin wrapper (task P9, research/p9-cli.md): the rules, output, receipt
# and exit status live in rangtoy.core_compare ("prospective"); also
# `rang-core prospective compare ...`.

import sys

from rangtoy.core_compare import main

if __name__ == "__main__":
    sys.exit(main("prospective"))
