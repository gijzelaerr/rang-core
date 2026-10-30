"""Compare a core injection campaign with an archive (research/core-phase3.md).

Usage:
    python examples/compare_core_injections.py <core result.json> <archive.json> <receipt.json>

Walks the archive and compares every field by the frozen classes: exact
decisions and counts (criterion 2), well-posed floats to 1e-9 relative
(criterion 3), distances to the clean solve to 1e-9 relative or 1e-12
absolute (criterion 4), injection metadata floats to 1e-12 relative
(criterion 1), and excluded fields (criterion 5). Writes a JSON receipt and
exits nonzero on any failure.
"""

# Thin wrapper (task P9, research/p9-cli.md): the rules, output, receipt
# and exit status live in rang.core_compare ("injections"); also
# `rang-core injections compare ...`.

import sys

from rang.core_compare import main

if __name__ == "__main__":
    sys.exit(main("injections"))
