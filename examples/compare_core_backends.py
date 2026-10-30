"""Compare two `tools/core-j-suite.sh` output directories file by file
(research/core-j-packaging.md, criterion 6).

    python examples/compare_core_backends.py REFERENCE CANDIDATE RECEIPT.json [IGNORE,...]

Every `.npz` and `.npy` array must be byte-equal, every FITS image's data
and header cards equal, every other file byte-equal, and every JSON leaf
equal except under the volatile keys listed in VOLATILE (wall times, memory,
dates, library and code hashes, interpreter and backend names, load) and
except strings that name the same file under the two run directories; both
are counted and reported. Logs, `.time` files and `timings.tsv`
are skipped, as are the top-level entries named in the optional
comma-separated IGNORE list; symbolic links are not followed. Exit status 1
on any difference or missing file.
"""

# Thin wrapper (task P9, research/p9-cli.md): the rules, output, receipt
# and exit status live in rangtoy.core_compare ("backends"); also
# `rang-core backends compare ...`.

import sys

from rangtoy.core_compare import main

if __name__ == "__main__":
    sys.exit(main("backends"))
