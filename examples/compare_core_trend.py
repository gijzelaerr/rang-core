"""Compare a trend result on the core mirror with the archive (research/core-phase3-trend.md).

Usage:
    python examples/compare_core_trend.py <trend result.json> <archive.json> <receipt.json> [--posthoc-slope-scale]
"""

# Thin wrapper (task P9, research/p9-cli.md): the rules, output, receipt
# and exit status live in rangtoy.core_compare ("trend"); also
# `rang-core trend compare ...`.

import sys

from rangtoy.core_compare import main

if __name__ == "__main__":
    sys.exit(main("trend"))
