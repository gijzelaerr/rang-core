"""Comparator for the Tricolour port (research/core-d-tricolour.md).

Usage:
    python examples/compare_core_flags.py archive-host <archive.json> <host-run> outputs/<fresh>
    python examples/compare_core_flags.py run <core-run> <host-run> <oracle-dir> outputs/<fresh>

`archive-host` is the protocol precondition: the archived control records in
`research/results/gain-tv-caracal.json` must agree with the host reproduction
`outputs/tv-caracal-wsl-20261029-01` before the host's flag snapshots are used
as the oracle. `run` applies the frozen criteria 1-5 to a core run. Both write
`result.json` into a fresh directory and exit non-zero on failure.
"""

# Thin wrapper (task P9, research/p9-cli.md): the rules, output, receipt
# and exit status live in rangtoy.core_compare ("flags"); also
# `rang-core flags compare ...`.

import sys

from rangtoy.core_compare import main

if __name__ == "__main__":
    sys.exit(main("flags"))
