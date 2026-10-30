"""Compare a core imaging replay with the archived imaging result
(research/core-i-imaging-replay.md).

    python examples/compare_core_imaging.py RESULT ORACLE RECEIPT.json
        [--images CANDIDATE_DIR REFERENCE_DIR]

RESULT is a core replay ``result.json`` (or, for the comparator precondition,
the host reproduction's ``result.json``); ORACLE is
``research/results/gain-tv-next-imaging.json`` (its ``raw_result`` is
compared) or any raw ``result.json``. Fields are compared leaf by leaf under
``rangtoy.core_imaging.classify_replay`` with task A's tolerances. With
``--images`` the dirty and PSF FITS of CANDIDATE_DIR are compared pixel by
pixel with REFERENCE_DIR. Exit status 1 when anything fails.
"""

# Thin wrapper (task P9, research/p9-cli.md): the rules, output, receipt
# and exit status live in rangtoy.core_compare ("imaging"); also
# `rang-core imaging compare ...`.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from rangtoy.core_compare import main

if __name__ == "__main__":
    sys.exit(main("imaging"))
